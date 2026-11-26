"""NSE options premium turnover: equity (index and single-stock) options and commodity options, from NSE's own daily UDiFF bhavcopies.

Premium turnover is exact, the same way the BSE tracker gets it: NSE's "total transfer value" of an option row is (strike + premium traded) x quantity, so subtracting
strike x quantity leaves the premium turnover. Quantity is contracts x lot for equity options (the lot is in the file) and contracts x the contract multiplier for commodity
options (not in the file: inferred from the row itself and snapped to the known contract sizes).

  equity     /content/fo/BhavCopy_NSE_FO_...   instrument types IDO (index options) and STO (stock options); the desk already downloads these for every session
  commodity  /content/com/BhavCopy_NSE_CO_...  instrument types COO and FUO (options on futures), every underlying; available from January 2024

Daily aggregates are kept in two small CSVs (data/, restored from the build cache) seeded from config/, so a build only fetches the sessions it does not have yet.
"""
from __future__ import annotations

import io
import os
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

BASE = "https://nsearchives.nseindia.com"
FO_URL = BASE + "/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
CO_URL = BASE + "/content/com/BhavCopy_NSE_CO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36", "Accept": "*/*"}
START = pd.Timestamp("2024-01-01")
HERE = os.path.dirname(os.path.abspath(__file__))
EQ_FILE, CO_FILE, NOFILE, PX_FILE = "nse_options_daily.csv", "nse_commodity_daily.csv", "nse_options_nofile.csv", "nse_share_price.csv"
LIST_DATE = pd.Timestamp("2026-09-24")      # National Stock Exchange of India shares began trading on BSE
EQ_COLS = ["date", "idx_contracts", "idx_premium_cr", "idx_notional_cr", "stk_contracts", "stk_premium_cr", "stk_notional_cr"]
CO_COLS = ["date", "underlying", "contracts", "premium_cr", "notional_cr", "trades", "expiries"]
OPTION_TYPES_EQ = ("IDO", "STO")
OPTION_TYPES_CO = ("COO", "FUO")
# contract sizes a commodity option's quantity can be: price unit x this = rupees per contract (crude 100 barrels, natural gas 1,250 mmBtu, gold 1 kg quoted per 10 g ...)
KNOWN_MULTIPLIERS = [1, 5, 10, 30, 50, 100, 250, 500, 1000, 1250, 2500, 5000, 10000]


# ------------------------------------------------------------------ one day's file -> daily aggregates
def _num(frame, col):
    return pd.to_numeric(frame[col], errors="coerce")


def read_zip(content):
    z = zipfile.ZipFile(io.BytesIO(content))
    return pd.read_csv(z.open(z.namelist()[0]))


def equity_summary(df):
    """One row of index and single-stock option aggregates from the F&O bhavcopy of a session, or None when it holds no traded options."""
    o = df[df["FinInstrmTp"].astype(str).isin(OPTION_TYPES_EQ)].copy()
    if o.empty: return None
    contracts, lot, strike, trf = _num(o, "TtlTradgVol"), _num(o, "NewBrdLotQty"), _num(o, "StrkPric"), _num(o, "TtlTrfVal")
    o = o.assign(c=contracts, notional=strike * contracts * lot)
    o["premium"] = trf - o["notional"]
    o = o[(o["c"] > 0) & o["premium"].notna()]
    out = {}
    for tag, kind in (("idx", "IDO"), ("stk", "STO")):
        g = o[o["FinInstrmTp"] == kind]
        out[f"{tag}_contracts"] = float(g["c"].sum()); out[f"{tag}_premium_cr"] = float(g["premium"].sum() / 1e7); out[f"{tag}_notional_cr"] = float(g["notional"].sum() / 1e7)
    return out


def infer_multiplier(rows):
    """The contract multiplier of one commodity's options from its own rows: transfer value / (quantity x (strike + a premium proxy)), the median, snapped to the nearest known size."""
    mid = (_num(rows, "HghPric") + _num(rows, "LwPric")) / 2
    price = _num(rows, "StrkPric") + mid.fillna(_num(rows, "ClsPric"))
    ratio = (_num(rows, "TtlTrfVal") / (_num(rows, "TtlTradgVol") * price)).replace([np.inf, -np.inf], np.nan).dropna()
    if ratio.empty: return None
    m = float(ratio.median())
    best = min(KNOWN_MULTIPLIERS, key=lambda k: abs(k / m - 1))
    return best if abs(best / m - 1) < 0.2 else float(round(m, 0))


