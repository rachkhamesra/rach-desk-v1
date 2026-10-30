"""Static page: tabs, tables and an in-page chart. Everything is inline (no external requests), so it works on GitHub Pages or from a file."""
import html, json, re
import numpy as np, pandas as pd
import metrics
from guidance import validated_changes

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


def zscore(x, d=1):
    return "–" if x is None or pd.isna(x) else f"{x:+.{d}f}σ".replace("-", MINUS)


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
    upcoming = [r for r in M.get("results", []) if r["symbol"] == s and r["event_date"].normalize() >= M["dates"][-1].normalize()]
    result = ""
    if upcoming:
        event = min(upcoming, key=lambda r: r["event_date"])
        result = f' <span class="resultmark" title="Upcoming result: {event["event_date"]:%d %b %Y}">RESULT {event["event_date"]:%d %b}</span>'
    return f'<a class="stk" data-s="{esc(s)}">{esc(s)}</a>{result}{w}'


def bar(v, mx):
    w = max(0.03, min(1.0, v / mx)) * 120 if pd.notna(v) and mx else 3
    return f'<span class="bar" style="width:{w:.0f}px"></span>'


def table(head, rows, cls=""):
    th = "".join(f'<th class="{c}">{h}</th>' for h, c in head)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


# ------------------------------------------------------------------ tabs
def tab_screen(M, n=30, allowed=None):
    df = M["screen"]
    if allowed is not None: df = df[df.sym.isin(allowed)]
    df = df.head(n).reset_index(drop=True); mx = df["ratio"].max(); rows = []
    for i, r in df.iterrows():
        bse = M["bse_share"][r.sym].iloc[-1]
        rows.append(f'<tr><td class="mut">{i + 1}</td><td class="l">{stk(r.sym, M)}</td><td>{fs(r.dq)}</td><td class="mut">{bse:.0f}</td>'
                    f'<td class="l">{bar(r.ratio, mx)}<span class="bv">{r.ratio:.2f}×</span></td><td>{r.delivpct:.1f}</td><td{heat(r.px1d, 6)}>{pc(r.px1d)}</td>'
                    f'<td>{fs(r.oi)}</td><td{heat(r.doi_pct, 12)}>{fl(r.doi)}</td><td{heat(r.doi_pct, 12)}>{pc(r.doi_pct)}</td><td>{mult(r.d_over_doi)}</td>'
                    f'<td>{pct_badge(r.pct)}</td><td class="mut">{r.value_cr:,.0f}</td></tr>')
    head = [("#", "mut"), ("STOCK", "l"), ("DELIVERED", ""), ("BSE %", ""), (f"÷ 20-DAY AVG", "l"), ("DELIV %", ""), ("PX 1D", ""), ("SSF OI", ""), ("ΔOI 1D", ""), ("ΔOI %", ""), ("DELIV ÷ ΔOI", ""), (f"{M['hist_label']} PCT", ""), ("₹ CR", "")]
    return (f'<h2>1-day delivery vs 20-day average <span class="sub">TOP {n}</span></h2>'
            f'<p class="desc">Selected universe, {len(allowed or M["syms"])} names; shares, NSE + BSE. Deliv % = share of traded quantity that went home. {M["hist_label"]} pct = today\'s deliverable quantity against the stock\'s own history in this file ({M["N"]} sessions so far). '
            f'The 20-day average is the mean of the previous 20 sessions\' delivered shares. Futures OI is shares summed over all expiries. ₹ cr = delivered value.</p>' + table(head, rows))


def tab_persist(M, n=40, allowed=None):
    all_df = M["persist"]
    if allowed is not None: all_df = all_df[all_df.sym.isin(allowed)]
    df = all_df.head(n).reset_index(drop=True); mx = df["ratio"].max() if len(df) else 1; rows = []
    for i, r in df.iterrows():
        rows.append(f'<tr><td class="mut">{i + 1}</td><td class="l">{stk(r.sym, M)}</td><td>{int(r.d125)} <span class="mut">/</span> {int(r.d150)}</td><td class="l">{bar(r.ratio, mx)}<span class="bv">{r.ratio:.2f}×</span></td>'
                    f'<td>{fs(r.dq5)}</td><td>{r.delivpct:.1f}</td><td{heat(r.px5, 10)}>{pc(r.px5)}</td><td{heat(r.px5_z, 3)}>{zscore(r.px5_z)}</td><td>{fs(r.oi)}</td><td{heat(r.doi_pct, 25)}>{fl(r.doi5)}</td><td{heat(r.doi_pct, 25)}>{pc(r.doi_pct)}</td>'
                    f'<td>{mult(r.d_over_doi)}</td><td>{pct_badge(r.pct)}</td></tr>')
    head = [("#", "mut"), ("STOCK", "l"), ("DAYS ≥1.25× / 1.5×", ""), ("5-DAY AVG ÷ 20D", "l"), ("5D DELIVERED", ""), ("DELIV %", ""), ("PX 5D", ""), ("PX 5D Z", ""), ("SSF OI", ""), ("ΔOI 5D", ""), ("ΔOI %", ""), ("DELIV ÷ ΔOI", ""), (f"{M['hist_label']} PCT", "")]
    q = len(all_df); q15 = int((all_df["d150"] >= 3).sum())
    return (f'<h2>Persistent delivery <span class="sub">≥3 OF THE LAST 5 SESSIONS ABOVE 1.25× 20D</span></h2>'
            f'<p class="desc">{q} qualify ({q15} at 1.5×); sorted by 5-day average ÷ 20d (the 5-day mean of delivered shares over the mean of the 20 sessions before them). Price and OI change from {M["persist_from"]:%d %b}. '
            f'PX 5D Z compares the five-session price move with the stock\'s own prior 60-session distribution of five-session moves. {M["hist_label"]} pct ranks the 5-day average against the stock\'s own rolling 5-day averages.</p>' + table(head, rows))


def tab_signal_confluence(M, allowed=None):
    allowed = set(allowed or M["syms"])

    def block(frame, title, subtitle):
        frame = frame[frame.sym.isin(allowed)].head(35).reset_index(drop=True)
        rows = []
        for i, r in frame.iterrows():
            ma = "–" if pd.isna(r.ma) else f'{int(r.ma)}D · {pc(r.ma_dist)}' + (' · crossed' if r.ma_cross else '')
            rs = "–" if not r.rs_horizons else f'{esc(r.rs_horizons)} · best {pc(r.rs_best)}'
            rows.append(f'<tr><td class="mut">{i+1}</td><td class="l">{stk(r.sym, M)}</td>'
                        f'<td>{int(r.d125)}/5</td><td>{r.ratio:.2f}×</td><td>{pc(r.px5)}</td><td>{zscore(r.px5_z)}</td>'
                        f'<td class="l">{rs}</td><td class="l">{ma}</td></tr>')
        head = [("#", "mut"), ("STOCK", "l"), ("DELIVERY DAYS", ""), ("5D ÷ 20D", ""), ("PX 5D", ""), ("PX Z", ""), ("RELATIVE STRENGTH", "l"), ("NEAREST MA", "l")]
        content = table(head, rows, "signals") if rows else '<div class="card rempty">No stocks currently qualify for this tier.</div>'
        return f'<h3 class="signalsub">{esc(title)}</h3><p class="desc">{esc(subtitle)}</p>{content}'

    return ('<h2>Signal Confluence</h2><div class="subl">PERSISTENT DELIVERY · RELATIVE STRENGTH · MOVING-AVERAGE PROXIMITY</div>'
            '<p class="desc">Persistent delivery requires at least three of the last five sessions at 1.25× or more of the prior 20-day average. Relative strength means a top-30 rank versus Nifty on at least one tracked horizon. MA proximity means within 0.5σ of an active moving average. The tiers are mutually exclusive.</p>'
            + block(M["signal_all_three"], "1 · DELIVERY + RELATIVE STRENGTH + MA", "Strongest confluence: all three conditions are present.")
            + block(M["signal_delivery_rs"], "2 · DELIVERY + RELATIVE STRENGTH", "Persistent accumulation with market outperformance, but not currently close to a moving average.")
            + block(M["signal_delivery_ma"], "3 · DELIVERY + MA", "Persistent delivery near a moving average without a current top-30 relative-strength rank; monitoring tier."))


def tab_52w_highs(M):
    def points(values, lo=None, hi=None, width=420, height=132, left=8, right=8, top=8, bottom=8):
        values = pd.Series(values).astype(float)
        valid = values.dropna()
        if valid.empty: return ""
        if lo is None or hi is None:
            lo, hi = valid.min(), valid.max(); pad = (hi - lo) * .07 or max(abs(hi) * .02, 1)
            lo, hi = lo - pad, hi + pad
        xs = np.linspace(left, width - right, len(values))
        out, pen = [], False
        for x, value in zip(xs, values):
            if pd.isna(value): pen = False; continue
            y = top + (1 - (value - lo) / (hi - lo)) * (height - top - bottom)
            out.append(("L" if pen else "M") + f"{x:.1f},{y:.1f}"); pen = True
        return " ".join(out)

    def card(row):
        s = row.sym; start = max(0, M["T"] - 251); close = M["C"][s].iloc[start:M["T"] + 1]
        dq = M["DQ"][s].iloc[start:M["T"] + 1]; ratio = M["RAT"][s].iloc[start:M["T"] + 1]
        mas = [(n, close.rolling(n, min_periods=n).mean()) for n in (50, 100, 200)]
        plotted = pd.concat([close] + [series for _, series in mas]); lo, hi = plotted.min(), plotted.max()
        pad = (hi - lo) * .07 or max(abs(hi) * .02, 1); lo, hi = lo - pad, hi + pad
        price_paths = ''.join(f'<path class="h52ma ma{n}" d="{points(series, lo, hi)}"/>' for n, series in mas)
        width, y0, bar_h = 420, 150, 52
        max_dq = dq.max(skipna=True) or 1; bw = max(.7, width / max(1, len(dq)) * .72)
        bars = []
        for i, (value, hot) in enumerate(zip(dq, ratio >= 1.25)):
            if pd.isna(value): continue
            h = value / max_dq * bar_h; x = i * width / max(1, len(dq) - 1) - bw / 2
            bars.append(f'<rect class="h52bar{(" hot" if bool(hot) else "")}" x="{x:.1f}" y="{y0 + bar_h - h:.1f}" width="{bw:.1f}" height="{max(.7,h):.1f}"/>')
        result = stk(s, M); cap = M.get("market_cap_cr", {}).get(s)
        bucket = "unknown" if cap is None else "under10" if cap < 10000 else "10to30" if cap <= 30000 else "over30"
        cap_text = "Market cap unavailable" if cap is None else f'₹{cap:,.0f} cr market cap'
        return (f'<article class="h52card" data-mcap="{bucket}"><div class="h52head"><h3>{result}</h3><b class="{("g" if row.px1d >= 0 else "r")}">{pc(row.px1d)} on the day</b></div>'
                f'<svg class="h52svg" viewBox="0 0 420 210" role="img" aria-label="One-year price and delivered-share chart for {esc(s)}">'
                f'<path class="h52price" d="{points(close, lo, hi)}"/>{price_paths}<line x1="0" x2="420" y1="202" y2="202"/> {"".join(bars)}</svg>'
                f'<div class="h52meta"><span>HIGH <b>{row.day_high:,.2f}</b></span><span>CLOSE <b>{row.close:,.2f}</b></span><span>FROM HIGH <b>{pc(row.close_from_high)}</b></span><span>DELIVERY <b>{row.ratio:.2f}×</b></span></div>'
                f'<div class="h52legend"><i></i> PRICE <i class="m50"></i> 50D <i class="m100"></i> 100D <i class="m200"></i> 200D · {cap_text}</div></article>')

    def group(is_fo):
        frame = M["high52"]
        frame = frame[frame.fo == is_fo].sort_values(["ratio", "px1d"], ascending=False)
        if frame.empty: return '<div class="card rempty">No stocks in this group reached a fresh 52-week intraday high today.</div>'
        return '<div class="h52grid">' + ''.join(card(r) for r in frame.itertuples()) + '</div>'

    return ('<h2>Fresh 52-Week Highs</h2><div class="subl">TODAY’S INTRADAY HIGH REACHED OR EXCEEDED THE PRIOR 252-SESSION HIGH</div>'
            '<p class="desc">Three compact one-year charts per row. Delivery bars are highlighted when they are at least 1.25× the prior 20-session average. Click a ticker to open its full Stocks chart.</p>'
            '<div class="h52tabs"><button class="h52tab on" data-h52="fo">F&amp;O</button><button class="h52tab" data-h52="nonfo">NON F&amp;O</button></div>'
            f'<div class="h52group" data-h52-group="fo">{group(True)}</div><div class="h52group" data-h52-group="nonfo" hidden>'
            '<div class="h52caps"><button class="h52cap on" data-mcap-filter="all">ALL</button><button class="h52cap" data-mcap-filter="under10">&lt; ₹10,000 CR</button>'
            '<button class="h52cap" data-mcap-filter="10to30">₹10,000–30,000 CR</button><button class="h52cap" data-mcap-filter="over30">&gt; ₹30,000 CR</button></div>'
            f'{group(False)}</div>')


