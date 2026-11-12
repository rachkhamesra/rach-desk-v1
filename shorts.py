"""Very experimental: F&O stocks where price action points to a potential short.

Six screens, all on the existing panels (adjusted closes, delivery, SSF open interest, Nifty). Each is a yes/no flag per stock per
session, so the same rule can be replayed over the sessions the desk holds to see what usually happened next. The replay is a
sanity check, not a backtest: a few hundred sessions, overlapping windows, no costs, and one market regime.
"""
import numpy as np
import pandas as pd

HOLD = 10             # sessions looked at after a flag in the replay
MIN_REPLAY = 15       # fewer independent flags than this and the replay is not shown
LOOKBACK_LOW = 40     # sessions for the breakdown screen's prior low

SCREENS = [
    ("cash_selling", "CASH SELLING", "Closes down, below the 50 and 100-day averages, with delivered shares above the prior 20-session average. Holders are handing stock over on a falling price: the mirror of the Cash Accumulation Watch."),
    ("laggards", "LAGGARDS", "Behind Nifty by 5 points or more over 20 days and by 10 or more over 3 months, and below the 50-day average. Persistent relative underperformance."),
    ("breakdown", "BREAKDOWN", "Closes below its lowest close of the prior 40 sessions on delivery above its 20-session average: support gave way with real selling behind it."),
    ("rejection", "REJECTED AT 50MA", "Traded up to or through the 50-day average today but closed back under it, down on the day, after closing under it yesterday. A failed attempt to reclaim the trend."),
    ("buildup", "SHORT BUILD-UP", "Down 3% or more over three sessions while single-stock-futures open interest rose 5% or more: new short positions are going on into the fall."),
    ("near_lows", "NEAR 52-WEEK LOW", "Within 4% of the lowest close of the past year (or all history held) and still behind Nifty over 20 days. A weak stock with no floor yet."),
]


def _rel(C, nifty, h):
    n = nifty.reindex(C.index).ffill()
    return (C / C.shift(h)).div(n / n.shift(h), axis=0).sub(1) * 100


def flags(M, syms):
    """{screen key: boolean DataFrame (sessions x syms)} plus the supporting panels used by the page."""
    C, H, O, RAT, oi = M["C"][syms], M["H"][syms], M["O"][syms], M["RAT"][syms], M["OIadj"][syms]
    nifty = M["nifty"]; ret1 = C.pct_change(fill_method=None) * 100
    ma50 = M["ma"][50][syms]; ma100 = M["ma"][100][syms]
    rel20, rel63 = _rel(C, nifty, 20), _rel(C, nifty, 63)
    ok = lambda df: df.fillna(False)
    f = {}
    below = (C < ma50) & (C < ma100)
    f["cash_selling"] = ok((ret1 < 0) & (RAT > 1) & below)
    f["laggards"] = ok((rel20 <= -5) & (rel63 <= -10) & (C < ma50))
    f["breakdown"] = ok((C < C.shift(1).rolling(LOOKBACK_LOW, min_periods=LOOKBACK_LOW).min()) & (RAT > 1))
    f["rejection"] = ok((H >= ma50) & (C < ma50) & (C.shift(1) < ma50.shift(1)) & (ret1 < 0))
    chg3 = (C / C.shift(3) - 1) * 100; oi3 = (oi / oi.shift(3) - 1) * 100
    f["buildup"] = ok((chg3 <= -3) & (oi3 >= 5))
    low = C.rolling(252, min_periods=120).min()
    f["near_lows"] = ok((C <= low * 1.04) & (rel20 < 0))
    extra = dict(ret1=ret1, chg3=chg3, oi3=oi3, rel20=rel20, rel63=rel63, ma50=ma50, low=low)
    return f, extra


def _streak(col):
    n = 0
    for v in col.to_numpy()[::-1]:
        if not v: break
        n += 1
    return n


