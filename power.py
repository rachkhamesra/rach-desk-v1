"""Alternative data: daily power generation from CEA's Daily Generation Report (npp.gov.in), experimental.

Sub-report 2 lists every conventional station (thermal, gas, hydro, nuclear, imports) with the day's actual
generation, coal stock days and outages. Wind and solar are not in it, so "total" here is conventional
generation, not national supply. Files appear one to two days late and layouts before Nov 2019 differ.

Each day is parsed, checked against the file's own region totals, and reduced to two small tables
(fleet by region/sector/fuel, and by plant owner) so years of history stay light.
"""
import datetime as dt
import json, os, shutil, tempfile, time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import heat
import iex
from nppdgr.fetch import fetch_one
from nppdgr.owners import OwnerMap
from nppdgr.parse_dgr2 import parse_dgr2, reconcile

FIRST_DAY = dt.date(2023, 1, 1)
RECENT_DAYS = 6                 # files this recent are fetched again every run: the portal revises them
RETRY_WINDOW = 12               # a missing or failed file older than this is not retried
PARSER_VERSION = 2              # bump when parsing changes in a way that makes stored days wrong: stored history is then reloaded
BUDGET_S = 900                  # per build; a long backfill simply continues on the next build
PAUSE_S = 0.5
WORKERS, AHEAD = 4, 8           # files downloaded at once, and how many days ahead of the parser the downloads run
KEYS = ["region", "sector", "fuel"]
FLEET_COLS = ["date", "region", "sector", "fuel", "n", "mw", "actual_mu", "prog_mu", "outage_mw", "coal_mw", "coal_mwdays"]
OWNER_COLS = ["date", "owner", "fuel", "n", "mw", "actual_mu", "outage_mw", "coal_mw", "coal_mwdays"]
SERIES = [("ALL", "All conventional", "MU/day"), ("THERMAL", "Coal and lignite", "MU/day"), ("HYDRO", "Hydro", "MU/day")]
LISTED = {"NTPC": "NTPC", "Adani Power": "ADANIPOWER", "JSW Energy": "JSWENERGY", "Tata Power": "TATAPOWER", "Torrent Power": "TORNTPOWER",
          "CESC": "CESC", "NLC": "NLCINDIA", "Reliance Power": "RPOWER", "SJVN": "SJVN", "Jindal Power": "JINDALSTEL", "Vedanta": "VEDL"}


# ------------------------------------------------------------------ one day
def aggregate(parsed, owners):
    """Reduce one parsed report to (fleet rows, owner rows, stations, units)."""
    st = pd.DataFrame(parsed.stations)
    st["sector"] = st["sector"].fillna(""); st["fuel"] = st["fuel"].fillna(""); st["region"] = st["region"].fillna("")
    look = [owners.lookup(p, s, state) for p, s, state in zip(st["plant"], st["sector"], st["state"])]
    st["owner"] = [x[0] for x in look]; st["owner_confidence"] = [x[1] for x in look]
    coal = (st["fuel"] == "THERMAL") & (st["coal_days"].fillna(0) > 0)           # a 0 may mean "not reported", so it is left out
    st["coal_mw"] = st["mw"].where(coal, 0.0); st["coal_mwdays"] = (st["mw"] * st["coal_days"]).where(coal, 0.0)
    st["plf"] = np.where(st["mw"] > 0, st["actual_mu"] * 1000 / (st["mw"] * 24) * 100, np.nan)
    agg = dict(n=("plant", "size"), mw=("mw", "sum"), actual_mu=("actual_mu", "sum"), prog_mu=("prog_mu", "sum"),
               outage_mw=("outage_mw", "sum"), coal_mw=("coal_mw", "sum"), coal_mwdays=("coal_mwdays", "sum"))
    day = parsed.date.isoformat()
    fleet = st.groupby(KEYS).agg(**agg).reset_index(); fleet.insert(0, "date", day)
    owner = st.groupby(["owner", "fuel"]).agg(**{k: v for k, v in agg.items() if k != "prog_mu"}).reset_index(); owner.insert(0, "date", day)
    units = pd.DataFrame(parsed.units)
    return fleet[FLEET_COLS], owner[OWNER_COLS], st, units