def tab_cash_accumulation(M):
    def block(df, empty_text):
        rows = []
        for i, r in df.iterrows():
            state = f'<span class="setupstate active">ACTIVE</span>' if r.cooldown == 0 else f'<span class="setupstate cool">COOLDOWN {int(r.cooldown)}/2</span>'
            fresh = '<span class="newcash">NEW TODAY</span>' if r.new else ''
            rows.append(f'<tr class="{"cashnew" if r.new else ""}"><td class="mut">{i + 1}</td><td class="l">{stk(r.sym, M)} {fresh}</td><td>{state}</td><td><b>{int(r.days)}D</b></td>'
                        f'<td>{r.signal_date:%d %b}</td><td{heat(r.ratio - 1, 1.5)}>{r.ratio:.2f}×</td><td{heat(r.px1d, 5)}>{pc(r.px1d)}</td>'
                        f'<td>{fs(r.oi)}</td><td{heat(r.doi_pct, 8)}>{fl(r.doi)}</td><td{heat(r.doi_pct, 8)}>{pc(r.doi_pct)}</td><td>{r.close:,.2f}</td>'
                        f'<td{heat(r.ma50, 15)}>{pc(r.ma50)}</td><td{heat(r.ma100, 15)}>{pc(r.ma100)}</td><td{heat(r.ma200, 15)}>{pc(r.ma200)}</td></tr>')
        head = [("#", "mut"), ("STOCK", "l"), ("STATUS", ""), ("SETUP DAYS", ""), ("LAST SIGNAL", ""),
                ("DELIVERY ÷ 20D", ""), ("PX 1D", ""), ("SSF OI", ""), ("ΔOI", ""), ("ΔOI %", ""), ("CLOSE", ""),
                ("50MA DIST", ""), ("100MA DIST", ""), ("200MA DIST", "")]
        return table(head, rows, "cashwatch") if rows else f'<div class="card rempty">{empty_text}</div>'
    confirmed = block(M["cash_accumulation"], "No F&amp;O stocks currently meet the confirmed setup or its two-session cooldown.")
    tracking = block(M["cash_tracking"], "No below-MA F&amp;O tracking candidates currently qualify or remain in cooldown.")
    return ('<h2>Cash Accumulation Watch</h2><div class="subl">F&amp;O · PRICE STRENGTH + DELIVERY + FALLING OI</div>'
            f'<p class="desc">A qualifying day closes higher and above the {" / ".join(str(n) for n in M["cash_mas"])}-day averages, with delivered shares above the prior 20-session average and total SSF OI falling. '
            f'Both lists require at least {metrics.CASH_MIN_DAYS} setup days. Setup Days counts qualifying sessions in the current episode; a pause remains visible for two trading sessions and resumes the same episode if the signal returns.</p>'
            '<h3 class="cashsub">CONFIRMED · ABOVE ALL ACTIVE AVERAGES</h3>' + confirmed +
            '<h3 class="cashsub track">TRACKING LIST · SAME SIGNAL, BELOW AT LEAST ONE AVERAGE</h3>'
            '<p class="desc">These names have positive price, above-average delivery and declining SSF OI, but still sit below one or more required averages. The final three columns show each name\'s distance from its 50-, 100- and 200-day moving averages at the last signal.</p>' + tracking)


def tab_rel(M, allowed=None):
    active = M["active_ma"]; blocks = []; allowed = set(allowed or M["syms"])
    cnt_top = pd.Series(0, index=M["syms"]); cnt_bot = pd.Series(0, index=M["syms"]); lists = {}
    for name, _ in metrics.HORIZONS:
        now = M["relT"][name].loc[list(allowed)].dropna(); prev = M["relPrev"][name].loc[list(allowed)].dropna()
        top, bot = now.nlargest(metrics.LIST_N), now.nsmallest(metrics.LIST_N)
        lists[name] = dict(top=top, bot=bot, new_top=set(top.index) - set(prev.nlargest(metrics.LIST_N).index), new_bot=set(bot.index) - set(prev.nsmallest(metrics.LIST_N).index))
        cnt_top.loc[top.index] += 1; cnt_bot.loc[bot.index] += 1
    for k, (name, h) in enumerate(metrics.HORIZONS):
        L = lists[name]; parts = []
        for side, title, col in (("top", "Outperformers", "g"), ("bot", "Underperformers", "r")):
            ser = L[side]; newset = L["new_" + side]; cnt = cnt_top if side == "top" else cnt_bot; rows = []
            for s, v in ser.items():
                cells = "".join(f'<td{heat(M["dist"][n][s].iloc[M["T"]], 25)}>{pc(M["dist"][n][s].iloc[M["T"]], 0)}</td>' if pd.notna(M["dist"][n][s].iloc[M["T"]]) else '<td class="mut">–</td>' for n in active)
                strong = ' class="strong ' + col + '"' if cnt[s] >= 3 else ""
                rows.append(f'<tr class="{"newrow" if s in newset else ""}"><td class="l tk {col}"><span{strong}>{stk(s, M)}</span></td><td class="{col}">{pc(v)}</td>{cells}</tr>')
            head = [("TICKER", "l"), ("REL %", "")] + [(str(n), "") for n in active]
            parts.append(f'<div class="card"><div class="ch"><span class="ct {col}">{title}</span><span class="mut">{name}</span></div>{table(head, rows, "rel")}</div>')
        blocks.append(f'<div class="hz" data-h="{k}"{"" if k == 0 else " hidden"}>{"".join(parts)}</div>')
    btns = "".join(f'<button class="seg{" on" if k == 0 else ""}" data-h="{k}">{name}</button>' for k, (name, _) in enumerate(metrics.HORIZONS))
    return (f'<h2>Relative performance</h2><div class="subl">TOP AND BOTTOM {metrics.LIST_N} OF {len(allowed)} VS NIFTY</div><div class="segs">{btns}</div>{"".join(blocks)}'
            f'<p class="desc">Rel % = return relative to the Nifty over the horizon ((1 + stock) ÷ (1 + Nifty) − 1); the numbered columns = % distance from that moving average (green above, red below, full depth at 25%). '
            f'A red bar = new on that list since the previous session; green / red bold ticker = on three or more of the five horizons.</p>')


def tab_results(M, allowed=None):
    rows = []
    events = M.get("results", [])
    allowed = set(allowed or M["syms"])
    for r in events:
        if r["symbol"] not in allowed: continue
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


def tab_at(M, allowed=None):
    out = []
    allowed = set(allowed or M["syms"])
    for n in M["active_ma"]:
        items = [x for x in M["at"][n] if x["sym"] in allowed]
        chips = "".join(f'<span class="chip {"u" if x["above"] else "d"}{" cr" if x["crossed"] else ""}{" nw" if x["new"] else ""}" title="{x["dist"]:+.2f}% from the {n}-day average = {x["k"]:.2f} σ (σ = {x["sigma"]:.2f}% daily)">'
                        f'{"▲" if x["above"] else "▼"} <a class="stk" data-s="{esc(x["sym"])}">{esc(x["sym"])}</a></span>' for x in items) or '<span class="mut">none</span>'
        out.append(f'<div class="atrow"><div class="atn"><div class="big">{n}</div><div class="mut">{len(items)} NAMES</div></div><div class="chips">{chips}</div></div>')
    for n, need in M["inactive_ma"]:
        out.append(f'<div class="atrow off"><div class="atn"><div class="big">{n}</div><div class="mut">OFF</div></div><div class="chips mut">Needs {n + 1} sessions of history; have {M["N"]}. Switches on in {need} sessions.</div></div>')
    return (f'<h2>Stocks at a moving average</h2><div class="subl">WITHIN 0.5σ, CLOSEST FIRST</div>'
            f'<p class="desc">▲ above · ▼ below · boxed = crossed today · underlined = new on the list. “Within 0.5σ” means the close is within half of the stock\'s own daily standard deviation ({metrics.SIGMA_WINDOW}-session) of the average, so a stock that moves 2% a day counts as at its average when it is within 1% of it. Hover a name for its exact distance.</p>'
            f'<div class="card">{"".join(out)}</div>')


def _line_points(values, width, height, left=44, top=18, right=18, bottom=30):
    vals = pd.Series(values, dtype=float); good = vals.dropna()
    if good.empty: return "", np.nan, np.nan
    lo, hi = float(good.min()), float(good.max())
    if hi == lo: hi = lo + 1
    xs = np.linspace(left, width - right, len(vals))
    ys = top + (hi - vals) / (hi - lo) * (height - top - bottom)
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys) if pd.notna(y))
    return points, lo, hi


def tab_turnover_tracker(X, title, subtitle, heading=True):
    heading_html = f'<h2>{esc(title)}</h2>' if heading else ''
    if not X.get("available"):
        return (f'{heading_html}<div class="subl">{esc(subtitle)}</div>'
                f'<div class="card rempty">{esc(X.get("commentary", ["Turnover data is not available yet."])[0])}</div>')
    price_label = X.get("price_label", "share price")
    source_label = X.get("source_label", "SOURCE")
    series = X["series"].dropna(subset=["roll5"]).reset_index(drop=True)
    end = pd.Timestamp(X["asof"])
    ranges = [("ytd", "YTD", end.replace(month=1, day=1)), ("6m", "6M", end - pd.DateOffset(months=6)),
              ("3m", "3M", end - pd.DateOffset(months=3)), ("1y", "1YR", end - pd.DateOffset(years=1)),
              ("2y", "2YR", end - pd.DateOffset(years=2))]

    def hero(start, key):
        # Match the bar-chart aspect ratio so all three panels remain balanced.
        # The SVG viewBox is redrawn at this size, so no chart is stretched.
        s = series[series.date >= start].reset_index(drop=True); W, H = 900, 402
        tp, tlo, thi = _line_points(s["roll5"], W, H, bottom=40)
        pp, plo, phi = _line_points(s["price"], W, H, bottom=40)
        x0, xb, base = 44, W - 18, H - 40
        area = f'{x0},{base} {tp} {xb},{base}'
        ticks = "".join(f'<text x="{44 + (W - 62) * i / 4:.0f}" y="{H-12}" text-anchor="middle">{s.date.iloc[round((len(s)-1)*i/4)]:%b %y}</text>' for i in range(5))
        grid = []
        for i in range(5):
            y = 18 + (base - 18) * i / 4
            turnover = thi - (thi - tlo) * i / 4
            price = np.nan if pd.isna(phi) else phi - (phi - plo) * i / 4
            grid.append(f'<line class="exgridline" x1="{x0}" x2="{xb}" y1="{y:.1f}" y2="{y:.1f}"/>'
                        f'<text class="exaxis" x="{x0-6}" y="{y+3:.1f}" text-anchor="end">₹{turnover:,.0f}cr</text>'
                        + ("" if pd.isna(price) else f'<text class="exaxis price" x="{W-8}" y="{y+3:.1f}" text-anchor="end">₹{price:,.0f}</text>'))
        note = "" if s.price.notna().all() else f'<text x="50" y="44">{esc(price_label)} begins with available desk history</text>'
        return (f'<div class="exrange" data-xr="{key}"{("" if key == "ytd" else " hidden")}><svg class="exsvg hero" viewBox="0 0 {W} {H}" role="img" aria-label="Premium turnover and {esc(price_label)}">'
                '<defs><linearGradient id="turnoverFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5aa9ff" stop-opacity=".34"/><stop offset="1" stop-color="#5aa9ff" stop-opacity=".025"/></linearGradient></defs>'
                f'{"".join(grid)}<polygon points="{area}" class="exarea"/><polyline points="{tp}" class="exto"/><polyline points="{pp}" class="expx"/>'
                f'{note}{ticks}</svg></div>')

    def bars(df, label, value, colour, current=False, month_axis=False, comparison=None):
        w, h, l, top, bot = 560, 250, 40, 18, 52
        vals = pd.to_numeric(df[value], errors="coerce"); mx = max(float(vals.max()), 1)
        bw = (w - l - 12) / max(len(df), 1); out = []
        for j in range(5):
            val = mx * j / 4; y = h - bot - (h - top - bot) * j / 4
            out.append(f'<line class="exbargrid" x1="{l}" x2="{w-8}" y1="{y:.1f}" y2="{y:.1f}"/>'
                       f'<text x="{l-5}" y="{y+3:.1f}" text-anchor="end">{val:,.0f}</text>')
        for i, (_, r) in enumerate(df.iterrows()):
            bh = float(r[value]) / mx * (h - top - bot); x = l + i * bw + 2; y = h - bot - bh
            cls = colour + (" latest" if current and i == len(df)-1 else "")
            barw = max(2.5, bw * (.48 if month_axis else .62)); bx = x + (bw - barw) / 2
            tip = f'{r[label]} · ₹{r[value]:,.0f} cr'
            if month_axis and "count" in r:
                tip += f' average · {int(r["count"])} sessions'
            hover_y = max(top + 11, y - 6)
            out.append(f'<g class="exbaritem"><rect class="{cls}" x="{bx:.1f}" y="{y:.1f}" width="{barw:.1f}" height="{bh:.1f}" tabindex="0" aria-label="{esc(tip)}"><title>{esc(tip)}</title></rect>'
                       + (f'<text class="exbarhover" x="{bx + barw / 2:.1f}" y="{hover_y:.1f}" text-anchor="middle">₹{r[value]:,.0f}cr</text>' if month_axis else '')
                       + '</g>')
            if not month_axis: out.append(f'<text x="{x+bw/2:.1f}" y="{h-24}" text-anchor="end" transform="rotate(-45 {x+bw/2:.1f} {h-24})">{r[label]}</text>')
        if month_axis:
            months = pd.to_datetime(df["date"]).dt.to_period("M")
            for month in months.drop_duplicates():
                idx = np.flatnonzero((months == month).to_numpy()); mid = l + (idx[0] + idx[-1] + 1) * bw / 2
                out.append(f'<text class="monthtag" x="{mid:.1f}" y="{h-23}" text-anchor="middle">{month.strftime("%b")}</text>')
        annotation_text = X.get("comparison_annotation", "VS YTD AVG")
        annotation = "" if comparison is None or pd.isna(comparison) else f'<text class="excompare {"up" if comparison >= 0 else "down"}" x="{w-12}" y="{top+10}" text-anchor="end">LATEST {comparison:+.0f}% {esc(annotation_text)}</text>'
        return f'<svg class="exsvg" viewBox="0 0 {w} {h}" role="img"><line x1="{l}" y1="{h-bot}" x2="{w-8}" y2="{h-bot}"/>' + "".join(out) + annotation + '</svg>'

    comparison = X.get("comparison", X.get("same_weekday", pd.DataFrame())).copy()
    comparison["date"] = pd.to_datetime(comparison["date"])
    comparison["label"] = comparison.date.dt.strftime("%b %y" if not X.get("comparison_month_axis", True) else "%d %b %y")
    comparison_prior_avg = comparison.iloc[:-1]["premium_turnover_cr"].mean() if len(comparison) > 1 else np.nan
    comparison_change = ((comparison.iloc[-1]["premium_turnover_cr"] / comparison_prior_avg - 1) * 100
                         if len(comparison) and pd.notna(comparison_prior_avg) and comparison_prior_avg else np.nan)
    monthly = X["monthly"].copy(); monthly["label"] = pd.to_datetime(monthly.month + "-01").dt.strftime("%b %y")
    comments = "".join(f'<li>{esc(x)}</li>' for x in X["commentary"])
    range_buttons = "".join(f'<button class="exrbtn{(" on" if key == "ytd" else "")}" data-xr="{key}">{label}</button>' for key, label, _ in ranges)
    hero_ranges = "".join(hero(start, key) for key, _, start in ranges)
    status = X.get("update_status", "")
    status_html = f'<div class="exstatus">{esc(status)}</div>' if status else ''
    return (f'{heading_html}<div class="subl">{esc(subtitle)}</div>'
            f'<div class="exheadline"><div><span>LATEST</span><b>₹{X["latest"]:,.0f} cr</b></div><div><span>AS OF</span><b>{X["asof"]:%d %b %Y}</b></div><div><span>DAY</span><b>{esc(X["weekday"])}</b></div></div>'
            f'{status_html}<div class="card excomment"><h3>DAILY READ</h3><ul>{comments}</ul><a href="{esc(X["source"])}" target="_blank" rel="noopener">{esc(source_label)} ↗</a></div>'
            f'<div class="exlayout"><div class="card excard exmain"><div class="ch"><span class="ct">5D ROLLING PREMIUM TURNOVER</span><span><i class="exkey to"></i>5D premium <i class="exkey px"></i>{esc(price_label)}</span></div>{hero_ranges}</div>'
            f'<div class="card excard"><div class="ch"><span class="ct">{esc(X.get("comparison_title", X["weekday"].upper() + "S · YTD"))}</span><span class="mut">{len(comparison)} {esc(X.get("comparison_count_label", "SESSIONS"))}</span></div>{bars(comparison,"label","premium_turnover_cr","exbar",True,X.get("comparison_month_axis", True),comparison_change)}</div>'
            f'<div class="card excard"><div class="ch"><span class="ct">AVERAGE DAILY PREMIUM TURNOVER</span><span class="mut">CURRENT MONTH IS PARTIAL</span></div>{bars(monthly,"label","mean","exbar month",True)}</div>'
            f'<div class="exranges exrangesbelow">{range_buttons}</div></div>'
            '<p class="desc">Premium turnover is the exchange-reported daily options premium value. The current month updates incrementally; if a new session is unavailable, the last verified observation remains visible with its exact date and refresh status.</p>')


