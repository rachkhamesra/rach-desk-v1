"""Very experimental: ascending triangles, descending triangles and rectangles on daily adjusted prices.

Everything is built from swing points. A swing high is a day whose high is the highest of the k sessions either side; a swing low likewise.
  Flat level   : two or more swing highs (or lows) within TOL of each other, at least MIN_GAP sessions apart. That is the resistance (or support).
  Sloped line  : a least-squares line through the swing lows (or highs) that run into the pattern, which must slope the right way and not be broken.
  Triangle     : a flat level plus a sloped line that converge: the gap between them shrinks to under CONVERGE of its starting size.
  Rectangle    : a flat resistance AND a flat support, a clean range of RANGE_MIN to RANGE_MAX of the price, with the closes mostly inside it.
A pattern is "fresh" for RECENT sessions after a close beyond its flat level (BREAKOUT up, BREAKDOWN down); SETUP means the close is within NEAR of that
level without crossing it; FORMING means the pattern stands but price is further away. The measured-move target adds the pattern's widest height to the break.
Nothing here says a break will follow through. See the page for the caveats.
"""
from collections import namedtuple

import numpy as np
import pandas as pd

K = 4                 # a swing point beats the k sessions either side
TOL = 0.02            # swing highs (lows) within 2% of each other touch the same level
RECT_TOL = 0.02       # both of a rectangle's levels have to hold
MIN_GAP = 12          # sessions between the first and last touch of a flat level
MIN_TOUCHES = 3       # a flat level must have been touched more than twice, by touches at least `gap` bars apart (swing highs a few bars apart are one test): two touches are just a developing pattern
MIN_DAYS, MAX_DAYS = 35, 270
CONVERGE = 0.80       # a triangle's gap now is at most this share of its starting gap
HEIGHT_MIN, HEIGHT_MAX = 0.06, 0.50   # a triangle starts between 6% and 50% of price tall; a rectangle is between RANGE_MIN and RANGE_MAX
RANGE_MIN, RANGE_MAX = 0.07, 0.40
RECENT = 10           # a break is fresh for this many sessions (the same window the Short Ideas charts highlight)
FORMING_MAX = 0.10    # a standing pattern whose price is further than 10% from the trigger level is not listed
NEAR = 0.04
BREAK = 0.01          # a close 1% beyond the level counts as through it
PIERCE = 0.03         # an earlier excursion this far beyond the level before the last RECENT sessions invalidates the pattern
CONFIRM = 1.25        # delivery on the break session at least this multiple of its own 20-session average (10-week for weekly) is high-delivery
MIN_TURNOVER_CR = 2.0 # median daily rupee turnover, so thin circuit-bound names do not fill the lists
CHART_DAYS = 230
# Bar-count settings per timeframe. The rules are identical (levels, touches, convergence, percentages); only what "a few bars" means differs.
#   k: a swing point beats this many bars either side; gap: bars between the first and last touch; bars: age limits of a pattern; recent: how long a break stays fresh;
#   wide: a flat level whose first and last touch are at least this many bars apart (about a quarter) needs only two touches, not three; retest: how many bars before the sloped side starts the flat level may last be touched; pad: bars of slack when picking swing points; chart: bars drawn.
Cfg = namedtuple("Cfg", "name unit k gap min_bars max_bars recent retest pad chart wide")
DAILY = Cfg("daily", "sessions", 4, 12, 35, 270, 10, 10, 5, 230, 60)
WEEKLY = Cfg("weekly", "weeks", 2, 5, 26, 156, 4, 4, 2, 140, 12)
KINDS = [("ascending", "ASCENDING TRIANGLE", "bullish"), ("descending", "DESCENDING TRIANGLE", "bearish"), ("rectangle", "RECTANGLE", "range")]


def swings(x, k=K, high=True):
    """[(index, price)] of confirmed swing highs (or lows): a point that beats the k bars on each side (strictly the left, ties allowed on the right so a flat top is counted
    once, at its first bar). The newest k bars cannot be confirmed yet. A window with a gap in it is skipped. Vectorised over sliding windows."""
    x = np.asarray(x, float)
    if len(x) < 2 * k + 1: return []
    win = np.lib.stride_tricks.sliding_window_view(x, 2 * k + 1)
    v, left, right = win[:, k], win[:, :k], win[:, k + 1:]
    ok = ~np.isnan(win).any(axis=1)
    m = ok & ((v > left.max(axis=1)) & (v >= right.max(axis=1)) if high else (v < left.min(axis=1)) & (v <= right.min(axis=1)))
    return [(int(i), float(x[i])) for i in np.flatnonzero(m) + k]


