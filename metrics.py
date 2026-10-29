"""Everything the pages show, computed from adjusted panels."""
import numpy as np, pandas as pd
import corp, panel

MA_SET = (32, 50, 100, 200, 233, 377, 610)
HORIZONS = [("5 days", 5), ("20 days", 20), ("3 months", 63), ("6 months", 126), ("12 months", 252)]
SIGMA_WINDOW = 60       # sessions of daily returns used for the 0.5 sigma "at a moving average" rule
LIST_N = 30             # names per side in the relative-performance lists
CASH_MAS = (50, 100, 200)
CASH_MIN_DAYS = 2


def pctile(series, value):
    s = series.dropna()
    return float((s < value).mean() * 100) if len(s) > 20 and pd.notna(value) else np.nan


def episode_state(flags, cooldown=2):
    """Count qualifying days in an episode, retaining it through short pauses."""
    hits, misses, last_hit = 0, cooldown + 1, None
    for i, value in enumerate(flags):
        is_hit = pd.notna(value) and bool(value)
        if is_hit:
            hits = hits + 1 if hits and misses <= cooldown else 1
            misses, last_hit = 0, i
        elif hits:
            misses += 1
            if misses > cooldown: hits, last_hit = 0, None
    return dict(days=hits, cooldown=misses, last_hit=last_hit) if hits else None


def split_cash_signals(base, above):
    """Keep confirmed setups and below-MA tracking candidates mutually exclusive."""
    return base & above, base & ~above


def appeared_today(flags, cooldown=2, min_days=1):
    """True when an episode is on today's table but was absent yesterday."""
    values = list(flags)
    now, prev = episode_state(values, cooldown), episode_state(values[:-1], cooldown)
    return bool(now and now["days"] >= min_days and (not prev or prev["days"] < min_days))


