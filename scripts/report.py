# -*- coding: utf-8 -*-
"""港股打新预测 · HTML 报告生成器

主题：Apple 风 · 高级浅色（近白底 / 白卡 / 发丝线 / 柔和阴影 / 单一蓝点缀）。
配色纪律：涨红跌绿（中国惯例）—— 正值=红、负值=绿、平=灰。
交互：因子名与计算式可悬停，用大白话解释「这是什么、干什么用、为什么这么算」。
"""
import datetime, html

CSS = """
:root{
  --bg:#fbfbfd; --card:#ffffff; --soft:#f5f5f7; --soft2:#fafafc;
  --ink:#1d1d1f; --ink2:#3a3a3c; --mut:#6e6e73; --mut2:#8e8e93;
  --line:#e8e8ed; --line2:#d2d2d7;
  --accent:#0071e3; --accent-ink:#0066cc; --accent-soft:#eef6fe;
  --pos:#d70015; --neg:#0b8043; --flat:#8e8e93;
  --amber:#b7791f; --amber-bg:#fff7e8; --amber-line:#f0d9ad;
  --shadow-sm:0 1px 2px rgba(0,0,0,.05);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Helvetica Neue","Microsoft YaHei",sans-serif;
  line-height:1.62;-webkit-font-smoothing:antialiased;}
.wrap{max-width:1040px;margin:0 auto;padding:44px 24px 80px;}
header{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:14px;
  padding-bottom:22px;border-bottom:1px solid var(--line);}
h1{font-size:30px;margin:0;font-weight:700;letter-spacing:-.02em;}
h1 .code{color:var(--mut);font-size:16px;font-weight:500;margin-left:10px;font-variant-numeric:tabular-nums;}
.sub{color:var(--mut);font-size:13px;margin-top:7px;}
.tag{display:inline-block;background:var(--soft);color:var(--ink2);border:1px solid var(--line);
  border-radius:999px;padding:4px 13px;font-size:12.5px;margin:10px 6px 0 0;}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0;}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px;
  position:relative;box-shadow:var(--shadow-sm);}
.card.cur{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft),0 12px 30px rgba(0,113,227,.13);}
.card h3{margin:0 0 8px;font-size:13px;color:var(--mut);font-weight:600;}
.range{font-size:27px;font-weight:700;margin:6px 0;letter-spacing:-.02em;font-variant-numeric:tabular-nums;}
.center{color:var(--ink2);font-size:13px;margin:4px 0;}
.price{color:var(--mut);font-size:12px;margin-top:8px;font-variant-numeric:tabular-nums;}
.stars{color:#f5a623;letter-spacing:2px;font-size:13px;}
.lo{color:var(--neg)} .hi{color:var(--pos)}
.badge{position:absolute;top:15px;right:15px;font-size:11px;padding:3px 10px;border-radius:999px;font-weight:600;}
.b-prov{background:var(--amber-bg);color:var(--amber);}
.b-cur{background:var(--accent);color:#fff;}
.b-done{background:#e7f7ee;color:var(--neg);}
.b-wait{background:var(--soft);color:var(--mut2);}
section{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:24px;margin:18px 0;box-shadow:var(--shadow-sm);}
section h2{margin:0 0 18px;font-size:18px;font-weight:600;letter-spacing:-.01em;display:flex;align-items:center;gap:10px;}
section h2::before{content:"";width:3px;height:16px;border-radius:2px;background:var(--accent);}
table{width:100%;border-collapse:collapse;font-size:13.5px;}
th,td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top;}
th{color:var(--mut);font-weight:600;font-size:12.5px;background:transparent;}
tr:last-child td{border-bottom:none;}
td.k{font-weight:600;white-space:nowrap;}
td.v{font-variant-numeric:tabular-nums;white-space:nowrap;}
td.v.pos{color:var(--pos)} td.v.neg{color:var(--neg)} td.v.flat{color:var(--flat)}
.base{font-weight:600} .delta{color:var(--ink2)} .info{color:var(--mut)}
.kpis{display:flex;flex-wrap:wrap;gap:12px;margin:10px 0;}
.kpi{flex:1;min-width:150px;background:var(--soft);border:1px solid var(--line);border-radius:14px;padding:14px 16px;}
.kpi .n{font-size:22px;font-weight:700;letter-spacing:-.01em;font-variant-numeric:tabular-nums;}
.kpi .l{font-size:12px;color:var(--mut);margin-top:2px;}
.note{font-size:12.5px;color:var(--ink2);background:var(--soft);border-left:3px solid var(--line2);
  padding:10px 14px;border-radius:0 10px 10px 0;margin:12px 0;}
.warn{border-left-color:var(--amber-line);background:var(--amber-bg);color:var(--amber);}
.facgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.fac{background:var(--soft2);border:1px solid var(--line);border-radius:14px;padding:14px 16px;}
.fac .ft{font-weight:600;font-size:14px;} .fac .fs{font-size:12.5px;color:var(--mut);margin-top:5px;}
.chip{font-size:11px;padding:2px 8px;border-radius:999px;margin-left:7px;font-weight:600;}
.c-use{background:#e7f7ee;color:var(--neg)} .c-show{background:var(--amber-bg);color:var(--amber)} .c-miss{background:#fdecec;color:#c0392b}
footer{color:var(--mut);font-size:12px;margin-top:28px;border-top:1px solid var(--line);padding-top:16px;line-height:1.75;}
footer b{color:var(--ink2)}
.open{background:linear-gradient(180deg,#fffdf8,#fff9ef);border-color:var(--amber-line);}
.open h2::before{background:var(--amber);}
.calcwrap{display:flex;flex-direction:column;gap:12px;margin:8px 0;}
.calc{display:flex;gap:14px;background:var(--soft2);border:1px solid var(--line);border-left-width:3px;border-radius:14px;padding:14px 16px;}
.calc.c-base{border-left-color:var(--accent)}
.calc.c-delta{border-left-color:#5e5ce6}
.calc.c-info{border-left-color:var(--line2)}
.cno{flex:0 0 26px;height:26px;border-radius:50%;background:var(--accent-soft);color:var(--accent-ink);
  font-weight:700;display:flex;align-items:center;justify-content:center;font-size:12.5px}
.cbody{flex:1;min-width:0}
.ck{font-size:14px;font-weight:600;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ctag{font-size:11px;padding:2px 8px;border-radius:999px;background:var(--soft);color:var(--mut);
  font-weight:500;border:1px solid var(--line)}
.cv{font-weight:700;font-variant-numeric:tabular-nums}
.cv.pos{color:var(--pos)} .cv.neg{color:var(--neg)}
.cform{margin:9px 0 5px;display:flex;gap:8px;align-items:flex-start}
.cform-l{flex:0 0 auto;font-size:11px;color:var(--accent-ink);background:var(--accent-soft);
  border-radius:6px;padding:3px 9px;margin-top:2px;font-weight:600}
.cform code{flex:1;display:block;background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:9px 11px;
  font-family:"SFMono-Regular",ui-monospace,Consolas,"Liberation Mono",monospace;font-size:12.5px;color:var(--ink2);
  white-space:pre-wrap;word-break:break-word;line-height:1.55;}
.cd{font-size:12.5px;color:var(--mut);margin-top:5px}
.clohi{font-size:12px;color:var(--ink2);margin-top:5px;font-variant-numeric:tabular-nums}
.fac .ff{margin-top:8px;font-family:"SFMono-Regular",ui-monospace,Consolas,"Liberation Mono",monospace;font-size:11.5px;
  color:var(--ink2);background:var(--soft);border:1px solid var(--line);border-radius:9px;padding:7px 9px;
  white-space:pre-wrap;word-break:break-word;}
/* —— 悬停通俗解释（Apple 风深色气泡） —— */
.tip,.codetip{position:relative;cursor:help;}
.tip{border-bottom:1px dashed var(--line2);}
.tip .q{display:inline-flex;align-items:center;justify-content:center;width:13px;height:13px;border-radius:50%;
  background:var(--accent-soft);color:var(--accent-ink);font-size:9px;font-weight:700;font-style:normal;
  margin-left:5px;vertical-align:1px;}
.tip::after,.codetip::after{content:attr(data-tip);position:absolute;left:0;top:calc(100% + 9px);z-index:60;
  width:330px;max-width:76vw;background:#1d1d1f;color:#f5f5f7;font-weight:400;font-size:12.5px;line-height:1.66;
  letter-spacing:0;text-align:left;padding:12px 14px;border-radius:12px;box-shadow:0 16px 44px rgba(0,0,0,.28);
  opacity:0;visibility:hidden;transform:translateY(-4px);transition:opacity .16s ease,transform .16s ease;
  pointer-events:none;white-space:normal;word-break:break-word;}
.tip:hover::after,.codetip:hover::after{opacity:1;visibility:visible;transform:translateY(0)}
.tip:hover,.codetip:hover{color:var(--ink)}
@media (max-width:720px){.grid{grid-template-columns:1fr}.facgrid{grid-template-columns:1fr}}
@media print{.tip::after,.codetip::after{display:none}.tip,.codetip{border-bottom:none}}
"""

