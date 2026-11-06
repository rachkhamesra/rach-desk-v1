"""Run locally (python backtest.py), not in the daily build. Writes config/backtest_results.json, which the Power generation tab shows.

Very experimental: do generation levels and IEX day-ahead prices lead these power stocks?

For each stock and each signal, on every fifth trading day of a calendar year: take what was knowable on that
day (generation lagged two days, IEX price one day), then look at the stock's return over the next 10 and 20
trading days in excess of the Nifty. A relationship "works" only if it has the expected sign (more generation, a
higher power price: stock up) and is statistically strong for that year alone. Years are scored separately.

This is a screen for ideas, not a trading system: a handful of observations per test, many tests, overlapping
return windows, no costs, and prices from Yahoo Finance rather than the exchange. See the page for the rules.
"""
import json, os
import numpy as np
import pandas as pd
import requests

STOCKS = [("NTPC", "NTPC", "NTPC.NS"), ("ADANIPOWER", "Adani Power", "ADANIPOWER.NS"), ("ADANIGREEN", None, "ADANIGREEN.NS"),
          ("NHPC", "NHPC", "NHPC.NS"), ("JSWENERGY", "JSW Energy", "JSWENERGY.NS")]
NIFTY = "^NSEI"
YEARS = (2024, 2025, 2026)
HORIZONS = (10, 20)
STEP = 5                      # a signal is sampled every fifth trading day
GEN_LAG, IEX_LAG = 2, 1       # calendar days between a day and the moment its figure is public
PROXIES = {"NHPC": "HYDRO"}   # no per-company series: NHPC is tested against all-India hydro generation (CEA, domestic hydro stations)
PROXY_NOTES = {"NHPC": "all-India hydro generation used as a stand-in for NHPC's own"}
SIGNALS = [("GEN_YOY", "Generation: 30-day average against the same dates a year earlier", "gen"),
           ("GEN_MOM", "Generation: 14-day average against its 60-day average", "gen"),
           ("PX_YOY", "IEX price: 30-day average against the same dates a year earlier", "iex"),
           ("PX_MOM", "IEX price: 14-day average against its 60-day average", "iex"),
           ("BOTH", "Generation and IEX price rising together (average of the two year-on-year z-scores)", "both")]
VERDICTS = ("WORKS", "SOMETIMES WORKS", "COULD WORK", "DOESN'T WORK", "INVERSE", "NO DATA")
RULES = {"WORKS": "t of 2 or more over 20 days, the same sign over 10 days, and the high-signal group beat the low-signal group",
         "SOMETIMES WORKS": "t of 1 or more over 20 days, or t of 2 or more over 10 days only",
         "COULD WORK": "right sign over 20 days with t between 0.5 and 1: not convincing yet, worth watching",
         "DOESN'T WORK": "no relationship, or weakly the wrong way round",
         "INVERSE": "t of -1.5 or less over 20 days (or -2 over 10 days): it worked backwards that year",
         "NO DATA": "no series to test, or fewer than 8 sampled dates"}
IDEAS = [("Adani Green against its own generation", "Wind and solar are not in the CEA conventional report. Needs Grid-India's daily renewable generation, or the company's monthly disclosures."),
         ("Merchant exposure", "Adani Power and JSW Energy sell part of their output on the exchange; a price signal weighted by each company's merchant share should beat the plain price."),
         ("Coal stock days", "Already in the power dataset per company: low stock can cap generation. Not tested here."),
         ("Peak demand and shortage", "Grid-India's daily peak demand and shortage figures would separate demand-led from supply-led generation.")]
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/"
UA = "Mozilla/5.0 (compatible; rach-desk-research/1.0)"
PRICE_START = pd.Timestamp("2023-09-01")
EVERY_DAYS = 7