def tab_exchange(M):
    bse = tab_turnover_tracker(M.get("exchange_tracker", {}), "BSE", "BSE OPTIONS PREMIUM TURNOVER · ₹ CRORE", heading=False)
    mcx = tab_turnover_tracker(M.get("mcx_tracker", {}), "MCX", "MCX OPTFUT PREMIUM TURNOVER · ₹ CRORE", heading=False)
    return ('<h2>Exchange Tracker</h2><div class="subl">OPTIONS PREMIUM TURNOVER</div>'
            '<div class="exswitch"><button class="exswitchbtn on" data-exchange="bse">BSE</button><button class="exswitchbtn" data-exchange="mcx">MCX</button></div>'
            f'<div class="exchangegroup" data-exchange-group="bse">{bse}</div><div class="exchangegroup" data-exchange-group="mcx" hidden>{mcx}</div>')


def tab_mcx(M):
    return tab_turnover_tracker(M.get("mcx_tracker", {}), "MCX Exchange Tracker", "MCX OPTFUT PREMIUM TURNOVER · ₹ CRORE")


def guidance_library(analysis, source_url):
    rows = []
    for change in validated_changes(analysis, source_url):
        e = change["evidence"]
        pair = (f'{esc(change["old_guidance"])} → {esc(change["new_guidance"])}'
                if change["old_guidance"] and change["new_guidance"] else esc(change["magnitude"]))
        rows.append(f'<details class="guidancechange {esc(change["direction"])}"><summary>{esc(change["direction"].upper())} · {esc(change["topic"])} · {pair}</summary>'
                    f'<p>{esc(change["explicit_statement"])}</p><blockquote>{esc(e["quote"])}</blockquote>'
                    f'<p>{esc(e["speaker"])} · {esc(e["role"])} · {esc(e["location"])} · {esc(e["call_period"])}</p>'
                    f'<a href="{esc(e["source_url"])}" target="_blank" rel="noopener">Exchange transcript · {esc(e["filing_date"])} ↗</a></details>')
    return '<section><h4>MATERIAL GUIDANCE CHANGES</h4>' + ''.join(rows) + '</section>' if rows else ''


def _tab_call_library_legacy(M):
    calls = M.get("calls", {})
    labels = {"revenue_growth": "Revenue growth", "volume_growth": "Volume growth", "order_inflow": "Order inflow",
              "demand_outlook": "Demand outlook", "margin_outlook": "Margin outlook", "ebitda_margin": "EBITDA margin",
              "credit_growth": "Credit growth", "credit_deposit_ratio": "Credit–deposit ratio", "disbursements": "Disbursements",
              "nim_outlook": "NIM outlook", "asset_quality": "Asset quality", "credit_cost_outlook": "Credit-cost outlook"}
    available = [(s, c) for s, c in calls.items() if c.get("analysis")]
    missing = [(s, c) for s, c in calls.items() if c.get("transcript_status") == "missing"]
    available.sort(key=lambda x: x[1].get("filed_at", ""), reverse=True)
    missing.sort(key=lambda x: x[1].get("filed_at", ""), reverse=True)
    cards = []
    for symbol, call in available:
        analysis = call["analysis"]
        expanded_focus = analysis.get("analyst_focus_scope") in {"all_material_themes", "top_themes_by_question_count"}
        outlook = analysis.get("next_quarter_outlook", []) if expanded_focus else analysis.get("next_quarter_outlook", [])[:6]
        focus = analysis.get("analyst_focus", []) if expanded_focus else analysis.get("analyst_focus", [])[:3]
        cg = analysis.get("congratulations", {}); filed = pd.to_datetime(call.get("filed_at"), errors="coerce")
        forward_only = str(analysis.get("analysis_profile", "")).startswith("forward_")
        forward_actuals = analysis.get("analysis_profile") == "forward_plus_actuals_v1"
        filed_text = "–" if pd.isna(filed) else f"{filed:%d %b %Y}"
        sector = analysis.get("manufacturer") if analysis.get("company_type") == "manufacturer" else analysis.get("bank_lender") if analysis.get("company_type") == "bank_lender" else None
        takeaways = []
        if sector:
            priority = (["revenue_growth", "order_inflow", "demand_outlook", "margin_outlook", "ebitda_margin", "volume_growth"]
                        if analysis.get("company_type") == "manufacturer" else
                        ["credit_growth", "nim_outlook", "asset_quality", "credit_cost_outlook", "disbursements", "credit_deposit_ratio"])
            takeaways.extend((labels.get(k, k.replace("_", " ").title()), sector.get(k)) for k in priority if sector.get(k))
        else:
            takeaways.extend((x["metric"], x["value"]) for x in analysis.get("key_actuals", []))
        risks = analysis.get("key_risks", [])
        takeaway_rows = takeaways[:3] + ([('Risk / watchpoint', risks[0])] if risks else [])
        outlook_html = "".join(f'<li><b>{esc(x.get("topic", ""))}</b>{esc(x.get("summary", ""))}</li>' for x in outlook) or '<li class="mut">No explicit outlook stored.</li>'
        focus_html = "".join(f'<li><b>{esc(x.get("topic", ""))}</b>{esc(x.get("why_it_mattered", ""))}<span>{str(x["question_count"]) + "Q" if x.get("question_count") is not None else "not disclosed"}</span></li>' for x in focus) or '<li class="mut">No analyst themes stored.</li>'
        takeaway_html = "".join(f'<li><b>{esc(k)}</b>{esc(str(v))}</li>' for k, v in takeaway_rows) or '<li class="mut">No additional takeaways stored.</li>'
        score_html = ('' if forward_only else
                      f'<div class="callscore"><strong>{"not disclosed" if cg.get("index_pct") is None else format(float(cg["index_pct"]), ".0f") + "%"}</strong><span>CONGRATULATIONS<br>{cg.get("count") if cg.get("count") is not None else "not disclosed"}/{cg.get("analyst_turns") if cg.get("analyst_turns") is not None else "not disclosed"} TURNS</span></div>')
        final_section = (f'<section class="takeaways"><h4>{"QUICK ACTUALS &amp; FORWARD WATCHPOINTS" if forward_actuals else "FORWARD RISKS &amp; WATCHPOINTS"}</h4><ul>{takeaway_html if forward_actuals else ""}{"".join(f"<li>{esc(x)}</li>" for x in risks) or "<li class=\"mut\">No forward risk disclosed.</li>"}</ul></section>'
                         if forward_only else f'<section class="takeaways"><h4>IMPORTANT TAKEAWAYS</h4><ul>{takeaway_html}</ul></section>')
        cards.append(f'<article class="callcard"><div class="callcardhead"><div><h3>{stk(symbol, M)}</h3><div>{esc(analysis.get("call_period", "Latest call"))} · transcript {filed_text}</div></div>'
                     f'{score_html}</div>'
                     f'<div class="callcols"><section><h4>NEXT QUARTER OUTLOOK</h4><ol>{outlook_html}</ol></section><section><h4>TOP ANALYST CONCERNS</h4><ol class="concerns">{focus_html}</ol></section></div>'
                     f'{final_section}{guidance_library(analysis, call.get("source_url"))}<a class="callsource" href="{esc(call.get("source_url", "#"))}" target="_blank" rel="noopener">OPEN SOURCE ↗</a></article>')
    for symbol, call in missing:
        filed = pd.to_datetime(call.get("filed_at"), errors="coerce")
        filed_text = "–" if pd.isna(filed) else f"{filed:%d %b %Y}"
        cards.append(f'<article class="callcard"><div class="callcardhead"><div><h3>{stk(symbol, M)}</h3><div>exchange filing {filed_text}</div></div></div>'
                     f'<div class="callnone"><b>TRANSCRIPT MISSING</b><br>{esc(call.get("status_detail", "The exchange attachment did not contain an extractable transcript."))}</div>'
                     f'<a class="callsource" href="{esc(call.get("source_url", "#"))}" target="_blank" rel="noopener">OPEN EXCHANGE FILING ↗</a></article>')
    ranked = sorted(available + missing, key=lambda x: x[1].get("filed_at", ""), reverse=True)
    latest = ranked[0][1] if ranked else None
    latest_label = "–" if latest is None else f'{esc(latest.get("symbol", ""))} · {esc(latest.get("analysis", {}).get("call_period", ""))}'
    return (f'<h2>Conference Call Library</h2><div class="subl">{len(available)} STATIC TRANSCRIPT SUMMARIES · {len(missing)} MISSING TRANSCRIPT</div>'
            f'<div class="calllibmeta"><span>LATEST COVERED CALL</span><b>{latest_label}</b></div>'
            '<p class="desc">A compact index of the transcript research already stored in Rachit’s Market Lens. Outlook, analyst concerns and takeaways below are pulled directly from the existing summaries; no additional analysis is performed on this page.</p>'
            f'<div class="calllibrary">{"".join(cards)}</div>' if cards else '<div class="card rempty">No conference-call summaries are available yet.</div>')


def _compact_text(value, words=16):
    text = " ".join(str(value or "").split())
    clauses = [x.strip() for x in re.split(r"(?<=[.;])\s+", text) if x.strip()]
    chosen = next((x for x in clauses if re.search(r"\d|%|bps|crore|guidance|target", x, re.I)), clauses[0] if clauses else "")
    parts = chosen.split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


def _call_chart(M, symbol):
    prices = M.get("C")
    if prices is None or symbol not in prices:
        return '<div class="callchartempty">Price history unavailable</div>'
    end = M.get("T", len(prices) - 1)
    close = prices[symbol].iloc[max(0, end - 251):end + 1]
    lines = [("price", close)] + [(f"ma{n}", close.rolling(n, min_periods=n).mean()) for n in (50, 100, 200)]
    valid = pd.concat([x for _, x in lines]).dropna()
    if valid.empty: return '<div class="callchartempty">Price history unavailable</div>'
    lo, hi = float(valid.min()), float(valid.max()); pad = (hi - lo) * .06 or max(abs(hi) * .02, 1); lo -= pad; hi += pad
    def path(values):
        xs = np.linspace(6, 394, len(values)); out, pen = [], False
        for x, value in zip(xs, values):
            if pd.isna(value): pen = False; continue
            y = 7 + (1 - (float(value) - lo) / (hi - lo)) * 118
            out.append(("L" if pen else "M") + f"{x:.1f},{y:.1f}"); pen = True
        return " ".join(out)
    paths = "".join(f'<path class="callchartline {name}" d="{path(values)}"/>' for name, values in lines)
    return f'<svg class="callchart" viewBox="0 0 400 136" role="img" aria-label="One-year price and moving averages for {esc(symbol)}">{paths}</svg><div class="callchartlegend"><i></i>PRICE <i class="m50"></i>50D <i class="m100"></i>100D <i class="m200"></i>200D</div>'


