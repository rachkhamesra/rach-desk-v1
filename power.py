"""Alternative data: daily power generation from CEA's Daily Generation Report (npp.gov.in), experimental.

Sub-report 2 lists every conventional station (thermal, gas, hydro, nuclear, imports) with the day's actual
generation, coal stock days and outages. Wind and solar are not in it, so "total" here is conventional
generation, not national supply. Files appear one to two days late and layouts before Nov 2019 differ.

Each day is parsed, checked against the file's own region totals, and reduced to two small tables
(fleet by region/sector/fuel, and by plant owner) so years of history stay light. The newest day's
stations and unit outages are kept in full for the watch tables.
"""
import datetime as dt
import json, os, shutil, tempfile, time

import numpy as np
import pandas as pd

import heat
from nppdgr.fetch import fetch_one
from nppdgr.owners import OwnerMap
from nppdgr.parse_dgr2 import parse_dgr2, reconcile

FIRST_DAY = dt.date(2023, 1, 1)
RECENT_DAYS = 6                 # files this recent are fetched again every run: the portal revises them
RETRY_WINDOW = 12               # a missing or failed file older than this is not retried
PARSER_VERSION = 2              # bump when parsing changes in a way that makes stored days wrong: stored history is then reloaded
BUDGET_S = 900                  # per build; a long backfill simply continues on the next build
PAUSE_S = 0.5
KEYS = ["region", "sector", "fuel"]
FLEET_COLS = ["date", "region", "sector", "fuel", "n", "mw", "actual_mu", "prog_mu", "outage_mw", "coal_mw", "coal_mwdays"]
OWNER_COLS = ["date", "owner", "fuel", "n", "mw", "actual_mu", "outage_mw", "coal_mw", "coal_mwdays"]
SERIES = [("ALL", "All conventional", "MU/day"), ("THERMAL", "Coal and lignite", "MU/day"), ("GAS", "Gas", "MU/day"),
          ("HYDRO", "Hydro", "MU/day"), ("NUCLEAR", "Nuclear", "MU/day"),
          ("NORTHERN", "Northern region", "MU/day"), ("WESTERN", "Western region", "MU/day"), ("SOUTHERN", "Southern region", "MU/day"),
          ("EASTERN", "Eastern region", "MU/day"), ("NORTH EASTERN", "North-eastern region", "MU/day"),
          ("PLF", "Coal and lignite plant load factor", "%"), ("COALDAYS", "Coal stock, MW-weighted days", "days"),
          ("OUTAGE", "Coal and lignite capacity on outage", "MW")]
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
    try:
        for day in days:
            iso, age = day.isoformat(), (today - day).days
            recent = age <= RECENT_DAYS
            if not recent and (iso in have or (age > RETRY_WINDOW and (iso in missing or iso in problems))): continue
            if time.time() - t0 > budget_s:
                log(f"power: time budget reached after {done} days; the rest continues on the next run"); break
            try:
                path, state = fetch(day, 2, raw, force=recent); streak = 0
            except RuntimeError as e:
                problems[iso] = f"download: {e}"[:160]; skipped += 1; streak += 1
                if streak >= MAX_DOWNLOAD_FAILS:
                    log(f"power: {streak} downloads failed in a row; stopping for this build"); break
                continue
            if state == "missing":
                missing[iso] = today.isoformat(); skipped += 1; pause and time.sleep(pause); continue
            try:
                parsed = parse_dgr2(path)
                if parsed.date != day: raise ValueError(f"file is dated {parsed.date}")
                bad = [r for r in reconcile(parsed) if not r[3]]
                if bad: raise ValueError(f"station sums do not match the file's totals {bad}")
                f_, o_, st, units = aggregate(parsed, owners)
                new_fleet.append(f_); new_owner.append(o_); missing.pop(iso, None); problems.pop(iso, None); done += 1
                if iso == max(have | {iso} | {x["date"].iloc[0] for x in new_fleet}):
                    st.drop(columns=["apr_prog_mu"], errors="ignore").to_csv(os.path.join(folder, "stations_last.csv"), index=False)
                    units.to_csv(os.path.join(folder, "units_last.csv"), index=False)
                    status["last_detail"] = iso
            except Exception as e:                                                   # one bad day must not stop the rest
                problems[iso] = f"{type(e).__name__}: {e}"[:160]; skipped += 1
            finally:
                if path and os.path.exists(path): os.remove(path)
            have.add(iso)
            if done and done % 100 == 0: flush()
            pause and time.sleep(pause)
    finally:
        flush(); shutil.rmtree(raw, ignore_errors=True)
    log(f"power: {done} days loaded, {skipped} missing or failed; {fleet['date'].nunique()} days stored, newest {fleet['date'].max() if len(fleet) else 'none'}")
    return fleet, owner


