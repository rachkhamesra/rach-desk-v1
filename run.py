#!/usr/bin/env python3
"""Daily job: pull NSE/BSE end-of-day files, rebuild everything, write site/index.html."""
import argparse, json, os, sys, time
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nse, metrics, webpage, results, universes, calls, exchange_tracker, mcx_tracker, heat, power

HERE = os.path.dirname(os.path.abspath(__file__))
MARKER = "published.json"


def previously_published(root):
    try:
        with open(os.path.join(root, MARKER)) as f: return json.load(f)
    except (OSError, ValueError):
        return {}


def nothing_new(marker, last, complete):
    """True when the latest session was already published, and either with BSE delivery or BSE is still missing."""
    return marker.get("asof") == f"{last:%Y-%m-%d}" and (bool(marker.get("complete")) or not complete)


def can_skip(marker, last, complete, today, daily, mcx_latest):
    """Whether a retry run may exit without building. Besides 'the newest session is already live', a run that
    must refresh something daily (`daily`) needs a build to have happened today, and a newer MCX day forces a build.
    `mcx_latest` is a zero-argument function returning the newest MCX date as YYYY-MM-DD ('' if none), so MCX is only asked when needed."""
    if not nothing_new(marker, last, complete): return False
    if daily and marker.get("built_on") != f"{today:%Y-%m-%d}": return False
    return not (mcx_latest() > marker.get("mcx_latest", ""))


def set_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f: f.write(f"{name}={value}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(HERE, "data")); ap.add_argument("--out", default=os.path.join(HERE, "site"))
    ap.add_argument("--days", type=int, default=420, help="calendar days of history (420 is about 14 months; 1100+ for 3 years)")
    ap.add_argument("--asof", help="build as of this date (YYYY-MM-DD)"); ap.add_argument("--wait-minutes", type=int, default=0)
    ap.add_argument("--skip-if-unchanged", action="store_true", help="exit without building when the newest session (and its BSE delivery) is already published")
    ap.add_argument("--daily", action="store_true", help="with --skip-if-unchanged: still build if nothing has been published yet today (a morning retry for a dropped 6 AM run)")
    a = ap.parse_args()
    end = pd.Timestamp(a.asof) if a.asof else pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize()
    t0 = time.time(); trading = nse.sync(a.root, end - pd.Timedelta(days=a.days), end, a.wait_minutes)
    parsed = nse.parse_all(a.root, trading)
    ov = pd.read_csv(os.path.join(HERE, "corp_actions.csv")) if os.path.exists(os.path.join(HERE, "corp_actions.csv")) else None
    last = sorted(parsed)[-1]; warn = ""
    complete = parsed[last].get("bse") is not None
    def mcx_newest():                                   # MCX posts its Summary Report overnight, after the NSE/BSE files
        h = mcx_tracker.load(a.root, end, log=lambda *x: None)[0]
        return f"{h.date.max():%Y-%m-%d}" if len(h) else ""
    if a.skip_if_unchanged and can_skip(previously_published(a.root), last, complete, end, a.daily, mcx_newest):
        print(f"{last:%d %b %Y} is already published{'' if complete else ' (BSE delivery still pending)'}, MCX has nothing newer{' and a build has run today' if a.daily else ''}; not rebuilding.")
        set_output("publish", "false"); return
    if parsed[last].get("bse") is None:
        if a.wait_minutes > 0: sys.exit(f"BSE delivery for {last.date()} is not usable yet; not publishing a page with NSE-only delivery.")
        warn = f"<br><span style='color:#e8a93a'>BSE delivery for {last:%d %b} is not published yet: latest-day delivered shares are NSE-only</span>"
    memberships = universes.load(a.root)
    market_cap_cr = memberships.pop("market_cap_cr", {})
    print(f"market-cap universe: {len(market_cap_cr)} NSE companies loaded in ₹ crore")
    M = metrics.build(parsed, ov, memberships)
    M["market_cap_cr"] = market_cap_cr
    calendar, actual = results.load(a.root, end)
    M["results"] = results.build_signals(M, calendar, actual)
    M["calls"] = calls.load(a.root, end, memberships.get("fo", []))
    M["power"] = power.load_and_build(a.root, end)         # experimental alternative data; each build loads what its time budget allows
    M["heat"] = heat.load_and_build(a.root, end)           # experimental alternative data; a failure here never stops the build
    exchange_history = exchange_tracker.load(a.root, end)
    exchange_prices = M["C"]["BSE"] if "BSE" in M["C"] else pd.Series(dtype=float)
    M["exchange_tracker"] = exchange_tracker.build(exchange_history, exchange_prices)
    if M["exchange_tracker"].get("available"):
        print(f"Exchange Tracker refreshed through {M['exchange_tracker']['asof']:%d %b %Y}")
    mcx_history, mcx_expiries, mcx_status = mcx_tracker.load(a.root, end)
    mcx_prices = M["C"]["MCX"] if "MCX" in M["C"] else pd.Series(dtype=float)
    M["mcx_tracker"] = mcx_tracker.build(mcx_history, mcx_prices, mcx_expiries, end, mcx_status)
    if M["mcx_tracker"].get("available"):
        print(f"MCX Tracker refreshed through {M['mcx_tracker']['asof']:%d %b %Y}")
    os.makedirs(a.out, exist_ok=True)
    page = webpage.render(M, f"AS OF {M['dates'][-1]:%a %d %b %Y}".upper() + warn)
    M["events"].to_csv(os.path.join(a.out, "corporate_actions.csv"), index=False)       # audit log only, not shown in the UI
    open(os.path.join(a.out, "index.html"), "w", encoding="utf-8").write(page); open(os.path.join(a.out, ".nojekyll"), "w").write("")
    mcx_last = f"{mcx_history.date.max():%Y-%m-%d}" if len(mcx_history) else ""
    with open(os.path.join(a.root, MARKER), "w") as f: json.dump({"asof": f"{last:%Y-%m-%d}", "complete": complete, "built_on": f"{end:%Y-%m-%d}", "mcx_latest": mcx_last}, f)
    set_output("publish", "true")
    print(f"built {a.out}/index.html: {len(page) / 1e6:.1f} MB, {M['N']} sessions to {M['dates'][-1]:%d %b %Y}, {len(M['events'])} corporate-action events ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