# ------------------------------------------------------------------ prices
def fetch_prices(symbol, start, end, session=None):
    """Daily dividend- and split-adjusted close from Yahoo Finance as a Series indexed by IST trading date, or None."""
    s = session or requests
    r = s.get(YAHOO + symbol, params=dict(period1=int(start.timestamp()), period2=int((end + pd.Timedelta(days=2)).timestamp()), interval="1d", events="div,splits"),
              headers={"User-Agent": UA}, timeout=40)
    if r.status_code != 200: return None
    res = (r.json().get("chart", {}).get("result") or [None])[0]
    if not res or "timestamp" not in res: return None
    idx = pd.to_datetime(res["timestamp"], unit="s").tz_localize("UTC").tz_convert("Asia/Kolkata").normalize().tz_localize(None)
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or res["indicators"]["quote"][0]["close"]
    out = pd.Series(adj, index=idx, dtype=float).dropna()
    return out[~out.index.duplicated(keep="last")]


def refresh_prices(root, today, log=print, fetcher=fetch_prices, every=None):
    """data/backtest/prices.csv: one column per stock plus NIFTY. Downloaded at most once a week; a failure keeps the cached file."""
    import time
    folder = os.path.join(root, "backtest"); os.makedirs(folder, exist_ok=True)
    path, meta_path = os.path.join(folder, "prices.csv"), os.path.join(folder, "_fetched.json")
    every = int(os.environ.get("BACKTEST_EVERY_DAYS", EVERY_DAYS)) if every is None else every
    old = pd.read_csv(path, index_col=0, parse_dates=True) if os.path.exists(path) else None
    try:
        with open(meta_path) as f: last = json.load(f).get("prices")
    except (OSError, ValueError):
        last = None
    today = pd.Timestamp(today).normalize()
    if old is not None and last and (today - pd.Timestamp(last)).days < every: return old
    cols, failed = {}, []
    for sym in [x[2] for x in STOCKS] + [NIFTY]:
        try: ser = fetcher(sym, PRICE_START, today)
        except Exception as e: ser = None; log(f"backtest: {sym}: {type(e).__name__}")
        if ser is None or len(ser) < 100: failed.append(sym); continue
        cols[sym] = ser; time.sleep(0.5)
    if failed:
        log(f"backtest: prices not refreshed for {', '.join(failed)}" + ("; using the cached file" if old is not None else ""))
        if not cols: return old
    df = pd.DataFrame(cols).sort_index()
    if old is not None:
        for c in old.columns:
            if c not in df: df[c] = old[c]
    df.to_csv(path, date_format="%Y-%m-%d")
    if not failed:
        with open(meta_path, "w") as f: json.dump({"prices": f"{today:%Y-%m-%d}"}, f)
    return df


# ------------------------------------------------------------------ signals
def _daily(s, first):
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(pd.date_range(min(first, s.index.min()), s.index.max()))


def yoy(s):
    """30-day average against the same 30 days 52 weeks earlier (so weekdays line up)."""
    m = s.rolling(30, min_periods=20).mean()
    return m / m.shift(364) - 1


def mom(s):
    return s.rolling(14, min_periods=10).mean() / s.rolling(60, min_periods=40).mean() - 1


def zscore(x):
    return (x - x.rolling(365, min_periods=120).mean()) / x.rolling(365, min_periods=120).std()


def make_signals(gen, iexp):
    """{signal key: daily Series of what was knowable that day}. `gen` or `iexp` may be None."""
    out = {}
    if gen is not None: g = _daily(gen, gen.index.min()); out["GEN_YOY"], out["GEN_MOM"] = yoy(g).shift(GEN_LAG), mom(g).shift(GEN_LAG)
    if iexp is not None: p = _daily(iexp, iexp.index.min()); out["PX_YOY"], out["PX_MOM"] = yoy(p).shift(IEX_LAG), mom(p).shift(IEX_LAG)
    if gen is not None and iexp is not None:
        both = pd.concat([zscore(yoy(g)).shift(GEN_LAG), zscore(yoy(p)).shift(IEX_LAG)], axis=1).dropna()
        out["BOTH"] = both.mean(axis=1)
    return out


# ------------------------------------------------------------------ scoring
def t_stat(ic, n_eff):
    return float(ic * np.sqrt((n_eff - 2) / max(1e-9, 1 - ic * ic))) if n_eff > 2 and pd.notna(ic) else np.nan