def commodity_summary(df):
    """[(underlying, dict)] of option aggregates per commodity from the commodity bhavcopy of a session. Every underlying that lists options gets a row, so a session with no
    trading still shows up as zero (the trading calendar and the expiry dates come from these rows)."""
    o = df[df["FinInstrmTp"].astype(str).isin(OPTION_TYPES_CO) & df["OptnTp"].notna()].copy()
    out = []
    for sym, g in o.groupby("TckrSymb"):
        expiries = "|".join(sorted({str(x)[:10] for x in g["XpryDt"].dropna()}))
        t = g[_num(g, "TtlTradgVol") > 0]
        if t.empty:
            out.append((str(sym), dict(contracts=0.0, premium_cr=0.0, notional_cr=0.0, trades=0.0, expiries=expiries))); continue
        mult = infer_multiplier(t) or 1.0
        vol, strike, trf = _num(t, "TtlTradgVol"), _num(t, "StrkPric"), _num(t, "TtlTrfVal")
        notional = strike * vol * mult
        out.append((str(sym), dict(contracts=float(vol.sum()), premium_cr=float((trf - notional).sum() / 1e7), notional_cr=float(notional.sum() / 1e7),
                                   trades=float(_num(t, "TtlNbOfTxsExctd").sum()), expiries=expiries)))
    return out


# ------------------------------------------------------------------ files: seed + cache, fetch what is missing
def _read(path, cols):
    if not os.path.exists(path): return pd.DataFrame(columns=cols)
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    return df.dropna(subset=["date"])


def _write(path, df):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df = df.assign(date=pd.to_datetime(df["date"]).dt.normalize())
    df.sort_values([c for c in ("date", "underlying") if c in df.columns]).to_csv(path, index=False, date_format="%Y-%m-%d")


def fetch(url, date, session=None, attempts=3):
    """The zip's content, None when NSE has no file for that date (a holiday, or not published yet), or raises after repeated failures."""
    import time
    session = session or requests.Session(); err = None
    for k in range(attempts):
        try:
            r = session.get(url.format(d=date), headers=UA, timeout=60)
            if r.status_code == 404: return None
            r.raise_for_status()
            if r.content[:2] != b"PK": raise ValueError("not a zip file")
            return r.content
        except Exception as e:
            err = e; time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"{date:%d %b %Y}: {err}")


def _local_fo(root, date):
    p = os.path.join(root, "raw", "fo", f"{date:%Y%m%d}.zip")
    return open(p, "rb").read() if os.path.exists(p) else None


def load(root, end, budget=160, workers=6, log=print, seed_dir=os.path.join(HERE, "config")):
    """(equity daily, commodity daily, status text). Reads config/ seeds and the cached CSVs, fetches up to `budget` missing sessions per segment (newest first), saves the cache."""
    end = pd.Timestamp(end).normalize()
    eq = pd.concat([_read(os.path.join(seed_dir, "nse_options_seed.csv"), EQ_COLS), _read(os.path.join(root, EQ_FILE), EQ_COLS)], ignore_index=True).drop_duplicates("date", keep="last")
    co = pd.concat([_read(os.path.join(seed_dir, "nse_commodity_seed.csv"), CO_COLS), _read(os.path.join(root, CO_FILE), CO_COLS)], ignore_index=True).drop_duplicates(["date", "underlying"], keep="last")
    nof = _read(os.path.join(root, NOFILE), ["date", "segment"]) if os.path.exists(os.path.join(root, NOFILE)) else pd.DataFrame(columns=["date", "segment"])
    nofile = {(r.date, r.segment) for r in nof.itertuples()}; new_nofile = set(); problems = []
    days = [d for d in pd.bdate_range(START, end)]

    def work(segment, url, summarise, have):
        todo = [d for d in days if d not in have and (d, segment) not in nofile][::-1][:budget]
        results = []
        if not todo: return results
        sess = requests.Session()

        def one(d):
            try:
                content = _local_fo(root, d) if segment == "eq" else None
                content = content if content is not None else fetch(url, d, sess)
                if content is None:
                    if (end - d).days > 3: new_nofile.add((d, segment))
                    return d, None
                return d, summarise(read_zip(content))
            except Exception as e:
                problems.append(f"{segment} {e}"); return d, None
        with ThreadPoolExecutor(workers) as ex: results = list(ex.map(one, todo))
        return results

    have_eq = set(eq["date"]); added = 0
    for d, row in work("eq", FO_URL, equity_summary, have_eq):
        if row: eq = pd.concat([eq, pd.DataFrame([dict(date=d, **row)])], ignore_index=True); added += 1
    have_co = set(co["date"])
    for d, rows in work("co", CO_URL, commodity_summary, have_co):
        if rows: co = pd.concat([co, pd.DataFrame([dict(date=d, underlying=u, **r) for u, r in rows])], ignore_index=True); added += 1
    eq = eq.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    co = co.drop_duplicates(["date", "underlying"], keep="last").sort_values(["date", "underlying"]).reset_index(drop=True)
    if added or new_nofile:
        _write(os.path.join(root, EQ_FILE), eq[EQ_COLS]); _write(os.path.join(root, CO_FILE), co[CO_COLS])
        if new_nofile:
            allno = pd.concat([nof, pd.DataFrame(sorted(new_nofile), columns=["date", "segment"])], ignore_index=True).drop_duplicates()
            _write(os.path.join(root, NOFILE), allno)
    for p in problems[:3]: log(f"warning: NSE options: {p}")
    missing = len([d for d in days if d not in set(eq["date"]) and (d, "eq") not in nofile and (d, "eq") not in new_nofile])
    status = (f"NSE bhavcopy: equity options through {eq['date'].max():%d %b %Y}, commodity options through {co['date'].max():%d %b %Y}" if len(eq) and len(co)
              else "NSE options data is not available yet")
    if missing > 5: status += f" · {missing} older sessions still to be filled in"
    return eq[eq["date"] <= end], co[co["date"] <= end], status


