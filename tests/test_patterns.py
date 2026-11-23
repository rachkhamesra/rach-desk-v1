import numpy as np, pandas as pd
import patterns as P, webpage


def osc(n, top, bottom, period=28, noise=.4, seed=1):
    """A price that swings between bottom(t) and top(t) (functions of t): close, high, low."""
    rng = np.random.default_rng(seed); t = np.arange(n)
    hi, lo = top(t), bottom(t); mid = (hi + lo) / 2; amp = (hi - lo) / 2 * .96
    c = mid + amp * np.sin(2 * np.pi * t / period - np.pi / 2) * -1 + rng.normal(0, noise, n)
    return c + .6, c - .6, c                                  # high, low, close


def ascending(n=190, end=None):
    H, L, C = osc(n, lambda t: np.full(n, 100.0), lambda t: 52 + 40 * t / n, period=34)
    if end is not None: C = C.copy(); C[-3:] = end; H = np.maximum(H, C + .5); L = np.minimum(L, C - .5)
    return H, L, C


def test_ascending_triangle_is_found_with_its_target():
    H, L, C = ascending(); r = P.triangle(H, L, C, True)
    assert r and r["kind"] == "ascending" and 97 <= r["level"] <= 103 and r["touches_flat"] >= 2 and r["touches_line"] >= 3 and r["slope"] > 0
    assert abs(r["target"] - (r["level"] + r["height"])) < 1e-9 and r["height_pct"] > 20
    assert P.triangle(H, L, C, False) is None                                           # not mistaken for a descending triangle


def test_breakout_is_fresh_only_for_ten_sessions():
    H, L, C = ascending(end=106.5)                                                      # the last three closes are 6% through the top
    r = P.triangle(H, L, C, True); assert r and r["status"] == "BREAKOUT" and r["break_idx"] >= len(C) - P.RECENT
    H2, L2, C2 = ascending(); C2 = np.r_[C2, np.full(14, 107.0)]; H2 = np.r_[H2, np.full(14, 107.6)]; L2 = np.r_[L2, np.full(14, 106.4)]
    assert P.triangle(H2, L2, C2, True) is None                                          # it broke out two weeks ago: no longer a live pattern


def test_descending_triangle_mirrors_it():
    n = 190; H, L, C = osc(n, lambda t: 84 - 28 * t / n, lambda t: np.full(n, 60.0), period=34)
    r = P.triangle(H, L, C, False)
    assert r and r["kind"] == "descending" and 57 <= r["level"] <= 63 and r["slope"] < 0 and r["target"] < r["level"]
    assert P.triangle(H, L, C, True) is None
    C = C.copy(); C[-3:] = 55.0; L = np.minimum(L, C - .5)
    r = P.triangle(H, L, C, False); assert r and r["status"] == "BREAKDOWN"


def test_rectangle_needs_a_flat_top_and_a_flat_bottom():
    n = 170; H, L, C = osc(n, lambda t: np.full(n, 100.0), lambda t: np.full(n, 78.0), period=30)
    r = P.rectangle(H, L, C)
    assert r and r["kind"] == "rectangle" and 97 <= r["top"] <= 103 and 75 <= r["bottom"] <= 81 and r["touches_flat"] + r["touches_line"] >= 5 and 0 <= r["position"] <= 100
    assert P.triangle(H, L, C, True) is None and P.triangle(H, L, C, False) is None      # a range is not a triangle
    Ha, La, Ca = ascending(); assert P.rectangle(Ha, La, Ca) is None                    # rising lows are not a flat bottom


def test_a_trend_or_a_random_walk_is_not_a_pattern():
    t = np.arange(200); C = 50 * 1.006 ** t; H, L = C * 1.01, C * .99
    assert not any(P.scan(H, L, C).values())
    hits = 0
    for seed in range(40):
        c = 100 * np.cumprod(1 + np.random.default_rng(seed).normal(0, .016, 260)); hits += any(P.scan(c * 1.01, c * .99, c).values())
    assert 0 < hits <= 22          # about four in ten random paths contain some pattern by these rules: the page says so, and this keeps the rules from drifting looser