def clusters(points, tol=TOL, min_gap=MIN_GAP):
    """Every group of swing points within tol of a seed point and spanning at least min_gap bars: [(level, members)], in seed order. The level is the median price of the group."""
    if len(points) < 2: return []
    idx = np.array([i for i, _ in points]); pr = np.array([p for _, p in points], float)
    out, seen = [], set()
    for p0 in pr:
        m = np.abs(pr / p0 - 1) <= tol
        if m.sum() < 2: continue
        key = m.tobytes()
        if key in seen: continue
        ii = idx[m]
        if ii[-1] - ii[0] < min_gap: continue
        seen.add(key); out.append((float(np.median(pr[m])), [(int(i), float(p)) for i, p in zip(ii, pr[m])]))
    return out


def spaced(members, sep):
    """The touches that count: each at least sep bars after the one before. Swing highs a few bars apart are one test of a level, not two."""
    out = []
    for m in members:
        if not out or m[0] - out[-1][0] >= sep: out.append(m)
    return out


def _line(points):
    """The trendline as you would draw it: through the first and last point of the chain. Points between that sit well beyond it on the wrong side disqualify the pattern."""
    (x0, y0), (x1, y1) = points[0], points[-1]
    slope = (y1 - y0) / (x1 - x0)
    return float(slope), float(y0 - slope * x0)


def streak_start(C, level, up, n):
    """Where the current unbroken run of closes beyond the level began, or None when the latest close is not beyond it (a wobble earlier does not count)."""
    thr = level * (1 + BREAK) if up else level * (1 - BREAK)
    beyond = (C[:n] > thr) if up else (C[:n] < thr)
    if not beyond[n - 1]: return None
    i = n - 1
    while i > 0 and beyond[i - 1]: i -= 1
    return i


def _status(C, level, up, n, cfg=DAILY):
    """BREAKOUT/BREAKDOWN if the first close beyond the level came within the last RECENT sessions and it still holds; SETUP when near; else FORMING."""
    now = C[n - 1]; begun = streak_start(C, level, up, n)
    if begun is not None and begun >= n - cfg.recent: return "BREAKOUT" if up else "BREAKDOWN", int(begun)
    gap = (level / now - 1) if up else (now / level - 1)
    if 0 <= gap <= NEAR: return "SETUP", None
    return ("FORMING", None) if 0 <= gap <= FORMING_MAX else (None, None)


def chain(points, up):
    """The rising chain of swing lows (up=True) or falling chain of swing highs: the points that are lower (higher) than every later swing point of their kind.
    That is the line price keeps bouncing off while the other side stays flat, with the noise between the points left out."""
    out = []
    for j, (i, p) in enumerate(points):
        later = [q for _, q in points[j + 1:]]
        if not later or (p < min(later) if up else p > max(later)): out.append((i, p))
    return out