def _bse_cm_url():
    import nse
    return nse.URL["bsecm"], nse.HDR.get("bsecm", UA)


def share_close(content):
    """The closing price of National Stock Exchange of India's share from a BSE equity bhavcopy (csv bytes), or None when it is not in the file."""
    df = pd.read_csv(io.BytesIO(content), usecols=lambda c: c in ("TckrSymb", "FinInstrmNm", "ClsPric"))
    m = df[(df["TckrSymb"].astype(str).str.strip() == "NSE") & df["FinInstrmNm"].astype(str).str.contains("National Stock", case=False)]
    return None if m.empty else float(pd.to_numeric(m["ClsPric"], errors="coerce").iloc[0])


def load_share_price(root, end, workers=6, log=print, seed_dir=os.path.join(HERE, "config")):
    """Daily closes of NSE's own share (BSE: NSE) from its listing date, from the seed, the cache and, for sessions not yet held, the BSE bhavcopy: the desk's NSE price file does not carry it,
    since the share trades on BSE. A Series indexed by date; short because the share is new."""
    end = pd.Timestamp(end).normalize()
    have = pd.concat([_read(os.path.join(seed_dir, "nse_share_seed.csv"), ["date", "close"]), _read(os.path.join(root, PX_FILE), ["date", "close"])], ignore_index=True).drop_duplicates("date", keep="last")
    seen = set(have["date"]); url, hdr = _bse_cm_url(); sess = requests.Session(); new = []
    days = [d for d in pd.bdate_range(LIST_DATE, end) if d not in seen]

    def one(d):
        try:
            p = os.path.join(root, "raw", "bsecm", f"{d:%Y%m%d}.csv")
            if os.path.exists(p): return d, share_close(open(p, "rb").read())
            r = sess.get(url.format(d=d), headers=hdr, timeout=45)
            return (d, share_close(r.content)) if r.status_code == 200 else (d, None)
        except Exception:
            return d, None
    with ThreadPoolExecutor(workers) as ex:
        for d, c in ex.map(one, days):
            if c is not None: new.append(dict(date=d, close=c))
    if new:
        have = pd.concat([have, pd.DataFrame(new)], ignore_index=True).drop_duplicates("date", keep="last"); _write(os.path.join(root, PX_FILE), have[["date", "close"]])
    have = have.sort_values("date")
    return pd.Series(have["close"].values, index=pd.DatetimeIndex(have["date"]))


# ------------------------------------------------------------------ the dashboard data
def _expiry_sets(co):
    out = {}
    for u, g in co.groupby("underlying"):
        s = set()
        for text in g["expiries"].dropna().astype(str):
            for x in text.split("|"):
                if x: s.add(pd.Timestamp(x))
        out[u] = s
    return out


def commodity_days(co):
    """Per (session, underlying): whether it is that commodity's option expiry day ('E'), the session before it ('E-1') or any other, with the premium and contracts of the day."""
    if co is None or co.empty: return pd.DataFrame(columns=CO_COLS + ["kind"])
    cal = list(sorted(co["date"].unique())); nxt = {cal[i]: cal[i + 1] for i in range(len(cal) - 1)}
    exp = _expiry_sets(co); d = co.copy()
    d["kind"] = [("E" if r.date in exp.get(r.underlying, ()) else "E-1" if nxt.get(r.date) in exp.get(r.underlying, ()) else "other") for r in d.itertuples()]
    return d