def esc(x): return html.escape(str(x))

def stars(c): return "★" * c + "☆" * (3 - c)

def pct(x, d=1):
    if x is None: return "—"
    return ("+" if x >= 0 else "") + f"{x:.{d}f}%"

def sgn(v):
    """涨红跌绿：正→pos(红)、负→neg(绿)、零/空→flat。"""
    if v is None or v == 0: return "flat"
    return "pos" if v > 0 else "neg"

# ---------------------------------------------------------------------------
# 大白话解释表：键为「因子 / 步骤名里的特征词」，命中即用（更具体的排前面）
# ---------------------------------------------------------------------------
PLAIN = [
    ("国配明细", "国际配售里到底是「谁」买了——比如多少是长线基金、多少是对冲基金。这个数据只有付费数据商有，所有免费渠道都拿不到。所以模型里没有它；如果你自己知道内情，可以用报告里的「改价」把它补进去。"),
    ("样本不足", "按超购热度分档后，如果这一档历史上样本太少（不到 2 个），样本不够就不敢用，改看「全部样本」的中位数兜底——宁可用稳的，也不用可能被个别股票带偏的。"),
    ("全样本兜底", "既没有超购数据、也没有 A+H 可参考时，不给任何偏向，用中性的 0% 加一个宽区间。这等于直白承认：「这只我算不准」，而不是硬编一个数。"),
    ("A+H", "有些公司同时在 A 股（内地）和港股上市。A 股现价比港股发行价贵得越多，说明港股这边相对「便宜」，上市后往 A 股靠拢的概率越大、通常越暖。做法是拿「A 股比发行价贵多少」乘一个系数（0.238）当预测起点。注意：折价深 ≠ 一定不破发，只是平均而言更暖。"),
    ("18C", "18C 是港交所给「特专科技公司」（还没盈利的硬科技）专门开的一条上市通道。这类股想象空间大，所以给它上沿一点点加分。"),
    ("超额配股", "绿鞋 = 「超额配股权」。承销商可以多卖约 15% 的股票；上市后 30 天内如果跌破发行价，稳价人可以买入托价。所以「有绿鞋 = 破发时下方有人接」。港股几乎人人都有，区分度低，只展示、不进打分。"),
    ("绿鞋", "绿鞋 = 「超额配股权」。承销商可以多卖约 15% 的股票；上市后 30 天内如果跌破发行价，稳价人可以买入托价。所以「有绿鞋 = 破发时下方有人接」。港股几乎人人都有，区分度低，只展示、不进打分。"),
    ("发售结构", "公开发售和国际配售各占多少、有没有回拨机制。它会明显影响中签率和货源集中度，但很难折算成一个分数，所以只展示、不加权。"),
    ("中签率", "散户的中签比例。它和超购其实是同一件事的两面（超购越高、越难中），信息重复，单独加入反而添乱，所以只展示、不加权。它影响的是「你能拿到多少货」，不是「暗盘会涨多少」。"),
    ("开盘价", "开盘价在招股 / 暗盘阶段还没发生，逻辑上不可能存在；已上市的股票我们会用 etnet 补齐首日开盘价。所以未上市股不预测开盘价，绝不假装能算。"),
    ("超购", "超购 = 认购量 ÷ 发行量。比如发行 1 亿股、大家认购了 20 亿股 = 超购 20 倍。超购越高说明抢的人越多、越难中签，上市后通常也越容易被炒高。我们把超购分成 7 档，直接看历史上「同样热度」的新股暗盘平均涨多少——这是整个模型最重要的一条参考。"),
    ("基准区间", "招股期还没公布超购数据，缺了最重要的参考，只能靠赛道、机制、入场费这些先给一个方向性的「宽区间」，不硬给点位——信息不够就别装精确。"),
    ("保荐人", "保荐人 = 帮公司上市的券商（投行）。看它过去保荐的新股首日表现好不好：战绩强的给一点小加分、差的扣一点。权重故意压得很小，因为这是统计规律、不是保证。"),
    ("基石", "基石投资者 = 提前签约、承诺拿货并锁定一段时间（通常 6 个月）的大机构。它们认购的比例越高，说明专业机构越看好、上市后短期抛压也越小。做法是按「基石占比 减 市场平均 35%」来微调，权重保守。"),
    ("残差分层", "在「超购热度」这条主线之外，再叠加保荐人、基石、国配、赛道、规模这些更细的特征：看它们在同一热度档里还能额外带来多少平均涨跌，再补上去。样本太少的档就不修，免得被噪声带偏。"),
    ("情绪周期", "先看最近 12 个月整体市场是冷是热：破发率很高、新股普遍跌就是「冷市」，就把所有预测整体下调；反之「热市」上调。相当于给预测装了一个温度计。"),
    ("隔夜大盘", "恒生指数前一晚（或当天）涨还是跌。大盘好，所有新股的情绪一起水涨船高；大盘差则相反。按恒指涨跌幅乘一个小系数来微调。"),
    ("大盘环境", "恒生指数当天涨还是跌。大盘好，所有新股的情绪一起水涨船高；大盘差则相反。按恒指涨跌幅乘一个小系数来微调。"),
    ("发行规模", "发行的盘子大小。小盘股筹码少、容易被炒、波动大；大盘股相对稳。所以小额度稍加分、大额度稍减分。"),
    ("国配", "国际配售 = 卖给机构的那部分。机构超购倍数高，说明机构也在抢，暗盘通常更暖。"),
    ("妖股标定", "有些新股暗盘会暴涨（俗称「妖股」）。对这类股，用历史数据找出「首日开盘 ÷ 暗盘收盘」的比例关系，来推算首日开盘大概是多少。"),
    ("破发延续", "如果暗盘已经跌破发行价（< −5%），说明市场不买账，首日往往也偏弱，所以再往下修一点。"),
    ("常规情形", "暗盘涨跌落在正常区间（−5% ~ +50%）内时，就以暗盘的实际表现为锚，不再额外调整。"),
    ("上下界夹逼", "给预测设一个合理的上下限（−40% ~ +400%），防止个别极端数据把结果算飞。"),
    ("赛道", "按股票名称里的关键词猜它属于哪个行业（站点没有行业字段，只能靠名字推断）。行业不同、热度表现不同，用来决定参考哪一档历史样本。"),
]