def world():
    n = 260; dates = pd.bdate_range("2025-09-01", periods=n); syms = ["ASC", "DESC", "RECT", "TREND"]
    Ha, La, Ca = ascending(n)
    Hd, Ld, Cd = osc(n, lambda t: 86 - 19 * t / n, lambda t: np.full(n, 60.0), period=34)
    Hr, Lr, Cr = osc(n, lambda t: np.full(n, 100.0), lambda t: np.full(n, 78.0), period=30)
    Ct = 50 * 1.004 ** np.arange(n)
    Ca = Ca.copy(); Ca[-3:] = 97.0; Cd = Cd.copy(); Cd[-3:] = 61.5; Cr = Cr.copy(); Cr[-3:] = 98.5          # each ends near its trigger, so each is charted
    Ha = np.maximum(Ha, Ca + .5); Hd = np.maximum(Hd, Cd + .5); Hr = np.maximum(Hr, Cr + .5)
    C = pd.DataFrame({"ASC": Ca, "DESC": Cd, "RECT": Cr, "TREND": Ct}, index=dates)
    H = pd.DataFrame({"ASC": Ha, "DESC": Hd, "RECT": Hr, "TREND": Ct * 1.01}, index=dates); L = pd.DataFrame({"ASC": La, "DESC": Ld, "RECT": Lr, "TREND": Ct * .99}, index=dates)
    ones = pd.DataFrame(1.0, index=dates, columns=syms)
    return dict(C=C, H=H, L=L, O=C.shift(1).fillna(C), DQ=ones * 1e5, TQ=ones * 5e6, dcode=np.sign(C.pct_change().fillna(0)), RAT=ones * 1.1, nifty=pd.Series(np.linspace(100, 120, n), index=dates),
                dates=list(dates), syms=syms, memberships={"fo": ["ASC"]}, N=n, T=n - 1, ma={50: C.rolling(50).mean(), 100: C.rolling(100).mean()}, unresolved=set())


def test_build_scans_the_universe_and_charts_each_find():
    M = world(); out = P.scan_timeframe(M)
    assert out["scanned"] == 4 and {r["sym"] for r in out["found"]["ascending"]} == {"ASC"} and {r["sym"] for r in out["found"]["descending"]} == {"DESC"}
    assert "RECT" in {r["sym"] for r in out["found"]["rectangle"]} and "TREND" not in {r["sym"] for k in out["found"] for r in out["found"][k]}
    asc = out["found"]["ascending"][0]; assert asc["fo"] is True and asc["turnover"] > 0
    ch = out["charts"]["ASC"]; pat = ch["patterns"]["ascending"]
    assert len(ch["close"]) == len(ch["dq"]) and len(pat["lines"]) == 2 and all(0 <= ln["a"][0] <= ln["b"][0] <= len(ch["close"]) - 1 for ln in pat["lines"])
    M["N"] = 50; assert P.scan_timeframe(M) is None                                               # too little history to scan
    M = world(); M["TQ"] = M["TQ"] * 0 + 1; assert P.scan_timeframe(M)["scanned"] == 0            # thin stocks are left out


def test_the_tab_has_three_subtabs_with_rules_filters_tables_and_charts():
    M = world(); M["patterns"] = P.build(M); M["results"] = []
    html = webpage.tab_patterns(M)
    for t in ("ASCENDING TRIANGLE", "DESCENDING TRIANGLE", "RECTANGLE", "EXPERIMENTAL", "HOW THIS PATTERN IS DEFINED"): assert t in html
    assert html.count('data-sub="ascending"') == 2 and html.count('data-sub="bases"') == 2 and html.count('data-sub="shorts"') == 2 and html.count("<svg") >= 3
    assert "BREAKOUT BASES" in html and "SHORT IDEAS" in html and 'id="p-bases"' in html          # the two former tabs now live here, with the base scanner's id kept for its filters and 'class="ptchip' in html and 'data-fo="1"' in html and "TARGET" in html
    assert "need about 120 sessions" in webpage.tab_patterns({"patterns": None})


