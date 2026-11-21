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
    C = pd.DataFrame({"ASC": Ca, "DESC": Cd, "RECT": Cr, "TREND": Ct}, index=dates)
    H = pd.DataFrame({"ASC": Ha, "DESC": Hd, "RECT": Hr, "TREND": Ct * 1.01}, index=dates); L = pd.DataFrame({"ASC": La, "DESC": Ld, "RECT": Lr, "TREND": Ct * .99}, index=dates)
    ones = pd.DataFrame(1.0, index=dates, columns=syms)
    return dict(C=C, H=H, L=L, O=C.shift(1).fillna(C), DQ=ones * 1e5, TQ=ones * 5e6, dcode=np.sign(C.pct_change().fillna(0)), RAT=ones * 1.1, nifty=pd.Series(np.linspace(100, 120, n), index=dates),
                dates=list(dates), syms=syms, memberships={"fo": ["ASC"]}, N=n, T=n - 1, ma={50: C.rolling(50).mean(), 100: C.rolling(100).mean()}, unresolved=set())


def test_build_scans_the_universe_and_charts_each_find():
    M = world(); out = P.build(M)
    assert out["scanned"] == 4 and {r["sym"] for r in out["found"]["ascending"]} == {"ASC"} and {r["sym"] for r in out["found"]["descending"]} == {"DESC"}
    assert "RECT" in {r["sym"] for r in out["found"]["rectangle"]} and "TREND" not in {r["sym"] for k in out["found"] for r in out["found"][k]}
    asc = out["found"]["ascending"][0]; assert asc["fo"] is True and asc["turnover"] > 0
    ch = out["charts"]["ASC"]; pat = ch["patterns"]["ascending"]
    assert len(ch["close"]) == len(ch["dq"]) and len(pat["lines"]) == 2 and all(0 <= ln["a"][0] <= ln["b"][0] <= len(ch["close"]) - 1 for ln in pat["lines"])
    M["N"] = 50; assert P.build(M) is None                                               # too little history to scan
    M = world(); M["TQ"] = M["TQ"] * 0 + 1; assert P.build(M)["scanned"] == 0            # thin stocks are left out


def test_the_tab_has_three_subtabs_with_rules_filters_tables_and_charts():
    M = world(); M["patterns"] = P.build(M); M["results"] = []
    html = webpage.tab_patterns(M)
    for t in ("ASCENDING TRIANGLE", "DESCENDING TRIANGLE", "RECTANGLE", "EXPERIMENTAL", "HOW THIS PATTERN IS DEFINED"): assert t in html
    assert html.count('class="subview"') == 3 and html.count("<svg") >= 3 and 'class="ptchip' in html and 'data-fo="1"' in html and "TARGET" in html
    assert "need about 120 sessions" in webpage.tab_patterns({"patterns": None})


def test_signal_confluence_is_archived_and_credit_desk_renamed():
    assert "signals" in webpage.ARCHIVED_TABS
    html = webpage.render.__doc__ or ""
    import inspect; src = inspect.getsource(webpage.render)
    assert "PEER RADAR" in src and "TECHNICAL PATTERNS" in src and "k not in archived" in src
