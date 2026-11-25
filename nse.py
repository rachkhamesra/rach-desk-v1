"""NSE end-of-day files: download (cached, resumable), holiday detection, parsing."""
import io, os, time, zipfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
PARSER_VERSION = 4          # 4: open interest leaves out the contracts expiring on the session (their open interest is settled to zero at the close). 3: trade-for-trade series (BE, BZ) are kept, with the whole volume counted as delivery, so a stock moved there keeps its history. Changing this re-parses every cached day.
SERIES_OK = ("EQ", "BE", "BZ")   # BL is the block-deal session and SM/ST are SME boards: not part of a stock's own price history
TFT = ("BE", "BZ")               # trade-for-trade: no intraday trading is allowed, so every share traded is a delivered share
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


def load_parsed(root):
    """The cached parsed days, or nothing when they were parsed by an older version of the parser."""
    f, v = os.path.join(root, "parsed.pkl"), os.path.join(root, "parsed.version")
    try: ok = os.path.exists(f) and open(v).read().strip() == str(PARSER_VERSION)
    except OSError: ok = False
    return pd.read_pickle(f) if ok else {}


def save_parsed(root, parsed):
    pd.to_pickle(parsed, os.path.join(root, "parsed.pkl")); open(os.path.join(root, "parsed.version"), "w").write(str(PARSER_VERSION))


def path(root, kind, d):
    return os.path.join(root, "raw", kind, f"{d:%Y%m%d}.{EXT[kind]}")


def download(kind, d, root):
    p = path(root, kind, d); os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.exists(p) and os.path.getsize(p) > 0: return "cached"
    for k in range(3):
        try:
            r = requests.get(URL[kind].format(d=d), headers=HDR.get(kind, UA), timeout=45)
            if r.status_code == 200 and len(r.content) > 2000 and not r.content[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):          # an error page served with a 200 is not data
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


def recent_without_bse(parsed):
    """Parsed days with no BSE delivery: either BSE had not published yet, or an older parser dropped it.
    They are asked for again every run (a missing file is one quick 404) until BSE data is in."""
    return {d for d in sorted(parsed) if parsed[d].get("bse") is None}


def sync(root, start, end, wait_minutes=0, budget_s=None, workers=6, log=print, backfill=None):
    """Download whatever is missing for every weekday in [start, end]. Returns the list of trading days.
    budget_s lets a caller stop early (resumable): the cache keeps whatever was fetched.
    backfill caps how many weekdays older than the oldest day already parsed are fetched in this call (newest first), so extending the history
    to a longer window takes a few runs instead of one very long one. The history stays contiguous."""
    t0 = time.time(); days = list(pd.bdate_range(start, end)); hol = _ghosts(root)
    cached = load_parsed(root)
    have = set(cached.keys())
    if backfill and have:
        older = [d for d in days if d < min(have) and d.strftime('%Y-%m-%d') not in hol]
        if len(older) > backfill: days = [d for d in days if d >= older[-backfill]]
        log(f"history backfill: {min(len([d for d in older]), backfill)} older weekdays this run")                                                    # days already parsed: nothing to download for them
    late_bse = recent_without_bse(cached)                                        # but BSE publishes later than NSE: keep asking for those
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
        need = [d for d in trading if (d not in have or (kind.startswith("bse") and d in late_bse)) and not os.path.exists(path(root, kind, d))]
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
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip(); df["SERIES"] = df["SERIES"].astype(str).str.strip()
    df = df[df["SERIES"].isin(SERIES_OK)]
    df = df.assign(_rank=df["SERIES"].map({k: i for i, k in enumerate(SERIES_OK)})).sort_values("_rank").drop_duplicates("SYMBOL")        # EQ wins if a symbol is somehow in two series
    tq = _num(df["TTL_TRD_QNTY"])
    dq = _num(df["DELIV_QTY"]).where(~df["SERIES"].isin(TFT), tq)           # the file prints "-" for delivery in trade-for-trade, where all of the volume is delivery
    return pd.DataFrame({"dq": dq.values, "tq": tq.values, "turn_cr": _num(df["TURNOVER_LACS"]).values / 100}, index=df["SYMBOL"].values)


def _read_zip_csv(p):
    z = zipfile.ZipFile(p); return pd.read_csv(z.open(z.namelist()[0]))


def read_cm(root, d):
    p = path(root, "cm", d)
    if not os.path.exists(p): return None
    df = _read_zip_csv(p); df = df[df["SctySrs"].isin(SERIES_OK)]
    df = df.assign(_rank=df["SctySrs"].map({k: i for i, k in enumerate(SERIES_OK)})).sort_values("_rank").drop_duplicates("TckrSymb")
    return pd.DataFrame({"isin": df["ISIN"].values, "open": df["OpnPric"].values, "high": df["HghPric"].values, "low": df["LwPric"].values,
                         "close": df["ClsPric"].values, "prev": df["PrvsClsgPric"].values}, index=df["TckrSymb"].astype(str).str.strip().values)


