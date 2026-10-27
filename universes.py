"""Official NSE index constituents and the top 1,000 companies by market cap."""
import html, io, json, os, re
import pandas as pd, requests

INDEX_URLS = {
    "nifty100": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "midcap150": "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "smallcap250": "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
    "nifty500": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
}
MCAP_PAGE = "https://www.nseindia.com/static/regulations/listing-compliance/nse-market-capitalisation-all-companies"
MCAP_FALLBACK = "https://nsearchives.nseindia.com/web/mediaattachment/2026-01/Average_MCAP_July2025ToDecember2025_20260102201101.xlsx"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def _symbols_csv(content):
    df = pd.read_csv(io.BytesIO(content))
    return [str(x).strip().upper() for x in df["Symbol"].dropna()]


def _top1000(content):
    df = pd.read_excel(io.BytesIO(content))
    cols = {str(c).strip().lower(): c for c in df.columns}
    symbol = next(c for k, c in cols.items() if k == "symbol")
    rank = next((c for k, c in cols.items() if k == "rank"), None)
    if rank is not None:
        df[rank] = pd.to_numeric(df[rank], errors="coerce")
        df = df[df[rank].between(1, 1000)].sort_values(rank)
    return [str(x).strip().upper() for x in df[symbol].dropna().head(1000)]


def _latest_mcap_url(session):
    text = session.get(MCAP_PAGE, headers=HEADERS, timeout=30).text
    links = re.findall(r'https?[^"\'<> ]+\.xlsx|/[^"\'<> ]+\.xlsx', html.unescape(text), flags=re.I)
    links = [x.replace("\\/", "/") for x in links if "mcap" in x.lower() or "capital" in x.lower()]
    if not links:
        return MCAP_FALLBACK
    url = links[0]
    return url if url.startswith("http") else "https://www.nseindia.com" + url


def load(root, log=print):
    """Return ordered membership lists; fall back to the last good local copy."""
    path = os.path.join(root, "universes.json")
    try:
        s = requests.Session()
        raw = {}
        for key, url in INDEX_URLS.items():
            r = s.get(url, headers=HEADERS, timeout=30); r.raise_for_status()
            raw[key] = _symbols_csv(r.content)
        url = _latest_mcap_url(s)
        r = s.get(url, headers=HEADERS, timeout=60); r.raise_for_status()
        raw["top1000"] = _top1000(r.content)
        raw["nifty250"] = list(dict.fromkeys(raw["nifty100"] + raw["midcap150"]))
        os.makedirs(root, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2)
        return raw
    except Exception as e:
        if os.path.exists(path):
            log(f"universe refresh failed; using cached memberships: {e}")
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        raise RuntimeError(f"could not load official NSE universe lists: {e}") from e
