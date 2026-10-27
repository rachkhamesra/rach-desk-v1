"""NSE end-of-day files: download (cached, resumable), holiday detection, parsing."""
import io, os, time, zipfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE = "https://nsearchives.nseindia.com"
URL = dict(
    deliv=BASE + "/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv",          # delivery quantity, EQ series
    cm=BASE + "/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip",     # prices + ISIN (UDiFF)
    fo=BASE + "/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip",     # futures/options incl. open interest (UDiFF)
    idx=BASE + "/content/indices/ind_close_all_{d:%d%m%Y}.csv",                  # index closes
    bsedel="https://www.bseindia.com/BSEDATA/gross/{d:%Y}/SCBSEALL{d:%d%m}.zip",  # BSE security-wise delivery
    bsecm="https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV",  # BSE prices + ISIN (scrip code -> ISIN)
)
EXT = dict(deliv="csv", cm="zip", fo="zip", idx="csv", bsedel="zip", bsecm="csv")
HDR = {"bsedel": {**UA, "Referer": "https://www.bseindia.com/"}, "bsecm": {**UA, "Referer": "https://www.bseindia.com/"}}


def path(root, kind, d):
    return os.path.join(root, "raw", kind, f"{d:%Y%m%d}.{EXT[kind]}")


def download(kind, d, root):
    p = path(root, kind, d); os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.exists(p) and os.path.getsize(p) > 0: return "cached"
    for k in range(3):
        try:
            r = requests.get(URL[kind].format(d=d), headers=HDR.get(kind, UA), timeout=45)
            if r.status_code == 200 and len(r.content) > 2000:
                with open(p, "wb") as f: f.write(r.content)
                return "ok"
            if r.status_code == 404: return "404"
        except requests.RequestException:
            pass
        time.sleep(1.5 * (k + 1))
    return "fail"


def deliv_file_date(p):
    """Date printed inside a delivery file. NSE serves the previous trading day's file for a holiday."""
    df = pd.read_csv(p, skipinitialspace=True, nrows=1)
    df.columns = [c.strip() for c in df.columns]
    return pd.to_datetime(str(df["DATE1"].iloc[0]).strip(), format="%d-%b-%Y")


def _ghosts(root):
    f = os.path.join(root, "holidays.txt")
    return set(open(f).read().split()) if os.path.exists(f) else set()


def sync(root, start, end, wait_minutes=0, budget_s=None, workers=6, log=print):
    """Download whatever is missing for every weekday in [start, end]. Returns the list of trading days.
    budget_s lets a caller stop early (resumable): the cache keeps whatever was fetched."""
    t0 = time.time(); days = list(pd.bdate_range(start, end)); hol = _ghosts(root)
    pf = os.path.join(root, "parsed.pkl")
    have = set(pd.read_pickle(pf).keys()) if os.path.exists(pf) else set()      # days already parsed: nothing to download for them
    key = lambda d: d.strftime("%Y-%m-%d")
    deadline = time.time() + wait_minutes * 60
    while True:
        need = [d for d in days if key(d) not in hol and d not in have and not os.path.exists(path(root, "deliv", d))]
        if need:
            log(f"delivery files to fetch: {len(need)}")
            with ThreadPoolExecutor(workers) as ex: list(ex.map(lambda d: download("deliv", d, root), need))
        trading, pending = [], False
        for d in days:
            if key(d) in hol: continue
            if d in have: trading.append(d); continue
            p = path(root, "deliv", d)
            if not os.path.exists(p):
                if d == days[-1] and wait_minutes > 0: pending = True
                continue
            if deliv_file_date(p) != d: hol.add(key(d)); os.remove(p); continue
            trading.append(d)
        open(os.path.join(root, "holidays.txt"), "w").write("\n".join(sorted(hol)))
        if not pending: break
        if time.time() >= deadline: raise SystemExit(f"NSE has not published {days[-1].date()} yet.")
        log("waiting for NSE to publish today's files ..."); time.sleep(300)
    for kind in ("cm", "fo", "idx", "bsedel", "bsecm"):
        need = [d for d in trading if d not in have and not os.path.exists(path(root, kind, d))]
        if budget_s: need = need[: max(0, int((budget_s - (time.time() - t0)) * 4))]
        if need:
            log(f"{kind} files to fetch: {len(need)}")
            with ThreadPoolExecutor(workers) as ex: list(ex.map(lambda d: download(kind, d, root), need))
    # the latest day must be complete: BSE in particular publishes its delivery file later than NSE
    if trading and wait_minutes > 0:
        last = trading[-1]; kinds = ("cm", "fo", "idx", "bsedel", "bsecm")
        missing = [k for k in kinds if not os.path.exists(path(root, k, last))]
        while missing and time.time() < deadline:
            log(f"waiting for {last.date()} files: {', '.join(missing)}"); time.sleep(300)
            for k in missing: download(k, last, root)
            missing = [k for k in kinds if not os.path.exists(path(root, k, last))]
        if missing: raise SystemExit(f"Files for {last.date()} still missing ({', '.join(missing)}). Not publishing a partial day.")
    return trading


