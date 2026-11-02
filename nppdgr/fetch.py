"""Download DGR .xls files from npp.gov.in with throttling, retries and an on-disk cache.

URL pattern (verified):
  https://npp.gov.in/public-reports/cea/daily/dgr/DD-MM-YYYY/dgrN-YYYY-MM-DD.xls
"""
import datetime as dt
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://npp.gov.in/public-reports/cea/daily/dgr"
UA = "rach-desk/1.0 (research; polite fetcher)"
OLE2_MAGIC = b"\xd0\xcf\x11\xe0"  # real .xls files start with this; an HTML error page does not


def url_for(day: dt.date, n: int) -> str:
    return f"{BASE}/{day:%d-%m-%Y}/dgr{n}-{day:%Y-%m-%d}.xls"


def cache_path(raw_dir: Path, day: dt.date, n: int) -> Path:
    return Path(raw_dir) / f"{day:%Y-%m-%d}" / f"dgr{n}.xls"


def fetch_one(day: dt.date, n: int, raw_dir, retries: int = 4, force: bool = False):
    """Return (path, status) with status in {'cached','ok','missing'}.

    'missing' means the portal has no file for that date yet (404, or a 200 that is not a
    real .xls). It is not an error: the next scheduled run tries again.
    Network failures and 5xx/429 are retried with backoff, then raised.
    """
    path = cache_path(raw_dir, day, n)
    if path.exists() and not force:
        return path, "cached"
    req = urllib.request.Request(url_for(day, n), headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            if not body.startswith(OLE2_MAGIC):
                return None, "missing"
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(body)
            tmp.replace(path)  # atomic: never leave a half-written file in the cache
            return path, "ok"
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None, "missing"
            err = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            err = e
        if attempt < retries - 1:
            time.sleep(5 * 2 ** attempt)  # 5s, 10s, 20s
    raise RuntimeError(f"giving up on {url_for(day, n)}: {err}")


def fetch_days(days, reports=(2,), raw_dir="data/raw", pause: float = 1.0, force: bool = False):
    """Fetch several dates. Returns {(day, n): (path, status)}. Pauses between real downloads."""
    out = {}
    for day in days:
        for n in reports:
            path, status = fetch_one(day, n, raw_dir, force=force)
            out[(day, n)] = (path, status)
            if status in ("ok", "missing"):
                time.sleep(pause)
    return out


def last_n_days(n: int, today: dt.date = None):
    today = today or dt.date.today()
    return [today - dt.timedelta(days=i) for i in range(n, -1, -1)]