def verdict(t10, t20, ic10, spread20, n):
    if n < 8 or pd.isna(t20): return "NO DATA"
    if t20 <= -1.5 or (pd.notna(t10) and t10 <= -2): return "INVERSE"
    if t20 >= 2 and pd.notna(ic10) and ic10 > 0 and spread20 > 0: return "WORKS"
    if t20 >= 1 or (pd.notna(t10) and t10 >= 2): return "SOMETIMES WORKS"
    if t20 >= .5: return "COULD WORK"
    return "DOESN'T WORK"


def evaluate(sig, px, nifty, year):
    """Scores one signal for one stock in one calendar year. Returns a dict (verdict NO DATA when there is nothing to score)."""
    days = px.index[px.index.year == year]
    s_td = sig.reindex(px.index.union(sig.index)).ffill(limit=5).reindex(px.index)
    med = s_td.rolling(120, min_periods=60).median()
    res, hits = {}, None
    for h in HORIZONS:
        fwd = np.log(px.shift(-h) / px) - np.log(nifty.reindex(px.index).ffill().shift(-h) / nifty.reindex(px.index).ffill())
        d = pd.DataFrame({"sig": s_td, "fwd": fwd, "med": med}).loc[days].dropna()
        n_eff = len(d) / h
        ic = d["sig"].rank().corr(d["fwd"].rank()) if len(d) > 5 else np.nan           # Spearman: Pearson on ranks (pandas' own needs scipy)
        samp = d.iloc[::STEP]
        hi = samp[samp["sig"] > samp["med"]]["fwd"]; lo = samp[samp["sig"] <= samp["med"]]["fwd"]
        res[h] = dict(ic=ic, t=t_stat(ic, n_eff), n=len(samp), spread=float((hi.mean() - lo.mean()) * 100) if len(hi) and len(lo) else np.nan,
                      hit=float((((samp["sig"] > samp["med"]) == (samp["fwd"] > 0)).mean()) * 100) if len(samp) else np.nan)
    r10, r20 = res[10], res[20]
    v = verdict(r10["t"], r20["t"], r10["ic"], r20["spread"] if pd.notna(r20["spread"]) else 0.0, r20["n"])
    return dict(verdict=v, n=r20["n"], ic10=r10["ic"], ic20=r20["ic"], t10=r10["t"], t20=r20["t"], spread20=r20["spread"], hit20=r20["hit"])


def run(gen_by_stock, iexp, prices, years=YEARS, proxy_notes=None):
    """The whole backtest. gen_by_stock: {ticker: daily Series or None}; iexp: daily Series (Rs/MWh) or None; prices: DataFrame by Yahoo symbol."""
    if prices is None or NIFTY not in prices: return None
    out = {"years": {}, "rules": RULES, "ideas": IDEAS, "signals": {k: d for k, d, _ in SIGNALS}, "asof": f"{prices.index.max():%Y-%m-%d}",
           "prices_from": f"{prices.index.min():%Y-%m-%d}"}
    sigs = {t: make_signals(gen_by_stock.get(t), iexp) for t, _, _ in STOCKS}
    proxy_notes = PROXY_NOTES if proxy_notes is None else proxy_notes
    for y in years:
        rows = []
        for ticker, owner, sym in STOCKS:
            for key, label, need in SIGNALS:
                sig = sigs[ticker].get(key); px = prices[sym].dropna() if sym in prices else None
                if sig is None or px is None or not len(px[px.index.year == y]):
                    why = "no generation series for this company in the CEA conventional report" if need in ("gen", "both") and gen_by_stock.get(ticker) is None else "no data"
                    rows.append(dict(stock=ticker, signal=key, label=label, verdict="NO DATA", note=why)); continue
                r = evaluate(sig, px, prices[NIFTY].dropna(), y); r.update(stock=ticker, signal=key, label=label, note="")
                if r["verdict"] == "NO DATA": r["note"] = "fewer than 8 usable dates this year (year-on-year signals need a year of history first)"
                elif need in ("gen", "both") and ticker in proxy_notes: r["note"] = proxy_notes[ticker]
                rows.append(r)
        scored = [r for r in rows if r["verdict"] != "NO DATA"]
        counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}
        out["years"][str(y)] = dict(rows=rows, counts=counts, tests=len(scored), chance=round(len(scored) * 0.023, 1),
                                    partial=bool(y == max(years) and prices.index.max().year == y), last=f"{prices.index.max():%Y-%m-%d}")
    return out


