import os, pickle
import numpy as np, pandas as pd
import metrics

# The function the incremental one replaced, verbatim: every past session is scanned on every call.
REFERENCE = r'''
def base_followthrough_reference(C, H, L, DQ, RAT, symbols, T, nifty=None, cooldown=10):
    """Replay the base scan on every past session and measure what happened next.

    A signal is the first day a stock appears in a stage after at least `cooldown` sessions out of
    it. Returns are from that day's close, so nothing after the signal date feeds the signal.
    `fail20` means the low undercut the base support within 20 sessions; it is only set once those
    20 sessions exist. `mdd20` is the worst low versus the signal close over the sessions seen.
    """
    pre = _base_pre(C, H, L, DQ, RAT)
    nifty = None if nifty is None else np.asarray(nifty, dtype=float)
    last_seen, rows = {}, []
    for t in range(max(BASE_WINDOWS) + 1, T + 1):
        frame = breakout_bases(C, H, L, DQ, RAT, symbols, t, pre=pre)
        for r in frame.itertuples():
            key = (r.sym, r.stage)
            fresh_signal = key not in last_seen or t - last_seen[key] > cooldown
            last_seen[key] = t
            if not fresh_signal: continue
            close, path = C[r.sym].iloc[t], C[r.sym].iloc[t + 1:]
            item = dict(sym=r.sym, t=t, stage=r.stage, support=r.support, close=close, quality=sum(getattr(r, f) for f in FOLLOW_FLAGS),
                        age=T - t, to_date=(path.iloc[-1] / close - 1) * 100 if len(path) and pd.notna(path.iloc[-1]) else np.nan)
            for f in FOLLOW_FLAGS: item[f] = bool(getattr(r, f))
            for h in FOLLOW_HORIZONS:
                ok = t + h <= T and pd.notna(C[r.sym].iloc[t + h]) and close > 0
                item[f"r{h}"] = (C[r.sym].iloc[t + h] / close - 1) * 100 if ok else np.nan
                bench = nifty is not None and ok and nifty[t] and not np.isnan(nifty[t]) and not np.isnan(nifty[t + h])
                item[f"x{h}"] = item[f"r{h}"] - (nifty[t + h] / nifty[t] - 1) * 100 if bench else np.nan
            lows = L[r.sym].iloc[t + 1:t + 1 + max(FOLLOW_HORIZONS)].dropna()
            item["mdd20"] = (lows.min() / close - 1) * 100 if len(lows) else np.nan
            item["fail20"] = (bool(lows.min() < r.support) if len(lows) else None) if t + max(FOLLOW_HORIZONS) <= T else None
            rows.append(item)
    return pd.DataFrame(rows, columns=FOLLOW_COLUMNS)


'''
_ns = dict(vars(metrics)); exec(REFERENCE, _ns); reference = _ns["base_followthrough_reference"]


def panel(n=230, k=22, seed=3):
    """Stocks that rise, then sit in a range for a while and break out, with ordinary noise, so the base scan has things to find."""
    rng = np.random.default_rng(seed); dates = pd.bdate_range("2025-01-01", periods=n); C = {}
    for j in range(k):
        r = rng.normal(0, .008, n); r[:60] += .004; r[60 + (j % 40):120 + (j % 50)] *= .25; r[150 + (j % 30):165 + (j % 30)] += .012
        C[f"S{j:02d}"] = 100 * np.cumprod(1 + r)
    C = pd.DataFrame(C, index=dates); H = C * (1 + rng.uniform(0, .01, C.shape)); L = C * (1 - rng.uniform(0, .01, C.shape))
    DQ = pd.DataFrame(rng.uniform(5e4, 2e5, C.shape), index=dates, columns=C.columns); RAT = DQ / DQ.shift(1).rolling(20, min_periods=15).mean()
    return C, H, L, DQ, RAT, list(C.columns), pd.Series(np.linspace(100, 130, n), index=dates).to_numpy()


def same(a, b):
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), check_dtype=False, check_exact=False, rtol=1e-9, atol=1e-9)


def test_the_new_function_matches_the_original_exactly_with_no_cache():
    C, H, L, DQ, RAT, syms, nf = panel(); T = len(C) - 1
    want = reference(C, H, L, DQ, RAT, syms, T, nifty=nf)
    assert len(want) > 20                                                                  # the fixture really produces signals
    same(metrics.base_followthrough(C, H, L, DQ, RAT, syms, T, nifty=nf), want)


def test_extending_the_cache_by_new_sessions_gives_the_same_answer_as_scanning_everything(tmp_path):
    C, H, L, DQ, RAT, syms, nf = panel(); T = len(C) - 1; path = str(tmp_path / "base_events.pkl")
    first = metrics.base_followthrough(C, H, L, DQ, RAT, syms, T - 12, nifty=nf, cache_path=path)               # yesterday's build, twelve sessions short
    assert os.path.exists(path) and pickle.load(open(path, "rb"))["t"] == T - 12
    later = metrics.base_followthrough(C, H, L, DQ, RAT, syms, T, nifty=nf, cache_path=path)                    # today's: only twelve sessions are scanned
    same(later, reference(C, H, L, DQ, RAT, syms, T, nifty=nf))
    assert pickle.load(open(path, "rb"))["t"] == T
    again = metrics.base_followthrough(C, H, L, DQ, RAT, syms, T, nifty=nf, cache_path=path)                    # a second build the same day changes nothing
    same(again, later)
    assert len(later) >= len(first)


def test_the_cache_is_not_used_if_earlier_data_was_restated_or_the_symbols_changed(tmp_path):
    C, H, L, DQ, RAT, syms, nf = panel(); T = len(C) - 1; path = str(tmp_path / "b.pkl")
    metrics.base_followthrough(C, H, L, DQ, RAT, syms, T - 20, nifty=nf, cache_path=path)
    C2 = C.copy(); C2.iloc[:150] = C2.iloc[:150] * 0.5                                       # a split restates the history
    H2, L2 = H.copy(), L.copy(); H2.iloc[:150] *= .5; L2.iloc[:150] *= .5
    same(metrics.base_followthrough(C2, H2, L2, DQ, RAT, syms, T, nifty=nf, cache_path=path), reference(C2, H2, L2, DQ, RAT, syms, T, nifty=nf))
    metrics.base_followthrough(C, H, L, DQ, RAT, syms, T - 20, nifty=nf, cache_path=path)
    fewer = syms[:15]; same(metrics.base_followthrough(C, H, L, DQ, RAT, fewer, T, nifty=nf, cache_path=path), reference(C, H, L, DQ, RAT, fewer, T, nifty=nf))     # a different symbol list
    open(path, "wb").write(b"not a pickle"); same(metrics.base_followthrough(C, H, L, DQ, RAT, syms, T, nifty=nf, cache_path=path), reference(C, H, L, DQ, RAT, syms, T, nifty=nf))   # a damaged file


def test_the_cache_is_faster_than_a_full_scan(tmp_path):
    import time
    C, H, L, DQ, RAT, syms, nf = panel(); T = len(C) - 1; path = str(tmp_path / "b.pkl")
    metrics.base_followthrough(C, H, L, DQ, RAT, syms, T - 1, nifty=nf, cache_path=path)
    t0 = time.time(); metrics.base_followthrough(C, H, L, DQ, RAT, syms, T, nifty=nf, cache_path=path); warm = time.time() - t0
    t0 = time.time(); reference(C, H, L, DQ, RAT, syms, T, nifty=nf); cold = time.time() - t0
    assert warm < cold / 3, (warm, cold)