def build(parsed, overrides=None, memberships=None):
    dates = sorted(parsed); memberships = memberships or {}
    fo_date = [d for d in dates if parsed[d]["fo"] is not None][-1]
    memberships["fo"] = list(parsed[fo_date]["fo"].index)
    requested = list(dict.fromkeys(memberships.get("top1000", []) + sum((memberships.get(k, []) for k in ("nifty500", "smallcap250", "nifty250", "nifty100", "fo")), [])))
    syms = panel.universe(parsed, requested); N = len(dates); T = N - 1
    W = lambda part, col: panel.wide(parsed, dates, syms, part, col)
    close_raw, high_raw, isin, lot = W("cm", "close"), W("cm", "high"), W("cm", "isin"), W("fo", "lot")
    nse_dq, nse_tq = W("deliv", "dq"), W("deliv", "tq")
    bse_dq = panel.wide(parsed, dates, syms, "bse", "dq").fillna(0); bse_vol = panel.wide(parsed, dates, syms, "bse", "vol").fillna(0)
    dq_raw, tq_raw = nse_dq + bse_dq, nse_tq + bse_vol                      # NSE + BSE, in shares, as on the reference page
    bse_share = (bse_dq / dq_raw * 100)
    oi, doi = W("fo", "oi"), W("fo", "doi")
    nifty = pd.Series({d: parsed[d]["nifty"] for d in dates}).astype(float).ffill()
    turn = W("deliv", "turn_cr")
    ev = corp.find_events(close_raw.ffill(limit=5), isin, lot, turn, overrides)
    F = corp.factors(pd.DatetimeIndex(dates), syms, ev)
    C = (close_raw * F).ffill(limit=5); H = high_raw * F; DQ = dq_raw / F; TQ = tq_raw / F
    allowed = set(syms)
    memberships = {k: [s for s in v if s in allowed] for k, v in memberships.items()}
    M = dict(bse_share=bse_share, dates=dates, syms=syms, memberships=memberships, N=N, T=T, events=ev, C=C, H=H, DQ=DQ, TQ=TQ, oi=oi, doi=doi, nifty=nifty, close_raw=close_raw, dq_raw=dq_raw, tq_raw=tq_raw)
    M["unresolved"] = set()

    ret1 = C.pct_change(fill_method=None); sig_prev = ret1.rolling(60, min_periods=30).std().shift(1)
    small = ret1.abs() < 0.5 * sig_prev
    M["ret1"] = ret1; M["zmove"] = ret1 / sig_prev; M["OIadj"] = oi / F
    M["dcode"] = pd.DataFrame(np.where(ret1.isna(), np.nan, np.where(small, 0.0, np.sign(ret1))), index=ret1.index, columns=ret1.columns)
    A20 = DQ.shift(1).rolling(20, min_periods=15).mean(); RAT = DQ / A20; M["RAT"] = RAT
    ret1 = C.pct_change(fill_method=None)

    # ---------------- fresh 52-week highs (intraday high versus prior 252 sessions)
    # Use adjusted exchange highs so splits/bonuses do not create false breakouts.
    prior_52w = H.shift(1).rolling(252, min_periods=252).max()
    fo_set = set(memberships.get("fo", [])); highs = []
    for s in memberships.get("top1000", syms):
        today, prior = H[s].iloc[T], prior_52w[s].iloc[T]
        if pd.isna(today) or pd.isna(prior) or today < prior * (1 - 1e-10): continue
        close = C[s].iloc[T]
        highs.append(dict(sym=s, fo=s in fo_set, day_high=today, prior_high=prior, close=close,
                          close_from_high=(close / today - 1) * 100 if pd.notna(close) and today else np.nan,
                          px1d=ret1[s].iloc[T] * 100, ratio=RAT[s].iloc[T]))
    M["high52"] = pd.DataFrame(highs, columns=["sym", "fo", "day_high", "prior_high", "close", "close_from_high", "px1d", "ratio"])

    # ---------------- 1-day screen
    rows = []
    for s in syms:
        r = RAT[s].iloc[T]
        if pd.isna(r) or pd.isna(DQ[s].iloc[T]): continue
        o, d_ = oi[s].iloc[T], doi[s].iloc[T]
        rows.append(dict(sym=s, dq=DQ[s].iloc[T], ratio=r, delivpct=dq_raw[s].iloc[T] / tq_raw[s].iloc[T] * 100, px1d=ret1[s].iloc[T] * 100,
                         oi=o, doi=d_, doi_pct=d_ / (o - d_) * 100 if pd.notna(o) and pd.notna(d_) and (o - d_) else np.nan,
                         d_over_doi=DQ[s].iloc[T] / d_ if pd.notna(d_) and d_ != 0 else np.nan, pct=pctile(DQ[s], DQ[s].iloc[T]),
                         value_cr=dq_raw[s].iloc[T] * close_raw[s].iloc[T] / 1e7))
    M["screen"] = pd.DataFrame(rows).sort_values("ratio", ascending=False).reset_index(drop=True)

    # ---------------- persistent delivery (last 5 sessions)
    ret5 = C.pct_change(5, fill_method=None)
    sig5 = ret5.rolling(SIGMA_WINDOW, min_periods=30).std().shift(1)
    rows = []
    for s in syms:
        r5 = RAT[s].iloc[T - 4:T + 1]
        if r5.isna().any(): continue
        d125, d150 = int((r5 >= 1.25).sum()), int((r5 >= 1.5).sum())
        base = DQ[s].iloc[T - 24:T - 4].mean(); avg5 = DQ[s].iloc[T - 4:T + 1].mean()
        o, o0 = oi[s].iloc[T], oi[s].iloc[T - 5]
        d5 = doi[s].iloc[T - 4:T + 1].sum(min_count=5)
        hist5 = DQ[s].rolling(5).mean()
        rows.append(dict(sym=s, d125=d125, d150=d150, ratio=avg5 / base if base else np.nan, dq5=DQ[s].iloc[T - 4:T + 1].sum(),
                         delivpct=dq_raw[s].iloc[T - 4:T + 1].sum() / tq_raw[s].iloc[T - 4:T + 1].sum() * 100, px5=ret5[s].iloc[T] * 100,
                         px5_z=ret5[s].iloc[T] / sig5[s].iloc[T] if pd.notna(sig5[s].iloc[T]) and sig5[s].iloc[T] else np.nan,
                         oi=o, doi5=d5, doi_pct=d5 / o0 * 100 if pd.notna(o0) and o0 and pd.notna(d5) else np.nan,
                         d_over_doi=DQ[s].iloc[T - 4:T + 1].sum() / d5 if pd.notna(d5) and d5 != 0 else np.nan, pct=pctile(hist5, hist5.iloc[T])))
    pers = pd.DataFrame(rows)
    M["persist_all"] = pers
    M["persist"] = pers[pers["d125"] >= 3].sort_values("ratio", ascending=False).reset_index(drop=True)
    M["persist_from"] = dates[T - 5]

    # ---------------- moving averages
    ma = {n: C.rolling(n, min_periods=n).mean() for n in MA_SET}
    M["ma"] = ma; M["active_ma"] = [n for n in MA_SET if N >= n + 1]
    M["inactive_ma"] = [(n, n + 1 - N) for n in MA_SET if N < n + 1]
    dist = {n: (C / ma[n] - 1) * 100 for n in MA_SET}; M["dist"] = dist

    # ---------------- cash accumulation watch (F&O only)
    oi_adj = M["OIadj"]; oi_change = oi_adj.diff(); active_cash_mas = [n for n in CASH_MAS if N >= n]
    above = pd.DataFrame(True, index=C.index, columns=C.columns)
    known = pd.DataFrame(True, index=C.index, columns=C.columns)
    for n in active_cash_mas:
        above &= C > ma[n]
        known &= ma[n].notna()
    base = (ret1 > 0) & (RAT > 1.0) & (oi_change < 0) & known
    qualifies, tracking = split_cash_signals(base, above)

    def episode_rows(flags, track=False):
        rows = []
        for s in memberships.get("fo", []):
            state = episode_state(flags[s].tolist(), cooldown=2)
            if not state or state["days"] < CASH_MIN_DAYS: continue
            i = state["last_hit"]; prior_oi = oi_adj[s].iloc[i - 1] if i else np.nan; delta = oi_change[s].iloc[i]
            ma_distance = {f"ma{n}": dist[n][s].iloc[i] if n in active_cash_mas else np.nan for n in CASH_MAS}
            rows.append(dict(sym=s, days=state["days"], cooldown=state["cooldown"], new=appeared_today(flags[s].tolist(), min_days=CASH_MIN_DAYS), signal_date=dates[i],
                             ratio=RAT[s].iloc[i], px1d=ret1[s].iloc[i] * 100, **ma_distance,
                             oi=oi_adj[s].iloc[i], doi=delta, doi_pct=delta / prior_oi * 100 if pd.notna(prior_oi) and prior_oi else np.nan,
                             close=C[s].iloc[i]))
        out = pd.DataFrame(rows)
        if len(out): out = out.sort_values(["cooldown", "days", "ratio"], ascending=[True, False, False]).reset_index(drop=True)
        return out

    M["cash_accumulation"] = episode_rows(qualifies)
    M["cash_tracking"] = episode_rows(tracking, track=True)
    M["cash_mas"] = active_cash_mas

    # ---------------- relative performance
    def rel_at(t, h):
        if t - h < 0: return pd.Series(np.nan, index=syms)
        rs = C.iloc[t] / C.iloc[t - h] - 1; rn = nifty.iloc[t] / nifty.iloc[t - h] - 1
        return ((1 + rs) / (1 + rn) - 1) * 100
    rel = {}; lists = {}
    for name, h in HORIZONS:
        now, prev = rel_at(T, h).dropna(), rel_at(T - 1, h).dropna()
        top, bot = now.sort_values(ascending=False).head(LIST_N), now.sort_values().head(LIST_N)
        ptop, pbot = set(prev.sort_values(ascending=False).head(LIST_N).index), set(prev.sort_values().head(LIST_N).index)
        lists[name] = dict(top=top, bot=bot, new_top=set(top.index) - ptop, new_bot=set(bot.index) - pbot, n=len(now))
    relT = {name: rel_at(T, h) for name, h in HORIZONS}; M["relT"] = relT
    M["relPrev"] = {name: rel_at(T - 1, h) for name, h in HORIZONS}
    M["relrank"] = {name: relT[name].rank(ascending=False, method="min") for name, _ in HORIZONS}
    cnt_top = pd.Series(0, index=syms); cnt_bot = pd.Series(0, index=syms)
    for name, _ in HORIZONS:
        for s in lists[name]["top"].index: cnt_top[s] += 1
        for s in lists[name]["bot"].index: cnt_bot[s] += 1
    M["rel"] = lists; M["cnt_top"] = cnt_top; M["cnt_bot"] = cnt_bot

    # ---------------- names at a moving average (within 0.5 sigma of daily moves)
    sig = ret1.rolling(SIGMA_WINDOW, min_periods=40).std() * 100
    at = {}
    for n in M["active_ma"]:
        items = []
        for s in syms:
            d_now, d_prev, sg, sg_p = dist[n][s].iloc[T], dist[n][s].iloc[T - 1], sig[s].iloc[T], sig[s].iloc[T - 1]
            if pd.isna(d_now) or pd.isna(sg) or sg == 0: continue
            k = abs(d_now) / sg
            if k > 0.5: continue
            crossed = pd.notna(d_prev) and np.sign(d_now) != np.sign(d_prev)
            new = not (pd.notna(d_prev) and pd.notna(sg_p) and sg_p > 0 and abs(d_prev) / sg_p <= 0.5)
            items.append(dict(sym=s, above=d_now >= 0, crossed=bool(crossed), new=bool(new), dist=d_now, k=k, sigma=sg))
        at[n] = sorted(items, key=lambda x: x["k"])
    M["at"] = at; M["sigma"] = sig.iloc[T]

    # ---------------- delivery / relative-strength / moving-average confluence
    # Relative strength means a top-30 rank on at least one configured horizon.
    # The three tables are mutually exclusive strength tiers.
    nearest_ma = {}
    for n, items in at.items():
        for item in items:
            hit = dict(ma=n, dist=item["dist"], k=item["k"], crossed=item["crossed"], new=item["new"])
            if item["sym"] not in nearest_ma or hit["k"] < nearest_ma[item["sym"]]["k"]:
                nearest_ma[item["sym"]] = hit
    rows = []
    for _, r in M["persist"].iterrows():
        s = r.sym
        horizons = [name for name, _ in HORIZONS if pd.notna(M["relrank"][name].get(s)) and M["relrank"][name].get(s) <= LIST_N]
        values = [(name, M["relT"][name].get(s)) for name in horizons]
        strongest = max(values, key=lambda x: x[1]) if values else ("", np.nan)
        ma_hit = nearest_ma.get(s)
        rows.append(dict(sym=s, d125=r.d125, d150=r.d150, ratio=r.ratio, px5=r.px5, px5_z=r.px5_z,
                         rs_count=len(horizons), rs_horizons=", ".join(horizons), rs_best=strongest[1],
                         ma=np.nan if ma_hit is None else ma_hit["ma"], ma_dist=np.nan if ma_hit is None else ma_hit["dist"],
                         ma_sigma=np.nan if ma_hit is None else ma_hit["k"], ma_cross=False if ma_hit is None else ma_hit["crossed"]))
    confluence = pd.DataFrame(rows)
    if len(confluence):
        has_rs, has_ma = confluence.rs_count > 0, confluence.ma.notna()
        M["signal_all_three"] = confluence[has_rs & has_ma].sort_values(["rs_count", "ratio"], ascending=False).reset_index(drop=True)
        M["signal_delivery_rs"] = confluence[has_rs & ~has_ma].sort_values(["rs_count", "ratio"], ascending=False).reset_index(drop=True)
        M["signal_delivery_ma"] = confluence[~has_rs & has_ma].sort_values(["ma_sigma", "ratio"], ascending=[True, False]).reset_index(drop=True)
    else:
        empty = pd.DataFrame(columns=["sym", "d125", "d150", "ratio", "px5", "px5_z", "rs_count", "rs_horizons", "rs_best", "ma", "ma_dist", "ma_sigma", "ma_cross"])
        M["signal_all_three"] = M["signal_delivery_rs"] = M["signal_delivery_ma"] = empty
    return M
