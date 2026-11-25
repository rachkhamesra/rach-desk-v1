"""Static page: tabs, tables and an in-page chart. Everything is inline (no external requests), so it works on GitHub Pages or from a file."""
import shorts as shorts_mod
import patterns as patterns_mod
import sectors as sectors_mod
import html, json, re
import numpy as np, pandas as pd
import metrics
from guidance import validated_changes
import outlook

ARCHIVED_TABS = {"signals"}     # tab keys switched off. Remove "signals" from this set to bring Signal Confluence back.
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
    if "_next_result" not in M:
        today, nxt = M["dates"][-1].normalize(), {}
        for r in M.get("results", []):
            if r["event_date"].normalize() >= today and (r["symbol"] not in nxt or r["event_date"] < nxt[r["symbol"]]["event_date"]): nxt[r["symbol"]] = r
        M["_next_result"] = nxt
    event = M["_next_result"].get(s)
    result = ""
    if event:
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
        bucket = "unknown" if cap is None else "under5" if cap < 5000 else "5to10" if cap < 10000 else "10to20" if cap <= 20000 else "over20"
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
            '<div class="h52caps"><button class="h52cap on" data-mcap-filter="all">ALL</button><button class="h52cap" data-mcap-filter="under5">&lt; ₹5,000 CR</button>'
            '<button class="h52cap" data-mcap-filter="5to10">₹5,000–10,000 CR</button><button class="h52cap" data-mcap-filter="10to20">₹10,000–20,000 CR</button>'
            '<button class="h52cap" data-mcap-filter="over20">&gt; ₹20,000 CR</button></div>'
            f'{group(False)}</div>')


def _subtabs(items):
    return ('<div class="subtabs" role="group">' + "".join(
        f'<button type="button" class="subtab{" on" if i == 0 else ""}" data-sub="{k}" aria-pressed="{"true" if i == 0 else "false"}">{label}</button>' for i, (k, label) in enumerate(items)) + '</div>')


BASE_FILTER_BUTTONS = (
    '<div class="basefilters" role="group" aria-label="Breakout base filters">'
    '<button class="basefilter on" data-base-filter="range" aria-pressed="true"><i></i>NARROW RANGE ≤10%</button>'
    '<button class="basefilter on" data-base-filter="compression" aria-pressed="true"><i></i>VOLATILITY COMPRESSION</button>'
    '<button class="basefilter on" data-base-filter="trend" aria-pressed="true"><i></i>FLAT / RISING 50DMA</button>'
    '<button class="basefilter on" data-base-filter="touches" aria-pressed="true"><i></i>2+ RESISTANCE TESTS</button>'
    '<button class="basefilter on" data-base-filter="delivery" aria-pressed="true"><i></i>DELIVERY CONFIRMATION</button>'
    '<span class="basecount" aria-live="polite"></span></div>'
)


def tab_breakout_bases(M):
    frame = M.get("breakout_bases", pd.DataFrame())
    by_sym = sectors_mod.by_symbol(M.get("sector_clusters") or [])

    def card(row):
        symbol = row.sym; end = M["T"] + 1; start = max(0, end - 120)
        o, h, l, c = (M[key][symbol].iloc[start:end] for key in ("O", "H", "L", "C"))
        dq, rat = M["DQ"][symbol].iloc[start:end], M["RAT"][symbol].iloc[start:end]
        mas = {n: M["C"][symbol].rolling(n, min_periods=n).mean().iloc[start:end] for n in (50, 100, 200)}
        valid = pd.concat([l, h] + list(mas.values())).dropna(); lo, hi = valid.min(), valid.max()
        pad = (hi - lo) * .06 or max(abs(hi) * .02, 1); lo, hi = lo - pad, hi + pad
        width, price_top, price_h, delivery_top, delivery_h = 420, 10, 145, 177, 48
        xs = np.linspace(8, width - 8, len(c)); bw = max(1.4, (width - 16) / max(1, len(c)) * .62)
        py = lambda value: price_top + (1 - (value - lo) / (hi - lo)) * price_h
        candles = []
        for x, ov, hv, lv, cv in zip(xs, o, h, l, c):
            if any(pd.isna(v) for v in (ov, hv, lv, cv)): continue
            colour = "#24bd84" if cv >= ov else "#ef5a4d"; top, bottom = py(max(ov, cv)), py(min(ov, cv))
            candles.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{py(hv):.1f}" y2="{py(lv):.1f}" stroke="{colour}"/>'
                           f'<rect x="{x-bw/2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(1,bottom-top):.1f}" fill="{colour}"/>')
        def path(values, cls):
            parts, pen = [], False
            for x, value in zip(xs, values):
                if pd.isna(value): pen = False; continue
                parts.append(("L" if pen else "M") + f"{x:.1f},{py(value):.1f}"); pen = True
            return f'<path class="basechartline {cls}" d="{" ".join(parts)}"/>'
        max_dq = dq.max(skipna=True) or 1; bars = []
        for x, value, ratio in zip(xs, dq, rat):
            if pd.isna(value): continue
            height = value / max_dq * delivery_h
            bars.append(f'<rect class="basevol{(" hot" if pd.notna(ratio) and ratio >= 1.25 else "")}" x="{x-bw/2:.1f}" y="{delivery_top+delivery_h-height:.1f}" width="{bw:.1f}" height="{max(1,height):.1f}"/>')
        base_start = xs[max(0, len(xs) - int(row.base_days))] if len(xs) else 8
        stage_label = {"building": "BUILDING A BASE", "near": "NEAR BREAKOUT", "fresh": "FRESH BREAKOUT"}[row.stage]
        distance_label = f'{row.distance:+.1f}% to resistance' if row.distance >= 0 else f'{abs(row.distance):.1f}% above resistance'
        flags = {"range": bool(row.range_ok), "compression": bool(row.compression_ok), "trend": bool(row.trend_ok),
                 "touches": bool(row.touches_ok), "delivery": bool(row.delivery_ok)}
        attrs = ' '.join(f'data-{key}="{str(value).lower()}"' for key, value in flags.items())
        cl = by_sym.get(symbol); ctag = f'<span class="ptst {"up" if row.stage == "fresh" else "near"}" title="Stocks of the same kind of business that are near a breakout or through one">{esc(cl["group"]).upper()} · {len(cl["members"])} TOGETHER</span>' if cl else ""
        return (f'<article class="basecard" {attrs}><div class="basehead"><div><h3>{stk(symbol, M)}</h3><span class="basestage {esc(row.stage)}">{stage_label}</span> {ctag}</div>'
                f'<b>{distance_label}</b></div><svg class="basechart" viewBox="0 0 420 238" role="img" aria-label="Candlestick consolidation chart for {esc(symbol)}">'
                f'<rect class="basezone" x="{base_start:.1f}" y="{py(row.resistance):.1f}" width="{width-base_start-8:.1f}" height="{max(1,py(row.support)-py(row.resistance)):.1f}"/>'
                f'<line class="baseres" x1="{base_start:.1f}" x2="412" y1="{py(row.resistance):.1f}" y2="{py(row.resistance):.1f}"/>'
                f'<line class="basesup" x1="{base_start:.1f}" x2="412" y1="{py(row.support):.1f}" y2="{py(row.support):.1f}"/>'
                f'{"".join(candles)}{path(mas[50], "ma50")}{path(mas[100], "ma100")}{path(mas[200], "ma200")}'
                f'<line class="baseaxis" x1="8" x2="412" y1="{delivery_top+delivery_h:.1f}" y2="{delivery_top+delivery_h:.1f}"/>{"".join(bars)}</svg>'
                f'<div class="basestats"><span>BASE <b>{int(row.base_days)}D</b></span><span>RANGE <b>{row.range_width:.1f}%</b></span><span>TESTS <b>{int(row.touches)}</b></span>'
                f'<span>20D/60D ATR <b>{row.compression:.2f}×</b></span><span>DELIVERY DAYS <b>{int(row.delivery_days)}/10</b></span><span>5D DELIVERY <b>{row.delivery5:.2f}×</b></span></div>'
                '<div class="baselegend"><i class="candle"></i> CANDLES <i class="m50"></i> 50D <i class="m100"></i> 100D <i class="m200"></i> 200D · blue bars = ≥1.25× delivery</div></article>')

    def group(stage):
        subset = frame[frame.stage == stage].sort_values("score", ascending=False) if len(frame) else frame
        return ('<div class="basegrid">' + ''.join(card(row) for row in subset.head(60).itertuples()) + '</div>'
                if len(subset) else '<div class="card rempty">No F&amp;O stocks currently qualify for this stage.</div>')

    scan = (cluster_html(M, compact=True, charts=0) + '<p class="desc">All cards are in the upper quarter of a valid 40-, 60- or 90-session base. Turn individual quality filters on or off above; your choices are remembered on this device.</p>'
            '<div class="basetabs"><button class="basetab on" data-base="near">NEAR BREAKOUT</button><button class="basetab" data-base="fresh">FRESH BREAKOUT</button><button class="basetab" data-base="building">BUILDING A BASE</button></div>'
            f'<div class="basegroup" data-base-group="near">{group("near")}</div><div class="basegroup" data-base-group="fresh" hidden>{group("fresh")}</div>'
            f'<div class="basegroup" data-base-group="building" hidden>{group("building")}</div>')
    return ('<h2>Breakout Bases</h2><div class="subl">F&amp;O · CUSTOMISABLE CONSOLIDATION SCANNER</div>'
            + _subtabs([("scan", "SCANNER"), ("follow", "FOLLOW-THROUGH")]) + BASE_FILTER_BUTTONS
            + f'<div class="subview" data-sub="scan">{scan}</div><div class="subview" data-sub="follow" hidden>{tab_followthrough(M)}</div>')


def regime(M):
    """Where Nifty stands against its own 50 and 100-day averages, as a flag for how much a breakout should count: level 0 above both, 1 under the 50, 2 under the 100."""
    if "_regime" in M: return M["_regime"]
    n = M["nifty"].dropna() if M.get("nifty") is not None else []; out = None
    if len(n) >= 100:
        last = float(n.iloc[-1]); m50 = float(n.rolling(50).mean().iloc[-1]); m100 = float(n.rolling(100).mean().iloc[-1])
        lvl = 2 if last < m100 else 1 if last < m50 else 0
        text = {0: "Nifty is above its 50 and 100-day averages: breakouts have a supportive market behind them.",
                1: "Nifty is below its 50-day average: breakouts count for less than usual.",
                2: "Nifty is below its 100-day average: breakouts count for even less."}[lvl]
        out = dict(level=lvl, nifty=last, ma50=m50, ma100=m100, d50=(last / m50 - 1) * 100, d100=(last / m100 - 1) * 100, text=text,
                   label={0: "NIFTY ABOVE 50 & 100DMA", 1: "NIFTY BELOW 50DMA", 2: "NIFTY BELOW 100DMA"}[lvl])
    M["_regime"] = out
    return out


def regime_banner(M):
    g = regime(M)
    if not g: return ""
    cls = {0: "ok", 1: "caution", 2: "weak"}[g["level"]]
    return (f'<div class="regime {cls}"><b>{g["label"]}</b><span>{esc(g["text"])}</span>'
            f'<small class="mut">Nifty {g["nifty"]:,.0f} · {g["d50"]:+.1f}% from its 50-day ({g["ma50"]:,.0f}) · {g["d100"]:+.1f}% from its 100-day ({g["ma100"]:,.0f})</small></div>')


def regime_badge(M, status):
    g = regime(M)
    if not g or g["level"] == 0 or status != "BREAKOUT": return ""
    t = ("Nifty is below its 50-day average: a breakout counts for less" if g["level"] == 1 else "Nifty is below its 100-day average: a breakout counts for even less")
    return f'<span class="ptst {"near" if g["level"] == 1 else "down"}" title="{t}">{"NIFTY < 50DMA" if g["level"] == 1 else "NIFTY < 100DMA"}</span>'


def mini_chart(M, symbol, n=70, w=220, ph=82, dh=26):
    """A small chart of the last n sessions: candles with the 50, 100 and 200-day averages over delivered-share bars (blue when delivery is at least 1.25x its average), as on the Breakout Bases cards."""
    T = M["T"]; end = T + 1; start = max(0, end - n)
    if symbol not in M["C"]: return ""
    o, h, l, c = (M[k][symbol].iloc[start:end] for k in ("O", "H", "L", "C")); dq, rat = M["DQ"][symbol].iloc[start:end], M["RAT"][symbol].iloc[start:end]
    mas = {k: M["ma"][k][symbol].iloc[start:end] for k in (50, 100, 200) if k in M["ma"]}
    valid = pd.concat([l, h] + list(mas.values())).dropna()
    if len(c) < 10 or not len(valid): return ""
    lo, hi = float(valid.min()), float(valid.max()); pad = (hi - lo) * .06 or max(abs(hi) * .02, 1); lo -= pad; hi += pad
    top, gap = 3, 4; dtop = top + ph + gap; H = dtop + dh
    xs = np.linspace(3, w - 3, len(c)); bw = max(1.0, (w - 6) / max(1, len(c)) * .62); py = lambda v: top + (1 - (v - lo) / (hi - lo)) * ph
    g = []
    for x, ov, hv, lv, cv in zip(xs, o, h, l, c):
        if any(pd.isna(v) for v in (ov, hv, lv, cv)): continue
        col = "#24bd84" if cv >= ov else "#ef5a4d"
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{py(hv):.1f}" y2="{py(lv):.1f}" stroke="{col}" stroke-width=".8"/><rect x="{x - bw / 2:.1f}" y="{py(max(ov, cv)):.1f}" width="{bw:.1f}" height="{max(.8, abs(py(ov) - py(cv))):.1f}" fill="{col}"/>')
    for k, ser in mas.items():
        pts = [f"{x:.1f},{py(v):.1f}" for x, v in zip(xs, ser) if pd.notna(v)]
        if len(pts) > 1: g.append(f'<polyline class="basechartline ma{k}" points="{" ".join(pts)}"/>')
    mx = dq.max(skipna=True) or 1
    for x, v, r in zip(xs, dq, rat):
        if pd.isna(v): continue
        bh = max(.8, v / mx * (dh - 2)); g.append(f'<rect class="basevol{" hot" if pd.notna(r) and r >= 1.25 else ""}" x="{x - bw / 2:.1f}" y="{dtop + dh - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}"/>')
    return f'<svg class="minichart" viewBox="0 0 {w} {H}" role="img" aria-label="{esc(symbol)}: last {n} sessions with moving averages and delivery">{"".join(g)}</svg>'


def cluster_html(M, compact=False, limit=None, charts=None):
    """Sector clusters as cards: the group, how many of its stocks are near a breakout or through one, each member with its delivery, and one line on what delivery says for the group."""
    cl = sorted(M.get("sector_clusters") or [], key=lambda c: -len(c["members"]) * (c["avg5"] or 1)); rest = 0
    if not cl: return ""
    if limit and len(cl) > limit: rest = len(cl) - limit; cl = cl[:limit]
    cards = []
    for c in cl:
        n = len(c["members"])
        count = f'{c["n_near"]} NEAR BREAKOUT' + (f' · {c["n_broke"]} BROKE OUT' if c["n_broke"] else "")
        k = len(c["members"]) if charts is None else charts
        chips = "".join(
            f'<div class="tdmem {"up" if m["state"] == "BROKE OUT" else ""}"><div class="tdmh"><b>{stk(m["sym"], M)}</b><span class="ptst {"up" if m["state"] == "BROKE OUT" else "near"}">{"BROKE OUT" if m["state"] == "BROKE OUT" else "NEAR"}</span></div>'
            f'{mini_chart(M, m["sym"])}<span class="tdmd {"hotd" if (m["today"] or 0) >= 1.25 else ""}">{"–" if m["today"] is None else f"{m["today"]:.1f}×"} <small>today</small> · {"–" if m["five"] is None else f"{m["five"]:.1f}×"} <small>5D</small></span></div>'
            for m in c["members"][:k])
        names = c["members"][k:]
        if names:
            lead = "ALSO" if k else "MEMBERS"
            chips += ('<div class="tdmem tdmore"><span class="tdlab">' + lead + '</span>' + " ".join(
                f'<span class="tdnm">{stk(m["sym"], M)} <small class="{"up" if m["state"] == "BROKE OUT" else ""}">{"BROKE OUT" if m["state"] == "BROKE OUT" else "NEAR"}</small> <small class="{"hotd" if (m["today"] or 0) >= 1.25 else "mut"}">{"–" if m["today"] is None else f"{m["today"]:.1f}×"}</small></span>' for m in names) + '</div>')
        tone = {"ABOVE NORMAL": f'Delivery is <b>above normal</b> across the group: {c["hot"]} of {n} at or over 1.25× their own average today, {c["avg5"]:.1f}× on average over five sessions.' if c["avg5"] is not None else "",
                "NORMAL": f'Delivery is <b>about normal</b>: {c["hot"]} of {n} over 1.25× today, {c["avg5"]:.1f}× over five sessions on average. Price is leading, not volume.' if c["avg5"] is not None else "",
                "LIGHT": f'Delivery is <b>light</b>: {c["avg5"]:.1f}× over five sessions on average, {c["hot"]} of {n} over 1.25× today. A breakout here would be on thin participation.' if c["avg5"] is not None else "",
                "NO DATA": ""}[c["tone"]]
        cards.append(f'<article class="tdclus {c["tone"].lower().replace(" ", "")}"><div class="tdclh"><span class="tdtag">SECTOR CLUSTER · {n} STOCKS</span><h3>{esc(c["group"])}</h3><span class="tdclcount">{count}</span></div>'
                     f'<div class="tdmems">{chips}</div><p class="tdcltone">{tone}</p></article>')
    more = f'<p class="tdsmall"><span class="mut">{rest} more sector cluster{"s" if rest != 1 else ""}</span> <a class="tdlink" data-go="patterns">SEE ALL ON BREAKOUT BASES →</a></p>' if rest else ""
    return f'<div class="tdclusters{" compact" if compact else ""}">{"".join(cards)}</div>{more}'


def _breaks(M):
    """Fresh breakouts and breakdowns that came on high delivery, best first: those that broke on the latest session, then by conviction and by delivery multiple."""
    P = M.get("patterns") or {}; out = []
    for tf in ("daily", "weekly"):
        XX = P.get(tf)
        if not XX: continue
        for kind, _, _ in patterns_mod.KINDS:
            for r in XX["found"][kind]:
                x = r.get("brk_ratio")
                if r["status"] in ("BREAKOUT", "BREAKDOWN") and r.get("confirmed") and x is not None and not pd.isna(x): out.append((r, tf, kind))
    out.sort(key=lambda t: (t[0].get("event") != "BROKE", -t[0].get("conv", 0), -t[0]["brk_ratio"]))
    return out


def today_data(M):
    """The three pattern charts the Today page draws in the browser (the stock's candles are only loaded there): which stock, and which of its patterns."""
    if "_today" in M: return M["_today"]
    br = _breaks(M); pick = []
    for want in ("BREAKOUT", "BREAKDOWN"):
        for r, tf, kind in br:
            if r["status"] == want and r["sym"] not in [p["s"] for p in pick]:
                pick.append(dict(s=r["sym"], k=kind, tf=tf[0], st=want)); break
    M["_today"] = dict(focus=pick)
    return M["_today"]