def build_commodity(co):
    d = commodity_days(co)
    if d.empty or d["premium_cr"].sum() == 0: return {"available": False}
    d["month"] = d["date"].dt.to_period("M")
    daily = d.groupby("date").agg(premium_cr=("premium_cr", "sum"), contracts=("contracts", "sum"), notional_cr=("notional_cr", "sum")).reset_index()
    kinds = d.pivot_table(index="date", columns="kind", values="premium_cr", aggfunc="sum", fill_value=0)
    for k in ("E", "E-1", "other"):
        daily[f"p_{k}"] = daily["date"].map(kinds[k]) if k in kinds else 0.0
    # a session's kind for the chart: E if any commodity expired that day, else E-1 if any expires next session, else other
    order = {"E": 0, "E-1": 1, "other": 2}
    daily["kind"] = daily["date"].map(d.sort_values("kind", key=lambda s: s.map(order)).groupby("date")["kind"].first())
    by_kind = d.pivot_table(index="month", columns="kind", values=["premium_cr", "contracts"], aggfunc="sum", fill_value=0)
    months = []
    for m in sorted(d["month"].unique()):
        g = d[d["month"] == m]; sess = g["date"].nunique(); tot = g["premium_cr"].sum(); row = dict(month=str(m), sessions=sess, premium=float(tot), contracts=float(g["contracts"].sum()))
        for k in ("E", "E-1", "other"):
            gk = g[g["kind"] == k]; row[f"p_{k}"] = float(gk["premium_cr"].sum()); row[f"c_{k}"] = float(gk["contracts"].sum())
        row["share_ee1"] = (row["p_E"] + row["p_E-1"]) / tot * 100 if tot else np.nan
        row["active"] = int((g.groupby("date")["premium_cr"].sum() > 0).sum())
        months.append(row)
    months = pd.DataFrame(months)
    # cumulative premium by session number, for the last months
    cum = {}
    for m in sorted(daily["date"].dt.to_period("M").unique())[-8:]:
        s = daily[daily["date"].dt.to_period("M") == m].sort_values("date")["premium_cr"].cumsum().tolist()
        cum[str(m)] = s
    # expiry events: for each commodity and each expiry date that has passed, the session before and the day itself
    cal = list(sorted(co["date"].unique())); prev = {cal[i]: cal[i - 1] for i in range(1, len(cal))}
    events = []
    for u, es in _expiry_sets(co).items():
        gu = d[d["underlying"] == u].set_index("date")
        for e in sorted(x for x in es if x in gu.index and x <= cal[-1]):
            p1 = prev.get(e); r_e = gu.loc[e]; r_p = gu.loc[p1] if p1 in gu.index else None
            if r_e["contracts"] == 0 and (r_p is None or r_p["contracts"] == 0): continue
            events.append(dict(underlying=u, expiry=e, prem_e=float(r_e["premium_cr"]), con_e=float(r_e["contracts"]), prem_p=0.0 if r_p is None else float(r_p["premium_cr"]), con_p=0.0 if r_p is None else float(r_p["contracts"])))
    events = pd.DataFrame(events).sort_values("expiry") if events else pd.DataFrame(columns=["underlying", "expiry", "prem_e", "con_e", "prem_p", "con_p"])
    last_month = d["month"].max(); recent = months.iloc[-4:-1] if len(months) > 3 else months.iloc[:-1]
    by_u = d.groupby(["month", "underlying"])["premium_cr"].sum().reset_index()
    asof = daily["date"].max(); com = []
    cur = months.iloc[-1]; n = int(cur["sessions"])
    if len(months) > 1:
        prior = months.iloc[-2]; pc = cum.get(str(prior["month"]), [])
        if len(pc) >= n and n > 0 and pc[n - 1] > 0:
            com.append(f"{pd.Timestamp(cur['month'] + '-01'):%B} so far: ₹{cur['premium']:,.1f} cr of option premium over {n} sessions, {(cur['premium'] / pc[n - 1] - 1) * 100:+.0f}% against {pd.Timestamp(prior['month'] + '-01'):%B} over its first {n}.")
    if len(recent) and recent["premium"].sum() > 0:
        share = (recent["p_E"].sum() + recent["p_E-1"].sum()) / recent["premium"].sum() * 100
        com.append(f"Over the last {len(recent)} full months, {share:.0f}% of commodity option premium turnover came on expiry day and the session before it, from {int(recent['active'].sum())} active sessions of {int(recent['sessions'].sum())}.")
        e_only = recent["p_E"].sum() / recent["premium"].sum() * 100
        com.append(f"Expiry day alone carried {e_only:.0f}% of it; the session before carried {share - e_only:.0f}%.")
    lastday = daily.iloc[-1]
    com.append(f"The latest session ({lastday['date']:%d %b}) had ₹{lastday['premium_cr']:,.1f} cr of premium on {lastday['contracts']:,.0f} contracts" + (" and was an expiry day." if lastday["kind"] == "E" else " and was the session before an expiry." if lastday["kind"] == "E-1" else "."))
    return dict(available=True, asof=asof, daily=daily, monthly=months, cumulative=cum, events=events, by_underlying=by_u, commentary=com)


