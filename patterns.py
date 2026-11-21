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
import numpy as np
import pandas as pd

K = 4                 # a swing point beats the k sessions either side
TOL = 0.02            # swing highs (lows) within 2% of each other touch the same level
RECT_TOL = 0.02       # both of a rectangle's levels have to hold
MIN_GAP = 12          # sessions between the first and last touch of a flat level
MIN_DAYS, MAX_DAYS = 35, 270
CONVERGE = 0.80       # a triangle's gap now is at most this share of its starting gap
HEIGHT_MIN, HEIGHT_MAX = 0.06, 0.50   # a triangle starts between 6% and 50% of price tall; a rectangle is between RANGE_MIN and RANGE_MAX
RANGE_MIN, RANGE_MAX = 0.07, 0.40
RECENT = 10           # a break is fresh for this many sessions (the same window the Short Ideas charts highlight)
FORMING_MAX = 0.10    # a standing pattern whose price is further than 10% from the trigger level is not listed
NEAR = 0.04
BREAK = 0.01          # a close 1% beyond the level counts as through it
PIERCE = 0.03         # an earlier excursion this far beyond the level before the last RECENT sessions invalidates the pattern
MIN_TURNOVER_CR = 2.0 # median daily rupee turnover, so thin circuit-bound names do not fill the lists
CHART_DAYS = 230
KINDS = [("ascending", "ASCENDING TRIANGLE", "bullish"), ("descending", "DESCENDING TRIANGLE", "bearish"), ("rectangle", "RECTANGLE", "range")]


def swings(x, k=K, high=True):
    """[(index, price)] of confirmed swing highs (or lows). The newest k sessions cannot be confirmed yet."""
    out = []
    for i in range(k, len(x) - k):
        v = x[i]
        if np.isnan(v): continue
        left, right = x[i - k:i], x[i + 1:i + k + 1]
        if np.isnan(left).any() or np.isnan(right).any(): continue
        if high and v > left.max() and v >= right.max(): out.append((i, float(v)))
        if not high and v < left.min() and v <= right.min(): out.append((i, float(v)))
    return out


def clusters(points, tol=TOL, min_gap=MIN_GAP):
    """Every group of swing points within tol of a seed point and spanning at least min_gap sessions: [(level, members)], widest first."""
    out, seen = [], set()
    for _, p0 in points:
        mem = tuple(m for m in points if abs(m[1] / p0 - 1) <= tol)
        if len(mem) < 2 or mem in seen or mem[-1][0] - mem[0][0] < min_gap: continue
        seen.add(mem); out.append((float(np.median([p for _, p in mem])), list(mem)))
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


def _status(C, level, up, n):
    """BREAKOUT/BREAKDOWN if the first close beyond the level came within the last RECENT sessions and it still holds; SETUP when near; else FORMING."""
    now = C[n - 1]; begun = streak_start(C, level, up, n)
    if begun is not None and begun >= n - RECENT: return "BREAKOUT" if up else "BREAKDOWN", int(begun)
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


def triangle(H, L, C, up):
    """Ascending (up=True: flat top, rising lows) or descending (flat bottom, falling highs). Returns the best match or None."""
    n = len(C)
    flat_pts = swings(H if up else L, high=up); slope_pts = swings(L if up else H, high=not up)
    best = None
    for level, mem in clusters(flat_pts):
        run = [(i, p) for i, p in chain([q for q in slope_pts if q[0] >= mem[0][0] - 5], up) if ((p < level * .97) if up else (p > level * 1.03))]
        if len(run) < 3: continue                                                              # three points on the sloped side, so it is a line and not just two dots
        i_s = run[0][0]; touches = mem
        if mem[-1][0] < i_s - 10 or not (MIN_DAYS <= n - i_s <= MAX_DAYS): continue            # the flat level must be tested again once the sloped side has started
        seg = H[i_s:n - RECENT] if up else L[i_s:n - RECENT]
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
        status, brk = _status(C, level, up, n)
        if status is None: continue
        score = len(touches) + len(run) + (n - i_s) / 40
        if best is None or score > best["score"]:
            best = dict(kind="ascending" if up else "descending", status=status, break_idx=brk, level=level, i0=i_s, days=n - i_s, slope=slope, icpt=icpt,
                        touches_flat=len(touches), touches_line=len(run), flat_pts=touches, line_pts=run, height=g0, height_pct=g0 / level * 100,
                        target=level + g0 if up else level - g0, score=score)
    return best


def rectangle(H, L, C):
    n = len(C); best = None
    for r_level, r_mem in clusters(swings(H, high=True), RECT_TOL):
        for s_level, s_mem in clusters(swings(L, high=False), RECT_TOL):
            if s_level >= r_level: continue
            i0 = min(r_mem[0][0], s_mem[0][0])
            if not (MIN_DAYS <= n - i0 <= MAX_DAYS): continue
            h = r_level - s_level; hp = h / s_level
            if not (RANGE_MIN <= hp <= RANGE_MAX): continue
            if H[i0:n - RECENT].max() > r_level * (1 + PIERCE) or L[i0:n - RECENT].min() < s_level * (1 - PIERCE): continue
            body = C[i0:n - RECENT]
            if len(body) < 10 or ((body >= s_level * .98) & (body <= r_level * 1.02)).mean() < .90: continue
            if abs(C[i0:i0 + 10].mean() - C[-10:].mean()) > 0.5 * h: continue                       # a drifting channel is not a range: the average close must not have moved more than half the range
            touches = len(r_mem) + len(s_mem)
            if len(r_mem) < 3 or len(s_mem) < 3 or touches < 7: continue
            now = C[n - 1]
            up_at, dn_at = streak_start(C, r_level, True, n), streak_start(C, s_level, False, n)
            if up_at is not None and up_at >= n - RECENT: status, brk, up = "BREAKOUT", int(up_at), True
            elif dn_at is not None and dn_at >= n - RECENT: status, brk, up = "BREAKDOWN", int(dn_at), False
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