def _spark(vals, colour="#e8a93a", w=220, h=46):
    v = [float(x) for x in vals if x is not None and not pd.isna(x)]
    if len(v) < 3: return ""
    lo, hi = min(v), max(v); span = (hi - lo) or 1
    pts = " ".join(f"{i * (w - 4) / (len(v) - 1) + 2:.1f},{h - 4 - (x - lo) / span * (h - 8):.1f}" for i, x in enumerate(v))
    return (f'<svg class="tdspark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true"><polyline points="{pts} {w - 2},{h} 2,{h}" fill="{colour}" opacity=".13"/>'
            f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="1.8" stroke-linejoin="round"/><circle cx="{w - 2}" cy="{h - 4 - (v[-1] - lo) / span * (h - 8):.1f}" r="2.6" fill="{colour}"/></svg>')


def _nice(name):
    return name.replace("BSE", "BSE").replace("MCX", "MCX").capitalize().replace("Bse", "BSE").replace("Mcx", "MCX")


def _pace(now, before):
    if not before: return "", ""
    d = (now / before - 1) * 100
    return f"{d:+.0f}%".replace("-", MINUS), "pup" if d >= 0 else "pdn"


def tab_today(M):
    """The landing page: a headline, the three charts worth a look, what exchange and power activity says, the short ideas, one call, and the rest of what is new."""
    br = _breaks(M); focus = today_data(M)["focus"]; date = M["dates"][-1]
    nifty = M["nifty"].dropna(); nchg = (nifty.iloc[-1] / nifty.iloc[-2] - 1) * 100 if len(nifty) > 1 else None
    ups = [t for t in br if t[0]["status"] == "BREAKOUT"]; downs = [t for t in br if t[0]["status"] == "BREAKDOWN"]
    X = M.get("shorts") or {}; conf = X.get("confluence"); newshort = {}
    for k, v in (X.get("screens") or {}).items():
        for r in v["rows"].itertuples():
            if getattr(r, "new", False) and bool(getattr(r, "fo", True)): newshort.setdefault(r.sym, []).append(v["title"])
    multi = conf[conf["count"] >= 2] if conf is not None and len(conf) else None
    cash = M.get("cash_accumulation"); newcash = cash[cash["new"]] if cash is not None and len(cash) and "new" in cash else None
    bases = M.get("breakout_bases"); fresh = bases[bases["stage"] == "fresh"].sort_values("score", ascending=False) if bases is not None and len(bases) else None
    kinds = {k: t for k, t, _ in patterns_mod.KINDS}

    def why(r, tf, kind):
        unit = "weeks" if tf == "weekly" else "sessions"; way = "broke out of" if r["status"] == "BREAKOUT" else "broke down from"
        t = f'{esc(r["sym"])} {way} a {r["days"]}-{unit[:-1]} {kinds[kind].lower()} on <b>{r["brk_ratio"]:.1f}×</b> its normal delivery'
        return f'{t}. Conviction {int(r.get("conv", 0))} of 5 · target {r["target"]:,.0f} ({(r["target"] / r["close"] - 1) * 100:+.0f}%) · {r["touches_flat"]} touches on the flat side.'

    lead = ups[0] if ups else (downs[0] if downs else None)
    headline = (f'<b>{len(ups)}</b> breakouts and <b>{len(downs)}</b> breakdowns came through on above-normal delivery' + (f', led by <b>{esc(lead[0]["sym"])}</b>' if lead else "")
                + (f'. <b>{esc((M.get("sector_clusters") or [{}])[0]["group"])}</b> is a sector cluster: <b>{len((M.get("sector_clusters") or [{}])[0]["members"])}</b> of its stocks are near a breakout together' if M.get("sector_clusters") else "")
                + f'. <b>{len(newshort)}</b> stocks are newly flagged as short ideas and <b>{0 if newcash is None else len(newcash)}</b> began cash accumulation.')
    tile = lambda big, lab, cls="": f'<div class="tdtile"><b class="{cls}">{big}</b><span>{lab}</span></div>'
    tiles = (tile(pc(nchg, 2) if nchg is not None else "–", "NIFTY TODAY", "pup" if (nchg or 0) >= 0 else "pdn") + tile(str(len(ups)), "HIGH-DELIVERY BREAKOUTS", "pup") + tile(str(len(downs)), "HIGH-DELIVERY BREAKDOWNS", "pdn")
             + tile(str(len(newshort)), "NEW SHORT IDEAS") + tile("–" if newcash is None else str(len(newcash)), "NEW CASH ACCUMULATION") + tile("–" if fresh is None else str(len(fresh)), "FRESH BASES"))
    hero = (f'<section class="tdhero"><div class="tdkick">{date:%A · %d %B %Y}</div><h1>What is moving<br>in the market.</h1><p class="tdlead">{headline}</p>{regime_banner(M)}<div class="tdtiles">{tiles}</div></section>')

    clus = cluster_html(M, limit=5, charts=3)
    clus_html = (f'<section class="tdsec"><div class="tdsech"><h2>Sector clusters</h2><span class="mut">Several stocks of one kind of business near a breakout together. Charts for the strongest three in each; the rest by name</span></div>{clus}</section>' if clus else "")
    # three charts to focus on: the best breakout and breakdown (drawn in the browser) and the strongest short idea
    cards = []
    for f in focus:
        r, tf, kind = next((t for t in br if t[0]["sym"] == f["s"] and t[0]["status"] == f["st"] and kinds[t[2]] == kinds[f["k"]]), (None, None, None))
        if r is None: continue
        up = r["status"] == "BREAKOUT"
        cards.append(f'<article class="tdfocus {"up" if up else "down"}" data-s="{esc(f["s"])}" data-k="{f["k"]}" data-tf="{f["tf"]}" data-st="{f["st"]}"><div class="tdfh"><span class="tdtag">{"BREAKOUT" if up else "BREAKDOWN"} · {tf.upper()}</span>{regime_badge(M, r["status"])}'
                     f'<h3>{stk(f["s"], M)}</h3></div><div class="tdchart"></div><p>{why(r, tf, kind)}</p></article>')
    if multi is not None and len(multi) and X.get("charts"):
        row = multi.iloc[0]; titles = {k: t for k, t, _ in shorts_mod.SCREENS}
        card = short_cards([row.sym], M, X, lambda sym: list(row.screens), cap=1)
        card = re.sub(r'<div class="shlegend">.*?</div>', "", card, count=1, flags=re.S)
        cards.append(f'<article class="tdfocus short"><div class="tdfh"><span class="tdtag">SHORT IDEA · {int(row["count"])} SCREENS AGREE</span></div>{card}'
                     f'<p>{esc(row.sym)} is flagged by <b>{" · ".join(esc(titles[k].title()) for k in row.screens)}</b>. Agreement between screens that read different things is the closest the page gets to conviction. A screen, not a recommendation.</p></article>')
    focus_html = (f'<section class="tdsec"><div class="tdsech"><h2>Three charts worth a look</h2><span class="mut">The best high-delivery break each way and the strongest short idea</span></div><div class="tdfocusgrid">{"".join(cards)}</div></section>' if cards else "")

    # exchange and power activity
    tiles2 = []
    XB = M.get("exchange_tracker") or {}
    if XB.get("available"):
        s_ = XB["series"]; r5 = s_["roll5"].iloc[-1]; r5b = s_["roll5"].iloc[-6] if len(s_) > 6 else None; d, c = _pace(r5, r5b)
        tiles2.append(('BSE OPTIONS', f'₹{r5:,.0f} cr', f'5-session average per day <b class="{c}">{d}</b> against five sessions ago. {esc(XB["commentary"][2]) if len(XB.get("commentary", [])) > 2 else ""}', _spark(s_["roll5"].tail(80)), f'As of {XB["asof"]:%d %b %Y}', d, c, "exchange"))
    XM = M.get("mcx_tracker") or {}
    if XM.get("available"):
        s_ = XM["series"]; r5 = s_["roll5"].iloc[-1]; r5b = s_["roll5"].iloc[-6] if len(s_) > 6 else None; d, c = _pace(r5, r5b)
        tiles2.append(('MCX OPTIONS', f'₹{r5:,.0f} cr', f'5-session average per day <b class="{c}">{d}</b> against five sessions ago. {esc(XM["commentary"][1]) if len(XM.get("commentary", [])) > 1 else ""}', _spark(s_["roll5"].tail(80), "#6db0ff"), f'Latest verified {XM["asof"]:%d %b %Y}', d, c, "exchange"))
    PW = M.get("power") or {}; ser = (PW.get("series") or {}).get("ALL")
    if ser:
        ys = sorted(ser["years"]); cur, prev = ser["years"][ys[-1]], ser["years"][ys[-2]] if len(ys) > 1 else None
        cur = [x for x in cur]; k = len([x for x in cur if x is not None]); win = [x for x in cur[max(0, k - 14):k] if x is not None]
        if win and prev:
            pw = [x for x in prev[max(0, k - 14):k] if x is not None]; d, c = _pace(sum(win) / len(win), sum(pw) / len(pw) if pw else None)
            iex = (PW.get("iex") or {}).get("latest") or {}
            tiles2.append(('POWER GENERATION', f'{sum(win) / len(win):,.0f} MU/day', f'Last 14 days <b class="{c}">{d}</b> against the same days last year. Data through {esc(PW["asof"])}.', _spark(cur[max(0, k - 80):k], "#4fd18b"), "All conventional + hydro generation", d, c, "alt"))
    cons = ""
    if len(tiles2) >= 2:
        hot = [(n, d) for n, _, _, _, _, d, c, _ in tiles2 if c == "pup"]; cool = [(n, d) for n, _, _, _, _, d, c, _ in tiles2 if c == "pdn"]
        cons = ("<p class=\"tdcons\">" + (f'Running hotter: <b>{", ".join(_nice(n) for n, _ in hot)}</b>. ' if hot else "") + (f'Running cooler: <b>{", ".join(_nice(n) for n, _ in cool)}</b>. ' if cool else "")
                + "Each is the recent average against five sessions ago (power: against the same days last year), so it reads direction, not level.</p>")
    t2 = "".join(f'<a class="tdact" data-go="{go}"><span class="tdlab">{n}</span><b class="tdbig">{big}</b><span class="tdmeta {c}">{d}</span>{sp}<p>{txt}</p><small class="mut">{foot}</small></a>' for n, big, txt, sp, foot, d, c, go in tiles2)
    act_html = f'<section class="tdsec"><div class="tdsech"><h2>Activity across exchanges and power</h2><span class="mut">BSE and MCX options premium turnover, and power generation</span></div><div class="tdactgrid">{t2}</div>{cons}</section>' if tiles2 else ""

    # short ideas
    chips = ""
    if multi is not None and len(multi):
        titles = {k: t for k, t, _ in shorts_mod.SCREENS}
        chips = "".join(f'<div class="tdchip"><b>{stk(r.sym, M)}</b><span class="mut">{" · ".join(esc(titles[k].title()) for k in r.screens)}</span></div>' for r in multi.head(8).itertuples())
    newchips = " ".join(f'<span class="tdpill">{stk(s_, M)}</span>' for s_ in list(newshort)[:14])
    short_html = ('<section class="tdsec"><div class="tdsech"><h2>Short ideas</h2><a class="tdlink" data-go="patterns">OPEN SHORT IDEAS →</a></div>'
                  + (f'<div class="tdchips">{chips}</div>' if chips else '<p class="mut">No F&amp;O stock is flagged by two screens today.</p>')
                  + (f'<p class="tdsmall"><span class="mut">NEW TODAY</span> {newchips}{" and " + str(len(newshort) - 14) + " more" if len(newshort) > 14 else ""}</p>' if newshort else "") + '</section>')

    # one call
    call_html = ""
    avail = sorted(((s_, c) for s_, c in M.get("calls", {}).items() if c.get("analysis")), key=lambda x: x[1].get("filed_at", ""), reverse=True)
    if avail:
        s_, c = avail[0]; a = c["analysis"]; lab = outlook.classify(a, ()).get("label", "")
        pts = a.get("next_quarter_outlook") or []; pt = pts[0] if pts else None; foc = (a.get("analyst_focus") or [None])[0]; risk = (a.get("key_risks") or [None])[0]
        call_html = ('<section class="tdsec"><div class="tdsech"><h2>From a call</h2><a class="tdlink" data-go="calls">OPEN THE CALL LIBRARY →</a></div>'
                     f'<div class="tdcall"><div class="tdcallh"><h3>{stk(s_, M)} <span class="mut">{esc(c.get("company_name", ""))}</span></h3><span class="tdlab">{esc(a.get("call_period", ""))} · {esc(lab.upper())}</span></div>'
                     + (f'<blockquote><b>{esc(pt["topic"])}</b><br>{esc(pt.get("summary", ""))}<cite>{esc(pt.get("speaker", ""))}, {esc(pt.get("role", ""))}</cite></blockquote>' if pt else "")
                     + '<div class="tdcallf">' + (f'<div><span class="tdlab">ANALYSTS PRESSED ON</span>{esc(foc["topic"])}</div>' if foc else "") + (f'<div><span class="tdlab">KEY RISK</span>{esc(risk)}</div>' if risk else "") + '</div></div></section>')

    # the rest
    def pills(items): return " ".join(f'<span class="tdpill">{x}</span>' for x in items)
    cashp = [f'{stk(r.sym, M)} <span class="mut">{int(r.days)}D · {r.ratio:.1f}×</span>' for r in newcash.itertuples()] if newcash is not None and len(newcash) else []
    basep = [f'{stk(r.sym, M)} <span class="mut">{int(r.base_days)}D base</span>' for r in fresh.head(12).itertuples()] if fresh is not None and len(fresh) else []
    morebr = [f'{stk(r["sym"], M)} <span class="mut">{kinds[k].title()} · {tf} · {r["brk_ratio"]:.1f}×</span>' for r, tf, k in br[:40] if r["sym"] not in [f["s"] for f in focus]][:14]
    rest = ('<section class="tdsec"><div class="tdsech"><h2>Also new today</h2></div><div class="tdrest">'
            f'<div><span class="tdlab">MORE HIGH-DELIVERY BREAKS</span><p>{pills(morebr) or "<span class=mut>None today.</span>"}</p><a class="tdlink" data-go="patterns">ALL OF THEM →</a></div>'
            f'<div><span class="tdlab">NEW CASH ACCUMULATION</span><p>{pills(cashp) or "<span class=mut>None today.</span>"}</p><a class="tdlink" data-go="cash">OPEN →</a></div>'
            f'<div><span class="tdlab">FRESH BREAKOUT BASES</span><p>{pills(basep) or "<span class=mut>None today.</span>"}</p><a class="tdlink" data-go="patterns">OPEN →</a></div>'
            '<div><span class="tdlab">YOUR WATCHLIST</span><div id="today-wl" class="ptwl"></div></div></div></section>')
    return f'<div class="today">{hero}{focus_html}{act_html}{short_html}{clus_html}{call_html}{rest}</div>'


def tab_timeline(M):
    """How the page evolved: a strip of numbers, the commit activity, what was removed, and the timeline itself, phase by phase."""
    T = M.get("timeline")
    if not T: return '<h2>Timeline</h2><div class="card rempty">The timeline is not available in this build.</div>'
    st = T["stats"]; kinds = dict(T["kinds"]); repo = T.get("repo", "")
    days = (pd.Timestamp(M["dates"][-1]).normalize() - pd.Timestamp(st["first"])).days + 1
    tile = lambda big, lab: f'<div class="tdtile"><b>{big}</b><span>{lab}</span></div>'
    tiles = (tile(f"{days}", "DAYS FROM THE FIRST COMMIT") + tile("–" if st["prs"] is None else str(st["prs"]), "PULL REQUESTS MERGED") + tile("–" if st["commits"] is None else str(st["commits"]), "COMMITS")
             + tile(str(M.get("_ntabs", "–")), "TABS TODAY") + tile(str(M["N"]), "SESSIONS OF HISTORY") + tile(str(st["removed"]), "THINGS TAKEN OUT"))
    act = _timeline_activity(T)
    gone = "".join(f'<li><a data-tl="{i}">{esc(n["title"])}</a> <span class="mut">{pd.Timestamp(n["date"]):%d %b}</span></li>' for i, n in _tl_nodes(T) if n["kind"] == "removed")
    filters = '<button type="button" class="tlfilter on" data-k="all">ALL</button>' + "".join(f'<button type="button" class="tlfilter" data-k="{k}">{lab}</button>' for k, lab in T["kinds"])
    blocks = []
    idx = 0
    for ph in T["phases"]:
        if not ph["nodes"]: continue
        items = []
        for n in ph["nodes"]:
            prs = "".join(f'<a class="tlpr" href="https://github.com/{esc(repo)}/pull/{p}" target="_blank" rel="noopener">#{p}</a>' if repo else f'<span class="tlpr">#{p}</span>' for p in n.get("prs", [])[:6])
            more = f'<span class="tlpr mut">+{len(n["prs"]) - 6}</span>' if len(n.get("prs", [])) > 6 else ""
            body = (f'<p class="tlwhat">{esc(n["what"])}</p>' if n.get("what") else "") + (f'<div class="tlwhy"><span>{"WHAT IT SHOWED" if n["kind"] != "removed" else "WHY IT WENT"}</span>{esc(n["insight"])}</div>' if n.get("insight") else "")
            tabchip = f'<span class="tltab">{esc(n["tab"])}</span>' if n.get("tab") else ""
            items.append(f'<li class="tlnode k-{n["kind"]}{" auto" if n.get("auto") else ""}" data-k="{n["kind"]}" id="tl-{idx}"><i class="tldot"></i><div class="tlcard"><div class="tlmeta"><time>{pd.Timestamp(n["date"]):%d %b %Y}</time>'
                         f'<span class="tlkind k-{n["kind"]}">{esc(kinds.get(n["kind"], n["kind"].upper()))}</span>{tabchip}</div>'
                         f'<h4>{esc(n["title"])}</h4>{body}<div class="tlprs">{prs}{more}</div></div></li>')
            idx += 1
        blocks.append(f'<section class="tlphase" data-phase="{esc(ph["key"])}"><header><span class="tlspan">{esc(ph["span"])}</span><h3>{esc(ph["label"])}</h3><p>{esc(ph["blurb"])}</p><span class="tlcount mut">{len(ph["nodes"])} CHANGE{"S" if len(ph["nodes"]) != 1 else ""}</span></header><ol class="tl">{"".join(items)}</ol></section>')
    return ('<div class="timeline"><section class="tdhero tlhero"><div class="tdkick">THE BUILD LOG, READ AS A STORY</div><h1>How this page<br>got here.</h1>'
            '<p class="tdlead">From a single cash-market screen to a briefing page: what was added, what was tried and taken out, and what each step showed. New changes appear here as they are merged.</p>'
            f'<div class="tdtiles">{tiles}</div></section>'
            f'<section class="tdsec"><div class="tdsech"><h2>Activity</h2><span class="mut">Commits per day; the first week was transcript batches, the later peaks are the larger features</span></div>{act}</section>'
            + (f'<section class="tdsec"><div class="tdsech"><h2>Taken out along the way</h2><span class="mut">Removing things is part of the history</span></div><ul class="tlgone">{gone}</ul></section>' if gone else "")
            + f'<section class="tdsec"><div class="tdsech"><h2>Timeline</h2><div class="tlfilters" role="group" aria-label="Filter by kind of change">{filters}</div></div>{"".join(blocks)}</section></div>')


def _tl_nodes(T):
    out, i = [], 0
    for ph in T["phases"]:
        for n in ph["nodes"]: out.append((i, n)); i += 1
    return out


def _timeline_activity(T):
    """Bars of commits per calendar day between the first commit and the last, with the start of each phase marked."""
    a = T.get("activity") or []
    if not a: return '<p class="mut">The commit history is not available in this build.</p>'
    days = pd.date_range(a[0][0], a[-1][0]); counts = {d: c for d, c in a}
    vals = [counts.get(f"{d:%Y-%m-%d}", 0) for d in days]; mx = max(vals) or 1; w, h, l, b = 1000, 96, 4, 20; bw = (w - l * 2) / len(vals)
    bars = "".join(f'<rect x="{l + i * bw:.1f}" y="{h - b - v / mx * (h - b - 6):.1f}" width="{max(1, bw - 3):.1f}" height="{max(0, v / mx * (h - b - 6)):.1f}" fill="#e8a93a" opacity=".85"><title>{d:%d %b}: {v} commit{"s" if v != 1 else ""}</title></rect>' for i, (d, v) in enumerate(zip(days, vals)) if v)
    marks, legend, k = "", [], 0
    for ph in T["phases"]:
        if ph["key"] == "latest" or not ph["nodes"]: continue
        k += 1; d0 = pd.Timestamp(ph["nodes"][0]["date"]); i = (d0 - days[0]).days
        marks += f'<line x1="{l + i * bw:.1f}" x2="{l + i * bw:.1f}" y1="0" y2="{h - b}" stroke="#444" stroke-dasharray="2 3"/><text x="{l + i * bw + 3:.1f}" y="{h - 6}" fill="#ffd17a" font-size="11" font-weight="700" font-family="monospace">{k}</text>'
        legend.append(f'<span><b>{k}</b> {esc(ph["label"])}</span>')
    return f'<svg class="tlactivity" viewBox="0 0 {w} {h}" role="img" aria-label="Commits per day">{marks}{bars}</svg><div class="tllegend mut">{"".join(legend)}</div>'


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

    def bars(df, label, value, colour, current=False, month_axis=False, comparison=None, avg=None, w=560, h=250, note=None):
        l, top, bot = 40, 18, 52
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
        if avg is not None and pd.notna(avg):
            ya = h - bot - float(avg) / mx * (h - top - bot)
            out.append(f'<line x1="{l}" x2="{w-8}" y1="{ya:.1f}" y2="{ya:.1f}" stroke="#ffd17a" stroke-dasharray="4 3" stroke-width="1.2"/><text x="{w-12}" y="{ya-4:.1f}" text-anchor="end" fill="#ffd17a" font-size="9">AVERAGE ₹{avg:,.0f}cr</text>')
        annotation_text = note or X.get("comparison_annotation", "VS YTD AVG")
        annotation = "" if comparison is None or pd.isna(comparison) else f'<text class="excompare {"up" if comparison >= 0 else "down"}" x="{w-12}" y="{top+10}" text-anchor="end">LATEST {comparison:+.0f}% {esc(annotation_text)}</text>'
        return f'<svg class="exsvg" viewBox="0 0 {w} {h}" role="img"><line x1="{l}" y1="{h-bot}" x2="{w-8}" y2="{h-bot}"/>' + "".join(out) + annotation + '</svg>'

    def weekday_card():
        full = X["series"][["date", "premium_turnover_cr"]].dropna().copy(); full["date"] = pd.to_datetime(full["date"]); full["wd"] = full.date.dt.day_name()
        if len(full) < 10: return ""
        periods = [("ytd", "YTD", end.replace(month=1, day=1)), ("6m", "LAST 6 MONTHS", end - pd.DateOffset(months=6)), ("all", "ALL HISTORY", full.date.min())]
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]; default = X["weekday"] if X["weekday"] in days else "Wednesday"
        views = []
        for pk, _, start in periods:
            win = full[full.date >= start]
            avgs = win.groupby("wd")["premium_turnover_cr"].mean()
            for d in days:
                df = win[win.wd == d].copy()
                shown = (d == default and pk == "ytd")
                if len(df) < 2:
                    body = f'<div class="mut pnote">Fewer than two {d}s in this window.</div>'
                else:
                    df["label"] = df.date.dt.strftime("%d %b %y"); av = float(df.premium_turnover_cr.mean()); last_v = float(df.premium_turnover_cr.iloc[-1])
                    prior = df.premium_turnover_cr.iloc[:-1].mean(); chg = (last_v / prior - 1) * 100 if prior else np.nan
                    hi, lo = df.loc[df.premium_turnover_cr.idxmax()], df.loc[df.premium_turnover_cr.idxmin()]
                    strip = " · ".join((f"<b>{x[:3]} ₹{avgs[x]:,.0f}</b>" if x == d else f"{x[:3]} ₹{avgs[x]:,.0f}") for x in days if x in avgs.index)
                    body = (bars(df, "label", "premium_turnover_cr", "exbar", True, True, chg, avg=av, w=1000, h=260, note=f"VS EARLIER {d.upper()[:3]} AVG")
                            + f'<div class="msum">{len(df)} {d}s · average <b>₹{av:,.0f} cr</b> · median ₹{df.premium_turnover_cr.median():,.0f} cr · highest ₹{hi.premium_turnover_cr:,.0f} cr ({hi.date:%d %b %y}) · lowest ₹{lo.premium_turnover_cr:,.0f} cr ({lo.date:%d %b %y}) · '
                              f'last {df.date.iloc[-1]:%d %b %y} ₹{last_v:,.0f} cr ({chg:+.0f}% vs the earlier {d} average)</div>'
                            + f'<div class="msum">Average by weekday in this window: {strip}</div>')
                views.append(f'<div class="wdview" data-wd="{d}" data-wp="{pk}"{"" if shown else " hidden"}>{body}</div>')
        opts_d = "".join(f'<option{" selected" if d == default else ""}>{d}</option>' for d in days)
        opts_p = "".join(f'<option value="{k}">{lbl}</option>' for k, lbl, _ in periods)
        return (f'<div class="exwdwrap"><div class="card excard exwd"><div class="ch"><span class="ct">ANY WEEKDAY</span><span class="exwdctl"><label>Day <select class="exsel wdsel">{opts_d}</select></label>'
                f'<label>Window <select class="exsel wdper">{opts_p}</select></label></span></div>{"".join(views)}</div></div>')

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
            f'{status_html}'
            f'<div class="exlayout"><div class="card excard exmain"><div class="ch"><span class="ct">5D ROLLING PREMIUM TURNOVER</span><span><i class="exkey to"></i>5D premium <i class="exkey px"></i>{esc(price_label)}</span></div>{hero_ranges}</div>'
            f'<div class="card excard"><div class="ch"><span class="ct">{esc(X.get("comparison_title", X["weekday"].upper() + "S · YTD"))}</span><span class="mut">{len(comparison)} {esc(X.get("comparison_count_label", "SESSIONS"))}</span></div>{bars(comparison,"label","premium_turnover_cr","exbar",True,X.get("comparison_month_axis", True),comparison_change)}</div>'
            f'<div class="card excard"><div class="ch"><span class="ct">AVERAGE DAILY PREMIUM TURNOVER</span><span class="mut">CURRENT MONTH IS PARTIAL</span></div>{bars(monthly,"label","mean","exbar month",True)}</div>'
            f'<div class="exranges exrangesbelow">{range_buttons}</div></div>'
            f'<div class="card excomment"><h3>DAILY READ</h3><ul>{comments}</ul><a href="{esc(X["source"])}" target="_blank" rel="noopener">{esc(source_label)} ↗</a></div>'
            f'{weekday_card()}'
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
def fl_detail(r, kind, unit):
    lvl = f'{r["bottom"]:,.0f} to {r["top"]:,.0f}' if kind == "rectangle" else f'{r["level"]:,.0f}'
    return (f'{r["status"]} · {"range" if kind == "rectangle" else "resistance" if kind == "ascending" else "support"} {lvl} · {r["touches_flat"]} touches on the flat side, {r["touches_line"]} on the other · '
            f'{r["height_pct"]:.0f}% tall · {r["days"]} {unit} · target {r["target"]:,.0f} ({(r["target"] / r["close"] - 1) * 100:+.0f}%)')


def lazy_panel(k, html):
    """A panel's HTML held as inert text (not parsed into the DOM) until its tab is first opened. `</script` and `<!--` would end or confuse a script element, so they are escaped here and
    the page undoes it when it fills the panel in."""
    return f'<script type="text/plain" id="lazy-{k}">{html.replace("</script", "<\\/script").replace("<!--", "<\\!--")}</script>'


def screen_flags(M):
    """{symbol: {"fl": [...], "pt": [...]}}: every screen and pattern that flags the stock today, for the stock page.
    fl items: g group, l label, t tone (up/down/near/mut), d detail, tab and sub (where to jump), tf (pattern timeframe). pt items are pattern geometry in daily-session coordinates."""
    out = {}
    add = lambda sym, **kw: out.setdefault(sym, {"fl": [], "pt": []})["fl"].append(kw)
    tone = {"BREAKOUT": "up", "BREAKDOWN": "down", "SETUP": "near", "AT TOP": "near", "AT BOTTOM": "near", "FORMING": "mut", "IN RANGE": "mut"}
    P = M.get("patterns") or {}
    for tf in ("daily", "weekly"):
        X = P.get(tf)
        if not X: continue
        for kind, title, _ in patterns_mod.KINDS:
            for r in X["found"][kind]:
                add(r["sym"], g="pattern", l=f'{title} · {tf.upper()}', t=tone.get(r["status"], "mut"), st=r["status"] + (" · HIGH DELIVERY" if r.get("confirmed") else ""), tab="patterns", sub=kind, tf=tf, d=fl_detail(r, kind, X["cfg"].unit), ev=r.get("event"))
                g = r["daily"]
                out[r["sym"]]["pt"].append(dict(tf=tf[0], k=kind, st=r["status"], lines=g["lines"], th=g["touches"], tg=g["target"], br=g["brk"], d=fl_detail(r, kind, X["cfg"].unit),
                                                 cf=bool(r.get("confirmed")), bx=None if pd.isna(r.get("brk_ratio", np.nan)) else round(float(r["brk_ratio"]), 1)))
    for c in (M.get("sector_clusters") or []):
        for m in c["members"]:
            others = ", ".join(x["sym"] for x in c["members"] if x["sym"] != m["sym"])
            add(m["sym"], g="sector", l=f'SECTOR CLUSTER · {c["group"].upper()}: {len(c["members"])} NEAR OR THROUGH A BREAKOUT', t="up" if m["state"] == "BROKE OUT" else "near", tab="patterns", sub="bases",
                d=f'with {others}. Delivery across the group: {c["tone"].lower()}' + ("" if c["avg5"] is None else f' ({c["avg5"]:.1f}× its average over five sessions)'), ev=None)
    sh = M.get("shorts")
    for key, v in ((sh or {}).get("screens") or {}).items():
        for r in v["rows"].itertuples():
            add(r.sym, g="short", l=f'SHORT IDEAS · {v["title"]}', t="down", tab="patterns", sub="shorts", sub2=key, d=(f'broke the 200-day average {int(r.days)} sessions ago on {r.brk_ratio:.1f}× delivery, fell {abs(r.depth):.0f}% under it, now {r.dist:+.1f}% from it' if key == "retest" else f'flagged {int(r.days)} session{"s" if r.days != 1 else ""}'), ev="NEW" if getattr(r, "new", False) else None)
    for df, lab, tn in ((M.get("cash_accumulation"), "CONFIRMED", "up"), (M.get("cash_tracking"), "TRACKING", "near")):
        for r in (df.itertuples() if df is not None and len(df) else []):
            add(r.sym, g="cash", l=f"CASH ACCUMULATION · {lab}", t=tn, tab="cash", sub="", d=f"{int(r.days)} setup days · delivery {r.ratio:.2f}× its 20-day average", ev="NEW" if getattr(r, "new", False) else None)
    for r in (M["breakout_bases"].itertuples() if len(M.get("breakout_bases", [])) else []):
        add(r.sym, g="base", l=f"BREAKOUT BASE · {str(r.stage).upper()}", t="up" if str(r.stage) == "fresh" else "near", tab="patterns", sub="bases", d="")
    for r in (M["high52"].itertuples() if len(M.get("high52", [])) else []):
        add(r.sym, g="high", l="52-WEEK HIGH", t="up", tab="high52", sub="", d=f"{r.close_from_high:+.1f}% from the high" if pd.notna(r.close_from_high) else "")
    return out


def oi_series(ser):
    """Open interest per session, or an empty list for a stock that has none (most of them): the page treats a missing entry as no data."""
    vals = [None if pd.isna(x) else int(x) for x in ser]
    return vals if any(v is not None for v in vals) else []


def stocks_json(M):
    dates = [f"{d:%Y-%m-%d}" for d in M["dates"]]; out = {}; T = M["T"]
    ev = M["events"]; di = {d: i for i, d in enumerate(M["dates"])}
    upcoming = {}
    for r in M.get("results", []):
        if r["event_date"].normalize() < M["dates"][-1].normalize(): continue
        old = upcoming.get(r["symbol"])
        if old is None or r["event_date"] < old["event_date"]: upcoming[r["symbol"]] = r
    nz = lambda x, f=float: None if x is None or pd.isna(x) else f(x)
    def ohl(series, close):
        """Open, high or low as whole paise away from the close (the page adds the close back): about half the bytes of three more price series."""
        return [None if pd.isna(a) or pd.isna(c) else int(round((round(float(a), 2) - round(float(c), 2)) * 100)) for a, c in zip(series, close)]
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
            changes = validated_changes(call["analysis"], call.get("source_url"))
            call = {**call, "analysis": {**call["analysis"], "material_guidance_changes": changes}, "outlook": outlook.classify(call["analysis"], changes)}
        closes = [nz(x, lambda v: round(float(v), 2)) for x in M["C"][s]]
        heavy = dict(c=closes, o=ohl(M["O"][s], M["C"][s]), h=ohl(M["H"][s], M["C"][s]), l=ohl(M["L"][s], M["C"][s]), dq=[nz(x, int) for x in M["DQ"][s]], oi=oi_series(M["OIadj"][s]))
        sm["last"] = next((v for v in reversed(closes) if v is not None), None)
        out[s] = dict(a=json.dumps(heavy, separators=(",", ":")),             # the price, delivery and open-interest arrays as one string: the page parses it only when the stock is opened
                      sm=sm,
                      result=None if result is None else dict(date=f'{result["event_date"]:%Y-%m-%d}', status=result["status"], purpose=result.get("purpose", ""),
                                                              period=result.get("period", ""), url=result.get("source_url") or ""), at=at, call=call,
                      ev=[[di[e["date"]], round(float(e["factor"]), 4), e["decision"]] for _, e in ev[ev["symbol"] == s].iterrows() if e["date"] in di and e["decision"] in ("auto", "accepted")])
    for sym, extra in screen_flags(M).items():
        if sym in out: out[sym]["fl"] = extra["fl"]; out[sym]["pt"] = extra["pt"]
    for r in M.get("breakout_bases", pd.DataFrame()).itertuples():
        if r.sym in out: out[r.sym]["bs"] = [r.stage, int(sum(bool(getattr(r, f)) for f in ("range_ok", "compression_ok", "trend_ok", "touches_ok", "delivery_ok")))]
    sig = M.get("base_signals", pd.DataFrame())
    order = ["range_ok", "compression_ok", "trend_ok", "touches_ok", "delivery_ok"]
    code = {"building": 0, "near": 1, "fresh": 2}
    r1 = lambda v: nz(v, lambda x: round(float(x), 2))
    fu = [[r.sym, int(r.t), code[r.stage], sum(1 << i for i, f in enumerate(order) if getattr(r, f)), r1(r.r5), r1(r.r10), r1(r.r20), r1(r.x5), r1(r.x10), r1(r.x20),
           r1(r.mdd20), None if r.fail20 is None or pd.isna(r.fail20) else int(bool(r.fail20)), r1(r.to_date), int(r.age)] for r in sig.itertuples()]
    default = M["screen"]["sym"].iloc[0] if len(M["screen"]) else M["syms"][0]
    return dict(dates=dates, mas=metrics.MA_SET, nifty=[nz(x, lambda v: round(float(v), 2)) for x in M["nifty"]], hz=[[n, h] for n, h in metrics.HORIZONS], default=default, universes=M["memberships"], stocks=out, fu=fu, heat=M.get("heat"), power=M.get("power"))



def tab_followthrough(M):
    sig = M.get("base_signals", pd.DataFrame())
    span = f'{M["dates"][int(sig.t.min())]:%d %b %Y} to {M["dates"][-1]:%d %b %Y}' if len(sig) else "no history yet"
    return (f'<p class="desc">The Breakout Bases scan is replayed on every past session ({span}, <b>{len(sig):,} signals</b>). A signal is the first day a stock reaches a stage after at least 10 sessions out of it. '
            'Returns run from that day\'s close. "Vs Nifty" is the return minus the Nifty over the same days. "Broke support" means the low went under the base support within 20 sessions. '
            'The filter buttons above apply here too. Rows with fewer than 30 signals are greyed: treat them as anecdotes.</p>'
            '<div id="fu-summary"></div><h3 class="fuh">RECENT SIGNALS</h3><div id="fu-list"></div>')


def tab_watchlist(M):
    return ('<p class="desc">Stocks you track, saved on this device. Press ☆ beside any stock on the Chart view, or add a ticker here. The list is saved in this browser only, so use Export and Import to move it between your phone and computer.</p>'
            '<div class="wlbar"><input id="wl-add" list="wl-syms" placeholder="Add ticker" autocomplete="off" autocapitalize="characters" spellcheck="false"><datalist id="wl-syms"></datalist>'
            '<button class="seg" id="wl-addbtn">ADD</button><button class="seg" id="wl-export">EXPORT</button><button class="seg" id="wl-import">IMPORT</button><span id="wl-msg" class="mut" aria-live="polite"></span></div>'
            '<div id="wl-body"></div>')


def _stocks_chart(M):
    return ('<div class="sx"><aside class="sl"><input id="q" placeholder="Search ticker" autocomplete="off" autocapitalize="characters" spellcheck="false">'
            '<button type="button" class="seg" id="wlonly" aria-pressed="false" title="Show only my watchlist" aria-label="Show only my watchlist">★</button>'
            '<select id="sort"><option value="az">Sort: A to Z</option><option value="ratio">Sort: delivery ÷ 20d avg</option><option value="px">Sort: price move today</option><option value="rs">Sort: 20-day relative strength</option></select>'
            '<div id="list"></div></aside><div class="sr"><div id="sh"></div>'
            '<div class="rb"><span class="mut">RANGE</span><button class="seg" data-r="504">2Y</button><button class="seg on" data-r="252">1Y</button><button class="seg" data-r="126">6M</button><button class="seg" data-r="63">3M</button>'
            '<span class="mut malabel">MOVING AVG</span><button class="seg mab" data-ma="32">32</button><button class="seg mab on" data-ma="50">50</button><button class="seg mab" data-ma="100">100</button><button class="seg mab on" data-ma="200">200</button><button class="seg mab" data-ma="233">233</button><button class="seg mab" data-ma="377">377</button><button class="seg mab" data-ma="610">610</button>'
            '<span class="mut" style="margin-left:18px">ABOVE-AVERAGE DELIVERY</span><select id="thr"><option value="1">1.0×</option><option value="1.25" selected>1.25×</option><option value="1.5">1.5×</option><option value="2">2.0×</option></select></div>'
            '<div class="chartgrid"><div class="charts"><div id="screens-row" hidden></div><div id="result-row" hidden></div><div id="outlook-row" hidden></div><div id="guidance-row" hidden></div><div id="chartbox" class="chartcard"><svg id="ch"></svg></div>'
            '<div class="chartcard"><svg id="rsch"></svg></div><div class="chartcard"><svg id="oich"></svg></div>'
            '<div id="ro"></div><div id="lg"></div></div><aside id="insights"></aside></div><section id="callintel"></section></div></div>')


def tab_stocks(M):
    return (_subtabs([("chart", "CHART"), ("watch", "WATCHLIST")]) + f'<div class="subview" data-sub="chart" id="sv-chart">{_stocks_chart(M)}</div>'
            f'<div class="subview" data-sub="watch" hidden>{tab_watchlist(M)}</div>')


def tab_upcoming_results(M):
    """Every result meeting NSE has announced for a stock in the universe, with filters applied in the browser."""
    today = M["dates"][-1].normalize()
    caps = M.get("market_cap_cr", {})
    top500 = set(sorted(caps, key=caps.get, reverse=True)[:500])
    fo = set(M["memberships"].get("fo", []))
    best = {}
    for r in M.get("results", []):
        if r["event_date"].normalize() < today or r["symbol"] not in M["syms"]: continue
        old = best.get(r["symbol"])
        if old is None or (r["event_date"], r["status"] != "DECLARED") < (old["event_date"], old["status"] != "DECLARED"): best[r["symbol"]] = r
    rows = []
    for r in sorted(best.values(), key=lambda r: (r["event_date"], r["symbol"])):
        s, cap = r["symbol"], caps.get(r["symbol"])
        bucket = "none" if cap is None else "under5" if cap < 5000 else "5to10" if cap < 10000 else "10to20" if cap <= 20000 else "over20"
        hit = any(x["hit"] for x in r["sessions"])
        filing = f'<a class="src" href="{esc(str(r["source_url"]))}" target="_blank" rel="noopener">NSE ↗</a>' if r.get("source_url") else ""
        status = "DECLARED" if r["status"] == "DECLARED" else ""
        rows.append(f'<tr data-sym="{esc(s)}" data-name="{esc(r.get("name", "").lower())}" data-date="{r["event_date"]:%Y-%m-%d}" data-fo="{int(s in fo)}" data-top500="{int(s in top500)}" data-cap="{bucket}">'
                    f'<td class="l">{stk(s, M).split(" <span class=\"resultmark")[0]}<div class="mut rname">{esc(r.get("name", ""))}</div></td>'
                    f'<td class="l">{r["event_date"]:%a %d %b}</td><td class="l rin"></td><td class="l">{esc(r.get("purpose", ""))}<div class="mut rname">{esc(r.get("period", ""))}</div></td>'
                    f'<td>{"–" if cap is None else f"{cap:,.0f}"}</td><td>{"F&amp;O" if s in fo else "–"}</td><td class="l mut">{esc(r.get("industry", "") if r.get("industry") not in ("-", None) else "")}</td>'
                    f'<td>{"<span class=\"rsig\">PRE-RESULT ACTIVITY</span>" if hit else "<span class=\"mut\">–</span>"}</td><td>{status or filing}</td></tr>')
    head = [("STOCK", "l"), ("DATE", "l"), ("IN", "l"), ("MEETING", "l"), ("MKT CAP ₹ CR", ""), ("F&amp;O", ""), ("SECTOR", "l"), ("PRE-RESULT", ""), ("NSE FILING", "")]
    chips = lambda grp, items: f'<div class="urgrp" data-grp="{grp}">' + "".join(f'<button type="button" class="urchip{" on" if i == 0 else ""}" data-v="{v}">{label}</button>' for i, (v, label) in enumerate(items)) + '</div>'
    return ('<h2>Upcoming Results</h2><div class="subl">BOARD MEETINGS TO CONSIDER FINANCIAL RESULTS · NSE ANNOUNCEMENTS</div>'
            f'<p class="desc">Every result meeting announced to NSE for the {len(M["syms"]):,} stocks tracked here (<b>{len(rows):,} companies</b>), refreshed with each daily build. A rescheduled meeting replaces its earlier date. '
            'Dates are the board-meeting dates in the exchange filing; the result is usually out the same day. Market caps are NSE’s last half-yearly average, so treat them as a size band, not today’s value.</p>'
            '<div class="urbar">' + chips("set", [("all", "ALL"), ("top500", "TOP 500"), ("fo", "F&amp;O")])
            + chips("cap", [("any", "ANY CAP"), ("under5", "&lt; ₹5,000 CR"), ("5to10", "₹5,000–10,000 CR"), ("10to20", "₹10,000–20,000 CR"), ("over20", "&gt; ₹20,000 CR")])
            + chips("within", [("0", "ANY DATE"), ("1", "TODAY"), ("3", "3 DAYS"), ("7", "7 DAYS"), ("14", "14 DAYS")])
            + '<input id="ur-q" placeholder="Search ticker or company" autocomplete="off" spellcheck="false"><span id="ur-count" class="basecount" aria-live="polite"></span></div>'
            + (table(head, rows, "urtable") if rows else '<div class="card rempty">No upcoming result meetings are in the calendar yet. It fills automatically as companies announce board meetings.</div>'))


