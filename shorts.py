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
    extra = dict(ret1=ret1, chg3=chg3, oi3=oi3, rel20=rel20, rel63=rel63, ma50=ma50, ma100=ma100, low=low)
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


CHART_DAYS = 90       # sessions of price drawn per chart
RECENT_DAYS = 10      # only flags from this many latest sessions are highlighted: older ones are not relevant to today's pick
PROFILE_DAYS = 250    # sessions of history used to find price congestion
PROFILE_BINS = 60
ZONE_HALF_WIDTH = 0.03   # a zone reaches at most 3% either side of its peak price
ZONE_GAP = 0.06          # two zones' peaks are at least 6% apart
MAX_ZONES = 2         # support and resistance zones kept on each side of the current price


def congestion_zones(H, L, DQ, close, days=PROFILE_DAYS, bins=PROFILE_BINS):
    """Where price has spent its time, weighted by delivered shares: each session spreads its delivered shares evenly over its high-low range.
    Peaks in that profile are congestion: prices where many shares changed hands, so holders are anchored there. Returns zones (lo, hi, weight share)
    below the close as support and above it as resistance, nearest first. A zone the close sits inside is reported as both."""
    h = pd.Series(H).iloc[-days:].to_numpy(float); l = pd.Series(L).iloc[-days:].to_numpy(float); w = pd.Series(DQ).iloc[-days:].to_numpy(float)
    ok = ~(np.isnan(h) | np.isnan(l)); h, l, w = h[ok], l[ok], w[ok]
    if len(h) < 40 or not np.isfinite(close): return {"support": [], "resistance": []}
    w = np.where(np.isnan(w) | (w <= 0), np.nanmedian(w[w > 0]) if (w > 0).any() else 1.0, w)
    lo, hi = float(l.min()), float(h.max())
    if hi <= lo: return {"support": [], "resistance": []}
    edges = np.linspace(lo, hi, bins + 1); prof = np.zeros(bins)
    for a_, b_, w_ in zip(l, h, w):
        i0 = min(bins - 1, int((a_ - lo) / (hi - lo) * bins)); i1 = min(bins - 1, int((b_ - lo) / (hi - lo) * bins))
        prof[i0:i1 + 1] += w_ / (i1 - i0 + 1)
    prof = np.convolve(prof, [.25, .5, .25], mode="same")
    peaks = [i for i in range(bins) if prof[i] >= prof[max(0, i - 1)] and prof[i] >= prof[min(bins - 1, i + 1)] and prof[i] >= 0.35 * prof.max()]
    peaks.sort(key=lambda i: -prof[i]); chosen = []
    for i in peaks:
        pi = (edges[i] + edges[i + 1]) / 2
        if all(abs(pi / ((edges[j] + edges[j + 1]) / 2) - 1) >= ZONE_GAP for j in chosen): chosen.append(i)
    zones = []
    for i in chosen:
        a_ = b_ = i
        pk = (edges[i] + edges[i + 1]) / 2
        while a_ > 0 and prof[a_ - 1] >= 0.75 * prof[i] and edges[a_ - 1] >= pk * (1 - ZONE_HALF_WIDTH): a_ -= 1
        while b_ < bins - 1 and prof[b_ + 1] >= 0.75 * prof[i] and edges[b_ + 2] <= pk * (1 + ZONE_HALF_WIDTH): b_ += 1
        zones.append(dict(lo=float(edges[a_]), hi=float(edges[b_ + 1]), share=float(prof[a_:b_ + 1].sum() / prof.sum() * 100)))
    sup = sorted([z for z in zones if z["hi"] <= close * 1.005], key=lambda z: -z["hi"])[:MAX_ZONES]
    res = sorted([z for z in zones if z["lo"] >= close * .995], key=lambda z: z["lo"])[:MAX_ZONES]
    inside = [z for z in zones if z["lo"] < close * .995 and z["hi"] > close * 1.005]          # price is sitting in congestion right now
    for z in inside: sup.append(z); res.append(z)
    return {"support": sup, "resistance": res}


def chart_data(f, M, fo, x, hits):
    """For every stock flagged today: the last CHART_DAYS sessions of open, high, low, close, delivered shares (and their 20-session average and the day's
    direction code, as on the Stocks screen), 50 and 100-day averages, the sessions among the latest RECENT_DAYS on which each screen's rule was true,
    and the congestion zones (support below, resistance above)."""
    C = M["C"][fo]; out = {}
    for s in hits:
        n = min(CHART_DAYS, len(C))
        num = lambda ser, d=2: [None if pd.isna(v) else round(float(v), d) for v in ser.iloc[-n:]]
        dq = M["DQ"][s]; avg = dq.shift(1).rolling(20, min_periods=15).mean()
        out[s] = dict(dates=[f"{d:%d %b %y}" for d in C.index[-n:]], open=num(M["O"][s]), high=num(M["H"][s]), low=num(M["L"][s]), close=num(C[s]),
                      dq=num(dq, 0), dqavg=num(avg, 0), dc=num(M["dcode"][s], 0), ma50=num(x["ma50"][s]), ma100=num(x["ma100"][s]),
                      flags={k: [int(i) for i in np.flatnonzero(f[k][s].to_numpy()[-n:]) if i >= n - RECENT_DAYS] for k in f},
                      zones=congestion_zones(M["H"][s], M["L"][s], dq, float(C[s].iloc[-1])))
    return out


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
    out["charts"] = chart_data(f, M, fo, x, hits)
    return out
