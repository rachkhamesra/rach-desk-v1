"""Range breakouts: a stricter rectangle, judged as a trade. Experimental, and kept apart from patterns.py so the existing pattern scans are untouched.

The idea (after a trader's description): trade the break of a horizontal boundary of a well-defined consolidation, with at least three touches on the boundary that breaks, pure price
action, and sound risk management: a small average loss against a large average win pays even with a win rate of 35-45%.

What makes a range well defined, beyond patterns.rectangle():
  * the boundary that breaks has at least three touches (the other side at least two), spaced a gap apart, and each touch is within a share of the range's own height of the level
    (patterns.py uses a fixed 2% of price, which is loose on a tight range and means little on a wide one);
  * the touches alternate between the two sides (top, bottom, top, bottom): price travelled across the range, it did not just sit against one edge;
  * the closes cross the middle of the range several times, and stay inside it;
  * no excursion beyond a boundary before the break (an earlier one means the level did not hold).
Each setup carries a trade plan: entry at the boundary, a stop at the middle of the range (or at its far side), the measured-move target, and the prior trend, so a break is read as
continuing the trend into the range or reversing it. range_replay.py replays every break as a trade (see simulate) and reports win rate, average win and loss in R, and expectancy.
"""
import json
import os

import numpy as np
import pandas as pd

import patterns as P

LOOSE = 0.035          # first pass: swing points within 3.5% of each other form a candidate boundary
TOUCH_FRAC = 0.12      # second pass: a touch is within this share of the range's height of the boundary
MIN_BREAK_TOUCHES = 3  # the boundary that breaks
MIN_OTHER_TOUCHES = 2  # the boundary that does not
MIN_SWITCHES = 3       # side changes in the touch sequence: top-bottom-top-bottom
MIN_CROSSINGS = 4      # closes crossing the middle of the range
INSIDE = 0.90          # share of closes inside the range (a little beyond either boundary allowed)
PRIOR_BARS = 60        # sessions before the range that define the prior trend
PRIOR_TREND = 0.10     # up or down by more than this over those sessions is a trend
MAX_TOUCH_GAP = {"daily": 70, "weekly": 14}      # bars between consecutive touches; a longer silence ends the range
TRAIL = {"daily": 20, "weekly": 8}               # trailing exit: a close under the lowest low (over the highest high) of this many bars
MAX_HOLD = {"daily": 120, "weekly": 26}
CHART_LEAD = {"daily": 25, "weekly": 8}          # bars drawn before the range starts
HERE = os.path.dirname(os.path.abspath(__file__))
SAVED = os.path.join(HERE, "config", "range_replay.json")


def _near(points, level, tol):
    return [p for p in points if abs(p[1] - level) <= tol]


def _alternations(tops, bottoms):
    """Side changes in the time-ordered touch sequence (T B T B is three)."""
    seq = [s for _, s in sorted([(i, "T") for i, _ in tops] + [(i, "B") for i, _ in bottoms])]
    runs = [s for k, s in enumerate(seq) if k == 0 or s != seq[k - 1]]
    return max(0, len(runs) - 1)


def _trim(tops, bottoms, max_gap):
    """Only the latest unbroken run of touches: a silence longer than max_gap bars before them is not part of this range."""
    allp = sorted([(i, "T", p) for i, p in tops] + [(i, "B", p) for i, p in bottoms])
    keep = [allp[-1]]
    for item in reversed(allp[:-1]):
        if keep[-1][0] - item[0] > max_gap: break
        keep.append(item)
    return [(i, p) for i, s, p in keep if s == "T"][::-1], [(i, p) for i, s, p in keep if s == "B"][::-1]