def triangle(H, L, C, up, cfg=DAILY):
    """Ascending (up=True: flat top, rising lows) or descending (flat bottom, falling highs). Returns the best match or None."""
    n = len(C)
    flat_pts = swings(H if up else L, cfg.k, up); slope_pts = swings(L if up else H, cfg.k, not up)
    best = None
    for level, mem in clusters(flat_pts, TOL, cfg.gap):
        run = [(i, p) for i, p in chain([q for q in slope_pts if q[0] >= mem[0][0] - cfg.pad], up) if ((p < level * .97) if up else (p > level * 1.03))]
        mem = spaced(mem, cfg.gap)
        if len(mem) < (2 if len(mem) >= 2 and mem[-1][0] - mem[0][0] >= cfg.wide else MIN_TOUCHES): continue          # touches far apart are evidence enough: two will do
        if len(run) < 3: continue                                                              # three points on the sloped side, so it is a line and not just two dots
        i_s = run[0][0]; touches = mem
        if mem[-1][0] < i_s - cfg.retest or not (cfg.min_bars <= n - i_s <= cfg.max_bars): continue            # the flat level must be tested again once the sloped side has started
        seg = H[i_s:n - cfg.recent] if up else L[i_s:n - cfg.recent]
        if len(seg) and ((seg.max() > level * (1 + PIERCE)) if up else (seg.min() < level * (1 - PIERCE))): continue          # it already broke out once: not this pattern
        slope, icpt = _line(run); line = lambda i: slope * i + icpt
        first, last = run[0][1], run[-1][1]
        if (last < first * 1.03) if up else (last > first * .97): continue                                                      # the lows must really rise (the highs must really fall)
        if any((p < line(i) * .94) if up else (p > line(i) * 1.06) for i, p in run): continue                                  # the chain must sit close to its line
        g0 = (level - line(i_s)) if up else (line(i_s) - level); gn = (level - line(n - 1)) if up else (line(n - 1) - level)
        if not (HEIGHT_MIN <= g0 / level <= HEIGHT_MAX) or gn <= 0 or gn > g0 * CONVERGE: continue
        ix = np.arange(i_s, n)
        inside = (C[i_s:] >= line(ix) * .97) if up else (C[i_s:] <= line(ix) * 1.03)
        if inside.mean() < .95: continue
        status, brk = _status(C, level, up, n, cfg)
        if status is None: continue
        score = len(touches) + len(run) + (n - i_s) / 40
        if best is None or score > best["score"]:
            best = dict(kind="ascending" if up else "descending", status=status, break_idx=brk, level=level, i0=i_s, days=n - i_s, slope=slope, icpt=icpt,
                        touches_flat=len(touches), touches_line=len(run), flat_pts=touches, line_pts=run, height=g0, height_pct=g0 / level * 100,
                        target=level + g0 if up else level - g0, score=score)
    return best


def rectangle(H, L, C, cfg=DAILY):
    n = len(C); best = None
    bottoms = clusters(swings(L, cfg.k, False), RECT_TOL, cfg.gap)                     # the same for every top, so found once
    for r_level, r_mem in clusters(swings(H, cfg.k, True), RECT_TOL, cfg.gap):
        r_mem = spaced(r_mem, cfg.gap)
        if len(r_mem) < MIN_TOUCHES: continue
        for s_level, s_mem in bottoms:
            s_mem = spaced(s_mem, cfg.gap)
            if s_level >= r_level: continue
            i0 = min(r_mem[0][0], s_mem[0][0])
            if not (cfg.min_bars <= n - i0 <= cfg.max_bars): continue
            h = r_level - s_level; hp = h / s_level
            if not (RANGE_MIN <= hp <= RANGE_MAX): continue
            if H[i0:n - cfg.recent].max() > r_level * (1 + PIERCE) or L[i0:n - cfg.recent].min() < s_level * (1 - PIERCE): continue
            body = C[i0:n - cfg.recent]
            if len(body) < 10 or ((body >= s_level * .98) & (body <= r_level * 1.02)).mean() < .90: continue
            if abs(C[i0:i0 + cfg.recent].mean() - C[-cfg.recent:].mean()) > 0.5 * h: continue                       # a drifting channel is not a range: the average close must not have moved more than half the range
            touches = len(r_mem) + len(s_mem)
            if len(r_mem) < MIN_TOUCHES or len(s_mem) < MIN_TOUCHES or touches < 7: continue
            now = C[n - 1]
            up_at, dn_at = streak_start(C, r_level, True, n), streak_start(C, s_level, False, n)
            if up_at is not None and up_at >= n - cfg.recent: status, brk, up = "BREAKOUT", int(up_at), True
            elif dn_at is not None and dn_at >= n - cfg.recent: status, brk, up = "BREAKDOWN", int(dn_at), False
            elif now >= r_level * (1 - NEAR) and now <= r_level * (1 + BREAK): status, brk, up = "AT TOP", None, True
            elif now <= s_level * (1 + NEAR) and now >= s_level * (1 - BREAK): status, brk, up = "AT BOTTOM", None, False
            elif s_level * (1 - BREAK) <= now <= r_level * (1 + BREAK): status, brk, up = "IN RANGE", None, True
            else: continue
            score = touches + (n - i0) / 40
            if best is None or score > best["score"]:
                best = dict(kind="rectangle", status=status, break_idx=brk, level=r_level if up else s_level, top=r_level, bottom=s_level, i0=i0, days=n - i0, slope=0.0, icpt=r_level,
                            touches_flat=len(r_mem), touches_line=len(s_mem), flat_pts=r_mem, line_pts=s_mem, height=h, height_pct=hp * 100,
                            target=r_level + h if up else s_level - h, score=score,
                            position=(now - s_level) / h * 100)
    return best


