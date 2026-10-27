"""Static page: tabs, tables and an in-page chart. Everything is inline (no external requests), so it works on GitHub Pages or from a file."""
import html, json
import numpy as np, pandas as pd
import metrics

MINUS = "\u2212"
esc = html.escape


def fs(x):
    if x is None or pd.isna(x): return "–"
    a = abs(x)
    if a >= 1e7: return f"{x / 1e7:,.2f} cr"
    if a >= 1e5: return f"{x / 1e5:,.1f} L"
    return f"{x:,.0f}"


def fl(x):
    return "–" if x is None or pd.isna(x) else f"{x / 1e5:+,.1f} L".replace("-", MINUS)


def pc(x, d=1, plus=True):
    if x is None or pd.isna(x): return "–"
    s = f"{x:+.{d}f}%" if plus else f"{x:.{d}f}%"
    return s.replace("-", MINUS)


def mult(x, d=1):
    if x is None or pd.isna(x): return "–"
    if x < -99: return f"<{MINUS}99×"
    if x > 99: return ">99×"
    return f"{x:+.{d}f}×".replace("-", MINUS)


def heat(v, full):
    if v is None or pd.isna(v): return ""
    a = min(abs(v) / full, 1.0) * 0.78
    rgb = "46,170,100" if v > 0 else "205,70,60"
    return f' style="background:rgba({rgb},{a:.2f})"'


def pct_badge(p):
    if p is None or pd.isna(p): return '<span class="pb">–</span>'
    a = max(0.0, (p - 50) / 50) * 0.8
    return f'<span class="pb" style="background:rgba(190,75,60,{a:.2f})">{p:.0f}</span>'


def stk(s, M):
    w = ' <span class="warn" title="Unresolved price jump in this stock\'s history (see Corporate Actions). Moving averages may be distorted.">⚠</span>' if s in M["unresolved"] else ""
    return f'<a class="stk" data-s="{esc(s)}">{esc(s)}</a>{w}'


def bar(v, mx):
    w = max(0.03, min(1.0, v / mx)) * 120 if pd.notna(v) and mx else 3
    return f'<span class="bar" style="width:{w:.0f}px"></span>'


def table(head, rows, cls=""):
    th = "".join(f'<th class="{c}">{h}</th>' for h, c in head)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


# ------------------------------------------------------------------ tabs
def tab_screen(M, n=30):
    df = M["screen"].head(n); mx = df["ratio"].max(); rows = []
    for i, r in df.iterrows():
        bse = M["bse_share"][r.sym].iloc[-1]
        rows.append(f'<tr><td class="mut">{i + 1}</td><td class="l">{stk(r.sym, M)}</td><td>{fs(r.dq)}</td><td class="mut">{bse:.0f}</td>'
                    f'<td class="l">{bar(r.ratio, mx)}<span class="bv">{r.ratio:.2f}×</span></td><td>{r.delivpct:.1f}</td><td{heat(r.px1d, 6)}>{pc(r.px1d)}</td>'
                    f'<td>{fs(r.oi)}</td><td{heat(r.doi_pct, 12)}>{fl(r.doi)}</td><td{heat(r.doi_pct, 12)}>{pc(r.doi_pct)}</td><td>{mult(r.d_over_doi)}</td>'
                    f'<td>{pct_badge(r.pct)}</td><td class="mut">{r.value_cr:,.0f}</td></tr>')
    head = [("#", "mut"), ("STOCK", "l"), ("DELIVERED", ""), ("BSE %", ""), (f"÷ 20-DAY AVG", "l"), ("DELIV %", ""), ("PX 1D", ""), ("SSF OI", ""), ("ΔOI 1D", ""), ("ΔOI %", ""), ("DELIV ÷ ΔOI", ""), (f"{M['hist_label']} PCT", ""), ("₹ CR", "")]
    return (f'<h2>1-day delivery vs 20-day average <span class="sub">TOP {n}</span></h2>'
            f'<p class="desc">F&amp;O universe, {len(M["syms"])} names; shares, NSE + BSE. Deliv % = share of traded quantity that went home. {M["hist_label"]} pct = today\'s deliverable quantity against the stock\'s own history in this file ({M["N"]} sessions so far). '
            f'The 20-day average is the mean of the previous 20 sessions\' delivered shares. Futures OI is shares summed over all expiries. ₹ cr = delivered value.</p>' + table(head, rows))


def tab_persist(M, n=40):
    df = M["persist"].head(n); mx = df["ratio"].max() if len(df) else 1; rows = []
    for i, r in df.iterrows():
        rows.append(f'<tr><td class="mut">{i + 1}</td><td class="l">{stk(r.sym, M)}</td><td>{int(r.d125)} <span class="mut">/</span> {int(r.d150)}</td><td class="l">{bar(r.ratio, mx)}<span class="bv">{r.ratio:.2f}×</span></td>'
                    f'<td>{fs(r.dq5)}</td><td>{r.delivpct:.1f}</td><td{heat(r.px5, 10)}>{pc(r.px5)}</td><td>{fs(r.oi)}</td><td{heat(r.doi_pct, 25)}>{fl(r.doi5)}</td><td{heat(r.doi_pct, 25)}>{pc(r.doi_pct)}</td>'
                    f'<td>{mult(r.d_over_doi)}</td><td>{pct_badge(r.pct)}</td></tr>')
    head = [("#", "mut"), ("STOCK", "l"), ("DAYS ≥1.25× / 1.5×", ""), ("5-DAY AVG ÷ 20D", "l"), ("5D DELIVERED", ""), ("DELIV %", ""), ("PX 5D", ""), ("SSF OI", ""), ("ΔOI 5D", ""), ("ΔOI %", ""), ("DELIV ÷ ΔOI", ""), (f"{M['hist_label']} PCT", "")]
    q = len(M["persist"]); q15 = int((M["persist"]["d150"] >= 3).sum())
    return (f'<h2>Persistent delivery <span class="sub">≥3 OF THE LAST 5 SESSIONS ABOVE 1.25× 20D</span></h2>'
            f'<p class="desc">{q} qualify ({q15} at 1.5×); sorted by 5-day average ÷ 20d (the 5-day mean of delivered shares over the mean of the 20 sessions before them). Price and OI change from {M["persist_from"]:%d %b}. '
            f'{M["hist_label"]} pct ranks the 5-day average against the stock\'s own rolling 5-day averages.</p>' + table(head, rows))


