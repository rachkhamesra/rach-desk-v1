"""Replay of the range breakouts as trades, against the existing rectangle scan on the same data. Run locally, not in the daily build:  python range_replay.py

For every stock and every second session (every week for the weekly scan) from deep enough into the history that a range can have formed, both detectors are run on the data up to that
session only. Each fresh break, counted once, becomes a trade: entered at the open of the next session, stopped at the middle of the range or at its far side, and left either by a trailing
exit (a close beyond the trailing 20-session low or high, 8 weeks on the weekly scan) or at the measured-move target (see ranges.simulate). The results are in R, the distance from the entry to the
stop: win rate, average win and loss, expectancy, and the share of trades that reached 4R. Writes config/range_replay.json, which the Ranges sub-tab shows.

What it can and cannot say: about three years, one market regime, overlapping trades in the same stock, no costs or slippage beyond the next open. A sanity check on whether one rule set is better
than another, not a back-test of a strategy.
"""
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import pattern_replay as PR
import patterns as P
import ranges as R

STEP = {"daily": 2, "weekly": 1}
START = {"daily": 120, "weekly": 45}
VARIANTS = ("mid_trail", "far_trail", "mid_target", "far_target")


def _events(model, res, t, tf, O, H, L, C, seen, sym):
    """The trade (if any) a detection at bar t starts: one record with the R of each variant."""
    if not res or res["status"] not in ("BREAKOUT", "BREAKDOWN"): return None
    side = 1 if res["status"] == "BREAKOUT" else -1
    key = (model, side, res["break_idx"])
    if key in seen or t + 1 >= len(C): return None
    seen.add(key)
    top, bottom = res["top"], res["bottom"]; mid = (top + bottom) / 2
    level, far = (top, bottom) if side == 1 else (bottom, top)
    height = top - bottom; target = level + side * height
    tn, mh = R.TRAIL[tf], R.MAX_HOLD[tf]
    r = {}
    for stop_name, stop in (("mid", mid), ("far", far)):
        r[f"{stop_name}_trail"] = R.simulate(O, H, L, C, t + 1, side, stop, exit_mode="trail", trail_n=tn, max_hold=mh)
        r[f"{stop_name}_target"] = R.simulate(O, H, L, C, t + 1, side, stop, target=target, exit_mode="target", max_hold=mh)
    return dict(sym=sym, tf=tf, model=model, side=side, t=int(t), brk=int(res["break_idx"]), prior=res.get("prior"), cont=res.get("cont"), height_pct=float(height / bottom * 100), **r)


def _worker(a):
    sym, O, H, L, C, name, times = a
    cfg = P.DAILY if name == "daily" else P.WEEKLY
    out, seen = [], set()
    for t in times:
        n = t + 1; h, l, c = H[:n], L[:n], C[:n]
        new = R.find_range(h, l, c, cfg)
        e = _events("new", new, t, name, O, H, L, C, seen, sym)
        if e: out.append(e)
        old = P.rectangle(h, l, c, cfg)
        e = _events("old", old, t, name, O, H, L, C, seen, sym)
        if e: out.append(e)
    return out


def events(M, name, workers=6, log=print):
    cfg = P.DAILY if name == "daily" else P.WEEKLY
    S = P.series(M, cfg); n = len(S["C"]); syms = list(S["C"].columns)
    turn = ((M["C"][syms] * M["TQ"][syms]) / 1e7).rolling(60, min_periods=30).median()
    last = n - 2
    times = list(range(START[name], last + 1, STEP[name]))
    jobs = []
    for s in syms:
        if not (turn[s].iloc[-1] >= P.MIN_TURNOVER_CR): continue
        ts = [t for t in times if np.isfinite(S["C"][s].iloc[t])]
        jobs.append((s, S["O"][s].to_numpy(float), S["H"][s].to_numpy(float), S["L"][s].to_numpy(float), S["C"][s].ffill().to_numpy(float), name, ts))
    log(f"{name}: {len(jobs)} stocks x {len(times)} scan times")
    t0 = time.time(); out = []
    with ProcessPoolExecutor(workers) as ex:
        for part in ex.map(_worker, jobs, chunksize=4): out += part
    log(f"{name}: {len(out)} fresh breaks found in {time.time() - t0:.0f}s")
    return out


def summarise(rows):
    """{'tf|model|side': {found, variants: {name: stats}}} and, for the new rules, the same split by whether the break continues the prior trend."""
    df = pd.DataFrame(rows); out = {}
    if df.empty: return out
    for (tf, model, side), g in df.groupby(["tf", "model", "side"]):
        key = f"{tf}|{model}|{'up' if side == 1 else 'down'}"
        out[key] = dict(found=int(len(g)), median_height_pct=float(g["height_pct"].median()), variants={v: R.stats(g[v].tolist()) for v in VARIANTS})
        if model == "new":
            for label, mask in (("continuation", g["cont"] == True), ("reversal", g["cont"] == False)):    # noqa: E712
                gg = g[mask]
                if len(gg): out[key + "|" + label] = dict(found=int(len(gg)), variants={v: R.stats(gg[v].tolist()) for v in VARIANTS})
    return out


def run(M, workers=6, log=print):
    rows = []
    for name in ("daily", "weekly"):
        if name == "weekly" and len(P.series(M, P.WEEKLY)["C"]) < START["weekly"] + 8: continue
        rows += events(M, name, workers, log)
    return dict(generated=f"{pd.Timestamp.now():%Y-%m-%d}", sessions=int(M["N"]), asof=f"{M['dates'][M['T']]:%Y-%m-%d}", trail=R.TRAIL, step=STEP, total=len(rows), groups=summarise(rows))


def main(root="data"):
    M = PR.build_panels(root)
    out = run(M, workers=max(2, (os.cpu_count() or 4) - 1))
    os.makedirs(os.path.dirname(R.SAVED), exist_ok=True)
    with open(R.SAVED, "w") as f: json.dump(out, f, indent=1)
    print("wrote", R.SAVED)


if __name__ == "__main__":
    main(*sys.argv[1:])
