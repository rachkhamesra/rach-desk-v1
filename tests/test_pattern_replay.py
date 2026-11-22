import json
import numpy as np, pandas as pd
import pattern_replay as R, patterns as P
from test_patterns import osc, world


def make_M(n=330, breakout_at=200, drift_after=0.004, seed=5):
    """One stock builds an ascending triangle and then rises after a break at `breakout_at`; flat controls and a flat Nifty."""
    rng = np.random.default_rng(seed); dates = pd.bdate_range("2025-01-01", periods=n)
    H0, L0, C0 = osc(breakout_at, lambda t: np.full(breakout_at, 100.0), lambda t: 52 + 40 * t / breakout_at, period=30, noise=.2)
    after = C0[-1] * (1 + drift_after) ** np.arange(1, n - breakout_at + 1) * 1.07                                        # a gap through the top, then a steady climb
    close = np.r_[C0, after]
    C = pd.DataFrame({"UP": close, "FLAT": 80 + rng.normal(0, .3, n), "FLAT2": 60 + rng.normal(0, .3, n)}, index=dates)
    H = C * 1.005; L = C * .995; H["UP"] = np.r_[H0, after + .5]; L["UP"] = np.r_[L0, after - .5]
    ones = pd.DataFrame(1.0, index=dates, columns=C.columns)
    return dict(C=C, H=H, L=L, O=C.shift(1).fillna(C), DQ=ones * 1e5, TQ=ones * 5e6, dcode=np.sign(C.pct_change().fillna(0)), RAT=ones * 1.5, nifty=pd.Series(100.0, index=dates),
                dates=list(dates), syms=list(C.columns), memberships={"fo": []}, N=n, T=n - 1, ma={50: C.rolling(50).mean(), 100: C.rolling(100).mean()}, unresolved=set())


def test_horizons_include_a_quarter_and_the_medians_are_reported():
    assert R.HORIZONS == (10, 20, 40, 60)
    M = make_M(); ev = R.forward(M, R.events(M, "daily", workers=1, log=lambda *a: None))
    assert ev and all(e["sym"] == "UP" for e in ev if e["kind"] == "ascending")
    g = R.summarise(ev)["daily|ascending|BREAKOUT"]
    for h in R.HORIZONS: assert {"n", "avg", "median", "right", "n_conf", "avg_conf", "median_conf", "right_conf"} <= set(g[str(h)])
    assert g["20"]["avg"] > 0 and g["20"]["median"] > 0 and g["20"]["right"] == 100.0                                  # the planted climb follows the break
    assert g["10"]["n"] >= g["20"]["n"] >= g["40"]["n"] >= g["60"]["n"]                                               # later breaks have less follow-up, and are counted only where there is some


def test_each_break_is_counted_once_and_confirmation_uses_delivery():
    M = make_M(); ev = [e for e in R.events(M, "daily", workers=1, log=lambda *a: None) if e["kind"] == "ascending"]
    assert len({(e["sym"], e["t_day"]) for e in ev}) == len(ev)
    g = R.summarise(R.forward(M, ev))["daily|ascending|BREAKOUT"]
    assert g["20"]["n_conf"] == g["20"]["n"]                                                                          # delivery was 1.5x on every day here
    M["RAT"] = M["RAT"] * 0 + 0.5; g2 = R.summarise(R.forward(M, R.events(M, "daily", workers=1, log=lambda *a: None)))["daily|ascending|BREAKOUT"]
    assert g2["20"]["n_conf"] == 0 and g2["20"]["avg_conf"] is None


def test_the_baseline_is_the_average_liquid_stock_with_its_median():
    b = R.baseline(make_M(), step=5, start=120)
    for h in R.HORIZONS: assert b[str(h)]["n"] > 0 and {"avg", "median", "up"} <= set(b[str(h)])
    assert abs(b["20"]["avg"]) < 20


def test_the_saved_file_round_trips(tmp_path):
    assert R.load_saved(str(tmp_path / "none.json")) is None
    (tmp_path / "r.json").write_text(json.dumps({"groups": {}})); assert R.load_saved(str(tmp_path / "r.json")) == {"groups": {}}