def test_signal_confluence_is_archived_and_credit_desk_renamed():
    assert "signals" in webpage.ARCHIVED_TABS
    html = webpage.render.__doc__ or ""
    import inspect; src = inspect.getsource(webpage.render)
    assert "PEER RADAR" in src and "TECHNICAL PATTERNS" in src and "k not in archived" in src


def test_a_flat_level_touched_only_twice_is_not_enough():
    n = 190; H, L, C = ascending(n)
    assert P.triangle(H, L, C, True)["touches_flat"] >= 3
    ph = P.swings(H, high=True); keep = ph[:2]                                           # leave just two swing highs near the top
    assert len(P.clusters(keep)) == 1 and P.MIN_TOUCHES == 3                              # the cluster exists, but a triangle needs three
    H2 = H.copy()
    for i, _ in ph[2:]: H2[i - 3:i + 4] = np.minimum(H2[i - 3:i + 4], 90.0)               # flatten every later test of the top
    C2 = np.minimum(C, 89.0); assert P.triangle(H2, L, C2, True) is None


def weekly_world(weeks=150):
    """Five identical sessions per week, so the weekly candles are known exactly: an ascending triangle with a 14-week swing."""
    Hw, Lw, Cw = osc(weeks, lambda t: np.full(weeks, 100.0), lambda t: 52 + 40 * t / weeks, period=14, noise=.2)
    Cw = Cw.copy(); Cw[-2:] = 97.0; Hw = np.maximum(Hw, Cw + .5)
    n = weeks * 5; dates = pd.bdate_range("2024-01-01", periods=n); syms = ["ASCW", "TREND"]
    rep = lambda a: np.repeat(a, 5)
    C = pd.DataFrame({"ASCW": rep(Cw), "TREND": 50 * 1.003 ** np.arange(n)}, index=dates)
    H = pd.DataFrame({"ASCW": rep(Hw), "TREND": C["TREND"] * 1.01}, index=dates); L = pd.DataFrame({"ASCW": rep(Lw), "TREND": C["TREND"] * .99}, index=dates)
    ones = pd.DataFrame(1.0, index=dates, columns=syms)
    return dict(C=C, H=H, L=L, O=C.shift(1).fillna(C), DQ=ones * 1e5, TQ=ones * 5e6, dcode=np.sign(C.pct_change().fillna(0)), RAT=ones * 1.1, nifty=pd.Series(np.linspace(100, 130, n), index=dates),
                dates=list(dates), syms=syms, memberships={"fo": ["ASCW"]}, N=n, T=n - 1, ma={50: C.rolling(50).mean(), 100: C.rolling(100).mean()}, unresolved=set())


def test_weekly_candles_are_the_daily_ones_resampled():
    M = weekly_world(); S = P.series(M, P.WEEKLY); n = len(S["C"])
    assert n == 150 and all(b - a == 4 for a, b in S["where"])                          # five sessions a week
    s = "ASCW"; first, last = S["where"][40]
    assert S["O"][s].iloc[40] == M["O"][s].iloc[first] and S["C"][s].iloc[40] == M["C"][s].iloc[last]
    assert S["H"][s].iloc[40] == M["H"][s].iloc[first:last + 1].max() and S["L"][s].iloc[40] == M["L"][s].iloc[first:last + 1].min()
    assert S["DQ"][s].iloc[40] == M["DQ"][s].iloc[first:last + 1].sum()


