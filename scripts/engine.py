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
import sys, os, json, re, math, time, hmac, hashlib, urllib.request, urllib.parse, statistics, datetime, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRAS_PATH = os.path.join(HERE, "extras.json")
SECRET = "6680fc61c8585cfca143366eea267b67617b7c2830c1c896cd952b276db117c9"
FX_CNY2HKD = 1.09
WINDOW_MONTHS = 12

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

# ---------------------------------------------------------------------------
# 数据获取（i668 API + 腾讯行情）
# ---------------------------------------------------------------------------
def api_get(path, params=None):
    base = "/api"
    url = "https://www.i668.vip" + base + path
    a = ""
    if params:
        a = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        url = url + "?" + a
    i = base + path
    t = str(int(time.time()))
    msg = t + i + a + "" + SECRET
    sig = hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(url, headers={
        "X-Timestamp": t, "X-Sign": sig,
        "Referer": "https://www.i668.vip/", "Origin": "https://www.i668.vip/"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())

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

def sponsor_stats(extras, code):
    st = extras.get("stocks", {}).get(code, {})
    sp = st.get("sp")
    if not sp: return None
    sw = sn = 0.0
    picked = []
    for nm in sp:
        s = extras.get("sponsors", {}).get(nm)
        if not s or not s.get("n"): continue
        picked.append((nm, s["n"], s["avg"]))
        sw += s["avg"] * s["n"]; sn += s["n"]
    if not sn: return None
    return {"avg": sw / sn, "n": int(sn), "names": picked}

def sponsor_baseline(extras):
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
    st = extras.get("stocks", {}).get(code, {})
    if st.get("openPct") is not None:
        return float(st["openPct"])
    return None

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

def build_sample(stocks):
    """可校准样本：有超购 + 有暗盘实测 + 在最近 WINDOW_MONTHS 内上市。"""
    today = datetime.date.today()
    cut = today - datetime.timedelta(days=WINDOW_MONTHS * 31)
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

def compute_buckets(sample):
    buckets = []
    for i in range(len(BUCKET_EDGES) - 1):
        vals = [r["dk"] for r in sample if bucket_index(r["over"]) == i]
        if len(vals) >= 2:
            med = statistics.median(vals)
            p25 = statistics.quantiles(vals, n=4)[0]
            p75 = statistics.quantiles(vals, n=4)[2]
            dLo = med - p25
            dHi = p75 - med
        elif len(vals) == 1:
            med = vals[0]; dLo = dHi = 0.0
        else:
            med = dLo = dHi = None
        buckets.append({"label": BUCKET_LABELS[i], "n": len(vals),
                        "med": med, "dLo": dLo, "dHi": dHi})
    return buckets

# ---------------------------------------------------------------------------
# 动态校准：情绪周期 / 冷热市（改造 G）
# ---------------------------------------------------------------------------
def compute_regime(sample):
    if not sample:
        return {"label": "无样本", "shift": 0.0, "break_rate": None,
                "avg_dark": None, "monthly": None, "median_over": None}
    dks = [r["dk"] for r in sample]
    avg = statistics.median(dks)  # 用中位数，防妖股右尾把均值拉偏
    brk = sum(1 for x in dks if x < 0) / len(dks)
    overs = [r["over"] for r in sample if r["over"] > 0]
    med_over = statistics.median(overs) if overs else None
    # 按月计数
    from collections import Counter
    mc = Counter(r["ls"].strftime("%Y-%m") for r in sample)
    monthly = dict(sorted(mc.items()))
    # 冷热市判定与平移
    if brk > 0.5 or avg < 0:
        label, shift = "冷市", -8.0
    elif brk < 0.3 and avg > 10:
        label, shift = "热市", 3.0
    else:
        label, shift = "中性", 0.0
    return {"label": label, "shift": shift, "break_rate": round(brk * 100, 1),
            "avg_dark": round(avg, 1), "monthly": monthly, "median_over": med_over}

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

def strata_correction(sample_with_res, extras, target):
    """对 target 股，按 5 因子档位取样本残差均值做修正（每层需 >=5 样本）。"""
    baseline = sponsor_baseline(extras)
    def lvl_sponsor(code):
        st = sponsor_stats(extras, code)
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
def predict_s1(stock, ctx, extras):
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
    sp = sponsor_adj_target(stock, extras, 0.15, 8)
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

def predict_s2(stock, ctx, extras, buckets, regime, sample_with_res):
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
        corr, cdetail = strata_correction(sample_with_res, extras, tgt)
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

def predict_s3(stock, ctx, extras, regime, ratio=None):
    """招股期→暗盘后首日开盘：实际计算统一在 _recalc_s3（用标定妖股系数）。本函数转发，避免与 _recalc_s3 重复。"""
    return _recalc_s3(stock, ctx, extras, regime, ratio or 0.7)

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

def sponsor_adj_target(stock, extras, k, cap):
    st = sponsor_stats(extras, stock.get("stock_code"))
    base = sponsor_baseline(extras)
    if not st or base is None: return None
    raw = (st["avg"] - base) * k
    v = clamp(raw, -cap, cap)
    return {"v": round(v, 2), "raw": round(raw, 2), "k": k, "cap": cap,
            "avg": round(st["avg"], 2), "base": round(base, 2), "n": st["n"],
            "names": [n for n, _, _ in st["names"]]}

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
    # 样本 + 桶 + 校准
    sample = build_sample(stocks)
    buckets = compute_buckets(sample)
    regime = compute_regime(sample)
    # 给样本补残差所需元数据（name/chapter/stock）
    for r in sample:
        s = next((x for x in stocks if x.get("stock_code") == r["code"]), {})
        r["name"] = s.get("stock_name", ""); r["chapter"] = s.get("listing_chapter", "")
        r["stock_meta"] = s
    swr = attach_residuals(sample, buckets)
    # 预测
    s1 = predict_s1(target, ctx, extras)
    s2 = predict_s2(target, ctx, extras, buckets, regime, swr)
    # S3 只算一次：标定系数就绪后再算（此前先 predict_s3(默认0.7) 又立刻被覆盖，纯浪费）
    # 妖股标定需要 (暗盘, 首日开盘) 对：从 stocks + extras 组装
    pairs = []
    for s in stocks:
        dk = num(s.get("dark_pool_change_pct"))
        op = first_day_open(extras, s.get("stock_code"))
        if dk is not None and op is not None:
            pairs.append((dk, op))
    ratio = calibrate_yao(pairs)
    # 重新算 S3 用标定系数
    s3 = _recalc_s3(target, ctx, extras, regime, ratio)
    # 开盘初判（基于 S2 收盘区间）
    openp = None
    if s2:
        openp = open_pronounce(s2["loPct"], s2["hiPct"], s2.get("base"))
    result = {"target": target, "ctx": ctx, "regime": regime, "buckets": buckets,
              "s1": s1, "s2": s2, "s3": s3, "open": openp, "yao_ratio": ratio,
              "sample_n": len(sample)}
    errs = selfcheck(result)
    if errs:
        sys.stderr.write("[自检告警] " + "；".join(errs) + "\n")
    else:
        sys.stderr.write("[自检通过] 价格⇄涨跌幅互推 / 区间方向 / 样本量 均正常\n")
    # 终端摘要
    print(summary_text(result))
    if out:
        html = build_report(result, extras)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n[报告已生成] {out}")
    return result

def _recalc_s3(target, ctx, extras, regime, ratio):
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
    sp = sponsor_adj_target(target, extras, 0.2, 10)
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
    L.append(f"恒指 {pct(r['ctx'].get('hsi'))} ｜ 情绪周期 {r['regime']['label']}(破发率{r['regime']['break_rate']}%、均涨{pct(r['regime']['avg_dark'])}) ｜ 校准样本 n={r['sample_n']}")
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
