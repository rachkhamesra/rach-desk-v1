"""Replay of the pattern scans over the sessions the desk holds. Run locally, not in the daily build:  python pattern_replay.py

For every fifth session (every week for the weekly scan) from deep enough into the history that the rules have something to see, the same detectors that
run on the page are run on the data up to that session only. Each fresh BREAKOUT or BREAKDOWN, counted once, is recorded at the moment it would have been
visible; then the stock's move against Nifty over the next 10 and 20 sessions is measured. Writes config/pattern_replay.json, which the Technical Patterns tab shows.

What it can and cannot say: about two years of history gives a few dozen to a few hundred events per pattern, overlapping in time and in one market
regime, with no costs. It is a sanity check on whether breaks followed through, not a back-test of a strategy.
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
import patterns as P

HORIZONS = (10, 20)
STEP = 5                       # sessions between daily scans
CONFIRM = 1.25                 # delivery at least this multiple of its 20-session average counts as confirmation
START = {"daily": 120, "weekly": 45}      # first bar scanned: before this there is too little history for the rules to see a pattern
SAVED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "pattern_replay.json")


def _worker(a):
    """All fresh breaks of one stock over every scan time. a = (sym, H, L, C, rat, where, cfg name, scan times)."""
    sym, H, L, C, rat, where, name, times = a
    cfg = P.DAILY if name == "daily" else P.WEEKLY
    out, seen = [], set()
    for t in times:
        n = t + 1
        for kind, r in P.scan(H[:n], L[:n], C[:n], cfg).items():
            if not r or r["status"] not in ("BREAKOUT", "BREAKDOWN"): continue
            key = (kind, r["status"], r["break_idx"])
            if key in seen: continue
            seen.add(key)
            day = t if where is None else where[t][1]
            out.append(dict(sym=sym, kind=kind, status=r["status"], tf=name, t_day=int(day), ratio=None if not np.isfinite(rat[day]) else float(rat[day])))
    return out


def events(M, name, workers=4, log=print):
    """Every fresh break the scan would have shown, for one timeframe."""
    cfg = P.DAILY if name == "daily" else P.WEEKLY
    S = P.series(M, cfg); n = len(S["C"]); syms = list(S["C"].columns)
    turn = ((M["C"][syms] * M["TQ"][syms]) / 1e7).rolling(60, min_periods=30).median()
    last = n - 1 - (HORIZONS[-1] if name == "daily" else 4)                              # leave room to see what happened next
    times = list(range(START[name], last + 1, STEP if name == "daily" else 1))
    where = None if name == "daily" else S["where"]
    jobs = []
    for s in syms:
        if not (turn[s].iloc[-1] >= P.MIN_TURNOVER_CR): continue                           # the same liquidity bar as the page, judged on the latest sessions
        ts = [t for t in times if np.isfinite(S["C"][s].iloc[t])]
        jobs.append((s, S["H"][s].to_numpy(float), S["L"][s].to_numpy(float), S["C"][s].ffill().to_numpy(float), M["RAT"][s].to_numpy(float), where, name, ts))
    log(f"{name}: {len(jobs)} stocks x {len(times)} scan times")
    t0 = time.time(); out = []
    if workers > 1:
        with ProcessPoolExecutor(workers) as ex:
            for part in ex.map(_worker, jobs, chunksize=6): out += part
    else:
        for j in jobs: out += _worker(j)
    log(f"{name}: {len(out)} fresh breaks found in {time.time() - t0:.0f}s")
    return out


def forward(M, ev):
    """Excess return over Nifty after each event, for every horizon the data allows (None otherwise)."""
    C = M["C"]; nf = M["nifty"].reindex(C.index).ffill(); rows = []
    for e in ev:
        c = C[e["sym"]].ffill().to_numpy(float); t = e["t_day"]; row = dict(e)
        for h in HORIZONS:
            row[f"x{h}"] = None if t + h >= len(c) or not np.isfinite(c[t]) or not np.isfinite(c[t + h]) else float(((c[t + h] / c[t]) - (nf.iloc[t + h] / nf.iloc[t])) * 100)
        rows.append(row)
    return rows


def baseline(M, step=STEP, start=START["daily"]):
    """What the average liquid stock did against Nifty over the same horizons, sampled the same way: the bar a pattern has to beat."""
    C = M["C"].ffill(); nf = M["nifty"].reindex(C.index).ffill(); out = {}
    turn = ((M["C"] * M["TQ"]) / 1e7).rolling(60, min_periods=30).median()
    for h in HORIZONS:
        vals = []
        for t in range(start, len(C) - 1 - h, step):
            ok = turn.iloc[t] >= P.MIN_TURNOVER_CR
            r = ((C.iloc[t + h] / C.iloc[t]) - (nf.iloc[t + h] / nf.iloc[t])) * 100
            vals += list(r[ok].dropna().to_numpy())
        v = np.array(vals); out[str(h)] = dict(n=int(len(v)), avg=float(v.mean()), up=float((v > 0).mean() * 100)) if len(v) else None
    return out


def summarise(rows):
    """{'tf|kind|status': {...}}: counts, average excess return, and the share that went the right way, with and without delivery confirmation."""
    groups = {}
    for r in rows: groups.setdefault(f'{r["tf"]}|{r["kind"]}|{r["status"]}', []).append(r)
    out = {}
    for key, rs in groups.items():
        up = key.endswith("BREAKOUT"); d = dict(found=len(rs))
        for h in HORIZONS:
            v = np.array([r[f"x{h}"] for r in rs if r[f"x{h}"] is not None])
            c = np.array([r[f"x{h}"] for r in rs if r[f"x{h}"] is not None and (r["ratio"] or 0) >= CONFIRM])
            right = (lambda a: float(((a > 0) if up else (a < 0)).mean() * 100) if len(a) else None)
            d[str(h)] = dict(n=int(len(v)), avg=float(v.mean()) if len(v) else None, right=right(v), n_conf=int(len(c)), avg_conf=float(c.mean()) if len(c) else None, right_conf=right(c))
        out[key] = d
    return out


def run(M, workers=4, log=print):
    rows = []
    for name in ("daily", "weekly"):
        if name == "weekly" and len(P.series(M, P.WEEKLY)["C"]) < START["weekly"] + 8: continue
        rows += forward(M, events(M, name, workers, log))
    return dict(generated=f"{pd.Timestamp.now():%Y-%m-%d}", sessions=int(M["N"]), asof=f"{M['dates'][M['T']]:%Y-%m-%d}", horizons=list(HORIZONS), step=STEP,
                baseline=baseline(M), groups=summarise(rows), total=len(rows))


def load_saved(path=SAVED):
    try:
        with open(path) as f: return json.load(f)
    except (OSError, ValueError):
        return None


def build_panels(root="data"):
    """The same panels the site is built from (see run.py), without the page."""
    import glob
    import corp_feed, metrics, nse, universes
    days = sorted(pd.Timestamp(os.path.basename(f)[:8]) for f in glob.glob(os.path.join(root, "raw", "cm", "*.zip")))
    parsed = nse.parse_all(root, days)
    here = os.path.dirname(os.path.abspath(__file__))
    ov = pd.read_csv(os.path.join(here, "corp_actions.csv")) if os.path.exists(os.path.join(here, "corp_actions.csv")) else None
    feed = corp_feed.load(root, min(parsed), max(parsed))
    ov = pd.concat([feed, ov], ignore_index=True) if len(feed) else ov
    mem = universes.load(root); mem.pop("market_cap_cr", None)
    return metrics.build(parsed, ov, mem)


def main(root="data"):
    M = build_panels(root)
    out = run(M)
    os.makedirs(os.path.dirname(SAVED), exist_ok=True)
    with open(SAVED, "w") as f: json.dump(out, f, indent=1)
    print("wrote", SAVED)


if __name__ == "__main__":
    main(*sys.argv[1:])