def fo_open_interest(df, d):
    """Single stock futures open interest per symbol for one session, from that day's F&O bhavcopy rows.

    A contract that expires on the session is settled at its close, so its open interest is zero afterwards: NSE's file still lists it with the open interest it had going into the
    close. Counting it makes the day's total too high by the whole expiring series, and the next session then shows a drop that never happened (Blue Star: 51.9 lakh shares on the
    expiry day against 39.1 lakh once the expiring series is out, so the next day read as down 25% when it was down 1%). So:
      oi   open interest of the contracts that continue past the session (those expiring on it are excluded)
      doi  the change from the previous session's total, which is the continuing contracts' own change less the open interest the expiring contracts carried in
    Lot and futures price come from the nearest continuing contract."""
    df = df[df["FinInstrmTp"] == "STF"].copy()
    d = pd.Timestamp(d).normalize()
    actual = pd.to_datetime(df["FininstrmActlXpryDt"], errors="coerce") if "FininstrmActlXpryDt" in df else pd.Series(pd.NaT, index=df.index)
    df["exp"] = actual.fillna(pd.to_datetime(df["XpryDt"], errors="coerce")).dt.normalize()
    df["sym"] = df["TckrSymb"].astype(str).str.strip()
    oi_, chg = pd.to_numeric(df["OpnIntrst"], errors="coerce"), pd.to_numeric(df["ChngInOpnIntrst"], errors="coerce")
    live = df["exp"] > d
    syms = pd.Index(sorted(df["sym"].unique()))
    oi = oi_[live].groupby(df.loc[live, "sym"]).sum().reindex(syms, fill_value=0)
    carried_in = (oi_ - chg)[~live].groupby(df.loc[~live, "sym"]).sum().reindex(syms, fill_value=0)       # what the expiring contracts held at the previous close
    doi = chg[live].groupby(df.loc[live, "sym"]).sum().reindex(syms, fill_value=0) - carried_in
    pool = df[live] if live.any() else df
    near = pool.sort_values("exp").groupby("sym").first().reindex(syms)
    allnear = df.sort_values("exp").groupby("sym").first().reindex(syms)                                    # a symbol with nothing past today still gets its lot and price
    lot = near["NewBrdLotQty"].fillna(allnear["NewBrdLotQty"]); fut = near["ClsPric"].fillna(allnear["ClsPric"])
    return pd.DataFrame({"oi": oi, "doi": doi, "lot": lot, "fut": fut})


def read_fo(root, d):
    """Single stock futures only, all expiries summed, with the contracts expiring on the day taken out (see fo_open_interest). Open interest here is in shares (verified against lot size)."""
    p = path(root, "fo", d)
    if not os.path.exists(p): return None
    return fo_open_interest(_read_zip_csv(p), d)


def read_bse(root, d, nse_cm):
    """BSE delivered/traded shares per NSE symbol. BSE scrip code -> ISIN (BSE price file) -> NSE symbol (NSE price file, same day)."""
    pd_, pc = path(root, "bsedel", d), path(root, "bsecm", d)
    if not (os.path.exists(pd_) and os.path.exists(pc)) or nse_cm is None: return None
    dl = _read_zip_csv_sep(pd_)
    dl.columns = [c.strip().replace("`", "'") for c in dl.columns]       # one day (25 Apr 2024) spells DAY'S with a backtick
    # BSE writes the date as a number (2 Nov 2026 is 2112026), so the leading zero of days 1-9 is lost
    if str(dl["DATE"].iloc[0]).strip().split(".")[0].zfill(8) != f"{d:%d%m%Y}": return None
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


class Parsed(dict):
    """The parsed days (date to frames) plus `aliases`: {earlier symbol: current symbol} for every stock that was renamed during the history."""
    aliases = {}


def symbol_aliases(parsed):
    """Stocks keep their ISIN when the exchange renames their symbol (Zomato became Eternal, Tata Motors became TMPV). Where one ISIN was traded under several symbols that never
    overlapped in time, every earlier symbol maps to the latest, so the history is one stock and not a short life under the new name. An ISIN seen under two symbols on the same
    day is left alone: that is two instruments, not a rename."""
    frames = []
    for d, p in parsed.items():
        cm = p.get("cm")
        if cm is not None and len(cm): frames.append(pd.DataFrame({"isin": cm["isin"].to_numpy(), "sym": cm.index.to_numpy(), "d": d}))
    if not frames: return {}
    long = pd.concat(frames, ignore_index=True).dropna(subset=["isin"])
    span = long.groupby(["isin", "sym"])["d"].agg(["min", "max"]).reset_index()
    alias = {}
    for isin, g in span.groupby("isin"):
        if len(g) < 2: continue
        g = g.sort_values("min")
        if (g["min"].to_numpy()[1:] <= g["max"].to_numpy()[:-1]).any(): continue                      # symbols overlap in time: not a rename
        latest = g["sym"].iloc[-1]
        for sym in g["sym"].iloc[:-1]:
            if sym != latest: alias[sym] = latest
    return alias


def canonical(parsed):
    """The parsed days with every renamed stock under its current symbol (see symbol_aliases)."""
    alias = symbol_aliases(parsed); out = Parsed()
    out.aliases = alias
    for d, p in parsed.items():
        q = dict(p)
        for part in ("cm", "deliv", "fo", "bse"):
            df = q.get(part)
            if df is not None and len(df) and alias: q[part] = df.rename(index=alias)
        out[d] = q
    return out


def parse_all(root, trading, log=print):
    """Parse each trading day once; results are cached in data/parsed.pkl."""
    parsed = load_parsed(root)
    retry = recent_without_bse({d: v for d, v in parsed.items() if d in trading})
    todo = [d for d in trading if (d not in parsed or "bse" not in parsed[d] or (d in retry and os.path.exists(path(root, "bsedel", d)) and os.path.exists(path(root, "bsecm", d)))) and os.path.exists(path(root, "cm", d)) and os.path.exists(path(root, "fo", d)) and os.path.exists(path(root, "idx", d))]
    if todo: log(f"parsing {len(todo)} days")
    for d in todo:
        if d in parsed: parsed[d]["bse"] = read_bse(root, d, parsed[d]["cm"]); continue
        cm = read_cm(root, d)
        parsed[d] = dict(deliv=read_deliv(root, d), cm=cm, fo=read_fo(root, d), nifty=read_nifty(root, d), bse=read_bse(root, d, cm))
    if todo: save_parsed(root, parsed)
    return canonical({d: parsed[d] for d in trading if d in parsed})
