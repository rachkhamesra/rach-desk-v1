"""IEX day-ahead market (DAM) prices and volumes, the exchange "merchant" power price, from iexindia.com.

The Market Snapshot page serves a daily table for any date range of up to 31 days (from 1 Apr 2022):
purchase bid, sell bid, cleared volume (MCV), scheduled volume, the simple average market clearing price (MCP)
and the volume-weighted MCP, in Rs/MWh and MWh. Nothing here is an API: it reads that page's HTML table, so a
layout change makes the parse fail loudly (no rows) and the last good data is kept.
"""
import calendar, json, os, re, time

import pandas as pd
import requests

URL = "https://www.iexindia.com/market-data/day-ahead-market/market-snapshot"
UA = "Mozilla/5.0 (compatible; rach-desk-research/1.0)"
FIRST_DAY = pd.Timestamp("2023-01-01")
COLUMNS = ["date", "purchase_bid_mwh", "sell_bid_mwh", "mcv_mwh", "scheduled_mwh", "mcp", "wmcp"]
HEADS = ["Date", "Purchase Bid (MWh)", "Sell Bid (MWh)", "MCV (MWh)", "Final Scheduled Volume (MWh)", "MCP (Rs/MWh) *", "Weighted MCP (Rs/MWh)"]
BUDGET_S, PAUSE_S, MAX_FAILS = 150, 1.0, 2


def parse(html):
    """DataFrame of daily DAM rows from the snapshot page, or an empty frame when the table is not there."""
    for t in re.findall(r"<table.*?</table>", html, flags=re.S):
        heads = [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", t, flags=re.S)]
        if heads[:7] != HEADS: continue
        rows = []
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S):
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", r, flags=re.S)]
            if len(cells) < 7 or not re.fullmatch(r"\d{2}-\d{2}-\d{4}", cells[0]): continue
            try: rows.append([pd.to_datetime(cells[0], format="%d-%m-%Y")] + [float(c.replace(",", "")) for c in cells[1:7]])
            except ValueError: continue
        return pd.DataFrame(rows, columns=COLUMNS)
    return pd.DataFrame(columns=COLUMNS)


def fetch_range(start, end, session=None, log=print):
    """One request: the daily table from start to end (at most 31 days). None when IEX does not answer sensibly."""
    s = session or requests
    params = dict(interval="DAILY", dp="SELECT_RANGE", showGraph="false", fromDate=f"{start:%d-%m-%Y}", toDate=f"{end:%d-%m-%Y}")
    for attempt in range(2):
        try:
            r = s.get(URL, params=params, headers={"User-Agent": UA}, timeout=40)
            if r.status_code == 200:
                df = parse(r.text)
                if len(df): return df
                log(f"iex: no table for {start:%d %b %Y} to {end:%d %b %Y}")
                return None
            log(f"iex: HTTP {r.status_code} for {start:%b %Y}")
        except requests.RequestException as e:
            log(f"iex: {type(e).__name__} for {start:%b %Y}")
        time.sleep(3)
    return None


def month_ranges(first, last):
    """Calendar-month (start, end) pairs from `first` to `last`, newest first."""
    out, cur = [], pd.Timestamp(year=last.year, month=last.month, day=1)
    while cur >= pd.Timestamp(year=first.year, month=first.month, day=1):
        end = min(pd.Timestamp(year=cur.year, month=cur.month, day=calendar.monthrange(cur.year, cur.month)[1]), last)
        out.append((max(cur, first), end)); cur = cur - pd.offsets.MonthBegin(1)
    return out


def refresh(root, today, start=FIRST_DAY, budget_s=BUDGET_S, log=print, fetch=fetch_range, pause=PAUSE_S, clock=time.time):
    """Bring data/power/iex_dam.csv up to date. The two newest months are fetched again once a day; older months only when incomplete."""
    folder = os.path.join(root, "power"); os.makedirs(folder, exist_ok=True)
    path, meta_path = os.path.join(folder, "iex_dam.csv"), os.path.join(folder, "iex_meta.json")
    old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=COLUMNS)
    old["date"] = pd.to_datetime(old["date"])
    try:
        with open(meta_path) as f: meta = json.load(f)
    except (OSError, ValueError):
        meta = {}
    today = pd.Timestamp(today).normalize(); have = old.groupby(old["date"].dt.to_period("M")).size().to_dict()
    t0, fails, got, frames = clock(), 0, 0, []
    for k, (a, b) in enumerate(month_ranges(start, today)):
        full = have.get(a.to_period("M"), 0) >= (b - a).days + 1
        if full and not (k < 2 and meta.get("fetched") != f"{today:%Y-%m-%d}"): continue
        if clock() - t0 > budget_s: log("iex: time budget reached; the rest continues on the next run"); break
        if fails >= MAX_FAILS: log("iex: stopping after repeated failures"); break
        if got: pause and time.sleep(pause)
        df = fetch(a, b, log=log)
        if df is None: fails += 1; continue
        fails = 0; got += 1; frames.append(df[(df["date"] >= a) & (df["date"] <= b)])
    if frames:
        new = pd.concat(frames); old = pd.concat([old[~old["date"].isin(new["date"])], new]).sort_values("date").reset_index(drop=True)
        old.to_csv(path, index=False, date_format="%Y-%m-%d")
        if not fails: meta["fetched"] = f"{today:%Y-%m-%d}"
        with open(meta_path, "w") as f: json.dump(meta, f)
    log(f"iex: {got} months fetched; {len(old)} days stored" + (f", newest {old['date'].max():%Y-%m-%d}" if len(old) else ""))
    return old
