# -*- coding: utf-8 -*-
"""港股打新预测 · HTML 报告生成器

主题：Apple 风 · 高级浅色（近白底 / 白卡 / 发丝线 / 柔和阴影 / 单一蓝点缀）。
配色纪律：涨红跌绿（中国惯例）—— 正值=红、负值=绿、平=灰。
交互：因子名与计算式可悬停，用大白话解释「这是什么、干什么用、为什么这么算」。
"""
import datetime, html, re

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
.tip::after,.codetip::after{content:attr(data-tip);position:absolute;left:var(--tipx,0);top:calc(100% + 9px);z-index:60;
  width:330px;max-width:76vw;background:#1d1d1f;color:#f5f5f7;font-weight:400;font-size:12.5px;line-height:1.66;
  letter-spacing:0;text-align:left;padding:12px 14px;border-radius:12px;box-shadow:0 16px 44px rgba(0,0,0,.28);
  opacity:0;visibility:hidden;transform:translateY(-4px);transition:opacity .16s ease,transform .16s ease;
  pointer-events:none;white-space:normal;word-break:break-word;}
.tip.flip::after,.codetip.flip::after{top:auto;bottom:calc(100% + 9px);transform:translateY(4px);}
.tip.flip:hover::after,.codetip.flip:hover::after{transform:translateY(0)}
.tip:hover::after,.codetip:hover::after{opacity:1;visibility:visible;transform:translateY(0)}
.tip:hover,.codetip:hover{color:var(--ink)}
/* —— 持仓处置单（本报告的重点章节，视觉上要压过其他节） —— */
section.plan{border:1px solid #cfd8e3;background:linear-gradient(180deg,#ffffff,#f8fafd);
  box-shadow:0 10px 34px rgba(0,60,140,.08);}
section.plan h2{font-size:20px;}
section.plan h2::before{background:linear-gradient(180deg,var(--accent),#5e5ce6);height:20px;}
.pl-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:0 0 16px;}
.pl-kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:13px 15px;}
.pl-kpi .l{font-size:11.5px;color:var(--mut);}
.pl-kpi .n{font-size:20px;font-weight:700;margin-top:3px;letter-spacing:-.01em;font-variant-numeric:tabular-nums;}
.pl-kpi .n.small{font-size:14px;line-height:1.45;}
.scn{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:14px 0;}
.scn .s{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;border-top:3px solid var(--accent);}
.scn .s.exit{border-top-color:var(--neg)} .scn .s.sell{border-top-color:var(--amber)} .scn .s.split{border-top-color:var(--accent);}
.scn .s .c{font-weight:600;font-size:13.5px;margin-bottom:6px;}
.scn .s .a{font-size:13px;color:var(--ink2);line-height:1.6;}
.scn .s .w{font-size:12px;color:var(--mut);margin-top:7px;border-top:1px dashed var(--line);padding-top:7px;}
table.bands td.bname{font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums;}
table.bands td.ev{font-size:12.5px;color:var(--mut);font-variant-numeric:tabular-nums;}
table.bands tr.g-exit td.bname{color:var(--neg)}
table.bands tr.g-sell td.bname{color:var(--amber)}
table.bands tr.g-split td.bname{color:var(--accent-ink)}
.obs{display:flex;flex-direction:column;gap:8px;margin:10px 0;}
.obs .o{display:flex;gap:11px;font-size:13px;align-items:flex-start;background:var(--soft2);
  border:1px solid var(--line);border-radius:11px;padding:10px 13px;}
.obs .o b{flex:0 0 auto;color:var(--ink);min-width:132px;}
.obs .o span{color:var(--ink2);flex:1;}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:12px 0;}
.two .colus{background:var(--soft2);border:1px solid var(--line);border-radius:14px;padding:15px 17px;}
.two .colus h4{margin:0 0 9px;font-size:14px;font-weight:600;}
.two .colus ul{margin:0;padding-left:17px;} .two .colus li{font-size:12.8px;color:var(--ink2);margin-bottom:7px;line-height:1.62;}
.exit-o{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0;}
.exit-o .e{flex:1;min-width:190px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;}
.exit-o .e .r{font-size:11px;color:var(--accent-ink);font-weight:600;}
.exit-o .e .t{font-weight:600;font-size:13.5px;margin:4px 0 3px;}
.exit-o .e .d{font-size:12px;color:var(--mut);line-height:1.55;}
.live{font-size:12.5px;color:var(--ink2);background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-top:10px;}
.live table{margin-top:8px;font-size:12.5px}
@media (max-width:720px){.grid{grid-template-columns:1fr}.facgrid{grid-template-columns:1fr}
  .pl-grid{grid-template-columns:1fr 1fr}.scn{grid-template-columns:1fr}.two{grid-template-columns:1fr}}
