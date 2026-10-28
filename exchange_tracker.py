"""BSE exchange-activity history and the derived dashboard snapshot."""
from __future__ import annotations

import os
import time
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import requests


API = "https://api.bseindia.com/BseIndiaAPI/api/Mkt_Keystat_turnover_deri_daily_par_beta/w"
CACHE = "bse_premium_turnover.csv"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://www.bseindia.com",
    "referer": "https://www.bseindia.com/",
    "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
}


def _month_starts(end):
    return pd.date_range("2025-01-01", pd.Timestamp(end).replace(day=1), freq="MS")


def fetch_month(month, session=None, attempts=3):
    """Download one calendar month from the endpoint used by BSE's Key Statistics page."""
    month = pd.Timestamp(month); session = session or requests.Session()
    url = API + "?" + urlencode({"YY": month.year, "MM": month.month, "type": "T"})
    error = None
    for attempt in range(attempts):
        try:
            response = session.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            rows = response.json().get("Table", [])
            out = pd.DataFrame(rows)
            if out.empty: return pd.DataFrame(columns=["date", "premium_turnover_cr"])
            out = out.rename(columns={"DT_TM": "date", "Avg_Op_turnover": "premium_turnover_cr"})
            out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
            out["premium_turnover_cr"] = pd.to_numeric(out["premium_turnover_cr"], errors="coerce")
            return out[["date", "premium_turnover_cr"]].dropna().drop_duplicates("date")
        except Exception as exc:
            error = exc
            if attempt + 1 < attempts: time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"BSE premium-turnover download failed for {month:%b %Y}: {error}")


def load(root, end, refresh=True):
    """Read the cache, backfill missing months from Jan-2025, and refresh the current month."""
    path = os.path.join(root, CACHE)
    if os.path.exists(path):
        cached = pd.read_csv(path, parse_dates=["date"])
    else:
        cached = pd.DataFrame(columns=["date", "premium_turnover_cr"])
    cached["date"] = pd.to_datetime(cached.get("date"), errors="coerce").dt.normalize()
    cached = cached.dropna(subset=["date"]).drop_duplicates("date", keep="last")
    if not refresh:
        return cached.sort_values("date").reset_index(drop=True)

    end = pd.Timestamp(end).normalize(); have = set(cached["date"].dt.to_period("M"))
    wanted = list(_month_starts(end)); current = end.to_period("M")
    todo = [m for m in wanted if m.to_period("M") not in have or m.to_period("M") == current]
    additions = []
    with requests.Session() as session:
        for month in todo:
            try:
                additions.append(fetch_month(month, session=session))
            except Exception as exc:
                print(f"warning: {exc}; retaining cached BSE exchange data")
    if additions:
        cached = pd.concat([cached] + additions, ignore_index=True)
        cached = cached.dropna().drop_duplicates("date", keep="last").sort_values("date")
        os.makedirs(root, exist_ok=True)
        cached.to_csv(path, index=False, date_format="%Y-%m-%d")
    return cached[cached["date"] <= end].sort_values("date").reset_index(drop=True)


def _change(now, before):
    return (now / before - 1) * 100 if pd.notna(now) and pd.notna(before) and before else np.nan


def build(history, prices):
    """Create chart series, comparisons and factual rule-based commentary."""
    if history is None or history.empty:
        return {"available": False, "commentary": ["BSE premium-turnover history is not available yet."]}
    h = history.copy().sort_values("date").drop_duplicates("date")
    h["roll5"] = h["premium_turnover_cr"].rolling(5, min_periods=3).mean()
    price = pd.Series(prices).copy(); price.index = pd.to_datetime(price.index).normalize()
    h["price"] = h["date"].map(price)
    h["weekday"] = h["date"].dt.day_name()
    last = h.iloc[-1]; weekday = last.weekday
    same = h[h["weekday"] == weekday].tail(13).copy()
    prior_same = same.iloc[:-1]["premium_turnover_cr"]
    weekday_median = prior_same.median() if len(prior_same) else np.nan

    monthly = (h.assign(month=h["date"].dt.to_period("M"))
                 .groupby("month")["premium_turnover_cr"].agg(mean="mean", count="count").reset_index())
    monthly["month"] = monthly["month"].astype(str)
    m_now = monthly.iloc[-1]; m_prev = monthly.iloc[-2] if len(monthly) > 1 else None
    roll_now = last.roll5; roll_prev = h.roll5.iloc[-6] if len(h) >= 6 else np.nan
    c = []
    if pd.notna(roll_now):
        c.append(f"The 5-session average is ₹{roll_now:,.0f} cr, {_change(roll_now, roll_prev):+.0f}% versus five sessions ago." if pd.notna(roll_prev)
                 else f"The 5-session average is ₹{roll_now:,.0f} cr.")
    if pd.notna(weekday_median):
        c.append(f"The latest {weekday} turnover of ₹{last.premium_turnover_cr:,.0f} cr is {_change(last.premium_turnover_cr, weekday_median):+.0f}% versus the median of the prior {len(prior_same)} {weekday}s.")
    if m_prev is not None:
        rank = int((monthly["mean"] <= m_now["mean"]).sum())
        c.append(f"{pd.Timestamp(m_now['month'] + '-01'):%B} is running at ₹{m_now['mean']:,.0f} cr per session ({int(m_now['count'])} sessions), {_change(m_now['mean'], m_prev['mean']):+.0f}% versus {pd.Timestamp(m_prev['month'] + '-01'):%B}; rank {rank} of {len(monthly)} months since January 2025.")
    return {
        "available": True,
        "asof": last.date,
        "latest": float(last.premium_turnover_cr),
        "weekday": weekday,
        "series": h[["date", "premium_turnover_cr", "roll5", "price"]].tail(420),
        "same_weekday": same[["date", "premium_turnover_cr"]],
        "monthly": monthly.tail(24),
        "commentary": c,
        "source": "https://www.bseindia.com/markets/keystatics/keystat_turnover_deri",
    }