def test_the_same_rules_find_the_same_pattern_on_weekly_candles():
    M = weekly_world(); out = P.build(M)
    w = out["weekly"]; assert w and w["cfg"].name == "weekly"
    rows = w["found"]["ascending"]; assert [r["sym"] for r in rows] == ["ASCW"] and rows[0]["tf"] == "weekly" and 97 <= rows[0]["level"] <= 103
    assert not any(w["found"][k] for k in ("descending",)) and "TREND" not in {r["sym"] for k in w["found"] for r in w["found"][k]}
    g = rows[0]["daily"]                                                                   # the same pattern, placed on the daily chart
    assert len(g["lines"]) == 2 and all(0 <= ln["a"][0] < ln["b"][0] < len(M["dates"]) for ln in g["lines"]) and g["touches"] and g["target"] > rows[0]["level"]
    ch = w["charts"]["ASCW"]; assert ch["ma_labels"] == [10, 30] and len(ch["close"]) <= P.WEEKLY.chart


def test_weekly_needs_enough_weeks_and_daily_results_are_unchanged():
    assert P.scan_timeframe(weekly_world(30), P.WEEKLY) is None and P.scan_timeframe(weekly_world(30), P.DAILY)          # 30 weeks is too few for the weekly rules, enough for daily
    M = world(); out = P.build(M); assert out["daily"] and {r["sym"] for r in out["daily"]["found"]["ascending"]} == {"ASC"}
    H, L, C = ascending(); assert P.triangle(H, L, C, True) == P.triangle(H, L, C, True, P.DAILY)


def test_every_screen_that_flags_a_stock_is_listed_for_its_page():
    import shorts
    M = world(); M["patterns"] = P.build(M); M["unresolved"] = set(); M["results"] = []
    M["shorts"] = {"screens": {"laggards": {"title": "LAGGARDS", "rows": pd.DataFrame([dict(sym="ASC", days=3)])}}}
    M["cash_accumulation"] = pd.DataFrame([dict(sym="ASC", days=2, ratio=1.4)]); M["cash_tracking"] = pd.DataFrame(columns=["sym", "days", "ratio"])
    M["breakout_bases"] = pd.DataFrame([dict(sym="ASC", stage="near")]); M["high52"] = pd.DataFrame([dict(sym="ASC", close_from_high=-1.5)])
    out = webpage.screen_flags(M)
    labels = [f["l"] for f in out["ASC"]["fl"]]
    assert any(l.startswith("ASCENDING TRIANGLE · DAILY") for l in labels) and "SHORT IDEAS · LAGGARDS" in labels and "CASH ACCUMULATION · CONFIRMED" in labels
    assert "BREAKOUT BASE · NEAR" in labels and "52-WEEK HIGH" in labels
    pat = [f for f in out["ASC"]["fl"] if f["g"] == "pattern"][0]; assert pat["tab"] == "patterns" and pat["sub"] == "ascending" and pat["tf"] == "daily" and pat["d"]
    g = out["ASC"]["pt"][0]; assert g["tf"] == "d" and g["k"] == "ascending" and len(g["lines"]) == 2 and g["th"] and g["tg"] > 0        # geometry for the side-panel chart
    assert "br" in g and g["d"] and (g["br"] is None or 0 <= g["br"] < len(M["dates"]))                          # where the break happened, and the text under the chart
    assert "TREND" not in out                                                                  # a stock nothing flags has no entry


def test_stocks_without_futures_send_no_open_interest():
    assert webpage.oi_series(pd.Series([np.nan, np.nan, np.nan])) == []
    assert webpage.oi_series(pd.Series([np.nan, 12.0, 15.0])) == [None, 12, 15]