def tab_alt_data(M):
    head = ('<h2>Alternative Data<span class="expbadge">EXPERIMENTAL</span></h2><div class="subl">WEATHER AND POWER · DEMAND SIGNALS OUTSIDE THE EXCHANGE FEEDS</div>')
    temp = ('<p class="desc">A read on cooling and heating demand for consumer durables (ACs, coolers, fans, heaters, geysers) from how 25 large cities are running against their own history; six of them are charted below. '
            'Each city is compared with the same days of the last two years and with its 1991–2020 normal. North, East, West and South are simple averages of their cities, not weighted by population or sales.</p>'
            '<div class="expnote"><b>Read with care.</b> Values are ERA5 model grid-cell estimates from Open-Meteo, not weather-station readings, and can differ from IMD by a degree or so, especially on the coast. '
            'The latest data is about a week old. Temperature is one input to demand, not a sales forecast. The El Niño reading shows correlation only. Research tooling, not investment advice.</div>')
    temp += ('<div id="heat-root"></div>' if M.get("heat") else '<div class="card rempty">No temperature data has been downloaded yet. It fills in on the next build; the first run pulls 1991 onward for each city and takes several minutes.</div>')
    power = ('<p class="desc">Daily generation by company from the Central Electricity Authority’s Daily Generation Report (npp.gov.in), a read on power demand and on the listed generators. '
             'Each year is compared with the same dates a year earlier, smoothed with a 14 or 30-day trailing average.</p>'
             '<div class="expnote"><b>Read with care.</b> The report covers conventional stations only (coal, lignite, gas, hydro, nuclear and imports); <b>wind and solar are not in it</b>, so the total is not national supply. '
             'Files appear one to two days late. Plant-to-company matching is hand-maintained in <code>config/plant_owner.csv</code>: unmatched plants are left out of the company table, some matches are medium confidence, '
             'and a coal stock of 0 can mean "not reported". Not investment advice.</div>')
    power += ('<div id="power-root"></div>' + backtest_panels(M.get("backtest")) if M.get("power") else '<div class="card rempty">No power data has been downloaded yet. It fills in over the next few builds: each build loads as many days as its time budget allows, newest first.</div>')
    return (head + _subtabs([("temp", "TEMPERATURE"), ("power", "POWER GENERATION")])
            + f'<div class="subview" data-sub="temp">{temp}</div><div class="subview" data-sub="power" hidden>{power}</div>')


PRETTY = {"NTPC": "NTPC", "ADANIPOWER": "Adani Power", "ADANIGREEN": "Adani Green", "NHPC": "NHPC", "JSWENERGY": "JSW Energy"}
SIG_SHORT = {"GEN_YOY": "Generation vs last year", "GEN_MOM": "Generation momentum", "PX_YOY": "IEX price vs last year", "PX_MOM": "IEX price momentum", "BOTH": "Both rising"}


def _band_bars(bands, hi):
    """Four small bars (mean 20-day excess return in each signal band) around a zero line; hi is the largest absolute value across rows."""
    w, h, mid = 220, 44, 22
    out = f'<line x1="0" x2="{w}" y1="{mid}" y2="{mid}" stroke="#444"/>'
    for i, b in enumerate(bands):
        v = b["mean"]
        if v is None or b["n"] < 8: continue
        ht = max(1, abs(v) / hi * (mid - 2)); y = mid - ht if v >= 0 else mid
        out += f'<rect x="{i * 55 + 8}" y="{y:.1f}" width="39" height="{ht:.1f}" fill="{"#4fd18b" if v >= 0 else "#ff7a5c"}"><title>{esc(b["label"])}: {v:+.1f}% over Nifty, {b["n"]} dates</title></rect>'
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Average 20-day return by signal band">{out}</svg>'


def backtest_panels(bt):
    """Small panels summarising the locally run backtest (config/backtest_results.json). Sits under the Power generation view."""
    head = '<h3 class="fuh">DO THESE SIGNALS LEAD THE STOCKS? <span class="expbadge red">VERY EXPERIMENTAL</span></h3>'
    if not bt:
        return head + '<div class="card rempty">The backtest has not been run yet. Run <code>python backtest.py</code> on a machine with the power data.</div>'
    ys = bt["years"]
    yrow = "".join(f'<div class="btrow"><b>{y if y != "2026" else "2026 to date"}</b><span class="vd vd-works">{c["WORKS"]} works</span><span class="vd vd-some">{c["SOMETIMES WORKS"]} sometimes</span>'
                   f'<span class="vd vd-could">{c["COULD WORK"]} could</span><span class="vd vd-doesnt">{c["DOESN\'T WORK"]} no</span><span class="vd vd-inverse">{c["INVERSE"]} inverse</span></div>' for y, c in ys.items())
    p1 = (f'<div class="mchart"><div class="mtitle"><b>What works</b><span class="mut">{sum(c["tests"] for c in ys.values())} tests</span></div>{yrow}'
          f'<div class="msum">Nothing reads WORKS in any year. About {list(ys.values())[0]["chance"]} per year would by luck alone.</div></div>')
    if bt["held"]:
        items = "".join(f'<div class="btrow"><b>{esc(PRETTY.get(h["stock"], h["stock"]))}</b> · {esc(SIG_SHORT.get(h["signal"], h["signal"]))}<span class="mut"> positive in {", ".join(h["years"])}'
                        + (f'; backwards in {", ".join(h["against"])}' if h["against"] else "") + '</span></div>' for h in bt["held"])
    else:
        items = '<div class="mut">None.</div>'
    p2 = (f'<div class="mchart"><div class="mtitle"><b>Held in more than one year</b><span class="mut">the only ones worth a second look</span></div>{items}'
          '<div class="msum">Even these are weak: one test passing twice out of fifteen is roughly what chance gives.</div></div>')
    rows = "".join(f'<div class="btrow"><b>{esc(SIG_SHORT.get(k, k))}</b><span class="mut">{v["positive"]} worked · {v["flat"]} nothing · <span class="{"pdn" if v["inverse"] else ""}">{v["inverse"]} backwards</span></span></div>' for k, v in bt["by_signal"].items())
    p3 = (f'<div class="mchart"><div class="mtitle"><b>What doesn\'t</b><span class="mut">each signal, all stocks and years</span></div>{rows}'
          '<div class="msum">The price signals went backwards in 2026: power prices and generation rose while these stocks fell.</div></div>')
    thr = bt["thresholds"]; hi = max([abs(b["mean"]) for t in thr.values() for b in t["bands"] if b["mean"] is not None and b["n"] >= 8] or [1])
    lab = "".join(f'<span>{esc(b["label"])}</span>' for b in next(iter(thr.values()))["bands"]) if thr else ""
    rowt = "".join(f'<div class="btrow"><b>{esc(SIG_SHORT.get(k, k))}</b>{_band_bars(t["bands"], hi)}</div>' for k, t in thr.items())
    s = bt["strongest"][0] if bt["strongest"] else None
    verdict = ("<b>No clear threshold.</b> " if not bt["strong_enough"] else "<b>A possible threshold.</b> ")
    if s:
        verdict += (f'The biggest gap is {esc(SIG_SHORT.get(s["signal"], s["signal"]))} above {s["cut"]:+.1f} standard deviations: {s["above"]:+.1f}% against {s["below"]:+.1f}% for the rest, '
                    f'but the noise on that is about ±{s["se"]:.1f} points, so it is not reliable. The bars show no pattern that repeats across signals.')
    p4 = (f'<div class="mchart"><div class="mtitle"><b>Is there a threshold?</b><span class="mut">20-day return over Nifty by signal level</span></div>'
          f'<div class="btbands"><span></span><div class="btlab">{lab}</div></div>{rowt}<div class="msum">{verdict}</div></div>')
    note = (f'<div class="mut pnote">Run on a local machine on {esc(bt.get("generated", "?"))}, share prices to {esc(bt["asof"])}. Signals use only what was public: generation two days late, IEX price one day late. Each test looks at the stock\'s 20-day return over Nifty, on every fifth trading day, and is scored year by year. '
            'Bands are the signal measured in standard deviations from its own past year. NHPC is tested against all-India hydro generation, and Adani Green has only price tests because wind and solar are not in the CEA report. About a dozen independent observations per test per year, no costs, ownership hand-matched. A screen for ideas, not investment advice.</div>')
    return head + f'<div class="mgrid c4">{p1}{p2}{p3}{p4}</div>' + note


SHORT_COLORS = {"cash_selling": "#ff7a5c", "laggards": "#b58cff", "breakdown": "#ff4d6d", "rejection": "#ffd17a", "buildup": "#6db0ff", "near_lows": "#6fd6c8", "retest": "#c792ff"}
SHORT_CHART_CAP = 30


def earlier_touches(ch, pat, start):
    """Touches of a pattern that fall before the part of the chart that is drawn (older than `start`, or older than the bars the chart carries): how many, and the whole-history strip that shows them."""
    if not ch.get("full"): return 0, ""
    off = ch.get("off", 0); pts = [(i + off, p) for i, p in pat["touches"]]; first = off + start
    n_before = sum(1 for i, _ in pts if i < first)
    if not n_before: return 0, ""
    full = ch["full"]; N = len(full); vals = [v for v in full if v is not None] + [p for _, p in pts]
    lo, hi = min(vals), max(vals); w, h, l, r, t, b = 420, 78, 4, 44, 6, 14
    X = lambda i: l + (i + .5) * (w - l - r) / N; Y = lambda v: t + (1 - (v - lo) / ((hi - lo) or 1)) * (h - t - b)
    q = f'<rect x="{X(first):.1f}" y="{t}" width="{w - r - X(first):.1f}" height="{h - t - b}" fill="rgba(232,169,58,.12)"/>'
    q += f'<polyline points="{" ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(full) if v is not None)}" fill="none" stroke="#8b8b86" stroke-width="1.2"/>'
    for ln in pat["lines"]:
        if abs(ln["a"][1] - ln["b"][1]) < 1e-6 * abs(ln["a"][1]):
            q += f'<line x1="{l}" x2="{w - r}" y1="{Y(ln["a"][1]):.1f}" y2="{Y(ln["a"][1]):.1f}" stroke="{"#ef5a4d" if ln["role"] == "resistance" else "#2fbf71"}" stroke-width="1.2" stroke-dasharray="4 3"/>'
    q += "".join(f'<circle cx="{X(i):.1f}" cy="{Y(p):.1f}" r="3" fill="none" stroke="#f1f1ec" stroke-width="1.2"/>' for i, p in pts)
    q += (f'<text x="{l + 2}" y="{h - 3}" fill="#77776f" font-size="9" font-family="monospace">{esc(ch.get("full_first", ""))}</text>'
          f'<text x="{w - r}" y="{h - 3}" text-anchor="end" fill="#77776f" font-size="9" font-family="monospace">{esc(ch["dates"][-1])}</text>')
    return n_before, (f'<div class="ptfull mut">WHOLE HISTORY · the shaded part is the chart above · {len(pts)} touches in all, {n_before} before it</div>'
                      f'<svg class="shsvg" viewBox="0 0 {w} {h}" role="img" aria-label="The pattern against the whole price history">{q}</svg>')


