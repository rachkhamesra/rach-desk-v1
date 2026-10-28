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
    upcoming = [r for r in M.get("results", []) if r["symbol"] == s and r["event_date"].normalize() >= M["dates"][-1].normalize()]
    result = ""
    if upcoming:
        event = min(upcoming, key=lambda r: r["event_date"])
        result = f' <span class="resultmark" title="Upcoming result: {event["event_date"]:%d %b %Y}">R</span>'
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
                    f'<td>{fs(r.dq5)}</td><td>{r.delivpct:.1f}</td><td{heat(r.px5, 10)}>{pc(r.px5)}</td><td>{fs(r.oi)}</td><td{heat(r.doi_pct, 25)}>{fl(r.doi5)}</td><td{heat(r.doi_pct, 25)}>{pc(r.doi_pct)}</td>'
                    f'<td>{mult(r.d_over_doi)}</td><td>{pct_badge(r.pct)}</td></tr>')
    head = [("#", "mut"), ("STOCK", "l"), ("DAYS ≥1.25× / 1.5×", ""), ("5-DAY AVG ÷ 20D", "l"), ("5D DELIVERED", ""), ("DELIV %", ""), ("PX 5D", ""), ("SSF OI", ""), ("ΔOI 5D", ""), ("ΔOI %", ""), ("DELIV ÷ ΔOI", ""), (f"{M['hist_label']} PCT", "")]
    q = len(all_df); q15 = int((all_df["d150"] >= 3).sum())
    return (f'<h2>Persistent delivery <span class="sub">≥3 OF THE LAST 5 SESSIONS ABOVE 1.25× 20D</span></h2>'
            f'<p class="desc">{q} qualify ({q15} at 1.5×); sorted by 5-day average ÷ 20d (the 5-day mean of delivered shares over the mean of the 20 sessions before them). Price and OI change from {M["persist_from"]:%d %b}. '
            f'{M["hist_label"]} pct ranks the 5-day average against the stock\'s own rolling 5-day averages.</p>' + table(head, rows))


def tab_cash_accumulation(M):
    def block(df, ma_heading, empty_text):
        rows = []
        for i, r in df.iterrows():
            state = f'<span class="setupstate active">ACTIVE</span>' if r.cooldown == 0 else f'<span class="setupstate cool">COOLDOWN {int(r.cooldown)}/2</span>'
            fresh = '<span class="newcash">NEW TODAY</span>' if r.new else ''
            rows.append(f'<tr class="{"cashnew" if r.new else ""}"><td class="mut">{i + 1}</td><td class="l">{stk(r.sym, M)} {fresh}</td><td>{state}</td><td><b>{int(r.days)}D</b></td>'
                        f'<td>{r.signal_date:%d %b}</td><td>{r.mas}</td><td{heat(r.ratio - 1, 1.5)}>{r.ratio:.2f}×</td><td{heat(r.px1d, 5)}>{pc(r.px1d)}</td>'
                        f'<td>{fs(r.oi)}</td><td{heat(r.doi_pct, 8)}>{fl(r.doi)}</td><td{heat(r.doi_pct, 8)}>{pc(r.doi_pct)}</td><td>{r.close:,.2f}</td></tr>')
        head = [("#", "mut"), ("STOCK", "l"), ("STATUS", ""), ("SETUP DAYS", ""), ("LAST SIGNAL", ""), (ma_heading, ""),
                ("DELIVERY ÷ 20D", ""), ("PX 1D", ""), ("SSF OI", ""), ("ΔOI", ""), ("ΔOI %", ""), ("CLOSE", "")]
        return table(head, rows, "cashwatch") if rows else f'<div class="card rempty">{empty_text}</div>'
    confirmed = block(M["cash_accumulation"], "ABOVE MA", "No F&amp;O stocks currently meet the confirmed setup or its two-session cooldown.")
    tracking = block(M["cash_tracking"], "BELOW MA", "No below-MA F&amp;O tracking candidates currently qualify or remain in cooldown.")
    return ('<h2>Cash Accumulation Watch</h2><div class="subl">F&amp;O · PRICE STRENGTH + DELIVERY + FALLING OI</div>'
            f'<p class="desc">A qualifying day closes higher and above the {" / ".join(str(n) for n in M["cash_mas"])}-day averages, with delivered shares above the prior 20-session average and total SSF OI falling. '
            f'Both lists require at least {metrics.CASH_MIN_DAYS} setup days. Setup Days counts qualifying sessions in the current episode; a pause remains visible for two trading sessions and resumes the same episode if the signal returns.</p>'
            '<h3 class="cashsub">CONFIRMED · ABOVE ALL ACTIVE AVERAGES</h3>' + confirmed +
            '<h3 class="cashsub track">TRACKING LIST · SAME SIGNAL, BELOW AT LEAST ONE AVERAGE</h3>'
            '<p class="desc">These names have positive price, above-average delivery and declining SSF OI, but still sit below one or more required averages. The Below MA column shows each unconfirmed average and the distance at the last signal.</p>' + tracking)


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


