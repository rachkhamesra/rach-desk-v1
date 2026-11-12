import numpy as np, pandas as pd
import shorts, webpage


def world(n=300, seed=1):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-09-01", periods=n)
    syms = ["FLAT", "FALLS", "BUILD", "OTHER"]
    nifty = pd.Series(100 * np.cumprod(1 + rng.normal(.0004, .006, n)), index=dates)
    C = pd.DataFrame({s: 100 * np.cumprod(1 + rng.normal(.0004, .01, n)) for s in syms}, index=dates)
    fall = np.r_[np.ones(n - 70), np.cumprod(np.full(70, .985))]
    C["FALLS"] = C["FALLS"] * fall                         # a steady slide over the last 70 sessions: behind Nifty, below its averages
    C.iloc[-1, C.columns.get_loc("BUILD")] = C.iloc[-4, C.columns.get_loc("BUILD")] * .94         # down 6% over three sessions
    oi = pd.DataFrame(1e6, index=dates, columns=syms); oi.iloc[-1, oi.columns.get_loc("BUILD")] = 1.2e6
    RAT = pd.DataFrame(1.5, index=dates, columns=syms)
    ma = {n_: C.rolling(n_, min_periods=n_).mean() for n_ in (50, 100)}
    DQ = pd.DataFrame(rng.uniform(1e5, 3e5, (n, len(syms))), index=dates, columns=syms)
    dcode = np.sign(C.pct_change().fillna(0))
    return dict(C=C, H=C * 1.01, L=C * .99, O=C.shift(1).fillna(C), DQ=DQ, dcode=dcode, RAT=RAT, OIadj=oi, nifty=nifty, ma=ma, memberships={"fo": syms}, N=n, T=n - 1, dates=list(dates))


def test_screens_flag_the_stocks_they_should():
    M = world(); out = shorts.build(M)
    assert out and set(out["screens"]) == {k for k, _, _ in shorts.SCREENS}
    assert "FALLS" in set(out["screens"]["laggards"]["rows"].sym) and "FALLS" in set(out["screens"]["cash_selling"]["rows"].sym)
    assert "BUILD" in set(out["screens"]["buildup"]["rows"].sym) and "FLAT" not in set(out["screens"]["buildup"]["rows"].sym)
    conf = out["confluence"]; assert conf.iloc[0]["count"] >= 2 and "FALLS" in set(conf.sym)


def test_replay_counts_each_stock_once_per_window_and_hides_small_samples():
    M = world(); C = M["C"]
    flag = pd.DataFrame(False, index=C.index, columns=C.columns); flag.iloc[100:130, 0] = True            # 30 consecutive flags on one stock
    r = shorts.replay(flag, C, M["nifty"])
    assert r["n"] == 3 and r["avg"] is None                                      # one per 10-session window, and three is too few to read
    flag.iloc[:, :] = True; assert shorts.replay(flag, C, M["nifty"])["avg"] is not None


def test_no_history_or_no_fo_universe_gives_nothing():
    M = world(); M["N"] = 40; assert shorts.build(M) is None
    M = world(); M["memberships"] = {"fo": []}; assert shorts.build(M) is None


def test_the_tab_renders_with_the_experimental_badge_and_every_screen():
    M = world(); M["unresolved"] = set(); M["shorts"] = shorts.build(M); M["results"] = []
    html = webpage.tab_shorts(M)
    assert "EXPERIMENTAL" in html and "Short Ideas" in html
    for _, title, _ in shorts.SCREENS: assert title in html
    assert html.count('class="subview"') + html.count("class=\"subview\"") >= 1 and "Replay:" in html
    assert "need an F&amp;O universe" in webpage.tab_shorts({"shorts": None})


def test_every_flagged_stock_gets_a_chart_with_its_screens_marked():
    M = world(); M["unresolved"] = set(); M["results"] = []; M["shorts"] = shorts.build(M)
    X = M["shorts"]; assert "FALLS" in X["charts"] and len(X["charts"]["FALLS"]["close"]) == len(X["charts"]["FALLS"]["dates"]) <= shorts.CHART_DAYS
    fl = X["charts"]["FALLS"]["flags"]["laggards"]; n = len(X["charts"]["FALLS"]["close"])
    assert fl and fl[-1] == n - 1 and min(fl) >= n - shorts.RECENT_DAYS                       # only the latest sessions are marked, never older ones      # flagged today = last session
    html = webpage.tab_shorts(M)
    assert html.count('class="shsvg"') >= 3 and 'class="shgrid"' in html and "shaded bars and dots mark only the last 10" in html
    assert 'fill="#b58cff" opacity=".24"' in html                      # laggard bars are drawn
    assert "DELIVERED SHARES" in html and html.count("<polyline") >= 3


def test_congestion_zones_find_where_price_spent_its_time():
    rng = np.random.default_rng(3); n = 250
    mid = np.r_[np.full(120, 121.0), np.linspace(121, 101, 10), np.full(100, 101.0), np.linspace(101, 110, 20)]
    close = mid + rng.normal(0, .3, n); H, L = close + 1, close - 1
    z = shorts.congestion_zones(H, L, np.full(n, 1e5), float(close[-1]))
    assert z["support"] and z["resistance"]
    assert 99 <= z["support"][0]["lo"] <= 102 and 100 <= z["support"][0]["hi"] <= 104          # the 101 shelf below the 110 close
    assert 118 <= z["resistance"][0]["lo"] <= 122 and z["resistance"][0]["hi"] >= 121           # the old 121 shelf above it
    assert z["support"][0]["hi"] < float(close[-1]) < z["resistance"][0]["lo"]
    assert shorts.congestion_zones(H[:20], L[:20], np.full(20, 1e5), 100.0) == {"support": [], "resistance": []}   # too little history to say


def test_charts_carry_candles_delivery_and_zones():
    M = world(); X = shorts.build(M); ch = X["charts"]["FALLS"]
    for k in ("open", "high", "low", "close", "dq", "dqavg", "dc", "ma50", "ma100", "zones"): assert k in ch
    assert len(ch["open"]) == len(ch["dq"]) == len(ch["close"]) and set(ch["zones"]) == {"support", "resistance"}
