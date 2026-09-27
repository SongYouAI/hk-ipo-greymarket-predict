# -*- coding: utf-8 -*-
"""
港股打新 · 暗盘/首日开盘预测引擎（WorkBuddy Skill 版）
----------------------------------------------------------------
移植自浏览器插件 i668-ipo-predict (core.js)，并做精细化改造：

  [A] 静态桶 → 每次实时用 i668 历史样本重算 OVER_BUCKETS
      （最近 12 个月滚动窗口），天然自带「动态校准」，
      不再依赖写死的 106 只样本常量。
  [B] S2 因子处理：原插件把 6 个因子全砍（"k=0 最好"依据偏脆）。
      改为「残差分层修正」——先取超购档中位数，再按
      保荐人/基石/国配/赛道/规模 的 *档位残差均值* 做边际修正，
      既避免与桶内已内化的均值重复计价，又吃到真实边际信息。
  [C] S3 妖股系数 0.7（裸常数）→ 用样本实测
      median(首日开盘% / 暗盘价格%) 标定。
  [D] S1 的 18C 三重计价 → 合并为单次 +5。
  [E] A+H 两处口径不一致 → 统一为回归斜率 0.238、截断 ±12。
  [F] FLAT 兜底中位数 +29.7%（右偏误导）→ 改为中性(≈0)宽区间。
  [G] 动态校准：情绪周期(冷热市)整体平移中位数；标注 FINI 后超购虚高。
  [H] 输出「暗盘收盘价区间(主) + 暗盘开盘价情绪初判(辅)」。

纯标准库，无第三方依赖。联网取数失败时明确报错，不编造。
"""
import sys, os, json, re, math, time, hmac, hashlib, urllib.request, urllib.error, urllib.parse, statistics, datetime, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRAS_PATH = os.path.join(HERE, "extras.json")
SECRET = "6680fc61c8585cfca143366eea267b67617b7c2830c1c896cd952b276db117c9"
FX_CNY2HKD = 1.09
WINDOW_MONTHS = 12           # 长期回退窗口
WINDOW_MONTHS_NEAR = 3       # 近端主窗口（分层首选）
WINDOW_MONTHS_RECENT = 6     # 次选窗口
WINDOW_DAYS_RECENT = 30      # 「当下市况」观察窗（情绪仪表盘用）
# 分层窗口（近端优先）的因果回测依据（n=66，只用该股上市前数据）：
#   固定 6 月窗口        MAE 52.66 / 最近12只 21.33 / 覆盖 56/66
#   近3月(>=5)→6月(>=3)→12月(>=3)  MAE 46.56 / 最近12只 18.49 / 覆盖 63/66  ← 采用
# 即「缩短窗口自动吸收情绪 + 不足时逐档回退」，优于加任何情绪动量/偏差校正项（后者实测更差）。

# 交易成本（HKD，2026 常见券商口径；仅用于处置方案的"打平线"估算，实际以你券商为准）
FEE_STAMP = 0.001        # 印花税 0.1%（买卖各收）
FEE_COMM = 0.0005        # 佣金 ~0.03%~0.06%，取 0.05%
FEE_PLATFORM = 15.0      # 平台费（富途暗盘 15 HKD/笔）
FEE_SETTLE = 0.000042    # 中央结算费
FEE_ALLOT = 0.010085     # 中签费 1.0085%（经纪佣金+证监会征费+交易费+财务汇报局费）

# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def num(v):
    try:
        if v is None: return None
        n = float(v)
        return n if not math.isnan(n) else None
    except Exception:
        return None

def pct(x, d=1):
    if x is None: return "—"
    return ("+" if x >= 0 else "") + f"{x:.{d}f}%"

def stars(c):
    return "★" * c + "☆" * (3 - c)

def md_off(s):
    """终端/纯文本场景：去掉 Markdown 加粗记号（HTML 报告侧由 report.rich() 转成真加粗）。"""
    return (s or "").replace("**", "")

# ---------------------------------------------------------------------------
# 数据获取（i668 API + 腾讯行情）
# ---------------------------------------------------------------------------
CACHE_DIR = os.path.join(HERE, "..", ".cache")
CACHE_TTL = int(os.environ.get("HKIPO_CACHE_TTL", "300"))   # 秒；0 = 禁用缓存

def _cache_path(path, params):
    key = path + "|" + json.dumps(params or {}, sort_keys=True)
    return os.path.join(CACHE_DIR, hashlib.sha256(key.encode()).hexdigest()[:20] + ".json")