# ------------------------------------------------------------------ glue for the build
def load_and_run(root, today, log=print):
    """What run.py calls. Any failure leaves the rest of the site untouched."""
    try:
        import power
        prices = refresh_prices(root, today, log=log)
        iex_path = os.path.join(root, "power", "iex_dam.csv")
        iexp = None
        if os.path.exists(iex_path):
            d = pd.read_csv(iex_path, parse_dates=["date"]).dropna(subset=["wmcp"]); iexp = d.set_index("date")["wmcp"]
        owner = power._read(os.path.join(root, "power", "owner.csv"), power.OWNER_COLS)
        fleet = power._read(os.path.join(root, "power", "fleet.csv"), power.FLEET_COLS)
        series = power.daily_series(fleet) if len(fleet) else {}
        gen = {}
        for ticker, name, _ in STOCKS:
            g = series.get(PROXIES[ticker]) if ticker in PROXIES else (owner[owner["owner"] == name].groupby("date")["actual_mu"].sum() if name else None)
            if g is not None and len(g): g.index = pd.to_datetime(g.index)
            gen[ticker] = g if g is not None and len(g) else None
        res = run(gen, iexp, prices)
        log("backtest: " + (f"{sum(y['tests'] for y in res['years'].values())} tests scored" if res else "no price data yet"))
        return res
    except Exception as e:
        log(f"backtest: skipped ({type(e).__name__}: {e})")
        return None


# ------------------------------------------------------------------ thresholds and the summary shown on the page
BANDS = [(-99, -1, "below -1"), (-1, 0, "-1 to 0"), (0, 1, "0 to +1"), (1, 99, "above +1")]
CUTS = (0.0, 0.5, 1.0, 1.5)


def _samples(gen_by_stock, iexp, prices, first_year=2024):
    """Every fifth trading day from first_year: the signal as a z-score against its own past year, and the 20-day return over Nifty."""
    rows = []
    for ticker, _, sym in STOCKS:
        if sym not in prices: continue
        px = prices[sym].dropna(); nf = prices[NIFTY].dropna().reindex(px.index).ffill()
        fwd = np.log(px.shift(-20) / px) - np.log(nf.shift(-20) / nf)
        for key, s in make_signals(gen_by_stock.get(ticker), iexp).items():
            s_td = s.reindex(px.index.union(s.index)).ffill(limit=5).reindex(px.index)
            z = s_td if key == "BOTH" else zscore(s_td)
            d = pd.DataFrame({"z": z, "f": fwd}).dropna(); d = d[d.index.year >= first_year].iloc[::STEP]
            d["stock"], d["sig"] = ticker, key; rows.append(d)
    return pd.concat(rows) if rows else pd.DataFrame(columns=["z", "f", "stock", "sig"])


def thresholds(gen_by_stock, iexp, prices):
    """Per signal, pooled over the five stocks and 2024 onward: mean 20-day excess return by signal band, and the best cut-off.
    se is the standard error of the difference between the groups, counting one independent observation per 20 trading days."""
    A = _samples(gen_by_stock, iexp, prices)
    out = {}
    sd = float(A["f"].std()) if len(A) else 0.0
    for key, _, _ in SIGNALS:
        x = A[A["sig"] == key]
        if len(x) < 40: continue
        bands = [dict(label=lab, n=int(((x.z > lo) & (x.z <= hi)).sum()), mean=float(x[(x.z > lo) & (x.z <= hi)]["f"].mean() * 100) if ((x.z > lo) & (x.z <= hi)).any() else None)
                 for lo, hi, lab in BANDS]
        cuts = []
        for c in CUTS:
            hi, lo = x[x.z > c]["f"], x[x.z <= c]["f"]
            if len(hi) < 10 or len(lo) < 10: continue
            se = sd * np.sqrt(1 / max(1, len(hi) * STEP / 20) + 1 / max(1, len(lo) * STEP / 20))
            cuts.append(dict(cut=c, n=int(len(hi)), above=float(hi.mean() * 100), below=float(lo.mean() * 100), diff=float((hi.mean() - lo.mean()) * 100), se=float(se * 100)))
        out[key] = dict(bands=bands, cuts=cuts, n=int(len(x)))
    return out