def plainOf(k):
    if not k: return ""
    for pat, txt in PLAIN:
        if pat in k: return txt
    return ""

def tip(name):
    """把因子名包成可悬停解释的 span；无解释则原样返回。"""
    p = plainOf(name)
    if not p: return esc(name)
    return f'<span class="tip" data-tip="{esc(p)}">{esc(name)}<i class="q">?</i></span>'

def codetip(formula, k):
    """把计算式包成可悬停解释的 code；无解释则原样返回。"""
    p = plainOf(k)
    if not p: return f'<code>{esc(formula)}</code>'
    return f'<code class="codetip" data-tip="{esc(p)}">{esc(formula)}</code>'

def stage_card(key, s, status, is_cur):
    if not s:
        return f'<div class="card"><h3>{key.upper()}</h3><div class="center info">数据不足</div></div>'
    badge = ""
    if status == "current": badge = '<span class="badge b-cur">当前</span>'
    elif s.get("provisional"): badge = '<span class="badge b-prov">预估</span>'
    cls = "card cur" if is_cur else "card"
    return f'''<div class="{cls}">{badge}
      <h3>{esc(s['title'])}</h3>
      <div class="range"><span class="lo">{pct(s['loPct'])}</span> ~ <span class="hi">{pct(s['hiPct'])}</span></div>
      <div class="center">中枢 <b class="base">{pct(s.get('base', (s['loPct']+s['hiPct'])/2))}</b> ｜ <span class="stars">{stars(s['conf'])}</span></div>
      <div class="price">价格 {s['lo']} ~ {s['hi']} HKD</div>
    </div>'''