def share_of_combined(eq, co, mcx, days=92):
    """NSE commodity options' share of NSE commodity plus MCX options premium turnover over a rolling three calendar months, at each MCX date. A point needs a full window of both, so the
    series starts three months after MCX's history does. None when there is no MCX history. (Equity options are left out: they have no MCX counterpart, so comparing them with MCX says nothing.)"""
    if mcx is None or len(mcx) == 0 or eq is None or len(eq) == 0: return None
    m = pd.Series(mcx["premium_turnover_cr"].values, index=pd.DatetimeIndex(mcx["date"])).sort_index()
    m = m[~m.index.duplicated(keep="last")]
    if co is None or len(co) == 0: return None
    nse_co = co.groupby("date")["premium_cr"].sum(); nse_co.index = pd.DatetimeIndex(nse_co.index)
    roll = lambda x: x.rolling(f"{days}D").sum()
    at = m.index[m.index >= m.index[0] + pd.Timedelta(days=days)]
    if len(at) == 0: return None
    c, mm = roll(nse_co).reindex(at, method="ffill"), roll(m).reindex(at)
    out = pd.DataFrame({"date": at, "share_commodity": (c / (c + mm) * 100).values, "nse_commodity": c.values, "mcx": mm.values}).dropna()
    return out.reset_index(drop=True) if len(out) else None


def build(eq, co, prices, status="", mcx=None):                # prices: NSE's own share price (see load_share_price); mcx: the MCX tracker's daily premium turnover
    """{all, equity, equity_monthly, commodity, status}: the all-NSE and equity series in the shape the BSE and MCX trackers use, plus the commodity analysis."""
    import exchange_tracker
    eq = eq.copy() if eq is not None else pd.DataFrame(columns=EQ_COLS)
    if eq.empty: return {"available": False, "status": status or "NSE options data is not available yet"}
    eq["equity"] = eq["idx_premium_cr"].fillna(0) + eq["stk_premium_cr"].fillna(0)
    cod = co.groupby("date")["premium_cr"].sum() if co is not None and len(co) else pd.Series(dtype=float)
    series_eq = eq.set_index("date")["equity"]
    allv = series_eq.add(cod, fill_value=0)
    px = pd.Series(prices).copy(); px.index = pd.to_datetime(px.index).normalize()

    def tracker(values, label, what):
        h = pd.DataFrame({"date": values.index, "premium_turnover_cr": values.values}).dropna(); h = h[h["premium_turnover_cr"] > 0]
        h.attrs["update_status"] = status
        X = exchange_tracker.build(h, px)
        if X.get("available"):
            X.update(source="https://www.nseindia.com/all-reports-derivatives", source_label="NSE UDIFF BHAVCOPY", price_label="NSE price", what=what)
        return X

    X_all = tracker(allv, "all", "Equity and commodity options")
    X_eq = tracker(series_eq, "equity", "Index and single-stock options")
    m = eq.assign(month=eq["date"].dt.to_period("M")).groupby("month").agg(idx=("idx_premium_cr", "mean"), stk=("stk_premium_cr", "mean"), sessions=("date", "count"),
                                                                       idx_c=("idx_contracts", "mean"), stk_c=("stk_contracts", "mean")).reset_index()
    m["month"] = m["month"].astype(str); m["idx_share"] = m["idx"] / (m["idx"] + m["stk"]) * 100
    return {"available": True, "status": status, "all": X_all, "equity": X_eq, "equity_monthly": m, "commodity": build_commodity(co if co is not None else pd.DataFrame(columns=CO_COLS)), "share": share_of_combined(eq, co, mcx)}