def tab_rel(M):
    active = M["active_ma"]; blocks = []
    for k, (name, h) in enumerate(metrics.HORIZONS):
        L = M["rel"][name]; parts = []
        for side, title, col in (("top", "Outperformers", "g"), ("bot", "Underperformers", "r")):
            ser = L[side]; newset = L["new_" + side]; cnt = M["cnt_top"] if side == "top" else M["cnt_bot"]; rows = []
            for s, v in ser.items():
                cells = "".join(f'<td{heat(M["dist"][n][s].iloc[M["T"]], 25)}>{pc(M["dist"][n][s].iloc[M["T"]], 0)}</td>' if pd.notna(M["dist"][n][s].iloc[M["T"]]) else '<td class="mut">–</td>' for n in active)
                strong = ' class="strong ' + col + '"' if cnt[s] >= 3 else ""
                rows.append(f'<tr class="{"newrow" if s in newset else ""}"><td class="l tk {col}"><span{strong}>{stk(s, M)}</span></td><td class="{col}">{pc(v)}</td>{cells}</tr>')
            head = [("TICKER", "l"), ("REL %", "")] + [(str(n), "") for n in active]
            parts.append(f'<div class="card"><div class="ch"><span class="ct {col}">{title}</span><span class="mut">{name}</span></div>{table(head, rows, "rel")}</div>')
        blocks.append(f'<div class="hz" data-h="{k}"{"" if k == 0 else " hidden"}>{"".join(parts)}</div>')
    btns = "".join(f'<button class="seg{" on" if k == 0 else ""}" data-h="{k}">{name}</button>' for k, (name, _) in enumerate(metrics.HORIZONS))
    return (f'<h2>Relative performance</h2><div class="subl">TOP AND BOTTOM {metrics.LIST_N} OF {len(M["syms"])} VS NIFTY</div><div class="segs">{btns}</div>{"".join(blocks)}'
            f'<p class="desc">Rel % = return relative to the Nifty over the horizon ((1 + stock) ÷ (1 + Nifty) − 1); the numbered columns = % distance from that moving average (green above, red below, full depth at 25%). '
            f'A red bar = new on that list since the previous session; green / red bold ticker = on three or more of the five horizons.</p>')


def tab_results(M):
    rows = []
    events = M.get("results", [])
    for r in events:
        hits = [x for x in r["sessions"] if x["hit"]]
        signal = ('<span class="rsig">PRE-RESULT ACTIVITY</span>' if hits else '<span class="mut">—</span>')
        trail = []
        by_lag = {x["lag"]: x for x in r["sessions"]}
        for lag in (3, 2, 1):
            x = by_lag.get(lag)
            if not x:
                trail.append('<td class="mut">—</td>'); continue
            cls = ' class="rhit"' if x["hit"] else ''
            trail.append(f'<td{cls}><b>D−{lag}</b> {x["ratio"]:.2f}× / {pc(x["move"])} / {x["z"]:+.2f}σ</td>')
        when = f'{r["declared_at"]:%d %b %H:%M}' if pd.notna(r["declared_at"]) else f'{r["event_date"]:%d %b}'
        source = f'<a class="src" href="{esc(str(r["source_url"]))}" target="_blank" rel="noopener">NSE ↗</a>' if r.get("source_url") else ''
        rows.append(f'<tr><td class="l">{stk(r["symbol"], M)}</td><td>{when}</td><td>{r["status"]}</td><td>{signal}</td>{"".join(trail)}<td>{source}</td></tr>')
    head = [("STOCK", "l"), ("RESULT DATE", ""), ("STATUS", ""), ("SIGNAL", ""),
            ("D−3: DELIVERY / MOVE / σ", ""), ("D−2", ""), ("D−1", ""), ("FILING", "")]
    if not rows:
        empty = '<div class="card rempty">No result dates in the current F&amp;O window. The calendar will fill automatically as NSE filings arrive.</div>'
        return '<h2>Results calendar</h2>' + empty
    return (f'<h2>Results calendar</h2><div class="subl">PRE-RESULT DELIVERY AND PRICE ACTIVITY</div>'
            '<p class="desc">A signal requires delivered shares above the prior 20-session average and an absolute price move above 0.8σ on the same session. '
            'σ is the stock’s prior-60-session daily-return volatility. D−1 to D−3 are completed trading sessions before the declaration date; no future data is used.</p>'
            + table(head, rows, "results"))