def steps_table(title, s):
    if not s or not s.get("steps"): return ""
    rows = ""
    for st in s["steps"]:
        cls = st.get("type", "info")
        v = st.get("v")
        # 增量缺失也要补占位 <td>，否则该行整体左移一格、与表头「步骤|增量|说明」错位
        vtxt = '<td class="v flat">—</td>' if v is None else f'<td class="v {sgn(v)}">{pct(v)}</td>'
        lohi = ""
        if st.get("lo") is not None and st.get("hi") is not None:
            lohi = f' <span class="info">→ [{pct(st["lo"])} ~ {pct(st["hi"])}]</span>'
        rows += f'<tr><td class="k">{tip(st["k"])}</td>{vtxt}<td class="{cls}">{esc(st["d"])}{lohi}</td></tr>'
    return f'''<section><h2>{esc(title)}</h2>
      <table><tr><th>步骤</th><th>增量</th><th>说明 / 理由</th></tr>{rows}</table>
      <div class="note">看不懂某一行？把鼠标停在<b>步骤名</b>上，会用大白话解释这个因子是干什么的。</div></section>'''

def calc_section(title, s):
    """详细计算式推导：每个 step 渲染为 步骤名 + 类型 + 增量 + 显式 formula + 自然语言解读。"""
    if not s or not s.get("steps"): return ""
    rows = ""
    for i, st in enumerate(s["steps"], 1):
        typ = st.get("type", "info")
        cls = {"base": "c-base", "delta": "c-delta", "info": "c-info"}.get(typ, "c-info")
        label = {"base": "基准", "delta": "增量", "info": "说明"}.get(typ, "说明")
        v = st.get("v")
        vtxt = "" if v is None else f'<span class="cv {sgn(v)}">{("+" if v >= 0 else "")}{v}%</span>'
        formula = st.get("formula")
        fhtml = ""
        if formula:
            fhtml = f'<div class="cform"><span class="cform-l">计算式</span>{codetip(formula, st["k"])}</div>'
        lohi = ""
        if st.get("lo") is not None and st.get("hi") is not None:
            lohi = f'<div class="clohi">→ 累计区间 [{pct(st["lo"])} ~ {pct(st["hi"])}]</div>'
        rows += f'''<div class="calc {cls}">
          <div class="cno">{i}</div>
          <div class="cbody">
            <div class="ck">{tip(st["k"])}<span class="ctag">{label}</span>{vtxt}</div>
            {fhtml}
            <div class="cd">{esc(st.get("d", ""))}</div>
            {lohi}
          </div></div>'''
    return f'''<section><h2>{esc(title)}</h2>
      <div class="calcwrap">{rows}</div>
      <div class="note">每一行 = 一个因子/修正项的「输入 → 公式 → 代入 → 输出」。带「累计区间」的最后一行端点必须等于下方三阶段结论的区间。悬停<b>因子名或计算式</b>可看大白话解释。</div>
    </section>'''