def api_get(path, params=None, retries=4, use_cache=True):
    """带**重试退避 + 短 TTL 缓存**的接口调用。

    为什么必须做：实测连续调用会触发站点 `HTTP 429 Too Many Requests`
    （批量跑 30 只时 11 只被拒）。缓存 TTL 默认 300 秒——既避免自己把自己限流，
    又保证「最新数据」的语义（5 分钟内的市况不会变），可用环境变量 HKIPO_CACHE_TTL 调整，0=禁用。
    """
    cp = _cache_path(path, params)
    if use_cache and CACHE_TTL > 0:
        try:
            with open(cp, encoding="utf-8") as f:
                c = json.load(f)
            if time.time() - c.get("t", 0) < CACHE_TTL:
                return c["d"]
        except Exception:
            pass
    base = "/api"
    url = "https://www.i668.vip" + base + path
    a = ""
    if params:
        a = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = url + "?" + a
    i = base + path
    last = None
    for attempt in range(retries):
        t = str(int(time.time()))
        msg = t + i + a + "" + SECRET
        sig = hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
        req = urllib.request.Request(url, headers={
            "X-Timestamp": t, "X-Sign": sig,
            "Referer": "https://www.i668.vip/", "Origin": "https://www.i668.vip/"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode())
            if use_cache and CACHE_TTL > 0:
                try:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    with open(cp, "w", encoding="utf-8") as f:
                        json.dump({"t": time.time(), "d": d}, f, ensure_ascii=False)
                except Exception:
                    pass
            return d
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 or 500 <= e.code < 600:
                # 退避：2s → 4s → 8s（并在末次前多给一点）
                wait = 2 ** (attempt + 1)
                sys.stderr.write(f"[warn] 接口返回 {e.code}，{wait}s 后重试（第 {attempt+1}/{retries} 次）\n")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise SystemExit(f"i668 接口调用失败（已重试 {retries} 次）：{last}\n"
                     f"提示：这是站点限流或网络问题，稍等 1~2 分钟再试即可；本引擎每次都会实时取数，不缓存过期数据（当前 TTL {CACHE_TTL}s）。")

def to_gtimg_code(code):
    code = str(code)
    if code[0] in "65": return "sh" + code
    if code[0] in "84": return "bj" + code
    return "sz" + code

def fetch_gtimg(codes):
    url = "https://qt.gtimg.cn/q=" + ",".join(codes)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        txt = r.read().decode("gbk", errors="replace")
    out = {}
    for line in txt.split(";"):
        m = re.search(r'v_(\w+)="([^"]*)"', line)
        if m:
            out[m.group(1)] = m.group(2).split("~")
    return out

def gtimg_pct(arr):
    if not arr: return None
    ti = next((i for i, x in enumerate(arr)
               if re.search(r'\d{4}/\d{2}/\d{2}', x) or re.fullmatch(r'\d{12,14}', x)), -1)
    if ti < 0: return None
    try:
        return float(arr[ti + 2])
    except Exception:
        return None

def gtimg_price(arr):
    try:
        return float(arr[3])
    except Exception:
        return None

# ---------------------------------------------------------------------------
# 因子库（内置 extras.json）
# ---------------------------------------------------------------------------
def load_extras():
    with open(EXTRAS_PATH, encoding="utf-8") as f:
        return json.load(f)

def build_sponsor_book(stocks, extras):
    """用**站点实时数据**重建「保荐人 → 首日收盘涨幅中位数」（每次运行都重算，永远最新）。

    为什么不再沿用内置 extras['sponsors'].avg：
      ① 口径不一致——全套模型其他环节（分桶中枢、情绪）都用中位数对抗右偏，唯独保荐人用均值；
      ② 实测：全样本首日开盘中位 37.4%，而内置「均值×n 加权」基准 = 50.7%（被妖股右尾抬高 13.3pt）；
         后果是 117 只里 68 只（58%）的保荐人项被误判为扣分。
    改用站点 first_day_close_price（覆盖 110/117）实时重算，门槛 n>=3。
    """
    per = {}
    for s in stocks:
        fdc = num(s.get("first_day_close_price")); ipo = num(s.get("ipo_price"))
        if fdc is None or not ipo or ipo <= 0: continue
        # ⚠️ 剔除占位行必须**两个哨兵信号同时出现**，不能只看一个（2026-09-27 踩过）：
        #    · 信号① `openPct` 为缺失哨兵（None / 精确 0，来自 extras.json 构建期抓取）
        #    · 信号② `first_day_close_price == ipo_price` 精确相等（来自实时 API，独立数据源）
        #    只有①②同时成立才是抓取失败的占位（大金重工 66.400=66.400、爱芯元智 28.200=28.200）。
        #    ⚠️ 只看①是**过激的**：openPct 来自 extras.json、fdc 来自实时 API，是两个独立源；
        #       实测 16 只 openPct 为哨兵的股票里有 14 只 fdc 是**真实值**（−56.9%、−27.0%、+4.7%…），
        #       误剔会把保荐人基准从 15.2% 虚推到 35.1%（比不剔除更错），并静默改变全部预测区间。
        #    ⚠️ 只看②也是**不对的**：晶合集成（开盘 +11.5%）等收盘恰等于发行价，那可能是
        #       **稳价人钉在发行价的真实形态**，属于有效信号，不该丢。
        _e = extras.get("stocks", {}).get(s.get("stock_code")) or {}
        _op = num(_e.get("openPct"))
        if (_op is None or _op == 0) and abs(fdc - ipo) < 1e-9: continue
        v = (fdc / ipo - 1) * 100
        for nm in (_e.get("sp") or []):
            per.setdefault(nm, []).append(v)
    allv = [v for vs in per.values() for v in vs]
    base = statistics.median(allv) if len(allv) >= 20 else None
    book = {nm: {"n": len(vs), "med": statistics.median(vs)} for nm, vs in per.items() if len(vs) >= 3}
    return {"book": book, "base": base, "covered": len(book), "all_n": len(allv)}

def sponsor_stats(extras, code, book=None):
    """该股保荐人的加权战绩（优先运行时中位数口径，缺失时回退内置均值口径）。"""
    st = extras.get("stocks", {}).get(code, {})
    sp = st.get("sp")
    if not sp: return None
    if book and book.get("base") is not None:
        picked = [(nm, book["book"][nm]["n"], book["book"][nm]["med"]) for nm in sp if nm in book["book"]]
        if picked:
            sw = sn = 0.0
            for nm, n, med in picked:
                sw += med * n; sn += n
            return {"avg": sw / sn, "n": int(sn), "names": picked, "src": "运行时中位数口径"}
    sw = sn = 0.0
    picked = []
    for nm in sp:
        s = extras.get("sponsors", {}).get(nm)
        if not s or not s.get("n"): continue
        picked.append((nm, s["n"], s["avg"]))
        sw += s["avg"] * s["n"]; sn += s["n"]
    if not sn: return None
    return {"avg": sw / sn, "n": int(sn), "names": picked, "src": "内置均值口径(旧)"}

def sponsor_baseline(extras, book=None):
    if book and book.get("base") is not None: return book["base"]
    sw = sn = 0.0
    for s in extras.get("sponsors", {}).values():
        if not s.get("n"): continue
        sw += s["avg"] * s["n"]; sn += s["n"]
    return sw / sn if sn else None

def cornerstone_of(extras, code, stock):
    st = extras.get("stocks", {}).get(code, {})
    p = st.get("pros")
    if not p or p.get("shares") is None: return None
    if p.get("pages") is not None and p["pages"] < 100: return None
    total = num(stock.get("shares_offered"))
    if total and total > 0 and p["shares"] > total: return None
    ratio = round(p["shares"] / total * 100, 1) if (total and total > 0) else None
    return {"shares": p["shares"], "usd": p.get("usd"), "ratio": ratio,
            "hasGreen": p.get("hasGreen"), "greenPct": p.get("greenPct"),
            "stabilizer": p.get("stabilizer")}

def first_day_open(extras, code):
    """首日开盘涨幅%（来自内置因子库）。
    ⚠ 数据纪律：`openPct == 0` 是**抓取缺失值**而非真实平开——
    实测抽查 14 只中 12 只首日收盘明显 ≠ 发行价（星环科技 −27%、华健未来 −56.9%），
    而 94 只正常样本里「恰好平开」只有 3 只。故一律按缺失处理（返回 None），
    否则会把「破发后熬首日更优」的胜率从 42% 假造成 70%。"""
    st = extras.get("stocks", {}).get(code, {})
    v = num(st.get("openPct"))
    if v is None or v == 0: return None
    return v

# ---------------------------------------------------------------------------
# 赛道推断（名称关键词；诚实标注"名称推断"）
# ---------------------------------------------------------------------------
def sector_adj(name, chapter):
    n = name or ""
    ch = chapter or ""
    if re.search(r'科技|电子|半导体|芯片|智能|机器人|自动化|数控|精密|光电|芯|光伏|新能源|储能|电池|新材|材料|装备|机电|计算|云|AI|光学|传感器|通信|软件|医药|生物|医疗|健康|基因|制药|微创', n):
        a = 8
    elif re.search(r'消费|食品|饮料|零售|品牌|传媒|文娱|旅游|户外|梅|糖|蜜|宠物|生活', n):
        a = 5
    elif re.search(r'金|矿|资源|铜|锂|钢铁|化工|传统|能源|电力|环保', n):
        a = -5
    elif re.search(r'证券|保险|银行|金融', n):
        a = -2
    else:
        a = 0
    extra = 4 if re.search(r'18C', ch) else 0
    why = "名称含科技/半导体/机器人等关键词" if a > 0 else ("名称含资源/化工/金融等关键词" if a < 0 else "名称未命中任何赛道关键词")
    if extra: why += "；且为 18C 特专科技章节"
    return {"v": a + extra, "base": a, "extra": extra, "why": why}

# ---------------------------------------------------------------------------
# 样本构建 + 动态分桶（核心改造 A）
# ---------------------------------------------------------------------------
def parse_date(s):
    if not s: return None
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def build_sample(stocks, months=WINDOW_MONTHS, today=None):
    """可校准样本：**只取已发生暗盘实测**的股票（有超购 + 有暗盘涨幅 + 在窗口内上市）。

    铁律：绝不用「还没暗盘、还没上市」的股票做校准——它们的 dk 为空，天然被排除。
    """
    today = today or datetime.date.today()
    cut = today - datetime.timedelta(days=int(months * 30.5))
    rows = []
    for s in stocks:
        over = num(s.get("public_offer_subscription_multiple"))
        dk = num(s.get("dark_pool_change_pct"))
        ls = parse_date(s.get("listing_date"))
        if over is None or dk is None or ls is None: continue
        if ls < cut: continue
        rows.append({"code": s.get("stock_code"), "name": s.get("stock_name"),
                     "over": over, "dk": dk, "ls": ls,
                     "intl": num(s.get("international_subscription_multiple")),
                     "ipo": num(s.get("ipo_price")),
                     "shares": num(s.get("shares_offered"))})
    return rows

# 超购档边界（FINI 后仍沿用，但每轮实时重算中位数/分位）
BUCKET_EDGES = [0, 15, 100, 500, 1000, 3000, 6000, math.inf]
BUCKET_LABELS = ["0–15倍", "15–100倍", "100–500倍", "500–1000倍",
                 "1000–3000倍", "3000–6000倍", ">6000倍"]

def bucket_index(over):
    for i, e in enumerate(BUCKET_EDGES[:-1]):
        if over < BUCKET_EDGES[i + 1]:
            return i
    return len(BUCKET_EDGES) - 2

def _bucket_stat(vals):
    if len(vals) >= 2:
        med = statistics.median(vals)
        p25 = statistics.quantiles(vals, n=4)[0]
        p75 = statistics.quantiles(vals, n=4)[2]
        return med, med - p25, p75 - med
    if len(vals) == 1:
        return vals[0], 0.0, 0.0
    return None, None, None

def compute_buckets(sample=None, fallback=None, tiers=None):
    """分桶统计，支持**分层窗口（近端优先）**。

    `tiers` = [(样本行, 该层最低样本数, 层名), ...] 按优先级排列：
      · 逐档（超购档）取第一个「样本数 >= 该层门槛」的窗口 → 自动做到「大档吃近端、小档退长期」；
      · 这样既让近 3 个月的情绪立刻反映到中枢，又不至于让小样本档位变成噪声。
    未传 tiers 时退化为旧的「主窗 + 单一 fallback」行为。
    """
    if tiers:
        buckets = []
        for i in range(len(BUCKET_EDGES) - 1):
            chosen = None
            for rows, min_n, label in tiers:
                vals = [r["dk"] for r in rows if bucket_index(r["over"]) == i]
                if len(vals) >= min_n:
                    med, dLo, dHi = _bucket_stat(vals)
                    chosen = {"label": BUCKET_LABELS[i], "n": len(vals), "med": med,
                              "dLo": dLo, "dHi": dHi, "src": label}
                    break
            if chosen is None:      # 连最宽窗口都凑不够门槛 → 有多少用多少，并标注
                rows = tiers[-1][0]
                vals = [r["dk"] for r in rows if bucket_index(r["over"]) == i]
                med, dLo, dHi = _bucket_stat(vals)
                chosen = {"label": BUCKET_LABELS[i], "n": len(vals), "med": med,
                          "dLo": dLo, "dHi": dHi,
                          "src": (tiers[-1][2] + "（样本偏少）") if vals else "无样本"}
            buckets.append(chosen)
        return buckets
    fb = fallback or []
    sample = sample or []
    buckets = []
    for i in range(len(BUCKET_EDGES) - 1):
        vals = [r["dk"] for r in sample if bucket_index(r["over"]) == i]
        med, dLo, dHi = _bucket_stat(vals)
        n, src = len(vals), "主窗"
        if med is None and fb:
            fvals = [r["dk"] for r in fb if bucket_index(r["over"]) == i]
            med, dLo, dHi = _bucket_stat(fvals)
            n, src = len(fvals), "长期回退"
        buckets.append({"label": BUCKET_LABELS[i], "n": n, "med": med, "dLo": dLo,
                        "dHi": dHi, "src": src})
    return buckets

# ---------------------------------------------------------------------------
# 动态校准：情绪周期 / 冷热市（改造 G）
# ---------------------------------------------------------------------------
def sentiment_windows(stocks, today=None):
    """情绪仪表盘：近 30 / 90 天与全窗口的**已上市**新股实况（只统计已有暗盘实测者）。

    为什么一定要看「近 30 天」：暗盘情绪月间波动极大——实测逐月中位从 +75.6%（2026-05）
    到 −0.7%（2026-09），跨度超过 76pt。用 12 个月窗口判定"热市/冷市"会严重滞后。
    """
    today = today or datetime.date.today()
    out = {}
    for key, days in (("d30", 30), ("d90", 90), ("all", None)):
        vals = []
        for s in stocks:
            dk = num(s.get("dark_pool_change_pct"))
            ls = parse_date(s.get("listing_date"))
            if dk is None or ls is None: continue
            if days is not None and ls < today - datetime.timedelta(days=days): continue
            vals.append(dk)
        out[key] = {
            "n": len(vals),
            "med": round(statistics.median(vals), 1) if vals else None,
            "brk": round(sum(1 for x in vals if x < 0) / len(vals) * 100, 1) if vals else None,
            "up": round(sum(1 for x in vals if x > 0) / len(vals) * 100, 1) if vals else None,
        }
    return out

def compute_regime(sample, sent=None):
    """情绪周期快照。

    ⚠ 重要变更（2026-09-27，严格因果回测驱动）：**取消「固定冷热平移」**。
    实测（n=46，只用该股上市前的数据建桶）：加固定平移 MAE 40.05、中位偏差 −8.4；
    去掉后 MAE 39.4、中位偏差 −5.4、方向命中 38/46（最好）。即那个 +3/−8 的平移是**负贡献**，
    尤其在它把「近 3 个月已转冷（破发率 48%~71%）」的市场仍判为"热市＋3pt"时。
    情绪不靠拍脑袋的加减项，而是靠 ① 滚动窗口（默认近 6 个月）自动吸收，
    ② 「近 30/90 天」指标如实呈现给决策者。
    """
    if not sample:
        return {"label": "无样本", "shift": 0.0, "break_rate": None, "avg_dark": None,
                "monthly": None, "median_over": None, "sent": sent or {},
                "label_basis": "无样本", "ref_n": None, "ref_med": None, "ref_brk": None,
                "ref_up": None, "long_break_rate": None, "long_avg_dark": None, "long_n": 0}
    dks = [r["dk"] for r in sample]
    avg = statistics.median(dks)          # 中位数，防妖股右尾把均值拉偏
    brk = sum(1 for x in dks if x < 0) / len(dks)
    overs = [r["over"] for r in sample if r["over"] > 0]
    med_over = statistics.median(overs) if overs else None
    from collections import Counter
    monthly = dict(sorted(Counter(r["ls"].strftime("%Y-%m") for r in sample).items()))

    # 「当前市况」标签优先用近 30 天（样本 >=3），否则近 90 天，最后退回整窗
    ref, ref_txt = None, "近12个月窗口"
    if sent:
        for k, txt in (("d30", "近30天"), ("d90", "近90天")):
            v = sent.get(k) or {}
            if (v.get("n") or 0) >= 3 and v.get("med") is not None:
                ref, ref_txt = v, txt
                break
    if ref is None:
        ref = {"med": avg, "brk": brk * 100, "up": round(sum(1 for x in dks if x > 0) / len(dks) * 100, 1), "n": len(dks)}
        ref_txt = "近12个月窗口"
    m, b = ref["med"], ref["brk"]
    if b > 50 or (m or 0) < 0:
        label = "偏冷"
    elif b < 30 and (m or 0) > 10:
        label = "偏热"
    else:
        label = "中性"
    # ⚠ 展示纪律：标签与数字必须**同窗口**。此前 label 取近30天、break_rate/avg_dark 却取 12 个月，
    #   会出现「偏冷（破发率 20.8%）」这种自相矛盾的展示 → 现统一为 ref 窗口，并单列长期窗口备查。
    return {"label": label, "label_basis": ref_txt, "shift": 0.0,
            "ref_n": ref.get("n"), "ref_med": round(m, 1) if m is not None else None,
            "ref_brk": round(b, 1) if b is not None else None, "ref_up": ref.get("up"),
            "break_rate": round(ref["brk"], 1) if ref.get("brk") is not None else None,
            "avg_dark": round(ref["med"], 1) if ref.get("med") is not None else None,
            "long_break_rate": round(brk * 100, 1), "long_avg_dark": round(avg, 1),
            "long_n": len(dks),
            "monthly": monthly, "median_over": med_over, "sent": sent or {}}

# ---------------------------------------------------------------------------
# 残差分层修正（改造 B）：超购档之外的边际信息
# ---------------------------------------------------------------------------
def attach_residuals(sample, buckets):
    """给样本补上 residual = dk - 所属桶中位数，并返回每只的因子档位。"""
    out = []
    for r in sample:
        b = buckets[bucket_index(r["over"])]
        med = b["med"]
        res = (r["dk"] - med) if med is not None else None
        out.append({**r, "bucket": bucket_index(r["over"]), "res": res})
    return out

def strata_correction(sample_with_res, extras, target, book=None):
    """对 target 股，按 5 因子档位取样本残差均值做修正（每层需 >=5 样本）。"""
    baseline = sponsor_baseline(extras, book)
    def lvl_sponsor(code):
        st = sponsor_stats(extras, code, book)
        if not st or baseline is None: return None
        d = st["avg"] - baseline
        return "pos" if d > 3 else ("neg" if d < -3 else "mid")
    def lvl_corner(code, stock):
        c = cornerstone_of(extras, code, stock)
        if not c or c["ratio"] is None: return None
        return "high" if c["ratio"] > 50 else ("low" if c["ratio"] < 20 else "mid")
    def lvl_intl(v):
        if v is None: return None
        return "pos" if v > 5 else ("neg" if v < 1 else "mid")
    def lvl_sector(name, ch):
        a = sector_adj(name, ch)["v"]
        return "pos" if a > 0 else ("neg" if a < 0 else "mid")
    def lvl_size(shares, ipo):
        if not shares or not ipo: return None
        cap = shares * ipo
        return "pos" if cap < 30e8 else ("neg" if cap > 300e8 else "mid")

    defs = {
        "sponsor": lvl_sponsor(target["code"]),
        "corner": lvl_corner(target["code"], target["stock"]),
        "intl": lvl_intl(target.get("intl")),
        "sector": lvl_sector(target.get("name"), target.get("chapter")),
        "size": lvl_size(target.get("shares"), target.get("ipo")),
    }
    # 累计每层残差
    acc = {"sponsor": {}, "corner": {}, "intl": {}, "sector": {}, "size": {}}
    for r in sample_with_res:
        if r["res"] is None: continue
        ls = {
            "sponsor": lvl_sponsor(r["code"]),
            "corner": lvl_corner(r["code"], r["stock_meta"]) if r.get("stock_meta") else None,
            "intl": lvl_intl(r["intl"]),
            "sector": lvl_sector(r.get("name", ""), r.get("chapter", "")),
            "size": lvl_size(r["shares"], r["ipo"]),
        }
        for k in acc:
            lv = ls.get(k)
            if lv: acc[k].setdefault(lv, []).append(r["res"])
    corr = 0.0
    detail = []
    for k, lv in defs.items():
        if not lv or lv not in acc[k] or len(acc[k][lv]) < 5:
            detail.append((k, lv, None, len(acc[k].get(lv, []))))
            continue
        m = statistics.mean(acc[k][lv])
        corr += m
        detail.append((k, lv, round(m, 2), len(acc[k][lv])))
    corr = clamp(corr, -10, 10)
    return round(corr, 2), detail

# ---------------------------------------------------------------------------
# A+H 锚（改造 E：统一口径）
# ---------------------------------------------------------------------------
AH_K = 0.238
AH_CAP = 12
def ah_implied(prem):
    """A 股较发行价溢价% → 暗盘隐含中枢（统一回归斜率）。"""
    return clamp(AH_K * prem, -AH_CAP, AH_CAP)

# ---------------------------------------------------------------------------
# 阶段预测
# ---------------------------------------------------------------------------
def predict_s1(stock, ctx, extras, book=None):
    """招股期：方向性宽区间。A+H 优先；否则赛道选档。18C 合并单次 +5。"""
    ipo = num(stock.get("ipo_price"))
    if ipo is None or ipo <= 0: return None
    steps = []
    is_ah = bool(stock.get("is_ah_share")) and stock.get("a_share_code")
    prem = ctx.get("ah", {}).get(stock.get("a_share_code")) if is_ah else None
    sec = sector_adj(stock.get("stock_name"), stock.get("listing_chapter"))
    conf = 1
    if prem is not None:
        center = ah_implied(prem)
        half = 10.0
        loP = center - half
        hiP = center + half
        if loP < -5: loP = -5
        steps.append({"k": "A+H 溢价锚", "v": None, "type": "base",
                      "lo": round(loP, 1), "hi": round(hiP, 1),
                      "d": f"A 股较发行价溢价 {pct(prem)} → 回归隐含中枢 {pct(center)}（斜率{AH_K}、截断±{AH_CAP}pt）；区间半宽 {half}pt",
                      "formula": f"中枢 = clamp({AH_K} × {prem:.1f}%, ±{AH_CAP}) = {center:.1f}%"})
        anchor = {"k": "A+H 溢价锚", "txt": pct(prem), "d": "A 股现价(折港币)相对发行价溢价；隐含中枢截断 ±12pt（与模型统一口径）"}
    else:
        if sec["v"] > 0:
            loP, hiP, pick = 0.0, 18.0, "赛道偏乐观→乐观档"
        elif sec["v"] < 0:
            loP, hiP, pick = -15.0, 5.0, "赛道偏悲观→悲观档"
        else:
            loP, hiP, pick = -10.0, 20.0, "无赛道信号→中性档"
        steps.append({"k": "基准区间(赛道选档)", "v": None, "type": "base",
                      "lo": loP, "hi": hiP, "d": f"{pick} → [{pct(loP,0)}, {pct(hiP,0)}]（{sec['why']}）",
                      "formula": f"赛道系数 sec = {sec['v']} → 选档: {pick}"})
        anchor = {"k": "赛道方向", "txt": pct(sec["v"], 0), "d": "招股期无超购，按赛道给方向性宽区间"}
    is18c = bool(re.search(r'18C', stock.get("listing_chapter") or ""))
    if is18c:
        hiP += 5
        steps.append({"k": "18C 特专科技", "v": 5, "type": "delta",
                      "lo": round(loP, 1), "hi": round(hiP, 1),
                      "d": "18C 章节 → 上沿 +5%（已合并单次计入，不再重复）",
                      "formula": "上沿 +5pt（18C 特专科技章节，合并单次计入，避免重复）"})
    sp = sponsor_adj_target(stock, extras, 0.15, 8, book)
    if sp:
        loP += sp["v"]; hiP += sp["v"]
        steps.append({"k": "保荐人战绩", "v": sp["v"], "type": "delta",
                      "lo": round(loP, 1), "hi": round(hiP, 1),
                      "d": f"历史首日均值 {pct(sp['avg'])} vs 基准 {pct(sp['base'])} → 偏离 {pct(sp['avg']-sp['base'])} ×{sp['k']}={pct(sp['v'])}",
                      "formula": f"({sp['avg']}% − {sp['base']}%) × {sp['k']} = {sp['raw']}% → clamp(±{sp['cap']}) = {sp['v']}%"})
    cs = cornerstone_adj_target(stock, extras)
    if cs:
        loP += cs["v"]; hiP += cs["v"]
        steps.append({"k": "基石配售", "v": cs["v"], "type": "delta",
                      "lo": round(loP, 1), "hi": round(hiP, 1),
                      "d": f"基石占比 {cs['ratio']}% vs 基准 35% → 偏离 {cs['ratio']-35:.1f}pt ×{cs['k']}={pct(cs['v'])}",
                      "formula": f"({cs['ratio']}% − 35%) × {cs['k']} = {cs['raw']}% → clamp(±6) = {cs['v']}%"})
    return mk_result("s1", ipo, loP, hiP, conf, {
        "title": "招股期预测", "basis": "方向性区间（相对发行价）",
        "anchor": anchor, "steps": steps, "stage": "S1",
        "degrade": "招股期信息最少（无超购），区间偏宽"})

def predict_s2(stock, ctx, extras, buckets, regime, sample_with_res, book=None):
    """中签后→暗盘收盘（核心）。超购分档 + 残差分层修正 + 大盘环境 + 冷热市平移。"""
    ipo = num(stock.get("ipo_price"))
    if ipo is None or ipo <= 0: return None
    over = num(stock.get("public_offer_subscription_multiple"))
    steps = []
    prov = False
    conf = 2
    if over is not None:
        b = buckets[bucket_index(over)]
        if b["med"] is None:  # 该档无样本 → 退全样本中位
            allv = [r["dk"] for r in sample_with_res if r["res"] is not None]
            med = statistics.median(allv) if allv else 0.0
            dLo = dHi = statistics.pstdev(allv) if len(allv) > 1 else 10.0
            conf = 2
            steps.append({"k": "超购分档(该档样本不足→全样本)", "v": round(med, 1), "type": "base",
                          "d": f"公开超购 {over} 倍，但此档样本不足，改用全样本中位 {pct(med,1)}",
                          "formula": f"bucket({over}) 该档 n<2 → 全样本中位 med = {med:.1f}%"})
        else:
            med, dLo, dHi = b["med"], b["dLo"], b["dHi"]
            conf = 3 if b["n"] >= 5 else 2
            steps.append({"k": "超购分档中枢", "v": round(med, 1), "type": "base",
                          "d": f"公开超购 {over} 倍 → {b['label']}（近12月 n={b['n']}）；该档暗盘中位 {pct(med,1)}、[P25,P75]=[{pct(med-dLo,1)}, {pct(med+dHi,1)}]",
                          "formula": f"档位 = bucket({over}) = {b['label']}；med = median(该档暗盘涨幅) = {med:.1f}%；dLo={dLo:.1f}, dHi={dHi:.1f}"})
    else:
        prov = True
        prem = ctx.get("ah", {}).get(stock.get("a_share_code")) if (stock.get("is_ah_share") and stock.get("a_share_code")) else None
        if prem is not None:
            center = ah_implied(prem)
            med, dLo, dHi = center, 10.0, 12.0
            steps.append({"k": "A+H 折价档中枢(降级)", "v": round(med, 1), "type": "base",
                          "d": f"⚠ 站点未录入超购 → 改用 A+H 隐含中枢 {pct(center)}（半宽 10/12pt）",
                          "formula": f"无超购 → center = clamp({AH_K} × {prem:.1f}%, ±{AH_CAP}) = {center:.1f}%"})
        else:
            med, dLo, dHi = 0.0, 18.0, 22.0  # 改造 F：中性兜底，不再 +29.7% 误导
            steps.append({"k": "全样本兜底(中性)", "v": 0.0, "type": "base",
                          "d": "⚠ 无超购且无 A+H → 中性兜底（中枢≈0、宽区间），不假装精确",
                          "formula": "无超购无A+H → 中性中枢 0%（不假装精确）"})
        conf = min(conf, 2) if prov else conf
    # 冷热市平移（动态校准）
    shift = regime["shift"]
    if shift:
        med += shift
        steps.append({"k": "情绪周期平移", "v": round(shift, 1), "type": "delta",
                      "d": f"近12月 {regime['label']}（破发率 {regime['break_rate']}%、均涨 {pct(regime['avg_dark'])}）→ 中枢平移 {pct(shift,1)}",
                      "formula": f"破发率={regime['break_rate']}%, 均涨={regime['avg_dark']}% → 判定 {regime['label']} → shift={shift:+.1f}pt"})
    # 残差分层修正（改造 B）：仅在「有超购、已落入某档」时启用。
    # 降级路径（无超购）没有桶基准，残差无处附着，强行修正会与 A+H/兜底中枢重复计价。
    corr, cdetail = 0.0, []
    if over is not None:
        tgt = {"code": stock.get("stock_code"), "stock": stock, "intl": num(stock.get("international_subscription_multiple")),
               "name": stock.get("stock_name"), "chapter": stock.get("listing_chapter"),
               "shares": num(stock.get("shares_offered")), "ipo": ipo}
        corr, cdetail = strata_correction(sample_with_res, extras, tgt, book)
    if corr:
        med += corr
        used = "; ".join(f"{k}:{lv}({v})" for k, lv, v, n in cdetail if v is not None)
        res_for = "; ".join(f"{k}[{lv}]={v}% (n={n})" for k, lv, v, n in cdetail if v is not None)
        steps.append({"k": "残差分层修正", "v": corr, "type": "delta",
                      "d": f"超购档之外的边际信息（保荐人/基石/国配/赛道/规模档位残差均值）合计 {pct(corr)} → [{used}]",
                      "formula": f"各因子档位残差均值: {res_for}；合计 corr = Σ = {corr}%"})
    else:
        steps.append({"k": "残差分层修正", "v": None, "type": "info",
                      "d": "超购档之外的因子档位样本不足或方向互抵 → 不强行修正（避免噪声）",
                      "formula": "Σ(各因子档位残差均值): 样本<5 或方向互抵 → 不修正（避免噪声）"})
    # 大盘环境（唯一实时修正项，保留）
    hsi = ctx.get("hsi")
    if hsi is not None:
        d = round(0.3 * hsi, 2)
        med += d
        steps.append({"k": "大盘环境", "v": d, "type": "delta", "d": f"恒指 {pct(hsi)} ×0.3 = {pct(d)}",
                      "formula": f"{hsi:+.1f}% × 0.3 = {d:+.2f}%"})
    raw = med
    med = clamp(med, -40, 400)
    if med != raw:
        steps.append({"k": "上下界夹逼", "v": round(med - raw, 2), "type": "delta",
                      "d": f"原始 {pct(raw,1)} 越界 → 收敛 {pct(med,1)}",
                      "formula": f"clamp({raw:.1f}%, −40, 400) = {med:.1f}%"})
    return mk_result("s2", ipo, med - dLo, med + dHi, conf, {
        "title": "中签后预测（暗盘收盘）", "basis": "目标：暗盘收盘价（相对发行价）",
        "anchor": ({"k": "公开超购倍数", "txt": f"{over} 倍", "d": bucket_label(over)} if over is not None
                   else {"k": "暂缺超购锚", "txt": "未录入", "d": "配售结果未公布，本次为降级估算"}),
        "steps": steps, "base": round(med, 1), "dLo": round(dLo, 1), "dHi": round(dHi, 1),
        "stage": "S2", "provisional": prov})

def predict_s3(stock, ctx, extras, regime, ratio=None, book=None):
    """招股期→暗盘后首日开盘：实际计算统一在 _recalc_s3（用标定妖股系数）。本函数转发，避免与 _recalc_s3 重复。"""
    return _recalc_s3(stock, ctx, extras, regime, ratio or 0.7, book)

# ---- 辅助：标定与因子 ----
def calibrate_yao(pairs):
    """pairs: list of (dark_pool_pct, first_day_open_pct)。
    返回 暗盘>50% 档的 首日开盘/暗盘收盘 中位比。
    实证发现该比值中位≈1.0（并不像旧规则 0.7 那样系统性收窄），故以样本中位为锚。"""
    rs = [o / d for d, o in pairs if d is not None and o is not None and d > 50 and d != 0]
    if len(rs) >= 5:
        return round(clamp(statistics.median(rs), 0.7, 1.3), 2)
    return 0.7  # 样本不足退化为经验值

def bucket_label(over):
    return BUCKET_LABELS[bucket_index(over)] if over is not None else "无超购"

def sponsor_adj_target(stock, extras, k, cap, book=None):
    st = sponsor_stats(extras, stock.get("stock_code"), book)
    base = sponsor_baseline(extras, book)
    if not st or base is None: return None
    raw = (st["avg"] - base) * k
    v = clamp(raw, -cap, cap)
    return {"v": round(v, 2), "raw": round(raw, 2), "k": k, "cap": cap,
            "avg": round(st["avg"], 2), "base": round(base, 2), "n": st["n"],
            "src": st.get("src", ""), "names": [n for n, _, _ in st["names"]]}

def cornerstone_adj_target(stock, extras):
    c = cornerstone_of(extras, stock.get("stock_code"), stock)
    if not c or c["ratio"] is None: return None
    raw = (c["ratio"] - 35) * 0.12
    v = clamp(raw, -6, 6)
    return {"v": round(v, 2), "raw": round(raw, 2), "ratio": c["ratio"], "k": 0.12, "cap": 6}

def mk_result(key, ipo, loP, hiP, conf, extra):
    loPct = round(loP, 1); hiPct = round(hiP, 1)
    return dict(extra, ok=True, key=key,
                loPct=loPct, hiPct=hiPct,
                lo=round(ipo * (1 + loPct / 100), 3),
                hi=round(ipo * (1 + hiPct / 100), 3),
                conf=conf)

def width_conf(lo, hi):
    w = hi - lo
    return 3 if w <= 10 else (2 if w <= 25 else 1)

# ---------------------------------------------------------------------------
# 暗盘开盘价「情绪初判」（辅输出，明确非模型）
# ---------------------------------------------------------------------------
def open_pronounce(close_lo, close_hi, base):
    mid = (close_lo + close_hi) / 2
    if base is not None and base > 50:
        band = 15
    elif close_hi < 0:
        band = 8
    else:
        band = 5
    return {"lo": round(mid - band, 1), "hi": round(mid + band, 1), "band": band,
            "note": "情绪初判（非模型输出）：暗盘开盘易被前几分钟大单砸偏，仅作方向参考；妖股开盘波动更大。"}

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def resolve_stock(stocks, query):
    q = query.strip()
    # 代码精确
    for s in stocks:
        if str(s.get("stock_code")) == q:
            return s
    # 名称包含
    for s in stocks:
        if q in (s.get("stock_name") or ""):
            return s
    # 名称被包含
    for s in stocks:
        nm = s.get("stock_name") or ""
        if nm and nm in q:
            return s
    return None

# ---------------------------------------------------------------------------
# 卖出/持有规则库（每条都带实测依据与样本量；处置方案与报告共用，禁改文案不带上依据）
# ---------------------------------------------------------------------------
# 实测口径：近 12 个月已上市新股，**剔除 openPct 缺失样本**后 n=94。
# 核心指标 = 「首日开盘涨幅 − 暗盘涨幅」：> 0 表示"熬到首日开盘再卖"比"暗盘直接卖"更好。
SELL_BANDS = [
    {"name": "暗盘 ≤ −10%", "grade": "exit",
     "action": "直接清仓，现金/融资都一样（深破发无豁免）",
     "ev": "本档 n=6：首日开盘优于暗盘 2/6；中位差 −3.3pt；P25 −11.0pt",
     "why": "深破发后首日平均更差，尾部极厚——样本里出现过暗盘 −3.5% 熬成首日开盘 −33.9% 的案例；连 A+H 的深破发（n=3）也一只都没托回发行价"},
    {"name": "暗盘 −10% ~ 0", "grade": "exit",
     "action": "直接清仓；**唯一豁免**见下方「破发豁免判定」",
     "ev": "本档 n=6：首日开盘优于暗盘 3/6；中位差 −1.9pt（破发合计 n=12：5/12 更优、中位差 −2.7pt、翻红 0/12）",
     "why": "12 只破发样本里没有一只在首日开盘翻红（涨过发行价）；但**有 3 只回到发行价附近**——那 3 只全是 A+H（有 A 股价格锚）且暗盘只小跌。绿鞋本身不是保护（有绿鞋的 9 只破发里 6 只照样崩）。"},
    {"name": "暗盘 0 ~ +20%", "grade": "sell",
     "action": "暗盘卖出为主（最多留 1/4 观察）",
     "ev": "本档 n=22：首日开盘优于暗盘 5/22（23%）；中位差 −1.8pt",
     "why": "小幅盈利时等首日的胜率只有 23%，是全样本最差的一档——落袋为优"},
    {"name": "暗盘 +20% ~ +50%", "grade": "sell",
     "action": "暗盘分批卖出，先落袋 6~7 成",
     "ev": "本档 n=19：首日开盘优于暗盘 7/19（37%）；中位差 −2.8pt",
     "why": "中高盈利时首日普遍回吐，先把大头变成现金"},
    {"name": "暗盘 +50% ~ +100%", "grade": "split",
     "action": "分批：暗盘卖一半，余量持到首日开盘早段卖",
     "ev": "本档 n=23：首日开盘优于暗盘 14/23（61%）；中位差 +1.6pt；P25 −5.6pt",
     "why": "期望微正但方差大，分批把'赌对/赌错'都锁在可承受范围"},
    {"name": "暗盘 +100% ~ +200%", "grade": "split",
     "action": "暗盘落袋 6~7 成，余量设移动止盈",
     "ev": "本档 n=11：首日开盘优于暗盘 5/11（45%）；中位差 −1.4pt；P25 −11.5pt",
     "why": "翻倍以上首日不确定性放大；且首日 60% 高开低走（收盘−开盘中位 −4.5pt）"},
    {"name": "暗盘 > +200%", "grade": "split",
     "action": "大比例落袋（≥7 成），余量用移动止盈博尾段",
     "ev": "本档 n=7：首日开盘优于暗盘 4/7（57%）；中位差 +9.0pt，但 P25 −15.0pt、最差 −24.8pt",
     "why": "中位很甜、方差失控：P25 已是 −15pt，等于约 1/4 概率把到手利润吐掉一大块"},
]

def band_of(dk):
    edges = [(-1e9, -10), (-10, 0), (0, 20), (20, 50), (50, 100), (100, 200), (200, 1e9)]
    for i, (lo, hi) in enumerate(edges):
        if lo <= dk < hi: return SELL_BANDS[i]
    return SELL_BANDS[-1]

def trade_fees(amount):
    """一买一卖的总摩擦成本与打平所需涨幅（低吸倒手是否划算的硬门槛）。"""
    if not amount: return {"total": None, "breakeven_pct": None}
    per = amount * (FEE_STAMP + FEE_COMM + FEE_SETTLE) + FEE_PLATFORM
    total = per * 2
    return {"total": round(total, 1), "breakeven_pct": round(total / amount * 100, 2)}

def bucket_break_prob(tiers, over):
    """该超购档的**暗盘破发概率**（实测频率，带样本量）。

    用与主预测相同的**分层窗口（近端优先）**——冷市里若仍用 12 个月口径，
    会把「近期破发率 71%」稀释成「20.8%」，严重低估风险。
    门槛：近3月>=8 只 → 近6月>=8 只 → 近12月(有多少算多少)。
    """
    if over is None: return None, 0
    bi = bucket_index(over)
    if isinstance(tiers, list) and tiers and isinstance(tiers[0], tuple):
        for rows, min_n in tiers:
            v = [r["dk"] for r in rows if bucket_index(r["over"]) == bi]
            if len(v) >= min_n:
                return round(sum(1 for x in v if x < 0) / len(v) * 100, 1), len(v)
        v = [r["dk"] for r in tiers[-1][0] if bucket_index(r["over"]) == bi]
        if not v: return None, 0
        return round(sum(1 for x in v if x < 0) / len(v) * 100, 1), len(v)
    v = [r["dk"] for r in (tiers or []) if bucket_index(r["over"]) == bi]
    if not v: return None, 0
    return round(sum(1 for x in v if x < 0) / len(v) * 100, 1), len(v)

def is_ah(stock):
    """A+H：站点标了 is_ah_share 且有 A 股代码 —— 也就是有 A 股价格锚（不是「有绿鞋」）。"""
    return bool(stock.get("is_ah_share")) and bool(stock.get("a_share_code"))

BREAKEVEN_DEPTH = -5.0   # 「温和破发」与「深破发」的分界（实测：A+H 温和破发 3/3 托回发行价）
HELD_LINE = -2.0         # 「托回发行价附近」的判定线（首日开盘 ≥ −2%）
# 保荐人「不托价」警示门槛：只看「温和破发 + 有绿鞋」——绿鞋最该生效、别人都能托住的区间。
# 需同时满足 项目数≥2 且 失败≥2 且 失败率≥50%，防小样本噪音。
SPONSOR_MIN_N = 2
SPONSOR_MIN_FAIL = 2
SPONSOR_FAIL_RATE = 50.0

def breakeven_playbook(stocks, extras):
    """破发处置的**实测判别表**：按「A 股锚 × 破发深度」拆象限，回答

        「破发之后，熬到首日开盘能不能等到买盘把价格托回发行价附近？」

    实测（近 12 个月已上市、剔除 openPct 缺失样本、n=94）：
      A+H + 温和破发(−5%~0)   3/3 回到发行价附近（立讯精密 / 安克创新 / 中际旭创）
      A+H + 深破发(≤−5%)      0/3（滨化股份 / 普源精电 / 鼎泰高科）
      非 A+H + 温和破发        0/2（江西生物 / 龙丰集团 —— **这两只都有绿鞋**，照样崩 −33.9% / −16.6%）
      非 A+H + 深破发          0/4
    结论：托不托得住，看的是**有没有 A 股锚 + 破发是否温和**，不是「有没有绿鞋」。
    """
    ex = extras.get("stocks", {})
    by = {s.get("stock_code"): s for s in stocks}
    rows = []
    for code, v in ex.items():
        o = num(v.get("openPct")); s = by.get(code, {})
        dk = num(s.get("dark_pool_change_pct"))
        # ⚠️ `o == 0` / `dk == 0` 是**缺失值哨兵，不是真实值**（2026-09-27 实测确认）：
        #    15 只 openPct 精确为 0.0000，其中 爱芯元智（发行价=首日收盘=28.200）、
        #    大金重工（66.400=66.400）、华健未来（暗盘 0.0000）等同值成对出现 → 抓取失败留下的占位。
        #    不加这个过滤会把「假 0.0」当成「恰好在发行价开盘」，虚高托回率（曾把真实 n=5 虚报成 n=12）。
        if o is None or o == 0 or dk is None or dk == 0 or not num(s.get("ipo_price")): continue
        rows.append({"code": code, "name": re.sub(r"[^\x20-\x7e\u4e00-\u9fff]", "", str(s.get("stock_name") or ""))[:12],
                     "dk": dk, "open": o, "gap": round(o - dk, 1),
                     "ah": is_ah(s), "green": (v.get("pros") or {}).get("hasGreen"),
                     "sp": v.get("sp") or [], "stab": (v.get("pros") or {}).get("stabilizer")})
    b = [r for r in rows if r["dk"] < 0]
    def quad(ah, mild):
        g = [r for r in b if r["ah"] == ah and ((r["dk"] > BREAKEVEN_DEPTH) == mild)]
        held = [r for r in g if r["open"] >= HELD_LINE]      # 回到发行价附近
        gaps = sorted(r["gap"] for r in g)
        return {"label": ("A+H" if ah else "非 A+H") + (" + 温和破发（−5%~0）" if mild else " + 深破发（≤−5%）"),
                "n": len(g), "held": len(held),
                "med_gap": round(statistics.median(gaps), 1) if gaps else None,
                "worst_gap": gaps[0] if gaps else None,
                "names": [f"{r['name']} {r['dk']:+.1f}%→{r['open']:+.1f}%" for r in sorted(g, key=lambda x: -x["gap"])]}
    gb = [r for r in b if r["green"] is True]
    gb_held = [r for r in gb if r["open"] >= HELD_LINE]

    # ── 保荐人「不托价」记录：只在「温和破发 + 有绿鞋」区间统计
    #    为什么限定这个区间：深度破发时谁都托不住（那是难度问题，不是态度问题）；
    #    只有「只需托回 5% 以内」却仍失败，才指向操盘方本身不托价。
    mild_g = [r for r in b if r["green"] and r["dk"] > BREAKEVEN_DEPTH]
    mild_fail = [r for r in mild_g if r["open"] < HELD_LINE]
    sp_frag = {}
    for r in mild_g:
        for nm in (r.get("sp") or []):
            a = sp_frag.setdefault(nm, {"n": 0, "fail": 0, "cases": []})
            a["n"] += 1
            if r["open"] < HELD_LINE:
                a["fail"] += 1
            a["cases"].append(f"{r['name']} {r['dk']:+.1f}%→{r['open']:+.1f}%")
    for a in sp_frag.values():
        a["rate"] = round(a["fail"] / a["n"] * 100, 1)
        a["watch"] = bool(a["n"] >= SPONSOR_MIN_N and a["fail"] >= SPONSOR_MIN_FAIL
                          and a["rate"] >= SPONSOR_FAIL_RATE)
    watch_nm = sorted([nm for nm, a in sp_frag.items() if a["watch"]])
    wat_n = sum(1 for r in mild_g if any(nm in (r.get("sp") or []) for nm in watch_nm))
    wat_fail = sum(1 for r in mild_g
                   if r["open"] < HELD_LINE and any(nm in (r.get("sp") or []) for nm in watch_nm))

    return {
        "n": len(b), "clean_n": len(rows),
        "quad": {"ah_mild": quad(True, True), "ah_deep": quad(True, False),
                 "ind_mild": quad(False, True), "ind_deep": quad(False, False)},
        "green": {"n": len(gb), "held": len(gb_held),
                  "med_gap": round(statistics.median([r["gap"] for r in gb]), 1) if gb else None},
        "mild_green": {"n": len(mild_g), "fail": len(mild_fail),
                       "wn": wat_n, "wfail": wat_fail, "watch": watch_nm,
                       "names": [f"{r['name']} {r['dk']:+.1f}%→{r['open']:+.1f}%"
                                 for r in sorted(mild_fail, key=lambda x: x["open"])]},
        "sponsors": sp_frag,
        "depth": BREAKEVEN_DEPTH,
    }

def sponsor_watch(target, extras, bp):
    """本股保荐人是否在「温和破发 + 绿鞋」区间留有反复不托价记录（一票否决级警示）。"""
    code = target.get("stock_code")
    mine = (extras.get("stocks", {}).get(code) or {}).get("sp") or []
    frag = (bp or {}).get("sponsors") or {}
    out = []
    for nm in mine:
        a = frag.get(nm)
        if a and a.get("watch"):
            out.append({"name": nm, "n": a["n"], "fail": a["fail"], "rate": a["rate"],
                        "cases": a["cases"]})
    return out

def recent_check(stocks, today=None, n=12):
    """最近已上市新股的**实况回测**（每次运行实时重算，严格因果、无未来函数）。

    关键纪律：回测必须**跑与主预测完全相同的算法**（分层窗口 近3月→6月→12月），
    否则回测的是另一个模型，等于假验证。做法：预测第 i 只时只用「比它更早上市」的新股，
    绝不使用尚未暗盘/尚未上市的新股，也不使用未来数据。
    """
    today = today or datetime.date.today()
    rows = sorted(build_sample(stocks, WINDOW_MONTHS, today), key=lambda r: r["ls"])
    out = []
    for r in rows:
        prior = [x for x in rows if x["ls"] < r["ls"]]
        if len(prior) < 40: continue
        cut = {}
        for key, months, min_n in (("near", WINDOW_MONTHS_NEAR, 5), ("mid", WINDOW_MONTHS_RECENT, 3),
                                   ("long", WINDOW_MONTHS, 3)):
            cut[key] = ([x for x in prior if x["ls"] >= r["ls"] - datetime.timedelta(days=int(months * 30.5))], min_n)
        b = compute_buckets(tiers=[(cut["near"][0], 5, "近3月"), (cut["mid"][0], 3, "近6月"),
                                   (cut["long"][0], 3, "近12月")])[bucket_index(r["over"])]
        if b["med"] is None: continue
        out.append({"code": r["code"], "name": r["name"], "ls": r["ls"].isoformat(),
                    "over": r["over"], "band": b["label"], "src": b["src"],
                    "pred": round(b["med"], 1), "actual": round(r["dk"], 1),
                    "err": round(r["dk"] - b["med"], 1)})
    tail = out[-n:]
    summary = None
    if tail:
        errs = [x["err"] for x in tail]
        dn = sum(1 for x in tail if x["actual"] < 0)
        summary = {
            "n": len(tail),
            "mae": round(sum(abs(x) for x in errs) / len(errs), 1),
            "med_err": round(statistics.median(errs), 1),
            "dir_hit": sum(1 for x in tail if (x["pred"] > 0) == (x["actual"] > 0)),
            "break_n": dn,
            "break_called": sum(1 for x in tail if x["actual"] < 0 and x["pred"] < 0),
            "span": f"{tail[0]['ls']} ~ {tail[-1]['ls']}",
        }
    return {"rows": tail, "summary": summary, "all_n": len(out)}

def trade_plan(target, s2, s3, extras, regime, book=None, long_sample=None, yao=None, tiers=None, bp=None):
    """持仓处置方案：**报告直接给结论，不需要追问用户中了几手、是否融资**。

    结构固定（每份报告一致）：身份/风险画像 → 三情景速查 → 七档卖出规则（带依据+样本量）
    → 现金 vs 融资两套 → 成本清单 → 退出时点排序 → 绿鞋真实含义 → 边界与免责。
    """
    ipo = num(target.get("ipo_price"))
    lot = num(target.get("lot_size")) or 0
    amount = round(ipo * lot, 0) if (ipo and lot) else None
    has_allot = target.get("has_allotment")
    over = num(target.get("public_offer_subscription_multiple"))
    prob, prob_n = bucket_break_prob(tiers if tiers is not None else (long_sample or []), over)
    break_src = "近端分层窗口" if tiers else "近12月窗口"
    pros = (extras.get("stocks", {}).get(target.get("stock_code"), {}) or {}).get("pros") or {}
    band = bucket_label(over) if over is not None else "暂无超购（未公布配售结果）"
    fees = trade_fees(amount)

    # 决策总纲：**按暗盘实际落点分档**（不问用户任何问题，一律给全部分支）
    # 注意：驱动变量是「暗盘实际成交价」，不是模型预测区间——预测只用于"预期"，
    # 动作必须在暗盘 16:15–18:30 内按实际价格执行。七档明细见 bands（SELL_BANDS）。
    scenarios = [
        {"case": "暗盘破发（< 0%）", "act": "直接清仓，现金/融资都一样——不等首日、不等绿鞋（**唯一豁免**见下方判定框）",
         "why": "实测破发组 12 只里首日开盘翻红 0/12；绿鞋托价上限＝发行价，等不来更好的价。但注意有 3 只回到发行价附近，那 3 只全是 A+H 且只小跌"},
        {"case": "暗盘小赚（0% ~ +50%）", "act": "以暗盘卖出为主：+0~+20% 全走，+20~+50% 至少落袋 6~7 成",
         "why": "这两档「首日开盘优于暗盘」的概率只有 23% / 37%，中位差 −1.8 / −2.8pt，等首日是负期望"},
        {"case": "暗盘大赚（> +50%）", "act": "分批：暗盘先卖一半，余量持到首日开盘早段（9:30–10:00）不冲高就清",
         "why": "该档「首日开盘优于暗盘」61%（+50~+100%）/ 57%（>+200%），但方差极大（P25 −5.6 / −15pt），不分批就是把到手利润交回去"},
    ]
    # 盘中形态观察规则（诚实标注：站点无暗盘开盘/最高/最低/成交量字段，无法对"高开低走/低开高走"建模，
    # 故只给"无论哪种形态都可执行"的观察纪律，不假装能预测形态）
    intraday = [
        ("暗盘开盘后 15 分钟（约 16:30 前）", "先别急着全平：用这 15 分钟看方向——若开盘即冲高后回落幅度 > 开盘价的 5%，按『高开低走』处理，直接清"),
        ("高开低走（冲高后跌破开盘价）", "不恋战：本档动作打对折执行（示例：原本留一半，改成只留 1/4），余量设『跌破开盘价 3% 即清』"),
        ("低开高走（先跌后收复开盘价并放量）", "可给该股额外 15 分钟观察窗；若收复后站上开盘价，按本档动作正常执行"),
        ("全程缩量横盘", "以本档动作为准，不因『看起来没跌』拖延——缩量横盘在暗盘里最常见的结局是首日开盘直接低开"),
        ("数据边界（重要）", "本站取不到暗盘的分时/最高/最低/成交量，所以『这只暗盘会高开低走还是低开高走』**无法用数据预测**；以上是执行纪律，不是预测。请以你券商 App 的实时报价为准（各券商暗盘独立撮合、价格不同）。"),
    ]

    amt_txt = f"{amount:,.0f} HKD" if amount else "—"
    cash_plan = [
        f"① 你的成本只有固定的认购手续费（约 49 HKD/笔）+ 中签费（{amt_txt} 的 1.0085%，约 {round(amount * FEE_ALLOT, 0):,.0f} HKD），**没有利息在跑**，所以不必为了省钱而着急卖。",
        f"② 中签 1 手（本金约 {amt_txt}）：一手就是一发子弹，**按上面七档动作整手执行**——别拆成碎单，暗盘流动性有限，拆碎了只会吃更差的价。",
        "③ 中签多手：**按档位分批**。例：若暗盘落在 +50%~+100% 档 → 暗盘卖一半、余量留首日开盘早段；若落在 0%~+20% 档 → 一次性全走。",
        "④ 现金户唯一需要注意的：**破发时必须走**。既然没有利息压力、没有时间成本，你都判断它弱，那留着只是把'已经确定的亏损'换成'更大的不确定亏损'。",
        "⑤ 关于「暗盘低吸加仓摊成本」：**它不改变你原本那手的盈亏，只是新增一笔独立交易**（数学见下方误区③）。捞货那笔的价差 (首开−暗盘) 要扣掉一买一卖摩擦（约 0.25~0.30% + 固定约 30 港元）才有意义；小额价差基本被吃光，且加仓＝把同一只股敞口翻倍。破发时唯一值得考虑的豁免见下方判定框。",
        "⑥ 别因为「就剩一天了」而拖延：首日实测 60% 高开低走（收盘比开盘再低 4.5pt），越晚卖越吃亏。",
    ]
    fin_plan = [
        f"① 融资（孖展）户的成本结构不同：认购手续费约 99 HKD/笔 + **利息按日计、不中签也要付** + 中签费（约 {round(amount * FEE_ALLOT, 0):,.0f} HKD，若中 1 手）。**每多持一天都在烧钱。**",
        "② 由此得出融资户的唯一原则：**提前一档执行**——比现金户更早、更多地落袋。例：现金户在 +50%~+100% 档是'卖一半留一半'，融资户应为'卖 7~8 成、只留 1~2 成博首日'。",
        "③ 破发档（< 0%）：**无条件立即清仓**。融资户没有『熬一熬』这个选项——利息+潜在首日下跌是双重损耗。",
        "④ 融资买入暗盘股票**不能再抵押融资**（各券商规则），所以别指望『低吸再加杠杆』这条路。",
        "⑤ 若中签多手且是融资：**先用暗盘了结还掉融资**，把利息链条断掉；只把确实想博的那部分（≤1/4）留在首日。",
    ]
    # 绿鞋占比：优先用招股书披露的 greenPct；缺失时用「超额配售股数 ÷ 全球发售股数」推算。
    # ⚠ 派生路径必须套同款 3–30% 防护（抓取侧早就有，这里曾漏）：
    #   实测 02475 立讯精密 的 greenShares 抓成 7,701,730,624 股（应为约 5750 万）→ 推算占比 2008%。
    #   越界即说明**股数本身解析错了**，按纪律「宁可不显示数字，也不显示错的数字」→ 占比与股数一起丢。
    gpct = pros.get("greenPct")
    if gpct is not None and not (3.0 <= gpct <= 30.0):
        gpct = None
    gshares = pros.get("greenShares")
    derived = False
    if gpct is None and gshares:
        total_off = num(target.get("shares_offered"))
        if total_off and total_off > 0:
            cand = round(gshares / total_off * 100, 1)
            if 3.0 <= cand <= 30.0:
                gpct, derived = cand, True
            else:
                gshares = None
    green = {
        "has": bool(pros.get("hasGreen")),
        "pct": gpct,
        "pct_derived": derived,
        "shares": gshares,
        "stabilizer": pros.get("stabilizer"),
        "url": pros.get("url"),
    }
    exit_order = [
        ("首日开盘早段（9:30–10:00）", "统计最优出场点：首日 60% 高开低走，收盘比开盘中位低 4.5pt"),
        ("暗盘（T-1 16:15–18:30）", "次优：T+0 可当日买卖，落袋即确定性"),
        ("首日收盘", "最差：多数回吐发生在盘中，等收盘等于把优势让掉"),
    ]
    # ── 破发豁免判定：这只股到底属于哪一类？（老板实战经验 → 量化成可执行规则）
    # 老板原话大意：「有绿鞋的项目，首日一般按发行价开，暗盘捞一点摊低成本就能赚。」
    # 实测检验：绿鞋本身不是保护（破发+有绿鞋 9 只里 6 只照样崩）；
    # 真正的判别变量是「A 股锚 × 破发是否温和」——A+H 且暗盘仅 −5%~0 时 3/3 回到发行价附近。
    ah = is_ah(target)
    ah_code = target.get("a_share_code")
    dk_now = num(target.get("dark_pool_change_pct"))
    mild_now = dk_now is not None and BREAKEVEN_DEPTH < dk_now < 0
    q = (bp or {}).get("quad") or {}
    gw = (bp or {}).get("green") or {}
    ax, ix, ad = q.get("ah_mild") or {}, q.get("ind_mild") or {}, q.get("ah_deep") or {}
    ah_ev = (f"实测「A+H + 温和破发（−5%~0）」{ax.get('held')}/{ax.get('n')} 只首日开盘回到发行价附近"
             + (f"：{'、'.join(ax.get('names') or [])}。" if ax.get("names") else "。"))
    ah_caveat = ("条件很窄，别外推：① 只在暗盘跌幅 −5%~0% 时成立；跌更深时同类 A+H 股 "
                 f"{(ad.get('held') or 0)}/{ad.get('n') or 0} 托回（{'、'.join(ad.get('names') or [])}）；"
                 "② 样本仅 3 只，是经验规律不是统计定理；③ 若首日开盘低于发行价 2% 以上，按普通破发处理、立即清。")
    ind_ev = (f"实测「非 A+H + 温和破发」{(ix.get('held') or 0)}/{ix.get('n') or 0} 只托回发行价附近，"
              f"首日开盘比暗盘再低中位 {abs(ix.get('med_gap') or 0)}pt"
              + (f"（{'、'.join(ix.get('names') or [])}）。" if ix.get("names") else "。"))
    if not ah:
        break_play = {
            "qualify": False, "mode": "no", "verdict": "不适用豁免：破发直接清仓",
            "why": f"本股不是 A+H（没有 A 股价格锚）。{ind_ev}",
            "caveat": ("绿鞋**不构成豁免**：上例两只都有绿鞋、暗盘也只小跌，首日开盘照样崩。"
                       f"整体看破发 + 有绿鞋 {gw.get('n')} 只里只有 {gw.get('held')} 只回到发行价附近。"),
            "plan": "暗盘破发即全清，不等首日、不等绿鞋。",
        }
    elif dk_now is None:
        break_play = {
            "qualify": True, "mode": "cond",
            "verdict": f"条件性适用：只有暗盘落在 −5%~0% 时才可留半仓（现在还没暗盘，先记规则）",
            "why": f"本股是 **A+H**（A 股 {ah_code}，有 A 股价格锚）。{ah_ev}",
            "caveat": ah_caveat,
            "plan": ("暗盘一旦出来就对号入座：落在 −5%~0% → 只卖一半，余量留首日开盘早段（9:30–10:00）按实际价出、"
                     "开盘 15 分钟不冲高就清；跌破 −5% → 豁免自动失效，全清。"),
        }
    elif mild_now:
        break_play = {
            "qualify": True, "mode": "yes",
            "verdict": f"适用：本股暗盘 {dk_now:+.1f}%，正好落在豁免区间（−5%~0%）",
            "why": f"本股是 **A+H**（A 股 {ah_code}，有 A 股价格锚）。{ah_ev}",
            "caveat": ah_caveat,
            "plan": "暗盘只卖一半（留一半），余量在首日开盘早段（9:30–10:00）按实际价出；开盘 15 分钟内不冲高就清。",
        }
    else:
        break_play = {
            "qualify": False, "mode": "no",
            "verdict": f"不适用：本股暗盘 {dk_now:+.1f}%，已超出豁免区间（−5%~0%）→ 按普通破发清仓",
            "why": (f"本股虽是 A+H（A 股 {ah_code}），但破发太深。{ah_ev}"
                    f"豁免只覆盖温和破发，深破发时同类 A+H 股 {(ad.get('held') or 0)}/{ad.get('n') or 0} 托回"
                    + (f"（{'、'.join(ad.get('names') or [])}）。" if ad.get("names") else "。")),
            "caveat": ("别因为「它是 A+H」就放宽：A 股锚只在温和破发时救得回来。"
                       f"整体看破发 + 有绿鞋 {gw.get('n')} 只里只有 {gw.get('held')} 只回到发行价附近。"),
            "plan": "暗盘已深破发 → 直接全清，不等首日、不等绿鞋。",
        }

    # ── 保荐人「不托价」一票否决（老板观察：绿鞋照样崩，是操盘方那边的问题）
    #    判据限定在「温和破发 + 有绿鞋」区间——深度破发谁都托不住（难度问题），
    #    只需托回 5% 以内却失败，才指向操盘方本身不托价（态度问题）。
    sw = sponsor_watch(target, extras, bp)
    mg = (bp or {}).get("mild_green") or {}
    if sw:
        who = "、".join(f"{x['name']}（{x['fail']}/{x['n']} 次未托回）" for x in sw)
        cases = "；".join(f"{x['name']}：{'、'.join(x['cases'][:4])}" for x in sw)
        mn, mf = mg.get("n"), mg.get("fail")
        wn, wf = mg.get("wn"), mg.get("wfail")
        break_play["mode"] = "no"
        break_play["qualify"] = False
        break_play["verdict"] = ("破发即全清：本股保荐人有「不托价」记录"
                                 + ("（覆盖 A+H 豁免）" if ah else "") + "，不给第二次机会")
        break_play["why"] = (
            f"本股保荐人 {who}。「温和破发（−5%~0）+ 有绿鞋」是绿鞋**最该生效**的区间"
            f"（只需托回 5% 以内），实测该区间 {mn} 只里失败 {mf} 只，"
            f"其中上述保荐人参与 {wn} 只、失败 {wf} 只，其余 {mn - wn} 只失败 {mf - wf} 只。"
            f"记录：{cases}。"
            + (f" 本股是 **A+H**（A 股 {ah_code}），但保荐人因素优先——"
               "A 股锚救得回「别人操盘」的破发，救不回「自己人不托」的破发。"
               if ah else ""))
        break_play["caveat"] = (
            f"诚实说明样本量：该保荐人参与样本仅 {wn} 只，Fisher 双侧检验 p≈0.10，"
            "**方向一致但未达统计显著**——这是「警惕信号」，不是定理。"
            "之所以仍设为**一票否决**，是因为风险极不对称："
            "走豁免的收益上限只是把 −4% 变成 0%（约 4pt），而失败下限是 −30pt（江西生物 −33.9%、龙丰集团 −16.6%）。"
            "宁可错杀，不可错放。名单由每次运行的实测数据实时生成，非硬编码。"
            f" 补充：破发 + 有绿鞋 {gw.get('n')} 只里只有 {gw.get('held')} 只回到发行价附近。")
        break_play["plan"] = "破发即全清，不等首日、不等绿鞋、不给保荐人第二次机会。"

    # ── 三个常见误区（用实测数据回答，不靠嘴说）
    myths = [
        {"t": "「只要有绿鞋的项目，首日就会按发行价开盘」",
         "verdict": f"不成立（实测 {(gw.get('held') or 0)}/{gw.get('n') or 0}）",
         "d": (f"绿鞋不是「开盘价 = 发行价」的保证人。实测破发 + 有绿鞋 {gw.get('n')} 只，只有 {gw.get('held')} 只"
               f"在首日开盘回到发行价附近，另外 {(gw.get('n') or 0) - (gw.get('held') or 0)} 只继续崩"
               f"（首开 − 暗盘中位 {gw.get('med_gap')}pt）。"),
         "why": ("机制上：稳价人的买入发生在**首日上市后的连续交易时段**，而开盘价由**开盘前竞价**撮合产生——"
                 "大量中签者集中抢跑时，开盘价照样可以远低于发行价。绿鞋是「破发时的托底买盘」，不是定价保证；"
                 "它还有失效条件（国际配售未超购则不能行使）。"),
         "fact": (f"托得住的样本全是 A+H（有 A 股价格锚）。反例：江西生物、龙丰集团**都有绿鞋**、暗盘也只小跌 "
                  f"−3.5% / −1.5%，首日开盘却崩到 −33.9% / −16.6%。")},
        {"t": "「暗盘破发时捞一点货，把成本摊低，首日就能赚一点」",
         "verdict": "摊低成本是心理账户，不改变总盈亏",
         "d": ("设发行价 P0、暗盘价 D、首日开盘价 O，中签 1 手。暗盘再捞 1 手、首日开盘卖 2 手，"
               "总盈亏 = 2O − P0 − D = (O − P0) + (O − D)。前半段是你原仓的盈亏（捞货前后**分毫不变**），"
               "后半段 (O − D) 才是捞货新增的那一笔交易。"),
         "why": ("所以「摊低成本」只让账面均价好看（(P0+D)/2），不提高总收益。真正让你少亏的是"
                 "「熬到首日开盘卖」这个动作本身，不是加仓；而加仓等于把同一只股票的敞口翻倍——"
                 "判断对了多赚一点，判断错了双倍亏。"),
         "fact": ("捞货那笔 (首开 − 暗盘) 的实测：A+H + 温和破发 3/3 为正（+0.2 ~ +4.9pt）；"
                  "非 A+H 组中位 −25.3pt。再扣掉一买一卖摩擦（约 0.25~0.30% + 固定约 30 港元），小额价差基本被吃光。")},
        {"t": "「开盘前挂一个比开盘价低的价格，直接出」",
         "verdict": "这个动作不改变成交价",
         "d": ("港股首日开盘价由**开盘前竞价**统一撮合（同一时段所有成交同一个价）。你在竞价里挂卖单——"
               "哪怕挂得比预期开盘价低——成交价仍是**开盘价**，不会更低。所以这一步只等于「确保按开盘价卖出」。"),
         "why": ("但如果你是在**开盘后的连续交易时段**挂一个远离市价的低价单，那就会真的成交在更低的价格（更差）。"
                 "所以要么把动作限制在开盘竞价阶段，要么开盘后直接按市价卖。"),
         "fact": "首日实测 60% 高开低走（收盘 − 开盘中位 −4.5pt），越晚卖越吃亏。"},
    ]

    expect = None
    if s2:
        base, lo, hi = s2.get("base"), s2.get("loPct"), s2.get("hiPct")
        exp_band = band_of(base) if base is not None else None
        expect = {
            "lo": lo, "hi": hi, "base": base,
            "band": exp_band["name"] if exp_band else None,
            "band_action": exp_band["action"] if exp_band else None,
            "txt": (f"落在 {pct(lo)} ~ {pct(hi)}（中枢 {pct(base)}）"
                    f"{'，对应卖出档「' + exp_band['name'] + '」' if exp_band else ''}"
                    f"{'，该档历史动作：' + exp_band['action'] if exp_band else ''}"),
            "provisional": bool(s2.get("provisional")),
        }
    return {
        "amount": amount, "lot": lot, "ipo": ipo, "band": band, "over": over,
        "prob": prob, "prob_n": prob_n, "break_src": break_src,
        "fees": fees, "fee_allot": round(amount * FEE_ALLOT, 1) if amount else None,
        "scenarios": scenarios, "bands": SELL_BANDS, "intraday": intraday, "expect": expect,
        "is_ah": ah, "ah_code": ah_code, "break_play": break_play, "myths": myths,
        "sponsor_watch": sw, "mild_green": mg,
        "green_stat": (bp or {}).get("green") or {},
        "quad": (bp or {}).get("quad") or {}, "bp_n": (bp or {}).get("n"),
        "cash_plan": cash_plan, "fin_plan": fin_plan,
        "green": green, "exit_order": exit_order, "sent": (regime or {}).get("sent") or {},
        "holding_days": "暗盘至首日共约 1 天（T-1 暗盘 → T 日开盘），融资利息按这 1~2 天计",
        "has_allotment": has_allot,
    }

def run(query, sim_date=None, out=None, no_live=False):
    extras = load_extras()
    if no_live:
        raise SystemExit("当前为离线模式禁用；本引擎要求实时取数以支持动态校准。")
    stocks = api_get("/ipo-stocks")
    target = resolve_stock(stocks, query)
    if not target:
        raise SystemExit(f"未在 i668 找到匹配「{query}」的新股。可尝试股票代码或全称。")
    # 行情
    ctx = {"hsi": None, "ah": {}}
    ah_codes = [s["a_share_code"] for s in stocks if s.get("is_ah_share") and s.get("a_share_code")]
    gt_codes = ["hkHSI"] + [to_gtimg_code(c) for c in ah_codes]
    try:
        gt = fetch_gtimg(gt_codes)
        ctx["hsi"] = gtimg_pct(gt.get("hkHSI"))
        for code in ah_codes:
            arr = gt.get(to_gtimg_code(code))
            if not arr: continue
            ap = gtimg_price(arr)
            st = next((x for x in stocks if x.get("a_share_code") == code), None)
            if ap is not None and st:
                ipo = num(st.get("ipo_price"))
                if ipo and ipo > 0:
                    ctx["ah"][code] = round(((ap * FX_CNY2HKD) / ipo - 1) * 100, 1)
    except Exception as e:
        sys.stderr.write(f"[warn] 行情获取失败，大盘修正项将缺失: {e}\n")
    # 样本 + 桶 + 校准：**分层窗口（近端优先）** + 长期回退
    #   近3月(>=5) → 近6月(>=3) → 近12月(>=3)：因果回测 MAE 46.6（固定6月窗口 52.7），最近12只 18.5（21.3）
    near_sample = build_sample(stocks, WINDOW_MONTHS_NEAR)
    recent_sample = build_sample(stocks, WINDOW_MONTHS_RECENT)
    long_sample = build_sample(stocks, WINDOW_MONTHS)
    tiers = [(near_sample, 5, "近3月"), (recent_sample, 3, "近6月"), (long_sample, 3, "近12月")]
    buckets = compute_buckets(tiers=tiers)                              # 主预测用（分层）
    buckets_long = compute_buckets(sample=long_sample)                   # 残差分层/破发概率用（样本更多）
    sent = sentiment_windows(stocks)
    regime = compute_regime(long_sample, sent)
    book = build_sponsor_book(stocks, extras)
    # 给样本补残差所需元数据（name/chapter/stock）
    for r in long_sample:
        s = next((x for x in stocks if x.get("stock_code") == r["code"]), {})
        r["name"] = s.get("stock_name", ""); r["chapter"] = s.get("listing_chapter", "")
        r["stock_meta"] = s
    swr = attach_residuals(long_sample, buckets_long)
    # 预测
    s1 = predict_s1(target, ctx, extras, book)
    s2 = predict_s2(target, ctx, extras, buckets, regime, swr, book)
    # S3 只算一次：标定系数就绪后再算
    # 妖股标定需要 (暗盘, 首日开盘) 对：从 stocks + extras 组装（openPct 缺失已按 None 处理）
    pairs = []
    for s in stocks:
        dk = num(s.get("dark_pool_change_pct"))
        op = first_day_open(extras, s.get("stock_code"))
        if dk is not None and op is not None:
            pairs.append((dk, op))
    ratio = calibrate_yao(pairs)
    s3 = _recalc_s3(target, ctx, extras, regime, ratio, book)
    # 开盘初判（基于 S2 收盘区间）
    openp = None
    if s2:
        openp = open_pronounce(s2["loPct"], s2["hiPct"], s2.get("base"))
    # 破发处置判别表（老板实战经验 → 量化）：破发 × A 股锚 × 破发深度
    bplay = breakeven_playbook(stocks, extras)
    plan = trade_plan(target, s2, s3, extras, regime, book, long_sample, ratio,
                      tiers=[(near_sample, 8), (recent_sample, 8), (long_sample, 0)], bp=bplay)
    live = recent_check(stocks)
    result = {"target": target, "ctx": ctx, "regime": regime, "buckets": buckets,
              "buckets_long": buckets_long, "s1": s1, "s2": s2, "s3": s3, "open": openp,
              "yao_ratio": ratio, "sample_n": len(long_sample),
              "sample_near_n": len(near_sample), "sample_recent_n": len(recent_sample),
              "book": {"covered": book["covered"], "base": round(book["base"], 1) if book["base"] is not None else None},
              "plan": plan, "live": live}
    errs = selfcheck(result)
    if errs:
        sys.stderr.write("[自检告警] " + "；".join(errs) + "\n")
    else:
        sys.stderr.write("[自检通过] 价格⇄涨跌幅互推 / 区间方向 / 样本量 / 处置方案结构 均正常\n")
    # 终端摘要
    print(summary_text(result))
    if out:
        html = build_report(result, extras)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n[报告已生成] {out}")
    return result

def _recalc_s3(target, ctx, extras, regime, ratio, book=None):
    """用标定妖股系数重算 S3。"""
    ipo = num(target.get("ipo_price")); dk = num(target.get("dark_pool_change_pct"))
    if ipo is None or ipo <= 0 or dk is None: return None
    steps = []
    base = dk; spread = 10
    if dk > 50:
        base = dk * ratio; spread = 18
        steps.append({"k": "妖股标定(样本实证)", "v": round(base - dk, 2), "type": "delta",
                      "d": f"暗盘 >50% → ×{ratio:.2f}（41只样本实测 首日开盘/暗盘收盘 中位比≈{ratio}，实证未现系统性收窄、仅波动放大）；区间 ±18%",
                      "formula": f"暗盘 {dk:.1f}% > 50 → 首日开盘 ≈ {dk:.1f}% × {ratio} = {base:.1f}%"})
    elif dk < -5:
        base = dk - 2; spread = 10
        steps.append({"k": "破发延续", "v": -2, "type": "delta", "d": "暗盘 <−5% → 额外 −2%",
                      "formula": f"暗盘 {dk:.1f}% < −5 → {dk:.1f}% − 2 = {base:.1f}%"})
    else:
        steps.append({"k": "常规情形", "v": 0, "type": "delta", "d": "暗盘 ±50% 内 → 以暗盘为锚，±10%",
                      "formula": f"暗盘 {dk:.1f}% ∈ [−5, +50] → 以暗盘为锚（不调整）"})
    hsi = ctx.get("hsi")
    if hsi is not None:
        d = round(0.4 * hsi, 2); base += d
        steps.append({"k": "隔夜大盘", "v": d, "type": "delta", "d": f"恒指 {pct(hsi)} ×0.4 = {pct(d)}",
                      "formula": f"{hsi:+.1f}% × 0.4 = {d:+.2f}%"})
    intl = num(target.get("international_subscription_multiple"))
    if intl is not None and intl > 5:
        base += 2; steps.append({"k": "国配修正", "v": 2, "type": "delta", "d": f"国配 {intl} 倍 >5 → +2%",
                      "formula": f"国配 {intl} 倍 > 5 → +2%"})
    sp = sponsor_adj_target(target, extras, 0.2, 10, book)
    if sp:
        base += sp["v"]; steps.append({"k": "保荐人战绩(首日口径)", "v": sp["v"], "type": "delta",
                      "d": f"历史首日均值 {pct(sp['avg'])} vs 基准 {pct(sp['base'])} → {pct(sp['v'])}",
                      "formula": f"({sp['avg']}% − {sp['base']}%) × {sp['k']} = {sp['v']}% (clamp±{sp['cap']})"})
    cs = cornerstone_adj_target(target, extras)
    if cs:
        base += cs["v"]; steps.append({"k": "基石配售(首日口径)", "v": cs["v"], "type": "delta",
                      "d": f"基石占比 {cs['ratio']}% vs 35% → {pct(cs['v'])}",
                      "formula": f"({cs['ratio']}% − 35%) × {cs['k']} = {cs['v']}% (clamp±6)"})
    raw = base; base = clamp(base, -45, 400)
    if base != raw:
        steps.append({"k": "上下界夹逼", "v": round(base - raw, 2), "type": "delta",
                      "d": f"原始 {pct(raw,1)} 越界 → {pct(base,1)}",
                      "formula": f"clamp({raw:.1f}%, −45, 400) = {base:.1f}%"})
    return mk_result("s3", ipo, base - spread, base + spread, 3, {
        "title": "暗盘后预测（首日开盘）", "basis": "目标：上市首日开盘价（相对发行价）",
        "anchor": {"k": "暗盘收盘涨幅", "txt": pct(dk)}, "steps": steps,
        "base": round(base, 1), "spread": spread, "stage": "S3"})

# ---------------------------------------------------------------------------
# 终端摘要 + HTML 报告
# ---------------------------------------------------------------------------
def summary_text(r):
    t = r["target"]
    L = []
    L.append(f"=== {t.get('stock_name')} ({t.get('stock_code')}) ===")
    L.append(f"发行价 {t.get('ipo_price')} ｜ 招股截止 {t.get('subscription_end_date')} ｜ 暗盘 {t.get('dark_pool_date')} ｜ 上市 {t.get('listing_date')}")
    rg = r["regime"]
    L.append(f"恒指 {pct(r['ctx'].get('hsi'))} ｜ 市况 {rg['label']}（{rg.get('label_basis')}：n={rg.get('ref_n')}、"
             f"中位暗盘 {pct(rg.get('ref_med'))}、破发率 {rg.get('ref_brk')}%）"
             f" ｜ 长期窗口(12m)：中位 {pct(rg.get('long_avg_dark'))}、破发率 {rg.get('long_break_rate')}%")
    L.append(f"校准样本：近3月 n={r.get('sample_near_n')} ／ 近6月 n={r.get('sample_recent_n')} ／ 近12月 n={r['sample_n']}"
             f"（分层窗口：近端优先）｜ 保荐人实时库 {r['book']['covered']} 位（基准 {pct(r['book']['base'])}）")
    L.append(f"妖股标定系数(首日/暗盘) = {r['yao_ratio']}")
    for k in ("s1", "s2", "s3"):
        s = r[k]
        if not s:
            L.append(f"[{k.upper()}] 数据不足，无法预测"); continue
        prov = " [预估]" if s.get("provisional") else ""
        L.append(f"[{k.upper()}]{prov} {s['title']}: {pct(s['loPct'])} ~ {pct(s['hiPct'])} ｜ 中枢 {pct(s.get('base', (s['loPct']+s['hiPct'])/2))} ｜ {stars(s['conf'])}")
        L.append(f"        价格区间 {s['lo']} ~ {s['hi']} HKD")
    if r["open"]:
        o = r["open"]
        L.append(f"[开盘初判·辅] {pct(o['lo'])} ~ {pct(o['hi'])} （±{o['band']}pt 情绪带，非模型输出）")
    p = r.get("plan") or {}
    if p:
        prob = "—（配售结果未公布）" if p.get("prob") is None else f"{p['prob']}%（{p.get('break_src')}，n={p['prob_n']}）"
        amt = "—" if p.get("amount") is None else f"{p['amount']:,.0f} HKD"
        L.append(f"[处置方案] 超购档 {p.get('band')} ｜ 该档暗盘破发概率 {prob} ｜ 一手本金 {amt}")
        if p.get("expect"):
            e = p["expect"]
            L.append(f"   模型预期：暗盘{e['txt']}{'（配售结果未公布，为预估）' if e.get('provisional') else ''}")
        for i, s in enumerate(p.get("scenarios") or [], 1):
            L.append(f"   总纲{i}. {md_off(s['case'])} → {md_off(s['act'])}")
        bpl = p.get("break_play") or {}
        if bpl:
            L.append(f"   破发豁免判定：{'✓ 适用' if bpl.get('qualify') else '✗ 不适用'} —— {md_off(bpl.get('verdict'))}")
            L.append(f"      依据：{md_off(bpl.get('why'))}")
            L.append(f"      动作：{md_off(bpl.get('plan'))}")
        L.append(f"   退出时点排序：{' ＞ '.join(x[0] for x in (p.get('exit_order') or []))}")
        g = p.get("green") or {}
        if g.get("has"):
            gp = f"{g.get('pct')}%" if g.get("pct") is not None else "占比未披露"
            if g.get("pct_derived"): gp += "（按股数推算）"
            gs = f"{g['shares']:,} 股" if g.get("shares") else "股数未披露"
            gst = f"稳价人 {g['stabilizer']}" if g.get("stabilizer") else "稳价人未披露"
            gw = p.get("green_stat") or {}
            L.append(f"   绿鞋：有（{gp} / {gs} / {gst}）→ 托价上限＝发行价；"
                     f"⚠ 但绿鞋不保证首日开盘回到发行价（实测破发+有绿鞋 {gw.get('n')} 只里仅 {gw.get('held')} 只托回）")
        else:
            L.append("   绿鞋：无 → 没有稳价买盘托底，破发只能自己扛")
        if p.get("fees", {}).get("total"):
            L.append(f"   摩擦成本：一手一买一卖 ≈ {p['fees']['total']} HKD（打平需 {p['fees']['breakeven_pct']}%）→ 低吸倒手不划算")
    lv = r.get("live") or {}
    if lv.get("summary"):
        s = lv["summary"]
        # ⚠️ 措辞必须写清覆盖范围：回测只跑「分层分桶中枢」，不含保荐人/基石/残差分层等个股因子调整。
        #    写「同一算法」是过度声明——实测把保荐人基准改错 +20pt，MAE 一动不动（回测根本不读保荐人库）。
        L.append(f"[实况回测] 最近 {s['n']} 只已上市新股（{s['span']}）滚动预测（覆盖范围＝分层分桶中枢，"
                 f"不含保荐人/基石等个股因子）：MAE {s['mae']}pt、中位偏差 {s['med_err']}pt、"
                 f"方向命中 {s['dir_hit']}/{s['n']}、破发识别 {s['break_called']}/{s['break_n']}")
    return "\n".join(L)

# —— HTML 报告在 report.py 中生成，保持本文件聚焦引擎 ——
def build_report(result, extras):
    import report
    return report.build(result, extras)

# ---------------------------------------------------------------------------
# 自检（verify-calc 风格）：保证不交带逻辑错误的半成品
# ---------------------------------------------------------------------------
def selfcheck(r):
    errs = []
    for k in ("s1", "s2", "s3"):
        s = r[k]
        if not s: continue
        # 价格⇄涨跌幅严格互推
        ipo = num(r["target"].get("ipo_price"))
        lo_calc = round(ipo * (1 + s["loPct"] / 100), 3)
        hi_calc = round(ipo * (1 + s["hiPct"] / 100), 3)
        if abs(lo_calc - s["lo"]) > 0.01: errs.append(f"[{k}] 低价互推偏差 {lo_calc} vs {s['lo']}")
        if abs(hi_calc - s["hi"]) > 0.01: errs.append(f"[{k}] 高价互推偏差 {hi_calc} vs {s['hi']}")
        if s["loPct"] > s["hiPct"]: errs.append(f"[{k}] 区间反转 lo>hi")
        if any(math.isnan(x) for x in (s["loPct"], s["hiPct"], s.get("base", 0) or 0)):
            errs.append(f"[{k}] 含 NaN")
        # 步骤累计校验：最后一个带 lo/hi 的步骤端点 ≈ 最终区间
        last_step = None
        for st in s["steps"]:
            if st.get("lo") is not None:
                last_step = st
        if last_step:
            if abs(last_step["lo"] - s["loPct"]) > 0.5 or abs(last_step["hi"] - s["hiPct"]) > 0.5:
                errs.append(f"[{k}] 步骤端点与最终区间不符 step={last_step['k']}")
    if r["open"] and r["open"]["lo"] > r["open"]["hi"]:
        errs.append("[open] 开盘初判区间反转")
    if r["sample_n"] < 50:
        errs.append(f"样本不足 {r['sample_n']}（<50），结论不可靠")
    # 处置方案结构校验（此前 selfcheck 未查 plan，却在终端打印"处置方案结构 均正常" → 假绿灯，现已补实）
    p = r.get("plan")
    if not p:
        errs.append("[plan] 处置方案缺失")
    else:
        for key in ("scenarios", "bands", "cash_plan", "fin_plan", "exit_order", "green"):
            if not p.get(key):
                errs.append(f"[plan] 缺字段 {key}")
        if len(p.get("bands") or []) != len(SELL_BANDS):
            errs.append(f"[plan] 卖出档位数量 {len(p.get('bands') or [])} ≠ {len(SELL_BANDS)}")
        # 每档必须带实测依据与样本量（防"只给结论不给依据"）
        for b in (p.get("bands") or []):
            if not b.get("ev") or not b.get("action"):
                errs.append(f"[plan] 档位 {b.get('name')} 缺 action/ev 依据")
        if p.get("amount") is not None and p["amount"] <= 0:
            errs.append("[plan] 一手本金异常")
        for s in (p.get("scenarios") or []):
            if not s.get("case") or not s.get("act"):
                errs.append(f"[plan] 情景 {s.get('case')} 缺动作")
        # 破发豁免判定必须给结论 + 依据 + 动作（且样本量必须跟着走，防止"没样本也敢下结论"）
        bpl = p.get("break_play") or {}
        if not bpl:
            errs.append("[plan] 缺破发豁免判定（break_play）")
        else:
            if not bpl.get("verdict") or not bpl.get("plan") or not bpl.get("why"):
                errs.append("[plan] 破发豁免判定缺 verdict/why/plan")
            if bpl.get("qualify") and not p.get("is_ah"):
                errs.append("[plan] 豁免判定为非 A+H 却标记 qualify（逻辑矛盾）")
            if bpl.get("mode") not in ("yes", "no", "cond"):
                errs.append(f"[plan] 破发豁免 mode 非法：{bpl.get('mode')}")
            # mode=yes 只有「A+H + 暗盘确实落在 −5%~0%」才允许（防把深破发也标成适用）
            if bpl.get("mode") == "yes" and not (p.get("is_ah") and r["target"].get("dark_pool_change_pct") is not None
                                                 and BREAKEVEN_DEPTH < num(r["target"].get("dark_pool_change_pct")) < 0):
                errs.append("[plan] mode=yes 但本股不满足「A+H 且暗盘 −5%~0」")
        # 误区条目必须带实测数字（防写回"凭印象"的话术）
        if len(p.get("myths") or []) != 3:
            errs.append(f"[plan] 误区条目 {len(p.get('myths') or [])} ≠ 3")
        for m in (p.get("myths") or []):
            if not m.get("fact") or not m.get("why"):
                errs.append(f"[plan] 误区「{m.get('t')}」缺实测依据")
        # 保荐人「不托价」警示：有警示就必须已覆盖豁免（否则等于警示了却不执行）
        sws = p.get("sponsor_watch") or []
        for x in sws:
            if not x.get("name") or x.get("n") is None or x.get("fail") is None or x.get("rate") is None:
                errs.append(f"[plan] 保荐人警示缺 n/fail/rate：{x.get('name')}")
            if x.get("rate", 0) < SPONSOR_FAIL_RATE or (x.get("fail") or 0) < SPONSOR_MIN_FAIL:
                errs.append(f"[plan] 保荐人警示 {x.get('name')} 未达门槛却进入名单")
        if sws and (p.get("break_play") or {}).get("mode") != "no":
            errs.append("[plan] 有保荐人警示但 break_play.mode ≠ no（警示未生效 = 假绿灯）")
        if sws and (p.get("break_play") or {}).get("qualify"):
            errs.append("[plan] 有保荐人警示却仍标 qualify=True（逻辑矛盾）")
        if not ((p.get("mild_green") or {}).get("n") or 0) and (p.get("mild_green") or {}).get("watch"):
            errs.append("[plan] mild_green 空却给出 watch 名单")
        # 绿鞋占比合理性（3–30%）：派生路径曾漏防护，算出过 2008% 的荒谬值
        g = p.get("green") or {}
        if g.get("pct") is not None and not (3.0 <= g["pct"] <= 30.0):
            errs.append(f"[plan] 绿鞋占比 {g['pct']}% 越出 3–30%（应为解析错）")
    # 情绪标签与展示数字必须同窗口（防「偏冷(破发率20.8%)」自相矛盾）
    rg = r.get("regime") or {}
    if rg.get("label") not in (None, "无样本") and rg.get("break_rate") is None:
        errs.append("[regime] 有标签但无同窗口破发率")
    lv = r.get("live") or {}
    if lv.get("rows"):
        if not lv.get("summary"):
            errs.append("[live] 实况回测有行但无汇总")
        else:
            for row in lv["rows"]:
                if row.get("pred") is None or row.get("actual") is None:
                    errs.append(f"[live] {row.get('code')} 缺预测/实际值")
                    break
    return errs

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="港股名称或代码（中签股）")
    ap.add_argument("--out", help="HTML 报告输出路径")
    ap.add_argument("--sim-date", help="模拟日期 YYYY-MM-DD（预留）")
    ap.add_argument("--no-live", action="store_true", help="禁用实时取数（当前不支持）")
    args = ap.parse_args()
    out = args.out
    if not out:
        code = args.query.strip()
        out = os.path.join(HERE, "..", "reports", f"{code}_{datetime.date.today().isoformat()}.html")
    run(args.query, sim_date=args.sim_date, out=out, no_live=args.no_live)