def tab_at(M):
    out = []
    for n in M["active_ma"]:
        items = M["at"][n]
        chips = "".join(f'<span class="chip {"u" if x["above"] else "d"}{" cr" if x["crossed"] else ""}{" nw" if x["new"] else ""}" title="{x["dist"]:+.2f}% from the {n}-day average = {x["k"]:.2f} σ (σ = {x["sigma"]:.2f}% daily)">'
                        f'{"▲" if x["above"] else "▼"} <a class="stk" data-s="{esc(x["sym"])}">{esc(x["sym"])}</a></span>' for x in items) or '<span class="mut">none</span>'
        out.append(f'<div class="atrow"><div class="atn"><div class="big">{n}</div><div class="mut">{len(items)} NAMES</div></div><div class="chips">{chips}</div></div>')
    for n, need in M["inactive_ma"]:
        out.append(f'<div class="atrow off"><div class="atn"><div class="big">{n}</div><div class="mut">OFF</div></div><div class="chips mut">Needs {n + 1} sessions of history; have {M["N"]}. Switches on in {need} sessions.</div></div>')
    return (f'<h2>Stocks at a moving average</h2><div class="subl">WITHIN 0.5σ, CLOSEST FIRST</div>'
            f'<p class="desc">▲ above · ▼ below · boxed = crossed today · underlined = new on the list. “Within 0.5σ” means the close is within half of the stock\'s own daily standard deviation ({metrics.SIGMA_WINDOW}-session) of the average, so a stock that moves 2% a day counts as at its average when it is within 1% of it. Hover a name for its exact distance.</p>'
            f'<div class="card">{"".join(out)}</div>')


# ------------------------------------------------------------------ assemble
def stocks_json(M):
    dates = [f"{d:%Y-%m-%d}" for d in M["dates"]]; out = {}; T = M["T"]
    ev = M["events"]; di = {d: i for i, d in enumerate(M["dates"])}
    nz = lambda x, f=float: None if x is None or pd.isna(x) else f(x)
    for s in M["syms"]:
        rel = [[nz(M["relT"][name][s], lambda v: round(float(v), 2)), nz(M["relrank"][name][s], int)] for name, _ in metrics.HORIZONS]
        sm = dict(px=nz(M["ret1"][s].iloc[T] * 100, lambda v: round(float(v), 2)), ratio=nz(M["RAT"][s].iloc[T], lambda v: round(float(v), 2)),
                  dp=nz(M["dq_raw"][s].iloc[T] / M["tq_raw"][s].iloc[T] * 100, lambda v: round(float(v), 1)), bse=nz(M["bse_share"][s].iloc[T], lambda v: round(float(v), 0)),
                  oi=nz(M["oi"][s].iloc[T], int), doi=nz(M["doi"][s].iloc[T], int), dq=nz(M["DQ"][s].iloc[T], int), rel=rel)
        out[s] = dict(c=[nz(x, lambda v: round(float(v), 2)) for x in M["C"][s]], dq=[nz(x, int) for x in M["DQ"][s]],
                      rat=[nz(x, lambda v: round(float(v), 2)) for x in M["RAT"][s]], d=[nz(x, int) for x in M["dcode"][s]], oi=[nz(x, int) for x in M["OIadj"][s]], sm=sm,
                      ev=[[di[e["date"]], round(float(e["factor"]), 4), e["decision"]] for _, e in ev[ev["symbol"] == s].iterrows() if e["date"] in di and e["decision"] in ("auto", "accepted")])
    default = M["screen"]["sym"].iloc[0] if len(M["screen"]) else M["syms"][0]
    return dict(dates=dates, mas=metrics.MA_SET, nifty=[nz(x, lambda v: round(float(v), 2)) for x in M["nifty"]], hz=[[n, h] for n, h in metrics.HORIZONS], default=default, stocks=out)


def tab_stocks(M):
    return ('<div class="sx"><aside class="sl"><input id="q" placeholder="Search ticker" autocomplete="off" autocapitalize="characters" spellcheck="false">'
            '<select id="sort"><option value="az">Sort: A to Z</option><option value="ratio">Sort: delivery ÷ 20d avg</option><option value="px">Sort: price move today</option><option value="rs">Sort: 20-day relative strength</option></select>'
            '<div id="list"></div></aside><div class="sr"><div id="sh"></div>'
            '<div class="rb"><span class="mut">RANGE</span><button class="seg on" data-r="252">1Y</button><button class="seg" data-r="126">6M</button><button class="seg" data-r="63">3M</button>'
            '<span class="mut" style="margin-left:18px">ABOVE-AVERAGE DELIVERY</span><select id="thr"><option value="1">1.0×</option><option value="1.25" selected>1.25×</option><option value="1.5">1.5×</option><option value="2">2.0×</option></select></div>'
            '<div id="chartbox"><svg id="ch"></svg></div><div id="ro"></div><div id="lg"></div></div></div>')