FACTORS = [
    ("超购分档", "use", "公开超购倍数分 7 档，取该档近12月暗盘中位数为中枢、[P25,P75] 为不对称区间。S2 主导项。", "i668 API · 实时重算",
     "档位=bucket(公开超购)；中枢=median(该档暗盘涨幅)；区间=[med−dLo, med+dHi]，dLo/dHi=该档[P25,P75]半距（实时重算）"),
    ("A+H 折价锚", "use", "A股较发行价溢价% × 回归斜率 0.238（截断±12pt）。S1/S2 统一口径（原两处不一致已合并）。", "腾讯行情 + 招股书",
     "隐含中枢 = clamp(0.238 × A股溢价%, ±12pt)"),
    ("残差分层修正", "use", "超购档之外的边际信息：保荐人/基石/国配/赛道/规模 的档位残差均值。替代原「6因子全砍」。", "样本残差回归 · 实时",
     "corr = Σ 各因子档位(样本≥5)的(dk−桶中位)残差均值，clamp(±10pt)"),
    ("情绪周期平移", "use", "近12月破发率/均涨判定冷热市，整体平移中位数（冷市−8 / 热市+3）。动态校准核心。", "滚动窗口 · 实时",
     "破发率>50% 或 中位暗盘<0 → 冷市−8pt；破发率<30% 且 中位暗盘>10% → 热市+3pt；否则 0"),
    ("大盘环境", "use", "恒指涨跌幅 ×0.3（S2）/ ×0.4（S3）。唯一实时修正项。", "腾讯恒指 · 实时",
     "S2: 中枢 += 恒指%×0.3；S3: 中枢 += 恒指%×0.4"),
    ("国配超购", "use", "国际配售 >5倍 +2%（S3参与；S2以残差分层间接计入）。", "i668 API",
     "国配>5倍 → +2pt（S3直接；S2经残差分层间接）"),
    ("发行规模", "use", "募资额分档（<30亿 / 30–300亿 / >300亿），按档位残差均值修正（残差分层间接计入）。", "招股书",
     "档位：<30亿(小) / 30–300亿(中) / >300亿(大)；Δ = 该档样本(dk−桶中位)残差均值，并入 corr 合计 clamp ±10pt"),
    ("保荐人战绩", "use", "(历史首日均值−市场基准)×权重，S1 15%±8、S3 20%±10；S2 经残差分层间接计入。etnet 公开页。", "etnet · 内置库",
     "Δ = (历史首日均值 − 市场基准) × 权重；S1/S2权重0.15±0.08，S3权重0.20±0.10；clamp"),
    ("基石配售", "use", "基石认购÷全球发售 = 占比，vs 基准35% ×0.12（±6pt）。招股章程PDF。", "港交所披露易 · 内置库",
     "Δ = (基石占比 − 35%) × 0.12，clamp(±6pt)"),
    ("妖股标定系数", "use", "S3：暗盘>50% 时 首日开盘/暗盘收盘 的样本中位比（原0.7裸常数已标定）。", "样本实测 · 实时",
     "S3: 暗盘>50% → 首日开盘 ≈ 暗盘 × ratio(样本中位比≈1.01，原0.7已证伪)"),
    ("超额配股权(绿鞋)", "show", "承销商可超额配售约15%，上市后30天破发可由稳价人托价。区分度低→只展示不入权重。", "招股章程PDF",
     "机制项：超额配售权≈15%，破发时稳价人可托价（不量化入权重）"),
    ("发售结构", "show", "公开占比/回拨/基石名单。机制影响中签率与筹码，难量化单分→只展示。", "招股章程PDF",
     "机制项：公开占比/回拨比例/基石名单（不量化入权重）"),
    ("散户中签率", "show", "与超购高度共线（r=−0.72），单独解释力弱→只展示不加权。人数口径。", "i668 API",
     "展示项：与超购 r=−0.72 共线，不单独加权"),
    ("国配明细(长线占比)", "miss", "付费数据商内容，免费源不披露国际配售认购人结构。", "—",
     "数据缺失：付费源，免费不披露 → 不参与"),
    ("未上市开盘价", "miss", "尚未发生，不可能存在；已上市股首日开盘由 etnet 补齐。", "—",
     "数据缺失：未发生，不可能存在"),
]