def replay(flag, C, nifty, hold=HOLD):
    """What happened over the next `hold` sessions after a flag, against Nifty, counting a stock once per hold window. Returns None when there are too few."""
    n = nifty.reindex(C.index).ffill()
    fwd = (C.shift(-hold) / C - 1).sub(n.shift(-hold) / n - 1, axis=0)
    vals = []
    F, V = flag.to_numpy(), fwd.to_numpy()
    for j in range(F.shape[1]):
        i = 0
        while i < F.shape[0]:
            if F[i, j] and not np.isnan(V[i, j]): vals.append(V[i, j]); i += hold
            else: i += 1
    if len(vals) < MIN_REPLAY: return dict(n=len(vals), avg=None, hit=None)
    v = np.array(vals) * 100
    return dict(n=len(v), avg=float(v.mean()), hit=float((v < 0).mean() * 100))


def baseline(C, nifty, hold=HOLD):
    n = nifty.reindex(C.index).ffill()
    fwd = (C.shift(-hold) / C - 1).sub(n.shift(-hold) / n - 1, axis=0).iloc[::hold]
    v = fwd.to_numpy().ravel(); v = v[~np.isnan(v)]
    return dict(n=int(len(v)), avg=float(v.mean() * 100), hit=float((v < 0).mean() * 100)) if len(v) else None


def build(M):
    """{asof, screens: {key: dict(title, desc, rows DataFrame, replay)}, confluence DataFrame, baseline}. None if there is no F&O universe or too little history."""
    fo = [s for s in M["memberships"].get("fo", []) if s in M["C"].columns]
    if not fo or M["N"] < 70: return None
    f, x = flags(M, fo); C = M["C"][fo]; T = M["T"]; nifty = M["nifty"]
    RAT = M["RAT"][fo]
    out = {"asof": M["dates"][T], "screens": {}, "baseline": baseline(C, nifty)}
    hits = {}
    for key, title, desc in SCREENS:
        fl = f[key]; syms = [s for s in fo if fl[s].iloc[-1]]
        rows = []
        for s in syms:
            rows.append(dict(sym=s, days=_streak(fl[s]), close=float(C[s].iloc[-1]), px1d=float(x["ret1"][s].iloc[-1]), px3d=float(x["chg3"][s].iloc[-1]), rel20=float(x["rel20"][s].iloc[-1]), rel63=float(x["rel63"][s].iloc[-1]),
                             ma50=float((C[s].iloc[-1] / x["ma50"][s].iloc[-1] - 1) * 100) if pd.notna(x["ma50"][s].iloc[-1]) else np.nan,
                             ratio=float(RAT[s].iloc[-1]) if pd.notna(RAT[s].iloc[-1]) else np.nan, oi3=float(x["oi3"][s].iloc[-1]) if pd.notna(x["oi3"][s].iloc[-1]) else np.nan,
                             new=bool(len(fl) > 1 and not fl[s].iloc[-2])))
            hits.setdefault(s, []).append(key)
        df = pd.DataFrame(rows, columns=["sym", "days", "close", "px1d", "px3d", "rel20", "rel63", "ma50", "ratio", "oi3", "new"])
        order = {"cash_selling": (["days", "ratio"], [False, False]), "laggards": (["rel63"], [True]), "breakdown": (["ratio"], [False]),
                 "rejection": (["px1d"], [True]), "buildup": (["oi3"], [False]), "near_lows": (["rel20"], [True])}[key]
        if len(df): df = df.sort_values(order[0], ascending=order[1]).reset_index(drop=True)
        out["screens"][key] = dict(title=title, desc=desc, rows=df, replay=replay(fl, C, nifty))
    conf = pd.DataFrame([dict(sym=s, count=len(k), screens=k) for s, k in hits.items()])
    if len(conf): conf = conf.sort_values(["count", "sym"], ascending=[False, True]).reset_index(drop=True)
    out["confluence"] = conf
    return out