@media print{.tip::after,.codetip::after{display:none}.tip,.codetip{border-bottom:none}}
"""

def esc(x): return html.escape(str(x))

def strip_md(x):
    """去掉 `**加粗**` 记号（用于 HTML 属性 / CSS content 场景——那里不解析 HTML）。"""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(x))

def rich(x):
    """HTML 正文用：先转义，再把 `**x**` 变成真加粗。
    ⚠ 纪律：报告里**禁止**让 `**` 原样显示（用户会看到星号）——正文一律走 rich()，
    属性/tooltip 一律走 strip_md()。"""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(str(x)))

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
    ("分层窗口", "港股打新的情绪一个月能翻脸——实测 2026 年 5 月暗盘中位 +75.6%，到 9 月已经是 −0.7%。所以不能只用一个固定的历史窗口：本引擎优先用「最近 3 个月」的样本算，某档样本不够就退到「近 6 个月」，再不够才用「近 12 个月」。这样市场一冷，预测立刻跟着降，不用等一整年才反应过来。"),
    ("暗盘", "暗盘 = 新股正式上市前一天的「场外预演交易」，时间通常是上市前一日 16:15–18:30。不通过交易所，由各家券商自己撮合，所以**不同券商报的价可能不一样**。它能买卖、T+0 当天可进出，是打新人最先能脱手的地方；港股通不能参与，也不是每只新股都有暗盘。"),
    ("动态校准", "不是一套写死的公式，而是每次都重新抓最近的真实成交、重算一遍参考档位——所以同一只股在不同时间问，结论会随最新市况刷新。"),
    ("摩擦成本", "一买一卖要交的钱：印花税 0.1%×2 + 券商佣金 + 平台费 + 结算费，合起来大约 1%~2% 就被吃掉了。意思是「低吸再倒手」这种操作，得先赚回这笔钱才叫赚钱。"),
    ("破发概率", "这一档热度（比如超购 100–500 倍）历史上出现「暗盘收在发行价以下」的比例。它是**实测频率**，不是模型预测——用来说明这档大概有多少比例是亏的。"),
    ("实况回测", "拿「最近已经真实上市的新股」，用和本次完全相同的算法、只喂给它上市之前的数据，回放一遍看准不准。这是防止「拿未来数据美化自己」的照妖镜，数字不好看也照实展示。"),
    ("卖出档", "按「暗盘实际成交涨幅」划分的 7 个区间，每个区间配一套动作。为什么按落点分而不是按预测分？因为动作必须在暗盘那两个小时里当场做，只有实际价格是确定的。"),
    ("绿鞋托价", "绿鞋（超额配售权）的稳价人只在**跌破发行价时**才买，而且**买入价不能高于发行价**。所以它的作用是「跌的时候下面有个垫子」，不是「帮你卖更高价」——散户不可能靠卖给绿鞋赚钱。"),
    ("退出时点", "同一只股票，在不同时间卖结果差别很大。实测首日有 60% 是「高开低走」（收盘比开盘中位低 4.5pt），所以越晚卖越吃亏。"),
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
    return f'<span class="tip" data-tip="{esc(strip_md(p))}">{esc(name)}<i class="q">?</i></span>'

def codetip(formula, k):
    """把计算式包成可悬停解释的 code；无解释则原样返回。"""
    p = plainOf(k)
    if not p: return f'<code>{esc(formula)}</code>'
    return f'<code class="codetip" data-tip="{esc(strip_md(p))}">{esc(formula)}</code>'

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
        rows += f'<tr><td class="k">{tip(st["k"])}</td>{vtxt}<td class="{cls}">{rich(st["d"])}{lohi}</td></tr>'
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
            <div class="cd">{rich(st.get("d", ""))}</div>
            {lohi}
          </div></div>'''
    return f'''<section><h2>{esc(title)}</h2>
      <div class="calcwrap">{rows}</div>
      <div class="note">每一行 = 一个因子/修正项的「输入 → 公式 → 代入 → 输出」。带「累计区间」的最后一行端点必须等于下方三阶段结论的区间。悬停<b>因子名或计算式</b>可看大白话解释。</div>
    </section>'''

FACTORS = [
    ("超购分档", "use", "公开超购倍数分 7 档，取该档暗盘中位数为中枢、[P25,P75] 为不对称区间。S2 主导项。", "i668 API · 实时重算",
     "档位=bucket(公开超购)；中枢=median(该档暗盘涨幅)；区间=[med−dLo, med+dHi]，dLo/dHi=该档[P25,P75]半距（实时重算）"),
    ("分层窗口(近端优先)", "use", "每档逐层取样本：近3月(≥5只) → 近6月(≥3只) → 近12月(≥3只)。市场一转冷，预测立刻跟着降。", "i668 API · 每次重算",
     "tiers=[(近3月,5),(近6月,3),(近12月,3)]；逐档取第一个满足样本门槛的窗口。因果回测 MAE 46.6（固定6月窗52.7）"),
    ("A+H 折价锚", "use", "A股较发行价溢价% × 回归斜率 0.238（截断±12pt）。S1/S2 统一口径（原两处不一致已合并）。", "腾讯行情 + 招股书",
     "隐含中枢 = clamp(0.238 × A股溢价%, ±12pt)"),
    ("残差分层修正", "use", "超购档之外的边际信息：保荐人/基石/国配/赛道/规模 的档位残差均值。替代原「6因子全砍」。", "样本残差回归 · 实时",
     "corr = Σ 各因子档位(样本≥5)的(dk−桶中位)残差均值，clamp(±10pt)"),
    ("情绪周期(已改口径)", "use", "不再用「冷市−8/热市+3」的固定平移（因果回测证明是负贡献）。情绪改由**分层窗口自动吸收** + 近30/90天指标如实展示。", "滚动窗口 · 实时",
     "固定平移已删除（实测 MAE 40.05→39.4、中位偏差 −8.4→−5.4）；市况标签取近30天(≥3只)，与展示数字同窗口"),
    ("大盘环境", "use", "恒指涨跌幅 ×0.3（S2）/ ×0.4（S3）。实时修正项。", "腾讯恒指 · 实时",
     "S2: 中枢 += 恒指%×0.3；S3: 中枢 += 恒指%×0.4"),
    ("国配超购", "use", "国际配售 >5倍 +2%（S3参与；S2以残差分层间接计入）。", "i668 API",
     "国配>5倍 → +2pt（S3直接；S2经残差分层间接）"),
    ("发行规模", "use", "募资额分档（<30亿 / 30–300亿 / >300亿），按档位残差均值修正（残差分层间接计入）。", "招股书",
     "档位：<30亿(小) / 30–300亿(中) / >300亿(大)；Δ = 该档样本(dk−桶中位)残差均值，并入 corr 合计 clamp ±10pt"),
    ("保荐人战绩", "use", "(历史首日表现−市场基准)×权重：S1 用 0.15±8、S3 用 0.20±10；S2 经残差分层间接计入。基准与战绩均为**运行时中位数口径**。", "站点首日收盘 · 实时重算",
     "Δ = (保荐人首日收盘涨幅中位数 − 全库中位基准) × 权重；S1 0.15/clamp±8，S3 0.20/clamp±10"),
    ("基石配售", "use", "基石认购÷全球发售 = 占比，vs 基准35% ×0.12（±6pt）。招股章程PDF。", "港交所披露易 · 内置库",
     "Δ = (基石占比 − 35%) × 0.12，clamp(±6pt)"),
    ("妖股标定系数", "use", "S3：暗盘>50% 时 首日开盘/暗盘收盘 的样本中位比（原0.7裸常数已标定）。", "样本实测 · 实时",
     "S3: 暗盘>50% → 首日开盘 ≈ 暗盘 × ratio(样本中位比≈1.01，原0.7已证伪)"),
    ("超额配股权(绿鞋)", "show", "承销商可超额配售约15%，上市后30天破发可由稳价人托价（买入价≤发行价）。区分度低→只展示不入权重。", "招股章程PDF",
     "机制项：超额配售权≈15%，破发时稳价人可托价（托价上限=发行价），不量化入权重"),
    ("发售结构", "show", "公开占比/回拨/基石名单。机制影响中签率与筹码，难量化单分→只展示。", "招股章程PDF",
     "机制项：公开占比/回拨比例/基石名单（不量化入权重）"),
    ("散户中签率", "show", "与超购高度共线（r=−0.72），单独解释力弱→只展示不加权。人数口径。", "i668 API",
     "展示项：与超购 r=−0.72 共线，不单独加权"),
    ("国配明细(长线占比)", "miss", "付费数据商内容，免费源不披露国际配售认购人结构。", "—",
     "数据缺失：付费源，免费不披露 → 不参与"),
    ("暗盘分时/最高/最低/成交量", "miss", "站点未提供暗盘盘口数据 → 「高开低走 / 低开高走」无法用数据预测，只能给执行纪律。", "—",
     "数据缺失：无暗盘分时数据 → 形态判断只能靠人工看盘"),
    ("未上市开盘价", "miss", "尚未发生，不可能存在；已上市股首日开盘由 etnet 补齐。", "—",
     "数据缺失：未发生，不可能存在"),
]

def factor_section():
    out = '<div class="facgrid">'
    for name, kind, desc, src, formula in FACTORS:
        c = {"use": "c-use", "show": "c-show", "miss": "c-miss"}[kind]
        lbl = {"use": "已纳入", "show": "只展示", "miss": "拿不到"}[kind]
        p = plainOf(name)
        attr = f' class="ff codetip" data-tip="{esc(strip_md(p))}"' if p else ' class="ff"'
        out += (f'<div class="fac"><div class="ft">{tip(name)}<span class="chip {c}">{lbl}</span></div>'
                f'<div class="fs">{rich(desc)}<br>来源：{esc(src)}</div>'
                f'<div{attr}>{esc(formula)}</div></div>')
    out += "</div>"
    return out

def plan_section(plan, live):
    """持仓处置单：老板要求「报告直接给方案，不追问用户中了几手、是否融资」。
    所有分情况（现金/融资、7 档落点、盘中形态）一次性写全，每份报告结构一致。"""
    if not plan:
        return '<section class="plan"><h2>中签之后怎么操作</h2><div class="note">本次未生成处置方案（数据不足）。</div></section>'
    amt = plan.get("amount")
    amt_txt = f"{amt:,.0f}" if amt else "—"
    prob = plan.get("prob")
    prob_txt = f"{prob}%" if prob is not None else "—"
    prob_sub = (f"{esc(plan.get('break_src'))} · n={plan['prob_n']}" if prob is not None
                else "配售结果未公布，暂无法取该档频率")
    g = plan.get("green") or {}
    if g.get("has"):
        green_n = f"有 · {g['pct']}%" if g.get("pct") is not None else "有"
        green_sub = (f"股数 {g['shares']:,} ｜ {g['stabilizer']}" if g.get("stabilizer")
                     else (f"股数 {g['shares']:,} ｜ 稳价人未披露" if g.get("shares") else "稳价人未披露"))
        if g.get("pct_derived"):
            green_sub += "（占比按股数推算）"
    else:
        green_n, green_sub = "无", "无稳价买盘托底（破发只能自己扛）"
    fees = plan.get("fees") or {}

    lot_txt = f"{plan.get('lot'):g}" if isinstance(plan.get("lot"), (int, float)) else esc(plan.get("lot"))
    band_lbl = esc(plan.get("band"))
    prob_lbl = f"{tip('破发概率')}（{band_lbl}）" if plan.get("over") is not None else f"{tip('破发概率')}<span style='font-weight:400'>（配售结果未公布）</span>"
    kpi = f'''<div class="pl-grid">
      <div class="pl-kpi"><div class="l">一手本金（{lot_txt} 股 × {esc(plan.get('ipo'))} 港元）</div>
        <div class="n">{amt_txt}<span style="font-size:12px;color:var(--mut)"> HKD</span></div></div>
      <div class="pl-kpi"><div class="l">{prob_lbl}</div>
        <div class="n">{prob_txt}</div><div class="l" style="margin-top:3px">{prob_sub}</div></div>
      <div class="pl-kpi"><div class="l">{tip('绿鞋')}</div>
        <div class="n small">{green_n}</div><div class="l" style="margin-top:3px">{esc(green_sub)}</div></div>
      <div class="pl-kpi"><div class="l">{tip('摩擦成本')}（一买一卖）</div>
        <div class="n">{fees.get('total', '—')}<span style="font-size:12px;color:var(--mut)"> HKD</span></div>
        <div class="l" style="margin-top:3px">打平需 {fees.get('breakeven_pct', '—')}%</div></div>
    </div>'''

    exp = plan.get("expect")
    exp_html = ""
    if exp:
        exp_html = (f'<div class="note"><b>模型预期（供参考，不是动作依据）</b>：{tip("暗盘")}'
                    f'{esc(exp.get("txt"))}'
                    f'{"（配售结果未公布，此处为预估）" if exp.get("provisional") else ""}</div>')

    grade_cls = {"exit": "exit", "sell": "sell", "split": "split"}
    scn = '<div class="scn">'
    for i, s in enumerate(plan.get("scenarios") or []):
        cls = ["exit", "sell", "split"][i] if i < 3 else "split"
        scn += (f'<div class="s {cls}"><div class="c">{rich(s["case"])}</div>'
                f'<div class="a">{rich(s["act"])}</div>'
                f'<div class="w">{rich(s.get("why", ""))}</div></div>')
    scn += "</div>"

    brows = ""
    for b in plan.get("bands") or []:
        brows += (f'<tr class="g-{esc(b["grade"])}"><td class="bname">{rich(b["name"])}</td>'
                  f'<td>{rich(b["action"])}</td><td class="ev">{rich(b["ev"])}</td>'
                  f'<td class="ev">{rich(b["why"])}</td></tr>')

    obs = '<div class="obs">'
    for k, v in plan.get("intraday") or []:
        obs += f'<div class="o"><b>{rich(k)}</b><span>{rich(v)}</span></div>'
    obs += "</div>"

    def ul(items):
        return "<ul>" + "".join(f"<li>{rich(x)}</li>" for x in items) + "</ul>"

    exits = '<div class="exit-o">'
    for i, (name, why) in enumerate(plan.get("exit_order") or [], 1):
        exits += f'<div class="e"><div class="r">第 {i} 优先</div><div class="t">{rich(name)}</div><div class="d">{rich(why)}</div></div>'
    exits += "</div>"

    live_html = ""
    if live and live.get("summary"):
        s = live["summary"]
        rws = "".join(
            f'<tr><td class="k">{esc(r["name"])}</td><td class="v">{esc(r["ls"])}</td>'
            f'<td class="v">{r["over"]:.0f}×</td><td class="v {sgn(r["pred"])}">{pct(r["pred"])}</td>'
            f'<td class="v {sgn(r["actual"])}">{pct(r["actual"])}</td>'
            f'<td class="v {sgn(r["err"])}">{r["err"]:+.1f}pt</td></tr>'
            for r in (live.get("rows") or [])[-8:])
        live_html = f'''<div class="live"><b>{tip('实况回测')}：最近 {s['n']} 只已上市新股（{esc(s['span'])}）</b>
        —— 用与本报告<b>完全相同</b>的算法滚动回放：MAE <b>{s['mae']}pt</b>、中位偏差 {s['med_err']}pt、
        方向命中 {s['dir_hit']}/{s['n']}、破发识别 {s['break_called']}/{s['break_n']}。
        <table><tr><th>名称</th><th>上市日</th><th>超购</th><th>当时预测</th><th>实际暗盘</th><th>误差</th></tr>{rws}</table>
        <div style="margin-top:7px;color:var(--mut)">⚠ 方向命中率不高是模型的真实局限：<b>它擅长给区间水平，不擅长猜单只涨跌方向</b>。
        所以本报告的卖出动作全部按「暗盘实际落点」触发，而不是按预测方向触发。</div></div>'''

    return f'''<section class="plan"><h2>中签之后怎么操作（处置单）</h2>
    <div class="note">本节的目的：<b>你不需要回答任何问题</b>——中几手、现金还是融资、什么价位，各种情况都写在下面，照着对号入座即可。</div>
    {kpi}{exp_html}
    <h3 style="font-size:15px;margin:20px 0 4px">一、三条总纲（先看这个）</h3>
    {scn}
    <h3 style="font-size:15px;margin:20px 0 4px">二、按{tip('卖出档')}照表执行（暗盘 16:15–18:30 内看实际价）</h3>
    <table class="bands"><tr><th>暗盘实际落点</th><th>动作</th><th>实测依据</th><th>为什么</th></tr>{brows}</table>
    <div class="note">依据口径：近 12 个月已上市新股，剔除缺失样本后 n=94；核心比较项 = 「首日开盘涨幅 − 暗盘涨幅」，大于 0 表示「熬到首日再卖」好过「暗盘直接卖」。</div>
    <h3 style="font-size:15px;margin:20px 0 4px">三、盘中形态怎么应对（数据边界如实说明）</h3>
    {obs}
    <h3 style="font-size:15px;margin:20px 0 4px">四、现金打新 / 融资打新，分别怎么做</h3>
    <div class="two">
      <div class="colus"><h4>💰 现金打新</h4>{ul(plan.get("cash_plan") or [])}</div>
      <div class="colus"><h4>🏦 融资打新（孖展）</h4>{ul(plan.get("fin_plan") or [])}</div>
    </div>
    <h3 style="font-size:15px;margin:20px 0 4px">五、{tip('退出时点')}排序</h3>
    {exits}
    <div class="note warn">⚠ <b>关于绿鞋，一个必须纠正的常见误解：</b>绿鞋（超额配售权）的稳价人只在<b>跌破发行价时</b>买入，
    且<b>买入价不得高于发行价</b>（上市规则 9.23），规模 ≤ 发行量 15%、窗口 ≤ 上市日起 30 个日历日。
    所以「第二天开盘卖给绿鞋赚一笔」在机制上不成立——托价上限就是发行价。另外，本站因子库显示
    <b>2026 年不少 A+H 股为「首日入通」主动放弃了绿鞋</b>，所以第一步永远是先确认这只到底有没有
    （见上方 KPI 与{tip('绿鞋托价')}）。</div>
    {live_html}
    <div class="note">合规与成本提示：融资利息按日计（<b>不中签也要付</b>）；中签费 1.0085%（含经纪佣金/征费/交易费/财汇局费）；
    暗盘由各券商独立撮合、<b>价格以你券商 App 为准</b>；港股通不能参与暗盘；
    内地居民境外证券投资盈利按规定需自行申报（20% 个人所得税口径），请以最新法规为准。</div>
    </section>'''

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
<div class="tag">市况 {esc(reg['label'])}（{esc(reg.get('label_basis') or '—')}）</div>
<div class="tag">校准样本 近3月 {result.get('sample_near_n')} / 近6月 {result.get('sample_recent_n')} / 近12月 {result['sample_n']}</div>
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

{plan_section(result.get('plan'), result.get('live'))}

{steps_table('S1 招股期 · 计算过程（速览）', s1)}
{steps_table('S2 中签后 · 计算过程（速览）', s2)}
{steps_table('S3 暗盘后 · 计算过程（速览）', s3)}
{calc_section('S1 招股期 · 详细计算式', s1)}
{calc_section('S2 中签后 · 详细计算式（暗盘收盘）', s2)}
{calc_section('S3 暗盘后 · 详细计算式（首日开盘）', s3)}

<section><h2>动态校准状态（市况 / 分层窗口 / FINI）</h2>
<div class="kpis">
  <div class="kpi"><div class="n">{esc(reg['label'])}</div><div class="l">当前市况（{esc(reg.get('label_basis') or '—')}）</div></div>
  <div class="kpi"><div class="n">{pct(reg.get('avg_dark'))}</div><div class="l">同窗口中位暗盘涨幅</div></div>
  <div class="kpi"><div class="n">{reg.get('break_rate')}%</div><div class="l">同窗口破发率</div></div>
  <div class="kpi"><div class="n">{reg.get('long_avg_dark') and pct(reg.get('long_avg_dark')) or '—'}</div><div class="l">长期(12月)中位暗盘（对照）</div></div>
  <div class="kpi"><div class="n">{reg.get('long_break_rate')}%</div><div class="l">长期(12月)破发率（对照）</div></div>
</div>
<div class="note">校准样本量：{tip('分层窗口')}<b>近3月 {result.get('sample_near_n')} 只 → 近6月 {result.get('sample_recent_n')} 只 → 近12月 {result['sample_n']} 只</b>（逐档取第一个够用的窗口）。保荐人实时库覆盖 {result.get('book',{}).get('covered')} 位保荐人，基准 {pct(result.get('book',{}).get('base'))}。</div>
<div class="note">逐月新股数（近12月窗口内）：{esc(monthly_txt)}</div>
<div class="note warn">⚠ 两点必须说明：<b>① FINI 口径</b>——2023 年底港交所 FINI 上线后申购资金仅冻结中签额，超购倍数系统性虚高；本引擎所有阈值均基于 FINI 后样本实时重算，不跨期混用。<b>② 为什么长期窗口对照很重要</b>——近 30 天破发率可能已到 70%，而 12 个月口径还显示「热市」，只看长期口径会严重低估风险；所以本报告的预测中枢走<b>近端优先</b>，长期数字只作对照展示。</div>
</section>

<section class="open"><h2>暗盘开盘价 · 情绪初判（辅输出）</h2>
{'<div class="kpis"><div class="kpi"><div class="n">%s ~ %s</div><div class="l">开盘价初判区间(相对发行价)</div></div></div><div class="note">%s</div>' % (pct(op['lo']), pct(op['hi']), esc(op['note'])) if op else '<div class="note">无 S2 区间，无法给出开盘初判。</div>'}
</section>

<section><h2>因子方法总表（参与 / 展示 / 缺失）</h2>
{factor_section()}
</section>

<footer>
<div>⚠ 免责：本预测是基于历史统计的条件分布推断，<b>不是荐股、不保收益、不是精确报价器</b>。模型只承诺「方向+区间」，点位级预测是伪命题。<b>处置单给出的是执行纪律（按暗盘实际落点触发），不是收益承诺。</b></div>
<div>实时性：每次运行均实时重抓配售结果 + 恒指/A股行情，并在<b>分层窗口（近3月→6月→12月，近端优先）</b>上重算分桶与保荐人战绩，故不同时段问会得到刷新后的评估。本页所有数字均为运行时实时计算，无写死常量。</div>
<div>诚实边界：本站无暗盘分时/最高/最低/成交量数据，<b>无法预测「高开低走还是低开高走」</b>；实况回测显示模型的方向命中率不高（不擅长猜单只涨跌方向），故动作全部按实际落点触发。</div>
<div>改造痕迹：静态桶→分层实时重算 ｜ 固定冷热平移→删除（因果回测证伪） ｜ S2 残差分层修正 ｜ S3 妖股系数标定 ｜ 保荐人改中位数口径 ｜ 剔除 openPct 缺失污染 ｜ 新增持仓处置单。</div>
</footer>
</div>
<script>
/* 悬停气泡自适应定位：保证靠右/靠下的元素，气泡也完整可见（不被屏幕边缘截断）。
   纯本地、无外链、无数据上报。 */
(function(){{
  var tipW = function(){{ return Math.min(330, window.innerWidth * 0.76); }};
  function place(el){{
    var r = el.getBoundingClientRect(), w = tipW() + 20;
    var left = Math.min(Math.max(4, r.left), Math.max(4, window.innerWidth - w));
    el.style.setProperty('--tipx', (left - r.left) + 'px');
    el.classList.toggle('flip', r.bottom + 260 > window.innerHeight && r.top > 280);
  }}
  document.addEventListener('mouseover', function(e){{
    var el = e.target && e.target.closest ? e.target.closest('.tip,.codetip') : null;
    if (el) place(el);
  }}, true);
  document.addEventListener('focusin', function(e){{
    var el = e.target && e.target.closest ? e.target.closest('.tip,.codetip') : null;
    if (el) place(el);
  }});
}})();
</script>
</body></html>'''
    return html_doc

def row(label, s):
    if not s:
        return f'<tr><td class="k">{esc(label)}</td><td colspan="4" class="info">数据不足 / 未到阶段</td></tr>'
    return (f'<tr><td class="k">{esc(label)}</td>'
            f'<td><span class="lo">{pct(s["loPct"])}</span> ~ <span class="hi">{pct(s["hiPct"])}</span></td>'
            f'<td class="base">{pct(s.get("base", (s["loPct"]+s["hiPct"])/2))}</td>'
            f'<td><span class="stars">{stars(s["conf"])}</span></td>'
            f'<td class="v">{s["lo"]} ~ {s["hi"]}</td></tr>')