# ---------------------------------------------------------------- parsing
def _num(s): return pd.to_numeric(s.astype(str).str.strip().replace("-", np.nan), errors="coerce")


def read_deliv(root, d):
    df = pd.read_csv(path(root, "deliv", d), skipinitialspace=True); df.columns = [c.strip() for c in df.columns]
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip(); df = df[df["SERIES"].astype(str).str.strip() == "EQ"]
    return pd.DataFrame({"dq": _num(df["DELIV_QTY"]).values, "tq": _num(df["TTL_TRD_QNTY"]).values,
                         "turn_cr": _num(df["TURNOVER_LACS"]).values / 100}, index=df["SYMBOL"].values)


def _read_zip_csv(p):
    z = zipfile.ZipFile(p); return pd.read_csv(z.open(z.namelist()[0]))


def read_cm(root, d):
    p = path(root, "cm", d)
    if not os.path.exists(p): return None
    df = _read_zip_csv(p); df = df[df["SctySrs"] == "EQ"]
    return pd.DataFrame({"isin": df["ISIN"].values, "open": df["OpnPric"].values, "high": df["HghPric"].values, "low": df["LwPric"].values,
                         "close": df["ClsPric"].values, "prev": df["PrvsClsgPric"].values}, index=df["TckrSymb"].astype(str).str.strip().values)


def read_fo(root, d):
    """Single stock futures only, all expiries summed. Open interest here is in shares (verified against lot size)."""
    p = path(root, "fo", d)
    if not os.path.exists(p): return None
    df = _read_zip_csv(p); df = df[df["FinInstrmTp"] == "STF"].copy()
    df["XpryDt"] = pd.to_datetime(df["XpryDt"])
    g = df.groupby(df["TckrSymb"].astype(str).str.strip())
    near = df.sort_values("XpryDt").groupby(df["TckrSymb"].astype(str).str.strip()).first()
    return pd.DataFrame({"oi": g["OpnIntrst"].sum(), "doi": g["ChngInOpnIntrst"].sum(), "lot": near["NewBrdLotQty"], "fut": near["ClsPric"]})


def read_bse(root, d, nse_cm):
    """BSE delivered/traded shares per NSE symbol. BSE scrip code -> ISIN (BSE price file) -> NSE symbol (NSE price file, same day)."""
    pd_, pc = path(root, "bsedel", d), path(root, "bsecm", d)
    if not (os.path.exists(pd_) and os.path.exists(pc)) or nse_cm is None: return None
    dl = _read_zip_csv_sep(pd_)
    dl.columns = [c.strip() for c in dl.columns]
    if str(dl["DATE"].iloc[0]).strip() != f"{d:%d%m%Y}": return None
    num = lambda c: pd.to_numeric(dl[c], errors="coerce")
    dl = pd.DataFrame({"code": num("SCRIP CODE").astype("Int64"), "dq": num("DELIVERY QTY"), "vol": num("DAY'S VOLUME")})
    cm = pd.read_csv(pc, usecols=["FinInstrmId", "ISIN"]); code_isin = dict(zip(pd.to_numeric(cm["FinInstrmId"], errors="coerce").astype("Int64"), cm["ISIN"]))
    dl["isin"] = dl["code"].map(code_isin)
    isin_sym = {v: k for k, v in nse_cm["isin"].dropna().items()}
    dl["symbol"] = dl["isin"].map(isin_sym)
    return dl.dropna(subset=["symbol"]).groupby("symbol")[["dq", "vol"]].sum()


def _read_zip_csv_sep(p):
    z = zipfile.ZipFile(p); return pd.read_csv(z.open(z.namelist()[0]), sep="|")


def read_nifty(root, d):
    p = path(root, "idx", d)
    if not os.path.exists(p): return np.nan
    df = pd.read_csv(p); df.columns = [c.strip() for c in df.columns]
    r = df[df["Index Name"].astype(str).str.strip() == "Nifty 50"]
    if r.empty or pd.to_datetime(str(r["Index Date"].iloc[0]).strip(), format="%d-%m-%Y") != d: return np.nan
    return float(r["Closing Index Value"].iloc[0])


def parse_all(root, trading, log=print):
    """Parse each trading day once; results are cached in data/parsed.pkl."""
    f = os.path.join(root, "parsed.pkl")
    parsed = pd.read_pickle(f) if os.path.exists(f) else {}
    todo = [d for d in trading if (d not in parsed or "bse" not in parsed[d]) and os.path.exists(path(root, "cm", d)) and os.path.exists(path(root, "fo", d)) and os.path.exists(path(root, "idx", d))]
    if todo: log(f"parsing {len(todo)} days")
    for d in todo:
        if d in parsed: parsed[d]["bse"] = read_bse(root, d, parsed[d]["cm"]); continue
        cm = read_cm(root, d)
        parsed[d] = dict(deliv=read_deliv(root, d), cm=cm, fo=read_fo(root, d), nifty=read_nifty(root, d), bse=read_bse(root, d, cm))
    if todo: pd.to_pickle(parsed, f)
    return {d: parsed[d] for d in trading if d in parsed}