def scan(H, L, C):
    """All three detectors on one stock's arrays (oldest first). {kind: result or None}"""
    return {"ascending": triangle(H, L, C, True), "descending": triangle(H, L, C, False), "rectangle": rectangle(H, L, C)}


def build(M):
    """Scans every liquid stock in the universe. None when there is too little history."""
    if M["N"] < 120: return None
    syms = list(M["syms"]); C, H, L, O = M["C"][syms], M["H"][syms], M["L"][syms], M["O"][syms]
    turn = (C * M["TQ"][syms]).iloc[-60:].median() / 1e7                                  # rupees traded per day, in crore
    fo = set(M["memberships"].get("fo", [])); n = len(C)
    out = {"asof": M["dates"][M["T"]], "found": {k: [] for k, _, _ in KINDS}, "charts": {}, "scanned": 0}
    nifty = M["nifty"].reindex(C.index).ffill()
    for s in syms:
        if not turn.get(s, 0) >= MIN_TURNOVER_CR or C[s].iloc[-120:].isna().sum() > 5: continue
        out["scanned"] += 1
        res = scan(H[s].to_numpy(float), L[s].to_numpy(float), C[s].ffill().to_numpy(float))
        for kind, r in res.items():
            if not r: continue
            c = C[s]; r.update(sym=s, close=float(c.iloc[-1]), px1d=float((c.iloc[-1] / c.iloc[-2] - 1) * 100), fo=s in fo,
                               rs3m=float(((c.iloc[-1] / c.iloc[-64]) / (nifty.iloc[-1] / nifty.iloc[-64]) - 1) * 100) if n > 64 else np.nan,
                               ratio=float(M["RAT"][s].iloc[-1]) if pd.notna(M["RAT"][s].iloc[-1]) else np.nan, turnover=float(turn[s]))
            out["found"][kind].append(r)
    order = {"BREAKOUT": 0, "BREAKDOWN": 0, "AT TOP": 1, "AT BOTTOM": 1, "SETUP": 1, "IN RANGE": 2, "FORMING": 2}
    for kind in out["found"]:
        out["found"][kind].sort(key=lambda r: (order.get(r["status"], 3), -r["score"]))
    out["charts"] = chart_data(M, out["found"])
    return out


def chart_data(M, found, cap=40):
    """Per stock charted (the first `cap` of each kind): sessions of candles and delivery, plus each pattern's lines and touch points in chart coordinates."""
    n = len(M["C"]); w = min(CHART_DAYS, n); off = n - w; res = {}
    for kind, rows in found.items():
        for r in rows[:cap]:
            s = r["sym"]
            if s not in res:
                dq = M["DQ"][s]; avg = dq.shift(1).rolling(20, min_periods=15).mean()
                num = lambda ser, d=2: [None if pd.isna(v) else round(float(v), d) for v in ser.iloc[-w:]]
                res[s] = dict(dates=[f"{d:%d %b %y}" for d in M["C"].index[-w:]], open=num(M["O"][s]), high=num(M["H"][s]), low=num(M["L"][s]), close=num(M["C"][s]),
                              dq=num(dq, 0), dqavg=num(avg, 0), dc=num(M["dcode"][s], 0), ma50=num(M["ma"][50][s]), ma100=num(M["ma"][100][s]), flags={}, zones={"support": [], "resistance": []}, patterns={})
            i0, i1 = r["i0"] - off, n - 1 - off
            if kind == "rectangle":
                lines = [dict(a=[i0, r["top"]], b=[i1, r["top"]], role="resistance"), dict(a=[i0, r["bottom"]], b=[i1, r["bottom"]], role="support")]
            elif kind == "ascending":
                lines = [dict(a=[i0, r["level"]], b=[i1, r["level"]], role="resistance"), dict(a=[i0, r["slope"] * r["i0"] + r["icpt"]], b=[i1, r["slope"] * (n - 1) + r["icpt"]], role="support")]
            else:
                lines = [dict(a=[i0, r["level"]], b=[i1, r["level"]], role="support"), dict(a=[i0, r["slope"] * r["i0"] + r["icpt"]], b=[i1, r["slope"] * (n - 1) + r["icpt"]], role="resistance")]
            res[s]["patterns"][kind] = dict(lines=[dict(a=[round(l["a"][0]), round(l["a"][1], 2)], b=[round(l["b"][0]), round(l["b"][1], 2)], role=l["role"]) for l in lines],
                                           touches=[[i - off, round(p, 2)] for i, p in r["flat_pts"] + r["line_pts"]], target=round(r["target"], 2))
    return res