# ------------------------------------------------------------------ refresh
def _read(path, cols):
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=cols)


MAX_DOWNLOAD_FAILS = 4          # downloads failing in a row: the portal is down or blocking this address, so stop for this build


def _fetch(day, n, raw, force=False):
    """Bounded: two tries of 30 seconds, so a slow portal costs about a minute a day rather than five."""
    return fetch_one(day, n, raw, retries=2, force=force, timeout=30)


def refresh(root, today, start=FIRST_DAY, budget_s=BUDGET_S, log=print, fetch=_fetch, pause=PAUSE_S, owners=None):
    """Bring data/power up to date. Newest days first, so a long backfill is resumable and the page fills from the recent end."""
    folder = os.path.join(root, "power"); os.makedirs(folder, exist_ok=True)
    fleet_p, owner_p, status_p = (os.path.join(folder, n) for n in ("fleet.csv", "owner.csv", "status.json"))
    fleet, owner = _read(fleet_p, FLEET_COLS), _read(owner_p, OWNER_COLS)
    try:
        with open(status_p) as f: status = json.load(f)
    except (OSError, ValueError):
        status = {}
    if status.get("version") != PARSER_VERSION:                                  # stored under an older parser: start the history again
        fleet, owner, status = fleet.iloc[0:0], owner.iloc[0:0], {"version": PARSER_VERSION}
    missing, problems = status.setdefault("missing", {}), status.setdefault("problems", {})
    have = set(fleet["date"].unique()); today = pd.Timestamp(today).date()
    days = [today - dt.timedelta(days=i) for i in range((today - start).days + 1)]       # newest first
    owners = owners or OwnerMap()
    raw = tempfile.mkdtemp(prefix="dgr-"); t0 = time.time(); done = skipped = streak = 0
    new_fleet, new_owner = [], []
    def flush(last=False):
        nonlocal fleet, owner, new_fleet, new_owner
        if new_fleet:
            dates = {f["date"].iloc[0] for f in new_fleet}
            fleet = pd.concat([fleet[~fleet["date"].isin(dates)]] + new_fleet, ignore_index=True).sort_values(["date"] + KEYS)
            owner = pd.concat([owner[~owner["date"].isin(dates)]] + new_owner, ignore_index=True).sort_values(["date", "owner", "fuel"])
            new_fleet, new_owner = [], []
        fleet.to_csv(fleet_p, index=False); owner.to_csv(owner_p, index=False)
        with open(status_p, "w") as f: json.dump(status, f)
    todo = []
    for day in days:
        iso, age = day.isoformat(), (today - day).days
        recent = age <= RECENT_DAYS
        if not recent and (iso in have or (age > RETRY_WINDOW and (iso in missing or iso in problems))): continue
        todo.append((day, iso, recent))
    ex = ThreadPoolExecutor(WORKERS)
    def job(day, recent):
        """Download one report. A download error comes back as a value, so the parser sees failures in date order."""
        try: return fetch(day, 2, raw, force=recent)
        except RuntimeError as e: return e
        finally: pause and time.sleep(pause)
    futures = {}
    def submit(i):
        if i < len(todo) and i not in futures: futures[i] = ex.submit(job, todo[i][0], todo[i][2])
    try:
        for i in range(min(AHEAD, len(todo))): submit(i)
        for i, (day, iso, recent) in enumerate(todo):                  # parsed in date order, newest first, while the next few download
            if time.time() - t0 > budget_s:
                log(f"power: time budget reached after {done} days; the rest continues on the next run"); break
            submit(i + AHEAD)
            res = futures.pop(i).result()
            if isinstance(res, RuntimeError):
                problems[iso] = f"download: {res}"[:160]; skipped += 1; streak += 1
                if streak >= MAX_DOWNLOAD_FAILS:
                    log(f"power: {streak} downloads failed in a row; stopping for this build"); break
                continue
            path, state = res; streak = 0
            if state == "missing":
                missing[iso] = today.isoformat(); skipped += 1; continue
            try:
                parsed = parse_dgr2(path)
                if parsed.date != day: raise ValueError(f"file is dated {parsed.date}")
                bad = [r for r in reconcile(parsed) if not r[3]]
                if bad: raise ValueError(f"station sums do not match the file's totals {bad}")
                f_, o_, _, _ = aggregate(parsed, owners)
                new_fleet.append(f_); new_owner.append(o_); missing.pop(iso, None); problems.pop(iso, None); done += 1
            except Exception as e:                                                   # one bad day must not stop the rest
                problems[iso] = f"{type(e).__name__}: {e}"[:160]; skipped += 1
            finally:
                if path and os.path.exists(path): os.remove(path)
            have.add(iso)
            if done and done % 100 == 0: flush()
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
        flush(); shutil.rmtree(raw, ignore_errors=True)
    log(f"power: {done} days loaded, {skipped} missing or failed; {fleet['date'].nunique()} days stored, newest {fleet['date'].max() if len(fleet) else 'none'}")
    return fleet, owner


