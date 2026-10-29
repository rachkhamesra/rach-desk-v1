"""MCX options-premium history, expiry calendar and dashboard snapshot."""
from __future__ import annotations

import html as html_lib
import json
import os
import re

import numpy as np
import pandas as pd
import requests


CACHE = "mcx_turnover.csv"
HISTORY_URL = "https://www.mcxindia.com/backpage.aspx/GetHistoricalDataDetails"
HISTORY_PAGE = "https://www.mcxindia.com/market-data/historical-data"
EXPIRY_URL = "https://groww.in/commodities/calendar?instrument=OPTIONS&exchange=MCX"
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json",
    "Origin": "https://www.mcxindia.com",
    "Referer": HISTORY_PAGE,
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
}
SYMBOL_NAMES = {
    "CRUDEOIL": "Crude Oil", "CRUDEOILM": "Crude Oil Mini",
    "NATURALGAS": "Natural Gas", "NATGASMINI": "Natural Gas Mini",
    "GOLD": "Gold", "GOLDM": "Gold Mini", "GOLDGUINEA": "Gold Guinea",
    "GOLDPETAL": "Gold Petal", "GOLDTEN": "Gold Ten",
    "SILVER": "Silver", "SILVERM": "Silver Mini", "SILVERMIC": "Silver Micro",
    "COPPER": "Copper", "ALUMINIUM": "Aluminium", "ZINC": "Zinc", "LEAD": "Lead",
}


def _column(frame, *candidates):
    normal = {re.sub(r"[^a-z0-9]", "", str(c).lower()): c for c in frame.columns}
    for candidate in candidates:
        key = re.sub(r"[^a-z0-9]", "", candidate.lower())
        if key in normal:
            return normal[key]
    return None


def fetch_history(start, end, session=None):
    """Read MCX's public date-wise summary endpoint (maximum 365 days)."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    payload = {"GroupBy": "D", "Segment": "ALL", "CommodityHead": "ALL", "Commodity": "ALL",
               "Startdate": f"{start:%Y%m%d}", "EndDate": f"{end:%Y%m%d}", "InstrumentName": "ALL"}
    session = session or requests.Session()
    response = session.post(HISTORY_URL, headers=HEADERS, json=payload, timeout=45)
    response.raise_for_status()
    rows = response.json().get("d", {}).get("Data", [])
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["date", "premium_value_lakh", "futures_notional_lakh"])
    instrument = _column(frame, "Instrument", "InstrumentName")
    date = _column(frame, "Date", "TradingDate")
    premium = _column(frame, "PremiumValue", "PremiumValueLakhs", "Premium Value (Lakhs)")
    total = _column(frame, "TotalValue", "TotalValueLakhs", "Total Value (Lakhs)")
    if not instrument or not date:
        raise ValueError(f"MCX response columns changed: {list(frame.columns)}")
    frame[date] = pd.to_datetime(frame[date], errors="coerce", dayfirst=True).dt.normalize()
    frame["_premium"] = pd.to_numeric(frame[premium], errors="coerce") if premium else np.nan
    frame["_total"] = pd.to_numeric(frame[total], errors="coerce") if total else np.nan
    op = frame[frame[instrument].astype(str).str.upper() == "OPTFUT"].groupby(date)["_premium"].sum(min_count=1)
    fu = frame[frame[instrument].astype(str).str.upper() == "FUTCOM"].groupby(date)["_total"].sum(min_count=1)
    return pd.concat([op.rename("premium_value_lakh"), fu.rename("futures_notional_lakh")], axis=1).reset_index(names="date").dropna(subset=["date"])


def fetch_expiries(session=None):
    """Parse the structured expiry map embedded in Groww's public MCX options calendar."""
    session = session or requests.Session()
    response = session.get(EXPIRY_URL, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=45)
    response.raise_for_status()
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', response.text, re.S)
    if not match:
        raise ValueError("Groww expiry calendar no longer exposes __NEXT_DATA__")
    page = json.loads(html_lib.unescape(match.group(1)))
    date_map = page.get("props", {}).get("pageProps", {}).get("dateExpiryMap", {})
    rows = []
    for date, contracts in date_map.items():
        for contract in contracts:
            symbol = str(contract.get("symbol") or "").upper()
            rows.append({"date": pd.Timestamp(date), "symbol": symbol, "name": SYMBOL_NAMES.get(symbol, symbol.title())})
    return pd.DataFrame(rows, columns=["date", "symbol", "name"]).drop_duplicates()


def load(root, end, log=print):
    """Refresh the official MCX summary when accessible and preserve the last good cache."""
    path = os.path.join(root, CACHE)
    cached = pd.read_csv(path, parse_dates=["date"]) if os.path.exists(path) else pd.DataFrame(columns=["date", "premium_value_lakh", "futures_notional_lakh"])
    cached["date"] = pd.to_datetime(cached.get("date"), errors="coerce").dt.normalize()
    cached = cached.dropna(subset=["date"]).drop_duplicates("date", keep="last")
    end = pd.Timestamp(end).normalize()
    status = "MCX history cache loaded"
    try:
        start = max(pd.Timestamp("2024-09-01"), end - pd.Timedelta(days=30))
        fresh = fetch_history(start, end)
        if len(fresh):
            cached = pd.concat([cached, fresh], ignore_index=True).drop_duplicates("date", keep="last").sort_values("date")
            os.makedirs(root, exist_ok=True)
            cached.to_csv(path, index=False, date_format="%Y-%m-%d")
            status = f"Official MCX history refreshed through {cached.date.max():%d %b %Y}"
    except Exception as exc:
        status = f"MCX refresh blocked ({type(exc).__name__}); showing last verified official report"
        log(status)
    try:
        expiries = fetch_expiries()
    except Exception as exc:
        expiries = pd.DataFrame(columns=["date", "symbol", "name"])
        log(f"MCX expiry refresh failed ({exc})")
    return cached[cached.date <= end].sort_values("date").reset_index(drop=True), expiries, status


