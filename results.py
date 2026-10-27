"""NSE results calendar and confirmed result-declaration timestamps."""
import os
from urllib.parse import urlencode

import pandas as pd
import requests


BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE + "/companies-listing/corporate-filings-application",
}


def _get(path, params=None):
    """Warm an NSE session before calling its public corporate-filings API."""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get(BASE, timeout=30)
    r = s.get(BASE + path + ("?" + urlencode(params) if params else ""), timeout=45)
    r.raise_for_status()
    return r.json()


def _merge_csv(path, fresh, keys):
    old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
    out = pd.concat([old, fresh], ignore_index=True) if len(old) else fresh.copy()
    if len(out): out = out.drop_duplicates(keys, keep="last")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.to_csv(path, index=False)
    return out


def load(root, asof, log=print):
    """Refresh and return (scheduled meetings, actual result declarations).

    The CSVs are an append-only fallback: an NSE outage leaves the last good
    calendar available and never prevents the price dashboard from building.
    """
    cal_path = os.path.join(root, "results_calendar.csv")
    actual_path = os.path.join(root, "results_actual.csv")

    try:
        raw = _get("/api/corporate-board-meetings", {"index": "equities"})
        rows = []
        for x in raw:
            purpose = str(x.get("bm_purpose") or "")
            desc = str(x.get("bm_desc") or "")
            if "financial result" not in (purpose + " " + desc).lower(): continue
            rows.append(dict(symbol=x.get("bm_symbol"), meeting_date=x.get("bm_date"), announced_at=x.get("bm_timestamp"),
                             purpose=purpose, source_url=x.get("attachment")))
        fresh = pd.DataFrame(rows, columns=["symbol", "meeting_date", "announced_at", "purpose", "source_url"])
        cal = _merge_csv(cal_path, fresh, ["symbol", "meeting_date"])
        log(f"results calendar: {len(fresh)} current NSE entries")
    except Exception as e:
        log(f"results calendar refresh failed ({e}); using cached copy")
        cal = pd.read_csv(cal_path) if os.path.exists(cal_path) else pd.DataFrame(columns=["symbol", "meeting_date", "announced_at", "purpose", "source_url"])

    try:
        start = pd.Timestamp(asof) - pd.Timedelta(days=8)
        raw = _get("/api/corporate-announcements", {"index": "equities", "from_date": f"{start:%d-%m-%Y}", "to_date": f"{asof:%d-%m-%Y}"})
        rows = []
        for x in raw:
            subject = str(x.get("desc") or "")
            detail = str(x.get("attchmntText") or "")
            text = (subject + " " + detail).lower()
            is_outcome = subject.lower() == "outcome of board meeting" or subject.lower() == "integrated filing- financial"
            if not (is_outcome and "financial result" in text): continue
            rows.append(dict(symbol=x.get("symbol"), declared_at=x.get("an_dt"), subject=subject,
                             source_url=x.get("attchmntFile")))
        fresh = pd.DataFrame(rows, columns=["symbol", "declared_at", "subject", "source_url"])
        actual = _merge_csv(actual_path, fresh, ["symbol", "declared_at"])
        log(f"actual results: {len(fresh)} NSE declarations in refresh window")
    except Exception as e:
        log(f"actual-results refresh failed ({e}); using cached copy")
        actual = pd.read_csv(actual_path) if os.path.exists(actual_path) else pd.DataFrame(columns=["symbol", "declared_at", "subject", "source_url"])

    for df, col in ((cal, "meeting_date"), (cal, "announced_at"), (actual, "declared_at")):
        if col in df: df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")
    return cal, actual


def build_signals(M, calendar, actual):
    """Attach the three pre-event sessions and flag delivery + 0.8 sigma moves."""
    dates = pd.DatetimeIndex(M["dates"])
    universe = set(M["syms"])

    def one(symbol, event_date):
        prior = [i for i, d in enumerate(dates) if d.normalize() < event_date.normalize()][-3:]
        sessions = []
        future_gap = 0
        if event_date.normalize() > dates[-1].normalize():
            future_gap = len(pd.bdate_range(dates[-1].normalize() + pd.offsets.BDay(1), event_date.normalize() - pd.offsets.BDay(1)))
        for lag, i in zip(range(len(prior) + future_gap, future_gap, -1), prior):
            if lag > 3: continue
            ratio, z, move = M["RAT"][symbol].iloc[i], M["zmove"][symbol].iloc[i], M["ret1"][symbol].iloc[i] * 100
            hit = pd.notna(ratio) and pd.notna(z) and ratio > 1.0 and abs(z) > 0.8
            sessions.append(dict(lag=lag, date=dates[i], ratio=ratio, move=move, z=z, hit=bool(hit)))
        return sessions

    rows = []
    today = dates[-1].normalize()
    if len(calendar):
        latest = calendar.sort_values("announced_at").drop_duplicates(["symbol", "meeting_date"], keep="last")
        for _, r in latest.iterrows():
            if r.symbol not in universe or pd.isna(r.meeting_date): continue
            d = pd.Timestamp(r.meeting_date)
            if today - pd.Timedelta(days=7) <= d <= today + pd.Timedelta(days=45):
                rows.append(dict(symbol=r.symbol, event_date=d, declared_at=pd.NaT, status="UPCOMING" if d >= today else "SCHEDULED",
                                 source_url=r.get("source_url", ""), sessions=one(r.symbol, d)))
    if len(actual):
        actual = actual.copy(); actual["event_day"] = actual["declared_at"].dt.normalize()
        latest = actual.sort_values("declared_at").drop_duplicates(["symbol", "event_day"], keep="first")
        for _, r in latest.iterrows():
            if r.symbol not in universe or pd.isna(r.declared_at): continue
            d = pd.Timestamp(r.declared_at)
            if d.normalize() >= today - pd.Timedelta(days=14):
                rows.append(dict(symbol=r.symbol, event_date=d.normalize(), declared_at=d, status="DECLARED",
                                 source_url=r.get("source_url", ""), sessions=one(r.symbol, d)))
    rows.sort(key=lambda r: (r["event_date"], r["symbol"]), reverse=True)
    return rows