# ------------------------------------------------------------------ build
def daily_series(fleet):
    """{key: pd.Series indexed by date} for every entry in SERIES."""
    f = fleet.copy(); f["date"] = pd.to_datetime(f["date"])
    return {"ALL": f.groupby("date")["actual_mu"].sum(),
            "THERMAL": f[f["fuel"] == "THERMAL"].groupby("date")["actual_mu"].sum(),
            "HYDRO": f[(f["fuel"] == "HYDRO") & (f["sector"] != "IMPORT")].groupby("date")["actual_mu"].sum()}


def _year(series, year, last):
    arr = heat.year_arrays(pd.DataFrame({"mean": series, "max": series}), year, last)["mean"]
    return [None if v is None else round(v, 1) for v in arr]


def owner_rows(owner, last, window=30):
    o = owner.copy(); o["date"] = pd.to_datetime(o["date"])
    lo, ly_lo, ly_hi = last - pd.Timedelta(days=window - 1), last - pd.Timedelta(days=364 + window - 1), last - pd.Timedelta(days=364)
    cur, prev = o[(o["date"] >= lo) & (o["date"] <= last)], o[(o["date"] >= ly_lo) & (o["date"] <= ly_hi)]
    rows = []
    for name, g in cur.groupby("owner"):
        days = g["date"].nunique()
        if name in ("Other", "REVIEW") or name.startswith(("STATE", "IMPORT")) or days < window // 2: continue
        mu = g["actual_mu"].sum() / days; pg = prev[prev["owner"] == name]
        pdays = pg["date"].nunique(); pmu = pg["actual_mu"].sum() / pdays if pdays >= window // 2 else None
        th = g[g["fuel"] == "THERMAL"]; latest = g[g["date"] == g["date"].max()]; lth = latest[latest["fuel"] == "THERMAL"]
        cm = lth["coal_mw"].sum()
        rows.append(dict(owner=name, symbol=LISTED.get(name), mw=round(float(latest["mw"].sum())), mu=round(float(mu), 1),
                         yoy=None if not pmu else round((mu / pmu - 1) * 100, 1),
                         plf=round(float(th["actual_mu"].sum() * 1000 / (th["mw"].sum() * 24) * 100), 1) if th["mw"].sum() else None,
                         coal=round(float(lth["coal_mwdays"].sum() / cm), 1) if cm else None))
    return sorted(rows, key=lambda r: -r["mu"])


