"""Alternative data: how hot each major city is running against its own history (experimental).

Daily temperatures come from the Open-Meteo archive (ERA5 reanalysis, model grid cells, not station
readings, about five days behind). Everything is measured against each city's 1991-2020 normal and against
the same dates in the two previous years. Cities live in config/cities.json. Nothing here is a forecast.
"""
import json, os, re, time
from datetime import timedelta

import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CITIES_FILE = os.path.join(HERE, "config", "cities.json")
API = "https://archive-api.open-meteo.com/v1/archive"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
FIRST_YEAR, BASE_FIRST, BASE_LAST = 1991, 1991, 2020
LAG_DAYS, REFRESH_DAYS, PAUSE_S = 6, 40, 2.0
REGIONS = ("North", "East", "West", "South")
SEASONS = {"summer": dict(label="Cooling season (Mar–Jun)", start_month=3, months=(3, 4, 5, 6), length=122),
           "winter": dict(label="Heating season (Dec–Feb)", start_month=12, months=(12, 1, 2), length=91)}
HOT_DAY_C = 40.0
ONI_CENTRE_MONTH = dict(DJF=1, JFM=2, FMA=3, MAM=4, AMJ=5, MJJ=6, JJA=7, JAS=8, ASO=9, SON=10, OND=11, NDJ=12)


def load_cities(path=CITIES_FILE):
    with open(path, encoding="utf-8") as f: cities = json.load(f)["cities"]
    for c in cities:
        if c["region"] not in REGIONS: raise ValueError(f"{c['name']}: region must be one of {REGIONS}")
    return cities


def slug(name): return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ------------------------------------------------------------------ fetching
def fetch_city(city, start, end, session=None, log=print, sleep=time.sleep):
    """Daily mean and max temperature for one city; backs off on rate limits and server errors."""
    s = session or requests
    params = dict(latitude=city["lat"], longitude=city["lon"], start_date=f"{start:%Y-%m-%d}", end_date=f"{end:%Y-%m-%d}",
                  daily="temperature_2m_mean,temperature_2m_max", timezone="Asia/Kolkata")
    for wait in (0, 15, 30, 45):
        sleep(wait)
        try:
            r = s.get(API, params=params, timeout=90)
            if r.status_code == 200:
                d = r.json()["daily"]
                return pd.DataFrame({"mean": d["temperature_2m_mean"], "max": d["temperature_2m_max"]},
                                    index=pd.to_datetime(d["time"])).astype(float)
            log(f"  {city['name']}: HTTP {r.status_code}, retrying" if r.status_code in (429, 500, 502, 503, 504) else f"  {city['name']}: HTTP {r.status_code}")
            if r.status_code not in (429, 500, 502, 503, 504): break
        except (requests.RequestException, ValueError, KeyError) as e:
            log(f"  {city['name']}: {type(e).__name__}, retrying")
    return None


def refresh(root, asof, cities=None, log=print, fetcher=fetch_city, sleep=time.sleep):
    """Update data/heat/<city>.csv and return {city name: DataFrame}. A failure for one city keeps its cache."""
    cities = cities or load_cities()
    folder = os.path.join(root, "heat"); os.makedirs(folder, exist_ok=True)
    meta_path = os.path.join(folder, "_fetched.json")
    try:
        with open(meta_path) as f: meta = json.load(f)
    except (OSError, ValueError):
        meta = {}
    end = pd.Timestamp(asof).normalize() - timedelta(days=LAG_DAYS)
    frames, today = {}, f"{pd.Timestamp(asof):%Y-%m-%d}"
    for i, c in enumerate(cities):
        path = os.path.join(folder, slug(c["name"]) + ".csv")
        old = pd.read_csv(path, index_col=0, parse_dates=True) if os.path.exists(path) else None
        if old is not None and meta.get(c["name"]) == today:
            frames[c["name"]] = old; continue                              # already refreshed today
        start = pd.Timestamp(f"{FIRST_YEAR}-01-01") if old is None or not len(old) else max(old.index.min(), end - timedelta(days=REFRESH_DAYS))
        if i: sleep(PAUSE_S)
        new = fetcher(c, start, end, log=log)
        if new is None:
            log(f"heat: {c['name']} not refreshed; keeping its last good data")
            if old is not None: frames[c["name"]] = old
            continue
        df = new if old is None else pd.concat([old[old.index < new.index.min()], new]).sort_index()
        df.to_csv(path); meta[c["name"]] = today; frames[c["name"]] = df
    with open(meta_path, "w") as f: json.dump(meta, f)
    return frames


def fetch_oni(root, log=print):
    """{'YYYY-MM': anomaly} from NOAA CPC, centred on the middle month of each 3-month season; cached."""
    path = os.path.join(root, "heat", "oni.txt"); os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        r = requests.get(ONI_URL, timeout=60); r.raise_for_status()
        text = r.text; open(path, "w").write(text)
    except requests.RequestException as e:
        log(f"heat: ONI download failed ({type(e).__name__}); using cached copy" if os.path.exists(path) else f"heat: ONI unavailable ({type(e).__name__})")
        text = open(path).read() if os.path.exists(path) else ""
    return parse_oni(text)