def factor_section():
    out = '<div class="facgrid">'
    for name, kind, desc, src, formula in FACTORS:
        c = {"use": "c-use", "show": "c-show", "miss": "c-miss"}[kind]
        lbl = {"use": "已纳入", "show": "只展示", "miss": "拿不到"}[kind]
        p = plainOf(name)
        attr = f' class="ff codetip" data-tip="{esc(p)}"' if p else ' class="ff"'
        out += (f'<div class="fac"><div class="ft">{tip(name)}<span class="chip {c}">{lbl}</span></div>'
                f'<div class="fs">{esc(desc)}<br>来源：{esc(src)}</div>'
                f'<div{attr}>{esc(formula)}</div></div>')
    out += "</div>"
    return out

def build(result, extras):
    t = result["target"]
    ctx = result["ctx"]
    reg = result["regime"]
    s1, s2, s3 = result["s1"], result["s2"], result["s3"]
    op = result["open"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    # 当前阶段判定：按「时间相位」（i668 项目铁律），而非仅凭数据可用性——
    #   招股截止前 → S1；截止后→暗盘结束前 → S2（即便超购未录、为预估）；
    #   暗盘已有实测（已上市）→ S3。
    # 日期解析失败时退回数据可用性启发式。
    today = datetime.date.today()
    def _pdate(s):
        try: return datetime.datetime.strptime(str(s or "")[:10], "%Y-%m-%d").date()
        except Exception: return None
    end_d = _pdate(t.get("subscription_end_date"))
    dk_d = _pdate(t.get("dark_pool_date"))
    if s3 and (dk_d is None or today >= dk_d):
        cur = "s3"                      # 暗盘已发生 → 焦点 S3
    elif s2 and not s2.get("provisional"):
        cur = "s2"                      # 超购已公布 → S2 为正式数据
    elif end_d and today <= end_d:
        cur = "s1"                      # 仍在招股期 → 焦点 S1（即便 S2 给了预估）
    elif s2:
        cur = "s2"                      # 招股截止后→暗盘前：焦点恒为 S2（预估）
    else:
        cur = "s1"
    status = {"s1": "wait", "s2": "wait", "s3": "wait"}
    status[cur] = "current"

    # 动态校准 KPI
    monthly = reg.get("monthly") or {}
    monthly_txt = "、".join(f"{k}:{v}" for k, v in list(monthly.items())[-6:]) or "—"

    html_doc = f'''<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>港股打新预测 · {esc(t.get('stock_name',''))}</title><style>{CSS}</style></head>
<body><div class="wrap">
<header>
  <div><h1>{esc(t.get('stock_name',''))}<span class="code">{esc(t.get('stock_code',''))}</span></h1>
  <div class="sub">发行价 {esc(t.get('ipo_price',''))} ｜ 招股截止 {esc(t.get('subscription_end_date',''))} ｜ 暗盘 {esc(t.get('dark_pool_date',''))} ｜ 上市 {esc(t.get('listing_date',''))}</div></div>
  <div class="sub">生成于 {now}<br>数据：i668 实时 API + 腾讯行情 + 内置因子库({len(extras.get('stocks', {}) or {})})</div>
</header>

<div class="tag">恒指 {pct(ctx.get('hsi'))}</div>
<div class="tag">情绪周期 {esc(reg['label'])}</div>
<div class="tag">校准样本 n={result['sample_n']}</div>
<div class="tag">妖股系数 {result['yao_ratio']}</div>

<div class="grid">
  {stage_card('s1', s1, status['s1'], cur=='s1')}
  {stage_card('s2', s2, status['s2'], cur=='s2')}
  {stage_card('s3', s3, status['s3'], cur=='s3')}
</div>

<section><h2>三阶段预测结论</h2>
<table><tr><th>阶段</th><th>预测区间(相对发行价)</th><th>中枢</th><th>置信</th><th>价格区间(HKD)</th></tr>
{row('S1 招股期', s1)}
{row('S2 中签后·暗盘收盘', s2)}
{row('S3 暗盘后·首日开盘', s3)}
</table>
<div class="note">区间 = 该条件集的 [P25,P75] 不对称分位（真实 50% 中央区间）。<b>区间越宽 = 这只股在历史样本里越没规律</b>，如实告知，比假装精确有用。</div>
</section>

{steps_table('S1 招股期 · 计算过程（速览）', s1)}
{steps_table('S2 中签后 · 计算过程（速览）', s2)}
{steps_table('S3 暗盘后 · 计算过程（速览）', s3)}
{calc_section('S1 招股期 · 详细计算式', s1)}
{calc_section('S2 中签后 · 详细计算式（暗盘收盘）', s2)}
{calc_section('S3 暗盘后 · 详细计算式（首日开盘）', s3)}

<section><h2>动态校准状态（情绪周期 / FINI）</h2>
<div class="kpis">
  <div class="kpi"><div class="n">{esc(reg['label'])}</div><div class="l">当前市况</div></div>
  <div class="kpi"><div class="n">{pct(reg['avg_dark'])}</div><div class="l">窗口内中位暗盘涨幅</div></div>
  <div class="kpi"><div class="n">{reg['break_rate']}%</div><div class="l">破发率</div></div>
  <div class="kpi"><div class="n">{reg['median_over']}</div><div class="l">超购中位数(倍)</div></div>
  <div class="kpi"><div class="n">{result['sample_n']}</div><div class="l">有效样本(近12月)</div></div>
</div>
<div class="note">近6月新股数：{esc(monthly_txt)}</div>
<div class="note warn">⚠ FINI 口径：2023年底港交所 FINI 上线后申购资金仅冻结中签额，超购倍数系统性虚高。本引擎所有阈值均基于 FINI 后样本实时重算，不跨期混用；冷热市平移即其对情绪的二次修正。</div>
</section>

<section class="open"><h2>暗盘开盘价 · 情绪初判（辅输出）</h2>
{'<div class="kpis"><div class="kpi"><div class="n">%s ~ %s</div><div class="l">开盘价初判区间(相对发行价)</div></div></div><div class="note">%s</div>' % (pct(op['lo']), pct(op['hi']), esc(op['note'])) if op else '<div class="note">无 S2 区间，无法给出开盘初判。</div>'}
</section>

<section><h2>因子方法总表（参与 / 展示 / 缺失）</h2>
{factor_section()}
</section>

<footer>
<div>⚠ 免责：本预测是基于历史统计的条件分布推断，<b>不是荐股、不保收益、不是精确报价器</b>。模型只承诺「方向+区间」，点位级预测是伪命题。</div>
<div>实时性：每次运行均实时重抓配售结果 + 恒指/A股行情并在最近12月窗口上重算分桶，故不同时段问会得到刷新后的评估。</div>
<div>改造痕迹：静态桶→实时重算(自带动态校准) ｜ S2 残差分层修正替代全砍 ｜ S3 妖股系数标定 ｜ S1 18C去重 ｜ A+H统一口径 ｜ FLAT兜底中性化。</div>
</footer>
</div></body></html>'''
    return html_doc

def row(label, s):
    if not s:
        return f'<tr><td class="k">{esc(label)}</td><td colspan="4" class="info">数据不足 / 未到阶段</td></tr>'
    return (f'<tr><td class="k">{esc(label)}</td>'
            f'<td><span class="lo">{pct(s["loPct"])}</span> ~ <span class="hi">{pct(s["hiPct"])}</span></td>'
            f'<td class="base">{pct(s.get("base", (s["loPct"]+s["hiPct"])/2))}</td>'
            f'<td><span class="stars">{stars(s["conf"])}</span></td>'
            f'<td class="v">{s["lo"]} ~ {s["hi"]}</td></tr>')