# ------------------------------------------------------------------ build
def daily_series(fleet):
    """{key: pd.Series indexed by date} for every entry in SERIES."""
    f = fleet.copy(); f["date"] = pd.to_datetime(f["date"])
    out = {"ALL": f.groupby("date")["actual_mu"].sum()}
    th = f[f["fuel"] == "THERMAL"]
    out["THERMAL"] = th.groupby("date")["actual_mu"].sum()
    out["GAS"] = f[f["fuel"] == "THER (GT)"].groupby("date")["actual_mu"].sum()
    out["HYDRO"] = f[(f["fuel"] == "HYDRO") & (f["sector"] != "IMPORT")].groupby("date")["actual_mu"].sum()
    out["NUCLEAR"] = f[f["fuel"] == "NUCLEAR"].groupby("date")["actual_mu"].sum()
    for r in ("NORTHERN", "WESTERN", "SOUTHERN", "EASTERN", "NORTH EASTERN"):
        out[r] = f[f["region"] == r].groupby("date")["actual_mu"].sum()
    g = th.groupby("date").agg(mu=("actual_mu", "sum"), mw=("mw", "sum"), cmw=("coal_mw", "sum"), cmd=("coal_mwdays", "sum"), out=("outage_mw", "sum"))
    out["PLF"] = (g["mu"] * 1000 / (g["mw"] * 24) * 100).where(g["mw"] > 0)
    out["COALDAYS"] = (g["cmd"] / g["cmw"]).where(g["cmw"] > 0)
    out["OUTAGE"] = g["out"]
    return out


def _year(series, year, last):
    arr = heat.year_arrays(pd.DataFrame({"mean": series, "max": series}), year, last)["mean"]
    return [None if v is None else round(v, 1) for v in arr]


def _window(cur, prior, n):
    """Mean of the last n days of `cur` against the same calendar days of `prior`, over days both have."""
    end = len(cur); pairs = [(a, b) for a, b in zip(cur[max(0, end - n):end], prior[max(0, end - n):end]) if a is not None and b is not None]
    if not pairs: return None, None, None
    a, b = float(np.mean([p[0] for p in pairs])), float(np.mean([p[1] for p in pairs]))
    return round(a, 1), round(b, 1), None if not b else round((a / b - 1) * 100, 1)


def owner_rows(owner, last, window=30):
    o = owner.copy(); o["date"] = pd.to_datetime(o["date"])
    lo, ly_lo, ly_hi = last - pd.Timedelta(days=window - 1), last - pd.Timedelta(days=364 + window - 1), last - pd.Timedelta(days=364)
    cur, prev = o[(o["date"] >= lo) & (o["date"] <= last)], o[(o["date"] >= ly_lo) & (o["date"] <= ly_hi)]
    rows = []
    for name, g in cur.groupby("owner"):
        days = g["date"].nunique()
        if name in ("Other", "REVIEW") or days < window // 2: continue
        mu = g["actual_mu"].sum() / days; pg = prev[prev["owner"] == name]
        pdays = pg["date"].nunique(); pmu = pg["actual_mu"].sum() / pdays if pdays >= window // 2 else None
        th = g[g["fuel"] == "THERMAL"]; latest = g[g["date"] == g["date"].max()]; lth = latest[latest["fuel"] == "THERMAL"]
        cm = lth["coal_mw"].sum()
        rows.append(dict(owner=name, symbol=LISTED.get(name), mw=round(float(latest["mw"].sum())), mu=round(float(mu), 1),
                         yoy=None if not pmu else round((mu / pmu - 1) * 100, 1),
                         plf=round(float(th["actual_mu"].sum() * 1000 / (th["mw"].sum() * 24) * 100), 1) if th["mw"].sum() else None,
                         coal=round(float(lth["coal_mwdays"].sum() / cm), 1) if cm else None, outage=round(float(lth["outage_mw"].sum()))))
    return sorted(rows, key=lambda r: -r["mu"])


