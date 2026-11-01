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


def parse_official_summary_row(cells, expected_date):
    """Validate one rendered MCX OPTFUT summary row and return its published premium value."""
    if len(cells) < 5 or str(cells[0]).strip().upper() != "OPTFUT":
        raise ValueError("not an MCX OPTFUT summary row")
    date = pd.to_datetime(str(cells[1]).strip(), dayfirst=True, errors="coerce")
    expected = pd.Timestamp(expected_date).normalize()
    if pd.isna(date) or date.normalize() != expected:
        raise ValueError(f"MCX summary returned {cells[1]!r}, expected {expected:%d %b %Y}")
    premium = pd.to_numeric(str(cells[4]).replace(",", "").strip(), errors="coerce")
    if pd.isna(premium) or premium <= 0:
        raise ValueError("MCX summary premium value is missing or invalid")
    return {"date": expected, "premium_value_lakh": float(premium), "futures_notional_lakh": np.nan}


def fetch_official_summaries(dates, timeout=35):
    """Read exchange-reported OPTFUT premium values from MCX's rendered Historical Data page.

    This deliberately uses the official Summary Report UI only. It does not estimate premium
    turnover from bhavcopy rows or substitute another source.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    options = Options()
    for flag in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                 "--window-size=1920,1080", "--disable-blink-features=AutomationControlled"):
        options.add_argument(flag)
    options.add_argument(f'user-agent={HEADERS["User-Agent"]}')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Chrome(options=options)
    output, missing = [], []
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        })
        driver.get(HISTORY_PAGE)
        WebDriverWait(driver, timeout).until(lambda d: d.find_element(By.ID, "datewise1"))
        for day in [pd.Timestamp(x).normalize() for x in dates]:
            driver.execute_script("""
const date=arguments[0];
document.querySelector('#datewise1').click();
const instrument=document.querySelector('#ddlInstrumentName-historicalSummary');
instrument.value='OPTFUT'; instrument.dispatchEvent(new Event('change',{bubbles:true}));
for(const id of ['#txtFromDate-historicalSummary_fromdate','#txtToDate-historicalSummary_toDate']){
  const input=document.querySelector(id); input.value=date;
  input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true}));
}
document.querySelectorAll('a#btnSummary')[0].click();
""", f"{day:%Y-%m-%d}")

            wanted = f"{day:%d %b %Y}".lower()
            try:
                def find_row(d):
                    for table in d.find_elements(By.TAG_NAME, "table"):
                        if not table.is_displayed(): continue
                        for row in table.find_elements(By.CSS_SELECTOR, "tbody tr"):
                            cells = [cell.text.strip() for cell in row.find_elements(By.TAG_NAME, "td")]
                            if len(cells) >= 5 and cells[0].upper() == "OPTFUT" and cells[1].lower() == wanted:
                                return cells
                    return False
                cells = WebDriverWait(driver, timeout).until(find_row)
                output.append(parse_official_summary_row(cells, day))
            except Exception:
                missing.append(day)
        frame = pd.DataFrame(output, columns=["date", "premium_value_lakh", "futures_notional_lakh"])
        return frame, missing
    finally:
        driver.quit()


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
    """Refresh from MCX's official rendered Summary Report and preserve verified history."""
    path = os.path.join(root, CACHE)
    cached = pd.read_csv(path, parse_dates=["date"]) if os.path.exists(path) else pd.DataFrame(columns=["date", "premium_value_lakh", "futures_notional_lakh"])
    cached["date"] = pd.to_datetime(cached.get("date"), errors="coerce").dt.normalize()
    cached = cached.dropna(subset=["date"]).drop_duplicates("date", keep="last")
    end = pd.Timestamp(end).normalize()
    status = "MCX history cache loaded"
    latest = cached.date.max() if len(cached) else max(pd.Timestamp("2024-09-01"), end - pd.Timedelta(days=10))
    missing_dates = list(pd.bdate_range(latest + pd.Timedelta(days=1), end))[-7:]
    try:
        fresh, unpublished = fetch_official_summaries(missing_dates) if missing_dates else (pd.DataFrame(), [])
        if len(fresh):
            cached = pd.concat([cached, fresh], ignore_index=True).drop_duplicates("date", keep="last").sort_values("date")
            os.makedirs(root, exist_ok=True)
            cached.to_csv(path, index=False, date_format="%Y-%m-%d")
            status = f"Official MCX Summary Report refreshed through {cached.date.max():%d %b %Y}"
        if unpublished:
            status = f"Official MCX Summary Report has no newer published row; latest verified date is {cached.date.max():%d %b %Y}"
            log("MCX Summary Report not yet published for: " + ", ".join(f"{x:%d %b}" for x in unpublished))
    except Exception as exc:
        status = f"Official MCX Summary Report unavailable ({type(exc).__name__}); latest verified date unchanged"
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