def short_chart(sym, ch, keys, w=420, ph=170, dh=52, start=0, pattern=None):
    """Candlesticks with 50 and 100-day averages over delivered-share bars, as on the Stocks screen. The sessions among the latest few on which a screen in
    `keys` was true are shaded; support and resistance zones (delivery-weighted price congestion) are drawn as bands. `start` hides everything before that session;
    `pattern` ({lines, touches, target}, in the same session coordinates) draws a chart pattern's trendlines, touch points and measured-move target."""
    if start:
        full = len(ch["close"]); ch = {k: (v[start:] if isinstance(v, list) and len(v) == full else v) for k, v in ch.items()}
        ch["flags"] = {k: [i - start for i in v if i >= start] for k, v in ch.get("flags", {}).items()}
    o, hh, ll, c, dq = ch["open"], ch["high"], ch["low"], ch["close"], ch["dq"]; n = len(c)
    m200 = ch.get("ma200") if "retest" in keys else None
    m50, m100, avg, rat_src = ch["ma50"], ch["ma100"], ch["dqavg"], [(d / a if d and a else None) for d, a in zip(dq, ch["dqavg"])]
    vals = [v for v in hh + ll + c + ((m200 or [])) if v is not None]
    if n < 5 or not vals: return ""
    lo, hi = min(vals), max(vals); pad = (hi - lo) * .06 or 1; lo -= pad; hi += pad
    l, r, t, gap = 4, 44, 6, 12; plot_b = t + ph; dbase = plot_b + gap + dh; H = dbase + 16
    X = lambda i: l + (w - l - r) * (i + .5) / n; Y = lambda v: t + (1 - (v - lo) / (hi - lo)) * ph
    bw = max(1.6, (w - l - r) / n * .72); slot = (w - l - r) / n
    g = "".join(f'<line x1="{l}" x2="{w - r}" y1="{Y(lo + (hi - lo) * k / 3):.1f}" y2="{Y(lo + (hi - lo) * k / 3):.1f}" stroke="#222"/><text x="{w - r + 4}" y="{Y(lo + (hi - lo) * k / 3) + 3:.1f}" fill="#77776f" font-size="9" font-family="monospace">{lo + (hi - lo) * k / 3:,.0f}</text>' for k in range(4))
    for kind, col in (("support", "#2fbf71"), ("resistance", "#ef5a4d")):
        for z in ch["zones"].get(kind, []):
            zt, zb = min(Y(z["hi"]), plot_b), max(Y(z["lo"]), t)
            if z["lo"] > hi or z["hi"] < lo or zb <= zt: continue
            zt, zb = max(zt, t), min(zb, plot_b)
            g += (f'<rect x="{l}" y="{zt:.1f}" width="{w - l - r}" height="{max(1.5, zb - zt):.1f}" fill="{col}" opacity=".13"><title>{kind} zone {z["lo"]:,.2f} to {z["hi"]:,.2f}</title></rect>'
                  f'<line x1="{l}" x2="{w - r}" y1="{zt:.1f}" y2="{zt:.1f}" stroke="{col}" stroke-opacity=".55" stroke-dasharray="2 3"/><line x1="{l}" x2="{w - r}" y1="{zb:.1f}" y2="{zb:.1f}" stroke="{col}" stroke-opacity=".55" stroke-dasharray="2 3"/>'
                  f'<text x="{l + 3}" y="{zt + 8:.1f}" fill="{col}" font-size="8" font-family="monospace">{"SUPPORT" if kind == "support" else "RESISTANCE"}</text>')
    for k in keys:
        col = SHORT_COLORS.get(k, "#fff")
        for i in ch["flags"].get(k, []):
            g += f'<rect x="{X(i) - slot / 2:.1f}" y="{t}" width="{slot:.1f}" height="{dbase - t:.1f}" fill="{col}" opacity=".24"><title>{esc(ch["dates"][i])} · {esc(k.replace("_", " "))}</title></rect>'
    line = lambda ser: " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(ser) if v is not None)
    g += f'<polyline points="{line(m100)}" fill="none" stroke="#5aa9ff" stroke-width="1" stroke-dasharray="4 3"/><polyline points="{line(m50)}" fill="none" stroke="#e8a93a" stroke-width="1.2" stroke-dasharray="4 3"/>'
    if m200: g += f'<polyline points="{line(m200)}" fill="none" stroke="#c792ff" stroke-width="1.6"/><text x="{w - r - 3}" y="{Y(m200[-1]) - 4 if m200[-1] is not None else 0:.1f}" text-anchor="end" fill="#c792ff" font-size="8" font-family="monospace">200DMA</text>' if m200[-1] is not None else ""
    for i in range(n):
        if None in (o[i], hh[i], ll[i], c[i]): continue
        col = "#2fbf71" if c[i] >= o[i] else "#ef5a4d"; x = X(i)
        g += (f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y(hh[i]):.1f}" y2="{Y(ll[i]):.1f}" stroke="{col}"/><rect x="{x - bw / 2:.1f}" y="{Y(max(o[i], c[i])):.1f}" width="{bw:.1f}" height="{max(1, abs(Y(o[i]) - Y(c[i]))):.1f}" fill="{col}"/>')
    if pattern:
        for ln in pattern["lines"]:
            (x0, y0), (x1, y1) = ln["a"], ln["b"]; x0 -= start; x1 -= start
            col = "#ef5a4d" if ln["role"] == "resistance" else "#2fbf71"
            g += f'<line x1="{X(max(x0, 0)):.1f}" y1="{Y(y0 + (y1 - y0) * (max(x0, 0) - x0) / ((x1 - x0) or 1)):.1f}" x2="{X(x1):.1f}" y2="{Y(y1):.1f}" stroke="{col}" stroke-width="1.6"/>'
        g += "".join(f'<circle cx="{X(i - start):.1f}" cy="{Y(p):.1f}" r="2.6" fill="none" stroke="#f1f1ec" stroke-width="1"/>' for i, p in pattern["touches"] if i >= start)
        if pattern.get("earlier"):
            for ln in pattern["lines"]:
                if abs(ln["a"][1] - ln["b"][1]) < 1e-6 * abs(ln["a"][1]) and lo < ln["a"][1] < hi:
                    col = "#ef5a4d" if ln["role"] == "resistance" else "#2fbf71"; yy = Y(ln["a"][1]); xa = X(max(ln["a"][0] - start, 0))
                    g += (f'<line x1="{l}" x2="{xa:.1f}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{col}" stroke-width="1.4" stroke-dasharray="4 3" opacity=".85"/>'
                          f'<text x="{l + 3}" y="{yy - 4:.1f}" fill="#f1f1ec" font-size="9" font-family="monospace">◄ {pattern["earlier"]} EARLIER TOUCH{"ES" if pattern["earlier"] > 1 else ""} · OFF THE LEFT OF THIS CHART</text>')
        tg = pattern.get("target")
        if tg is not None and lo < tg < hi:
            g += (f'<line x1="{l}" x2="{w - r}" y1="{Y(tg):.1f}" y2="{Y(tg):.1f}" stroke="#ffd17a" stroke-dasharray="5 3" stroke-width="1.2"/>'
                  f'<text x="{w - r - 3}" y="{Y(tg) - 3:.1f}" text-anchor="end" fill="#ffd17a" font-size="9" font-family="monospace">TARGET {tg:,.0f}</text>')
    # delivered shares: colour by the day's move, brighter when delivery is at least 1.25x its 20-session average
    dmax = max([v for v in dq + avg if v] or [1]) * 1.05
    g += f'<text x="{l + 3}" y="{plot_b + gap + 9}" fill="#77776f" font-size="8" font-family="monospace">DELIVERED SHARES · DASHED = 20D AVG</text>'
    for i in range(n):
        if dq[i] is None: continue
        hot = (rat_src[i] or 0) >= 1.25; d = ch["dc"][i]
        col = ("#a3a39c" if hot else "rgba(163,163,156,.46)") if d == 0 else ("#2fbf71" if hot else "rgba(47,191,113,.64)") if d == 1 else ("#ef5a4d" if hot else "rgba(239,90,77,.64)")
        bh = dq[i] / dmax * (dh - 10)
        g += f'<rect x="{X(i) - bw / 2:.1f}" y="{dbase - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{col}"/>'
    ap = " ".join(f"{X(i):.1f},{dbase - v / dmax * (dh - 10):.1f}" for i, v in enumerate(avg) if v)
    if ap: g += f'<polyline points="{ap}" fill="none" stroke="#e8e8e2" stroke-width="1.2" stroke-dasharray="4 3"/>'
    for k in keys:
        col = SHORT_COLORS.get(k, "#fff")
        g += "".join(f'<circle cx="{X(i):.1f}" cy="{Y(hh[i]) - 4:.1f}" r="2.4" fill="{col}"/>' for i in ch["flags"].get(k, []) if hh[i] is not None)
    for q in (0, n // 3, 2 * n // 3, n - 1):
        g += f'<text x="{X(q):.1f}" y="{H - 3}" fill="#77776f" font-size="9" font-family="monospace" text-anchor="{"start" if q == 0 else "end" if q == n - 1 else "middle"}">{esc(ch["dates"][q][:6])}</text>'
    return f'<svg class="shsvg" viewBox="0 0 {w} {H}" role="img" aria-label="{esc(sym)} candlesticks with delivered shares, 50 and 100-day averages, support and resistance">{g}</svg>'


def _zone_text(ch):
    z = ch["zones"]; c = ch["close"][-1]; out = []
    for kind, lab in (("support", "Support"), ("resistance", "Resistance")):
        zs = z.get(kind, [])
        if zs:
            a = zs[0]; mid = (a["lo"] + a["hi"]) / 2
            out.append(f'<span class="{"pup" if kind == "support" else "pdn"}">{lab} {a["lo"]:,.0f}–{a["hi"]:,.0f}</span> <span class="mut">({(mid / c - 1) * 100:+.1f}%)</span>')
    return " · ".join(out)


def short_cards(syms, M, X, keys_for, cap=SHORT_CHART_CAP):
    """A grid of chart cards. keys_for(sym) names the screens to mark on that stock's chart."""
    cards = []
    for sym in syms[:cap]:
        ch = X["charts"].get(sym)
        if not ch: continue
        keys = keys_for(sym); c = ch["close"]; last = c[-1]
        px1 = (c[-1] / c[-2] - 1) * 100 if len(c) > 1 and c[-1] and c[-2] else None
        days = sum(len(ch["flags"].get(k, [])) for k in keys)
        marks = " ".join(f'<i class="shkey" style="background:{SHORT_COLORS[k]}"></i>{esc(k.replace("_", " ").title())}' for k in keys)
        cards.append(f'<div class="card shcard"><div class="shhead"><b>{stk(sym, M)}</b><span class="mut">{last:,.2f}</span><span class="{"pup" if (px1 or 0) >= 0 else "pdn"}">{pc(px1)}</span><span class="mut shdays">{days} flagged day{"s" if days != 1 else ""} in the last {shorts_mod.RECENT_DAYS}</span></div>'
                     f'<div class="shmarks">{marks}</div><div class="shzones">{_zone_text(ch)}</div>{short_chart(sym, ch, keys)}</div>')
    more = f'<p class="desc">Showing the first {cap} of {len(syms)}, in the same order as the table.</p>' if len(syms) > cap else ""
    return ('<div class="shlegend"><i class="shln a"></i>50-day <i class="shln b"></i>100-day <i class="shkey" style="background:#2fbf71;opacity:.45"></i>Support <i class="shkey" style="background:#ef5a4d;opacity:.45"></i>Resistance <span class="mut">· shaded bars and dots mark only the last 10 sessions on which the rule was true</span></div>'
            f'<div class="shgrid">{"".join(cards)}</div>{more}')


def tab_shorts(M):
    X = M.get("shorts")
    head = '<h2>Short Ideas<span class="expbadge">EXPERIMENTAL</span></h2><div class="subl">F&amp;O · PRICE ACTION THAT POINTS TO A POTENTIAL SHORT · THE 200DMA RETEST ALSO COVERS EVERY LIQUID SHARE, WITH AN F&amp;O FILTER</div>'
    if not X:
        return head + '<div class="card rempty">Short ideas need an F&amp;O universe and about 70 sessions of history.</div>'
    note = ('<div class="expnote"><b>Read with care.</b> These are screens, not recommendations. Each flags F&amp;O stocks whose price action looks weak by a stated rule; none says a stock will fall. '
            'The replay column applies the same rule to the sessions this desk holds and shows what the stock did against Nifty over the next 10 sessions: a few hundred sessions, overlapping windows, no costs, one market regime. '
            'Shorting in a rising market has unlimited loss, and F&amp;O stocks can gap against you on results or news. Not investment advice.</div>')
    base = X.get("baseline")
    base_txt = (f'For comparison, the average F&amp;O stock moved {base["avg"]:+.1f}% against Nifty over 10 sessions and underperformed {base["hit"]:.0f}% of the time.' if base else "")

    def replay_line(r):
        if not r or r["avg"] is None: return f'<span class="mut">Replay: only {r["n"] if r else 0} past flags, too few to read.</span>'
        edge = r["avg"] - (base["avg"] if base else 0)
        verdict = ("Weaker than the average F&amp;O stock, as a short needs." if edge <= -0.5 else "Stronger than the average F&amp;O stock: it has not worked as a short."
                   if edge >= 0.5 else "About the same as any F&amp;O stock: the replay shows no edge.")
        cls = "pdn" if edge <= -0.5 else "pup" if edge >= 0.5 else ""
        return (f'Replay: after {r["n"]} past flags the stock moved <b class="{cls}">{r["avg"]:+.1f}%</b> against Nifty over the next 10 sessions and underperformed <b>{r["hit"]:.0f}%</b> of the time. {verdict}')

    def rows_table(df):
        if not len(df): return '<div class="card rempty">No F&amp;O stock meets this rule today.</div>'
        rows = []
        for i, r in df.iterrows():
            new = '<span class="newcash">NEW TODAY</span>' if r.new else ""
            rows.append(f'<tr class="{"cashnew" if r.new else ""}"><td class="mut">{i + 1}</td><td class="l">{stk(r.sym, M)} {new}</td><td><b>{int(r.days)}D</b></td><td>{r.close:,.2f}</td>'
                        f'<td{heat(r.px1d, 5)}>{pc(r.px1d)}</td><td{heat(r.px3d, 8)}>{pc(r.px3d)}</td><td{heat(r.rel20, 15)}>{pc(r.rel20)}</td><td{heat(r.rel63, 30)}>{pc(r.rel63)}</td>'
                        f'<td{heat(r.ma50, 15)}>{pc(r.ma50)}</td><td>{"–" if pd.isna(r.ratio) else f"{r.ratio:.2f}×"}</td><td{heat(-(r.oi3 if pd.notna(r.oi3) else 0), 15)}>{"–" if pd.isna(r.oi3) else pc(r.oi3)}</td></tr>')
        headr = [("#", "mut"), ("STOCK", "l"), ("DAYS FLAGGED", ""), ("CLOSE", ""), ("PX 1D", ""), ("PX 3D", ""), ("VS NIFTY 20D", ""), ("VS NIFTY 3M", ""), ("VS 50MA", ""), ("DELIVERY ÷ 20D", ""), ("SSF OI 3D", "")]
        return table(headr, rows, "cashwatch")

    def srow(v):
        r = v["replay"]; avg = "–" if r["avg"] is None else f'{r["avg"]:+.1f}%'; hit = "–" if r["hit"] is None else f'{r["hit"]:.0f}%'
        return f'<tr><td class="l">{esc(v["title"])}</td><td>{len(v["rows"])}</td><td{heat(-(r["avg"] or 0), 3)}>{avg}</td><td>{hit}</td><td>{r["n"]}</td></tr>'

    conf = X["confluence"]; titles = {k: t for k, t, _ in shorts_mod.SCREENS}
    crow = []
    for _, r in conf[conf["count"] >= 2].head(40).iterrows():
        crow.append(f'<tr><td class="l">{stk(r.sym, M)}</td><td><b>{int(r["count"])}</b></td><td class="l">{" · ".join(esc(titles[k].title()) for k in r.screens)}</td></tr>')
    overview = ('<p class="desc">Stocks flagged by more than one screen today. Agreement between screens that look at different things (selling, relative weakness, a broken level, open interest) is the closest this page gets to conviction.</p>'
                + (table([("STOCK", "l"), ("SCREENS", ""), ("WHICH", "l")], crow) if crow else '<div class="card rempty">No F&amp;O stock is flagged by two or more screens today.</div>')
                + (short_cards(list(conf[conf["count"] >= 2]["sym"]), M, X, lambda sym: list(conf.loc[conf.sym == sym, "screens"].iloc[0]), cap=12) if len(conf[conf["count"] >= 2]) else "")
                + '<h3 class="fuh">HOW MANY EACH SCREEN FLAGS TODAY</h3>'
                + table([("SCREEN", "l"), ("TODAY", ""), ("REPLAY: MOVE VS NIFTY, NEXT 10 SESSIONS", ""), ("REPLAY: UNDERPERFORMED", ""), ("PAST FLAGS", "")],
                        [srow(v) for v in X["screens"].values()]))
    subs = [("overview", "OVERVIEW")] + [(k, v["title"]) for k, v in X["screens"].items()]
    body = _subtabs(subs) + f'<div class="subview" data-sub="overview">{overview}</div>'
    def retest_view(v):
        df = v["rows"]
        rows = []
        for i, r in df.iterrows():
            tag = '<span class="newcash">NEW TODAY</span>' if r.new else ""
            fo = ' <span class="fotag" title="Has single-stock futures">F&amp;O</span>' if r.fo else ""
            rows.append(f'<tr class="{"cashnew" if r.new else ""}" data-fo="{int(bool(r.fo))}"><td class="l">{stk(r.sym, M)}{fo} {tag}</td><td>{int(r.days)}</td><td>{r.brk_date:%d %b}</td><td{heat(r.brk_ratio - 1, 3)}>{r.brk_ratio:.1f}×</td>'
                        f'<td{heat(r.depth, 15)}>{pc(r.depth)}</td><td{heat(r.dist, 4)}>{pc(r.dist)}</td><td>{r.close:,.2f}</td><td{heat(r.px1d, 5)}>{pc(r.px1d)}</td><td>{"–" if pd.isna(r.ratio) else f"{r.ratio:.2f}×"}</td></tr>')
        tbl = table([("STOCK", "l"), ("SESSIONS SINCE BREAK", ""), ("BROKE ON", ""), ("DELIVERY ON BREAK", ""), ("LOWEST SINCE VS 200DMA", ""), ("NOW VS 200DMA", ""), ("CLOSE", ""), ("PX 1D", ""), ("DELIVERY ÷ 20D", "")], rows, "cashwatch retesttable") if rows else '<div class="card rempty">No stock is retesting a lost 200-day average today.</div>'
        cards = short_cards(list(df["sym"]), M, X, lambda sym: ["retest"], cap=30) if len(df) else ""
        cards = re.sub(r'<div class="shlegend">.*?</div>', '<div class="shlegend"><i class="shln" style="border-color:#c792ff"></i>200-day average <i class="shln a"></i>50-day <i class="shln b"></i>100-day</div>', cards, count=1, flags=re.S)
        fo_of = dict(zip(df["sym"], df["fo"]))
        cards = re.sub(r'<div class="card shcard">(<div class="shhead"><b><a class="stk" data-s="([^"]+)")', lambda m: f'<div class="card shcard" data-fo="{int(bool(fo_of.get(m.group(2))))}">{m.group(1)}', cards)
        nfo = int(df["fo"].sum()) if len(df) else 0
        ctl = (f'<div class="fobar"><span class="mut">UNIVERSE</span><div class="urgrp"><button class="fochip fotoggle on" data-fo="all">ALL LIQUID SHARES · {len(df)}</button><button class="fochip fotoggle" data-fo="1">F&amp;O ONLY · {nfo}</button></div></div>')
        return ctl, tbl, cards

    for k, v in X["screens"].items():
        if k == "retest":
            ctl, tbl, cards = retest_view(v)
            rf = v.get("replay_fo")
            body += (f'<div class="subview fofilter" data-sub="retest" hidden><p class="desc">{esc(v["desc"])}</p>{ctl}<div class="msum">All liquid shares ({v["universe"]}): {replay_line(v["replay"])}<br>F&amp;O only ({v["fo_universe"]}): {replay_line(rf)} {base_txt}</div>'
                     f'{tbl}' + (f'<h3 class="fuh">CHARTS</h3>{cards}' if cards else "") + '</div>')
            continue
        body += (f'<div class="subview" data-sub="{k}" hidden><p class="desc">{esc(v["desc"])}</p><div class="msum">{replay_line(v["replay"])} {base_txt}</div>{rows_table(v["rows"])}'
                 + (f'<h3 class="fuh">CHARTS</h3>' + short_cards(list(v["rows"]["sym"]), M, X, lambda sym, k=k: [k]) if len(v["rows"]) else "") + '</div>')
    return head + f'<div class="hmeta">As of <b>{X["asof"]:%d %b %Y}</b> · {sum(len(v["rows"]) for v in X["screens"].values())} flags across {len(conf)} F&amp;O stocks</div>' + note + body


def tab_credit(M):
    """The Credit Desk: the Banks and NBFC dashboards (credit.py), each in a sandboxed frame that is filled in the first time its subtab is opened."""
    import credit
    head = '<h2>Peer Radar</h2><div class="subl">SAME-SECTOR STOCKS SIDE BY SIDE · TRENDS ACROSS THE PACK · BANKS AND NBFCS FOR NOW</div>'
    docs = [(k, lbl, sub, credit.document(k)) for k, lbl, sub in credit.DASHBOARDS]
    live = [d for d in docs if d[3]]
    if not live: return head + '<div class="card rempty">The dashboards are not available in this build.</div>'
    note = ('<div class="expnote">These are static snapshots, written from each company\'s Q2 FY27 filings and calls. The daily build does not refresh them; replace the files in <code>config/dashboards/</code> to update. '
            'Views and valuation are interpretation, not fact, and not investment advice.</div>')
    body = _subtabs([(k, lbl) for k, lbl, _, _ in live]) + "".join(
        f'<div class="subview" data-sub="{k}"{"" if i == 0 else " hidden"}><iframe class="creditframe" data-key="{k}" title="{esc(sub)}" sandbox="allow-scripts"></iframe>'
        f'<script type="application/json" id="credit-doc-{k}">{json.dumps(doc).replace("</", "<\\/")}</script></div>' for i, (k, _, sub, doc) in enumerate(live))
    return head + note + body


PATTERN_RULES = {
    "ascending": ("Flat top, rising lows. A potential breakout on the upside.",
                  ["Resistance: three or more swing highs within 2% of each other (touched more than twice), at least 12 sessions apart.",
                   "Support: at least three swing lows, each lower than every swing low after it, so the lows keep rising by at least 3%; the trendline joins the first and last of them.",
                   "Converging: the gap between the flat top and the rising line starts 6% to 50% of the price tall and has shrunk to 80% or less of that now; the pattern is 35 to 270 sessions old.",
                   "Closes stay above the rising line (95% of sessions, 3% leeway) and nothing has pushed more than 3% through the top before the latest 10 sessions.",
                   "BREAKOUT: the first close 1% above the top came in the last 10 sessions and still holds. SETUP: close within 4% under the top. FORMING: within 10% under it.",
                   "Target: the top plus the pattern's widest height."]),
    "descending": ("Flat bottom, falling highs. A potential breakdown on the downside.",
                   ["Support: three or more swing lows within 2% of each other (touched more than twice), at least 12 sessions apart.",
                    "Resistance: at least three swing highs, each higher than every swing high after it, so the highs keep falling by at least 3%; the trendline joins the first and last of them.",
                    "Converging: the gap starts 6% to 50% of the price tall and has shrunk to 80% or less of that now; the pattern is 35 to 270 sessions old.",
                    "Closes stay below the falling line (95% of sessions, 3% leeway) and nothing has dropped more than 3% through the bottom before the latest 10 sessions.",
                    "BREAKDOWN: the first close 1% below the bottom came in the last 10 sessions and still holds. SETUP: close within 4% above the bottom. FORMING: within 10% above it.",
                    "Target: the bottom minus the pattern's widest height."]),
    "rectangle": ("A clean, defined range: flat top and flat bottom.",
                  ["Resistance and support must each be touched more than twice: three or more swing points within 2% of their level, at least 12 sessions apart, seven or more touches in all.",
                   "The range is 7% to 40% of the price and 35 to 270 sessions old; at least 90% of closes sit inside it (2% leeway), the average close has not drifted by more than half the range from start to now, and nothing has pushed more than 3% outside it before the latest 10 sessions.",
                   "BREAKOUT or BREAKDOWN: the first close 1% beyond a side came in the last 10 sessions and still holds. AT TOP or AT BOTTOM: within 4% of that side. IN RANGE: anywhere else inside.",
                   "Target: the break level plus (or minus) the range height."]),
}


def _embed(html):
    """A whole tab placed inside another: its own big heading goes, its subtitle and content stay."""
    return re.sub(r"<h2>.*?</h2>", "", html, count=1, flags=re.S)


def tab_patterns(M):
    P = M.get("patterns") or {}
    head = '<h2>Technical Patterns<span class="expbadge">EXPERIMENTAL</span></h2><div class="subl">TRIANGLES AND RECTANGLES FROM SWING HIGHS AND LOWS · BREAKOUT BASES · SHORT IDEAS</div>'
    note = ('<div class="expnote"><b>Read with care.</b> A rule-based reading of the chart, not a forecast. Patterns are found on adjusted prices, on daily candles and again, with the same rules, on weekly candles, for the top-1,000 shares that trade at least ₹2 crore a day; '
            'the lines are drawn through swing points by a fixed rule, so another analyst may draw them differently. Many patterns resolve the other way, and a break on thin delivery often fails. On simulated random price paths these same rules still find a pattern in about four paths in ten, so a pattern on its own is weak evidence: read it with the delivery on the break and the stock\'s sector. '
            'The longest patterns are limited by the price history the desk holds. Each table is headed by a replay of how past fresh breaks of that pattern went, high-delivery breaks first (see its caveats): the results differ a good deal by pattern and timeframe, and some show no edge at all. Not investment advice.</div>')
    cls = {"BREAKOUT": "up", "BREAKDOWN": "down", "SETUP": "near", "AT TOP": "near", "AT BOTTOM": "near", "FORMING": "mut", "IN RANGE": "mut"}
    pretty = {k: t for k, t, _ in patterns_mod.KINDS}

    def ev_badge(r):
        e = r.get("event")
        return "" if not e else '<span class="newcash">NEW</span>' if e == "NEW" else f'<span class="newcash">JUST BROKE {"OUT" if r["status"] == "BREAKOUT" else "DOWN"}</span>'

    def dv_badge(r):
        x = r.get("brk_ratio")
        if r["status"] not in ("BREAKOUT", "BREAKDOWN") or x is None or pd.isna(x): return ""
        return (f'<span class="ptst up" title="Delivery on the break session against its own recent average">HIGH DELIVERY {x:.1f}×</span>' if r.get("confirmed")
                else f'<span class="ptst mut" title="Delivery on the break session against its own recent average">DELIVERY {x:.1f}×</span>')

    def start_on_confirmed(rows): return any(r.get("confirmed") for r in rows)

    RP = M.get("pattern_replay")

    def replay_html(kind, tf):
        """What past fresh breaks of this pattern went on to do over about one, two and three months (config/pattern_replay.json, run locally): breaks with high delivery on the break session
        first, then all breaks, beside the average stock."""
        if not RP: return ""
        base = RP.get("baseline") or {}; blocks = []
        have = [str(x) for x in (RP.get("horizons") or [20])]
        horizons = [(h, w) for h, w in (("20", "~1 month"), ("40", "~2 months"), ("60", "~3 months")) if h in have]
        for status in (("BREAKOUT",) if kind == "ascending" else ("BREAKDOWN",) if kind == "descending" else ("BREAKOUT", "BREAKDOWN")):
            g = RP["groups"].get(f"{tf}|{kind}|{status}")
            if not g: continue
            word = "breakouts" if status == "BREAKOUT" else "breakdowns"; way = "up" if status == "BREAKOUT" else "down"; rows = []
            for h, label in horizons:
                x = g.get(h); bs = base.get(h)
                if not x: continue
                good = lambda edge: "pup" if (edge > 1 if status == "BREAKOUT" else edge < -1) else "pdn" if (edge < -1 if status == "BREAKOUT" else edge > 1) else ""
                if x["n_conf"] >= 15 and x["avg_conf"] is not None:
                    conf = (f'<td>{x["n_conf"]}</td><td class="{good(x["median_conf"] - (bs["median"] if bs else 0))}"><b>{x["avg_conf"]:+.1f}%</b></td><td class="{good(x["median_conf"] - (bs["median"] if bs else 0))}"><b>{x["median_conf"]:+.1f}%</b></td><td><b>{x["right_conf"]:.0f}%</b></td>')
                else:
                    conf = f'<td>{x["n_conf"]}</td><td colspan="3" class="mut l">too few with that much follow-up to read</td>'
                allb = f'<td class="mut">{x["n"]}</td><td class="mut">{x["avg"]:+.1f}%</td><td class="mut">{x["median"]:+.1f}%</td><td class="mut">{x["right"]:.0f}%</td>' if x["n"] and x["avg"] is not None else '<td colspan="4"></td>'
                avg = f'<td class="mut">{bs["avg"]:+.1f}%</td><td class="mut">{bs["median"]:+.1f}%</td><td class="mut">{bs["up"]:.0f}% up</td>' if bs else '<td colspan="3"></td>'
                rows.append(f'<tr><td class="l">{label}</td>{conf}{allb}{avg}</tr>')
            head_ = [("AFTER THE BREAK", "l"), ("HIGH-DELIVERY BREAKS", ""), ("AVERAGE MOVE VS NIFTY", ""), ("MEDIAN", ""), (f"WENT {way.upper()}", ""), ("ALL BREAKS", ""), ("AVERAGE", ""), ("MEDIAN", ""), (f"WENT {way.upper()}", ""),
                     ("AVERAGE STOCK: AVERAGE", ""), ("MEDIAN", ""), ("UP", "")]
            blocks.append(f'<div class="ptrt"><b>Replay · past {tf} {word} on high delivery</b>{table(head_, rows)}</div>')
        return ('<div class="msum ptreplay">' + "".join(blocks) + f'<div class="mut">High delivery means delivered shares on the break session at least 1.25× their own recent average. Replayed over {RP["sessions"]} sessions to {esc(RP["asof"])}. Each break is counted once, at the moment it would have been visible; '
                'later horizons count only breaks with that much history after them. The average stock is every liquid stock sampled the same way. Overlapping windows, one market regime, no costs: a sanity check, not a forecast.</div></div>') if blocks else ""

    def digest():
        rows, parts = [], []
        for tf in ("daily", "weekly"):
            XX = P.get(tf)
            if not XX or not XX.get("compared"): continue
            marked = [r for kind, _, _ in patterns_mod.KINDS for r in XX["found"][kind] if r.get("event")]
            hi = sum(1 for r in marked if r.get("confirmed"))
            parts.append(f'{tf.title()}: <b>{XX["changes"]["new"]}</b> new, <b>{XX["changes"]["broke"]}</b> just broke, <b>{hi}</b> of them breaks on high delivery')
            for kind, title, _ in patterns_mod.KINDS:
                rows += [(r, tf, title) for r in XX["found"][kind] if r.get("event") and r.get("confirmed")]
        sh = M.get("shorts"); n_short = sum(int(bool(getattr(r, "new", False)) and bool(getattr(r, "fo", True))) for v in ((sh or {}).get("screens") or {}).values() for r in v["rows"].itertuples())
        cash = M.get("cash_accumulation"); n_cash = int(cash["new"].sum()) if cash is not None and len(cash) and "new" in cash else 0
        bases = M.get("breakout_bases"); n_fresh = int((bases["stage"] == "fresh").sum()) if bases is not None and len(bases) else 0
        if not parts and not n_short and not n_cash: return ""
        rows.sort(key=lambda x: (x[0]["event"] != "BROKE", -x[0].get("conv", 0)))
        chips = " ".join(f'<span class="ptdchip">{stk(r["sym"], M)} <span class="mut">{esc(title.title())} · {tf}</span> <span class="ptst {cls.get(r["status"], "mut")}">{"BROKE OUT" if r["status"] == "BREAKOUT" else "BROKE DOWN"} · {r["brk_ratio"]:.1f}× DELIVERY</span></span>' for r, tf, title in rows[:16])
        more = f' <span class="mut">and {len(rows) - 16} more</span>' if len(rows) > 16 else ""
        return ('<div class="card ptdigest"><div class="ititle">SINCE THE PREVIOUS SESSION</div>'
                f'<div>Patterns: {" · ".join(parts) or "no earlier scan to compare with"}. Short Ideas: <b>{n_short}</b> new today. Cash accumulation: <b>{n_cash}</b> new. Breakout bases: <b>{n_fresh}</b> fresh breakouts.</div>'
                + (f'<div class="ptdchips">{chips}{more}</div>' if rows else '<div class="mut">No fresh break on high delivery since the previous session.</div>') + '<div id="pt-wl" class="ptwl"></div></div>')

    def info(r, unit="sessions"):
        if r["kind"] == "rectangle":
            return (f'Range {r["bottom"]:,.0f} to {r["top"]:,.0f} ({r["height_pct"]:.0f}% tall) · {r["touches_flat"]} touches at the top, {r["touches_line"]} at the bottom · {r["days"]} {unit} · '
                    f'{r["position"]:.0f}% of the way up it · target {r["target"]:,.0f} ({(r["target"] / r["close"] - 1) * 100:+.0f}%) on a break {"up" if r["status"] in ("BREAKOUT", "AT TOP") else "down" if r["status"] in ("BREAKDOWN", "AT BOTTOM") else "either way"}')
        side = "Resistance" if r["kind"] == "ascending" else "Support"
        return (f'{side} {r["level"]:,.0f} ({r["touches_flat"]} touches) · {"rising lows" if r["kind"] == "ascending" else "falling highs"} ({r["touches_line"]} points) · {r["days"]} {unit} · '
                f'{r["height_pct"]:.0f}% tall · target {r["target"]:,.0f} ({(r["target"] / r["close"] - 1) * 100:+.0f}%)')

    def table_for(kind, rows, unit="sessions"):
        only = start_on_confirmed(rows)
        if not rows: return '<div class="card rempty">No stock matches these rules today.</div>'
        body = []
        for i, r in enumerate(rows):
            lvl = f'{r["bottom"]:,.0f} – {r["top"]:,.0f}' if kind == "rectangle" else f'{r["level"]:,.1f}'
            if kind == "rectangle":                              # the nearer side of the range is the trigger
                dist = min(((r["close"] / r["top"] - 1) * 100, (r["close"] / r["bottom"] - 1) * 100), key=abs)
            else:
                dist = (r["close"] / r["level"] - 1) * 100
            body.append(f'<tr data-status="{esc(r["status"])}" data-fo="{1 if r["fo"] else 0}" data-ev="{1 if r.get("event") else 0}" data-conf="{1 if r.get("confirmed") else 0}"{" hidden" if only and not r.get("confirmed") else ""}><td class="mut">{i + 1}</td><td class="l">{stk(r["sym"], M)}{" <span class=\"mut\">F&amp;O</span>" if r["fo"] else ""}</td>'
                        f'<td class="l"><span class="ptst {cls.get(r["status"], "mut")}">{esc(r["status"])}</span> {ev_badge(r)} {dv_badge(r)} {regime_badge(M, r["status"])}</td><td>{r["days"]}</td><td>{lvl}</td><td{heat(dist, 8)}>{pc(dist)}</td><td>{r["height_pct"]:.0f}%</td>'
                        f'<td>{r["touches_flat"]} / {r["touches_line"]}</td><td>{r["target"]:,.0f} <span class="mut">({pc((r["target"] / r["close"] - 1) * 100, 0)})</span></td>'
                        f'<td{heat(r["rs3m"], 30)}>{pc(r["rs3m"])}</td><td>{"–" if pd.isna(r["ratio"]) else f"{r["ratio"]:.2f}×"}</td><td>{"–" if r["status"] not in ("BREAKOUT", "BREAKDOWN") or pd.isna(r.get("brk_ratio", np.nan)) else f"{r["brk_ratio"]:.2f}×"}</td><td><b>{r.get("conv", 0)}</b><span class="mut">/5</span></td></tr>')
        headr = [("#", "mut"), ("STOCK", "l"), ("STATUS", "l"), (unit.upper(), ""), ("LEVEL" if kind != "rectangle" else "BOTTOM – TOP", ""), ("CLOSE VS TRIGGER", ""), ("HEIGHT", ""), ("TOUCHES", ""), ("TARGET", ""), ("VS NIFTY 3M", ""), ("DELIVERY NOW ÷ 20D", ""), ("DELIVERY ON THE BREAK", ""), ("SCORE", "")]
        return table(headr, body, "cashwatch ptable")

    def cards_for(kind, rows, XX, cap=30):
        only = start_on_confirmed(rows)
        out = []; total = len(rows); rows = [r for r in rows if r["status"] not in ("FORMING", "IN RANGE")]            # charts for the actionable ones; the rest stay in the table
        for r in rows[:cap]:
            ch = XX["charts"].get(r["sym"])
            if not ch or kind not in ch["patterns"]: continue
            pat = ch["patterns"][kind]; start = max(0, min(a[0] for ln in pat["lines"] for a in (ln["a"], ln["b"])) - 12)
            px1 = r["px1d"]
            out.append(f'<div class="card shcard" data-status="{esc(r["status"])}" data-fo="{1 if r["fo"] else 0}" data-ev="{1 if r.get("event") else 0}" data-conf="{1 if r.get("confirmed") else 0}"{" hidden" if only and not r.get("confirmed") else ""}><div class="shhead"><b>{stk(r["sym"], M)}</b><span class="mut">{r["close"]:,.2f}</span><span class="{"pup" if px1 >= 0 else "pdn"}">{pc(px1)}</span>'
                       f'{ev_badge(r)}{dv_badge(r)}{regime_badge(M, r["status"])}<span class="ptst {cls.get(r["status"], "mut")} shdays">{esc(r["status"])}</span></div><div class="shzones">{info(r, XX["cfg"].unit)}</div>{short_chart(r["sym"], ch, [], start=start, pattern=dict(pat, earlier=earlier_touches(ch, pat, start)[0]))}{earlier_touches(ch, pat, start)[1]}</div>')
        more = (f'<p class="desc">Charts for the {len(out)} stocks that have broken out or are at or near their trigger level; the {total - len(rows)} still forming or sitting mid-range are in the table only.'
                + (f' Showing the first {cap} of {len(rows)}.' if len(rows) > cap else "") + '</p>')
        legend = ('<div class="shlegend"><i class="shln" style="border-color:#ef5a4d"></i>Resistance <i class="shln" style="border-color:#2fbf71"></i>Support <i class="shln" style="border-color:#ffd17a;border-top-style:dashed"></i>Target '
                  f'<i class="shln a"></i>{XX["cfg"].name == "daily" and "50-day" or "10-week"} <i class="shln b"></i>{XX["cfg"].name == "daily" and "100-day" or "30-week"} <span class="mut">· circles are the swing points the lines are drawn through</span></div>')
        return legend + f'<div class="shgrid">{"".join(out)}</div>{more}' if out else ""

    TF = [("daily", "DAILY"), ("weekly", "WEEKLY")]

    def pane(kind, tf, XX):
        rows = XX["found"][kind]; unit = XX["cfg"].unit
        statuses = [st for st in ("BREAKOUT", "BREAKDOWN", "AT TOP", "AT BOTTOM", "SETUP", "IN RANGE", "FORMING") if any(r["status"] == st for r in rows)]
        n_conf = sum(1 for r in rows if r.get("confirmed")); on_conf = n_conf > 0
        chips = ('<div class="ptchips">'
                 + (f'<button type="button" class="ptchip{" on" if on_conf else ""}" data-st="CONF">HIGH-DELIVERY BREAKS {n_conf}</button>' if rows else "")
                 + f'<button type="button" class="ptchip{"" if on_conf else " on"}" data-st="ALL">ALL {len(rows)}</button>'
                 + "".join(f'<button type="button" class="ptchip" data-st="{st}">{st} {sum(1 for r in rows if r["status"] == st)}</button>' for st in statuses)
                 + ('<button type="button" class="ptchip" data-ev="1">NEW / JUST BROKE</button>' if any(r.get("event") for r in rows) else "")
                 + '<button type="button" class="ptchip" data-fo="1">F&amp;O ONLY</button></div>') if rows else ""
        return (f'<p class="desc">{len(rows)} found among {XX["scanned"]} stocks scanned on {tf} candles. Breaks with high delivery on the break session (at least 1.25× its own recent average) are shown first and are the default view; the other patterns are one click away. Ordered by status, then by a 0 to 5 score: a fresh break or a setup near the trigger, delivery at least 1.25× its average, relative strength leaning the pattern\'s way, and the other timeframe agreeing.</p>{replay_html(kind, tf)}{chips}{table_for(kind, rows, unit)}'
                + (f'<h3 class="fuh">CHARTS</h3>{cards_for(kind, rows, XX)}' if rows else ""))

    subs, views = [], ""
    for i, (kind, title, _) in enumerate(patterns_mod.KINDS if P else []):
        desc, rules = PATTERN_RULES[kind]
        have = [(tf, lbl) for tf, lbl in TF if P.get(tf)]
        weekly_note = (f'<li>Weekly candles: the same rules, counted in weeks. A swing point beats {patterns_mod.WEEKLY.k} weeks either side, a flat level\'s first and last touch are at least {patterns_mod.WEEKLY.gap} weeks apart, '
                       f'the pattern is {patterns_mod.WEEKLY.min_bars} to {patterns_mod.WEEKLY.max_bars} weeks old, and a break stays fresh for {patterns_mod.WEEKLY.recent} weeks. Every percentage in the rules is unchanged. The week in progress is the last candle.</li>')
        rule_html = '<details class="ptrules"><summary>HOW THIS PATTERN IS DEFINED</summary><ul>' + "".join(f'<li>{esc(x)}</li>' for x in rules) + weekly_note + '</ul></details>'
        tfbar = '<div class="ptfbar">' + "".join(f'<button type="button" class="ptfbtn{" on" if j == 0 else ""}" data-tf="{tf}">{lbl}</button>' for j, (tf, lbl) in enumerate(have)) + '</div>'
        panes = "".join(f'<div class="ptview" data-tf="{tf}"{"" if j == 0 else " hidden"}>{pane(kind, tf, P[tf])}</div>' for j, (tf, _) in enumerate(have))
        views += f'<div class="subview" data-sub="{kind}"{"" if i == 0 else " hidden"}><p class="desc">{esc(desc)}</p>{rule_html}{tfbar}{panes}</div>'
        subs.append((kind, title))
    first = not subs
    subs += [("bases", "BREAKOUT BASES"), ("shorts", "SHORT IDEAS")]
    views += (f'<div class="subview" data-sub="bases"{"" if first else " hidden"}><div id="p-bases">{_embed(tab_breakout_bases(M))}</div></div>'
              f'<div class="subview" data-sub="shorts" hidden>{_embed(tab_shorts(M))}</div>')
    live = P.get("daily") or P.get("weekly")
    meta = f'<div class="hmeta">As of <b>{live["asof"]:%d %b %Y}</b></div>' if live else ""
    gap = "" if P else '<div class="card rempty">Pattern scans need about 120 sessions of history, so the triangle and rectangle views are not available yet.</div>'
    return head + meta + regime_banner(M) + (note if P else gap) + digest() + _subtabs(subs) + views


def tab_calls(M):
    return (_subtabs([("calls", "CALLS"), ("guidance", "GUIDANCE SHIFTS"), ("results", "UPCOMING RESULTS")]) + f'<div class="subview" data-sub="calls">{tab_call_library(M)}</div>'
            f'<div class="subview" data-sub="guidance" hidden>{tab_guidance_shifts(M)}</div><div class="subview" data-sub="results" hidden>{tab_upcoming_results(M)}</div>')


def render(M, asof_text):
    M["hist_label"] = f"{max(1, round(M['N'] / 252))}Y"
    sj = stocks_json(M); sj["today"] = today_data(M)
    data = json.dumps(sj, separators=(",", ":"))
    choices = [("top1000", "TOP 1000"), ("nifty500", "NIFTY 500"), ("smallcap250", "NIFTY SMALLCAP 250"),
               ("nifty250", "NIFTY 100 + MIDCAP 150"), ("nifty100", "NIFTY 100"), ("fo", "F&O")]
    choices = [(k, label) for k, label in choices if M["memberships"].get(k)]
    def views(fn):
        return "".join(f'<div class="uview" data-u="{k}"{("" if k == "top1000" else " hidden")}>{fn(M, allowed=M["memberships"][k])}</div>' for k, _ in choices)
    archived = ARCHIVED_TABS                                   # tabs kept in the code but not shown or built; see README to bring one back
    candidates = [("today", "TODAY", lambda: tab_today(M)), ("stocks", "STOCKS", lambda: tab_stocks(M)), ("high52", "52W HIGHS", lambda: tab_52w_highs(M)),
                  ("signals", "SIGNAL CONFLUENCE", lambda: views(tab_signal_confluence)), ("patterns", "TECHNICAL PATTERNS", lambda: tab_patterns(M)),
                  ("cash", "CASH ACCUMULATION", lambda: tab_cash_accumulation(M)), ("calls", "CALL LIBRARY", lambda: tab_calls(M)),
                  ("exchange", "EXCHANGE TRACKER", lambda: tab_exchange(M)), ("credit", "PEER RADAR", lambda: tab_credit(M)),
                  ("alt", "ALTERNATIVE DATA", lambda: tab_alt_data(M)), ("timeline", "TIMELINE", lambda: tab_timeline(M))]
    M["_ntabs"] = len([c for c in candidates if c[0] not in archived])
    panels = [(k, lbl, build()) for k, lbl, build in candidates if k not in archived]
    nav = "".join(f'<button class="tab{" on" if i == 0 else ""}{" exp" if k in ("alt", "shorts", "patterns") else ""}" data-t="{k}"{" title=\"Experimental\"" if k in ("alt", "shorts", "patterns") else ""}>{lbl}</button>' for i, (k, lbl, _) in enumerate(panels))
    LAZY_PANELS = ("patterns", "calls", "high52", "exchange", "timeline")          # held as inert text until their tab is first opened: most of the page's HTML, none of it in the DOM at start
    lazy = lazy_panel
    body = "".join(f'<section class="panel" id="p-{k}"{"" if i == 0 else " hidden"}{" data-lazy=\"1\"" if k in LAZY_PANELS and i else ""}>{lazy(k, h) if k in LAZY_PANELS and i else h}</section>' for i, (k, _, h) in enumerate(panels))
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
.basefilters{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:13px 0 10px}.basefilter{display:flex;align-items:center;gap:7px;border:1px solid #3b3b3b;background:#111;color:var(--mut);padding:8px 10px;font:800 9px var(--sans);letter-spacing:.07em;cursor:pointer}.basefilter i{width:8px;height:8px;border:1px solid #666;background:transparent}.basefilter.on{color:var(--ink);border-color:#74746f}.basefilter.on i{background:var(--g);border-color:var(--g);box-shadow:0 0 0 2px rgba(63,191,122,.14)}.basefilter:focus-visible{outline:2px solid var(--am);outline-offset:2px}.basecount{margin-left:auto;color:var(--mut);font:700 10px var(--mono);white-space:nowrap}
.exheadline{display:flex;gap:28px;margin:12px 0 14px}.exheadline div{display:flex;flex-direction:column}.exheadline span{font:700 9px var(--sans);letter-spacing:.1em;color:var(--mut)}.exheadline b{font:700 17px var(--mono)}
.exstatus{display:inline-block;margin:0 0 9px;padding:5px 8px;border:1px solid #3c3c38;color:#b6b6af;font:700 9px var(--mono);letter-spacing:.04em}
.exswitch{display:flex;width:max-content;border:1px solid #444;margin:13px 0 12px}.exswitchbtn{border:0;background:#111;color:var(--mut);padding:8px 20px;font:800 10px var(--sans);letter-spacing:.08em;cursor:pointer}.exswitchbtn.on{background:#f4f4f0;color:#090909}
.excard{padding:0;margin-bottom:12px;overflow:hidden}.excard .ch{display:flex;justify-content:flex-start;align-items:center;gap:18px;min-height:42px;padding:10px 12px 8px;background:#101010;border-bottom:1px solid var(--line);overflow:hidden}.excard .ch>*{white-space:nowrap}.excard .ct{flex:0 0 auto;font-size:13px;line-height:1;font-weight:800;letter-spacing:.035em}.excard .ch>span:last-child{min-width:0;overflow:hidden;text-overflow:ellipsis;font-size:10px}.exsvg{width:100%;height:auto;display:block;background:linear-gradient(180deg,#13171c 0%,#101010 100%)}.exsvg text{fill:var(--mut);font:10px var(--mono)}.exsvg line{stroke:var(--line)}
.exarea{fill:url(#turnoverFill)}.exto{fill:none;stroke:#68b4ff;stroke-width:2.7;filter:drop-shadow(0 0 3px rgba(90,169,255,.35))}.expx{fill:none;stroke:#f1ae39;stroke-width:2.7;filter:drop-shadow(0 0 3px rgba(232,169,58,.25))}.exgridline{stroke:#34383d!important;stroke-width:1}.exaxis{fill:#88bdf0!important}.exaxis.price{fill:#d8a74f!important}.exkey{display:inline-block;width:17px;border-top:2px solid;margin:0 5px 2px 12px}.exkey.to{border-color:#5aa9ff}.exkey.px{border-color:var(--am)}
.exlayout{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;align-items:stretch}.exlayout>*{min-width:0}.exlayout>.excard{height:100%;margin-bottom:0}.exranges{display:flex;gap:5px;padding:0 18px 10px;flex-wrap:wrap}.exrangesbelow{grid-column:1;padding:0;align-self:start}.exrbtn{border:1px solid var(--line);background:transparent;color:var(--mut);font:800 9px var(--sans);letter-spacing:.08em;padding:6px 10px;cursor:pointer}.exrbtn:hover{color:var(--ink);border-color:var(--mut)}.exrbtn.on{background:var(--am);border-color:var(--am);color:#090909}.exbar{fill:#4e85d8;transition:opacity .12s}.exbar:hover,.exbar:focus{opacity:.72;stroke:#fff;stroke-width:1;outline:none}.exbar.month{fill:#607fc2}.exbar.latest{fill:var(--am)}.exbargrid{stroke:#30343a!important;stroke-width:1}.excompare{fill:var(--ink)!important;font-weight:800;letter-spacing:.04em}.excompare.up{fill:var(--g)!important}.excompare.down{fill:var(--r)!important}.monthtag{fill:var(--ink)!important;font-weight:700}.exbarhover{display:none;fill:var(--ink)!important;font-weight:800;paint-order:stroke;stroke:#101010;stroke-width:4px;stroke-linejoin:round;pointer-events:none}.exbaritem:hover .exbarhover,.exbaritem:focus-within .exbarhover{display:block}.excomment{margin:0 0 12px;padding:15px 16px;background:#101010;border-left:4px solid var(--am)}.excomment h3{margin:0 0 8px;font:800 10px var(--sans);letter-spacing:.11em}.excomment ul{margin:0 0 10px;padding-left:20px}.excomment li{margin:6px 0}.excomment a{font:700 9px var(--sans);letter-spacing:.08em;color:var(--am)}
@media(max-width:1100px){.exlayout{grid-template-columns:1fr 1fr}.subtabs{max-width:100%;overflow-x:auto}.exmain{grid-column:1/-1}}@media(max-width:700px){.exlayout{grid-template-columns:1fr}.exmain{grid-column:auto}.exheadline{gap:16px;flex-wrap:wrap}}
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
.fochip{border:0;background:#111;color:var(--mut);padding:8px 12px;font:800 10px var(--sans);letter-spacing:.06em;cursor:pointer}.fochip.on{background:#f4f4f0;color:#090909}.regime{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline;margin:0 0 18px;padding:10px 14px;border-left:3px solid var(--g);background:rgba(63,191,122,.08);font-size:12.5px}.regime b{font:800 10px var(--sans);letter-spacing:.1em}.regime.caution{border-color:var(--am);background:rgba(232,169,58,.12)}.regime.weak{border-color:var(--r);background:rgba(239,90,77,.12)}.regime small{flex-basis:100%;font:10px var(--mono)}.ptfull{font:800 9px var(--sans);letter-spacing:.08em;margin:8px 0 2px}.tlhero h1{font-size:clamp(32px,5.5vw,54px)}.tlactivity{display:block;width:100%;height:auto;background:var(--panel);padding:8px}.tlgone{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 24px;font-size:13px}@media (max-width:700px){.tlgone{grid-template-columns:1fr}}.tlgone li{padding:6px 0;border-bottom:1px solid var(--line)}.tlgone a{color:#ff8f84;cursor:pointer}.tlfilters{display:flex;flex-wrap:wrap;border:1px solid #444}.tlfilter{border:0;background:#111;color:var(--mut);padding:8px 13px;font:800 10px var(--sans);letter-spacing:.07em;cursor:pointer}.tlfilter.on{background:#f4f4f0;color:#090909}.tlphase{margin:0 0 44px}.tlphase>header{display:grid;grid-template-columns:auto 1fr auto;gap:2px 18px;align-items:baseline;margin:0 0 22px;padding:0 0 14px;border-bottom:1px solid var(--line)}.tlphase h3{margin:0;font:800 20px var(--sans)}.tlphase header p{grid-column:2/4;margin:0;color:#b9b9b2;font-size:13px;line-height:1.55;max-width:720px}.tlspan{font:800 10px var(--sans);letter-spacing:.14em;color:#ffd17a}.tlcount{font:800 9px var(--sans);letter-spacing:.1em}.tl{list-style:none;margin:0;padding:0;position:relative}.tl{display:grid;grid-template-columns:1fr 1fr}.tl::before{content:"";position:absolute;left:50%;top:0;bottom:0;width:2px;margin-left:-1px;background:#333}.tlnode{position:relative;grid-column:1;grid-row:span 2;padding:0 34px 26px 0;box-sizing:border-box}.tlnode:nth-child(even){grid-column:2;padding:0 0 26px 34px}.tllegend{display:flex;flex-wrap:wrap;gap:4px 16px;margin-top:8px;font-size:11px}.tllegend b{color:#ffd17a}.tldot{position:absolute;top:18px;right:-7px;width:14px;height:14px;border-radius:50%;background:var(--bg);border:3px solid #888}.tlnode:nth-child(even) .tldot{right:auto;left:-7px}.tlcard{background:var(--panel);padding:14px 16px;border-top:2px solid #444}.tlmeta{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center;margin-bottom:6px}.tlmeta time{font:700 11px var(--mono);color:var(--mut)}.tlkind{font:800 9px var(--sans);letter-spacing:.1em;padding:2px 7px;border:1px solid currentColor}.tltab{font:700 10px var(--mono);color:var(--mut)}.tlcard h4{margin:0 0 6px;font:800 16px/1.3 var(--sans)}.tlwhat{margin:0 0 10px;font-size:13px;line-height:1.55;color:#cfcfc8}.tlwhy{border-left:2px solid #e8a93a;padding:2px 0 2px 11px;font-size:12.5px;line-height:1.55;color:#e8e8e2}.tlwhy span{display:block;font:800 9px var(--sans);letter-spacing:.12em;color:#ffd17a;margin-bottom:3px}.tlprs{display:flex;flex-wrap:wrap;gap:4px 8px;margin-top:10px}.tlpr{font:700 10px var(--mono);color:var(--mut);text-decoration:none}a.tlpr:hover{color:#ffd17a}.k-added .tlkind,.k-added .tldot{color:#4fd18b;border-color:#4fd18b}.k-added .tlcard{border-top-color:#4fd18b}.k-improved .tlkind,.k-improved .tldot{color:#ffd17a;border-color:#e8a93a}.k-improved .tlcard{border-top-color:#e8a93a}.k-fixed .tlkind,.k-fixed .tldot{color:#6db0ff;border-color:#6db0ff}.k-fixed .tlcard{border-top-color:#6db0ff}.k-removed .tlkind,.k-removed .tldot{color:#ff7a5c;border-color:#ef5a4d}.k-removed .tlcard{border-top-color:#ef5a4d;background:rgba(239,90,77,.06)}.k-infra .tlkind,.k-infra .tldot{color:#b58cff;border-color:#b58cff}.k-infra .tlcard{border-top-color:#b58cff}.tlnode.auto .tlcard{border-style:dashed;background:transparent}.tlnode.flash .tlcard{outline:2px solid #ffd17a}.tlnode[hidden]{display:none}@media (max-width:800px){.tl{display:block}.tl::before{left:7px}.tlnode,.tlnode:nth-child(even){padding:0 0 22px 30px}.tldot,.tlnode:nth-child(even) .tldot{left:0;right:auto}.tlphase>header{grid-template-columns:1fr}.tlphase header p{grid-column:1}}.tdclusters{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}@media (max-width:900px){.tdclusters{grid-template-columns:1fr}}.tdclus{background:var(--panel);border-left:4px solid #e8a93a;padding:16px 18px}.tdclus.abovenormal{border-color:#4fd18b;background:linear-gradient(90deg,rgba(79,209,139,.08),var(--panel) 40%)}.tdclus.light{border-color:#777}.tdclh{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 14px;margin-bottom:10px}.tdclh h3{margin:0;flex:1 1 auto;font:800 20px var(--sans)}.tdclcount{font:800 10px var(--sans);letter-spacing:.1em;color:#ffd17a}.tdmems{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}@media (max-width:520px){.tdmems{grid-template-columns:repeat(2,minmax(0,1fr))}}.tdmem{display:flex;flex-direction:column;gap:4px;padding:8px;background:#191919;font-size:12px;min-width:0}.tdmem.up{background:rgba(79,209,139,.08)}.tdmore{grid-column:1/-1;flex-direction:row;flex-wrap:wrap;align-items:center;gap:4px 14px;font-size:11.5px;background:transparent;padding:4px 2px}.tdmore .tdlab{margin:0}.tdnm small{font:700 9px var(--mono);color:var(--mut)}.tdnm small.up{color:#4fd18b}.tdnm small.hotd{color:#4fd18b}.tdmh{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:2px 6px}.tdmh .ptst{font-size:8px;padding:1px 5px}.minichart{display:block;width:100%;height:auto;background:#101010}.tdmd{text-align:right;font:700 11px var(--mono)}.tdmd small{font:600 9px var(--sans);color:var(--mut);letter-spacing:.05em}.tdmd.hotd{color:#4fd18b}.tdcltone{margin:10px 0 0;font-size:12.5px;line-height:1.55;color:#cfcfc8}.tdclusters.compact{margin:0 0 14px}.fobar{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;margin:0 0 10px;font:800 10px var(--sans);letter-spacing:.08em}.fotag{display:inline-block;margin-left:6px;padding:1px 6px;border:1px solid #444;font:800 8px var(--sans);letter-spacing:.08em;color:var(--mut)}.today{max-width:1180px;margin:0 auto}.tdhero{padding:44px 6px 34px;margin:0 0 8px;border-bottom:1px solid var(--line);background:radial-gradient(900px 260px at 0 0,rgba(232,169,58,.14),transparent 70%)}.tdkick{font:800 11px var(--sans);letter-spacing:.2em;color:#ffd17a;margin-bottom:14px}.tdhero h1{margin:0 0 16px;font:800 clamp(34px,6vw,60px)/1.04 var(--sans);letter-spacing:-.02em}.tdlead{max-width:760px;margin:0 0 26px;font-size:clamp(15px,2vw,19px);line-height:1.55;color:#cfcfc8}.tdlead b{color:var(--ink)}.tdtiles{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line)}.tdtile{background:var(--bg);padding:16px 14px}.tdtile b{display:block;font:800 28px var(--mono);margin-bottom:4px}.tdtile span{font:800 9px var(--sans);letter-spacing:.1em;color:var(--mut)}@media (max-width:900px){.tdtiles{grid-template-columns:repeat(3,minmax(0,1fr))}}@media (max-width:520px){.tdtiles{grid-template-columns:repeat(2,minmax(0,1fr))}}.tdsec{padding:34px 6px 8px}.tdsech{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:6px 16px;margin-bottom:16px}.tdsech h2{margin:0;font:800 24px var(--sans);letter-spacing:-.01em}.tdlink{font:800 10px var(--sans);letter-spacing:.08em;color:#ffd17a;cursor:pointer;text-decoration:none}.tdlink:hover{text-decoration:underline}.tdfocusgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}@media (max-width:1000px){.tdfocusgrid{grid-template-columns:1fr}}.tdfocus{background:var(--panel);border-top:3px solid #555;padding:14px 14px 12px;min-width:0}.tdfocus.up{border-color:#4fd18b}.tdfocus.down,.tdfocus.short{border-color:#ff7a5c}.tdfocus p{margin:10px 0 0;font-size:12.5px;line-height:1.55;color:#c9c9c2}.tdfh{display:flex;flex-direction:column;gap:4px;margin-bottom:8px}.tdfh h3{margin:0;font:800 20px var(--sans)}.tdtag{font:800 9px var(--sans);letter-spacing:.12em;color:var(--mut)}.tdfocus.up .tdtag{color:#4fd18b}.tdfocus.down .tdtag,.tdfocus.short .tdtag{color:#ff7a5c}.tdchart svg{width:100%;height:auto;display:block}.tdfocus .shcard{background:none;padding:0;border:0}.tdfocus .shgrid{display:block;margin:0}.tdfocus .shsvg{width:100%}.tdactgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}@media (max-width:900px){.tdactgrid{grid-template-columns:1fr}}.tdact{display:block;background:var(--panel);padding:16px;text-decoration:none;color:var(--ink);cursor:pointer;border-left:3px solid #333}.tdact:hover{border-color:#e8a93a}.tdlab{display:block;font:800 9px var(--sans);letter-spacing:.12em;color:var(--mut);margin-bottom:6px}.tdbig{display:block;font:800 26px var(--mono)}.tdmeta{font:800 12px var(--mono)}.tdspark{display:block;width:100%;height:46px;margin:10px 0 6px}.tdact p{margin:6px 0;font-size:12px;line-height:1.5;color:#c9c9c2}.tdcons{margin:14px 0 0;font-size:13px;line-height:1.6;color:#cfcfc8;max-width:820px}.tdchips{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}@media (max-width:900px){.tdchips{grid-template-columns:repeat(2,minmax(0,1fr))}}.tdchip{background:var(--panel);padding:12px;display:flex;flex-direction:column;gap:4px;font-size:11px;border-top:2px solid #ff7a5c}.tdchip b{font-size:14px}.tdsmall{margin:14px 0 0;font-size:12px;line-height:2}.tdpill{display:inline-block;border:1px solid #333;padding:2px 9px;margin:0 2px;font-size:11px}.tdcall{background:var(--panel);border-left:3px solid #e8a93a;padding:18px 20px}.tdcallh{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 14px;align-items:baseline}.tdcallh h3{margin:0;font:800 18px var(--sans)}.tdcall blockquote{margin:14px 0;padding:0 0 0 14px;border-left:2px solid #444;font-size:14px;line-height:1.6;color:#dcdcd5;max-width:860px}.tdcall cite{display:block;margin-top:6px;font:11px var(--mono);color:var(--mut);font-style:normal}.tdcallf{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;font-size:12.5px;line-height:1.5;color:#c9c9c2}@media (max-width:700px){.tdcallf{grid-template-columns:1fr}}.tdrest{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}@media (max-width:800px){.tdrest{grid-template-columns:1fr}}.tdrest p{margin:4px 0 6px;line-height:2}.guidancerow{display:flex;flex-wrap:nowrap;gap:6px 12px;align-items:center;border-left:3px solid var(--g);background:rgba(63,191,122,.16);padding:8px 10px;margin-bottom:8px;font-size:12px;white-space:nowrap;overflow-x:auto}.guidancerow>*{flex:0 0 auto}.guidancerow.reduction,.guidancerow.downgrade{border-color:var(--r);background:rgba(239,90,77,.16)}.guidancerow button{margin-left:auto;cursor:pointer;white-space:nowrap}.guidancerow small{color:var(--mut)}#guidance-row[hidden]{display:none}.guidancechange{border-left:3px solid var(--g);padding:10px;margin:8px 0;background:var(--panel);overflow-wrap:anywhere}.guidancechange.reduction,.guidancechange.downgrade{border-color:var(--r)}.guidancechange summary{cursor:pointer}.guidancechange blockquote{margin:8px 0;white-space:pre-wrap}.guidancechange:focus,.guidancerow button:focus-visible{outline:2px solid #ffd17a;outline-offset:3px}.outlookrow{display:flex;flex-wrap:nowrap;gap:6px 12px;align-items:center;border-left:3px solid #777;background:var(--panel);padding:8px 10px;margin-bottom:8px;font-size:12px;white-space:nowrap;overflow-x:auto}.outlookrow>*{flex:0 0 auto}.outlookrow small{color:var(--mut)}.outlookrow button{margin-left:auto;cursor:pointer}#outlook-row[hidden]{display:none}.outlookrow.bullish{border-color:#1fd07a;background:rgba(31,208,122,.24)}.outlookrow.optimistic{border-color:var(--g);background:rgba(63,191,122,.16)}.outlookrow.positive{border-color:#7fbf9a;background:rgba(127,191,154,.1)}.outlookrow.muted{border-color:#8b8b86;background:rgba(139,139,134,.12)}.outlookrow.cautious{border-color:var(--am);background:rgba(232,169,58,.15)}.outlookrow.bearish{border-color:var(--r);background:rgba(239,90,77,.2)}.olab{font:800 10px var(--sans);letter-spacing:.06em}.olab.bullish{color:#1fd07a}.olab.optimistic{color:var(--g)}.olab.positive{color:#9fd4b4}.olab.muted{color:var(--mut)}.olab.cautious{color:var(--am)}.olab.bearish{color:var(--r)}#callintel{margin-top:10px}.tab.xred{color:#ff6b5e;background:rgba(239,90,77,.12);box-shadow:inset 0 -2px rgba(239,90,77,.65)}.tab.xred.on{background:#ef5a4d;color:#0a0a0a;box-shadow:none}.expbadge.red{border-color:rgba(239,90,77,.75);background:rgba(239,90,77,.16);color:#ff8f84}.expnote.red{border-left-color:var(--r);background:rgba(239,90,77,.08)}.btsum{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 8px}.vd{display:inline-block;padding:3px 8px;font:800 10px var(--sans);letter-spacing:.05em;border:1px solid currentColor;white-space:nowrap}.vd-works{color:#4fd18b;background:rgba(79,209,139,.14)}.vd-some{color:#c9d86a;background:rgba(201,216,106,.1)}.vd-could{color:#6db0ff;background:rgba(109,176,255,.1)}.vd-doesnt{color:#9a9a94}.vd-inverse{color:#ff7a5c;background:rgba(255,122,92,.12)}.vd-nodata{color:#6b6b66;border-style:dashed}.shgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:8px}@media (max-width:1000px){.shgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:640px){.shgrid{grid-template-columns:1fr}}.shcard{padding:8px 10px;margin:0;min-width:0}.shhead{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline;font-size:12px}.shhead .shdays{margin-left:auto;font-size:10px}.shmarks{font-size:10px;color:var(--mut);margin:2px 0 4px}.shkey{display:inline-block;width:9px;height:9px;margin:0 4px 0 8px;vertical-align:-1px}.shkey:first-child{margin-left:0}.shzones{font-size:10px;margin:0 0 4px}.shsvg{display:block;width:100%;height:auto}.shlegend{font-size:11px;margin:6px 0 8px;display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center}.shln{display:inline-block;width:16px;height:0;border-top:2px solid;margin-right:5px;vertical-align:middle}.shln.w{border-color:#f1f1ec}.shln.a{border-color:#e8a93a;border-top-style:dashed}.shln.b{border-color:#5aa9ff;border-top-style:dashed}.creditframe{display:block;width:100%;height:760px;border:0;background:#0a0a0a}.exwdwrap{width:50%;margin-top:26px}@media (max-width:900px){.exwdwrap{width:100%}}.exwd{margin:0}.exwd .ch{flex-wrap:wrap;overflow:visible}.exwdctl{display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:11px;color:var(--mut)}.exsel{background:#101010;color:var(--ink);border:1px solid #444;padding:6px 8px;font:600 12px var(--mono)}.exwd .msum{padding:4px 12px}.exwd svg{margin:0 6px}.exlayout+.excomment{margin-top:22px}.ptst{display:inline-block;padding:2px 8px;font:800 10px var(--sans);letter-spacing:.05em;border:1px solid currentColor;white-space:nowrap}.ptst.up{color:#4fd18b;background:rgba(79,209,139,.14)}.ptst.down{color:#ff7a5c;background:rgba(255,122,92,.12)}.ptst.near{color:#ffd17a;background:rgba(255,209,122,.1)}.ptst.mut{color:#9a9a94}.ptfbar{display:flex;width:max-content;border:1px solid #444;margin:10px 0 4px}.ptfbtn{border:0;background:#111;color:var(--mut);padding:8px 20px;font:800 10px var(--sans);letter-spacing:.08em;cursor:pointer}.ptfbtn.on{background:#e8a93a;color:#0a0a0a}.ptchips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 10px}.ptchip{border:1px solid #444;background:#111;color:var(--mut);padding:6px 11px;font:800 10px var(--sans);letter-spacing:.06em;cursor:pointer}.ptchip.on{background:#f4f4f0;color:#090909}.ptrules{margin:4px 0 6px;font-size:12px;color:var(--mut)}.ptrules summary{cursor:pointer;font:800 10px var(--sans);letter-spacing:.08em}.ptrules ul{margin:6px 0 0;padding-left:18px;line-height:1.5}.ptable tr[hidden],.shcard[hidden]{display:none}.ptpanels{margin-bottom:14px}.ptpanel{background:#191919;border-left:3px solid #e8a93a;padding:8px 9px 7px;margin:0 0 10px}.pthd{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px;font-size:11px;letter-spacing:.04em}.patsvg{display:block;width:100%;height:auto}.ptdv{margin:0 0 4px}.ptdet{font:10px var(--mono);color:var(--mut);line-height:1.5;margin-top:4px}.ptdigest{margin:0 0 12px;font-size:12px;line-height:1.7}.ptdchips{display:flex;flex-wrap:wrap;gap:6px 10px;margin-top:6px}.ptdchip{border:1px solid #333;padding:2px 8px;font-size:11px}.ptwl{margin-top:8px;padding-top:6px;border-top:1px solid var(--line)}.ptreplay{padding:6px 0;line-height:1.6}.ptrt{margin:0 0 10px}.ptrt table{font-size:11px}.ptrt th,.ptrt td{padding:5px 7px}.screensrow{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center;margin:0 0 10px;padding:8px 10px;background:var(--panel);border-left:3px solid #e8a93a}.scrlab{font:800 10px var(--sans);letter-spacing:.1em}.scrchip{border:1px solid currentColor;background:transparent;font:11px var(--mono);padding:3px 9px;cursor:pointer;color:var(--ink)}.scrchip b{font-weight:800}.scrchip i{font-style:normal;opacity:.85}.scrchip small{opacity:.75}.scrchip.up{color:#4fd18b;background:rgba(79,209,139,.1)}.scrchip.down{color:#ff7a5c;background:rgba(255,122,92,.1)}.scrchip.near{color:#ffd17a;background:rgba(255,209,122,.08)}.scrchip.mut{color:#9a9a94}.scrchip:hover{filter:brightness(1.25)}#screens-row[hidden]{display:none}.btrow{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;padding:5px 0;border-top:1px solid var(--line);font-size:11px}.btrow:first-of-type{border-top:0}.btrow b{min-width:86px}.btrow svg{margin-left:auto}.btbands{display:flex;justify-content:flex-end}.btlab{display:flex;width:220px;font:9px var(--mono);color:var(--mut)}.btlab span{width:55px;text-align:center}.mgrid.c4{grid-template-columns:repeat(2,minmax(0,1fr))}@media (max-width:700px){.mgrid.c4{grid-template-columns:1fr}}.mgrid{display:grid;gap:10px;margin-bottom:6px}.mgrid.c3{grid-template-columns:repeat(3,minmax(0,1fr))}.mchart{background:var(--panel);padding:9px 9px 7px;min-width:0;margin-bottom:6px}.mtitle{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:4px;font-size:12px;letter-spacing:.06em}.mtitle b{font:800 12px var(--sans)}.ycbox{position:relative;min-height:150px}.ycbox svg{display:block;width:100%;height:auto}.hctl .seg{font:800 10px var(--sans);letter-spacing:.06em;padding:7px 12px}.ytip{position:absolute;top:4px;background:#0d0d0d;border:1px solid #444;padding:6px 8px;font:10px var(--mono);pointer-events:none;min-width:130px;z-index:2}.msum{font:11px var(--mono);line-height:1.6;color:var(--mut);margin-top:2px}.ylegendrow{display:inline-flex;flex-wrap:wrap;gap:8px;align-items:center;margin-left:6px;font-size:11px}@media (max-width:1000px){.mgrid.c3{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:640px){.mgrid.c3{grid-template-columns:1fr}}.mgrid.c2{grid-template-columns:repeat(2,minmax(0,1fr))}@media (max-width:640px){.mgrid.c2{grid-template-columns:1fr}}.mgrid.c21{grid-template-columns:2fr 1fr}@media (max-width:900px){.mgrid.c21{grid-template-columns:1fr}}.pco{cursor:pointer;color:var(--ink)}.pco:hover{text-decoration:underline}.pup{color:#4fd18b}.pdn{color:#ff7a5c}.ppick{cursor:pointer;color:var(--ink)}.ppick:hover{text-decoration:underline}.pnote{margin:8px 0 0;font-size:11px;line-height:1.5}#pchart{position:relative;min-height:240px}#pchart svg{display:block;max-width:100%}.htipbox{position:absolute;top:8px;background:#0d0d0d;border:1px solid #444;padding:7px 9px;font:11px var(--mono);pointer-events:none;min-width:150px;z-index:2}.expnote code{font:11px var(--mono);color:#ffd17a}.tab.exp{color:#e8b04d;background:rgba(232,169,58,.1);box-shadow:inset 0 -2px rgba(232,169,58,.55)}.tab.exp.on{background:#e8a93a;color:#0a0a0a;box-shadow:none}.expbadge{display:inline-block;margin-left:12px;padding:3px 8px;border:1px solid rgba(232,169,58,.6);background:rgba(232,169,58,.14);color:#ffd17a;font:800 9px var(--sans);letter-spacing:.12em;vertical-align:middle}#p-alt h2{margin-top:16px}.expnote{border-left:3px solid var(--am);background:rgba(232,169,58,.08);padding:9px 12px;margin:0 0 14px;font-size:12px;line-height:1.5;color:#c9c9c2;max-width:1100px}.hmeta{margin:0 0 10px;color:var(--mut);font:11px var(--mono)}.hmeta b{color:var(--ink)}.hcards{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:6px}.hcard{background:var(--panel);border-top:3px solid #555;padding:11px 12px;min-width:0}.hcard h4{margin:0 0 4px;font:800 11px var(--sans);letter-spacing:.1em;display:flex;justify-content:space-between}.hcard h4 small{color:var(--mut);font-weight:600;letter-spacing:.04em}.hbig{font:800 26px var(--mono);margin:2px 0}.hsub{color:var(--mut);font-size:11px;margin-bottom:8px;line-height:1.35}.hrow{display:flex;justify-content:space-between;gap:8px;padding:5px 0;border-top:1px solid var(--line);font:11px var(--mono)}.hrow span{color:var(--mut);font-family:var(--sans)}.hhot{color:#ff7a5c}.hcool{color:#6db0ff}.hflat{color:var(--mut)}.hctl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 10px;font-size:11px}.hctl select{background:#101010;color:var(--ink);border:1px solid #444;padding:7px 8px;font:600 12px var(--mono)}.hctl .seg.on{background:#f4f4f0;color:#0a0a0a}.hchartcard{padding:8px}#hchart{position:relative;min-height:240px}#hchart svg{display:block;max-width:100%}#htip{position:absolute;top:8px;background:#0d0d0d;border:1px solid #444;padding:7px 9px;font:11px var(--mono);pointer-events:none;min-width:150px;z-index:2}#hlegend{display:flex;flex-wrap:wrap;gap:12px;align-items:center;padding:6px 4px 2px;font-size:11px}.hleg{background:none;border:0;color:var(--ink);cursor:pointer;font:700 12px var(--mono);display:inline-flex;gap:6px;align-items:center;padding:2px 4px}.hleg i{display:inline-block;width:16px;height:3px}.hleg.off{opacity:.35;text-decoration:line-through}.hsumbox{background:var(--panel);border-left:3px solid #ff7a3d;padding:10px 12px;margin-top:8px;font-size:12px;line-height:1.6}.hverdict{font:800 15px var(--sans);margin:4px 0 6px}.hgrid th,.hgrid td{padding:5px 4px;font-size:11px}.hgrid td.hc{text-align:center;min-width:34px;font:600 10px var(--mono)}.hgrid tr.hfirst td{border-top:2px solid #333}.hpick{cursor:pointer;color:var(--ink);text-decoration:none}.hpick:hover{text-decoration:underline}@media (max-width:900px){.hcards{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:480px){.hcards{grid-template-columns:1fr}}.resultrow{display:flex;flex-wrap:nowrap;gap:6px 12px;align-items:center;border-left:3px solid var(--am);background:rgba(232,169,58,.14);padding:8px 10px;margin-bottom:8px;font-size:12px;white-space:nowrap;overflow-x:auto}.resultrow>*{flex:0 0 auto}.resultrow.soon{background:rgba(232,169,58,.26)}.resultrow b{color:#ffd17a}.resultrow small{color:var(--mut)}.resultrow a{color:#ffd17a;margin-left:auto}#result-row[hidden]{display:none}.urbar{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:0 0 12px}.urgrp{display:flex;border:1px solid #444}.urchip{border:0;background:#111;color:var(--mut);padding:8px 12px;font:800 10px var(--sans);letter-spacing:.06em;cursor:pointer}.urchip.on{background:#f4f4f0;color:#090909}.urchip:focus-visible{outline:2px solid var(--am);outline-offset:2px}#ur-q{background:#101010;color:var(--ink);border:1px solid #444;padding:8px 10px;font:600 12px var(--mono);min-width:200px}.rname{font:10px var(--sans);margin-top:2px;white-space:normal}.soonc{color:#ffd17a;font-weight:700}.urtable tr[hidden]{display:none}.fuh{margin:22px 0 8px;font:800 10px var(--sans);letter-spacing:.1em;color:var(--mut)}#fu-summary tr.mut td{color:var(--mut)}.star{background:none;border:0;color:var(--mut);font-size:20px;line-height:1;cursor:pointer;padding:0 4px}.star.on,.wlmark{color:#ffd17a;font-style:normal}.star:focus-visible,.wlx:focus-visible,#wlonly:focus-visible{outline:2px solid var(--am);outline-offset:2px}#wlonly{flex:0 0 auto;padding:6px 11px;font-size:14px;line-height:1}#wlonly.on{background:#f4f4f0;color:#0a0a0a}.wlbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}.wlbar input{background:#101010;color:var(--ink);border:1px solid #444;padding:8px 10px;font:600 12px var(--mono);text-transform:uppercase}.wlx{background:none;border:0;color:var(--mut);cursor:pointer;padding:4px 8px}.wlx:hover{color:var(--r)}.callhead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;background:var(--panel);border-top:3px solid #f4f4f0;padding:12px 14px;margin-bottom:8px}.callhead h3{margin:0;font-size:16px;letter-spacing:.04em}.callhead a{color:#ffd17a;font:11px var(--mono)}.callmeta{color:var(--mut);font:10px var(--mono);margin-top:3px}.callpanels{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:8px}.callsection{background:var(--panel);border-top:3px solid #444;padding:12px;min-width:0}.callsection.outlookpanel{border-color:var(--g)}.callsection.focuspanel{border-color:var(--am)}.callsection.actualspanel{border-color:#5aa9ff}.callsection h4{margin:0 0 9px;font:800 10px var(--sans);letter-spacing:.1em;color:var(--mut)}.outlook{padding:9px 10px;margin-bottom:7px;background:#191919;border-left:3px solid #777;font-size:12px;line-height:1.45}.outlook.positive{border-color:var(--g)}.outlook.cautious,.outlook.negative{border-color:var(--r)}.outlook b{display:block;margin-bottom:2px}.evidence{display:block;color:#9d9d96;font:10px var(--mono);margin-top:4px}.focus{display:grid;grid-template-columns:1fr auto;gap:9px;padding:7px 0;border-bottom:1px solid var(--line);font-size:12px}.focus small{display:block;color:var(--mut);margin-top:2px}.qcount{font:700 11px var(--mono);color:#ffd17a}.metricgrid{display:grid;grid-template-columns:1fr;gap:7px}.metric{background:#191919;padding:8px 9px;font-size:11px;line-height:1.4}.metric b{display:block;color:var(--mut);font:800 9px var(--sans);letter-spacing:.07em;margin-bottom:2px}.congrats{display:flex;gap:16px;align-items:baseline;padding:10px;background:rgba(232,169,58,.1);margin-top:12px}.congrats strong{font:700 24px var(--mono);color:#ffd17a}.congrats span{font-size:11px;color:var(--mut)}.callnone{background:var(--panel);border-top:3px solid #444;padding:12px;color:var(--mut);font-size:12px}.aicaveat{margin-top:8px;color:#666;font-size:10px}
.calllibmeta{display:flex;flex-direction:column;margin:12px 0}.calllibmeta span{font:800 9px var(--sans);letter-spacing:.1em;color:var(--mut)}.calllibmeta b{font:700 15px var(--mono)}.calllibrary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.callcard{background:var(--panel);border-top:3px solid #f4f4f0;padding:13px;min-width:0}.callcardhead{display:flex;justify-content:space-between;gap:15px;align-items:flex-start;padding-bottom:11px;border-bottom:1px solid var(--line)}.callcardhead h3{margin:0 0 2px;font-size:18px}.callcardhead>div>div{color:var(--mut);font:10px var(--mono)}.callscore{display:flex;gap:7px;align-items:center;text-align:right}.callscore strong{font:800 23px var(--mono);color:#ffd17a}.callscore span{font:800 8px var(--sans);letter-spacing:.07em;color:var(--mut)}.callcols{display:grid;grid-template-columns:1fr 1fr;gap:12px}.callcard h4{margin:13px 0 5px;font:800 9px var(--sans);letter-spacing:.1em;color:var(--mut)}.callcard ol,.callcard ul{margin:0;padding-left:20px}.callcard li{position:relative;padding:6px 0 7px 2px;border-bottom:1px solid var(--line);font-size:11px;line-height:1.4}.callcard li b{display:block;font-size:11px;margin-bottom:1px}.callcard .concerns li{padding-right:28px}.callcard .concerns li span{position:absolute;right:0;top:7px;color:#ffd17a;font:700 10px var(--mono)}.takeaways{border-top:2px solid #333;margin-top:8px}.takeaways ul{display:grid;grid-template-columns:1fr 1fr;gap:0 12px;list-style:none;padding:0}.callsource{display:inline-block;margin-top:10px;color:#ffd17a;font:800 9px var(--sans);letter-spacing:.08em}
.calllibrary{display:flex;flex-direction:column;gap:10px}.callrow{background:var(--panel);border-top:3px solid #f4f4f0;padding:10px 12px;min-width:0}.callrowhead{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:7px}.callrowhead h3{display:inline;margin:0 9px 0 0;font-size:16px}.callrowhead span{color:var(--mut);font:9px var(--mono)}.callrowhead a{color:#ffd17a;font:800 9px var(--sans)}.callrowgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0}.callrowgrid>section{min-width:0;padding:10px 13px;border-left:1px solid var(--line)}.callrowgrid>section:first-child{border-left:0;padding-left:0}.callrowgrid h4{margin:0 0 6px;font:800 9px var(--sans);letter-spacing:.1em;color:var(--mut)}.callrowgrid ul{list-style:none;margin:0;padding:0}.callrowgrid li{padding:5px 0;border-bottom:1px solid var(--line);font-size:10px;line-height:1.35}.callrowgrid li:last-child{border-bottom:0}.callrowgrid li b,.callrowgrid li span{display:block}.callrowgrid li span{color:#b4b4ad;margin-top:1px}.callrowgrid .shift.upgrade,.callrowgrid .shift.increase,.callrowgrid .shift.improvement{border-left:3px solid var(--g);padding-left:7px}.callrowgrid .shift.reduction,.callrowgrid .shift.downgrade{border-left:3px solid var(--r);padding-left:7px}.callchart{display:block;width:100%;height:auto;background:#111}.callchartline{fill:none;stroke-linejoin:round;stroke-linecap:round}.callchartline.price{stroke:#f4f4f0;stroke-width:2}.callchartline.ma50{stroke:#f5a623}.callchartline.ma100{stroke:#b58cff}.callchartline.ma200{stroke:#ffd84d}.callchartlegend{color:var(--mut);font:8px var(--mono);margin-top:4px}.callchartlegend i{display:inline-block;width:10px;border-top:2px solid #f4f4f0;margin:0 3px 2px 6px}.callchartlegend i:first-child{margin-left:0}.callchartlegend i.m50{border-color:#f5a623}.callchartlegend i.m100{border-color:#b58cff}.callchartlegend i.m200{border-color:#ffd84d}.callchartempty{height:115px;display:grid;place-items:center;background:#111;color:var(--mut);font:10px var(--mono)}
.basetabs,.subtabs{display:flex;width:max-content;max-width:100%;border:1px solid #444;margin:13px 0 12px}.subtabs{margin-top:10px}.basetab,.subtab{border:0;background:#111;color:var(--mut);padding:8px 16px;font:800 10px var(--sans);letter-spacing:.08em;cursor:pointer}.basetab.on,.subtab.on{background:#f4f4f0;color:#090909}.subtab:focus-visible{outline:2px solid var(--am);outline-offset:2px}.basegrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:11px}.basecard{min-width:0;background:var(--panel);border-top:3px solid #555;padding:10px}.basehead{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.basehead h3{display:inline;margin:0 7px 0 0;font-size:16px}.basehead>b{font:700 9px var(--mono);color:var(--mut);white-space:nowrap;margin-top:3px}.basestage{display:inline-block;padding:3px 5px;font:800 8px var(--sans);letter-spacing:.06em;background:#292929}.basestage.near{color:#ffd17a}.basestage.fresh{color:#8ce4b4;background:rgba(63,191,122,.13)}.basestage.building{color:#9ec9ff}.basechart{display:block;width:100%;height:auto;background:#101010;margin-top:7px}.basezone{fill:rgba(90,169,255,.07)}.baseres{stroke:#e8a93a;stroke-dasharray:4 3}.basesup{stroke:#555;stroke-dasharray:3 4}.basechartline{fill:none;stroke-width:1.15;opacity:.9}.basechartline.ma50{stroke:#2f77ff}.basechartline.ma100{stroke:#b58cff}.basechartline.ma200{stroke:#ffd84d}.basevol{fill:#586778;opacity:.55}.basevol.hot{fill:#5aa9ff;opacity:.95}.baseaxis{stroke:#333}.basestats{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;border-top:1px solid var(--line);padding-top:8px}.basestats span{font:800 8px var(--sans);letter-spacing:.05em;color:var(--mut)}.basestats b{display:block;color:var(--ink);font:700 10px var(--mono);margin-top:2px}.baselegend{margin-top:7px;color:var(--mut);font:8px var(--mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.baselegend i{display:inline-block;width:12px;border-top:2px solid;margin:0 3px 2px 6px}.baselegend i:first-child{margin-left:0}.baselegend .candle{border-color:#f4f4f0}.baselegend .m50{border-color:#2f77ff}.baselegend .m100{border-color:#b58cff}.baselegend .m200{border-color:#ffd84d}
#ro{min-height:22px;font:11px var(--mono);color:#cfcfc8;padding:5px 4px}
#lg{display:flex;flex-wrap:wrap;gap:6px 18px;font:12px var(--mono);color:var(--mut);padding:2px 4px 10px}#lg i{display:inline-block;width:14px;height:10px;margin-right:6px;vertical-align:-1px}#lg u{display:inline-block;width:18px;border-top:2px solid;margin-right:5px;vertical-align:middle}
footer{max-width:1280px;margin:0 auto;padding:0 22px 40px;color:var(--mut);font-size:13px}
@media (max-width:1000px){.h52grid,.basegrid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:900px){.sx{padding-top:76px}.sl{width:100%;flex-wrap:wrap}.sl #q{flex-basis:calc(100% - 52px)}#sort{width:100%}#list{top:38px;width:100%;max-height:230px}.chartgrid,.callpanels{grid-template-columns:1fr}.callrowgrid{grid-template-columns:1fr}.callrowgrid>section{border-left:0;border-top:1px solid var(--line);padding:10px 0}.callrowgrid>section:first-child{border-top:0}#insights{position:static;max-height:none}.hd1 b{font-size:21px}header{flex-direction:column;align-items:flex-start}.headright{align-items:flex-start;flex-direction:column}.meta{text-align:left}h2{font-size:21px}.hz{grid-template-columns:1fr}.atrow{flex-direction:column;gap:9px}main{padding:4px 9px 35px}}@media (max-width:620px){.h52grid,.basegrid{grid-template-columns:1fr}.h52meta{grid-template-columns:1fr 1fr}.h52caps,.basetabs{width:100%;flex-wrap:wrap}}
"""

JS = r"""
const D=JSON.parse(document.getElementById('data').textContent),ALL=Object.keys(D.stocks);
/* A stock's price, delivery and open-interest arrays arrive as one string (S.a) and are parsed only when the stock is first opened. Open, high and low are sent as paise from the close;
   the delivery ratio (delivered shares against the mean of the previous 20 sessions, at least 15 of them present) and each day's direction (up, down, or flat when the move is under half the
   prior 60-session standard deviation) are rebuilt here instead of being sent. Same rules as the build. */
function ensureStock(k){const S=D.stocks[k];if(!S||!S.a)return S;Object.assign(S,JSON.parse(S.a));delete S.a;const n=S.c.length,c=S.c,q=S.dq;
 const rat=new Array(n).fill(null),d=new Array(n).fill(null),ret=new Array(n).fill(null);
 for(let i=0;i<n;i++){if(q[i]!=null&&i>=15){let s=0,m=0;for(let j=Math.max(0,i-20);j<i;j++)if(q[j]!=null){s+=q[j];m++}if(m>=15&&s>0)rat[i]=q[i]/(s/m)}
  if(i>0&&c[i]!=null&&c[i-1]!=null)ret[i]=c[i]/c[i-1]-1}
 for(let i=1;i<n;i++){if(ret[i]==null)continue;let s=0,s2=0,m=0;for(let j=Math.max(1,i-60);j<i;j++)if(ret[j]!=null){s+=ret[j];s2+=ret[j]*ret[j];m++}
  let sd=null;if(m>=30){const v=(s2-s*s/m)/(m-1);sd=Math.sqrt(Math.max(0,v))}
  d[i]=sd!=null&&Math.abs(ret[i])<0.5*sd?0:Math.sign(ret[i])}
 S.rat=rat;S.d=d;if(S.o)for(const f of ['o','h','l'])S[f]=S[f].map((d,i)=>d==null||S.c[i]==null?null:Math.round(S.c[i]*100+d)/100);return S}
const COL={32:'#5aa9ff',50:'#f5a623',100:'#b58cff',200:'#ffd84d',233:'#3fd0a0',377:'#ff7aa2',610:'#9a9a94'};
const G='#2fbf71',R='#ef5a4d',GL='rgba(47,191,113,.64)',RL='rgba(239,90,77,.64)',GR='#a3a39c',GRL='rgba(163,163,156,.46)';
let cur=null,rng=252,thr=1.25,universe='top1000',SY=D.universes[universe]||ALL,selectedMas=new Set([50,200]);
try{const saved=JSON.parse(localStorage.getItem('desk-mas'));if(Array.isArray(saved))selectedMas=new Set(saved.map(Number))}catch(e){}
function tab(t){const b=document.querySelector('.tab[data-t="'+t+'"]');if(b)b.click()}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{ensurePanel(b.dataset.t);document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!=='p-'+b.dataset.t);if(b.dataset.t==='stocks'){draw()}if(b.dataset.t==='alt'){drawAlt()}if(b.dataset.t==='credit'){loadCredit()}});
/* ---------- results calendar ---------- */
function istToday(){const p=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata'}).format(new Date());return Date.UTC(+p.slice(0,4),+p.slice(5,7)-1,+p.slice(8,10))}
function daysTo(iso){return Math.round((Date.UTC(+iso.slice(0,4),+iso.slice(5,7)-1,+iso.slice(8,10))-istToday())/864e5)}
function inLabel(n){return n===0?'TODAY':n===1?'TOMORROW':'IN '+n+' DAYS'}
const PT_NAMES={ascending:'ASC TRIANGLE',descending:'DESC TRIANGLE',rectangle:'RECTANGLE'};
let WK=null;
function weekMap(){if(WK)return WK;const wk=[],first=[],last=[];let prev=null;
 D.dates.forEach((d,i)=>{const t=new Date(d+'T00:00:00Z'),f=new Date(t.getTime()+((5-t.getUTCDay()+7)%7)*864e5).toISOString().slice(0,10);if(f!==prev){first.push(i);last.push(i);prev=f}else last[last.length-1]=i;wk.push(first.length-1)});return WK={wk,first,last}}
function weeklyBars(S){if(S._w)return S._w;const m=weekMap(),n=m.first.length,o=[],h=[],l=[],c=[];
 for(let w=0;w<n;w++){let hi=null,lo=null;for(let i=m.first[w];i<=m.last[w];i++){if(S.h[i]!=null)hi=hi==null?S.h[i]:Math.max(hi,S.h[i]);if(S.l[i]!=null)lo=lo==null?S.l[i]:Math.min(lo,S.l[i])}
  o.push(S.o[m.first[w]]);c.push(S.c[m.last[w]]);h.push(hi);l.push(lo)}return S._w={o,h,l,c}}
/* One pattern drawn on its own small chart: the candles of the timeframe it was found on (weekly patterns get weekly candles), the two lines with the shape filled in, the touch points, where the break happened, and the target. */
function patChart(S,p){const wkly=p.tf==='w',B=wkly?weeklyBars(S):{o:S.o,h:S.h,l:S.l,c:S.c},m=wkly?weekMap():null,idx=i=>wkly?m.wk[i]:i,n=B.c.length;
 const lines=p.lines.map(l=>({a:[idx(l.a[0]),l.a[1]],b:[idx(l.b[0]),l.b[1]],role:l.role})),i0=Math.min(lines[0].a[0],lines[1].a[0]),span=n-1-i0,from=Math.max(0,i0-Math.max(5,Math.round(span*.22)));
 let lo=1e18,hi=-1e18;for(let i=from;i<n;i++){if(B.h[i]!=null)hi=Math.max(hi,B.h[i]);if(B.l[i]!=null)lo=Math.min(lo,B.l[i])}lines.forEach(l=>[l.a[1],l.b[1]].forEach(v=>{hi=Math.max(hi,v);lo=Math.min(lo,v)}));
 const ext=hi-lo;if(p.tg!=null&&p.tg>lo-ext*.4&&p.tg<hi+ext*.4){hi=Math.max(hi,p.tg);lo=Math.min(lo,p.tg)}const pad=(hi-lo)*.06;lo-=pad;hi+=pad;
 const W=380,H=190,L=4,Rr=46,T=8,Bt=18,x=i=>L+(i-from+.5)*(W-L-Rr)/(n-from),y=v=>T+(1-(v-lo)/(hi-lo))*(H-T-Bt),bw=Math.max(1.6,(W-L-Rr)/(n-from)*.62);
 let g='';for(let k=0;k<=2;k++){const v=lo+(hi-lo)*k/2;g+=`<line x1="${L}" x2="${W-Rr}" y1="${y(v)}" y2="${y(v)}" stroke="#222"/><text x="${W-Rr+4}" y="${y(v)+3}" fill="#77776f" font-size="9" font-family="monospace">${v>=1000?v.toFixed(0):v.toFixed(1)}</text>`}
 const [u,d]=lines;g+=`<polygon points="${x(u.a[0])},${y(u.a[1])} ${x(u.b[0])},${y(u.b[1])} ${x(d.b[0])},${y(d.b[1])} ${x(d.a[0])},${y(d.a[1])}" fill="rgba(240,240,236,.07)"/>`;
 if(p.br!=null){const bi=idx(p.br);g+=`<line x1="${x(bi)}" x2="${x(bi)}" y1="${T}" y2="${H-Bt}" stroke="${p.st==='BREAKDOWN'?R:G}" stroke-dasharray="3 3" opacity=".8"/><text x="${Math.min(x(bi)+4,W-Rr-70)}" y="${T+10}" fill="${p.st==='BREAKDOWN'?R:G}" font-size="9" font-family="monospace">${p.st} ${(D.dates[p.br]||'').slice(5)}</text>`}
 for(let i=from;i<n;i++){const o=B.o[i],h=B.h[i],l=B.l[i],c=B.c[i];if(o==null||h==null||l==null||c==null)continue;const col=c>=o?G:R;g+=`<line x1="${x(i)}" x2="${x(i)}" y1="${y(h)}" y2="${y(l)}" stroke="${col}"/><rect x="${x(i)-bw/2}" y="${y(Math.max(o,c))}" width="${bw}" height="${Math.max(1,Math.abs(y(o)-y(c)))}" fill="${col}"/>`}
 lines.forEach(l=>{g+=`<line x1="${x(l.a[0])}" y1="${y(l.a[1])}" x2="${x(l.b[0])}" y2="${y(l.b[1])}" stroke="${l.role==='resistance'?R:G}" stroke-width="2"/>`});
 p.th.forEach(([di,pr])=>{const i=idx(di);if(i>=from)g+=`<circle cx="${x(i)}" cy="${y(pr)}" r="3" fill="none" stroke="#f1f1ec" stroke-width="1.2"/>`});
 if(p.tg!=null&&p.tg>lo&&p.tg<hi)g+=`<line x1="${L}" x2="${W-Rr}" y1="${y(p.tg)}" y2="${y(p.tg)}" stroke="#ffd17a" stroke-dasharray="5 3"/><text x="${W-Rr-3}" y="${y(p.tg)-4}" text-anchor="end" fill="#ffd17a" font-size="9" font-family="monospace">TARGET ${p.tg.toFixed(0)}</text>`;
 const ds=wkly?D.dates[m.last[from]]:D.dates[from],de=D.dates[D.dates.length-1];
 g+=`<text x="${L+2}" y="${H-4}" fill="#77776f" font-size="9" font-family="monospace">${ds}</text><text x="${W-Rr}" y="${H-4}" text-anchor="end" fill="#77776f" font-size="9" font-family="monospace">${de}</text>`;
 const flats=lines.filter(l=>Math.abs(l.a[1]-l.b[1])<1e-6*Math.abs(l.a[1])),offs=p.th.map(([di,pr])=>[idx(di),pr]).filter(([i])=>i<from);
 if(offs.length&&flats.length){flats.forEach(l=>{const yy=y(l.a[1]);if(yy>T&&yy<H-Bt){g+=`<line x1="${L}" x2="${x(l.a[0])}" y1="${yy}" y2="${yy}" stroke="${l.role==='resistance'?R:G}" stroke-width="1.4" stroke-dasharray="4 3" opacity=".8"/><text x="${L+2}" y="${yy-4}" fill="#f1f1ec" font-size="9" font-family="monospace">◄ ${offs.length} EARLIER TOUCH${offs.length>1?'ES':''} · OFF THE LEFT OF THIS CHART</text>`}})}
 const main=`<svg viewBox="0 0 ${W} ${H}" class="patsvg" role="img" aria-label="${PT_NAMES[p.k]} ${wkly?'weekly':'daily'}">${g}</svg>`;
 if(!offs.length)return main;
 /* the touches that fall before the chart: the same pattern against the whole history, so a level tested years ago is visible */
 const Hm=78,Tm=6,Bm=14,N=B.c.length;let l2=1e18,h2=-1e18;for(let i=0;i<N;i++){const v=B.c[i];if(v!=null){l2=Math.min(l2,v);h2=Math.max(h2,v)}}p.th.forEach(([di,pr])=>{l2=Math.min(l2,pr);h2=Math.max(h2,pr)});
 const x2=i=>L+(i+.5)*(W-L-Rr)/N,y2=v=>Tm+(1-(v-l2)/((h2-l2)||1))*(Hm-Tm-Bm);let q=`<rect x="${x2(from)}" y="${Tm}" width="${W-Rr-x2(from)}" height="${Hm-Tm-Bm}" fill="rgba(232,169,58,.12)"/>`;
 let pts='';for(let i=0;i<N;i++){const v=B.c[i];if(v!=null)pts+=(pts?' ':'')+x2(i).toFixed(1)+','+y2(v).toFixed(1)}q+=`<polyline points="${pts}" fill="none" stroke="#8b8b86" stroke-width="1.2"/>`;
 flats.forEach(l=>{q+=`<line x1="${L}" x2="${W-Rr}" y1="${y2(l.a[1])}" y2="${y2(l.a[1])}" stroke="${l.role==='resistance'?R:G}" stroke-width="1.2" stroke-dasharray="4 3"/>`});
 p.th.forEach(([di,pr])=>{q+=`<circle cx="${x2(idx(di))}" cy="${y2(pr)}" r="3" fill="none" stroke="#f1f1ec" stroke-width="1.2"/>`});
 q+=`<text x="${L+2}" y="${Hm-3}" fill="#77776f" font-size="9" font-family="monospace">${wkly?D.dates[weekMap().last[0]]:D.dates[0]}</text><text x="${W-Rr}" y="${Hm-3}" text-anchor="end" fill="#77776f" font-size="9" font-family="monospace">${D.dates[D.dates.length-1]}</text>`;
 return main+`<div class="ptfull mut">WHOLE HISTORY · the shaded part is the chart above · ${p.th.length} touches in all, ${offs.length} before it</div><svg viewBox="0 0 ${W} ${Hm}" class="patsvg" role="img" aria-label="The pattern against the whole price history">${q}</svg>`}
function patternPanels(S){const a=S.pt||[];if(!a.length)return '';const tone={BREAKOUT:'up',BREAKDOWN:'down',SETUP:'near','AT TOP':'near','AT BOTTOM':'near'};
 return '<div class="ptpanels"><div class="ititle">CHART PATTERNS</div>'+a.map(p=>`<div class="ptpanel"><div class="pthd"><b>${PT_NAMES[p.k]} · ${p.tf==='w'?'WEEKLY':'DAILY'}</b><span class="ptst ${tone[p.st]||'mut'}">${p.st}</span></div>${p.bx!=null&&(p.st==='BREAKOUT'||p.st==='BREAKDOWN')?`<div class="ptdv"><span class="ptst ${p.cf?'up':'mut'}">${p.cf?'HIGH DELIVERY':'DELIVERY'} ${p.bx}× ON THE BREAK</span></div>`:''}${patChart(S,p)}<div class="ptdet">${escH(p.d||'')}</div></div>`).join('')+'</div>'}
function screensRow(S){const row=document.getElementById('screens-row');row.hidden=true;row.innerHTML='';const f=S.fl||[];if(!f.length)return;row.hidden=false;row.className='screensrow';
 row.innerHTML='<span class="mut scrlab">FLAGGED IN</span>'+f.map(x=>`<button type="button" class="scrchip ${x.t}" data-goto-tab="${x.tab}" data-goto-sub="${x.sub||''}" data-goto-sub2="${x.sub2||''}" data-goto-tf="${x.tf||''}" title="${escH(x.d||'')} · open this screen"><b>${escH(x.l)}</b>${x.st?` <i>${escH(x.st)}</i>`:''}${x.d&&!x.st?` <small>${escH(x.d)}</small>`:''}</button>`).join('')}
function gotoScreen(tab,sub,tf,sub2){const tb=document.querySelector('.tab[data-t="'+tab+'"]');if(!tb)return;tb.click();const p=document.getElementById('p-'+tab);if(sub){const sb=p.querySelector('.subtab[data-sub="'+sub+'"]');if(sb)sb.click()}
 const cur=p.querySelector(':scope > .subview:not([hidden])');                       /* the visible screen of this tab, not a nested one */
 if(tf&&cur){const fb=cur.querySelector('.ptfbtn[data-tf="'+tf+'"]');if(fb)fb.click()}
 if(sub2&&cur){const sb2=cur.querySelector('.subtab[data-sub="'+sub2+'"]');if(sb2)sb2.click()}window.scrollTo(0,0)}
function resultRow(S){const row=document.getElementById('result-row'),r=S.result;row.hidden=true;row.innerHTML='';row.className='';if(!r)return;const n=daysTo(r.date);if(n<0)return;
 row.hidden=false;row.className='resultrow'+(n<=3?' soon':'');const d=new Date(r.date+'T00:00:00').toLocaleDateString('en-GB',{weekday:'short',day:'2-digit',month:'short'});
 row.innerHTML=`<b>RESULT ${inLabel(n)}</b><span>${escH(d)}${r.status==='DECLARED'?' · DECLARED':''}</span>${r.purpose?`<span>${escH(r.purpose)}</span>`:''}${r.period?`<small>${escH(r.period)}</small>`:''}${r.url?`<a href="${escH(r.url)}" target="_blank" rel="noopener">NSE filing ↗</a>`:''}`}
const OUTLOOK_NAMES={bullish:'BULLISH',optimistic:'OPTIMISTIC',positive:'POSITIVE',muted:'MUTED',cautious:'CAUTIOUS',bearish:'BEARISH'};
function outlookRow(S){const row=document.getElementById('outlook-row'),o=S.call&&S.call.outlook;row.hidden=true;row.innerHTML='';row.className='';if(!o)return;
 const c=o.counts,bits=[`${c.positive} positive`,`${c.neutral} neutral`,`${c.cautious} cautious`,`${c.negative} negative`].filter((t,i)=>[c.positive,c.neutral,c.cautious,c.negative][i]>0),
  g=o.guidance>0?'guidance raised':o.guidance<0?'guidance cut':'',period=(S.call.analysis&&S.call.analysis.call_period)||'';
 row.hidden=false;row.className='outlookrow '+o.label;
 row.innerHTML=`<b>OUTLOOK · ${OUTLOOK_NAMES[o.label]}</b><span>${escH(bits.join(' · '))} of ${o.n} near-term points</span>${g?`<span>${g}</span>`:''}${period?`<small>${escH(period)} call</small>`:''}<button type="button" title="Jump to the next-quarter outlook below the charts">View management's points</button>`;
 row.querySelector('button').onclick=()=>{const t=document.querySelector('#callintel .outlookpanel');if(t)t.scrollIntoView({block:'nearest',behavior:'smooth'})}}
let urState={set:'all',cap:'any',within:'0'};
function renderUpcoming(){const t=document.querySelector('.urtable');if(!t)return;const q=document.getElementById('ur-q').value.trim().toLowerCase();let shown=0;
 t.querySelectorAll('tbody tr').forEach(tr=>{const n=daysTo(tr.dataset.date),cell=tr.querySelector('.rin');cell.textContent=n<0?'PAST':inLabel(n);cell.classList.toggle('soonc',n>=0&&n<=3);
  const w=+urState.within,ok=n>=0&&(urState.set==='all'||(urState.set==='top500'&&tr.dataset.top500==='1')||(urState.set==='fo'&&tr.dataset.fo==='1'))&&(urState.cap==='any'||tr.dataset.cap===urState.cap)&&(!w||n<w)&&(!q||tr.dataset.sym.toLowerCase().includes(q)||tr.dataset.name.includes(q));
  tr.hidden=!ok;if(ok)shown++});document.getElementById('ur-count').textContent=shown+' SHOWN'}
/* ---------- alternative data (experimental): shared pieces ---------- */
const HEAT=D.heat,POWER=D.power;let heatWin=14,heatMetric='mean',powerWin=14,powerCo=null;const heatHidden=new Set(),powerHidden=new Set();
const hT=(v,d=1)=>v==null?'–':(v>=0?'+':'−')+Math.abs(v).toFixed(d)+'°C',hCls=v=>v==null?'':v>.2?'hhot':v<-.2?'hcool':'hflat',hWord=v=>v==null?'–':v>.2?'HOTTER':v<-.2?'COOLER':'ABOUT THE SAME';
const pPct=v=>v==null?'–':(v>=0?'+':'−')+Math.abs(v).toFixed(1)+'%',pCls=v=>v==null?'':v>.5?'pup':v<-.5?'pdn':'hflat',pNum=(v,d=0)=>v==null?'–':Number(v).toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d});
function hCell(v){if(v==null)return '<td class="hc mut">–</td>';const a=Math.min(1,Math.abs(v)/3)*.85;return `<td class="hc" style="background:${v>=0?`rgba(239,90,77,${a})`:`rgba(90,169,255,${a})`}" title="${hT(v,2)}">${v>=0?'+':'−'}${Math.abs(v).toFixed(1)}</td>`}
function hRolling(values,win){const out=new Array(values.length).fill(null);let sum=0,n=0;for(let i=0;i<values.length;i++){const v=values[i];if(v!=null){sum+=v;n++}if(i>=win){const o=values[i-win];if(o!=null){sum-=o;n--}}if(i>=win-1&&n===win)out[i]=sum/win}return out}
const H_MONTHS=[0,31,59,90,120,151,181,212,243,273,304,334],H_NAMES=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function hDate(i){let m=11;while(H_MONTHS[m]>i)m--;return (i-H_MONTHS[m]+1)+' '+H_NAMES[m]}
function hMatched(cur,other){let g=0,n=0,w=0,b=0;for(let i=0;i<cur.length;i++){if(cur[i]!=null&&other[i]!=null){g+=cur[i]-other[i];b+=other[i];n++;if(cur[i]>other[i])w++}}return n?{gap:g/n,warm:100*w/n,n,pct:b?g/b*100:null}:null}
const Y_COLS=['#ff7a3d','#9fb0c4','#66758a'],Y_W=[2.6,1.8,1.4];
/* One year-vs-year line chart: three years on a shared Jan-Dec axis, a trailing mean, hover values. o = {years, raw, win, hidden, h, small, zero, unit, tip(vals,i)} */
function yoyDraw(box,o){const ys=o.raw.map(a=>hRolling(a,o.win)),W=Math.max(220,Math.floor(box.clientWidth)),Ht=o.h,L=o.small?34:46,R=6,T=8,B=18;
 let lo=1e12,hi=-1e12;ys.forEach((a,k)=>{if(!o.hidden.has(k))a.forEach(v=>{if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v)}})});if(lo>hi){lo=0;hi=1}const pad=(hi-lo)*.08||1;lo-=pad;hi+=pad;if(o.zero)lo=Math.max(0,lo);
 const x=i=>L+i*(W-L-R)/364,y=v=>T+(1-(v-lo)/(hi-lo))*(Ht-T-B),fmt=v=>(hi-lo>20?v.toFixed(0):v.toFixed(1))+(o.unit||'');
 let g='';for(let k=0;k<=3;k++){const v=lo+(hi-lo)*k/3;g+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#222"/><text x="${L-4}" y="${y(v)+3}" fill="#77776f" font-size="9" text-anchor="end" font-family="monospace">${fmt(v)}</text>`}
 H_MONTHS.forEach((m,i)=>{if(!o.small||i%2===0)g+=`<text x="${x(m)}" y="${Ht-6}" fill="#77776f" font-size="9" font-family="monospace">${H_NAMES[i]}</text>`});
 for(let k=2;k>=0;k--){if(o.hidden.has(k))continue;let d='',pen=false;ys[k].forEach((v,i)=>{if(v==null){pen=false;return}d+=(pen?'L':'M')+x(i).toFixed(1)+','+y(v).toFixed(1);pen=true});g+=`<path d="${d}" fill="none" stroke="${Y_COLS[k]}" stroke-width="${Y_W[k]}" stroke-linejoin="round"/>`}
 box.innerHTML=`<svg viewBox="0 0 ${W} ${Ht}" role="img" aria-label="${escH(o.label||'')} rolling ${o.win}-day, ${o.years.join(' versus ')}">${g}<line class="yx" y1="${T}" y2="${Ht-B}" stroke="#555" visibility="hidden"/><rect class="yhit" x="${L}" y="${T}" width="${W-L-R}" height="${Ht-T-B}" fill="transparent"/></svg><div class="ytip" hidden></div>`;
 const hit=box.querySelector('.yhit'),tip=box.querySelector('.ytip'),line=box.querySelector('.yx');
 const move=e=>{const r=hit.getBoundingClientRect(),i=Math.max(0,Math.min(364,Math.round((e.clientX-r.left)/r.width*364)));line.setAttribute('x1',x(i));line.setAttribute('x2',x(i));line.setAttribute('visibility','visible');tip.hidden=false;tip.style.left=Math.min(W-150,Math.max(0,x(i)+8))+'px';tip.innerHTML=`<b>${hDate(i)}</b>`+o.tip(ys.map(a=>a[i]),i)};
 hit.onmousemove=move;hit.onmouseleave=()=>{tip.hidden=true;line.setAttribute('visibility','hidden')};hit.ontouchmove=e=>move(e.touches[0])}
function yoyLegend(el,years,hidden,key,win){el.innerHTML=years.map((y,k)=>`<button type="button" class="hleg${hidden.has(k)?' off':''}" data-yl="${key}" data-k="${k}"><i style="background:${Y_COLS[k]}"></i>${y}</button>`).join('')+`<span class="mut">click a year to hide it · ${win}-day trailing mean · Feb 29 removed</span>`}
function winButtons(attr,cur){return [14,30].map(w=>`<button type="button" class="seg${w===cur?' on':''}" data-${attr}="${w}">${w}-DAY</button>`).join('')}
/* ---------- alternative data: temperature ---------- */
const HEAT_SIX=['Delhi','Mumbai','Bengaluru','Hyderabad','Chennai','Kolkata'];
function heatSix(){return HEAT_SIX.map(n=>HEAT.cities.find(c=>c.name===n)).filter(Boolean)}
function renderHeat(){const root=document.getElementById('heat-root');if(!root||!HEAT)return;
 const Y=HEAT.years,regs=[['ALL INDIA',HEAT.all],...['North','East','West','South'].filter(k=>HEAT.regions[k]).map(k=>[k.toUpperCase(),HEAT.regions[k]])];
 const cards=regs.map(([n,r])=>`<div class="hcard"><h4>${n}<small>${r.n} cities</small></h4><div class="hbig ${hCls(r.p1)}">${hT(r.p1)}</div><div class="hsub">${Y[0]} vs ${Y[1]}, same days so far · <b class="${hCls(r.p1)}">${hWord(r.p1)}</b></div><div class="hrow"><span>vs ${Y[2]}</span><b class="${hCls(r.p2)}">${hT(r.p2)}</b></div><div class="hrow"><span>Warmer days vs ${Y[1]}</span><b>${r.w1==null?'–':Math.round(r.w1)+'%'}</b></div><div class="hrow"><span>Year to date vs 1991–2020</span><b class="${hCls(r.ytd)}">${hT(r.ytd)}</b></div><div class="hrow"><span>Last 30 days vs normal</span><b class="${hCls(r.last30)}">${hT(r.last30)}</b></div></div>`).join('');
 const seasonTable=(key,title,summer)=>{const rows=regs.map(([n,r])=>{const s=r.seasons[key];if(!s)return '';const d=s.d_prev,read=summer?(d>.2?'HOTTER · cooling tailwind':d<-.2?'COOLER · cooling headwind':'ABOUT THE SAME'):(d<-.2?'COLDER · heating tailwind':d>.2?'WARMER · heating headwind':'ABOUT THE SAME');
   return `<tr><td class="l"><b>${n}</b></td><td>${s.label}${s.partial?` <span class="mut">(${s.days} days so far)</span>`:''}</td><td>${s.mean.toFixed(1)}°C</td><td class="${hCls(d)}">${hT(d)}</td><td class="${hCls(s.d_norm)}">${hT(s.d_norm)}</td><td class="${hCls(s.max_prev)}">${hT(s.max_prev)}</td>${summer?`<td>${s.hot.toFixed(1)} <span class="mut">(${s.hot_prev>=0?'+':'−'}${Math.abs(s.hot_prev).toFixed(1)})</span></td>`:''}<td class="l"><b class="${summer?hCls(d):hCls(-d)}">${read}</b></td></tr>`}).join('');
  const first=regs[0][1].seasons[key];return `<h3 class="fuh">${title}${first?` · ${first.label} vs ${first.prev_label}`:''}</h3><div class="card"><div class="tw"><table><thead><tr><th class="l">REGION</th><th>SEASON</th><th>AVG TEMP</th><th>VS LAST SEASON</th><th>VS 1991–2020</th><th>AVG MAX VS LAST</th>${summer?'<th>DAYS ≥40°C PER CITY (VS LAST)</th>':''}<th class="l">TEMPERATURE READ</th></tr></thead><tbody>${rows}</tbody></table></div></div>`};
 const grid='<div class="card"><div class="tw"><table class="hgrid"><thead><tr><th class="l">CITY</th>'+HEAT.months.map(m=>`<th>${H_NAMES[+m.slice(5)-1].toUpperCase()}<div class="mut">${m.slice(2,4)}</div></th>`).join('')+'</tr></thead><tbody>'+['North','East','West','South'].map(rg=>HEAT.cities.filter(c=>c.region===rg).map((c,i)=>`<tr${i===0?' class="hfirst"':''}><td class="l">${escH(c.name)} <span class="mut">${rg[0]}</span></td>${c.grid.map(hCell).join('')}</tr>`).join('')).join('')+'</tbody></table></div></div>';
 const oni=Object.entries(HEAT.oni),lastO=oni[oni.length-1],six=heatSix();
 root.innerHTML=`<div class="hmeta">Data through <b>${HEAT.asof}</b>${lastO?` · Niño 3.4 (ONI) <b>${lastO[1]>=0?'+':'−'}${Math.abs(lastO[1]).toFixed(2)}</b> for ${lastO[0]}${lastO[1]>=.5?' · El Niño conditions':lastO[1]<=-.5?' · La Niña conditions':''}`:''}</div><div class="hcards">${cards}</div>${seasonTable('summer','COOLING SEASON · MARCH–JUNE',true)}${seasonTable('winter','HEATING SEASON · DECEMBER–FEBRUARY',false)}
 <h3 class="fuh">YEAR VS YEAR · SIX LARGE CITIES</h3><div class="hctl"><span class="mut">SMOOTHING</span><span id="hwin">${winButtons('hw',heatWin)}</span><span class="mut">METRIC</span><button type="button" class="seg" data-hm="mean">MEAN</button><button type="button" class="seg" data-hm="max">MAX</button><span id="hlegend" class="ylegendrow"></span></div>
 <div class="mgrid c3">${six.map((c,i)=>`<div class="mchart"><div class="mtitle"><b>${escH(c.name)}</b><span class="mut">${c.region}</span></div><div class="ycbox" id="hm${i}"></div><div class="msum" id="hs${i}"></div></div>`).join('')}</div>
 <h3 class="fuh">MONTHLY TEMPERATURE VS 1991–2020 NORMAL · °C · LAST 18 MONTHS</h3>${grid}`;
 drawHeat()}
function drawHeat(){const six=heatSix(),Y=HEAT&&HEAT.years;if(!HEAT||!six.length||!document.getElementById('hm0'))return;
 document.querySelectorAll('[data-hm]').forEach(b=>b.classList.toggle('on',b.dataset.hm===heatMetric));
 yoyLegend(document.getElementById('hlegend'),Y,heatHidden,'heat',heatWin);
 six.forEach((c,i)=>{const raw=Y.map(y=>c.years[y][heatMetric]),m1=hMatched(raw[0],raw[1]),m2=hMatched(raw[0],raw[2]),line=(m,y)=>m?`<span class="${hCls(m.gap)}">${hT(m.gap)}</span> vs ${y} · warmer on ${Math.round(m.warm)}% of days`:'';
  yoyDraw(document.getElementById('hm'+i),{years:Y,raw,win:heatWin,hidden:heatHidden,h:190,small:true,unit:'°',label:c.name,
   tip:vals=>vals.map((v,k)=>`<div style="color:${Y_COLS[k]}">${Y[k]}: ${v==null?'–':v.toFixed(1)+'°C'}</div>`).join('')+(vals[0]!=null&&vals[1]!=null?`<div class="mut">vs ${Y[1]} ${hT(vals[0]-vals[1])}</div>`:'')});
  document.getElementById('hs'+i).innerHTML=`<div>${line(m1,Y[1])}</div><div>${line(m2,Y[2])}</div>`})}
/* ---------- monthly and fiscal-quarter generation, with the period in progress estimated from the run-rate ---------- */
const FQ_NAMES=['Q1','Q2','Q3','Q4'];
function dim(y,m){return new Date(Date.UTC(y,m+1,0)).getUTCDate()}
function fq(y,m){return m>=3?{fy:y+1,q:Math.floor((m-3)/3)}:{fy:y,q:3}}
/* Per company: month and fiscal-quarter totals (MU) from the daily arrays. A month's total is its observed daily mean times its calendar days, so a missing day or Feb 29 cannot skew it.
   The period in progress gets generation so far plus an estimate: remaining days times the mean of the last `win` days. */
function coPeriods(co,win){const ys=POWER.years.slice().reverse(),cur=co.years[ys[ys.length-1]],L=cur.length;
 let run=null;{const v=[];for(let i=L-1;i>=0&&v.length<win;i--)if(cur[i]!=null)v.push(cur[i]);if(v.length)run=v.reduce((a,b)=>a+b,0)/v.length}
 const months=[];
 ys.forEach((y,yi)=>{const arr=co.years[y];for(let m=0;m<12;m++){const a=H_MONTHS[m],b=m<11?H_MONTHS[m+1]:365,end=yi===ys.length-1?Math.min(b,L):b;if(end<=a)continue;
  const seg=arr.slice(a,end).filter(v=>v!=null),el=end-a;if(seg.length<Math.max(1,Math.ceil(el*.5)))continue;
  const mean=seg.reduce((p,q)=>p+q,0)/seg.length,d=dim(y,m),partial=yi===ys.length-1&&end<b;
  months.push({y,m,label:H_NAMES[m]+' '+String(y).slice(2),total:partial?mean*el:mean*d,est:partial?(run==null?0:run*(d-el)):0,partial,d,el})}});
 months.forEach(x=>{const p=months.find(z=>z.y===x.y-1&&z.m===x.m);x.ly=p&&!p.partial?p.total:null});
 const groups={};months.forEach(x=>{const k=fq(x.y,x.m),key=k.fy*10+k.q;(groups[key]=groups[key]||{fy:k.fy,q:k.q,items:[]}).items.push(x)});
 const last=months[months.length-1],quarters=[];
 Object.values(groups).sort((a,b)=>a.fy*10+a.q-(b.fy*10+b.q)).forEach(g=>{let total=g.items.reduce((s,x)=>s+x.total,0),est=g.items.reduce((s,x)=>s+x.est,0),partial=g.items.some(x=>x.partial);
  if(g.items.length<3){ // only the quarter in progress may be short: its later months have not happened yet
   const lq=last&&fq(last.y,last.m);if(!lq||lq.fy!==g.fy||lq.q!==g.q)return;partial=true;
   for(let k=1;k<=3;k++){const m=(g.q===3?k-1:(3+g.q*3+k-1))%12,y=m>=3?g.fy-1:g.fy;if(!g.items.some(x=>x.m===m)&&run!=null)est+=run*dim(y,m)}}
  quarters.push({fy:g.fy,q:g.q,label:FQ_NAMES[g.q]+' FY'+String(g.fy).slice(2),total,est,partial})});
 quarters.forEach(x=>{const p=quarters.find(z=>z.fy===x.fy-1&&z.q===x.q);x.ly=p&&!p.partial?p.total+p.est:null});
 return {months,quarters,run}}
/* A bar chart: solid = generation (orange while the period is in progress), dashed = estimate on top, white tick = the same period a year earlier. */
function barDraw(box,items,o){const W=Math.max(220,Math.floor(box.clientWidth)),Ht=o.h,L=o.small?38:46,R=6,T=8,B=o.two?30:20,n=items.length;if(!n){box.innerHTML='';return}
 let hi=0;items.forEach(x=>{hi=Math.max(hi,x.total+x.est,x.ly||0)});hi*=1.12;const x0=i=>L+(i+.5)*(W-L-R)/n,bw=Math.max(3,(W-L-R)/n*.68),y=v=>T+(1-v/hi)*(Ht-T-B);
 let g='';for(let k=0;k<=3;k++){const v=hi*k/3;g+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#222"/><text x="${L-4}" y="${y(v)+3}" fill="#77776f" font-size="9" text-anchor="end" font-family="monospace">${pNum(v)}</text>`}
 const step=o.two?1:(n>16?3:n>9?2:1);
 items.forEach((x,i)=>{const done=x.total,col=x.partial?'#ff7a3d':'#9fb0c4',pw=o.pair?bw/2:bw,cx=o.pair?x0(i)+bw/4:x0(i);
  if(o.pair&&x.ly!=null)g+=`<rect x="${(x0(i)-bw/2).toFixed(1)}" y="${y(x.ly).toFixed(1)}" width="${pw.toFixed(1)}" height="${Math.max(.5,y(0)-y(x.ly)).toFixed(1)}" fill="#4a5360"/>`;
  g+=`<rect x="${(cx-pw/2).toFixed(1)}" y="${y(done).toFixed(1)}" width="${pw.toFixed(1)}" height="${Math.max(.5,y(0)-y(done)).toFixed(1)}" fill="${col}"/>`;
  if(x.est>0)g+=`<rect x="${(cx-pw/2).toFixed(1)}" y="${y(done+x.est).toFixed(1)}" width="${pw.toFixed(1)}" height="${Math.max(.5,y(done)-y(done+x.est)).toFixed(1)}" fill="rgba(255,122,61,.22)" stroke="#ff7a3d" stroke-dasharray="3 2"/>`;
  if(!o.pair&&x.ly!=null)g+=`<line x1="${(cx-bw/2-1).toFixed(1)}" x2="${(cx+bw/2+1).toFixed(1)}" y1="${y(x.ly).toFixed(1)}" y2="${y(x.ly).toFixed(1)}" stroke="#f4f4f0" stroke-width="1.6"/>`;
  if(i%step===0||i===n-1){const [a,b]=o.two?x.label.split(' '):[x.label,''];g+=`<text x="${cx.toFixed(1)}" y="${Ht-(o.two?16:6)}" fill="#77776f" font-size="9" text-anchor="middle" font-family="monospace">${a}</text>${b?`<text x="${cx.toFixed(1)}" y="${Ht-5}" fill="#77776f" font-size="9" text-anchor="middle" font-family="monospace">${b}</text>`:''}`}
  g+=`<rect class="bh" data-i="${i}" x="${(cx-(W-L-R)/n/2).toFixed(1)}" y="${T}" width="${((W-L-R)/n).toFixed(1)}" height="${Ht-T-B}" fill="transparent"/>`});
 box.innerHTML=`<svg viewBox="0 0 ${W} ${Ht}" role="img" aria-label="${escH(o.label)}">${g}</svg><div class="ytip" hidden></div>`;
 const tip=box.querySelector('.ytip');box.querySelectorAll('.bh').forEach(r=>{r.onmousemove=e=>{const x=items[+r.dataset.i],rect=box.getBoundingClientRect();tip.hidden=false;tip.style.left=Math.min(W-170,Math.max(0,e.clientX-rect.left+8))+'px';
  tip.innerHTML=`<b>${x.label}</b><div>${x.partial?'so far ':''}${pNum(x.total)} MU</div>${x.est>0?`<div style="color:#ff7a3d">+ ${pNum(x.est)} MU estimated</div><div>= ${pNum(x.total+x.est)} MU</div>`:''}${x.ly!=null?`<div class="mut">last year ${pNum(x.ly)} MU (${pPct(((x.total+x.est)/x.ly-1)*100)})</div>`:''}`};r.onmouseleave=()=>{tip.hidden=true}})}
function drawCoBars(co){const P=coPeriods(co,powerWin),mon=P.months.slice(-6),q=P.quarters.slice(-12),run=P.run;
 barDraw(document.getElementById('pmon'),mon,{h:230,pair:true,label:co.name+' monthly generation'});barDraw(document.getElementById('pqtr'),q,{h:230,small:true,two:true,label:co.name+' quarterly generation'});
 const note=(x,days)=>{if(!x)return '';const ly=x.ly,tot=x.total+x.est;return `<div><b>${x.label}</b> · ${x.partial?`${pNum(x.total)} MU so far${days?` (${days})`:''} + <span class="pup">${pNum(x.est)} MU estimated</span> at the last ${powerWin}-day run-rate of ${pNum(P.run,1)} MU a day = <b>${pNum(tot)} MU</b>`:`<b>${pNum(tot)} MU</b>`}${ly!=null?` · last year ${pNum(ly)} MU (<span class="${pCls((tot/ly-1)*100)}">${pPct((tot/ly-1)*100)}</span>)`:''}</div>`};
 const cm=mon[mon.length-1],cq=q[q.length-1];
 document.getElementById('pmons').innerHTML=note(cm,cm&&cm.partial?`${cm.el} of ${cm.d} days`:'');document.getElementById('pqtrs').innerHTML=note(cq,'')}
/* ---------- alternative data: power generation (companies) ---------- */
function drawAlt(){const t=document.querySelector('#p-alt > .subview[data-sub="temp"]');if(t&&!t.hidden){if(HEAT)drawHeat()}else if(POWER)drawPower()}
function renderPower(){const root=document.getElementById('power-root');if(!root||!POWER)return;
 if(!powerCo||!POWER.companies.some(c=>c.name===powerCo))powerCo=(POWER.companies.find(c=>c.name==='NTPC')||POWER.companies[0]||{}).name;
 const owners=POWER.owners.map(o=>`<tr><td class="l"><a class="pco" data-co="${escH(o.owner)}"><b>${escH(o.owner)}</b></a>${o.symbol&&D.stocks[o.symbol]?` <a class="stk mut" data-s="${o.symbol}">${o.symbol===o.owner?'':o.symbol+' '}↗</a>`:''}</td><td>${pNum(o.mw)}</td><td>${pNum(o.mu,1)}</td><td class="${pCls(o.yoy)}">${pPct(o.yoy)}</td><td>${o.plf==null?'–':o.plf.toFixed(1)+'%'}</td><td>${o.coal==null?'–':o.coal.toFixed(1)}</td></tr>`).join('');
 const tbl=(head,rows)=>`<div class="card"><div class="tw"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div></div>`;
 root.innerHTML=`<div class="hmeta">Data through <b>${POWER.asof}</b> · ${POWER.n_days.toLocaleString()} days stored since ${POWER.first} · conventional generation only, wind and solar excluded</div>
 <div class="hctl"><span class="mut">SMOOTHING</span><span id="pwin">${winButtons('pw',powerWin)}</span><span id="plegend" class="ylegendrow"></span></div>
 <div class="mgrid c3">${['ALL','THERMAL','HYDRO'].filter(k=>POWER.series[k]).map(k=>`<div class="mchart"><div class="mtitle"><b>${escH(POWER.series[k].label)}</b><span class="mut">MU per day</span></div><div class="ycbox" id="pm-${k}"></div><div class="msum" id="ps-${k}"></div></div>`).join('')}</div>
 ${POWER.iex?`<h3 class="fuh">IEX DAY-AHEAD MARKET · MERCHANT POWER PRICE</h3><div class="hmeta">Latest <b>${POWER.iex.latest.date}</b> · weighted price <b>₹${POWER.iex.latest.wmcp.toFixed(2)}</b> per kWh · simple average <b>₹${POWER.iex.latest.mcp.toFixed(2)}</b> · <b>${POWER.iex.latest.mcv.toFixed(0)}</b> MU cleared · IEX day-ahead market, all India</div>
 <div class="mgrid c2"><div class="mchart"><div class="mtitle"><b>Weighted price</b><span class="mut">₹ per kWh</span></div><div class="ycbox" id="pxp"></div><div class="msum" id="pxps"></div></div><div class="mchart"><div class="mtitle"><b>Cleared volume</b><span class="mut">MU per day</span></div><div class="ycbox" id="pxv"></div><div class="msum" id="pxvs"></div></div></div>`:''}
 <h3 class="fuh">BY COMPANY</h3><div class="hctl"><label>Company <select id="pco">${POWER.companies.map(c=>`<option${c.name===powerCo?' selected':''}>${escH(c.name)}</option>`).join('')}</select></label><span id="pcosym"></span></div>
 <div class="mgrid c3"><div class="mchart"><div class="mtitle"><b id="pcotitle"></b><span class="mut">MU per day</span></div><div class="ycbox" id="pcob"></div><div class="msum" id="pcos"></div></div>
 <div class="mchart"><div class="mtitle"><b>Monthly generation</b><span class="mut">MU per month · last 6 months</span></div><div class="ycbox" id="pmon"></div><div class="msum" id="pmons"></div></div>
 <div class="mchart"><div class="mtitle"><b>Fiscal quarters</b><span class="mut">MU per quarter</span></div><div class="ycbox" id="pqtr"></div><div class="msum" id="pqtrs"></div></div></div>
 <div class="mut pnote">Orange: the month or quarter in progress. Solid is generation so far, dashed is the estimate (the remaining days at the average of the last 14 or 30 days, as chosen with the smoothing control). Grey bar (months) or white tick (quarters): the same period a year earlier. Quarters are Indian fiscal quarters (Q1 is April to June).</div>
 <h3 class="fuh">COMPANIES · LAST 30 DAYS</h3>${tbl('<th class="l">COMPANY</th><th>CAPACITY MW</th><th>MU PER DAY</th><th>VS SAME WEEKDAYS LAST YEAR</th><th>COAL PLF</th><th>COAL STOCK DAYS</th>',owners)}<div class="mut pnote">Click a company to chart it. Left out of this table, as shares of the last 30 days' generation: state-owned and imported (${POWER.coverage.state}%), plants not matched to a company (${POWER.coverage.other}%) and plants whose ownership needs checking (${POWER.coverage.review}%). Coal PLF and stock days cover coal and lignite stations only.</div>`;
 drawPower()}
function drawPower(){if(!POWER||!document.getElementById('pcob'))return;const Y=POWER.years;
 yoyLegend(document.getElementById('plegend'),Y,powerHidden,'power',powerWin);
 const note=(raw,label)=>{const m1=hMatched(raw[0],raw[1]),m2=hMatched(raw[0],raw[2]),line=(m,y)=>m&&m.pct!=null?`<span class="${pCls(m.pct)}">${pPct(m.pct)}</span> vs ${y} · higher on ${Math.round(m.warm)}% of days`:'';return `<div>${line(m1,Y[1])}</div><div>${line(m2,Y[2])}</div>`};
 const tip=vals=>vals.map((v,k)=>`<div style="color:${Y_COLS[k]}">${Y[k]}: ${v==null?'–':v.toFixed(1)+' MU'}</div>`).join('')+(vals[0]!=null&&vals[1]?`<div class="mut">vs ${Y[1]} ${pPct((vals[0]/vals[1]-1)*100)}</div>`:'');
 ['ALL','THERMAL','HYDRO'].filter(k=>POWER.series[k]).forEach(k=>{const raw=Y.map(y=>POWER.series[k].years[y]);yoyDraw(document.getElementById('pm-'+k),{years:Y,raw,win:powerWin,hidden:powerHidden,h:190,small:true,zero:true,label:POWER.series[k].label,tip});document.getElementById('ps-'+k).innerHTML=note(raw)});
 if(POWER.iex&&document.getElementById('pxp')){const X=POWER.iex,XY=X.years;[['pxp',X.price,'₹','/kWh',2],['pxv',X.volume,'',' MU',0]].forEach(([id,ser,pre,suf,dp])=>{const raw=XY.map(y=>ser[y]),m1=hMatched(raw[0],raw[1]),m2=hMatched(raw[0],raw[2]),line=(m,y)=>m&&m.pct!=null?`<span class="${pCls(m.pct)}">${pPct(m.pct)}</span> vs ${y} · higher on ${Math.round(m.warm)}% of days`:'';
 yoyDraw(document.getElementById(id),{years:XY,raw,win:powerWin,hidden:powerHidden,h:190,small:true,zero:true,label:id==='pxp'?'IEX weighted price':'IEX cleared volume',tip:vals=>vals.map((v,k)=>`<div style="color:${Y_COLS[k]}">${XY[k]}: ${v==null?'–':pre+v.toFixed(dp)+suf}</div>`).join('')});document.getElementById(id+'s').innerHTML=`<div>${line(m1,XY[1])}</div><div>${line(m2,XY[2])}</div>`})}
 const co=POWER.companies.find(c=>c.name===powerCo);if(!co)return;const raw=Y.map(y=>co.years[y]);
 document.getElementById('pcotitle').textContent=co.name;document.getElementById('pcosym').innerHTML=co.symbol&&D.stocks[co.symbol]?`<a class="stk" data-s="${co.symbol}">${co.symbol} stock chart ↗</a>`:'';
 yoyDraw(document.getElementById('pcob'),{years:Y,raw,win:powerWin,hidden:powerHidden,h:230,small:true,zero:true,label:co.name,tip});document.getElementById('pcos').innerHTML=note(raw);drawCoBars(co)}
document.addEventListener('click',e=>{const b=e.target,btn=b.closest&&b.closest('button, a');if(!btn)return;const d=btn.dataset;if(d.gotoTab){gotoScreen(d.gotoTab,d.gotoSub,d.gotoTf,d.gotoSub2);return}
 if(d.hw){heatWin=+d.hw;document.getElementById('hwin').innerHTML=winButtons('hw',heatWin);drawHeat()}
 else if(d.hm){heatMetric=d.hm;drawHeat()}
 else if(d.pw){powerWin=+d.pw;document.getElementById('pwin').innerHTML=winButtons('pw',powerWin);drawPower()}
 else if(d.yl){const set=d.yl==='heat'?heatHidden:powerHidden,k=+d.k;set.has(k)?set.delete(k):set.add(k);d.yl==='heat'?drawHeat():drawPower()}
 else if(d.co){e.preventDefault();powerCo=d.co;document.getElementById('pco').value=powerCo;drawPower();document.getElementById('pcob').scrollIntoView({block:'center',behavior:'smooth'})}});
document.addEventListener('change',e=>{if(e.target.id==='pco'){powerCo=e.target.value;drawPower()}});
window.addEventListener('resize',()=>{if(!document.getElementById('p-alt').hidden)drawAlt()});
/* ---------- sub-tabs inside a tab ---------- */
/* ---------- watchlist ---------- */
let WL=[],wlOnly=false;try{const s=JSON.parse(localStorage.getItem('desk-watchlist'));if(Array.isArray(s))WL=s.filter(x=>D.stocks[x])}catch(e){}
function saveWL(){try{localStorage.setItem('desk-watchlist',JSON.stringify(WL))}catch(e){}}
function inWL(s){return WL.includes(s)}
function toggleWL(s){if(!D.stocks[s])return;WL=inWL(s)?WL.filter(x=>x!==s):[...WL,s];saveWL();renderWatch();list();document.querySelectorAll('.star[data-s]').forEach(b=>{const on=inWL(b.dataset.s);b.classList.toggle('on',on);b.textContent=on?'★':'☆';b.setAttribute('aria-pressed',String(on));b.title=on?'Remove from watchlist':'Add to watchlist'})}
function wlDigest(){const els=['pt-wl','today-wl'].map(i=>document.getElementById(i)).filter(Boolean);if(!els.length)return;const rows=[];WL.forEach(s=>{const S=D.stocks[s];if(S&&S.fl)S.fl.filter(x=>x.ev).forEach(x=>rows.push([s,x]))});
 const html=rows.length?'<span class="mut">YOUR WATCHLIST</span> '+rows.map(([s,x])=>`<a class="stk" data-s="${s}">${s}</a> <span class="ptst near">${x.ev==='BROKE'?'JUST BROKE':'NEW'}</span> <span class="mut">${escH(x.l)}</span>`).join(' · '):(WL.length?'<span class="mut">Nothing new on your watchlist today.</span>':'<span class="mut">Star a stock to see its new flags here.</span>');els.forEach(el=>el.innerHTML=html)}
function renderWatch(){wlDigest();const el=document.getElementById('wl-body');if(!el)return;
 if(!WL.length){el.innerHTML='<div class="card rempty">Your watchlist is empty. Add a ticker above, or press ☆ next to any stock on the Stocks tab.</div>';return}
 const stageName={fresh:'FRESH BREAKOUT',near:'NEAR BREAKOUT',building:'BUILDING A BASE'};
 el.innerHTML='<div class="card"><div class="tw"><table><thead><tr><th class="l">STOCK</th><th>PRICE</th><th>1D</th><th>DELIVERY ÷ 20D</th><th>20D VS NIFTY</th><th>NEAR MA (±0.5σ)</th><th>RESULT</th><th>OUTLOOK</th><th>GUIDANCE</th><th>BASE</th><th></th></tr></thead><tbody>'+WL.map(s=>{
  const S=D.stocks[s],m=S.sm,last=m.last,g=((S.call&&S.call.analysis&&S.call.analysis.material_guidance_changes)||[])[0],rel=m.rel&&m.rel[1]?m.rel[1][0]:null;
  return `<tr><td class="l"><a class="stk" data-s="${escH(s)}">${escH(s)}</a></td><td>${last==null?'–':last.toFixed(2)}</td><td class="${cls(m.px)}">${pc(m.px)}</td><td>${m.ratio==null?'–':m.ratio.toFixed(2)+'×'}</td><td class="${cls(rel)}">${pc(rel)}</td><td>${S.at.length?S.at.map(a=>a.ma+'D').join(' · '):'–'}</td><td>${S.result?escH(resultLabel(S.result)):'–'}</td><td>${S.call&&S.call.outlook?`<span class="olab ${S.call.outlook.label}">${OUTLOOK_NAMES[S.call.outlook.label]}</span>`:'–'}</td><td>${g?`<span class="${g.direction==='upgrade'||g.direction==='increase'||g.direction==='improvement'?'g':'r'}">${escH(g.direction.toUpperCase())}</span>`:'–'}</td><td>${S.bs?escH(stageName[S.bs[0]]||S.bs[0])+' · '+S.bs[1]+'/5':'–'}</td><td><button type="button" class="wlx" data-rm="${escH(s)}" title="Remove" aria-label="Remove ${escH(s)}">✕</button></td></tr>`}).join('')+'</tbody></table></div></div>'}
function wlAdd(){const i=document.getElementById('wl-add'),msg=document.getElementById('wl-msg'),s=i.value.trim().toUpperCase();if(!s)return;
 if(!D.stocks[s]){msg.textContent=s+' is not in the tracked universe.';return}
 msg.textContent='';if(!inWL(s))toggleWL(s);i.value=''}
document.getElementById('wl-syms').innerHTML=ALL.slice().sort().map(s=>`<option value="${s}">`).join('');
document.getElementById('wl-addbtn').onclick=wlAdd;document.getElementById('wl-add').onkeydown=e=>{if(e.key==='Enter')wlAdd()};
document.getElementById('wl-export').onclick=()=>{prompt('Copy your watchlist:',WL.join(','))};
document.getElementById('wl-import').onclick=()=>{const t=prompt('Paste tickers separated by commas:');if(t==null)return;const add=t.toUpperCase().split(/[^A-Z0-9&_-]+/).filter(x=>x&&D.stocks[x]&&!inWL(x));WL=[...WL,...add];saveWL();renderWatch();list();document.getElementById('wl-msg').textContent=add.length+' added.'};
document.getElementById('wl-body').onclick=e=>{const b=e.target.closest('[data-rm]');if(b)toggleWL(b.dataset.rm)};
document.getElementById('wlonly').onclick=e=>{wlOnly=!wlOnly;e.currentTarget.classList.toggle('on',wlOnly);e.currentTarget.setAttribute('aria-pressed',String(wlOnly));list()};
document.addEventListener('click',e=>{const b=e.target.closest('.star[data-s]');if(b)toggleWL(b.dataset.s)});
/* ---------- base follow-through ---------- */
const FU_ORDER=['range','compression','trend','touches','delivery'],FU_STAGES=[['fresh','FRESH BREAKOUT',2],['near','NEAR BREAKOUT',1],['building','BUILDING A BASE',0]];
function fuRows(){const need=[...activeBaseFilters].map(f=>FU_ORDER.indexOf(f)).filter(i=>i>=0);return D.fu.filter(r=>need.every(i=>(r[3]>>i)&1))}
function fuMed(a){if(!a.length)return null;const s=[...a].sort((x,y)=>x-y),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2}
function fuAvg(a){return a.length?a.reduce((x,y)=>x+y,0)/a.length:null}
function renderFollow(){const sum=document.getElementById('fu-summary'),lst=document.getElementById('fu-list');if(!sum)return;
 const rows=fuRows(),HZ=[['5D',4,7],['10D',5,8],['20D',6,9]],c=v=>v==null?'–':pc(v);
 sum.innerHTML='<div class="card"><div class="tw"><table><thead><tr><th class="l">STAGE</th><th>SIGNALS</th>'+HZ.map(h=>`<th>${h[0]} WIN %</th><th>${h[0]} AVG</th><th>${h[0]} MEDIAN</th><th>${h[0]} VS NIFTY</th>`).join('')+'<th>BROKE SUPPORT ≤20D</th><th>AVG WORST DIP</th></tr></thead><tbody>'+FU_STAGES.map(([k,label,code])=>{
  const r=rows.filter(x=>x[2]===code),cells=HZ.map(([,i,xi])=>{const v=r.map(x=>x[i]).filter(x=>x!=null),xv=r.map(x=>x[xi]).filter(x=>x!=null),av=fuAvg(v),md=fuMed(v),ax=fuAvg(xv);
   return `<td>${v.length?(100*v.filter(x=>x>0).length/v.length).toFixed(0)+'%':'–'}</td><td class="${cls(av)}">${c(av)}</td><td class="${cls(md)}">${c(md)}</td><td class="${cls(ax)}">${c(ax)}</td>`}).join(''),
   f=r.filter(x=>x[11]!=null),dd=fuAvg(r.map(x=>x[10]).filter(x=>x!=null));
  return `<tr class="${r.length<30?'mut':''}"><td class="l"><b>${label}</b></td><td>${r.length}</td>${cells}<td>${f.length?(100*f.filter(x=>x[11]===1).length/f.length).toFixed(0)+'% <span class="mut">of '+f.length+'</span>':'–'}</td><td class="${cls(dd)}">${c(dd)}</td></tr>`}).join('')+'</tbody></table></div></div>';
 const recent=rows.slice().sort((a,b)=>b[1]-a[1]||(b[2]-a[2])).slice(0,60),nm={2:'FRESH',1:'NEAR',0:'BUILDING'};
 lst.innerHTML=recent.length?'<div class="card"><div class="tw"><table><thead><tr><th class="l">STOCK</th><th>SIGNAL DATE</th><th>STAGE</th><th>FILTERS PASSED</th><th>5D</th><th>10D</th><th>20D</th><th>TO DATE</th><th>STATUS</th></tr></thead><tbody>'+recent.map(r=>{
  const q=[0,1,2,3,4].filter(i=>(r[3]>>i)&1).length,st=r[11]===1?'<span class="r">BROKE SUPPORT</span>':r[11]===0?'<span class="g">HELD</span>':`<span class="mut">OPEN · DAY ${r[13]}/20</span>`;
  return `<tr><td class="l"><a class="stk" data-s="${escH(r[0])}">${escH(r[0])}</a></td><td>${new Date(D.dates[r[1]]+'T00:00:00').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'2-digit'})}</td><td>${nm[r[2]]}</td><td>${q}/5</td><td class="${cls(r[4])}">${c(r[4])}</td><td class="${cls(r[5])}">${c(r[5])}</td><td class="${cls(r[6])}">${c(r[6])}</td><td class="${cls(r[12])}">${c(r[12])}</td><td>${st}</td></tr>`}).join('')+'</tbody></table></div></div>':'<div class="card rempty">No past signals pass the selected filters.</div>'}
const baseFilterDefaults=['range','compression','trend','touches','delivery'];let activeBaseFilters=new Set(baseFilterDefaults);
try{const saved=JSON.parse(localStorage.getItem('desk-base-filters'));if(Array.isArray(saved))activeBaseFilters=new Set(saved)}catch(e){}
function applyBaseFilters(){const p=document.getElementById('p-bases');if(!p)return;document.querySelectorAll('.basefilter').forEach(b=>{const on=activeBaseFilters.has(b.dataset.baseFilter);b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on))});let shown=0;p.querySelectorAll('.basecard').forEach(card=>{const visible=[...activeBaseFilters].every(f=>card.dataset[f]==='true');card.hidden=!visible;if(visible&&!card.closest('.basegroup').hidden)shown++});const count=p.querySelector('.basecount');if(count)count.textContent=`${shown} SHOWN`;renderFollow()}
document.querySelectorAll('.seg[data-r]').forEach(b=>b.onclick=()=>{rng=+b.dataset.r;document.querySelectorAll('.seg[data-r]').forEach(x=>x.classList.toggle('on',x===b));draw()});
function loadCredit(){document.querySelectorAll('#p-credit .subview:not([hidden]) iframe.creditframe').forEach(f=>{if(f.dataset.loaded)return;f.dataset.loaded='1';try{f.srcdoc=JSON.parse(document.getElementById('credit-doc-'+f.dataset.key).textContent)}catch(e){}})}
document.querySelectorAll('#p-credit .subtab').forEach(b=>b.addEventListener('click',loadCredit));
window.addEventListener('message',e=>{const d=e.data;if(!d||!d.creditFrame)return;const f=document.querySelector('iframe.creditframe[data-key="'+d.creditFrame+'"]');if(f&&e.source===f.contentWindow)f.style.height=Math.max(520,+d.height||0)+'px'});
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
 const a=SY.filter(s=>(!q||s.includes(q))&&(!wlOnly||inWL(s))).sort((x,y)=>{const a=key(x),b=key(y);return a<b?-1:a>b?1:0});
 document.getElementById('list').innerHTML=a.map(s=>{const m=D.stocks[s].sm,r=D.stocks[s].result?`<span class="resultmark" title="Upcoming result">${resultLabel(D.stocks[s].result)}</span>`:'';return `<div class="li${s===cur?' on':''}" data-s="${s}" tabindex="-1"><b>${inWL(s)?'<i class="wlmark">★</i> ':''}${s} ${r}</b><span class="${cls(m.px)}">${pc(m.px)}</span><span class="mut">${m.ratio==null?'–':m.ratio.toFixed(1)+'×'}</span></div>`}).join('')||`<div class="li mut">${wlOnly&&!WL.length?'Watchlist is empty':'No match'}</div>`}
document.getElementById('q').oninput=list;document.getElementById('sort').onchange=list;
document.getElementById('q').onkeydown=e=>{if(e.key==='Enter'){const f=document.querySelector('#list .li[data-s]');if(f)pick(f.dataset.s)}};
document.getElementById('list').onclick=e=>{const li=e.target.closest('.li[data-s]');if(li)pick(li.dataset.s)};
function pick(s){cur=s;list();draw();history.replaceState(null,'','#'+s);if(document.activeElement)document.activeElement.blur();if(window.innerWidth<900)document.getElementById('sh').scrollIntoView({behavior:'smooth',block:'start'})}
document.addEventListener('click',e=>{const a=e.target.closest('a.stk');if(a){e.preventDefault();tab('stocks');document.querySelector('#p-stocks .subtab[data-sub="chart"]').click();cur=a.dataset.s;list();draw();history.replaceState(null,'','#'+cur);window.scrollTo(0,0)}});
/* ---------- chart ---------- */
function drawLegacy(){
 if(!cur||document.getElementById('p-stocks').hidden)return;
 const S=ensureStock(cur),n=S.c.length,v0=Math.max(0,n-rng),box=document.getElementById('chartbox'),W=Math.max(320,Math.min(1460,box.clientWidth-8)),sm=W<560,fs=sm?9:10,L=sm?42:54,Rr=8;
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
 if(!cur||document.getElementById('p-stocks').hidden||document.getElementById('sv-chart').hidden)return;
 const S=ensureStock(cur),n=S.c.length,v0=Math.max(0,n-rng),box=document.getElementById('chartbox'),W=Math.max(320,box.clientWidth-8),sm=W<560,fs=sm?9:10,L=sm?42:54,Rr=8;
 const xs=i=>L+(i-v0)*(W-L-Rr)/Math.max(1,n-1-v0),bw=Math.max(1.4,(W-L-Rr)/(n-v0)*.82);
 const line=(a,y,col,sw=1.5,dash=null,map=v=>v)=>{let d='',pen=false;for(let i=v0;i<n;i++){const v=a[i];if(v==null){pen=false;continue}d+=(pen?'L':'M')+xs(i).toFixed(1)+','+y(map(v)).toFixed(1);pen=true}return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${sw}"${dash?' stroke-dasharray="'+dash+'"':''} stroke-linejoin="round"/>`};
 const candles=(S,y)=>{let o='';for(let i=v0;i<n;i++){const O=S.o[i],Hh=S.h[i],Ll=S.l[i],C=S.c[i];if(O==null||Hh==null||Ll==null||C==null)continue;const col=C>=O?G:R,x=xs(i).toFixed(1),top=y(Math.max(O,C)),bot=y(Math.min(O,C));o+=`<line x1="${x}" x2="${x}" y1="${y(Hh).toFixed(1)}" y2="${y(Ll).toFixed(1)}" stroke="${col}"/><rect x="${(xs(i)-bw/2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1,bot-top).toFixed(1)}" fill="${col}"/>`}return o};
  const frame=(lo,hi,H,title,format=v=>v.toFixed(0))=>{const y=v=>8+(1-(v-lo)/(hi-lo||1))*(H-18);let g=`<text x="${L+4}" y="18" fill="#77776f" font-size="${fs}" font-family="monospace" letter-spacing="1">${title}</text>`;for(let j=0;j<=2;j++){const v=lo+(hi-lo)*j/2,yy=y(v);g+=`<line x1="${L}" x2="${W-Rr}" y1="${yy}" y2="${yy}" stroke="#222"/><text x="${L-5}" y="${yy+3}" fill="#77776f" font-size="${fs}" text-anchor="end" font-family="monospace">${format(v)}</text>`}return [y,g]};
 const setsvg=(id,H,g)=>{const s=document.getElementById(id);s.setAttribute('viewBox',`0 0 ${W} ${H}`);s.setAttribute('width',W);s.setAttribute('height',H);s.innerHTML=g;return s};
 const mas=D.mas.filter(m=>n>=m+1&&selectedMas.has(m)).map(m=>[m,sma(S.c,m)]),PH=sm?150:190,DH=sm?76:90,gap=18,dateH=20,plotBottom=PH+gap+DH,MH=plotBottom+dateH;
 let lo=1e18,hi=-1e18;for(let i=v0;i<n;i++){for(const v of [S.c[i],S.h&&S.h[i],S.l&&S.l[i]])if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v)}}const lo0=lo,hi0=hi;mas.forEach(([,a])=>{for(let i=v0;i<n;i++){const v=a[i];if(v!=null&&v>lo0*.8&&v<hi0*1.25){lo=Math.min(lo,v);hi=Math.max(hi,v)}}});let pad=(hi-lo)*.05||1;lo-=pad;hi+=pad;
 let [yp,g]=frame(lo,hi,PH,sm?'PRICE · AVERAGES':'PRICE (ADJUSTED) · MOVING AVERAGES',v=>v.toFixed(v>=1000?0:1));mas.forEach(([m,a])=>g+=line(a,yp,COL[m],m===200?1.9:1.3));g+=S.o?candles(S,yp):line(S.c,yp,'#fff',1.8);
 const avg=new Array(n).fill(null);for(let i=20;i<n;i++){let s=0,c=0;for(let j=i-20;j<i;j++)if(S.dq[j]!=null){s+=S.dq[j];c++}if(c>=15)avg[i]=s/c}let dmax=0;for(let i=v0;i<n;i++)dmax=Math.max(dmax,S.dq[i]||0,avg[i]||0);dmax*=1.05;
 const yd=v=>PH+gap+(1-v/(dmax||1))*(DH-12);g+=`<text x="${L+4}" y="${PH+gap+11}" fill="#77776f" font-size="${fs}" font-family="monospace" letter-spacing="1">DELIVERED SHARES · DASHED = 20D AVG</text>`;for(let i=v0;i<n;i++){const q=S.dq[i];if(q==null)continue;const hot=(S.rat[i]??0)>=thr,d=S.d[i],col=d===0?(hot?GR:GRL):d===1?(hot?G:GL):(hot?R:RL),h=q/(dmax||1)*(DH-12);g+=`<rect x="${(xs(i)-bw/2).toFixed(1)}" y="${(plotBottom-h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" fill="${col}"/>`}g+=line(avg,yd,'#e8e8e2',1.4,'4 3');
 S.ev.forEach(([i,f])=>{if(i<v0)return;const x=xs(i);g+=`<line x1="${x}" x2="${x}" y1="8" y2="${plotBottom}" stroke="${G}" stroke-dasharray="4 3" opacity=".7"/><text x="${x+4}" y="31" fill="${G}" font-size="${fs}" font-family="monospace">adjusted ×${f}</text>`});g+=`<line x1="${L}" x2="${W-Rr}" y1="${plotBottom}" y2="${plotBottom}" stroke="#333"/>`;const dateIdx=sm?[v0,Math.round((v0+n-1)/2),n-1]:[v0,Math.round(v0+(n-1-v0)*.25),Math.round((v0+n-1)/2),Math.round(v0+(n-1-v0)*.75),n-1];dateIdx.forEach(i=>g+=`<text x="${xs(i)}" y="${plotBottom+15}" fill="#8b8b86" font-size="${fs}" text-anchor="${i===v0?'start':i===n-1?'end':'middle'}" font-family="monospace">${D.dates[i]}</text>`);g+=`<line id="xh" x1="0" x2="0" y1="8" y2="${plotBottom}" stroke="#aaa" visibility="hidden"/>`;const main=setsvg('ch',MH,g);
 const RH=sm?74:92,rsf=S.c.map((v,i)=>v!=null&&D.nifty[i]!=null?v/D.nifty[i]:null),rsm=sma(rsf,50);let base=null;for(let i=v0;i<n;i++)if(rsf[i]!=null){base=rsf[i];break}let rg='';if(base){const rb=v=>v/base*100;let rlo=1e18,rhi=-1e18;for(let i=v0;i<n;i++)for(const v of [rsf[i],rsm[i]])if(v!=null){rlo=Math.min(rlo,rb(v));rhi=Math.max(rhi,rb(v))}const rp=(rhi-rlo)*.08||1;rlo-=rp;rhi+=rp;let yr;[yr,rg]=frame(rlo,rhi,RH,'RELATIVE STRENGTH VS NIFTY · ORANGE = 50D AVG',v=>v.toFixed(0));rg+=line(rsm,yr,'#f5a623',1.3,null,rb)+line(rsf,yr,'#fff',1.7,null,rb)}setsvg('rsch',RH,rg);
 const OH=sm?78:98,dl=new Array(n).fill(null);let omax=0;for(let i=1;i<n;i++){if(S.oi[i]!=null&&S.oi[i-1]!=null)dl[i]=S.oi[i]-S.oi[i-1];if(i>=v0)omax=Math.max(omax,S.oi[i]||0)}let [yo,og]=frame(0,omax*1.05||1,OH,'TOTAL SSF OPEN INTEREST · COLOUR = PRICE/OI BEHAVIOUR',fmt);if(omax){for(let i=v0;i<n;i++){const oi=S.oi[i];if(oi==null)continue;const up=i>0&&S.c[i]!=null&&S.c[i-1]!=null&&S.c[i]>=S.c[i-1],od=dl[i],col=od==null?'#555':od>=0?(up?G:R):(up?'#5aa9ff':'#e8a93a'),h=OH-18-yo(oi);og+=`<rect x="${(xs(i)-bw/2).toFixed(1)}" y="${yo(oi).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(.5,h).toFixed(1)}" fill="${col}"/>`}}else og+=`<text x="${L+4}" y="${OH/2}" fill="#555" font-size="${fs}" font-family="monospace">not in F&amp;O for this period</text>`;setsvg('oich',OH,og);
 const m=S.sm,last=S.c[n-1],lastOI=S.oi[n-1],dOI=dl[n-1],dOIPct=dOI!=null&&S.oi[n-2]?dOI/S.oi[n-2]*100:null,up=S.c[n-1]>=S.c[n-2],bu=dOI==null?'–':dOI>=0?(up?'Long Buildup':'Cash Selling'):(up?'Cash Buying':'Long Unwind'),buc=dOI==null?'':bu==='Long Buildup'?'g':bu==='Cash Selling'?'r':'';
 const rs=D.hz.map((h,k)=>{const r=m.rel[k];return `<div><span>${h[0].toUpperCase()}</span><b class="${cls(r[0])}">${pc(r[0])}</b> <i class="mut" style="font-style:normal">#${r[1]??'–'}/${SY.length}</i></div>`}).join(''),rbadge=S.result?`<span class="resultmark" title="Upcoming result">${resultLabel(S.result)}</span>`:'';
 screensRow(S);resultRow(S);outlookRow(S);document.getElementById('sh').innerHTML=`<div class="hd1"><b>${cur}</b><button type="button" class="star${inWL(cur)?' on':''}" data-s="${cur}" aria-pressed="${inWL(cur)}" title="${inWL(cur)?'Remove from watchlist':'Add to watchlist'}">${inWL(cur)?'★':'☆'}</button>${rbadge}<span class="px">${last==null?'–':last.toFixed(2)}</span><span class="${cls(m.px)}">${pc(m.px,2)}</span></div><div class="chips2"><div><span>DELIVERED</span>${fmt(m.dq)}</div><div><span>÷ 20D AVG</span>${m.ratio==null?'–':m.ratio.toFixed(2)+'×'}</div><div><span>DELIV %</span>${m.dp==null?'–':m.dp.toFixed(1)}</div><div><span>BSE %</span>${m.bse==null?'–':m.bse.toFixed(0)}</div><div><span>SSF OI</span>${fmt(lastOI)}</div><div><span>ΔOI 1D</span><b class="${cls(dOIPct)}">${pc(dOIPct)}</b></div><div><span>OI SIGNAL</span><b class="${buc}">${bu}</b></div></div><div class="rsrow">${rs}</div>`;
 const events=[];for(let i=Math.max(1,n-5);i<n;i++){const move=S.c[i]!=null&&S.c[i-1]!=null?(S.c[i]/S.c[i-1]-1)*100:null,op=dl[i]!=null&&S.oi[i-1]?dl[i]/S.oi[i-1]*100:null,aboveAvg=(S.rat[i]??0)>1,cashbuy=aboveAvg&&move>0&&op<0,cashsell=aboveAvg&&move<0&&op>0;if(cashbuy){events.push({i,kind:'cash',tone:'cashbuy',txt:`${S.rat[i].toFixed(2)}× delivery · ${pc(op)} OI`});continue}if(cashsell){events.push({i,kind:'cashsell',tone:'cashsell',txt:`${S.rat[i].toFixed(2)}× delivery · ${pc(op)} OI`});continue}if((S.rat[i]??0)>=1.5)events.push({i,kind:'del',txt:`${S.rat[i].toFixed(2)}× delivery · ${pc(move)}`});if(op!=null&&Math.abs(op)>=3){const pu=move>=0,label=dl[i]>=0?(pu?'Long Buildup':'Cash Selling'):(pu?'Cash Buying':'Long Unwind');events.push({i,kind:'oi',txt:`${label} · ${pc(op)} OI`})}}events.sort((a,b)=>b.i-a.i);let ih='<div class="ititle">RECENT ACTIVITY · 5 SESSIONS</div>';if(S.result)ih+=`<div class="resultbox"><b>UPCOMING RESULT</b>${S.result.date} · ${S.result.status}</div>`;ih+=events.length?events.map(e=>`<div class="ievent${e.tone?' '+e.tone:''}"><span class="idate">${D.dates[e.i].slice(5)}</span><span class="itag ${e.kind}">${e.kind==='del'?'DELIVERY':e.kind==='cash'?'CASH BUYING':e.kind==='cashsell'?'CASH SELLING':'OI'}</span>${e.txt}</div>`).join(''):'<div class="inone">No above-average delivery cash-buying/cash-selling signal, delivery ≥1.5× average, or daily OI move ≥3% in the last 5 sessions.</div>';ih+='<div class="mahere"><div class="ititle">AT A MOVING AVERAGE</div>'+(S.at&&S.at.length?S.at.map(a=>`<div class="mahit"><b>${a.ma}-DAY MA</b>${a.crossed?'<span class="cross">CROSSED TODAY</span>':''}<br><span class="${a.new?'fresh':''}">${a.above?'above':'below'} by ${Math.abs(a.dist).toFixed(2)}% · ${Math.abs(a.dist/a.sigma).toFixed(2)}σ${a.new?' · new today':''}</span></div>`).join(''):'<div class="inone">Not currently within 0.5σ of an active moving average.</div>')+'</div>';document.getElementById('insights').innerHTML=patternPanels(S)+ih;
 callPanel(S);
 guidanceRow(S);
 document.getElementById('lg').innerHTML=mas.map(([m])=>`<span><u style="border-color:${COL[m]}"></u>${m}</span>`).join('')+`<span><u style="border-color:#fff"></u>price / RS</span><span><i style="background:${G}"></i>Long Buildup</span><span><i style="background:#5aa9ff"></i>Cash Buying</span><span><i style="background:${R}"></i>Cash Selling</span><span><i style="background:#e8a93a"></i>Long Unwind</span>`;
 const ro=document.getElementById('ro');ro.innerHTML='<span class="mut">Move over the price chart for daily detail</span>';const mv=e=>{const r=main.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*W;let i=Math.round(v0+(x-L)*(n-1-v0)/(W-L-Rr));i=Math.max(v0,Math.min(n-1,i));const xh=document.getElementById('xh');xh.setAttribute('x1',xs(i));xh.setAttribute('x2',xs(i));xh.setAttribute('visibility','visible');const ch=S.c[i]!=null&&S.c[i-1]!=null?(S.c[i]/S.c[i-1]-1)*100:null,op=dl[i]!=null&&S.oi[i-1]?dl[i]/S.oi[i-1]*100:null;ro.innerHTML=`${D.dates[i]} · close ${S.c[i]??'–'} <span class="${cls(ch)}">${pc(ch,2)}</span> · delivered ${fmt(S.dq[i])} (${S.rat[i]==null?'–':S.rat[i].toFixed(2)+'× avg'}) · OI ${fmt(S.oi[i])} · ΔOI ${pc(op)}`};main.onpointermove=mv;main.onpointerdown=mv;main.onpointerleave=()=>document.getElementById('xh').setAttribute('visibility','hidden');
}
let rz;window.addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(draw,120)});
const h0=location.hash.slice(1);cur=D.stocks[h0]?h0:D.default;/* Click handlers for everything inside `R` (the whole page at start, a panel when it is first opened). The heavy panels are held as inert text until their tab is first opened. */
function bindPanel(R){
R.querySelectorAll('.tlfilter').forEach(b=>b.onclick=()=>{const p=b.closest('.timeline'),k=b.dataset.k;p.querySelectorAll('.tlfilter').forEach(x=>x.classList.toggle('on',x===b));p.querySelectorAll('.tlnode').forEach(n=>n.hidden=k!=='all'&&n.dataset.k!==k);p.querySelectorAll('.tlphase').forEach(ph=>ph.hidden=![...ph.querySelectorAll('.tlnode')].some(n=>!n.hidden))});
R.querySelectorAll('.tlgone a[data-tl]').forEach(a=>a.onclick=()=>{const n=document.getElementById('tl-'+a.dataset.tl);if(n){document.querySelectorAll('.tlfilter')[0].click();n.scrollIntoView({behavior:'smooth',block:'center'});n.classList.add('flash');setTimeout(()=>n.classList.remove('flash'),1600)}});
R.querySelectorAll('.fotoggle').forEach(b=>b.onclick=()=>{const v=b.closest('.subview'),only=b.dataset.fo==='1';v.querySelectorAll('.fotoggle').forEach(x=>x.classList.toggle('on',x===b));v.querySelectorAll('[data-fo]:not(.fotoggle)').forEach(x=>x.hidden=only&&x.dataset.fo!=='1')});
R.querySelectorAll('.h52tab').forEach(b=>b.onclick=()=>{const p=b.closest('.panel');p.querySelectorAll('.h52tab').forEach(x=>x.classList.toggle('on',x===b));p.querySelectorAll('.h52group').forEach(x=>x.hidden=x.dataset.h52Group!==b.dataset.h52)});
R.querySelectorAll('.h52cap').forEach(b=>b.onclick=()=>{const g=b.closest('.h52group'),f=b.dataset.mcapFilter;g.querySelectorAll('.h52cap').forEach(x=>x.classList.toggle('on',x===b));g.querySelectorAll('.h52card').forEach(x=>x.hidden=f!=='all'&&x.dataset.mcap!==f)});
R.querySelectorAll('.basetab').forEach(b=>b.onclick=()=>{const p=b.closest('.panel');p.querySelectorAll('.basetab').forEach(x=>x.classList.toggle('on',x===b));p.querySelectorAll('.basegroup').forEach(x=>x.hidden=x.dataset.baseGroup!==b.dataset.base)});
R.querySelectorAll('.urchip').forEach(b=>b.onclick=()=>{const g=b.closest('.urgrp');g.querySelectorAll('.urchip').forEach(x=>x.classList.toggle('on',x===b));urState[g.dataset.grp]=b.dataset.v;renderUpcoming()});
{const q=R.querySelector('#ur-q');if(q)q.oninput=renderUpcoming}
R.querySelectorAll('.subtab').forEach(b=>b.onclick=()=>{const bar=b.closest('.subtabs'),root=bar.parentElement;bar.querySelectorAll('.subtab').forEach(x=>{x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',String(x===b))});root.querySelectorAll(':scope > .subview').forEach(v=>v.hidden=v.dataset.sub!==b.dataset.sub);
 if(b.dataset.sub==='chart')draw();else if(b.dataset.sub==='watch')renderWatch();else if(b.dataset.sub==='follow')renderFollow();else if(b.dataset.sub==='results')renderUpcoming();else if(b.dataset.sub==='temp'||b.dataset.sub==='power')drawAlt();const bc=root.querySelector('.basecount');if(bc)bc.hidden=b.dataset.sub==='follow'});
R.querySelectorAll('.basefilter').forEach(b=>b.onclick=()=>{const f=b.dataset.baseFilter;activeBaseFilters.has(f)?activeBaseFilters.delete(f):activeBaseFilters.add(f);try{localStorage.setItem('desk-base-filters',JSON.stringify([...activeBaseFilters]))}catch(e){}applyBaseFilters()});
R.querySelectorAll('.basetab').forEach(b=>{const old=b.onclick;b.onclick=()=>{old();applyBaseFilters()}});applyBaseFilters();
R.querySelectorAll('.exswitchbtn').forEach(b=>b.onclick=()=>{const p=b.closest('.panel');p.querySelectorAll('.exswitchbtn').forEach(x=>x.classList.toggle('on',x===b));p.querySelectorAll('.exchangegroup').forEach(x=>x.hidden=x.dataset.exchangeGroup!==b.dataset.exchange)});
R.querySelectorAll('.seg[data-h]').forEach(b=>b.onclick=()=>{const v=b.closest('.uview')||document;v.querySelectorAll('.seg[data-h]').forEach(x=>x.classList.toggle('on',x===b));v.querySelectorAll('.hz').forEach(h=>h.hidden=h.dataset.h!==b.dataset.h)});
R.querySelectorAll('.ptchip').forEach(b=>b.onclick=()=>{const v=b.closest('.ptview');
 if(b.dataset.fo||b.dataset.ev){b.classList.toggle('on')}else{v.querySelectorAll('.ptchip[data-st]').forEach(x=>x.classList.toggle('on',x===b))}
 const st=v.querySelector('.ptchip[data-st].on').dataset.st,fo=!!v.querySelector('.ptchip[data-fo].on'),ev=!!v.querySelector('.ptchip[data-ev].on');
 v.querySelectorAll('tr[data-status],.shcard[data-status]').forEach(e=>{e.hidden=!((st==='ALL'||(st==='CONF'?e.dataset.conf==='1':e.dataset.status===st))&&(!fo||e.dataset.fo==='1')&&(!ev||e.dataset.ev==='1'))})});
R.querySelectorAll('.ptfbtn').forEach(b=>b.onclick=()=>{const v=b.closest('.subview');v.querySelectorAll('.ptfbtn').forEach(x=>x.classList.toggle('on',x===b));v.querySelectorAll('.ptview').forEach(x=>x.hidden=x.dataset.tf!==b.dataset.tf)});
R.querySelectorAll('.exwd').forEach(c=>{const f=()=>{const d=c.querySelector('.wdsel').value,p=c.querySelector('.wdper').value;c.querySelectorAll('.wdview').forEach(v=>v.hidden=!(v.dataset.wd===d&&v.dataset.wp===p))};c.querySelector('.wdsel').onchange=f;c.querySelector('.wdper').onchange=f});
R.querySelectorAll('.exrbtn').forEach(b=>b.onclick=()=>{const v=b.closest('.exlayout');v.querySelectorAll('.exrbtn').forEach(x=>x.classList.toggle('on',x===b));v.querySelectorAll('.exrange').forEach(x=>x.hidden=x.dataset.xr!==b.dataset.xr)});
}
document.addEventListener('click',e=>{const a=e.target.closest('a[data-go]');if(a){e.preventDefault();tab(a.dataset.go);window.scrollTo(0,0)}});
function renderToday(){document.querySelectorAll('.tdfocus[data-s]').forEach(el=>{const S=ensureStock(el.dataset.s),p=(D.stocks[el.dataset.s].pt||[]).find(x=>x.k===el.dataset.k&&x.tf===el.dataset.tf&&x.st===el.dataset.st);if(S&&p)el.querySelector('.tdchart').innerHTML=patChart(S,p)})}
const LAZY_INIT={calls:()=>renderUpcoming(),patterns:()=>{wlDigest();applyBaseFilters()}};
function ensurePanel(k){const p=document.getElementById('p-'+k);if(!p||!p.dataset.lazy)return;const t=document.getElementById('lazy-'+k);
 p.innerHTML=t.textContent.replace(/<\\\/script/g,'</script').replace(/<\\!--/g,'<!--');delete p.dataset.lazy;bindPanel(p);if(LAZY_INIT[k])LAZY_INIT[k]()}
bindPanel(document);renderWatch();renderHeat();renderPower();list();draw();renderToday();if(D.stocks[h0])tab('stocks');
"""
