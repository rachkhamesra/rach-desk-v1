#!/usr/bin/env python3
"""Daily job: pull NSE/BSE end-of-day files, rebuild everything, write site/index.html."""
import argparse, os, sys, time
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nse, metrics, webpage, results, universes, calls, exchange_tracker

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(HERE, "data")); ap.add_argument("--out", default=os.path.join(HERE, "site"))
    ap.add_argument("--days", type=int, default=420, help="calendar days of history (420 is about 14 months; 1100+ for 3 years)")
    ap.add_argument("--asof", help="build as of this date (YYYY-MM-DD)"); ap.add_argument("--wait-minutes", type=int, default=0)
    a = ap.parse_args()
    end = pd.Timestamp(a.asof) if a.asof else pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize()
    t0 = time.time(); trading = nse.sync(a.root, end - pd.Timedelta(days=a.days), end, a.wait_minutes)
    parsed = nse.parse_all(a.root, trading)
    ov = pd.read_csv(os.path.join(HERE, "corp_actions.csv")) if os.path.exists(os.path.join(HERE, "corp_actions.csv")) else None
    last = sorted(parsed)[-1]; warn = ""
    if parsed[last].get("bse") is None:
        if a.wait_minutes > 0: sys.exit(f"BSE delivery for {last.date()} is not usable yet; not publishing a page with NSE-only delivery.")
        warn = f"<br><span style='color:#e8a93a'>BSE delivery for {last:%d %b} is not published yet: latest-day delivered shares are NSE-only</span>"
    memberships = universes.load(a.root)
    M = metrics.build(parsed, ov, memberships)
    calendar, actual = results.load(a.root, end)
    M["results"] = results.build_signals(M, calendar, actual)
    M["calls"] = calls.load(a.root, end, memberships.get("fo", []))
    exchange_history = exchange_tracker.load(a.root, end)
    exchange_prices = M["C"]["BSE"] if "BSE" in M["C"] else pd.Series(dtype=float)
    M["exchange_tracker"] = exchange_tracker.build(exchange_history, exchange_prices)
    if M["exchange_tracker"].get("available"):
        print(f"Exchange Tracker refreshed through {M['exchange_tracker']['asof']:%d %b %Y}")
    os.makedirs(a.out, exist_ok=True)
    page = webpage.render(M, f"AS OF {M['dates'][-1]:%a %d %b %Y}".upper() + warn)
    M["events"].to_csv(os.path.join(a.out, "corporate_actions.csv"), index=False)       # audit log only, not shown in the UI
    open(os.path.join(a.out, "index.html"), "w", encoding="utf-8").write(page); open(os.path.join(a.out, ".nojekyll"), "w").write("")
    print(f"built {a.out}/index.html: {len(page) / 1e6:.1f} MB, {M['N']} sessions to {M['dates'][-1]:%d %b %Y}, {len(M['events'])} corporate-action events ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