def summarise(res, thr):
    """The small panels: verdict counts by year, what held in more than one year, how each signal fared overall, and the threshold read."""
    years = list(res["years"])
    keep = ("WORKS", "SOMETIMES WORKS", "COULD WORK")
    held, by_sig = [], {}
    for i, r0 in enumerate(res["years"][years[0]]["rows"]):
        vs = [res["years"][y]["rows"][i] for y in years]
        pos = [r for r in vs if r["verdict"] in keep]
        neg = [r for r in vs if r["verdict"] == "INVERSE"]
        if len(pos) >= 2: held.append(dict(stock=r0["stock"], signal=r0["signal"], years=[y for y, r in zip(years, vs) if r["verdict"] in keep], against=[y for y, r in zip(years, vs) if r["verdict"] == "INVERSE"]))
        b = by_sig.setdefault(r0["signal"], dict(positive=0, flat=0, inverse=0, nodata=0))
        for r in vs:
            b["positive" if r["verdict"] in ("WORKS", "SOMETIMES WORKS") else "inverse" if r["verdict"] == "INVERSE" else "nodata" if r["verdict"] == "NO DATA" else "flat"] += 1
    best = []
    for key, t in thr.items():
        for c in t["cuts"]:
            best.append(dict(signal=key, **c, z=c["diff"] / c["se"] if c["se"] else 0.0))
    best.sort(key=lambda r: -abs(r["z"]))
    return dict(years={y: res["years"][y]["counts"] | {"tests": res["years"][y]["tests"], "chance": res["years"][y]["chance"]} for y in years},
                held=held, by_signal=by_sig, thresholds=thr, strongest=best[:3], signals=res["signals"], asof=res["asof"], prices_from=res["prices_from"],
                partial=res["years"][years[-1]]["partial"], strong_enough=bool(best and abs(best[0]["z"]) >= 2))


SAVED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "backtest_results.json")


def load_saved(path=SAVED):
    try:
        with open(path) as f: return json.load(f)
    except (OSError, ValueError):
        return None


def main(root="data", today=None):
    import datetime as dt
    today = today or dt.date.today()
    import power
    prices = refresh_prices(root, today)
    res = load_and_run(root, today)
    if not res: raise SystemExit("no results: needs prices and the power dataset in " + root)
    iex = pd.read_csv(os.path.join(root, "power", "iex_dam.csv"), parse_dates=["date"]).dropna(subset=["wmcp"]).set_index("date")["wmcp"]
    owner = power._read(os.path.join(root, "power", "owner.csv"), power.OWNER_COLS); series = power.daily_series(power._read(os.path.join(root, "power", "fleet.csv"), power.FLEET_COLS))
    gen = {}
    for t, name, _ in STOCKS:
        g = series.get(PROXIES[t]) if t in PROXIES else (owner[owner["owner"] == name].groupby("date")["actual_mu"].sum() if name else None)
        if g is not None and len(g): g = g.copy(); g.index = pd.to_datetime(g.index)
        gen[t] = g if g is not None and len(g) else None
    out = summarise(res, thresholds(gen, iex, prices)); out["generated"] = f"{today:%Y-%m-%d}"
    os.makedirs(os.path.dirname(SAVED), exist_ok=True)
    with open(SAVED, "w") as f: json.dump(out, f, indent=1, default=float)
    print("wrote", SAVED)


if __name__ == "__main__":
    main()
