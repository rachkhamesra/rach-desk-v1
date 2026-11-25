"""Audit of single-stock-futures open interest against NSE's own F&O bhavcopies, for every F&O stock and every session held. Run locally:  python oi_audit.py [data_dir]

Two checks.
  1. Expiry days. A contract that expires on a session is settled at its close, but the file still lists it with the open interest it had going into the close. Totals that include it
     are too high on the expiry day and the next session shows a drop that did not happen. This reports, for each expiry day, how many stocks are affected and by how much, and what
     the next-session change would have read as, with and without the expiring series.
  2. Continuity. The change a session reports (ChngInOpnIntrst) must equal the difference between the open interest the previous session closed with and what this session's rows say the
     previous close was. A break means missing contract rows, a restated series or an adjustment, and the stock-day is listed.
"""
import glob, os, sys
import numpy as np
import pandas as pd
import nse


def session(path):
    d = pd.Timestamp(os.path.basename(path)[:8])
    df = nse._read_zip_csv(path); df = df[df["FinInstrmTp"] == "STF"].copy()
    df["sym"] = df["TckrSymb"].astype(str).str.strip()
    actual = pd.to_datetime(df["FininstrmActlXpryDt"], errors="coerce"); df["exp"] = actual.fillna(pd.to_datetime(df["XpryDt"], errors="coerce")).dt.normalize()
    df["oi"] = pd.to_numeric(df["OpnIntrst"], errors="coerce"); df["chg"] = pd.to_numeric(df["ChngInOpnIntrst"], errors="coerce")
    return d, df


def audit(root="data", log=print):
    files = sorted(glob.glob(os.path.join(root, "raw", "fo", "*.zip")))
    prev_total, rows, breaks = None, [], []
    for f in files:
        d, df = session(f)
        all_oi = df.groupby("sym")["oi"].sum(); live = df[df["exp"] > d].groupby("sym")["oi"].sum().reindex(all_oi.index, fill_value=0)
        carried_in = (df["oi"] - df["chg"]).groupby(df["sym"]).sum()                       # what the rows say the previous close was
        if prev_total is not None:
            for sym, was in carried_in.items():
                prev = prev_total.get(sym)
                if prev is not None and prev > 0 and abs(was - prev) > 0.02 * prev and abs(was - prev) > 2000: breaks.append((d, sym, prev, was))
        rows.append(pd.DataFrame({"date": d, "sym": all_oi.index, "all_oi": all_oi.values, "live_oi": live.values}))
        # 
        prev_total = live.to_dict()           # the next session's rows list only contracts still alive, so its carried-in figure is compared with what continued
    log_df = pd.concat(rows, ignore_index=True)
    log_df["expiring"] = log_df["all_oi"] - log_df["live_oi"]
    return log_df, breaks


def report(root="data", top=15, log=print):
    h, breaks = audit(root)
    exp = h[h["expiring"] > 0]
    days = exp.groupby("date")["sym"].nunique()
    log(f"{h['date'].nunique()} sessions, {h['sym'].nunique()} F&O stocks, {len(days)} sessions on which a futures contract expired")
    h = h.sort_values(["sym", "date"]); h["next_all"] = h.groupby("sym")["all_oi"].shift(-1); h["next_live"] = h.groupby("sym")["live_oi"].shift(-1)
    e = h[(h["expiring"] > 0) & (h["live_oi"] > 0) & (h["next_live"] > 0)].copy()                   # a stock with nothing left past the expiry has no next-session change to compare
    e["old_next_pct"] = (e["next_all"] / e["all_oi"] - 1) * 100          # next session against the expiry day's total, expiring series included (what the page used to show)
    e["new_next_pct"] = (e["next_live"] / e["live_oi"] - 1) * 100        # next session against the expiry day's total without it
    e = e.dropna(subset=["old_next_pct", "new_next_pct"])
    e["phantom"] = e["old_next_pct"] - e["new_next_pct"]
    log(f"stock-sessions affected: {len(e)}; median share of the day's open interest that was the expiring series: {(e['expiring'] / e['all_oi']).median() * 100:.0f}%")
    log(f"next-session change that was a phantom drop of more than 10 points: {(e['phantom'] < -10).sum()} stock-sessions ({(e['phantom'] < -10).mean() * 100:.0f}%); more than 25 points: {(e['phantom'] < -25).sum()}")
    for d, g in e.groupby("date"):
        if len(g) >= 100: log(f"  {d:%d %b %Y}: {len(g)} stocks, median phantom drop {g['phantom'].median():.0f} points")
    log("largest phantom drops:")
    for r in e.sort_values("phantom").head(top).itertuples(): log(f"  {r.date:%d %b %Y} {r.sym}: next session read {r.old_next_pct:+.0f}%, really {r.new_next_pct:+.0f}%")
    log(f"continuity breaks (the day's own rows disagree with the previous close by more than 2%): {len(breaks)}")
    for d, sym, prev, was in sorted(breaks, key=lambda x: -abs(x[3] / x[2] - 1))[:top]: log(f"  {d:%d %b %Y} {sym}: previous close {prev:,.0f}, this file says it was {was:,.0f}")
    return e, breaks


if __name__ == "__main__":
    report(*sys.argv[1:2])
