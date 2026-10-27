"""Corporate actions, fully automatic. NSE and BSE do not adjust the previous close in their files, so a split or bonus looks like a crash.

A one-day jump is treated as a corporate action (history adjusted) when
  1. it is confirmed by an exchange signal: the ISIN changed, or the futures lot size moved the opposite way; or
  2. it has no such signal (the stock was not in F&O then) but rupee turnover stayed normal. A split changes the share count, not the
     rupees traded, whereas a crash or a news-driven gap comes with a turnover spike (3x the prior 20-day average or more).
Anything else is a real move and is left alone. Ratios are snapped to standard split/bonus values when within 2%, else the observed ratio is used (demergers).
corp_actions.csv can still force a decision (symbol,date,action(accept|reject|adjust),ratio,note); nothing needs to be maintained by hand.
"""
import numpy as np, pandas as pd

STD = sorted({1/2, 1/3, 1/4, 1/5, 1/6, 1/7, 1/8, 1/9, 1/10, 1/12, 1/15, 1/20, 1/25, 1/50, 2/3, 3/4, 4/5, 5/6, 3/5, 2/5, 3/8, 4/7})
STD_UP = [1 / x for x in STD]


def snap(r):
    cands = STD if r < 1 else STD_UP
    c = min(cands, key=lambda x: abs(np.log(r / x)))
    tol = 0.15 if (r < 0.6 or r > 1.7) else 0.07
    return c if abs(np.log(r / c)) < tol else None


def find_events(close, isin, lot, turn=None, overrides=None):
    dates = close.index; syms = list(close.columns)
    R = (close / close.shift(1)).values
    I = isin.values; ISINCHG = np.zeros(R.shape, bool)
    ISINCHG[1:] = (I[1:] != I[:-1]) & pd.notna(I[1:]) & pd.notna(I[:-1])
    L = lot.values.astype(float); LR = np.full(R.shape, np.nan); LR[1:] = L[1:] / L[:-1]
    big = (R < 0.78) | (R > 1.25); mid = (R < 0.85) | (R > 1.18)
    cand = big | ISINCHG | (mid & (np.nan_to_num(LR, nan=1.0) != 1.0))
    out = []
    for t, j in np.argwhere(cand):
        if t == 0: continue
        r = R[t, j]; sym = syms[j]
        w = slice(max(t - 1, 1), min(t + 3, len(dates)))              # signals may land a day either side of the price jump
        isin_near = bool(ISINCHG[w, j].any())
        lrw = np.nanprod(np.where(np.isnan(LR[w, j]), 1.0, LR[w, j]))
        lot_ok = lrw != 1.0 and not np.isnan(r) and abs(np.log(lrw * r)) < 0.22
        f = snap(r) if not np.isnan(r) else None
        quiet = None
        if turn is not None and not np.isnan(r):
            base = turn[sym].iloc[max(0, t - 20):t].dropna()
            if len(base) >= 5 and base.mean() > 0: quiet = bool(turn[sym].iloc[t:t + 3].max() / base.mean() < 3.0)
        if (big[t, j] or (mid[t, j] and (isin_near or lot_ok))) and not np.isnan(r):
            sig = " and ".join(x for x, ok in (("ISIN change", isin_near), ("lot-size change", lot_ok)) if ok)
            tight = f is not None and abs(np.log(r / f)) < 0.02
            if isin_near or lot_ok:
                dec, fac = "auto", (f if f else r)
                why = f"price ratio {r:.3f} confirmed by {sig}" + ("" if f else " (off-standard ratio, factor taken from the price)")
            elif quiet:
                dec, fac = "auto", (f if tight else r)
                why = f"price ratio {r:.3f}, no ISIN/lot signal, but rupee turnover stayed normal, so treated as a share-count change"
            elif quiet is False: dec, fac, why = "left", 1.0, f"price ratio {r:.3f} with a turnover spike: a real move, not adjusted"
            else: dec, fac, why = "left", 1.0, f"price ratio {r:.3f} but too little history to test turnover: not adjusted"
        elif ISINCHG[t, j]:
            if any(e["symbol"] == sym and abs((e["date"] - dates[t]).days) <= 5 for e in out): continue
            dec, fac, why = "info", 1.0, "ISIN changed with no price jump"
        else: continue
        out.append(dict(date=dates[t], symbol=sym, ratio=float(r) if not np.isnan(r) else np.nan, isin_change=isin_near,
                        lot_ratio=float(lrw) if lrw != 1.0 else np.nan, decision=dec, factor=float(fac), note=why))
    ev = pd.DataFrame(out, columns=["date", "symbol", "ratio", "isin_change", "lot_ratio", "decision", "factor", "note"])
    # a split often shows up on two adjacent days (ISIN one day, price the next): keep the first, drop the repeat
    ev = ev.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "decision", "factor"], keep="first") if len(ev) else ev
    ev = _apply_overrides(ev, overrides)
    return ev.sort_values("date").reset_index(drop=True)


def _apply_overrides(ev, ov):
    if ov is None or not len(ov): return ev
    ev = ev.copy()
    for _, o in ov.iterrows():
        d = pd.Timestamp(o["date"]); act = str(o["action"]).strip().lower(); sym = o["symbol"]
        m = (ev["symbol"] == sym) & ((ev["date"] - d).abs() <= pd.Timedelta(days=3))
        ratio = float(o["ratio"]) if pd.notna(o.get("ratio")) else np.nan
        note = f"override ({act}): {o.get('note', '')}"
        if act == "reject": ev.loc[m, ["decision", "factor", "note"]] = ["rejected", 1.0, note]
        elif act == "accept" and m.any():
            ev.loc[m, "factor"] = ratio if not np.isnan(ratio) else ev.loc[m, "ratio"].apply(lambda r: snap(r) or r); ev.loc[m, ["decision", "note"]] = ["accepted", note]
        elif act in ("adjust", "accept"):
            ev = pd.concat([ev, pd.DataFrame([dict(date=d, symbol=sym, ratio=np.nan, isin_change=False, lot_ratio=np.nan, decision="accepted", factor=ratio, note=note)])], ignore_index=True)
    return ev


def factors(dates, symbols, ev):
    """F[t, s] multiplies the raw price on day t to put it on today's share basis (quantities are divided by it)."""
    F = pd.DataFrame(1.0, index=dates, columns=symbols)
    for _, e in ev[ev["decision"].isin(["auto", "accepted"])].iterrows():
        if e["symbol"] in F.columns: F.loc[F.index < e["date"], e["symbol"]] *= e["factor"]
    return F