def scan(H, L, C, cfg=DAILY):
    """All three detectors on one stock's arrays (oldest first). {kind: result or None}"""
    return {"ascending": triangle(H, L, C, True, cfg), "descending": triangle(H, L, C, False, cfg), "rectangle": rectangle(H, L, C, cfg)}


def series(M, cfg=DAILY):
    """The bars the detectors and charts work on. Daily comes straight from the panels; weekly resamples them: open of the first session, highest high, lowest low,
    close of the last session, delivered shares summed. The week still in progress is the last bar. `where` maps a bar to the daily session positions it covers."""
    syms = list(M["syms"]); idx = M["C"].index
    if cfg.name == "daily":
        S = dict(C=M["C"][syms], H=M["H"][syms], L=M["L"][syms], O=M["O"][syms], DQ=M["DQ"][syms], dc=M["dcode"][syms], ma=(50, 100),
                 ma1=M["ma"][50][syms], ma2=M["ma"][100][syms], where=[(i, i) for i in range(len(idx))], ends=list(idx))
        S["avg"] = S["DQ"].shift(1).rolling(20, min_periods=15).mean()
        return S
    wk = pd.Series(np.arange(len(idx)), index=idx).groupby(idx.to_period("W-FRI"))
    first, last = wk.min().to_numpy(), wk.max().to_numpy(); ends = idx[last]
    pick = lambda df, f: df[syms].groupby(idx.to_period("W-FRI")).agg(f).set_axis(ends)
    C = pick(M["C"], "last"); DQ = pick(M["DQ"], "sum")
    ret = C.pct_change(fill_method=None)
    S = dict(C=C, H=pick(M["H"], "max"), L=pick(M["L"], "min"), O=pick(M["O"], "first"), DQ=DQ, dc=np.sign(ret).where(ret.abs() > 0.01, 0.0).where(ret.notna()), ma=(10, 30),
             ma1=C.rolling(10, min_periods=10).mean(), ma2=C.rolling(30, min_periods=30).mean(), where=list(zip(first.tolist(), last.tolist())), ends=list(ends))
    S["avg"] = DQ.shift(1).rolling(10, min_periods=7).mean()
    return S