def _call_row(M, symbol, call, changes=None):
    analysis = call["analysis"]; filed = pd.to_datetime(call.get("filed_at"), errors="coerce")
    filed_text = "–" if pd.isna(filed) else f"{filed:%d %b %Y}"
    focus = analysis.get("analyst_focus", [])[:3]
    if changes is None:
        middle_title = "NEXT QUARTER OUTLOOK"
        middle = "".join(f'<li><b>{esc(x.get("topic", ""))}</b><span>{esc(_compact_text(x.get("summary")))}</span></li>' for x in analysis.get("next_quarter_outlook", [])[:3])
    else:
        middle_title = "GUIDANCE CHANGE"
        middle = "".join(f'<li class="shift {esc(x["direction"])}"><b>{esc(x["direction"].upper())} · {esc(x["topic"])}</b><span>{esc((str(x["old_guidance"]) + " → " + str(x["new_guidance"])) if x["old_guidance"] else x["magnitude"])}</span></li>' for x in changes[:3])
    middle = middle or '<li class="mut">No explicit statement stored.</li>'
    questions = "".join(f'<li><b>{esc(x.get("topic", ""))}</b><span>{str(x["question_count"]) + " questions" if x.get("question_count") is not None else "Analyst focus"}</span></li>' for x in focus) or '<li class="mut">No analyst themes stored.</li>'
    return (f'<article class="callrow"><div class="callrowhead"><div><h3>{stk(symbol, M)}</h3><span>{esc(analysis.get("call_period", "Latest call"))} · {filed_text}</span></div>'
            f'<a href="{esc(call.get("source_url", "#"))}" target="_blank" rel="noopener">SOURCE ↗</a></div><div class="callrowgrid">'
            f'<section class="callchartbox">{_call_chart(M, symbol)}</section><section><h4>{middle_title}</h4><ul>{middle}</ul></section>'
            f'<section><h4>ANALYST QUESTIONS</h4><ul>{questions}</ul></section></div></article>')


def tab_call_library(M):
    available = sorted(((s, c) for s, c in M.get("calls", {}).items() if c.get("analysis")), key=lambda x: x[1].get("filed_at", ""), reverse=True)
    rows = [_call_row(M, symbol, call) for symbol, call in available]
    latest = available[0] if available else None
    latest_label = "–" if latest is None else f'{esc(latest[0])} · {esc(latest[1]["analysis"].get("call_period", ""))}'
    return (f'<h2>Conference Call Library</h2><div class="subl">{len(available)} CONCISE TRANSCRIPT SUMMARIES</div>'
            f'<div class="calllibmeta"><span>LATEST COVERED CALL</span><b>{latest_label}</b></div>'
            '<p class="desc">One stock per row: one-year price and moving averages, three concise next-quarter points, and the three leading analyst-question themes.</p>'
            f'<div class="calllibrary">{"".join(rows)}</div>' if rows else '<div class="card rempty">No conference-call summaries are available yet.</div>')


def tab_guidance_shifts(M):
    ranked = []
    for symbol, call in M.get("calls", {}).items():
        if not call.get("analysis"): continue
        changes = validated_changes(call["analysis"], call.get("source_url"))
        if changes: ranked.append((symbol, call, changes))
    ranked.sort(key=lambda x: (x[1].get("filed_at", ""), max(c["materiality"] for c in x[2])), reverse=True)
    rows = [_call_row(M, symbol, call, changes) for symbol, call, changes in ranked]
    return ('<h2>Guidance Shifts</h2><div class="subl">EXPLICIT MANAGEMENT UPGRADES &amp; DOWNGRADES</div>'
            '<p class="desc">Only clear, source-verified changes to management guidance are included. General optimism or caution does not qualify.</p>'
            f'<div class="calllibrary">{"".join(rows)}</div>' if rows else '<div class="card rempty">No explicit guidance upgrades or downgrades are stored in the current call library.</div>')


# ------------------------------------------------------------------ assemble
def stocks_json(M):
    dates = [f"{d:%Y-%m-%d}" for d in M["dates"]]; out = {}; T = M["T"]
    ev = M["events"]; di = {d: i for i, d in enumerate(M["dates"])}
    upcoming = {}
    for r in M.get("results", []):
        if r["event_date"].normalize() < M["dates"][-1].normalize(): continue
        old = upcoming.get(r["symbol"])
        if old is None or r["event_date"] < old["event_date"]: upcoming[r["symbol"]] = r
    nz = lambda x, f=float: None if x is None or pd.isna(x) else f(x)
    for s in M["syms"]:
        at = []
        for ma in M["active_ma"]:
            hit = next((x for x in M["at"][ma] if x["sym"] == s), None)
            if hit:
                at.append(dict(ma=ma, above=bool(hit["above"]), crossed=bool(hit["crossed"]),
                               new=bool(hit["new"]), dist=round(float(hit["dist"]), 2),
                               sigma=round(float(hit["sigma"]), 2)))
        rel = [[nz(M["relT"][name][s], lambda v: round(float(v), 2)), nz(M["relrank"][name][s], int)] for name, _ in metrics.HORIZONS]
        sm = dict(px=nz(M["ret1"][s].iloc[T] * 100, lambda v: round(float(v), 2)), ratio=nz(M["RAT"][s].iloc[T], lambda v: round(float(v), 2)),
                  dp=nz(M["dq_raw"][s].iloc[T] / M["tq_raw"][s].iloc[T] * 100, lambda v: round(float(v), 1)), bse=nz(M["bse_share"][s].iloc[T], lambda v: round(float(v), 0)),
                  oi=nz(M["oi"][s].iloc[T], int), doi=nz(M["doi"][s].iloc[T], int), dq=nz(M["DQ"][s].iloc[T], int), rel=rel)
        result = upcoming.get(s)
        call = M.get("calls", {}).get(s)
        if call and call.get("analysis"):
            call = {**call, "analysis": {**call["analysis"], "material_guidance_changes": validated_changes(call["analysis"], call.get("source_url"))}}
        out[s] = dict(c=[nz(x, lambda v: round(float(v), 2)) for x in M["C"][s]], dq=[nz(x, int) for x in M["DQ"][s]],
                      rat=[nz(x, lambda v: round(float(v), 2)) for x in M["RAT"][s]], d=[nz(x, int) for x in M["dcode"][s]], oi=[nz(x, int) for x in M["OIadj"][s]], sm=sm,
                      result=None if result is None else dict(date=f'{result["event_date"]:%Y-%m-%d}', status=result["status"]), at=at, call=call,
                      ev=[[di[e["date"]], round(float(e["factor"]), 4), e["decision"]] for _, e in ev[ev["symbol"] == s].iterrows() if e["date"] in di and e["decision"] in ("auto", "accepted")])
    default = M["screen"]["sym"].iloc[0] if len(M["screen"]) else M["syms"][0]
    return dict(dates=dates, mas=metrics.MA_SET, nifty=[nz(x, lambda v: round(float(v), 2)) for x in M["nifty"]], hz=[[n, h] for n, h in metrics.HORIZONS], default=default, universes=M["memberships"], stocks=out)


def tab_stocks(M):
    return ('<div class="sx"><aside class="sl"><input id="q" placeholder="Search ticker" autocomplete="off" autocapitalize="characters" spellcheck="false">'
            '<select id="sort"><option value="az">Sort: A to Z</option><option value="ratio">Sort: delivery ÷ 20d avg</option><option value="px">Sort: price move today</option><option value="rs">Sort: 20-day relative strength</option></select>'
            '<div id="list"></div></aside><div class="sr"><div id="sh"></div>'
            '<div class="rb"><span class="mut">RANGE</span><button class="seg on" data-r="252">1Y</button><button class="seg" data-r="126">6M</button><button class="seg" data-r="63">3M</button>'
            '<span class="mut malabel">MOVING AVG</span><button class="seg mab" data-ma="32">32</button><button class="seg mab on" data-ma="50">50</button><button class="seg mab" data-ma="100">100</button><button class="seg mab on" data-ma="200">200</button><button class="seg mab" data-ma="233">233</button><button class="seg mab" data-ma="377">377</button><button class="seg mab" data-ma="610">610</button>'
            '<span class="mut" style="margin-left:18px">ABOVE-AVERAGE DELIVERY</span><select id="thr"><option value="1">1.0×</option><option value="1.25" selected>1.25×</option><option value="1.5">1.5×</option><option value="2">2.0×</option></select></div>'
            '<div class="chartgrid"><div class="charts"><div id="guidance-row" hidden></div><div id="chartbox" class="chartcard"><svg id="ch"></svg></div>'
            '<div class="chartcard"><svg id="rsch"></svg></div><div class="chartcard"><svg id="oich"></svg></div>'
            '<div id="ro"></div><div id="lg"></div></div><aside id="insights"></aside></div><section id="callintel"></section></div></div>')


def render(M, asof_text):
    M["hist_label"] = "1Y" if M["N"] < 600 else "3Y"
    data = json.dumps(stocks_json(M), separators=(",", ":"))
    choices = [("top1000", "TOP 1000"), ("nifty500", "NIFTY 500"), ("smallcap250", "NIFTY SMALLCAP 250"),
               ("nifty250", "NIFTY 100 + MIDCAP 150"), ("nifty100", "NIFTY 100"), ("fo", "F&O")]
    choices = [(k, label) for k, label in choices if M["memberships"].get(k)]
    def views(fn):
        return "".join(f'<div class="uview" data-u="{k}"{("" if k == "top1000" else " hidden")}>{fn(M, allowed=M["memberships"][k])}</div>' for k, _ in choices)
    panels = [("stocks", "STOCKS", tab_stocks(M)), ("high52", "52W HIGHS", tab_52w_highs(M)), ("signals", "SIGNAL CONFLUENCE", views(tab_signal_confluence)),
              ("cash", "CASH ACCUMULATION", tab_cash_accumulation(M)),
              ("calls", "CALL LIBRARY", tab_call_library(M)),
              ("guidance", "GUIDANCE SHIFTS", tab_guidance_shifts(M)),
              ("exchange", "EXCHANGE TRACKER", tab_exchange(M))]
    nav = "".join(f'<button class="tab{" on" if i == 0 else ""}" data-t="{k}">{lbl}</button>' for i, (k, lbl, _) in enumerate(panels))
    body = "".join(f'<section class="panel" id="p-{k}"{"" if i == 0 else " hidden"}>{h}</section>' for i, (k, _, h) in enumerate(panels))
    opts = "".join(f'<option value="{k}">{label}</option>' for k, label in choices)
    head = (f'<header><div class="brand">RACHIT’S MARKET LENS</div><div class="headright"><select id="universe" aria-label="Stock universe">{opts}</select><div class="meta">{asof_text}<br><span class="mut">{M["N"]} sessions since {M["dates"][0]:%d %b %Y} · top 1,000 NSE shares · NSE + BSE delivery</span></div></div></header>')
    foot = '<footer>Splits, bonuses and demergers are detected and adjusted automatically (prices, averages and delivered shares are all on today\'s share basis). Delivery % is shown for reference and never used to rank.</footer>'
    return (HTML.replace("%%CSS%%", CSS).replace("%%HEAD%%", head).replace("%%NAV%%", nav).replace("%%BODY%%", body + foot)
            .replace("%%DATA%%", data.replace("</", "<\\/")).replace("%%JS%%", JS).replace("%%TITLE%%", f"Rachit’s Market Lens · {M['dates'][-1]:%d %b %Y}"))


HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>%%TITLE%%</title><style>%%CSS%%</style></head><body>%%HEAD%%<nav class="tabs">%%NAV%%</nav><main>%%BODY%%</main>
<script id="data" type="application/json">%%DATA%%</script><script>%%JS%%</script></body></html>"""

CSS = r"""
:root{--bg:#0a0a0a;--panel:#141414;--line:#262626;--ink:#f2f2ee;--mut:#8b8b86;--g:#3fbf7a;--r:#ef5a4d;--am:#e8a93a;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;--sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;box-sizing:border-box;
padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
*,*::before,*::after{box-sizing:inherit}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:13px;line-height:1.35}
header{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 18px 8px;border-bottom:1px solid var(--line)}
.brand{font-weight:800;letter-spacing:.11em;font-size:16px;white-space:nowrap}.headright{display:flex;align-items:center;gap:12px}.meta{font-family:var(--mono);font-size:10.5px;text-align:right}.mut{color:var(--mut)}
#universe{font:700 11px var(--sans);letter-spacing:.05em;background:#f4f4f0;color:#0a0a0a;border:0;padding:7px 9px;max-width:220px}
.tabs{display:flex;gap:3px;padding:5px 14px;border-bottom:1px solid var(--line);overflow-x:auto;position:sticky;top:env(safe-area-inset-top,0px);background:var(--bg);z-index:5}
.tab{font:600 11px var(--sans);letter-spacing:.08em;color:var(--mut);background:none;border:0;padding:8px 12px;cursor:pointer;white-space:nowrap}
.tab.on{background:#f4f4f0;color:#0a0a0a}.tab:focus-visible,.seg:focus-visible,#mx:focus-visible{outline:2px solid var(--am);outline-offset:2px}
main{max-width:1500px;margin:0 auto;padding:4px 16px 40px}
h2{font-size:23px;line-height:1.1;margin:20px 0 4px;font-weight:800;letter-spacing:-.01em}h2 .sub,.subl{font:600 11px var(--sans);letter-spacing:.1em;color:var(--mut);margin-left:8px}.subl{margin:0 0 8px}
.desc{color:#9a9a94;font-size:13px;line-height:1.45;max-width:1100px;margin:4px 0 11px}.desc b{color:var(--ink)}
.card,.tw{background:var(--panel);border-top:3px solid #f4f4f0}.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}.card .tw{border-top:0}
table{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:12.5px}
th{font:600 10.5px var(--sans);letter-spacing:.08em;color:var(--mut);text-align:right;padding:11px 8px 8px;white-space:nowrap;border-bottom:2px solid #2c2c2c}
td{padding:8px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}th.l,td.l{text-align:left}th.mut,td.mut{color:var(--mut)}
td.l a.stk,td.l span{font-weight:700;letter-spacing:.02em}.stk{cursor:pointer;color:var(--ink);text-decoration:none}.stk:hover{text-decoration:underline}
.warn{color:var(--am);font-size:12px}.bar{display:inline-block;height:12px;background:#f4f4f0;border-radius:3px;vertical-align:middle;margin-right:10px}.bv{display:inline-block;min-width:56px}
.pb{display:inline-block;min-width:44px;padding:6px 8px;border-radius:3px;color:#fff;background:#222;text-align:center}
.rsig{display:inline-block;padding:5px 8px;background:var(--am);color:#0a0a0a;font:700 11px var(--sans);letter-spacing:.06em}.rhit{background:rgba(232,169,58,.2);color:#ffd17a}.src{color:var(--ink)}.rempty{padding:22px;color:var(--mut)}
.resultmark{display:inline-grid!important;place-items:center;min-width:17px;height:17px;padding:0 4px;border-radius:9px;background:var(--am);color:#090909!important;font:800 9px var(--sans)!important;vertical-align:2px;cursor:help}
.setupstate{display:inline-block;padding:4px 7px;font:800 9px var(--sans);letter-spacing:.07em;white-space:nowrap}.setupstate.active{background:var(--g);color:#06160d}.setupstate.cool{border:1px solid var(--am);color:#ffd17a}.cashwatch td b{color:var(--g)}
.cashsub{margin:18px 0 7px;font:800 11px var(--sans);letter-spacing:.1em}.cashsub.track{color:#ffd17a;margin-top:26px}
.cashwatch tr.cashnew td{background:rgba(232,169,58,.08)}.cashwatch tr.cashnew td:first-child{box-shadow:inset 4px 0 var(--am)}.newcash{display:inline-block;margin-left:5px;padding:3px 5px;background:var(--am);color:#090909;font:800 8px var(--sans);letter-spacing:.06em;vertical-align:1px}
.signalsub{margin:22px 0 3px;font:800 12px var(--sans);letter-spacing:.08em}.signals td{padding-top:7px;padding-bottom:7px}.signals td:nth-child(7),.signals td:nth-child(8){font-size:11px}
.h52tabs,.h52caps{display:flex;width:max-content;border:1px solid #444;margin:13px 0 12px}.h52tab,.h52cap{border:0;background:#111;color:var(--mut);padding:8px 17px;font:800 10px var(--sans);letter-spacing:.08em;cursor:pointer}.h52tab.on,.h52cap.on{background:#f4f4f0;color:#090909}.h52grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}.h52card{min-width:0;background:var(--panel);border-top:3px solid var(--g);padding:10px}.h52card[hidden]{display:none}.h52head{display:flex;justify-content:space-between;gap:8px;align-items:center}.h52head h3{margin:0;font-size:16px}.h52head>b{font:700 10px var(--mono);white-space:nowrap}.h52svg{display:block;width:100%;height:auto;margin-top:5px;background:#111}.h52svg line{stroke:#333}.h52price,.h52ma{fill:none;stroke-linecap:round;stroke-linejoin:round}.h52price{stroke:#f4f4f0;stroke-width:2}.h52ma{stroke-width:1.2;opacity:.9}.h52ma.ma50{stroke:#f5a623}.h52ma.ma100{stroke:#b58cff}.h52ma.ma200{stroke:#ffd84d}.h52bar{fill:#546477;opacity:.56}.h52bar.hot{fill:#5aa9ff;opacity:.95}.h52meta{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;border-top:1px solid #2b2b2b;padding-top:7px}.h52meta span{font:700 8px var(--sans);letter-spacing:.06em;color:var(--mut)}.h52meta b{display:block;color:var(--ink);font:700 10px var(--mono);margin-top:2px}.h52legend{margin-top:7px;color:var(--mut);font:8px var(--mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.h52legend i{display:inline-block;width:13px;border-top:2px solid #f4f4f0;margin:0 3px 2px 5px}.h52legend i.m50{border-color:#f5a623}.h52legend i.m100{border-color:#b58cff}.h52legend i.m200{border-color:#ffd84d}
.exheadline{display:flex;gap:28px;margin:12px 0 14px}.exheadline div{display:flex;flex-direction:column}.exheadline span{font:700 9px var(--sans);letter-spacing:.1em;color:var(--mut)}.exheadline b{font:700 17px var(--mono)}
.exstatus{display:inline-block;margin:0 0 9px;padding:5px 8px;border:1px solid #3c3c38;color:#b6b6af;font:700 9px var(--mono);letter-spacing:.04em}
.exswitch{display:flex;width:max-content;border:1px solid #444;margin:13px 0 12px}.exswitchbtn{border:0;background:#111;color:var(--mut);padding:8px 20px;font:800 10px var(--sans);letter-spacing:.08em;cursor:pointer}.exswitchbtn.on{background:#f4f4f0;color:#090909}
.excard{padding:0;margin-bottom:12px;overflow:hidden}.excard .ch{display:flex;justify-content:flex-start;align-items:center;gap:18px;min-height:42px;padding:10px 12px 8px;background:#101010;border-bottom:1px solid var(--line);overflow:hidden}.excard .ch>*{white-space:nowrap}.excard .ct{flex:0 0 auto;font-size:13px;line-height:1;font-weight:800;letter-spacing:.035em}.excard .ch>span:last-child{min-width:0;overflow:hidden;text-overflow:ellipsis;font-size:10px}.exsvg{width:100%;height:auto;display:block;background:linear-gradient(180deg,#13171c 0%,#101010 100%)}.exsvg text{fill:var(--mut);font:10px var(--mono)}.exsvg line{stroke:var(--line)}
.exarea{fill:url(#turnoverFill)}.exto{fill:none;stroke:#68b4ff;stroke-width:2.7;filter:drop-shadow(0 0 3px rgba(90,169,255,.35))}.expx{fill:none;stroke:#f1ae39;stroke-width:2.7;filter:drop-shadow(0 0 3px rgba(232,169,58,.25))}.exgridline{stroke:#34383d!important;stroke-width:1}.exaxis{fill:#88bdf0!important}.exaxis.price{fill:#d8a74f!important}.exkey{display:inline-block;width:17px;border-top:2px solid;margin:0 5px 2px 12px}.exkey.to{border-color:#5aa9ff}.exkey.px{border-color:var(--am)}
.exlayout{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;align-items:stretch}.exlayout>*{min-width:0}.exlayout>.excard{height:100%;margin-bottom:0}.exranges{display:flex;gap:5px;padding:0 18px 10px;flex-wrap:wrap}.exrangesbelow{grid-column:1;padding:0;align-self:start}.exrbtn{border:1px solid var(--line);background:transparent;color:var(--mut);font:800 9px var(--sans);letter-spacing:.08em;padding:6px 10px;cursor:pointer}.exrbtn:hover{color:var(--ink);border-color:var(--mut)}.exrbtn.on{background:var(--am);border-color:var(--am);color:#090909}.exbar{fill:#4e85d8;transition:opacity .12s}.exbar:hover,.exbar:focus{opacity:.72;stroke:#fff;stroke-width:1;outline:none}.exbar.month{fill:#607fc2}.exbar.latest{fill:var(--am)}.exbargrid{stroke:#30343a!important;stroke-width:1}.excompare{fill:var(--ink)!important;font-weight:800;letter-spacing:.04em}.excompare.up{fill:var(--g)!important}.excompare.down{fill:var(--r)!important}.monthtag{fill:var(--ink)!important;font-weight:700}.exbarhover{display:none;fill:var(--ink)!important;font-weight:800;paint-order:stroke;stroke:#101010;stroke-width:4px;stroke-linejoin:round;pointer-events:none}.exbaritem:hover .exbarhover,.exbaritem:focus-within .exbarhover{display:block}.excomment{margin:0 0 12px;padding:15px 16px;background:#101010;border-left:4px solid var(--am)}.excomment h3{margin:0 0 8px;font:800 10px var(--sans);letter-spacing:.11em}.excomment ul{margin:0 0 10px;padding-left:20px}.excomment li{margin:6px 0}.excomment a{font:700 9px var(--sans);letter-spacing:.08em;color:var(--am)}
@media(max-width:1100px){.exlayout{grid-template-columns:1fr 1fr}.exmain{grid-column:1/-1}}@media(max-width:700px){.exlayout{grid-template-columns:1fr}.exmain{grid-column:auto}.exheadline{gap:16px;flex-wrap:wrap}}
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
.sx{position:relative;margin-top:10px;padding-top:40px}.sl{position:absolute;right:0;top:0;z-index:4;display:flex;gap:6px;width:390px;padding:0}
#q{flex:1;min-width:0;font:600 12px var(--mono);background:#0d0d0d;color:var(--ink);border:1px solid #333;padding:8px 9px;border-radius:3px}#q:focus{outline:2px solid var(--am)}
#sort,#thr{font:600 11px var(--sans);background:#0d0d0d;color:var(--ink);border:1px solid #333;padding:6px 7px;border-radius:3px}#sort{width:175px}
#list{display:none;position:absolute;right:0;top:38px;width:390px;max-height:55vh;overflow:auto;background:var(--panel);border:1px solid #333;box-shadow:0 12px 30px #000}.sl:focus-within #list{display:block}.li{display:grid;grid-template-columns:1fr auto auto;gap:10px;padding:7px 10px;border-bottom:1px solid var(--line);cursor:pointer;font-family:var(--mono);font-size:12px;align-items:center}
.li:hover{background:#1c1c1c}.li.on{background:#262626;box-shadow:inset 4px 0 #f4f4f0}.li b{letter-spacing:.02em}.li span{min-width:52px;text-align:right}
.sr{min-width:0}#sh{background:var(--panel);border-top:3px solid #f4f4f0;padding:10px 13px 9px}.hd1{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 11px}.hd1 b{font-size:23px;letter-spacing:.01em}.hd1 .px{font:700 18px var(--mono)}
.chips2{display:flex;flex-wrap:wrap;gap:5px 17px;margin-top:7px;font:11px var(--mono)}.chips2 div span{display:block;color:var(--mut);font:600 9px var(--sans);letter-spacing:.08em;margin-bottom:1px}
.rsrow{display:flex;flex-wrap:wrap;gap:5px 14px;margin-top:7px;padding-top:7px;border-top:1px solid var(--line);font:11px var(--mono)}.rsrow span{color:var(--mut)}
.rb{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:7px 0 6px;font:600 10px var(--sans);letter-spacing:.08em}.rb .seg{padding:5px 10px;font-size:11px;border:1px solid #444}
.rb .mab{padding:5px 8px}.rb .mab.on{background:var(--am);border-color:var(--am);color:#090909}.rb .mab:disabled{opacity:.28;cursor:not-allowed}.malabel{margin-left:12px}
#chartbox{padding-top:6px}.chartgrid{display:grid;grid-template-columns:minmax(0,2fr) minmax(250px,1fr);gap:10px}.charts{min-width:0}.chartcard{background:var(--panel);padding:3px 4px 1px;margin-bottom:8px}.chartcard svg{display:block;width:100%;touch-action:pan-y}
#insights{background:var(--panel);border-top:3px solid #f4f4f0;padding:12px;align-self:start}.ititle{font:800 12px var(--sans);letter-spacing:.1em;margin-bottom:9px}.resultbox{background:rgba(232,169,58,.15);border-left:3px solid var(--am);padding:10px;margin-bottom:12px}.resultbox b{display:block;color:#ffd17a}.ievent{padding:9px 6px;border-top:1px solid var(--line);font:11px var(--mono);white-space:nowrap}.ievent.cashbuy{background:rgba(63,191,122,.13);box-shadow:inset 3px 0 var(--g);color:#d7f5e5}.ievent.cashsell{background:rgba(255,91,82,.13);box-shadow:inset 3px 0 var(--r);color:#ffd9d6}.ievent .idate{display:inline-block;color:var(--mut);margin-right:7px;white-space:nowrap}.itag{display:inline-block;font:800 9px var(--sans);letter-spacing:.06em;padding:3px 5px;margin-right:6px;background:#292929}.itag.del{color:#fff}.itag.oi{color:#8fc0ff}.itag.cash{background:var(--g);color:#06160d}.itag.cashsell{background:var(--r);color:#210302}.inone{color:var(--mut);font-size:12px;line-height:1.5}
.mahere{margin-top:15px;padding-top:13px;border-top:2px solid #333}.mahit{margin-top:7px;padding:9px 10px;background:#1b1b1b;border-left:3px solid var(--am);font:11px var(--mono);line-height:1.5}.mahit b{font:800 12px var(--sans);color:#ffd17a}.mahit .cross{display:inline-block;margin-left:6px;padding:2px 5px;background:var(--g);color:#07140c;font:800 8px var(--sans);letter-spacing:.05em}.mahit .fresh{color:var(--g)}
.guidancerow{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;border-left:3px solid var(--g);background:var(--panel);padding:8px 10px;margin-bottom:8px;font-size:12px}.guidancerow.reduction,.guidancerow.downgrade{border-color:var(--r)}.guidancerow button{margin-left:auto;cursor:pointer;white-space:normal}.guidancerow small{color:var(--mut)}#guidance-row[hidden]{display:none}.guidancechange{border-left:3px solid var(--g);padding:10px;margin:8px 0;background:var(--panel);overflow-wrap:anywhere}.guidancechange.reduction,.guidancechange.downgrade{border-color:var(--r)}.guidancechange summary{cursor:pointer}.guidancechange blockquote{margin:8px 0;white-space:pre-wrap}.guidancechange:focus,.guidancerow button:focus-visible{outline:2px solid #ffd17a;outline-offset:3px}#callintel{margin-top:10px}.callhead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;background:var(--panel);border-top:3px solid #f4f4f0;padding:12px 14px;margin-bottom:8px}.callhead h3{margin:0;font-size:16px;letter-spacing:.04em}.callhead a{color:#ffd17a;font:11px var(--mono)}.callmeta{color:var(--mut);font:10px var(--mono);margin-top:3px}.callpanels{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:8px}.callsection{background:var(--panel);border-top:3px solid #444;padding:12px;min-width:0}.callsection.outlookpanel{border-color:var(--g)}.callsection.focuspanel{border-color:var(--am)}.callsection.actualspanel{border-color:#5aa9ff}.callsection h4{margin:0 0 9px;font:800 10px var(--sans);letter-spacing:.1em;color:var(--mut)}.outlook{padding:9px 10px;margin-bottom:7px;background:#191919;border-left:3px solid #777;font-size:12px;line-height:1.45}.outlook.positive{border-color:var(--g)}.outlook.cautious,.outlook.negative{border-color:var(--r)}.outlook b{display:block;margin-bottom:2px}.evidence{display:block;color:#9d9d96;font:10px var(--mono);margin-top:4px}.focus{display:grid;grid-template-columns:1fr auto;gap:9px;padding:7px 0;border-bottom:1px solid var(--line);font-size:12px}.focus small{display:block;color:var(--mut);margin-top:2px}.qcount{font:700 11px var(--mono);color:#ffd17a}.metricgrid{display:grid;grid-template-columns:1fr;gap:7px}.metric{background:#191919;padding:8px 9px;font-size:11px;line-height:1.4}.metric b{display:block;color:var(--mut);font:800 9px var(--sans);letter-spacing:.07em;margin-bottom:2px}.congrats{display:flex;gap:16px;align-items:baseline;padding:10px;background:rgba(232,169,58,.1);margin-top:12px}.congrats strong{font:700 24px var(--mono);color:#ffd17a}.congrats span{font-size:11px;color:var(--mut)}.callnone{background:var(--panel);border-top:3px solid #444;padding:12px;color:var(--mut);font-size:12px}.aicaveat{margin-top:8px;color:#666;font-size:10px}
.calllibmeta{display:flex;flex-direction:column;margin:12px 0}.calllibmeta span{font:800 9px var(--sans);letter-spacing:.1em;color:var(--mut)}.calllibmeta b{font:700 15px var(--mono)}.calllibrary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.callcard{background:var(--panel);border-top:3px solid #f4f4f0;padding:13px;min-width:0}.callcardhead{display:flex;justify-content:space-between;gap:15px;align-items:flex-start;padding-bottom:11px;border-bottom:1px solid var(--line)}.callcardhead h3{margin:0 0 2px;font-size:18px}.callcardhead>div>div{color:var(--mut);font:10px var(--mono)}.callscore{display:flex;gap:7px;align-items:center;text-align:right}.callscore strong{font:800 23px var(--mono);color:#ffd17a}.callscore span{font:800 8px var(--sans);letter-spacing:.07em;color:var(--mut)}.callcols{display:grid;grid-template-columns:1fr 1fr;gap:12px}.callcard h4{margin:13px 0 5px;font:800 9px var(--sans);letter-spacing:.1em;color:var(--mut)}.callcard ol,.callcard ul{margin:0;padding-left:20px}.callcard li{position:relative;padding:6px 0 7px 2px;border-bottom:1px solid var(--line);font-size:11px;line-height:1.4}.callcard li b{display:block;font-size:11px;margin-bottom:1px}.callcard .concerns li{padding-right:28px}.callcard .concerns li span{position:absolute;right:0;top:7px;color:#ffd17a;font:700 10px var(--mono)}.takeaways{border-top:2px solid #333;margin-top:8px}.takeaways ul{display:grid;grid-template-columns:1fr 1fr;gap:0 12px;list-style:none;padding:0}.callsource{display:inline-block;margin-top:10px;color:#ffd17a;font:800 9px var(--sans);letter-spacing:.08em}
.calllibrary{display:flex;flex-direction:column;gap:10px}.callrow{background:var(--panel);border-top:3px solid #f4f4f0;padding:10px 12px;min-width:0}.callrowhead{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:7px}.callrowhead h3{display:inline;margin:0 9px 0 0;font-size:16px}.callrowhead span{color:var(--mut);font:9px var(--mono)}.callrowhead a{color:#ffd17a;font:800 9px var(--sans)}.callrowgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0}.callrowgrid>section{min-width:0;padding:10px 13px;border-left:1px solid var(--line)}.callrowgrid>section:first-child{border-left:0;padding-left:0}.callrowgrid h4{margin:0 0 6px;font:800 9px var(--sans);letter-spacing:.1em;color:var(--mut)}.callrowgrid ul{list-style:none;margin:0;padding:0}.callrowgrid li{padding:5px 0;border-bottom:1px solid var(--line);font-size:10px;line-height:1.35}.callrowgrid li:last-child{border-bottom:0}.callrowgrid li b,.callrowgrid li span{display:block}.callrowgrid li span{color:#b4b4ad;margin-top:1px}.callrowgrid .shift.upgrade,.callrowgrid .shift.increase,.callrowgrid .shift.improvement{border-left:3px solid var(--g);padding-left:7px}.callrowgrid .shift.reduction,.callrowgrid .shift.downgrade{border-left:3px solid var(--r);padding-left:7px}.callchart{display:block;width:100%;height:auto;background:#111}.callchartline{fill:none;stroke-linejoin:round;stroke-linecap:round}.callchartline.price{stroke:#f4f4f0;stroke-width:2}.callchartline.ma50{stroke:#f5a623}.callchartline.ma100{stroke:#b58cff}.callchartline.ma200{stroke:#ffd84d}.callchartlegend{color:var(--mut);font:8px var(--mono);margin-top:4px}.callchartlegend i{display:inline-block;width:10px;border-top:2px solid #f4f4f0;margin:0 3px 2px 6px}.callchartlegend i:first-child{margin-left:0}.callchartlegend i.m50{border-color:#f5a623}.callchartlegend i.m100{border-color:#b58cff}.callchartlegend i.m200{border-color:#ffd84d}.callchartempty{height:115px;display:grid;place-items:center;background:#111;color:var(--mut);font:10px var(--mono)}
#ro{min-height:22px;font:11px var(--mono);color:#cfcfc8;padding:5px 4px}
#lg{display:flex;flex-wrap:wrap;gap:6px 18px;font:12px var(--mono);color:var(--mut);padding:2px 4px 10px}#lg i{display:inline-block;width:14px;height:10px;margin-right:6px;vertical-align:-1px}#lg u{display:inline-block;width:18px;border-top:2px solid;margin-right:5px;vertical-align:middle}
footer{max-width:1280px;margin:0 auto;padding:0 22px 40px;color:var(--mut);font-size:13px}
@media (max-width:1000px){.h52grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:900px){.sx{padding-top:76px}.sl{width:100%;flex-wrap:wrap}.sl #q{flex-basis:100%}#sort{width:100%}#list{top:38px;width:100%;max-height:230px}.chartgrid,.callpanels{grid-template-columns:1fr}.callrowgrid{grid-template-columns:1fr}.callrowgrid>section{border-left:0;border-top:1px solid var(--line);padding:10px 0}.callrowgrid>section:first-child{border-top:0}#insights{position:static;max-height:none}.hd1 b{font-size:21px}header{flex-direction:column;align-items:flex-start}.headright{align-items:flex-start;flex-direction:column}.meta{text-align:left}h2{font-size:21px}.hz{grid-template-columns:1fr}.atrow{flex-direction:column;gap:9px}main{padding:4px 9px 35px}}@media (max-width:620px){.h52grid{grid-template-columns:1fr}.h52meta{grid-template-columns:1fr 1fr}.h52caps{width:100%;flex-wrap:wrap}}
"""

JS = r"""
const D=JSON.parse(document.getElementById('data').textContent),ALL=Object.keys(D.stocks);
const COL={32:'#5aa9ff',50:'#f5a623',100:'#b58cff',200:'#ffd84d',233:'#3fd0a0',377:'#ff7aa2',610:'#9a9a94'};
const G='#2fbf71',R='#ef5a4d',GL='rgba(47,191,113,.64)',RL='rgba(239,90,77,.64)',GR='#a3a39c',GRL='rgba(163,163,156,.46)';
let cur=null,rng=252,thr=1.25,universe='top1000',SY=D.universes[universe]||ALL,selectedMas=new Set([50,200]);
try{const saved=JSON.parse(localStorage.getItem('desk-mas'));if(Array.isArray(saved))selectedMas=new Set(saved.map(Number))}catch(e){}
function tab(t){const b=document.querySelector('.tab[data-t="'+t+'"]');if(b)b.click()}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!=='p-'+b.dataset.t);if(b.dataset.t==='stocks'){draw()}});
document.querySelectorAll('.h52tab').forEach(b=>b.onclick=()=>{const p=b.closest('.panel');p.querySelectorAll('.h52tab').forEach(x=>x.classList.toggle('on',x===b));p.querySelectorAll('.h52group').forEach(x=>x.hidden=x.dataset.h52Group!==b.dataset.h52)});
document.querySelectorAll('.h52cap').forEach(b=>b.onclick=()=>{const g=b.closest('.h52group'),f=b.dataset.mcapFilter;g.querySelectorAll('.h52cap').forEach(x=>x.classList.toggle('on',x===b));g.querySelectorAll('.h52card').forEach(x=>x.hidden=f!=='all'&&x.dataset.mcap!==f)});
document.querySelectorAll('.exswitchbtn').forEach(b=>b.onclick=()=>{const p=b.closest('.panel');p.querySelectorAll('.exswitchbtn').forEach(x=>x.classList.toggle('on',x===b));p.querySelectorAll('.exchangegroup').forEach(x=>x.hidden=x.dataset.exchangeGroup!==b.dataset.exchange)});
document.querySelectorAll('.seg[data-h]').forEach(b=>b.onclick=()=>{const v=b.closest('.uview')||document;v.querySelectorAll('.seg[data-h]').forEach(x=>x.classList.toggle('on',x===b));v.querySelectorAll('.hz').forEach(h=>h.hidden=h.dataset.h!==b.dataset.h)});
document.querySelectorAll('.seg[data-r]').forEach(b=>b.onclick=()=>{rng=+b.dataset.r;document.querySelectorAll('.seg[data-r]').forEach(x=>x.classList.toggle('on',x===b));draw()});
document.querySelectorAll('.exrbtn').forEach(b=>b.onclick=()=>{const v=b.closest('.exlayout');v.querySelectorAll('.exrbtn').forEach(x=>x.classList.toggle('on',x===b));v.querySelectorAll('.exrange').forEach(x=>x.hidden=x.dataset.xr!==b.dataset.xr)});
document.querySelectorAll('.mab').forEach(b=>{const m=+b.dataset.ma;b.disabled=D.dates.length<m+1;b.classList.toggle('on',selectedMas.has(m)&&!b.disabled);b.title=b.disabled?`Needs ${m+1} sessions; currently ${D.dates.length}`:`Toggle ${m}-day moving average`;b.onclick=()=>{selectedMas.has(m)?selectedMas.delete(m):selectedMas.add(m);b.classList.toggle('on',selectedMas.has(m));try{localStorage.setItem('desk-mas',JSON.stringify([...selectedMas]))}catch(e){}draw()}});
document.getElementById('thr').onchange=e=>{thr=+e.target.value;draw()};
document.getElementById('universe').onchange=e=>{universe=e.target.value;SY=D.universes[universe]||ALL;document.querySelectorAll('.uview').forEach(v=>v.hidden=v.dataset.u!==universe);if(!SY.includes(cur))cur=SY[0]||D.default;list();draw()};
function sma(a,n){const o=new Array(a.length).fill(null);let s=0,c=0;for(let i=0;i<a.length;i++){const v=a[i];if(v!=null){s+=v;c++}if(i>=n){const u=a[i-n];if(u!=null){s-=u;c--}}if(c===n&&i>=n-1)o[i]=s/n}return o}
function fmt(x){if(x==null)return'–';const a=Math.abs(x);return a>=1e7?(x/1e7).toFixed(2)+' cr':a>=1e5?(x/1e5).toFixed(1)+' L':Math.round(x).toLocaleString()}
function fL(x){return x==null?'–':(x>=0?'+':'−')+Math.abs(x/1e5).toLocaleString(undefined,{maximumFractionDigits:1,minimumFractionDigits:1})+' L'}
function pc(x,d=1){return x==null?'–':(x>=0?'+':'−')+Math.abs(x).toFixed(d)+'%'}
function cls(x){return x==null?'':x>=0?'g':'r'}
function resultLabel(r){if(!r)return'';const d=new Date(r.date+'T00:00:00');return 'RESULT '+d.toLocaleDateString('en-GB',{day:'2-digit',month:'short'}).toUpperCase()}
function escH(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function guidanceEvidence(e){return `<blockquote>${escH(e.quote)}</blockquote><p>${escH(e.speaker)} · ${escH(e.role)} · ${escH(e.location)} · ${escH(e.call_period)}<br><a href="${escH(e.source_url)}" target="_blank" rel="noopener">Exchange transcript · ${escH(e.filing_date)} ↗</a></p>`}
function guidanceDetails(changes){return changes.length?`<section aria-label="Material Guidance Changes"><h3>MATERIAL GUIDANCE CHANGES</h3>${changes.map((g,i)=>{const pair=g.old_guidance&&g.new_guidance?`${escH(g.old_guidance)} → ${escH(g.new_guidance)}`:escH(g.magnitude);return `<details class="guidancechange ${escH(g.direction)}" id="guidance-${i}" tabindex="-1"><summary>${escH(g.direction.toUpperCase())} · ${escH(g.topic)} · ${pair}</summary><p>${escH(g.explicit_statement)}</p>${guidanceEvidence(g.evidence)}</details>`}).join('')}</section>`:''}
function guidanceRow(S){const row=document.getElementById('guidance-row'),changes=S.call?.analysis?.material_guidance_changes||[],g=changes[0];row.hidden=!g;row.innerHTML='';row.className='';if(!g)return;const pair=g.old_guidance&&g.new_guidance?`${escH(g.old_guidance)} → ${escH(g.new_guidance)}`:escH(g.magnitude);row.className='guidancerow '+g.direction;row.innerHTML=`<b>${escH(g.direction.toUpperCase())} · ${escH(g.topic)}</b><span>${pair}</span><small>${escH(g.evidence.call_period)} · ${escH(g.evidence.filing_date)}</small><button type="button" aria-controls="guidance-0">View contextual evidence</button>`;row.querySelector('button').onclick=()=>{const detail=document.getElementById('guidance-0');if(detail){detail.open=true;detail.scrollIntoView({block:'nearest',behavior:'smooth'});detail.focus()}}}
function callPanel(S){const el=document.getElementById('callintel'),c=S.call;if(c&&c.transcript_status==='missing'){el.innerHTML=`<div class="callnone"><b>CALL INTELLIGENCE · TRANSCRIPT MISSING</b><br>${escH(c.status_detail||'The exchange attachment did not contain an extractable transcript.')} <a href="${escH(c.source_url)}" target="_blank" rel="noopener">OPEN EXCHANGE FILING ↗</a></div>`;return}if(!c||!c.analysis){el.innerHTML='<div class="callnone">CALL INTELLIGENCE · No bundled transcript analysis for this stock yet.</div>';return}const a=c.analysis,o=a.next_quarter_outlook||[],f=['all_material_themes','top_themes_by_question_count'].includes(a.analyst_focus_scope)?(a.analyst_focus||[]):(a.analyst_focus||[]).slice(0,2),cg=a.congratulations||{},forwardOnly=a.analysis_profile==='forward_only_v1',sector=a.company_type==='manufacturer'?a.manufacturer:a.company_type==='bank_lender'?a.bank_lender:null;const labels={revenue_growth:'Revenue growth',volume_growth:'Volume growth',order_inflow:'Order inflow',demand_outlook:'Demand outlook',margin_outlook:'Margin outlook',ebitda_margin:'EBITDA margin',credit_growth:'Credit growth',credit_deposit_ratio:'Credit–deposit ratio',disbursements:'Disbursements',nim_outlook:'NIM outlook',asset_quality:'Asset quality',credit_cost_outlook:'Credit cost outlook'};const actuals=sector?Object.entries(sector).filter(([,v])=>v).map(([k,v])=>`<div class="metric"><b>${escH(labels[k]||k)}</b>${escH(v)}</div>`).join(''):(a.key_actuals||[]).map(x=>`<div class="metric"><b>${escH(x.metric)}</b>${escH(x.value)}</div>`).join('');const risks=(a.key_risks||[]).map(v=>`<div class="metric"><b>FORWARD RISK / WATCHPOINT</b>${escH(v)}</div>`).join('');const legacyCongrats=forwardOnly?'':`<div class="congrats"><strong>${cg.index_pct==null?'not disclosed':Number(cg.index_pct).toFixed(0)+'%'}</strong><div>CONGRATULATIONS INDEX<br><span>${cg.count??'not disclosed'} congratulatory turns / ${cg.analyst_turns??'not disclosed'} analyst turns</span></div></div>`;const lastPanel=forwardOnly?`<div class="callsection actualspanel"><h4>FORWARD RISKS &amp; WATCHPOINTS</h4><div class="metricgrid">${risks||'<div class="inone">No forward risk disclosed.</div>'}</div><div class="aicaveat">Static research from the linked transcript. Check the source before relying on a statement.</div></div>`:`<div class="callsection actualspanel"><h4>KEY ACTUALS &amp; GUIDANCE</h4><div class="metricgrid">${actuals||'<div class="inone">No disclosed actuals extracted.</div>'}${risks}</div><div class="aicaveat">Static research from the linked transcript. Check the source before relying on a statement.</div></div>`;el.innerHTML=`<div class="callhead"><div><h3>CALL INTELLIGENCE · ${escH(a.call_period||'LATEST CALL')}</h3><div class="callmeta">${escH(a.company_type.replace('_',' ').toUpperCase())} · filed ${escH((c.filed_at||'').slice(0,10))}</div></div><a href="${escH(c.source_url)}" target="_blank" rel="noopener">OPEN TRANSCRIPT ↗</a></div><div class="callpanels"><div class="callsection outlookpanel"><h4>NEXT QUARTER OUTLOOK</h4>${o.length?o.map(x=>`<div class="outlook ${escH(x.tone)}"><b>${escH(x.topic)}</b>${escH(x.summary)}<details class="evidence"><summary>Transcript evidence</summary>${escH(x.evidence)} · ${escH(x.speaker)} · ${escH(x.role)} · ${escH(x.location)}</details></div>`).join(''):'<div class="inone">No explicit next-quarter guidance found.</div>'}</div><div class="callsection focuspanel"><h4>WHAT ANALYSTS CARED ABOUT</h4>${f.length?f.map(x=>`<div class="focus"><div><b>${escH(x.topic)}</b><small>${escH(x.why_it_mattered)}</small></div></div>`).join(''):'<div class="inone">No analyst-question themes extracted.</div>'}${legacyCongrats}</div>${lastPanel}</div>${guidanceDetails(a.material_guidance_changes||[])}`}
const callPanelBase=callPanel;
callPanel=function(S){const plus=S.call?.analysis?.analysis_profile==='forward_plus_actuals_v1';if(!plus)return callPanelBase(S);const a=S.call.analysis,copy={...S,call:{...S.call,analysis:{...a,analysis_profile:'forward_only_v1'}}};callPanelBase(copy);const panel=document.querySelector('#callintel .actualspanel'),grid=panel?.querySelector('.metricgrid');if(panel&&grid){panel.querySelector('h4').textContent='QUICK ACTUALS & FORWARD WATCHPOINTS';grid.insertAdjacentHTML('afterbegin',(a.key_actuals||[]).map(x=>`<div class="metric"><b>${escH(x.metric)}</b>${escH(x.value)}</div>`).join(''))}}
/* ---------- ticker list ---------- */
function list(){const q=document.getElementById('q').value.trim().toUpperCase(),so=document.getElementById('sort').value;
 const key={az:s=>s,ratio:s=>-(D.stocks[s].sm.ratio??-1e9),px:s=>-(D.stocks[s].sm.px??-1e9),rs:s=>-(D.stocks[s].sm.rel[1][0]??-1e9)}[so];
 const a=SY.filter(s=>!q||s.includes(q)).sort((x,y)=>{const a=key(x),b=key(y);return a<b?-1:a>b?1:0});
 document.getElementById('list').innerHTML=a.map(s=>{const m=D.stocks[s].sm,r=D.stocks[s].result?`<span class="resultmark" title="Upcoming result">${resultLabel(D.stocks[s].result)}</span>`:'';return `<div class="li${s===cur?' on':''}" data-s="${s}" tabindex="-1"><b>${s} ${r}</b><span class="${cls(m.px)}">${pc(m.px)}</span><span class="mut">${m.ratio==null?'–':m.ratio.toFixed(1)+'×'}</span></div>`}).join('')||'<div class="li mut">No match</div>'}
document.getElementById('q').oninput=list;document.getElementById('sort').onchange=list;
document.getElementById('q').onkeydown=e=>{if(e.key==='Enter'){const f=document.querySelector('#list .li[data-s]');if(f)pick(f.dataset.s)}};
document.getElementById('list').onclick=e=>{const li=e.target.closest('.li[data-s]');if(li)pick(li.dataset.s)};
function pick(s){cur=s;list();draw();history.replaceState(null,'','#'+s);if(document.activeElement)document.activeElement.blur();if(window.innerWidth<900)document.getElementById('sh').scrollIntoView({behavior:'smooth',block:'start'})}
document.addEventListener('click',e=>{const a=e.target.closest('a.stk');if(a){e.preventDefault();tab('stocks');cur=a.dataset.s;list();draw();history.replaceState(null,'','#'+cur);window.scrollTo(0,0)}});
/* ---------- chart ---------- */
function drawLegacy(){
 if(!cur||document.getElementById('p-stocks').hidden)return;
 const S=D.stocks[cur],n=S.c.length,v0=Math.max(0,n-rng),box=document.getElementById('chartbox'),W=Math.max(320,Math.min(1460,box.clientWidth-8)),sm=W<560,fs=sm?9:10,L=sm?42:54,Rr=8;
 const H=sm?[150,62,58,46,46]:[205,76,70,54,54],gap=sm?18:21,tops=[6];for(let k=1;k<5;k++)tops.push(tops[k-1]+H[k-1]+gap);const TH=tops[4]+H[4]+18;
 const xs=i=>L+(i-v0)*(W-L-Rr)/Math.max(1,n-1-v0),bw=Math.max(1.4,(W-L-Rr)/(n-v0)*.82);
 const y=(v,lo,hi,k)=>tops[k]+(1-(v-lo)/(hi-lo||1))*H[k];
 let g='';const lab=(t,k)=>`<text x="${L+4}" y="${tops[k]+11}" fill="#77776f" font-size="${fs}" font-family="monospace" letter-spacing="1">${t}</text>`;
 const grid=(lo,hi,k,f)=>{let o='';for(let j=0;j<=2;j++){const v=lo+(hi-lo)*j/2,yy=y(v,lo,hi,k);o+=`<line x1="${L}" x2="${W-Rr}" y1="${yy}" y2="${yy}" stroke="#222"/><text x="${L-5}" y="${yy+3}" fill="#77776f" font-size="${fs}" text-anchor="end" font-family="monospace">${f(v)}</text>`}return o};
 const path=(a,k,lo,hi,col,sw,dash,base)=>{let d='',pen=false;for(let i=v0;i<n;i++){const v=a[i];if(v==null){pen=false;continue}d+=(pen?'L':'M')+xs(i).toFixed(1)+','+y(base?base(v):v,lo,hi,k).toFixed(1);pen=true}return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${sw}"${dash?' stroke-dasharray="'+dash+'"':''} stroke-linejoin="round"/>`};
 /* 1 price + averages */
 const mas=D.mas.filter(m=>n>=m+1&&selectedMas.has(m)).map(m=>[m,sma(S.c,m)]);let lo=1e18,hi=-1e18;for(let i=v0;i<n;i++){const v=S.c[i];if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v)}}
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
 const bu=dOI==null?'–':dOI>=0?(up?'Long Buildup':'Cash Selling'):(up?'Cash Buying':'Long Unwind'),buc=dOI==null?'':(up?'g':'r');
 const rs=D.hz.map((h,k)=>{const r=m.rel[k];return `<div><span>${h[0].toUpperCase()}</span><b class="${cls(r[0])}">${pc(r[0])}</b> <i class="mut" style="font-style:normal">#${r[1]??'–'}/${SY.length}</i></div>`}).join('');
 document.getElementById('sh').innerHTML=`<div class="hd1"><b>${cur}</b><span class="px">${last==null?'–':last.toFixed(2)}</span><span class="${cls(m.px)}">${pc(m.px,2)}</span></div>
 <div class="chips2"><div><span>DELIVERED</span>${fmt(m.dq)}</div><div><span>÷ 20D AVG</span>${m.ratio==null?'–':m.ratio.toFixed(2)+'×'}</div><div><span>DELIV %</span>${m.dp==null?'–':m.dp.toFixed(1)}</div><div><span>BSE %</span>${m.bse==null?'–':m.bse.toFixed(0)}</div>
 <div><span>SSF OI</span>${fmt(lastOI)}</div><div><span>ΔOI 1D</span><b class="${cls(dOI)}">${fL(dOI)}</b></div><div><span>OI BUILD-UP</span><b class="${buc}">${bu}</b></div></div>
 <div class="rsrow">${rs}</div>`;
 /* legend + hover */
 document.getElementById('lg').innerHTML=mas.map(([m])=>`<span><u style="border-color:${COL[m]}"></u>${m}</span>`).join('')+`<span><u style="border-color:#fff"></u>price</span><span><i style="background:${G}"></i>Long Buildup</span><span><i style="background:#5aa9ff"></i>Cash Buying</span><span><i style="background:${R}"></i>Cash Selling</span><span><i style="background:#e8a93a"></i>Long Unwind</span>`;
 const ro=document.getElementById('ro');ro.innerHTML='<span class="mut">Move over the chart for daily detail</span>';
 const mv=e=>{const r=svg.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*W;let i=Math.round(v0+(x-L)*(n-1-v0)/(W-L-Rr));i=Math.max(v0,Math.min(n-1,i));const xh=document.getElementById('xh');xh.setAttribute('x1',xs(i));xh.setAttribute('x2',xs(i));xh.setAttribute('visibility','visible');
  const ch=S.c[i]!=null&&S.c[i-1]!=null?(S.c[i]/S.c[i-1]-1)*100:null;ro.innerHTML=`${D.dates[i]} · close ${S.c[i]??'–'} <span class="${cls(ch)}">${pc(ch,2)}</span> · delivered ${fmt(S.dq[i])} (${S.rat[i]==null?'–':S.rat[i].toFixed(2)+'× avg'}) · ΔOI ${fL(dl[i])}`};
 svg.onpointermove=mv;svg.onpointerdown=mv;svg.onpointerleave=()=>{document.getElementById('xh').setAttribute('visibility','hidden')};
}
function draw(){
 if(!cur||document.getElementById('p-stocks').hidden)return;
 const S=D.stocks[cur],n=S.c.length,v0=Math.max(0,n-rng),box=document.getElementById('chartbox'),W=Math.max(320,box.clientWidth-8),sm=W<560,fs=sm?9:10,L=sm?42:54,Rr=8;
 const xs=i=>L+(i-v0)*(W-L-Rr)/Math.max(1,n-1-v0),bw=Math.max(1.4,(W-L-Rr)/(n-v0)*.82);
 const line=(a,y,col,sw=1.5,dash=null,map=v=>v)=>{let d='',pen=false;for(let i=v0;i<n;i++){const v=a[i];if(v==null){pen=false;continue}d+=(pen?'L':'M')+xs(i).toFixed(1)+','+y(map(v)).toFixed(1);pen=true}return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${sw}"${dash?' stroke-dasharray="'+dash+'"':''} stroke-linejoin="round"/>`};
 const frame=(lo,hi,H,title,format=v=>v.toFixed(0))=>{const y=v=>8+(1-(v-lo)/(hi-lo||1))*(H-18);let g=`<text x="${L+4}" y="18" fill="#77776f" font-size="${fs}" font-family="monospace" letter-spacing="1">${title}</text>`;for(let j=0;j<=2;j++){const v=lo+(hi-lo)*j/2,yy=y(v);g+=`<line x1="${L}" x2="${W-Rr}" y1="${yy}" y2="${yy}" stroke="#222"/><text x="${L-5}" y="${yy+3}" fill="#77776f" font-size="${fs}" text-anchor="end" font-family="monospace">${format(v)}</text>`}return [y,g]};
 const setsvg=(id,H,g)=>{const s=document.getElementById(id);s.setAttribute('viewBox',`0 0 ${W} ${H}`);s.setAttribute('width',W);s.setAttribute('height',H);s.innerHTML=g;return s};
 const mas=D.mas.filter(m=>n>=m+1&&selectedMas.has(m)).map(m=>[m,sma(S.c,m)]),PH=sm?150:190,DH=sm?76:90,gap=18,dateH=20,plotBottom=PH+gap+DH,MH=plotBottom+dateH;
 let lo=1e18,hi=-1e18;for(let i=v0;i<n;i++){const v=S.c[i];if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v)}}const lo0=lo,hi0=hi;mas.forEach(([,a])=>{for(let i=v0;i<n;i++){const v=a[i];if(v!=null&&v>lo0*.8&&v<hi0*1.25){lo=Math.min(lo,v);hi=Math.max(hi,v)}}});let pad=(hi-lo)*.05||1;lo-=pad;hi+=pad;
 let [yp,g]=frame(lo,hi,PH,sm?'PRICE · AVERAGES':'PRICE (ADJUSTED) · MOVING AVERAGES',v=>v.toFixed(v>=1000?0:1));mas.forEach(([m,a])=>g+=line(a,yp,COL[m],m===200?1.9:1.3));g+=line(S.c,yp,'#fff',1.8);
 const avg=new Array(n).fill(null);for(let i=20;i<n;i++){let s=0,c=0;for(let j=i-20;j<i;j++)if(S.dq[j]!=null){s+=S.dq[j];c++}if(c>=15)avg[i]=s/c}let dmax=0;for(let i=v0;i<n;i++)dmax=Math.max(dmax,S.dq[i]||0,avg[i]||0);dmax*=1.05;
 const yd=v=>PH+gap+(1-v/(dmax||1))*(DH-12);g+=`<text x="${L+4}" y="${PH+gap+11}" fill="#77776f" font-size="${fs}" font-family="monospace" letter-spacing="1">DELIVERED SHARES · DASHED = 20D AVG</text>`;for(let i=v0;i<n;i++){const q=S.dq[i];if(q==null)continue;const hot=(S.rat[i]??0)>=thr,d=S.d[i],col=d===0?(hot?GR:GRL):d===1?(hot?G:GL):(hot?R:RL),h=q/(dmax||1)*(DH-12);g+=`<rect x="${(xs(i)-bw/2).toFixed(1)}" y="${(plotBottom-h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" fill="${col}"/>`}g+=line(avg,yd,'#e8e8e2',1.4,'4 3');
 S.ev.forEach(([i,f])=>{if(i<v0)return;const x=xs(i);g+=`<line x1="${x}" x2="${x}" y1="8" y2="${plotBottom}" stroke="${G}" stroke-dasharray="4 3" opacity=".7"/><text x="${x+4}" y="31" fill="${G}" font-size="${fs}" font-family="monospace">adjusted ×${f}</text>`});g+=`<line x1="${L}" x2="${W-Rr}" y1="${plotBottom}" y2="${plotBottom}" stroke="#333"/>`;const dateIdx=sm?[v0,Math.round((v0+n-1)/2),n-1]:[v0,Math.round(v0+(n-1-v0)*.25),Math.round((v0+n-1)/2),Math.round(v0+(n-1-v0)*.75),n-1];dateIdx.forEach(i=>g+=`<text x="${xs(i)}" y="${plotBottom+15}" fill="#8b8b86" font-size="${fs}" text-anchor="${i===v0?'start':i===n-1?'end':'middle'}" font-family="monospace">${D.dates[i]}</text>`);g+=`<line id="xh" x1="0" x2="0" y1="8" y2="${plotBottom}" stroke="#aaa" visibility="hidden"/>`;const main=setsvg('ch',MH,g);
 const RH=sm?74:92,rsf=S.c.map((v,i)=>v!=null&&D.nifty[i]!=null?v/D.nifty[i]:null),rsm=sma(rsf,50);let base=null;for(let i=v0;i<n;i++)if(rsf[i]!=null){base=rsf[i];break}let rg='';if(base){const rb=v=>v/base*100;let rlo=1e18,rhi=-1e18;for(let i=v0;i<n;i++)for(const v of [rsf[i],rsm[i]])if(v!=null){rlo=Math.min(rlo,rb(v));rhi=Math.max(rhi,rb(v))}const rp=(rhi-rlo)*.08||1;rlo-=rp;rhi+=rp;let yr;[yr,rg]=frame(rlo,rhi,RH,'RELATIVE STRENGTH VS NIFTY · ORANGE = 50D AVG',v=>v.toFixed(0));rg+=line(rsm,yr,'#f5a623',1.3,null,rb)+line(rsf,yr,'#fff',1.7,null,rb)}setsvg('rsch',RH,rg);
 const OH=sm?78:98,dl=new Array(n).fill(null);let omax=0;for(let i=1;i<n;i++){if(S.oi[i]!=null&&S.oi[i-1]!=null)dl[i]=S.oi[i]-S.oi[i-1];if(i>=v0)omax=Math.max(omax,S.oi[i]||0)}let [yo,og]=frame(0,omax*1.05||1,OH,'TOTAL SSF OPEN INTEREST · COLOUR = PRICE/OI BEHAVIOUR',fmt);if(omax){for(let i=v0;i<n;i++){const oi=S.oi[i];if(oi==null)continue;const up=i>0&&S.c[i]!=null&&S.c[i-1]!=null&&S.c[i]>=S.c[i-1],od=dl[i],col=od==null?'#555':od>=0?(up?G:R):(up?'#5aa9ff':'#e8a93a'),h=OH-18-yo(oi);og+=`<rect x="${(xs(i)-bw/2).toFixed(1)}" y="${yo(oi).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(.5,h).toFixed(1)}" fill="${col}"/>`}}else og+=`<text x="${L+4}" y="${OH/2}" fill="#555" font-size="${fs}" font-family="monospace">not in F&amp;O for this period</text>`;setsvg('oich',OH,og);
 const m=S.sm,last=S.c[n-1],lastOI=S.oi[n-1],dOI=dl[n-1],dOIPct=dOI!=null&&S.oi[n-2]?dOI/S.oi[n-2]*100:null,up=S.c[n-1]>=S.c[n-2],bu=dOI==null?'–':dOI>=0?(up?'Long Buildup':'Cash Selling'):(up?'Cash Buying':'Long Unwind'),buc=dOI==null?'':bu==='Long Buildup'?'g':bu==='Cash Selling'?'r':'';
 const rs=D.hz.map((h,k)=>{const r=m.rel[k];return `<div><span>${h[0].toUpperCase()}</span><b class="${cls(r[0])}">${pc(r[0])}</b> <i class="mut" style="font-style:normal">#${r[1]??'–'}/${SY.length}</i></div>`}).join(''),rbadge=S.result?`<span class="resultmark" title="Upcoming result">${resultLabel(S.result)}</span>`:'';
 document.getElementById('sh').innerHTML=`<div class="hd1"><b>${cur}</b>${rbadge}<span class="px">${last==null?'–':last.toFixed(2)}</span><span class="${cls(m.px)}">${pc(m.px,2)}</span></div><div class="chips2"><div><span>DELIVERED</span>${fmt(m.dq)}</div><div><span>÷ 20D AVG</span>${m.ratio==null?'–':m.ratio.toFixed(2)+'×'}</div><div><span>DELIV %</span>${m.dp==null?'–':m.dp.toFixed(1)}</div><div><span>BSE %</span>${m.bse==null?'–':m.bse.toFixed(0)}</div><div><span>SSF OI</span>${fmt(lastOI)}</div><div><span>ΔOI 1D</span><b class="${cls(dOIPct)}">${pc(dOIPct)}</b></div><div><span>OI SIGNAL</span><b class="${buc}">${bu}</b></div></div><div class="rsrow">${rs}</div>`;
 const events=[];for(let i=Math.max(1,n-5);i<n;i++){const move=S.c[i]!=null&&S.c[i-1]!=null?(S.c[i]/S.c[i-1]-1)*100:null,op=dl[i]!=null&&S.oi[i-1]?dl[i]/S.oi[i-1]*100:null,aboveAvg=(S.rat[i]??0)>1,cashbuy=aboveAvg&&move>0&&op<0,cashsell=aboveAvg&&move<0&&op>0;if(cashbuy){events.push({i,kind:'cash',tone:'cashbuy',txt:`${S.rat[i].toFixed(2)}× delivery · ${pc(op)} OI`});continue}if(cashsell){events.push({i,kind:'cashsell',tone:'cashsell',txt:`${S.rat[i].toFixed(2)}× delivery · ${pc(op)} OI`});continue}if((S.rat[i]??0)>=1.5)events.push({i,kind:'del',txt:`${S.rat[i].toFixed(2)}× delivery · ${pc(move)}`});if(op!=null&&Math.abs(op)>=3){const pu=move>=0,label=dl[i]>=0?(pu?'Long Buildup':'Cash Selling'):(pu?'Cash Buying':'Long Unwind');events.push({i,kind:'oi',txt:`${label} · ${pc(op)} OI`})}}events.sort((a,b)=>b.i-a.i);let ih='<div class="ititle">RECENT ACTIVITY · 5 SESSIONS</div>';if(S.result)ih+=`<div class="resultbox"><b>UPCOMING RESULT</b>${S.result.date} · ${S.result.status}</div>`;ih+=events.length?events.map(e=>`<div class="ievent${e.tone?' '+e.tone:''}"><span class="idate">${D.dates[e.i].slice(5)}</span><span class="itag ${e.kind}">${e.kind==='del'?'DELIVERY':e.kind==='cash'?'CASH BUYING':e.kind==='cashsell'?'CASH SELLING':'OI'}</span>${e.txt}</div>`).join(''):'<div class="inone">No above-average delivery cash-buying/cash-selling signal, delivery ≥1.5× average, or daily OI move ≥3% in the last 5 sessions.</div>';ih+='<div class="mahere"><div class="ititle">AT A MOVING AVERAGE</div>'+(S.at&&S.at.length?S.at.map(a=>`<div class="mahit"><b>${a.ma}-DAY MA</b>${a.crossed?'<span class="cross">CROSSED TODAY</span>':''}<br><span class="${a.new?'fresh':''}">${a.above?'above':'below'} by ${Math.abs(a.dist).toFixed(2)}% · ${Math.abs(a.dist/a.sigma).toFixed(2)}σ${a.new?' · new today':''}</span></div>`).join(''):'<div class="inone">Not currently within 0.5σ of an active moving average.</div>')+'</div>';document.getElementById('insights').innerHTML=ih;
 callPanel(S);
 guidanceRow(S);
 document.getElementById('lg').innerHTML=mas.map(([m])=>`<span><u style="border-color:${COL[m]}"></u>${m}</span>`).join('')+`<span><u style="border-color:#fff"></u>price / RS</span><span><i style="background:${G}"></i>Long Buildup</span><span><i style="background:#5aa9ff"></i>Cash Buying</span><span><i style="background:${R}"></i>Cash Selling</span><span><i style="background:#e8a93a"></i>Long Unwind</span>`;
 const ro=document.getElementById('ro');ro.innerHTML='<span class="mut">Move over the price chart for daily detail</span>';const mv=e=>{const r=main.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*W;let i=Math.round(v0+(x-L)*(n-1-v0)/(W-L-Rr));i=Math.max(v0,Math.min(n-1,i));const xh=document.getElementById('xh');xh.setAttribute('x1',xs(i));xh.setAttribute('x2',xs(i));xh.setAttribute('visibility','visible');const ch=S.c[i]!=null&&S.c[i-1]!=null?(S.c[i]/S.c[i-1]-1)*100:null,op=dl[i]!=null&&S.oi[i-1]?dl[i]/S.oi[i-1]*100:null;ro.innerHTML=`${D.dates[i]} · close ${S.c[i]??'–'} <span class="${cls(ch)}">${pc(ch,2)}</span> · delivered ${fmt(S.dq[i])} (${S.rat[i]==null?'–':S.rat[i].toFixed(2)+'× avg'}) · OI ${fmt(S.oi[i])} · ΔOI ${pc(op)}`};main.onpointermove=mv;main.onpointerdown=mv;main.onpointerleave=()=>document.getElementById('xh').setAttribute('visibility','hidden');
}
let rz;window.addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(draw,120)});
const h0=location.hash.slice(1);cur=D.stocks[h0]?h0:D.default;list();draw();
"""