def test_breakout_bases_and_short_ideas_are_no_longer_top_level_tabs():
    import inspect
    src = inspect.getsource(webpage.render)
    assert '("bases", "BREAKOUT BASES"' not in src and '("shorts", "SHORT IDEAS"' not in src
    M = world(); M["unresolved"] = set(); M["results"] = []
    M["breakout_bases"] = pd.DataFrame([dict(sym="ASC", stage="near")]); M["shorts"] = None
    out = webpage.screen_flags(M | {"patterns": None, "cash_accumulation": None, "cash_tracking": None, "high52": pd.DataFrame()})
    base = out["ASC"]["fl"][0]; assert base["tab"] == "patterns" and base["sub"] == "bases"
    M["patterns"] = P.build(M); M["shorts"] = {"screens": {"laggards": {"title": "LAGGARDS", "rows": pd.DataFrame([dict(sym="ASC", days=2)])}}}
    sh = [f for f in webpage.screen_flags(M | {"cash_accumulation": None, "cash_tracking": None, "high52": pd.DataFrame()})["ASC"]["fl"] if f["g"] == "short"][0]
    assert sh["tab"] == "patterns" and sh["sub"] == "shorts" and sh["sub2"] == "laggards"


def test_new_patterns_and_fresh_breaks_are_marked_against_the_previous_session():
    M = world(); out = P.build(M)
    d = out["daily"]; assert d["compared"] and set(d["changes"]) == {"new", "broke"}
    assert all("event" in r for rows in d["found"].values() for r in rows)
    prev = P.previous_view(M); assert len(prev["C"]) == len(M["C"]) - 1 and prev["T"] == M["T"] - 1 and prev["dates"][-1] < M["dates"][-1]
    # a stock that set up one session ago and breaks today is BROKE; one that was not there yesterday is NEW
    H, L, C = ascending(end=None); n = len(C)
    before = {"found": {"ascending": [dict(sym="X", status="SETUP")], "descending": [], "rectangle": []}}
    cur = {"found": {"ascending": [dict(sym="X", status="BREAKOUT", event=None), dict(sym="Y", status="SETUP", event=None)], "descending": [], "rectangle": []}}
    counts = P.mark_changes(cur, before)
    assert cur["found"]["ascending"][0]["event"] == "BROKE" and cur["found"]["ascending"][1]["event"] == "NEW" and counts == {"new": 1, "broke": 1}
    cur2 = {"found": {"ascending": [dict(sym="X", status="BREAKOUT", event=None)], "descending": [], "rectangle": []}}
    assert P.mark_changes(cur2, None) == {"new": 0, "broke": 0} and cur2["found"]["ascending"][0]["event"] is None     # nothing to compare with: nothing marked
    M["N"] = 100; assert P.previous_view(M)["N"] == 99


def test_conviction_scores_a_fresh_confirmed_leaning_break_highest():
    base = dict(kind="ascending", status="BREAKOUT", ratio=2.0, rs3m=15.0, sym="X")
    assert P.conviction(base, {"X": {1}}) == 5                                          # fresh break, delivery, relative strength and the other timeframe agree
    assert P.conviction(base, {}) == 4 and P.conviction({**base, "ratio": 0.8}, {}) == 3 and P.conviction({**base, "rs3m": -5.0}, {}) == 3
    assert P.conviction({**base, "status": "FORMING", "ratio": 0.5, "rs3m": -1.0}, {}) == 0
    assert P.conviction({**base, "kind": "descending", "status": "BREAKDOWN", "rs3m": -9.0}, {"X": {-1}}) == 5      # for a pattern that points down, weakness is what agrees
    assert P.conviction({**base, "kind": "rectangle", "status": "IN RANGE"}, {"X": {1}}) == 1                        # a range with no lean gets only its delivery point
    M = world(); out = P.build(M)
    for rows in out["daily"]["found"].values():
        assert all(0 <= r["conv"] <= 5 for r in rows)
        by = {}
        for r in rows: by.setdefault(r["status"], []).append(r["conv"])
        assert all(v == sorted(v, reverse=True) for v in by.values())                   # within a status, higher conviction comes first