def iex_block(root):
    """IEX day-ahead prices (weighted MCP, Rs per kWh) and cleared volume (MU a day) as year-versus-year arrays, or None."""
    path = os.path.join(root, "power", "iex_dam.csv")
    if not os.path.exists(path): return None
    d = pd.read_csv(path, parse_dates=["date"]).dropna(subset=["wmcp"]).sort_values("date")
    if len(d) < 30: return None
    last = d["date"].max(); years = [last.year, last.year - 1, last.year - 2]; d = d.set_index("date")
    price, volume, simple = d["wmcp"] / 1000.0, d["mcv_mwh"] / 1000.0, d["mcp"] / 1000.0
    arr = lambda s: {str(y): [None if v is None else round(v, 2) for v in heat.year_arrays(pd.DataFrame({"mean": s, "max": s}), y, last)["mean"]] for y in years}
    row = d.iloc[-1]
    return dict(asof=f"{last:%Y-%m-%d}", years=years, price=arr(price), volume=arr(volume),
                latest=dict(date=f"{last:%Y-%m-%d}", wmcp=round(float(row["wmcp"]) / 1000, 2), mcp=round(float(row["mcp"]) / 1000, 2), mcv=round(float(row["mcv_mwh"]) / 1000, 1)))


def company_series(owner, names, last, years):
    """Daily generation (all fuels, MU/day) for each named owner, on the 365-day calendar, as [{name, symbol, years}]."""
    o = owner.copy(); o["date"] = pd.to_datetime(o["date"]); out = []
    for name in names:
        s = o[o["owner"] == name].groupby("date")["actual_mu"].sum()
        out.append(dict(name=name, symbol=LISTED.get(name), years={str(y): _year(s, y, last) for y in years}))
    return out


def build(root, asof=None):
    """Everything the Power view shows, or None when nothing is stored yet."""
    folder = os.path.join(root, "power")
    fleet, owner = _read(os.path.join(folder, "fleet.csv"), FLEET_COLS), _read(os.path.join(folder, "owner.csv"), OWNER_COLS)
    if not len(fleet): return None
    last = pd.Timestamp(fleet["date"].max()); series = daily_series(fleet)
    years = [last.year, last.year - 1, last.year - 2]
    out_series = {key: dict(label=label, unit=unit, years={str(y): _year(series[key], y, last) for y in years})
                  for key, label, unit in SERIES if key in series and len(series[key])}
    owners = owner_rows(owner, last)
    window = owner[(pd.to_datetime(owner["date"]) > last - pd.Timedelta(days=30))]
    tot = window["actual_mu"].sum() or 1.0
    share = lambda names: round(float(window[window["owner"].isin(names)]["actual_mu"].sum() / tot * 100), 1)
    state = round(float(window[window["owner"].str.startswith(("STATE", "IMPORT"))]["actual_mu"].sum() / tot * 100), 1)
    dates = sorted(fleet["date"].unique())
    return dict(asof=f"{last:%Y-%m-%d}", first=dates[0], n_days=len(dates), years=years, series=out_series,
                companies=company_series(owner, [o["owner"] for o in owners], last, years), owners=owners,
                coverage=dict(other=share(["Other"]), review=share(["REVIEW"]), state=state), iex=iex_block(root))


def load_and_build(root, asof, log=print, budget_s=None):
    """The one call run.py makes. A failure here never stops the desk publishing."""
    try:
        refresh(root, asof, budget_s=budget_s if budget_s is not None else float(os.environ.get("POWER_BUDGET_S", BUDGET_S)), log=log)
        try:
            iex.refresh(root, asof, log=log)                          # the exchange price; its failure never affects the generation data
        except Exception as e:
            log(f"iex: skipped ({type(e).__name__}: {e})")
        data = build(root, asof)
        log(f"power: {data['n_days']} days, {data['first']} to {data['asof']}" if data else "power: no data yet; the Power view will say so")
        return data
    except Exception as e:
        log(f"power: skipped ({type(e).__name__}: {e})")
        return None