def tab_exchange(M):
    X = M.get("exchange_tracker", {})
    if not X.get("available"):
        return ('<h2>Exchange Tracker</h2><div class="subl">BSE OPTIONS ACTIVITY</div>'
                f'<div class="card rempty">{esc(X.get("commentary", ["BSE data is not available yet."])[0])}</div>')
    s = X["series"].dropna(subset=["roll5", "price"]).reset_index(drop=True)
    W, H = 900, 300
    tp, tlo, thi = _line_points(s["roll5"], W, H)
    pp, plo, phi = _line_points(s["price"], W, H)
    x0, xb = 44, W - 18; base = H - 30
    area = f'{x0},{base} {tp} {xb},{base}'
    ticks = "".join(f'<text x="{44 + (W - 62) * i / 4:.0f}" y="292" text-anchor="middle">{s.date.iloc[round((len(s)-1)*i/4)]:%b %y}</text>' for i in range(5))
    hero = (f'<svg class="exsvg hero" viewBox="0 0 {W} {H}" role="img" aria-label="BSE premium turnover and BSE share price">'
            f'<polygon points="{area}" class="exarea"/><polyline points="{tp}" class="exto"/><polyline points="{pp}" class="expx"/>'
            f'<text x="8" y="20">₹{thi:,.0f}cr</text><text x="8" y="{base}">₹{tlo:,.0f}cr</text>'
            f'<text x="{W-8}" y="20" text-anchor="end">₹{phi:,.0f}</text><text x="{W-8}" y="{base}" text-anchor="end">₹{plo:,.0f}</text>{ticks}</svg>')

    def bars(df, label, value, colour, current=False):
        w, h, l, top, bot = 560, 250, 40, 18, 42
        vals = pd.to_numeric(df[value], errors="coerce"); mx = max(float(vals.max()), 1)
        bw = (w - l - 12) / max(len(df), 1); out = []
        for i, (_, r) in enumerate(df.iterrows()):
            bh = float(r[value]) / mx * (h - top - bot); x = l + i * bw + 2; y = h - bot - bh
            cls = colour + (" latest" if current and i == len(df)-1 else "")
            out.append(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{max(3,bw-4):.1f}" height="{bh:.1f}"><title>{r[label]} · ₹{r[value]:,.0f} cr</title></rect>')
            out.append(f'<text x="{x+bw/2-2:.1f}" y="{h-24}" text-anchor="end" transform="rotate(-45 {x+bw/2-2:.1f} {h-24})">{r[label]}</text>')
        return f'<svg class="exsvg" viewBox="0 0 {w} {h}"><line x1="{l}" y1="{h-bot}" x2="{w-8}" y2="{h-bot}"/>' + "".join(out) + f'<text x="6" y="18">₹{mx:,.0f}cr</text></svg>'

    wd = X["same_weekday"].copy(); wd["label"] = wd.date.dt.strftime("%d %b %y")
    monthly = X["monthly"].copy(); monthly["label"] = pd.to_datetime(monthly.month + "-01").dt.strftime("%b %y")
    comments = "".join(f'<li>{esc(x)}</li>' for x in X["commentary"])
    return (f'<h2>Exchange Tracker</h2><div class="subl">BSE OPTIONS PREMIUM TURNOVER · ₹ CRORE</div>'
            f'<div class="exheadline"><div><span>LATEST</span><b>₹{X["latest"]:,.0f} cr</b></div><div><span>AS OF</span><b>{X["asof"]:%d %b %Y}</b></div><div><span>DAY</span><b>{esc(X["weekday"])}</b></div></div>'
            f'<div class="card excard"><div class="ch"><span class="ct">5D ROLLING PREMIUM TURNOVER</span><span><i class="exkey to"></i>5D premium <i class="exkey px"></i>BSE price</span></div>{hero}</div>'
            f'<div class="exgrid"><div class="card excard"><div class="ch"><span class="ct">{esc(X["weekday"].upper())} VS PRIOR {esc(X["weekday"].upper())}S</span><span class="mut">LATEST 13</span></div>{bars(wd,"label","premium_turnover_cr","exbar",True)}</div>'
            f'<div class="card excard"><div class="ch"><span class="ct">AVERAGE DAILY PREMIUM TURNOVER</span><span class="mut">CURRENT MONTH IS PARTIAL</span></div>{bars(monthly,"label","mean","exbar month",True)}</div></div>'
            f'<div class="card excomment"><h3>DAILY READ</h3><ul>{comments}</ul><a href="{esc(X["source"])}" target="_blank" rel="noopener">BSE KEY STATISTICS ↗</a></div>'
            '<p class="desc">Premium turnover is the BSE-reported daily Options Premium Turnover. The current month updates incrementally; if BSE has not published a new session, the last available observation remains visible.</p>')


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
            '<div class="chartgrid"><div class="charts"><div id="chartbox" class="chartcard"><svg id="ch"></svg></div>'
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
    panels = [("stocks", "STOCKS", tab_stocks(M)), ("screen", "1-DAY SCREEN", views(tab_screen)), ("persist", "PERSISTENT DELIVERY", views(tab_persist)),
              ("cash", "CASH ACCUMULATION", tab_cash_accumulation(M)), ("results", "RESULTS CALENDAR", views(tab_results)),
              ("rel", "RELATIVE PERFORMANCE", views(tab_rel)), ("at", "AT A MOVING AVERAGE", views(tab_at)),
              ("exchange", "EXCHANGE TRACKER", tab_exchange(M))]
    nav = "".join(f'<button class="tab{" on" if i == 0 else ""}" data-t="{k}">{lbl}</button>' for i, (k, lbl, _) in enumerate(panels))
    body = "".join(f'<section class="panel" id="p-{k}"{"" if i == 0 else " hidden"}>{h}</section>' for i, (k, _, h) in enumerate(panels))
    opts = "".join(f'<option value="{k}">{label}</option>' for k, label in choices)
    head = (f'<header><div class="brand">DESK</div><div class="headright"><select id="universe" aria-label="Stock universe">{opts}</select><div class="meta">{asof_text}<br><span class="mut">{M["N"]} sessions since {M["dates"][0]:%d %b %Y} · top 1,000 NSE shares · NSE + BSE delivery</span></div></div></header>')
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
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:13px;line-height:1.35}
header{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 18px 8px;border-bottom:1px solid var(--line)}
.brand{font-weight:800;letter-spacing:.18em;font-size:17px}.headright{display:flex;align-items:center;gap:12px}.meta{font-family:var(--mono);font-size:10.5px;text-align:right}.mut{color:var(--mut)}
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
.exheadline{display:flex;gap:28px;margin:12px 0 14px}.exheadline div{display:flex;flex-direction:column}.exheadline span{font:700 9px var(--sans);letter-spacing:.1em;color:var(--mut)}.exheadline b{font:700 17px var(--mono)}
.excard{padding:12px 14px;margin-bottom:12px}.exsvg{width:100%;height:auto;display:block;background:#111}.exsvg text{fill:var(--mut);font:10px var(--mono)}.exsvg line{stroke:var(--line)}
.exarea{fill:rgba(59,130,246,.22)}.exto{fill:none;stroke:#5aa9ff;stroke-width:2}.expx{fill:none;stroke:var(--am);stroke-width:2.3}.exkey{display:inline-block;width:17px;border-top:2px solid;margin:0 5px 2px 12px}.exkey.to{border-color:#5aa9ff}.exkey.px{border-color:var(--am)}
.exgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.exbar{fill:#4e85d8}.exbar.month{fill:#607fc2}.exbar.latest{fill:var(--am)}.excomment{padding:16px 18px;border-left:4px solid var(--am)}.excomment h3{margin:0 0 8px;font:800 10px var(--sans);letter-spacing:.11em}.excomment ul{margin:0 0 10px;padding-left:20px}.excomment li{margin:6px 0}.excomment a{font:700 9px var(--sans);letter-spacing:.08em;color:var(--am)}
@media(max-width:850px){.exgrid{grid-template-columns:1fr}.exheadline{gap:16px;flex-wrap:wrap}}
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
#insights{background:var(--panel);border-top:3px solid #f4f4f0;padding:12px;align-self:start;position:sticky;top:58px;max-height:calc(100vh - 80px);overflow:auto}.ititle{font:800 12px var(--sans);letter-spacing:.1em;margin-bottom:9px}.resultbox{background:rgba(232,169,58,.15);border-left:3px solid var(--am);padding:10px;margin-bottom:12px}.resultbox b{display:block;color:#ffd17a}.ievent{padding:9px 0;border-top:1px solid var(--line);font:11px var(--mono)}.ievent .idate{color:var(--mut);margin-right:7px}.itag{display:inline-block;font:800 9px var(--sans);letter-spacing:.06em;padding:3px 5px;margin-right:6px;background:#292929}.itag.del{color:#fff}.itag.oi{color:#8fc0ff}.inone{color:var(--mut);font-size:12px;line-height:1.5}
.mahere{margin-top:15px;padding-top:13px;border-top:2px solid #333}.mahit{margin-top:7px;padding:9px 10px;background:#1b1b1b;border-left:3px solid var(--am);font:11px var(--mono);line-height:1.5}.mahit b{font:800 12px var(--sans);color:#ffd17a}.mahit .cross{display:inline-block;margin-left:6px;padding:2px 5px;background:var(--g);color:#07140c;font:800 8px var(--sans);letter-spacing:.05em}.mahit .fresh{color:var(--g)}
#callintel{margin-top:10px}.callhead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;background:var(--panel);border-top:3px solid #f4f4f0;padding:12px 14px;margin-bottom:8px}.callhead h3{margin:0;font-size:16px;letter-spacing:.04em}.callhead a{color:#ffd17a;font:11px var(--mono)}.callmeta{color:var(--mut);font:10px var(--mono);margin-top:3px}.callpanels{display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:8px}.callsection{background:var(--panel);border-top:3px solid #444;padding:12px;min-width:0}.callsection.outlookpanel{border-color:var(--g)}.callsection.focuspanel{border-color:var(--am)}.callsection.actualspanel{border-color:#5aa9ff}.callsection h4{margin:0 0 9px;font:800 10px var(--sans);letter-spacing:.1em;color:var(--mut)}.outlook{padding:9px 10px;margin-bottom:7px;background:#191919;border-left:3px solid #777;font-size:12px;line-height:1.45}.outlook.positive{border-color:var(--g)}.outlook.cautious,.outlook.negative{border-color:var(--r)}.outlook b{display:block;margin-bottom:2px}.evidence{display:block;color:#9d9d96;font:10px var(--mono);margin-top:4px}.focus{display:grid;grid-template-columns:1fr auto;gap:9px;padding:7px 0;border-bottom:1px solid var(--line);font-size:12px}.focus small{display:block;color:var(--mut);margin-top:2px}.qcount{font:700 11px var(--mono);color:#ffd17a}.metricgrid{display:grid;grid-template-columns:1fr;gap:7px}.metric{background:#191919;padding:8px 9px;font-size:11px;line-height:1.4}.metric b{display:block;color:var(--mut);font:800 9px var(--sans);letter-spacing:.07em;margin-bottom:2px}.congrats{display:flex;gap:16px;align-items:baseline;padding:10px;background:rgba(232,169,58,.1);margin-top:12px}.congrats strong{font:700 24px var(--mono);color:#ffd17a}.congrats span{font-size:11px;color:var(--mut)}.callnone{background:var(--panel);border-top:3px solid #444;padding:12px;color:var(--mut);font-size:12px}.aicaveat{margin-top:8px;color:#666;font-size:10px}
#ro{min-height:22px;font:11px var(--mono);color:#cfcfc8;padding:5px 4px}
#lg{display:flex;flex-wrap:wrap;gap:6px 18px;font:12px var(--mono);color:var(--mut);padding:2px 4px 10px}#lg i{display:inline-block;width:14px;height:10px;margin-right:6px;vertical-align:-1px}#lg u{display:inline-block;width:18px;border-top:2px solid;margin-right:5px;vertical-align:middle}
footer{max-width:1280px;margin:0 auto;padding:0 22px 40px;color:var(--mut);font-size:13px}
@media (max-width:900px){.sx{padding-top:76px}.sl{width:100%;flex-wrap:wrap}.sl #q{flex-basis:100%}#sort{width:100%}#list{top:38px;width:100%;max-height:230px}.chartgrid,.callpanels{grid-template-columns:1fr}#insights{position:static;max-height:none}.hd1 b{font-size:21px}header{flex-direction:column;align-items:flex-start}.headright{align-items:flex-start;flex-direction:column}.meta{text-align:left}h2{font-size:21px}.hz{grid-template-columns:1fr}.atrow{flex-direction:column;gap:9px}main{padding:4px 9px 35px}}
"""

JS = r"""
const D=JSON.parse(document.getElementById('data').textContent),ALL=Object.keys(D.stocks);
const COL={32:'#5aa9ff',50:'#f5a623',100:'#b58cff',200:'#ffd84d',233:'#3fd0a0',377:'#ff7aa2',610:'#9a9a94'};
const G='#2fbf71',R='#ef5a4d',GL='rgba(47,191,113,.64)',RL='rgba(239,90,77,.64)',GR='#a3a39c',GRL='rgba(163,163,156,.46)';
let cur=null,rng=252,thr=1.25,universe='top1000',SY=D.universes[universe]||ALL,selectedMas=new Set([50,200]);
try{const saved=JSON.parse(localStorage.getItem('desk-mas'));if(Array.isArray(saved))selectedMas=new Set(saved.map(Number))}catch(e){}
function tab(t){const b=document.querySelector('.tab[data-t="'+t+'"]');if(b)b.click()}
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.panel').forEach(p=>p.hidden=p.id!=='p-'+b.dataset.t);if(b.dataset.t==='stocks'){draw()}});
document.querySelectorAll('.seg[data-h]').forEach(b=>b.onclick=()=>{const v=b.closest('.uview')||document;v.querySelectorAll('.seg[data-h]').forEach(x=>x.classList.toggle('on',x===b));v.querySelectorAll('.hz').forEach(h=>h.hidden=h.dataset.h!==b.dataset.h)});
document.querySelectorAll('.seg[data-r]').forEach(b=>b.onclick=()=>{rng=+b.dataset.r;document.querySelectorAll('.seg[data-r]').forEach(x=>x.classList.toggle('on',x===b));draw()});
document.querySelectorAll('.mab').forEach(b=>{const m=+b.dataset.ma;b.disabled=D.dates.length<m+1;b.classList.toggle('on',selectedMas.has(m)&&!b.disabled);b.title=b.disabled?`Needs ${m+1} sessions; currently ${D.dates.length}`:`Toggle ${m}-day moving average`;b.onclick=()=>{selectedMas.has(m)?selectedMas.delete(m):selectedMas.add(m);b.classList.toggle('on',selectedMas.has(m));try{localStorage.setItem('desk-mas',JSON.stringify([...selectedMas]))}catch(e){}draw()}});
document.getElementById('thr').onchange=e=>{thr=+e.target.value;draw()};
document.getElementById('universe').onchange=e=>{universe=e.target.value;SY=D.universes[universe]||ALL;document.querySelectorAll('.uview').forEach(v=>v.hidden=v.dataset.u!==universe);if(!SY.includes(cur))cur=SY[0]||D.default;list();draw()};
function sma(a,n){const o=new Array(a.length).fill(null);let s=0,c=0;for(let i=0;i<a.length;i++){const v=a[i];if(v!=null){s+=v;c++}if(i>=n){const u=a[i-n];if(u!=null){s-=u;c--}}if(c===n&&i>=n-1)o[i]=s/n}return o}
function fmt(x){if(x==null)return'–';const a=Math.abs(x);return a>=1e7?(x/1e7).toFixed(2)+' cr':a>=1e5?(x/1e5).toFixed(1)+' L':Math.round(x).toLocaleString()}
function fL(x){return x==null?'–':(x>=0?'+':'−')+Math.abs(x/1e5).toLocaleString(undefined,{maximumFractionDigits:1,minimumFractionDigits:1})+' L'}
function pc(x,d=1){return x==null?'–':(x>=0?'+':'−')+Math.abs(x).toFixed(d)+'%'}
function cls(x){return x==null?'':x>=0?'g':'r'}
function escH(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function callPanel(S){const el=document.getElementById('callintel'),c=S.call;if(!c||!c.analysis){el.innerHTML='<div class="callnone">CALL INTELLIGENCE · No bundled transcript analysis for this stock yet.</div>';return}const a=c.analysis,o=a.next_quarter_outlook||[],f=a.analyst_focus||[],cg=a.congratulations||{},sector=a.company_type==='manufacturer'?a.manufacturer:a.company_type==='bank_lender'?a.bank_lender:null;const labels={revenue_growth:'Revenue growth',volume_growth:'Volume growth',order_inflow:'Order inflow',demand_outlook:'Demand outlook',margin_outlook:'Margin outlook',ebitda_margin:'EBITDA margin',credit_growth:'Credit growth',credit_deposit_ratio:'Credit–deposit ratio',disbursements:'Disbursements',nim_outlook:'NIM outlook',asset_quality:'Asset quality',credit_cost_outlook:'Credit cost outlook'};const actuals=sector?Object.entries(sector).filter(([,v])=>v).map(([k,v])=>`<div class="metric"><b>${escH(labels[k]||k)}</b>${escH(v)}</div>`).join(''):'';const risks=(a.key_risks||[]).map(v=>`<div class="metric"><b>RISK / WATCHPOINT</b>${escH(v)}</div>`).join('');el.innerHTML=`<div class="callhead"><div><h3>CALL INTELLIGENCE · ${escH(a.call_period||'LATEST CALL')}</h3><div class="callmeta">${escH(a.company_type.replace('_',' ').toUpperCase())} · filed ${escH((c.filed_at||'').slice(0,10))}</div></div><a href="${escH(c.source_url)}" target="_blank" rel="noopener">OPEN TRANSCRIPT ↗</a></div><div class="callpanels"><div class="callsection outlookpanel"><h4>NEXT QUARTER OUTLOOK</h4>${o.length?o.map(x=>`<div class="outlook ${escH(x.tone)}"><b>${escH(x.topic)}</b>${escH(x.summary)}<span class="evidence">“${escH(x.evidence)}”</span></div>`).join(''):'<div class="inone">No explicit next-quarter guidance found.</div>'}</div><div class="callsection focuspanel"><h4>WHAT ANALYSTS CARED ABOUT</h4>${f.length?f.map(x=>`<div class="focus"><div><b>${escH(x.topic)}</b><small>${escH(x.why_it_mattered)}</small></div><span class="qcount">${x.question_count}Q</span></div>`).join(''):'<div class="inone">No analyst-question themes extracted.</div>'}<div class="congrats"><strong>${Number(cg.index_pct||0).toFixed(0)}%</strong><div>CONGRATULATIONS INDEX<br><span>${cg.count||0} congratulatory turns / ${cg.analyst_turns||0} analyst turns</span></div></div></div><div class="callsection actualspanel"><h4>KEY ACTUALS &amp; GUIDANCE</h4><div class="metricgrid">${actuals||'<div class="inone">No sector actuals extracted.</div>'}${risks}</div><div class="aicaveat">Static research from the linked transcript. Check the source before relying on a statement.</div></div></div>`}
/* ---------- ticker list ---------- */
function list(){const q=document.getElementById('q').value.trim().toUpperCase(),so=document.getElementById('sort').value;
 const key={az:s=>s,ratio:s=>-(D.stocks[s].sm.ratio??-1e9),px:s=>-(D.stocks[s].sm.px??-1e9),rs:s=>-(D.stocks[s].sm.rel[1][0]??-1e9)}[so];
 const a=SY.filter(s=>!q||s.includes(q)).sort((x,y)=>{const a=key(x),b=key(y);return a<b?-1:a>b?1:0});
 document.getElementById('list').innerHTML=a.map(s=>{const m=D.stocks[s].sm,r=D.stocks[s].result?'<span class="resultmark" title="Upcoming result">R</span>':'';return `<div class="li${s===cur?' on':''}" data-s="${s}" tabindex="-1"><b>${s} ${r}</b><span class="${cls(m.px)}">${pc(m.px)}</span><span class="mut">${m.ratio==null?'–':m.ratio.toFixed(1)+'×'}</span></div>`}).join('')||'<div class="li mut">No match</div>'}
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
 const m=S.sm,last=S.c[n-1],lastOI=S.oi[n-1],dOI=dl[n-1],up=S.c[n-1]>=S.c[n-2],bu=dOI==null?'–':dOI>=0?(up?'Long Buildup':'Cash Selling'):(up?'Cash Buying':'Long Unwind'),buc=dOI==null?'':bu==='Long Buildup'?'g':bu==='Cash Selling'?'r':'';
 const rs=D.hz.map((h,k)=>{const r=m.rel[k];return `<div><span>${h[0].toUpperCase()}</span><b class="${cls(r[0])}">${pc(r[0])}</b> <i class="mut" style="font-style:normal">#${r[1]??'–'}/${SY.length}</i></div>`}).join(''),rbadge=S.result?`<span class="resultmark" title="Upcoming result">R</span>`:'';
 document.getElementById('sh').innerHTML=`<div class="hd1"><b>${cur}</b>${rbadge}<span class="px">${last==null?'–':last.toFixed(2)}</span><span class="${cls(m.px)}">${pc(m.px,2)}</span></div><div class="chips2"><div><span>DELIVERED</span>${fmt(m.dq)}</div><div><span>÷ 20D AVG</span>${m.ratio==null?'–':m.ratio.toFixed(2)+'×'}</div><div><span>DELIV %</span>${m.dp==null?'–':m.dp.toFixed(1)}</div><div><span>BSE %</span>${m.bse==null?'–':m.bse.toFixed(0)}</div><div><span>SSF OI</span>${fmt(lastOI)}</div><div><span>ΔOI 1D</span><b class="${cls(dOI)}">${fL(dOI)}</b></div><div><span>OI SIGNAL</span><b class="${buc}">${bu}</b></div></div><div class="rsrow">${rs}</div>`;
 const events=[];for(let i=Math.max(1,n-30);i<n;i++){const move=S.c[i]!=null&&S.c[i-1]!=null?(S.c[i]/S.c[i-1]-1)*100:null;if((S.rat[i]??0)>=1.5)events.push({i,kind:'del',txt:`${S.rat[i].toFixed(2)}× delivery · ${pc(move)}`});if(dl[i]!=null&&S.oi[i-1]){const op=dl[i]/S.oi[i-1]*100;if(Math.abs(op)>=3){const pu=move>=0,label=dl[i]>=0?(pu?'Long Buildup':'Cash Selling'):(pu?'Cash Buying':'Long Unwind');events.push({i,kind:'oi',txt:`${label} · ${pc(op)} OI`})}}}events.sort((a,b)=>b.i-a.i);let ih='<div class="ititle">RECENT ACTIVITY · 30 SESSIONS</div>';if(S.result)ih+=`<div class="resultbox"><b>UPCOMING RESULT</b>${S.result.date} · ${S.result.status}</div>`;ih+=events.length?events.slice(0,14).map(e=>`<div class="ievent"><span class="idate">${D.dates[e.i].slice(5)}</span><span class="itag ${e.kind}">${e.kind==='del'?'DELIVERY':'OI'}</span>${e.txt}</div>`).join(''):'<div class="inone">No delivery ≥1.5× average or daily OI move ≥3% in the last 30 sessions.</div>';ih+='<div class="mahere"><div class="ititle">AT A MOVING AVERAGE</div>'+(S.at&&S.at.length?S.at.map(a=>`<div class="mahit"><b>${a.ma}-DAY MA</b>${a.crossed?'<span class="cross">CROSSED TODAY</span>':''}<br><span class="${a.new?'fresh':''}">${a.above?'above':'below'} by ${Math.abs(a.dist).toFixed(2)}% · ${Math.abs(a.dist/a.sigma).toFixed(2)}σ${a.new?' · new today':''}</span></div>`).join(''):'<div class="inone">Not currently within 0.5σ of an active moving average.</div>')+'</div>';document.getElementById('insights').innerHTML=ih;
 callPanel(S);
 document.getElementById('lg').innerHTML=mas.map(([m])=>`<span><u style="border-color:${COL[m]}"></u>${m}</span>`).join('')+`<span><u style="border-color:#fff"></u>price / RS</span><span><i style="background:${G}"></i>Long Buildup</span><span><i style="background:#5aa9ff"></i>Cash Buying</span><span><i style="background:${R}"></i>Cash Selling</span><span><i style="background:#e8a93a"></i>Long Unwind</span>`;
 const ro=document.getElementById('ro');ro.innerHTML='<span class="mut">Move over the price chart for daily detail</span>';const mv=e=>{const r=main.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*W;let i=Math.round(v0+(x-L)*(n-1-v0)/(W-L-Rr));i=Math.max(v0,Math.min(n-1,i));const xh=document.getElementById('xh');xh.setAttribute('x1',xs(i));xh.setAttribute('x2',xs(i));xh.setAttribute('visibility','visible');const ch=S.c[i]!=null&&S.c[i-1]!=null?(S.c[i]/S.c[i-1]-1)*100:null;ro.innerHTML=`${D.dates[i]} · close ${S.c[i]??'–'} <span class="${cls(ch)}">${pc(ch,2)}</span> · delivered ${fmt(S.dq[i])} (${S.rat[i]==null?'–':S.rat[i].toFixed(2)+'× avg'}) · OI ${fmt(S.oi[i])} · ΔOI ${fL(dl[i])}`};main.onpointermove=mv;main.onpointerdown=mv;main.onpointerleave=()=>document.getElementById('xh').setAttribute('visibility','hidden');
}
let rz;window.addEventListener('resize',()=>{clearTimeout(rz);rz=setTimeout(draw,120)});
const h0=location.hash.slice(1);cur=D.stocks[h0]?h0:D.default;list();draw();
"""