def scan_timeframe(M, cfg=DAILY, charts=True):
    """Scans every liquid stock in the universe on one timeframe. None when there is too little history for it."""
    S = series(M, cfg); n = len(S["C"])
    if (M["N"] < 120) or n < cfg.min_bars + cfg.k * 2 + 10: return None
    syms = list(S["C"].columns); C, H, L = S["C"], S["H"], S["L"]; Cd = M["C"][syms]
    turn = (Cd * M["TQ"][syms]).iloc[-60:].median() / 1e7                                  # rupees traded per day, in crore
    fo = set(M["memberships"].get("fo", [])); nd = len(Cd)
    out = {"asof": M["dates"][M["T"]], "found": {k: [] for k, _, _ in KINDS}, "charts": {}, "scanned": 0, "cfg": cfg}
    nifty = M["nifty"].reindex(Cd.index).ffill()
    for s in syms:
        if not turn.get(s, 0) >= MIN_TURNOVER_CR or C[s].iloc[-max(8, cfg.min_bars // 4):].isna().sum() > 1: continue
        out["scanned"] += 1
        res = scan(H[s].to_numpy(float), L[s].to_numpy(float), C[s].ffill().to_numpy(float), cfg)
        for kind, r in res.items():
            if not r: continue
            c = Cd[s]; rat = M["RAT"][s].iloc[-1]
            b = r.get("break_idx"); bd = S["avg"][s].iloc[b] if b is not None else np.nan
            brk = float(S["DQ"][s].iloc[b] / bd) if b is not None and pd.notna(bd) and bd > 0 and pd.notna(S["DQ"][s].iloc[b]) else np.nan
            r.update(brk_ratio=brk, confirmed=bool(b is not None and pd.notna(brk) and brk >= CONFIRM), sym=s, close=float(c.iloc[-1]), px1d=float((c.iloc[-1] / c.iloc[-2] - 1) * 100), fo=s in fo, tf=cfg.name,
                     rs3m=float(((c.iloc[-1] / c.iloc[-64]) / (nifty.iloc[-1] / nifty.iloc[-64]) - 1) * 100) if nd > 64 else np.nan,
                     ratio=float(rat) if pd.notna(rat) else np.nan, turnover=float(turn[s]))
            out["found"][kind].append(r)
    order = {"BREAKOUT": 0, "BREAKDOWN": 0, "AT TOP": 1, "AT BOTTOM": 1, "SETUP": 1, "IN RANGE": 2, "FORMING": 2}
    for kind in out["found"]:
        out["found"][kind].sort(key=lambda r: (order.get(r["status"], 3), -r["score"]))
    for rows in out["found"].values():
        for r in rows: r["event"] = None
    if charts:
        out["charts"] = chart_data(S, cfg, out["found"])
        for kind, rows in out["found"].items():
            for r in rows: r["daily"] = daily_geometry(r, S)
    return out


def previous_view(M):
    """The panels as they stood one session earlier: the same data with the newest session cut off."""
    P2 = dict(M)
    for k in ("C", "H", "L", "O", "DQ", "TQ", "dcode", "RAT"): P2[k] = M[k].iloc[:-1]
    P2["ma"] = {k: v.iloc[:-1] for k, v in M["ma"].items()}
    P2["nifty"] = M["nifty"].iloc[:-1]; P2["dates"] = M["dates"][:-1]; P2["N"] = M["N"] - 1; P2["T"] = M["T"] - 1
    return P2


def mark_changes(cur, prev):
    """event on each pattern found today: NEW when the stock had no such pattern at the previous session, BROKE when it had one that had not yet broken (or had broken the other way)
    and has broken now. Nothing is marked when there is no earlier scan to compare with. Returns the number of NEW and BROKE marks."""
    counts = dict(new=0, broke=0)
    if not prev: return counts
    for kind, rows in cur["found"].items():
        before = {r["sym"]: r["status"] for r in prev["found"][kind]}
        for r in rows:
            was = before.get(r["sym"])
            if was is None: r["event"] = "NEW"; counts["new"] += 1
            elif r["status"] in ("BREAKOUT", "BREAKDOWN") and was != r["status"]: r["event"] = "BROKE"; counts["broke"] += 1
    return counts


def direction(kind, status):
    """+1 for a pattern that points up, -1 for one that points down, 0 for a range with no lean yet."""
    if kind == "ascending": return 1
    if kind == "descending": return -1
    return 1 if status in ("BREAKOUT", "AT TOP") else -1 if status in ("BREAKDOWN", "AT BOTTOM") else 0


def conviction(r, other_tf_dirs):
    """0 to 5. A fresh break (2) or a setup within reach of the trigger (1); delivery at least 1.25x its 20-session average, on the break session for a break and on the latest session otherwise (1);
    the stock's 3-month return against Nifty leaning the pattern's way (1); the other timeframe showing a pattern with the same lean (1).
    A way of ordering today's list, not a probability."""
    d = direction(r["kind"], r["status"]); sc = 0
    sc += 2 if r["status"] in ("BREAKOUT", "BREAKDOWN") else 1 if r["status"] in ("SETUP", "AT TOP", "AT BOTTOM") else 0
    dv = r.get("brk_ratio") if r["status"] in ("BREAKOUT", "BREAKDOWN") and pd.notna(r.get("brk_ratio", np.nan)) else r["ratio"]      # a break is judged on the delivery of the break itself
    sc += 1 if pd.notna(dv) and dv >= CONFIRM else 0
    sc += 1 if d and pd.notna(r["rs3m"]) and (r["rs3m"] > 0) == (d > 0) and r["rs3m"] != 0 else 0
    sc += 1 if d and d in other_tf_dirs.get(r["sym"], set()) else 0
    return sc


def build(M):
    """{"daily": scan or None, "weekly": scan or None}. None for both when there is no history to speak of. Each pattern is marked NEW or BROKE against the previous session."""
    d, w = scan_timeframe(M, DAILY), scan_timeframe(M, WEEKLY)
    if not (d or w): return None
    prev = previous_view(M) if M["N"] > 130 else None
    for cur, cfg in ((d, DAILY), (w, WEEKLY)):
        if cur:
            before = scan_timeframe(prev, cfg, charts=False) if prev else None
            cur["compared"] = before is not None; cur["changes"] = mark_changes(cur, before)
    leans = {name: {} for name in ("daily", "weekly")}
    for name, cur in (("daily", d), ("weekly", w)):
        for rows in (cur["found"].values() if cur else []):
            for r in rows:
                if direction(r["kind"], r["status"]): leans[name].setdefault(r["sym"], set()).add(direction(r["kind"], r["status"]))
    order = {"BREAKOUT": 0, "BREAKDOWN": 0, "AT TOP": 1, "AT BOTTOM": 1, "SETUP": 1, "IN RANGE": 2, "FORMING": 2}
    for name, cur in (("daily", d), ("weekly", w)):
        for rows in (cur["found"].values() if cur else []):
            for r in rows: r["conv"] = conviction(r, leans["weekly" if name == "daily" else "daily"])
            rows.sort(key=lambda r: (order.get(r["status"], 3), not r.get("confirmed"), -r["conv"], -r["score"]))
    return {"daily": d, "weekly": w}


def _lines(kind, r, n):
    """The two lines of a pattern as ((bar, price), (bar, price), role), in bar coordinates."""
    i0, i1 = r["i0"], n - 1
    if kind == "rectangle": return [((i0, r["top"]), (i1, r["top"]), "resistance"), ((i0, r["bottom"]), (i1, r["bottom"]), "support")]
    sl = ((i0, r["slope"] * i0 + r["icpt"]), (i1, r["slope"] * i1 + r["icpt"]))
    if kind == "ascending": return [((i0, r["level"]), (i1, r["level"]), "resistance"), (sl[0], sl[1], "support")]
    return [((i0, r["level"]), (i1, r["level"]), "support"), (sl[0], sl[1], "resistance")]


def daily_geometry(r, S):
    """The pattern placed on the DAILY chart of the stock page: bar positions become session positions (a weekly bar spans its first to its last session)."""
    n = len(S["C"]); wh = S["where"]
    start = lambda b: wh[max(0, min(b, n - 1))][0]; end = lambda b: wh[max(0, min(b, n - 1))][1]
    lines = [dict(a=[int(start(a[0])), round(a[1], 2)], b=[int(end(b[0])), round(b[1], 2)], role=role) for a, b, role in _lines(r["kind"], r, n)]
    pts = [[int((start(i) + end(i)) // 2), round(p, 2)] for i, p in r["flat_pts"] + r["line_pts"]]
    brk = r.get("break_idx")
    return dict(lines=lines, touches=pts, target=round(r["target"], 2), brk=None if brk is None else int(start(brk)))


def chart_data(S, cfg, found, cap=40):
    """Per stock charted (the first `cap` of each kind): the bars, delivery and averages, plus each pattern's lines and touch points in chart coordinates."""
    n = len(S["C"]); w = min(cfg.chart, n); off = n - w; res = {}
    num = lambda ser, d=2: [None if pd.isna(v) else round(float(v), d) for v in ser.iloc[-w:]]
    for kind, rows in found.items():
        for r in rows[:cap]:
            s = r["sym"]
            if s not in res:
                res[s] = dict(dates=[f"{d:%d %b %y}" for d in S["ends"][-w:]], open=num(S["O"][s]), high=num(S["H"][s]), low=num(S["L"][s]), close=num(S["C"][s]),
                              dq=num(S["DQ"][s], 0), dqavg=num(S["avg"][s], 0), dc=num(S["dc"][s], 0), ma50=num(S["ma1"][s]), ma100=num(S["ma2"][s]), ma_labels=list(S["ma"]),
                              flags={}, zones={"support": [], "resistance": []}, patterns={})
            res[s]["patterns"][kind] = dict(lines=[dict(a=[round(a[0] - off), round(a[1], 2)], b=[round(b[0] - off), round(b[1], 2)], role=role) for a, b, role in _lines(kind, r, n)],
                                           touches=[[i - off, round(p, 2)] for i, p in r["flat_pts"] + r["line_pts"]], target=round(r["target"], 2))
    return res