def find_range(H, L, C, cfg=P.DAILY):
    """The best well-defined range at the end of the arrays (oldest first), or None. Status: BREAKOUT / BREAKDOWN (a fresh close beyond a boundary with three touches),
    AT TOP / AT BOTTOM (near that boundary, not through it)."""
    n = len(C); tf = cfg.name
    if n < cfg.min_bars + 2 * cfg.k + 4: return None
    lo_bound = n - cfg.max_bars
    hi_pts = [p for p in P.swings(H, cfg.k, True) if p[0] >= lo_bound]; lo_pts = [p for p in P.swings(L, cfg.k, False) if p[0] >= lo_bound]
    if len(hi_pts) < 2 or len(lo_pts) < 2: return None
    tops_c = P.clusters(hi_pts, LOOSE, cfg.gap); bots_c = P.clusters(lo_pts, LOOSE, cfg.gap)
    best = None
    for t_level, _ in tops_c:
        for b_level, _ in bots_c:
            if b_level >= t_level: continue
            h = t_level - b_level; hp = h / b_level
            if not (P.RANGE_MIN <= hp <= P.RANGE_MAX): continue
            tol = TOUCH_FRAC * h
            tops = P.spaced(_near(hi_pts, t_level, tol), cfg.gap); bots = P.spaced(_near(lo_pts, b_level, tol), cfg.gap)
            if len(tops) < 2 or len(bots) < 2: continue
            tops, bots = _trim(tops, bots, MAX_TOUCH_GAP[tf])
            if len(tops) < MIN_OTHER_TOUCHES or len(bots) < MIN_OTHER_TOUCHES: continue
            top = float(np.median([p for _, p in tops])); bottom = float(np.median([p for _, p in bots]))
            if bottom >= top: continue
            height = top - bottom; mid = (top + bottom) / 2
            i0 = min(tops[0][0], bots[0][0])
            if not (cfg.min_bars <= n - i0 <= cfg.max_bars): continue
            sw = _alternations(tops, bots)
            if sw < MIN_SWITCHES: continue
            body = C[i0:n - cfg.recent]
            if len(body) < 10 or not np.isfinite(body).all(): continue
            if ((body >= bottom - 0.02 * height) & (body <= top + 0.02 * height)).mean() < INSIDE: continue
            crossings = int(np.count_nonzero(np.diff(np.sign(body - mid)) != 0))
            if crossings < MIN_CROSSINGS: continue
            if H[i0:n - cfg.recent].max() > top * (1 + P.PIERCE) or L[i0:n - cfg.recent].min() < bottom * (1 - P.PIERCE): continue          # an earlier excursion: the level did not hold
            up_at, dn_at = P.streak_start(C, top, True, n), P.streak_start(C, bottom, False, n)
            now = C[n - 1]
            if up_at is not None and up_at >= n - cfg.recent: status, brk, side = "BREAKOUT", int(up_at), 1
            elif dn_at is not None and dn_at >= n - cfg.recent: status, brk, side = "BREAKDOWN", int(dn_at), -1
            elif top * (1 - P.NEAR) <= now <= top * (1 + P.BREAK): status, brk, side = "AT TOP", None, 1
            elif bottom * (1 - P.BREAK) <= now <= bottom * (1 + P.NEAR): status, brk, side = "AT BOTTOM", None, -1
            else: continue
            if (side == 1 and len(tops) < MIN_BREAK_TOUCHES) or (side == -1 and len(bots) < MIN_BREAK_TOUCHES): continue
            score = len(tops) + len(bots) + sw + (n - i0) / 40
            if best is None or score > best["score"]:
                prior_ret = float(C[i0] / C[max(0, i0 - PRIOR_BARS)] - 1) if i0 >= 20 and np.isfinite(C[max(0, i0 - PRIOR_BARS)]) and C[max(0, i0 - PRIOR_BARS)] > 0 else float("nan")
                prior = "none" if not np.isfinite(prior_ret) else "up" if prior_ret >= PRIOR_TREND else "down" if prior_ret <= -PRIOR_TREND else "flat"
                cont = None if prior in ("none", "flat") else (prior == ("up" if side == 1 else "down"))
                level, opp = (top, bottom) if side == 1 else (bottom, top)
                best = dict(kind="range", status=status, side=side, break_idx=brk, top=top, bottom=bottom, mid=mid, level=level, opp=opp, height=height, height_pct=height / bottom * 100,
                            nt=len(tops), nb=len(bots), tops=tops, bottoms=bots, i0=i0, days=n - i0, switches=sw, crossings=crossings, prior=prior, prior_ret=prior_ret * 100 if np.isfinite(prior_ret) else float("nan"),
                            cont=cont, target=level + side * height, stop_mid=mid, stop_far=opp, score=score)
    return best