def fake_replay(n=40, avg=3.2, base=0.4):
    h = lambda n_, a: dict(n=n_, avg=a, median=a - 1.0, right=58.0, n_conf=n_ // 2, avg_conf=5.1, median_conf=3.0, right_conf=67.0)
    grp = lambda n_, a: dict(found=n_, **{k: h(n_, a) for k in ("10", "20", "40", "60")})
    bs = lambda a: dict(n=9000, avg=a, median=a - 0.5, up=51.0)
    return dict(generated="2026-11-22", sessions=514, asof="2026-11-20", horizons=[10, 20, 40, 60], step=5, total=100, baseline={k: bs(base) for k in ("10", "20", "40", "60")},
                groups={"daily|ascending|BREAKOUT": grp(n, avg), "weekly|ascending|BREAKOUT": grp(6, 1.0), "daily|rectangle|BREAKOUT": grp(30, -1.0), "daily|rectangle|BREAKDOWN": grp(20, -2.5)})


def test_the_tab_shows_a_digest_badges_a_score_column_and_the_replay():
    M = world(); M["patterns"] = P.build(M); M["results"] = []; M["pattern_replay"] = fake_replay()
    html = webpage.tab_patterns(M)
    assert "SINCE THE PREVIOUS SESSION" in html and 'id="pt-wl"' in html and "Short Ideas:" in html
    assert "SCORE" in html and 'data-ev="' in html
    assert "Replay · past daily breakouts on high delivery" in html and "HIGH-DELIVERY BREAKS" in html and "ALL BREAKS" in html
    assert "~1 month" in html and "~2 months" in html and "~3 months" in html                                                    # three horizons
    assert "+5.1%" in html and "+3.0%" in html and "67%" in html                                                                  # the high-delivery breaks lead: average, median, share that went up
    assert "+3.2%" in html and "+2.2%" in html and "+0.4%" in html and "51% up" in html                                          # all breaks, and the average stock, beside them
    assert "too few with that much follow-up to read" in html                                                                    # six weekly breaks: said, not hidden
    assert "past daily breakdowns" in html and "WENT DOWN" in html                                                               # a rectangle is replayed both ways
    M["pattern_replay"] = None; assert "Replay ·" not in webpage.tab_patterns(M)


def test_flags_carry_the_event_so_the_watchlist_can_show_what_is_new():
    M = world(); M["patterns"] = P.build(M); M["unresolved"] = set(); M["results"] = []
    M["shorts"] = {"screens": {"laggards": {"title": "LAGGARDS", "rows": pd.DataFrame([dict(sym="ASC", days=1, new=True)])}}}
    out = webpage.screen_flags(M | {"cash_accumulation": None, "cash_tracking": None, "high52": pd.DataFrame(), "breakout_bases": pd.DataFrame()})
    fl = out["ASC"]["fl"]; assert any(f["g"] == "short" and f["ev"] == "NEW" for f in fl) and all("ev" in f for f in fl if f["g"] in ("pattern", "short"))


def test_high_delivery_is_judged_on_the_break_session_and_leads_the_tables():
    out = P.scan_timeframe(world(), P.DAILY)
    for rows in out["found"].values():
        for r in rows:
            assert "brk_ratio" in r and "confirmed" in r
            if r["status"] not in ("BREAKOUT", "BREAKDOWN"): assert r["confirmed"] is False                     # nothing to confirm before a break
    brk = {"kind": "ascending", "status": "BREAKOUT", "ratio": 0.8, "rs3m": 5.0, "sym": "X", "brk_ratio": 2.0}
    assert P.conviction(brk, {}) == 4                                                          # fresh break 2, delivery on the break itself 1, relative strength 1: the latest day's 0.8x does not count against it
    assert P.conviction({**brk, "brk_ratio": 0.9, "ratio": 3.0}, {}) == 3                       # high delivery today does not rescue a break on ordinary delivery
    M = world(); col = M["C"].columns.get_loc("ASC")
    M["C"] = M["C"].copy(); M["C"].iloc[-3:, col] = 108.0; M["H"] = np.maximum(M["H"], M["C"] + .5)             # a break three sessions ago
    M["ma"] = {50: M["C"].rolling(50).mean(), 100: M["C"].rolling(100).mean()}
    ordinary = P.scan_timeframe(M, P.DAILY)["found"]["ascending"]
    asc = [r for r in ordinary if r["sym"] == "ASC"]
    assert asc and asc[0]["status"] == "BREAKOUT" and asc[0]["brk_ratio"] < P.CONFIRM and not asc[0]["confirmed"]
    M["DQ"] = M["DQ"].copy(); M["DQ"].iloc[-3, col] = 8e5                                                  # the break session itself: eight times the usual delivery
    out = P.build(M)["daily"]; asc = [r for r in out["found"]["ascending"] if r["sym"] == "ASC"]
    assert asc and asc[0]["brk_ratio"] >= P.CONFIRM and asc[0]["confirmed"]
    rows = out["found"]["ascending"]; breaks = [r for r in rows if r["status"] == "BREAKOUT"]
    assert [r["confirmed"] for r in breaks] == sorted([r["confirmed"] for r in breaks], reverse=True)         # confirmed breaks come first within the break status
    M["patterns"] = P.build(M); M["results"] = []; html = webpage.tab_patterns(M)
    assert "HIGH-DELIVERY BREAKS" in html and "DELIVERY ON THE BREAK" in html and "HIGH DELIVERY" in html and 'data-conf="1"' in html


def swings_reference(x, k, high):
    """The straightforward loop the vectorised version replaced."""
    out = []
    for i in range(k, len(x) - k):
        v = x[i]
        if np.isnan(v): continue
        left, right = x[i - k:i], x[i + 1:i + k + 1]
        if np.isnan(left).any() or np.isnan(right).any(): continue
        if high and v > left.max() and v >= right.max(): out.append((i, float(v)))
        if not high and v < left.min() and v <= right.min(): out.append((i, float(v)))
    return out


def clusters_reference(points, tol, min_gap):
    out, seen = [], set()
    for _, p0 in points:
        mem = tuple(m for m in points if abs(m[1] / p0 - 1) <= tol)
        if len(mem) < 2 or mem in seen or mem[-1][0] - mem[0][0] < min_gap: continue
        seen.add(mem); out.append((float(np.median([p for _, p in mem])), list(mem)))
    return out


def test_vectorised_swings_and_clusters_match_the_plain_loops_exactly():
    rng = np.random.default_rng(11)
    for trial in range(60):
        n = int(rng.integers(5, 400)); x = 100 * np.cumprod(1 + rng.normal(0, .02, n))
        if trial % 3 == 0: x[rng.integers(0, n, size=max(1, n // 20))] = np.nan                       # gaps
        if trial % 4 == 0: x = np.round(x, 0)                                                         # many ties, so flat tops and bottoms
        for k in (1, 2, 4):
            for high in (True, False):
                assert P.swings(x, k, high) == swings_reference(x, k, high), (trial, k, high)
        pts = P.swings(x, 2, True)
        for tol, gap in ((.02, 12), (.03, 5), (.05, 1)):
            assert P.clusters(pts, tol, gap) == clusters_reference(pts, tol, gap), (trial, tol, gap)
    assert P.swings([1.0, 2.0], 4, True) == [] and P.swings([], 2, False) == [] and P.clusters([(3, 10.0)], .02, 1) == []        # too short to have any


def test_a_flat_top_is_one_swing_at_its_first_bar():
    x = np.array([1, 2, 3, 5, 5, 5, 3, 2, 1], float)
    assert P.swings(x, 2, True) == [(3, 5.0)]                                                         # the plateau counts once, at its first bar


def test_touches_a_few_bars_apart_count_as_one_test_of_the_level():
    assert P.spaced([(0, 1.0), (6, 1.0), (20, 1.0), (24, 1.0), (40, 1.0)], 12) == [(0, 1.0), (20, 1.0), (40, 1.0)]
    # a flat top tested twice close together and once much later has two real touches, so no triangle or rectangle is built on it
    assert len(P.spaced([(409, 241.0), (403, 241.0)][::-1] + [(800, 241.0)], P.DAILY.gap)) == 2