def _change(now, before):
    return (now / before - 1) * 100 if pd.notna(now) and pd.notna(before) and before else np.nan


def month_week(day):
    """User-defined monthly buckets: 1–8, 9–16, 17–24 and 25–month-end."""
    day = int(day)
    return 1 if day <= 8 else 2 if day <= 16 else 3 if day <= 24 else 4


def build(history, prices, expiries=None, asof=None, update_status=""):
    if history is None or history.empty:
        return {"available": False, "commentary": ["MCX premium-turnover history is not available yet."], "update_status": update_status}
    h = history.copy().sort_values("date").drop_duplicates("date")
    h["premium_turnover_cr"] = pd.to_numeric(h["premium_value_lakh"], errors="coerce") / 100
    h = h.dropna(subset=["premium_turnover_cr"])
    h["roll5"] = h.premium_turnover_cr.rolling(5, min_periods=3).mean()
    price = pd.Series(prices).copy(); price.index = pd.to_datetime(price.index).normalize()
    h["price"] = h.date.map(price); h["weekday"] = h.date.dt.day_name(); h["month_week"] = h.date.dt.day.map(month_week)
    last = h.iloc[-1]; weekday = last.weekday; bucket = month_week(last.date.day)
    bucket_ranges = {1: "1–8", 2: "9–16", 3: "17–24", 4: "25–MONTH END"}
    same_bucket = h[h.month_week == bucket].copy()
    comparison = (same_bucket.assign(month=same_bucket.date.dt.to_period("M"))
                   .groupby("month").premium_turnover_cr.agg(premium_turnover_cr="mean", count="count").reset_index())
    comparison["date"] = comparison.month.dt.to_timestamp()
    current_bucket = comparison.iloc[-1].premium_turnover_cr
    prior_bucket = comparison.iloc[:-1].premium_turnover_cr
    prior_bucket_avg = prior_bucket.mean() if len(prior_bucket) else np.nan
    monthly = h.assign(month=h.date.dt.to_period("M")).groupby("month").premium_turnover_cr.agg(mean="mean", count="count").reset_index()
    monthly["month"] = monthly.month.astype(str); now = monthly.iloc[-1]; prev = monthly.iloc[-2] if len(monthly) > 1 else None
    roll_now = last.roll5; roll_prev = h.roll5.iloc[-6] if len(h) >= 6 else np.nan
    comments = []
    if pd.notna(roll_now):
        comments.append(f"The 5-session average is ₹{roll_now:,.0f} cr, {_change(roll_now, roll_prev):+.0f}% versus five sessions ago." if pd.notna(roll_prev) else f"The 5-session average is ₹{roll_now:,.0f} cr.")
    if pd.notna(prior_bucket_avg):
        comments.append(f"Week {bucket} ({bucket_ranges[bucket]}) is averaging ₹{current_bucket:,.0f} cr per session so far, {_change(current_bucket, prior_bucket_avg):+.0f}% versus the average Week {bucket} across the prior {len(prior_bucket)} months.")
    if prev is not None:
        comments.append(f"{pd.Timestamp(now['month'] + '-01'):%B} is running at ₹{now['mean']:,.0f} cr per session ({int(now['count'])} sessions), {_change(now['mean'], prev['mean']):+.0f}% versus {pd.Timestamp(prev['month'] + '-01'):%B}.")
    ref = pd.Timestamp(asof or last.date).normalize()
    if expiries is not None and len(expiries):
        upcoming = expiries[(expiries.date >= ref) & (expiries.date <= ref + pd.Timedelta(days=45))].sort_values(["date", "name"])
        for date, group in upcoming.groupby("date"):
            days = (pd.Timestamp(date) - ref).days
            when = "today" if days == 0 else f"in {days}D"
            comments.append(f"{', '.join(group.name.tolist())} options expiry {when} ({pd.Timestamp(date):%d %b}).")
    return {"available": True, "asof": last.date, "latest": float(last.premium_turnover_cr), "weekday": weekday,
            "series": h[["date", "premium_turnover_cr", "roll5", "price"]],
            "comparison": comparison[["date", "premium_turnover_cr", "count"]],
            "comparison_title": f"WEEK {bucket} · {bucket_ranges[bucket]} · BY MONTH",
            "comparison_count_label": "MONTHS",
            "comparison_annotation": "VS PRIOR BUCKET AVG",
            "comparison_month_axis": False,
            "monthly": monthly.tail(24), "commentary": comments, "source": HISTORY_PAGE, "source_label": "MCX HISTORICAL DATA",
            "price_label": "MCX price", "update_status": update_status}