def simulate(O, H, L, C, i, side, stop, target=None, exit_mode="trail", trail_n=20, max_hold=120):
    """One trade, in R (the distance from entry to the stop). Entered at the open of bar i, the session after the signal. The stop fills at the stop, or at the open when the bar gaps through it,
    and is checked before a target within a bar (the cautious reading). exit_mode 'trail' leaves on a close beyond the trail_n-bar low (high for a short); 'target' sells at the measured move.
    A trade open at max_hold leaves at that close. None when the stop was already behind the entry."""
    n = len(C)
    if i >= n or not np.isfinite(O[i]): return None
    entry = O[i]; risk = (entry - stop) * side
    if not risk > 0: return None
    if exit_mode == "target" and (target is None or (target - entry) * side <= 0): return None
    last = min(n, i + max_hold) - 1
    for j in range(i, last + 1):
        lo, hi, op = L[j], H[j], O[j]
        if side > 0:
            if lo <= stop:
                ex = min(stop, op) if j > i else stop
                return (ex - entry) / risk
            if exit_mode == "target" and hi >= target:
                ex = max(target, op) if j > i else target
                return (ex - entry) / risk
        else:
            if hi >= stop:
                ex = max(stop, op) if j > i else stop
                return (entry - ex) / risk
            if exit_mode == "target" and lo <= target:
                ex = min(target, op) if j > i else target
                return (entry - ex) / risk
        if exit_mode == "trail" and j - trail_n >= 0:
            ref = np.nanmin(L[j - trail_n:j]) if side > 0 else np.nanmax(H[j - trail_n:j])
            if (side > 0 and C[j] < ref) or (side < 0 and C[j] > ref): return (C[j] - entry) * side / risk
    return (C[last] - entry) * side / risk


def stats(rs):
    """Win rate, average win and loss in R, expectancy, the share reaching 4R and the median, for a list of R multiples."""
    r = np.array([x for x in rs if x is not None and np.isfinite(x)], float)
    if len(r) == 0: return dict(n=0)
    w, l = r[r > 0], r[r <= 0]
    return dict(n=int(len(r)), win=float(len(w) / len(r) * 100), avg_win=float(w.mean()) if len(w) else None, avg_loss=float(l.mean()) if len(l) else None,
                exp=float(r.mean()), p4=float((r >= 4).mean() * 100), median=float(np.median(r)))


def build(M):
    """The ranges standing at the latest session, on daily and weekly bars, for the liquid stocks: {tf: {asof, found, scanned}}. None when there is too little history."""
    out = {}
    fo = set(M["memberships"].get("fo", []))
    for cfg in (P.DAILY, P.WEEKLY):
        S = P.series(M, cfg); n = len(S["C"])
        if M["N"] < 120 or n < cfg.min_bars + cfg.k * 2 + 10: continue
        syms = list(S["C"].columns); Cd = M["C"][syms]
        turn = (Cd * M["TQ"][syms]).iloc[-60:].median() / 1e7
        found, scanned = [], 0
        for s in syms:
            if not turn.get(s, 0) >= P.MIN_TURNOVER_CR or S["C"][s].iloc[-max(8, cfg.min_bars // 4):].isna().sum() > 1: continue
            scanned += 1
            Cs = S["C"][s].ffill().to_numpy(float)
            r = find_range(S["H"][s].to_numpy(float), S["L"][s].to_numpy(float), Cs, cfg)
            if not r: continue
            o, h, l = S["O"][s].to_numpy(float), S["H"][s].to_numpy(float), S["L"][s].to_numpy(float)
            lo = max(0, r["i0"] - CHART_LEAD[cfg.name])
            trail_n = TRAIL[cfg.name]
            trail = float(np.nanmin(l[n - trail_n:n]) if r["side"] > 0 else np.nanmax(h[n - trail_n:n]))
            r.update(sym=s, fo=s in fo, tf=cfg.name, close=float(Cs[-1]), px1d=float((Cs[-1] / Cs[-2] - 1) * 100) if n > 1 else float("nan"), turnover=float(turn[s]),
                     ext_r=float((Cs[-1] - r["level"]) * r["side"] / abs(r["level"] - r["stop_mid"])), trail=trail,
                     chart=dict(lo=lo, dates=[f"{d:%d %b %y}" for d in S["ends"][lo:]], o=[None if pd.isna(x) else round(float(x), 2) for x in o[lo:]], h=[None if pd.isna(x) else round(float(x), 2) for x in h[lo:]],
                                l=[None if pd.isna(x) else round(float(x), 2) for x in l[lo:]], c=[None if pd.isna(x) else round(float(x), 2) for x in Cs[lo:]]))
            found.append(r)
        order = {"BREAKOUT": 0, "BREAKDOWN": 0, "AT TOP": 1, "AT BOTTOM": 1}
        found.sort(key=lambda r: (order.get(r["status"], 2), -r["score"]))
        out[cfg.name] = dict(asof=M["dates"][M["T"]], found=found, scanned=scanned, cfg=cfg)
    return out or None


def load_replay(path=SAVED):
    try:
        with open(path) as f: return json.load(f)
    except (OSError, ValueError):
        return None