def render(M, asof_text):
    M["hist_label"] = "1Y" if M["N"] < 600 else "3Y"
    data = json.dumps(stocks_json(M), separators=(",", ":"))
    panels = [("stocks", "STOCKS", tab_stocks(M)), ("screen", "1-DAY SCREEN", tab_screen(M)), ("persist", "PERSISTENT DELIVERY", tab_persist(M)),
              ("results", "RESULTS CALENDAR", tab_results(M)), ("rel", "RELATIVE PERFORMANCE", tab_rel(M)), ("at", "AT A MOVING AVERAGE", tab_at(M))]
    nav = "".join(f'<button class="tab{" on" if i == 0 else ""}" data-t="{k}">{lbl}</button>' for i, (k, lbl, _) in enumerate(panels))
    body = "".join(f'<section class="panel" id="p-{k}"{"" if i == 0 else " hidden"}>{h}</section>' for i, (k, _, h) in enumerate(panels))
    head = (f'<header><div class="brand">DESK</div><div class="meta">{asof_text}<br><span class="mut">{M["N"]} sessions since {M["dates"][0]:%d %b %Y} · {len(M["syms"])} F&amp;O names · NSE + BSE delivery</span></div></header>')
    foot = '<footer>Splits, bonuses and demergers are detected and adjusted automatically (prices, averages and delivered shares are all on today\'s share basis). Delivery % is shown for reference and never used to rank.</footer>'
    return (HTML.replace("%%CSS%%", CSS).replace("%%HEAD%%", head).replace("%%NAV%%", nav).replace("%%BODY%%", body + foot)
            .replace("%%DATA%%", data.replace("</", "<\\/")).replace("%%JS%%", JS).replace("%%TITLE%%", f"Desk · {M['dates'][-1]:%d %b %Y}"))


HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>%%TITLE%%</title><style>%%CSS%%</style></head><body>%%HEAD%%<nav class="tabs">%%NAV%%</nav><main>%%BODY%%</main>
<script id="data" type="application/json">%%DATA%%</script><script>%%JS%%</script></body></html>"""

CSS = r"""
:root{--bg:#0a0a0a;--panel:#141414;--line:#262626;--ink:#f2f2ee;--mut:#8b8b86;--g:#3fbf7a;--r:#ef5a4d;--am:#e8a93a;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;box-sizing:border-box;
padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
*,*::before,*::after{box-sizing:inherit}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.45}
header{display:flex;justify-content:space-between;gap:16px;align-items:flex-end;padding:18px 22px 12px;border-bottom:1px solid var(--line)}
.brand{font-weight:800;letter-spacing:.18em;font-size:20px}.meta{font-family:var(--mono);font-size:12px;text-align:right}.mut{color:var(--mut)}
.tabs{display:flex;gap:4px;padding:10px 18px;border-bottom:1px solid var(--line);overflow-x:auto;position:sticky;top:env(safe-area-inset-top,0px);background:var(--bg);z-index:5}
.tab{font:600 13px var(--sans);letter-spacing:.09em;color:var(--mut);background:none;border:0;padding:11px 16px;cursor:pointer;white-space:nowrap}
.tab.on{background:#f4f4f0;color:#0a0a0a}.tab:focus-visible,.seg:focus-visible,#mx:focus-visible{outline:2px solid var(--am);outline-offset:2px}
main{max-width:1280px;margin:0 auto;padding:6px 22px 60px}
h2{font-size:30px;line-height:1.1;margin:30px 0 6px;font-weight:800;letter-spacing:-.01em}h2 .sub,.subl{font:600 13px var(--sans);letter-spacing:.12em;color:var(--mut);margin-left:10px}.subl{margin:0 0 12px}
.desc{color:#9a9a94;font-size:17px;line-height:1.6;max-width:1000px;margin:6px 0 18px}.desc b{color:var(--ink)}
.card,.tw{background:var(--panel);border-top:3px solid #f4f4f0}.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}.card .tw{border-top:0}
table{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:15px}
th{font:600 12.5px var(--sans);letter-spacing:.1em;color:var(--mut);text-align:right;padding:18px 12px 12px;white-space:nowrap;border-bottom:2px solid #2c2c2c}
td{padding:14px 12px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}th.l,td.l{text-align:left}th.mut,td.mut{color:var(--mut)}
td.l a.stk,td.l span{font-weight:700;letter-spacing:.02em}.stk{cursor:pointer;color:var(--ink);text-decoration:none}.stk:hover{text-decoration:underline}
.warn{color:var(--am);font-size:12px}.bar{display:inline-block;height:12px;background:#f4f4f0;border-radius:3px;vertical-align:middle;margin-right:10px}.bv{display:inline-block;min-width:56px}
.pb{display:inline-block;min-width:44px;padding:6px 8px;border-radius:3px;color:#fff;background:#222;text-align:center}
.rsig{display:inline-block;padding:5px 8px;background:var(--am);color:#0a0a0a;font:700 11px var(--sans);letter-spacing:.06em}.rhit{background:rgba(232,169,58,.2);color:#ffd17a}.src{color:var(--ink)}.rempty{padding:22px;color:var(--mut)}
.segs{display:flex;gap:0;margin:0 0 16px;border:2px solid #f4f4f0;width:max-content;max-width:100%;overflow-x:auto}.seg{font:600 15px var(--sans);color:var(--ink);background:none;border:0;padding:12px 22px;cursor:pointer;white-space:nowrap}.seg.on{background:#f4f4f0;color:#0a0a0a}
.hz{display:grid;grid-template-columns:1fr 1fr;gap:20px}.ch{display:flex;justify-content:space-between;padding:20px 18px 6px}.ct{font-size:22px;font-weight:700}.g{color:var(--g)}.r{color:var(--r)}
table.rel td,table.rel th{padding:11px 12px}tr.newrow td.tk{box-shadow:inset 5px 0 var(--r)}span.strong.g a{color:var(--g)}span.strong.r a{color:var(--r)}
.atrow{display:flex;gap:26px;padding:22px 20px;border-bottom:1px solid var(--line)}.atn{min-width:96px}.big{font:700 44px var(--mono);line-height:1}.chips{display:flex;flex-wrap:wrap;gap:10px;align-content:flex-start}
.atrow.off .big{color:#4a4a46}.atrow.off .chips{align-self:center}
.chip{font:700 17px var(--mono);padding:9px 14px;background:#1b1b1b;border-radius:3px;border:2px solid transparent}.chip.u{color:var(--g)}.chip.d{color:var(--r)}.chip a{color:inherit;text-decoration:none}
.chip.cr{border-color:var(--r)}.chip.u.cr{border-color:var(--g)}.chip.nw a{text-decoration:underline;text-decoration-thickness:3px;text-underline-offset:5px}
table.ca td.note{white-space:normal;min-width:340px;max-width:560px;color:#b9b9b2;font-family:var(--sans);font-size:14px}tr.rv td{background:rgba(232,169,58,.08)}tr.rv td b{color:var(--am)}tr.ok td b{color:var(--g)}
#modal{position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:20;display:flex;align-items:center;justify-content:center;padding:14px}.mbox{background:#101010;border:1px solid #333;width:min(1040px,100%);max-height:100%;overflow:auto;padding:16px 18px;position:relative}
#mx{position:absolute;right:10px;top:6px;font-size:30px;color:var(--mut);background:none;border:0;cursor:pointer}#mh{font:600 15px var(--mono);margin:0 40px 8px 0}#mh b{font-size:22px;font-family:var(--sans)}#mc{width:100%;height:auto;display:block}#ml{font:12px var(--mono);color:var(--mut);margin-top:8px;display:flex;flex-wrap:wrap;gap:4px 16px}
#ml i{display:inline-block;width:18px;border-top:2px solid;vertical-align:middle;margin-right:5px}
.sx{display:grid;grid-template-columns:290px minmax(0,1fr);gap:18px;margin-top:18px}.sl{background:var(--panel);border-top:3px solid #f4f4f0;padding:12px;align-self:start;position:sticky;top:72px}
#q{width:100%;font:600 16px var(--mono);background:#0d0d0d;color:var(--ink);border:1px solid #333;padding:11px 12px;margin-bottom:8px;border-radius:3px}#q:focus{outline:2px solid var(--am)}
#sort,#thr{font:600 13px var(--sans);background:#0d0d0d;color:var(--ink);border:1px solid #333;padding:7px 8px;border-radius:3px}#sort{width:100%;margin-bottom:6px}
#list{max-height:68vh;overflow:auto;margin:0 -12px -12px}.li{display:grid;grid-template-columns:1fr auto auto;gap:12px;padding:10px 14px;border-bottom:1px solid var(--line);cursor:pointer;font-family:var(--mono);font-size:14px;align-items:center}
.li:hover{background:#1c1c1c}.li.on{background:#262626;box-shadow:inset 4px 0 #f4f4f0}.li b{letter-spacing:.02em}.li span{min-width:52px;text-align:right}
.sr{min-width:0}#sh{background:var(--panel);border-top:3px solid #f4f4f0;padding:16px 18px 14px}.hd1{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 16px}.hd1 b{font-size:30px;letter-spacing:.01em}.hd1 .px{font:700 24px var(--mono)}
.chips2{display:flex;flex-wrap:wrap;gap:8px 22px;margin-top:12px;font:13px var(--mono)}.chips2 div span{display:block;color:var(--mut);font:600 11px var(--sans);letter-spacing:.1em;margin-bottom:2px}
.rsrow{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:12px;padding-top:12px;border-top:1px solid var(--line);font:13px var(--mono)}.rsrow span{color:var(--mut)}
.rb{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:12px 0 10px;font:600 12px var(--sans);letter-spacing:.1em}.rb .seg{padding:8px 14px;font-size:13px;border:1px solid #444}
#chartbox{background:var(--panel);padding:6px 4px 2px}#ch{display:block;width:100%;touch-action:pan-y}#ro{min-height:24px;font:13px var(--mono);color:#cfcfc8;padding:8px 4px}
#lg{display:flex;flex-wrap:wrap;gap:6px 18px;font:12px var(--mono);color:var(--mut);padding:2px 4px 10px}#lg i{display:inline-block;width:14px;height:10px;margin-right:6px;vertical-align:-1px}#lg u{display:inline-block;width:18px;border-top:2px solid;margin-right:5px;vertical-align:middle}
footer{max-width:1280px;margin:0 auto;padding:0 22px 40px;color:var(--mut);font-size:13px}
@media (max-width:900px){.sx{grid-template-columns:1fr}.sl{position:static}#list{max-height:230px}.hd1 b{font-size:24px}header{flex-direction:column;align-items:flex-start}.meta{text-align:left}h2{font-size:25px}.desc{font-size:15px}.hz{grid-template-columns:1fr}table{font-size:13.5px}td{padding:11px 9px}.atrow{flex-direction:column;gap:12px}main{padding:6px 12px 50px}}
"""

JS = r"""
const D=JSON.parse(document.getElementById('data').textContent),SY=Object.keys(D.stocks);
const COL={32:'#5aa9ff',50:'#f5a623',100:'#b58cff',200:'#ffd84d',233:'#3fd0a0',377:'#ff7aa2',610:'#9a9a94'};
const G='#2fbf71',R='#ef5a4d',GL='rgba(47,191,113,.46)',RL='rgba(239,90,77,.46)',GR='#a3a39c',GRL='rgba(163,163,156,.30)';
let cur=null,rng=252,thr=1.25;
function tab(t){const b=document.querySelector('.tab[data-t="'+t+'"]');if(b)b.click()}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!=='p-'+b.dataset.t);if(b.dataset.t==='stocks'){draw()}});
document.querySelectorAll('.seg[data-h]').forEach(b=>b.onclick=()=>{document.querySelectorAll('.seg[data-h]').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.hz').forEach(h=>h.hidden=h.dataset.h!==b.dataset.h)});
document.querySelectorAll('.seg[data-r]').forEach(b=>b.onclick=()=>{rng=+b.dataset.r;document.querySelectorAll('.seg[data-r]').forEach(x=>x.classList.toggle('on',x===b));draw()});
document.getElementById('thr').onchange=e=>{thr=+e.target.value;draw()};
function sma(a,n){const o=new Array(a.length).fill(null);let s=0,c=0;for(let i=0;i<a.length;i++){const v=a[i];if(v!=null){s+=v;c++}if(i>=n){const u=a[i-n];if(u!=null){s-=u;c--}}if(c===n&&i>=n-1)o[i]=s/n}return o}
function fmt(x){if(x==null)return'–';const a=Math.abs(x);return a>=1e7?(x/1e7).toFixed(2)+' cr':a>=1e5?(x/1e5).toFixed(1)+' L':Math.round(x).toLocaleString()}
function fL(x){return x==null?'–':(x>=0?'+':'−')+Math.abs(x/1e5).toLocaleString(undefined,{maximumFractionDigits:1,minimumFractionDigits:1})+' L'}
function pc(x,d=1){return x==null?'–':(x>=0?'+':'−')+Math.abs(x).toFixed(d)+'%'}
function cls(x){return x==null?'':x>=0?'g':'r'}
/* ---------- ticker list ---------- */
function list(){const q=document.getElementById('q').value.trim().toUpperCase(),so=document.getElementById('sort').value;
 const key={az:s=>s,ratio:s=>-(D.stocks[s].sm.ratio??-1e9),px:s=>-(D.stocks[s].sm.px??-1e9),rs:s=>-(D.stocks[s].sm.rel[1][0]??-1e9)}[so];
 const a=SY.filter(s=>!q||s.includes(q)).sort((x,y)=>{const a=key(x),b=key(y);return a<b?-1:a>b?1:0});
 document.getElementById('list').innerHTML=a.map(s=>{const m=D.stocks[s].sm;return `<div class="li${s===cur?' on':''}" data-s="${s}"><b>${s}</b><span class="${cls(m.px)}">${pc(m.px)}</span><span class="mut">${m.ratio==null?'–':m.ratio.toFixed(1)+'×'}</span></div>`}).join('')||'<div class="li mut">No match</div>'}
document.getElementById('q').oninput=list;document.getElementById('sort').onchange=list;
document.getElementById('q').onkeydown=e=>{if(e.key==='Enter'){const f=document.querySelector('#list .li[data-s]');if(f)pick(f.dataset.s)}};
document.getElementById('list').onclick=e=>{const li=e.target.closest('.li[data-s]');if(li)pick(li.dataset.s)};
function pick(s){cur=s;list();draw();history.replaceState(null,'','#'+s);if(window.innerWidth<900)document.getElementById('sh').scrollIntoView({behavior:'smooth',block:'start'})}
document.addEventListener('click',e=>{const a=e.target.closest('a.stk');if(a){e.preventDefault();tab('stocks');cur=a.dataset.s;list();draw();history.replaceState(null,'','#'+cur);window.scrollTo(0,0)}});
/* ---------- chart ---------- */
function draw(){
 if(!cur||document.getElementById('p-stocks').hidden)return;
 const S=D.stocks[cur],n=S.c.length,v0=Math.max(0,n-rng),box=document.getElementById('chartbox'),W=Math.max(320,Math.min(1060,box.clientWidth-8)),sm=W<560,fs=sm?10:11,L=sm?46:60,Rr=10;
 const H=sm?[210,90,80,64,64]:[290,115,105,80,80],gap=sm?24:28,tops=[8];for(let k=1;k<5;k++)tops.push(tops[k-1]+H[k-1]+gap);const TH=tops[4]+H[4]+24;
 const xs=i=>L+(i-v0)*(W-L-Rr)/Math.max(1,n-1-v0),bw=Math.max(1,(W-L-Rr)/(n-v0)*.72);
 const y=(v,lo,hi,k)=>tops[k]+(1-(v-lo)/(hi-lo||1))*H[k];
 let g='';const lab=(t,k)=>`<text x="${L+4}" y="${tops[k]+11}" fill="#77776f" font-size="${fs}" font-family="monospace" letter-spacing="1">${t}</text>`;
 const grid=(lo,hi,k,f)=>{let o='';for(let j=0;j<=2;j++){const v=lo+(hi-lo)*j/2,yy=y(v,lo,hi,k);o+=`<line x1="${L}" x2="${W-Rr}" y1="${yy}" y2="${yy}" stroke="#222"/><text x="${L-5}" y="${yy+3}" fill="#77776f" font-size="${fs}" text-anchor="end" font-family="monospace">${f(v)}</text>`}return o};
 const path=(a,k,lo,hi,col,sw,dash,base)=>{let d='',pen=false;for(let i=v0;i<n;i++){const v=a[i];if(v==null){pen=false;continue}d+=(pen?'L':'M')+xs(i).toFixed(1)+','+y(base?base(v):v,lo,hi,k).toFixed(1);pen=true}return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${sw}"${dash?' stroke-dasharray="'+dash+'"':''} stroke-linejoin="round"/>`};
 /* 1 price + averages */
 const mas=D.mas.filter(m=>n>=m+1).map(m=>[m,sma(S.c,m)]);let lo=1e18,hi=-1e18;for(let i=v0;i<n;i++){const v=S.c[i];if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v)}}
 const lo0=lo,hi0=hi;mas.forEach(([m,a])=>{for(let i=v0;i<n;i++){const v=a[i];if(v!=null&&v>lo0*.8&&v<hi0*1.25){lo=Math.min(lo,v);hi=Math.max(hi,v)}}});const pd=(hi-lo)*.05;lo-=pd;hi+=pd;
 g+=lab(sm?'PRICE · AVERAGES':'PRICE (ADJUSTED) · MOVING AVERAGES',0)+grid(lo,hi,0,v=>v.toFixed(v>=1000?0:1));
 mas.forEach(([m,a])=>g+=path(a,0,lo,hi,COL[m],m===200?1.9:1.3));g+=path(S.c,0,lo,hi,'#fff',1.8);
 /* 2 delivery bars */
 const avg=new Array(n).fill(null);for(let i=20;i<n;i++){let s=0,c=0;for(let j=i-20;j<i;j++)if(S.dq[j]!=null){s+=S.dq[j];c++}if(c>=15)avg[i]=s/c}
 let mx=0;for(let i=v0;i<n;i++)mx=Math.max(mx,S.dq[i]||0,avg[i]||0);mx*=1.05;
 g+=lab(sm?'DELIVERED · DASHED = 20D AVG':'DELIVERED SHARES · DASHED = 20-DAY AVERAGE',1)+grid(0,mx,1,fmt);
 for(let i=v0;i<n;i++){const q=S.dq[i];if(q==null)continue;const hi_=(S.rat[i]??0)>=thr,d=S.d[i];const col=d===0?(hi_?GR:GRL):d===1?(hi_?G:GL):d===-1?(hi_?R:RL):GRL;const h=q/mx*H[1];g+=`<rect x="${(xs(i)-bw/2).toFixed(1)}" y="${(tops[1]+H[1]-h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" fill="${col}"/>`}
 g+=path(avg,1,0,mx,'#e8e8e2',1.3,'4 3');
 /* 3 relative strength */
 const rsf=S.c.map((v,i)=>v!=null&&D.nifty[i]!=null?v/D.nifty[i]:null),rsm=sma(rsf,50);let b0=null;for(let i=v0;i<n;i++)if(rsf[i]!=null){b0=rsf[i];break}
 if(b0){const rb=v=>v/b0*100;let l3=1e18,h3=-1e18;for(let i=v0;i<n;i++){[rsf[i],rsm[i]].forEach(v=>{if(v!=null){l3=Math.min(l3,rb(v));h3=Math.max(h3,rb(v))}})}const p3=(h3-l3)*.08||1;l3-=p3;h3+=p3;
  g+=lab(sm?'RS VS NIFTY (START=100)':'RELATIVE STRENGTH VS NIFTY (START = 100) · ORANGE = 50-DAY AVERAGE OF RS',2)+grid(l3,h3,2,v=>v.toFixed(0));
  if(100>l3&&100<h3)g+=`<line x1="${L}" x2="${W-Rr}" y1="${y(100,l3,h3,2)}" y2="${y(100,l3,h3,2)}" stroke="#555" stroke-dasharray="3 3"/>`;
  g+=path(rsm,2,l3,h3,'#f5a623',1.3,null,rb)+path(rsf,2,l3,h3,'#fff',1.7,null,rb)}
 /* 4 open interest level + 5 buildup bars */
 let l4=1e18,h4=-1e18;for(let i=v0;i<n;i++){const v=S.oi[i];if(v!=null){l4=Math.min(l4,v);h4=Math.max(h4,v)}}
 g+=lab(sm?'SSF OPEN INTEREST':'SSF OPEN INTEREST (SHARES, ALL EXPIRIES)',3);
 if(h4>0){const p4=(h4-l4)*.1||h4*.05;l4=Math.max(0,l4-p4);h4+=p4;g+=grid(l4,h4,3,fmt)+path(S.oi,3,l4,h4,'#7db4ff',1.7)}else g+=`<text x="${L+4}" y="${tops[3]+H[3]/2}" fill="#555" font-size="${fs}" font-family="monospace">not in F&amp;O for this period</text>`;
 g+=lab(sm?'ΔOI · BUILD-UP':'CHANGE IN OI, COLOURED BY BUILD-UP',4);let md=0;const dl=new Array(n).fill(null);for(let i=1;i<n;i++)if(S.oi[i]!=null&&S.oi[i-1]!=null){dl[i]=S.oi[i]-S.oi[i-1];if(i>=v0)md=Math.max(md,Math.abs(dl[i]))}
 const mid=tops[4]+H[4]/2;g+=`<line x1="${L}" x2="${W-Rr}" y1="${mid}" y2="${mid}" stroke="#333"/>`;
 if(md>0){g+=`<text x="${L-5}" y="${tops[4]+9}" fill="#77776f" font-size="${fs}" text-anchor="end" font-family="monospace">${fmt(md)}</text><text x="${L-5}" y="${tops[4]+H[4]}" fill="#77776f" font-size="${fs}" text-anchor="end" font-family="monospace">−${fmt(md)}</text>`;
  for(let i=v0;i<n;i++){const d=dl[i];if(d==null||!(S.c[i]!=null&&S.c[i-1]!=null))continue;const up=S.c[i]>=S.c[i-1],col=d>=0?(up?G:R):(up?GL:RL),h=Math.abs(d)/md*H[4]/2;g+=`<rect x="${(xs(i)-bw/2).toFixed(1)}" y="${(d>=0?mid-h:mid).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(h,.5).toFixed(1)}" fill="${col}"/>`}}
 /* corporate-action markers */
 S.ev.forEach(([i,f])=>{if(i<v0)return;const x=xs(i);g+=`<line x1="${x}" x2="${x}" y1="${tops[0]}" y2="${tops[4]+H[4]}" stroke="${G}" stroke-dasharray="4 3" opacity=".7"/><text x="${x+4}" y="${tops[0]+24}" fill="${G}" font-size="${fs}" font-family="monospace">adjusted ×${f}</text>`});
 [v0,Math.round((v0+n-1)/2),n-1].forEach(i=>g+=`<text x="${xs(i)}" y="${TH-6}" fill="#77776f" font-size="${fs}" text-anchor="${i===v0?'start':i===n-1?'end':'middle'}" font-family="monospace">${D.dates[i]}</text>`);
 g+=`<line id="xh" x1="0" x2="0" y1="${tops[0]}" y2="${tops[4]+H[4]}" stroke="#aaa" visibility="hidden"/>`;
 const svg=document.getElementById('ch');svg.setAttribute('viewBox',`0 0 ${W} ${TH}`);svg.setAttribute('width',W);svg.setAttribute('height',TH);svg.innerHTML=g;
 /* header */
 const m=S.sm,last=S.c[n-1],lastOI=S.oi[n-1],dOI=dl[n-1],up=S.c[n-1]>=S.c[n-2];
 const bu=dOI==null?'–':dOI>=0?(up?'Long build-up':'Short build-up'):(up?'Short covering':'Long unwinding'),buc=dOI==null?'':(up?'g':'r');
 const rs=D.hz.map((h,k)=>{const r=m.rel[k];return `<div><span>${h[0].toUpperCase()}</span><b class="${cls(r[0])}">${pc(r[0])}</b> <i class="mut" style="font-style:normal">#${r[1]??'–'}/${SY.length}</i></div>`}).join('');
 document.getElementById('sh').innerHTML=`<div class="hd1"><b>${cur}</b><span class="px">${last==null?'–':last.toFixed(2)}</span><span class="${cls(m.px)}">${pc(m.px,2)}</span></div>
 <div class="chips2"><div><span>DELIVERED</span>${fmt(m.dq)}</div><div><span>÷ 20D AVG</span>${m.ratio==null?'–':m.ratio.toFixed(2)+'×'}</div><div><span>DELIV %</span>${m.dp==null?'–':m.dp.toFixed(1)}</div><div><span>BSE %</span>${m.bse==null?'–':m.bse.toFixed(0)}</div>
 <div><span>SSF OI</span>${fmt(lastOI)}</div><div><span>ΔOI 1D</span><b class="${cls(dOI)}">${fL(dOI)}</b></div><div><span>OI BUILD-UP</span><b class="${buc}">${bu}</b></div></div>
 <div class="rsrow">${rs}</div>`;
 /* legend + hover */
 document.getElementById('lg').innerHTML=mas.map(([m])=>`<span><u style="border-color:${COL[m]}"></u>${m}</span>`).join('')+`<span><u style="border-color:#fff"></u>price</span><span><i style="background:${G}"></i>up, delivery ≥${thr}× avg</span><span><i style="background:${GL}"></i>up, lower delivery</span><span><i style="background:${R}"></i>down, delivery ≥${thr}× avg</span><span><i style="background:${RL}"></i>down, lower delivery</span><span><i style="background:${GR}"></i>move under 0.5σ (grey)</span><span>OI bars: dark green = long build-up, dark red = short build-up, light green = short covering, light red = long unwinding</span>`;
 const ro=document.getElementById('ro');ro.innerHTML='<span class="mut">Move over the chart for daily detail</span>';
 const mv=e=>{const r=svg.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*W;let i=Math.round(v0+(x-L)*(n-1-v0)/(W-L-Rr));i=Math.max(v0,Math.min(n-1,i));const xh=document.getElementById('xh');xh.setAttribute('x1',xs(i));xh.setAttribute('x2',xs(i));xh.setAttribute('visibility','visible');
  const ch=S.c[i]!=null&&S.c[i-1]!=null?(S.c[i]/S.c[i-1]-1)*100:null;ro.innerHTML=`${D.dates[i]} · close ${S.c[i]??'–'} <span class="${cls(ch)}">${pc(ch,2)}</span> · delivered ${fmt(S.dq[i])} (${S.rat[i]==null?'–':S.rat[i].toFixed(2)+'× avg'}) · ΔOI ${fL(dl[i])}`};
 svg.onpointermove=mv;svg.onpointerdown=mv;svg.onpointerleave=()=>{document.getElementById('xh').setAttribute('visibility','hidden')};
}
let rz;window.addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(draw,120)});
const h0=location.hash.slice(1);cur=D.stocks[h0]?h0:D.default;list();draw();
"""