def build(root, asof=None):
    """Everything the Power view shows, or None when nothing is stored yet."""
    folder = os.path.join(root, "power")
    fleet, owner = _read(os.path.join(folder, "fleet.csv"), FLEET_COLS), _read(os.path.join(folder, "owner.csv"), OWNER_COLS)
    if not len(fleet): return None
    last = pd.Timestamp(fleet["date"].max()); series = daily_series(fleet)
    years = [last.year, last.year - 1, last.year - 2]
    out_series, cards = {}, []
    for key, label, unit in SERIES:
        s = series.get(key)
        if s is None or not len(s): continue
        arrs = {str(y): _year(s, y, last) for y in years}; out_series[key] = dict(label=label, unit=unit, years=arrs)
        cur, p1 = arrs[str(years[0])], arrs[str(years[1])]
        v = cur[-1] if cur and cur[-1] is not None else next((x for x in reversed(cur) if x is not None), None)
        a7, b7, d7 = _window(cur, p1, 7); a30, b30, d30 = _window(cur, p1, 30); ay, by, dy = _window(cur, p1, len(cur))
        cards.append(dict(key=key, label=label, unit=unit, last=v, a7=a7, b7=b7, d7=d7, a30=a30, b30=b30, d30=d30, ytd=ay, dytd=dy))
    detail = os.path.join(folder, "stations_last.csv"); stations = units = []
    if os.path.exists(detail):
        st = pd.read_csv(detail); lastd = str(st["date"].iloc[0]) if len(st) else ""
        th = st[(st["fuel"] == "THERMAL") & (st["mw"] >= 500) & (st["coal_days"].fillna(0) > 0)].sort_values("coal_days").head(15)
        stations = [dict(plant=r.plant, owner=r.owner, state=str(r.state).title(), mw=round(float(r.mw)), coal=round(float(r.coal_days), 1),
                         plf=None if pd.isna(r.plf) else round(float(r.plf), 1), outage=0 if pd.isna(r.outage_mw) else round(float(r.outage_mw)))
                    for r in th.itertuples()]
        up = os.path.join(folder, "units_last.csv")
        if os.path.exists(up):
            u = pd.read_csv(up); u = u[u["outage_mw"].fillna(0) > 0].sort_values("outage_mw", ascending=False).head(15)
            units = [dict(plant=r.plant, unit=str(r.unit), mw=round(float(r.outage_mw)), since=None if pd.isna(r.outage_date) else str(r.outage_date)[:10],
                          back=None if pd.isna(r.expected_return) else str(r.expected_return)[:10], why=None if pd.isna(r.remarks) else str(r.remarks)[:60]) for r in u.itertuples()]
    window = owner[(pd.to_datetime(owner["date"]) > last - pd.Timedelta(days=30))]
    tot = window["actual_mu"].sum() or 1.0
    share = lambda names: round(float(window[window["owner"].isin(names)]["actual_mu"].sum() / tot * 100), 1)
    dates = sorted(fleet["date"].unique())
    return dict(asof=f"{last:%Y-%m-%d}", first=dates[0], n_days=len(dates), years=years, series=out_series, cards=cards,
                owners=owner_rows(owner, last), stations=stations, units=units,
                coverage=dict(other=share(["Other"]), review=share(["REVIEW"])))


def load_and_build(root, asof, log=print, budget_s=None):
    """The one call run.py makes. A failure here never stops the desk publishing."""
    try:
        refresh(root, asof, budget_s=budget_s if budget_s is not None else float(os.environ.get("POWER_BUDGET_S", BUDGET_S)), log=log)
        data = build(root, asof)
        log(f"power: {data['n_days']} days, {data['first']} to {data['asof']}" if data else "power: no data yet; the Power view will say so")
        return data
    except Exception as e:
        log(f"power: skipped ({type(e).__name__}: {e})")
        return None
