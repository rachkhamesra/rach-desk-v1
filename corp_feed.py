"""Bonus issues and splits straight from NSE's corporate-actions feed.

The detector in corp.py works from prices, so it can miss a bonus or split that arrives without an ISIN or lot-size change (a stock outside F&O)
when the day's market move nudges the ratio past its cut-off, or when bonus-news trading makes turnover look like a spike. City Union Bank's 1:3
bonus (ex-date 12 Jun 2026) was missed exactly that way and its chart showed a 21% crash. The exchange publishes the ratio and ex-date, so use it.

The feed is cached in data/corp_feed.csv, refreshed for the recent window on every run, and a failed fetch keeps the cache. Rows come back in the
shape corp.find_events accepts as overrides, marked source "nse" so they are only applied when the price really moved by about the announced ratio.
"""
import os, re
import numpy as np, pandas as pd

ENDPOINT = "/api/corporates-corporateActions"
COLUMNS = ["symbol", "date", "action", "ratio", "note", "source"]
BONUS = re.compile(r"bonus\s+(\d+)\s*:\s*(\d+)", re.I)
SPLIT = re.compile(r"(?:split|sub-?division|consolidation).*?from\s+r[se]\.?\s*([\d.]+).*?to\s+r[se]\.?\s*([\d.]+)", re.I | re.S)
REFRESH_DAYS = 30            # how far back each run re-reads: late corrections and newly announced ex-dates


def factor(subject):
    """Price factor on the ex-date for a bonus or split subject, else None. 'Bonus 1:3' is one new share per three held: the price becomes 3/4."""
    m = BONUS.search(subject or "")
    if m:
        new, held = int(m.group(1)), int(m.group(2))
        return held / (held + new) if new and held else None
    m = SPLIT.search(subject or "")
    if m:
        old, new = float(m.group(1)), float(m.group(2))
        return new / old if old and new and new != old else None
    return None


def rows(raw):
    out = []
    for r in raw or []:
        f = factor(r.get("subject", ""))
        d = pd.to_datetime(r.get("exDate"), format="%d-%b-%Y", errors="coerce")
        if f is None or pd.isna(d) or not r.get("symbol"): continue
        out.append(dict(symbol=str(r["symbol"]).strip(), date=d.normalize(), action="adjust", ratio=float(f), note=f"NSE corporate action: {r['subject'].strip()}, ex-date {r['exDate']}", source="nse"))
    df = pd.DataFrame(out, columns=COLUMNS)
    if len(df):                                           # a split and a bonus often share an ex-date: the price falls by both, so the factors multiply
        df = (df.groupby(["symbol", "date"], as_index=False).agg(action=("action", "first"), ratio=("ratio", "prod"), note=("note", " + ".join), source=("source", "first"))[COLUMNS])
    return df


def load(root, start, end, fetch=None, log=print):
    """The cached feed rows from `start`, after refreshing the recent window. Never raises: on failure the cache is used."""
    path = os.path.join(root, "corp_feed.csv")
    old = pd.read_csv(path, parse_dates=["date"]) if os.path.exists(path) else pd.DataFrame(columns=COLUMNS)
    if fetch is None:
        import results
        fetch = lambda a, b: results._get(ENDPOINT, {"index": "equities", "from_date": f"{a:%d-%m-%Y}", "to_date": f"{b:%d-%m-%Y}"})
    first = pd.Timestamp(start) if not len(old) else max(pd.Timestamp(start), pd.Timestamp(end) - pd.Timedelta(days=REFRESH_DAYS))
    try:
        fresh = rows(fetch(first, pd.Timestamp(end) + pd.Timedelta(days=45)))        # announced ex-dates a little ahead are harmless: they only apply once the price has moved
        if len(fresh):
            old = pd.concat([old, fresh], ignore_index=True).drop_duplicates(["symbol", "date", "ratio"], keep="last")
            os.makedirs(root, exist_ok=True); old.to_csv(path, index=False, date_format="%Y-%m-%d")
    except Exception as e:
        log(f"corporate-action feed not refreshed ({type(e).__name__}); using the cached copy of {len(old)} rows")
    return old[old["date"] >= pd.Timestamp(start)].reset_index(drop=True)