def parse_oni(text):
    out = {}
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 4 and p[0] in ONI_CENTRE_MONTH:
            try: out[f"{int(p[1])}-{ONI_CENTRE_MONTH[p[0]]:02d}"] = float(p[3])
            except ValueError: pass
    return out


# ------------------------------------------------------------------ calculations
NON_LEAP = pd.date_range("2001-01-01", "2001-12-31")           # a fixed 365-day calendar to align every year on


def drop_feb29(df): return df[~((df.index.month == 2) & (df.index.day == 29))]


def doy365(index):
    """Position 0-364 of each date in a 365-day year (Feb 29 must already be removed)."""
    lookup = {(d.month, d.day): i for i, d in enumerate(NON_LEAP)}
    return np.array([lookup[(d.month, d.day)] for d in index])


def daily_normal(df):
    """1991-2020 mean of the daily mean for each calendar day, smoothed over 15 days around the year end."""
    base = drop_feb29(df[(df.index.year >= BASE_FIRST) & (df.index.year <= BASE_LAST)])
    raw = np.full(365, np.nan)
    pos = doy365(base.index)
    for k in range(365):
        v = base["mean"].to_numpy()[pos == k]; v = v[~np.isnan(v)]
        if len(v): raw[k] = v.mean()
    pad = np.concatenate([raw[-7:], raw, raw[:7]])
    return np.array([np.nanmean(pad[i:i + 15]) for i in range(365)])


def monthly(df):
    g = df["mean"].groupby([df.index.year, df.index.month]).agg(["mean", "count"])
    return g[g["count"] >= 20]["mean"]


def month_baseline(m):
    b = m[(m.index.get_level_values(0) >= BASE_FIRST) & (m.index.get_level_values(0) <= BASE_LAST)]
    return b.groupby(level=1).mean()


def year_arrays(df, year, last):
    """Daily mean and max for one calendar year on the 365-day calendar, None where missing, ending at `last`."""
    d = drop_feb29(df[df.index.year == year])
    n = 365
    if year == last.year:
        d = d[d.index <= last]
        n = 59 if (last.month == 2 and last.day == 29) else int(doy365([last])[0]) + 1
    out = {}
    for col in ("mean", "max"):
        arr = [None] * n
        for i, v in zip(doy365(d.index), d[col].to_numpy()):
            if i < n and not np.isnan(v): arr[i] = round(float(v), 1)
        out[col] = arr
    return out


def matched(cur, other):
    """Compare two year arrays over the same days (Jan 1 to the current year's last day): mean gap and share of warmer days."""
    pairs = [(a, b) for a, b in zip(cur, other) if a is not None and b is not None]
    if not pairs: return None, None
    gap = float(np.mean([a - b for a, b in pairs])); warmer = 100 * float(np.mean([a > b for a, b in pairs]))
    return round(gap, 2), round(warmer)


def season_instance(df, key, start_year, clip_to=None):
    """Mean temperature, mean max and hot days for one season; `clip_to` keeps only the first N days of the season."""
    cfg = SEASONS[key]; s = pd.Timestamp(year=start_year, month=cfg["start_month"], day=1)
    e = s + pd.DateOffset(months=len(cfg["months"])) - pd.Timedelta(days=1)
    d = df[(df.index >= s) & (df.index <= e)].copy()
    d = d[(d.index - s).days < (clip_to if clip_to is not None else cfg["length"])]
    d = d.dropna(subset=["mean"])
    if len(d) < 10: return None
    return dict(mean=float(d["mean"].mean()), max=float(d["max"].mean()), hot=int((d["max"] >= HOT_DAY_C).sum()), n=int(len(d)))


def season_read(df, key, last):
    """Latest season instance (finished or in progress) against the previous year's and the 1991-2020 normal, over the same days."""
    cfg = SEASONS[key]
    start = last.year if (last.month == 12 if key == "winter" else last.month >= 3) else last.year - 1
    cur = season_instance(df, key, start)
    if cur is None: return None
    n = cur["n"]; prev = season_instance(df, key, start - 1, clip_to=n)
    norm = [x for x in (season_instance(df, key, y, clip_to=n) for y in range(BASE_FIRST, BASE_LAST + (0 if key == "winter" else 1))) if x]
    label = f"{start}–{str(start + 1)[2:]}" if key == "winter" else str(start)
    prev_label = f"{start - 1}–{str(start)[2:]}" if key == "winter" else str(start - 1)
    return dict(label=label, prev_label=prev_label, partial=n < cfg["length"] - 2, days=n,
                mean=cur["mean"], max=cur["max"], hot=cur["hot"],
                d_prev=None if prev is None else cur["mean"] - prev["mean"], max_prev=None if prev is None else cur["max"] - prev["max"],
                hot_prev=None if prev is None else cur["hot"] - prev["hot"],
                d_norm=None if not norm else cur["mean"] - float(np.mean([x["mean"] for x in norm])))


def build_city(df, city):
    df = df.sort_index(); df = df[~df.index.duplicated(keep="last")]
    last = df.dropna(subset=["mean"]).index.max()
    normal = daily_normal(df); m = monthly(df); mb = month_baseline(m)
    anom = {f"{y}-{mo:02d}": round(float(v - mb[mo]), 2) for (y, mo), v in m.items() if mo in mb.index and y >= last.year - 2}
    this_year = [v for k, v in anom.items() if k.startswith(str(last.year))]
    ytd = round(float(np.mean(this_year)), 2) if this_year else None
    recent = drop_feb29(df[df.index > last - timedelta(days=30)]).dropna(subset=["mean"])
    last30 = round(float(np.mean(recent["mean"].to_numpy() - normal[doy365(recent.index)])), 2) if len(recent) else None
    recent_years = df[df.index.year >= 2000]
    hot = {str(y): int((g["max"] >= HOT_DAY_C).sum()) for y, g in recent_years.groupby(recent_years.index.year)}
    years = {str(y): year_arrays(df, y, last) for y in (last.year, last.year - 1, last.year - 2)}
    cur = years[str(last.year)]
    cmp = {}
    for yr, tag in ((last.year - 1, "p1"), (last.year - 2, "p2")):
        gap, warmer = matched(cur["mean"], years[str(yr)]["mean"]); cmp[tag] = dict(year=yr, gap=gap, warmer=warmer)
    return dict(name=city["name"], state=city["state"], region=city["region"], lat=city["lat"], lon=city["lon"], last=f"{last:%Y-%m-%d}",
                ytd=ytd, last30=last30, anom=anom, hot=hot, cmp=cmp, years=years,
                seasons={k: season_read(df, k, last) for k in SEASONS},
                grid=[None if f"{p.year}-{p.month:02d}" not in anom else anom[f"{p.year}-{p.month:02d}"] for p in pd.period_range(end=pd.Period(last, "M"), periods=18, freq="M")])


def _mean(values):
    v = [x for x in values if x is not None]
    return None if not v else round(float(np.mean(v)), 2)


def build(frames, oni=None, asof=None, cities=None):
    """Everything the Alternative Data tab shows, or None when no city has data."""
    cities = cities or load_cities()
    built = [build_city(frames[c["name"]], c) for c in cities if c["name"] in frames and len(frames[c["name"]].dropna(subset=["mean"])) > 365 * 5]
    if not built: return None
    last = max(pd.Timestamp(c["last"]) for c in built)
    def region(group):
        out = dict(n=len(group), ytd=_mean(c["ytd"] for c in group), last30=_mean(c["last30"] for c in group),
                   p1=_mean(c["cmp"]["p1"]["gap"] for c in group), p2=_mean(c["cmp"]["p2"]["gap"] for c in group),
                   w1=_mean(c["cmp"]["p1"]["warmer"] for c in group), w2=_mean(c["cmp"]["p2"]["warmer"] for c in group), seasons={})
        for k in SEASONS:
            rows = [c["seasons"][k] for c in group if c["seasons"].get(k)]
            if rows:
                out["seasons"][k] = dict(label=rows[0]["label"], prev_label=rows[0]["prev_label"], partial=rows[0]["partial"], days=rows[0]["days"],
                                         **{f: _mean(r[f] for r in rows) for f in ("mean", "max", "hot", "d_prev", "max_prev", "hot_prev", "d_norm")})
        return out
    regions = {r: region([c for c in built if c["region"] == r]) for r in REGIONS if any(c["region"] == r for c in built)}
    oni = oni or {}
    months = [f"{p.year}-{p.month:02d}" for p in pd.period_range(end=pd.Period(last, "M"), periods=18, freq="M")]
    return dict(asof=f"{last:%Y-%m-%d}", months=months, years=[last.year, last.year - 1, last.year - 2],
                oni={k: oni[k] for k in sorted(oni)[-6:]}, regions=regions, all=region(built), cities=built,
                season_labels={k: v["label"] for k, v in SEASONS.items()})


def load_and_build(root, asof, log=print):
    """The one call run.py makes. Any failure leaves the rest of the site untouched."""
    try:
        frames = refresh(root, asof, log=log)
        data = build(frames, fetch_oni(root, log=log), asof)
        if data: log(f"heat: {len(data['cities'])} cities, through {data['asof']}")
        else: log("heat: no city data yet; the Alternative Data tab will say so")
        return data
    except Exception as e:                                                  # an experimental tab must never stop the desk publishing
        log(f"heat: skipped ({type(e).__name__}: {e})")
        return None
