import numpy as np
import pandas as pd
import patterns as P
import ranges as R


def sim(O, H, L, C, **k):
    f = lambda x: np.array(x, float)
    return R.simulate(f(O), f(H), f(L), f(C), **k)


def test_a_stopped_long_loses_one_r_and_a_gap_through_the_stop_loses_more():
    # entry at the open of bar 1 (100), stop 95: risk 5. The next bar's low touches 94: out at the stop, -1R.
    r = sim([99, 100, 99], [101, 102, 99], [98, 99, 94], [100, 101, 95], i=1, side=1, stop=95)
    assert round(r, 6) == -1.0
    # a gap down through the stop fills at the open, worse than -1R
    r = sim([99, 100, 90], [101, 102, 92], [98, 99, 89], [100, 101, 91], i=1, side=1, stop=95)
    assert round(r, 6) == -2.0


def test_a_trailing_exit_rides_a_trend_and_the_target_exit_takes_the_measured_move():
    n = 40; c = 100 + np.arange(n) * 1.0; o = c - 0.2; h = c + 0.5; l = c - 0.5
    c2 = c.copy(); c2[-1] = c[-5] - 5                                                          # the trend ends with a drop below the trailing low on the last bar
    r_trail = R.simulate(o, h, l, c2, i=1, side=1, stop=95.0, exit_mode="trail", trail_n=5, max_hold=60)
    assert r_trail > 4                                                                         # a long ride against a 5-point risk
    r_target = R.simulate(o, h, l, c, i=1, side=1, stop=95.0, target=110.0, exit_mode="target")
    assert round(r_target, 6) == round((110 - o[1]) / (o[1] - 95), 6)
    assert R.simulate(o, h, l, c, i=1, side=1, stop=150.0) is None                           # a stop above the entry is not a long


def test_a_short_is_the_mirror_image():
    r = sim([101, 100, 101], [102, 101, 106], [99, 98, 100], [100, 99, 105], i=1, side=-1, stop=105)
    assert round(r, 6) == -1.0


def test_stats_report_win_rate_average_win_and_loss_and_expectancy():
    s = R.stats([5.0, -1.0, -1.0, -1.0, 4.5])
    assert s["n"] == 5 and s["win"] == 40.0 and round(s["avg_win"], 6) == 4.75 and s["avg_loss"] == -1.0 and round(s["exp"], 6) == 1.3 and s["p4"] == 40.0


def synthetic_range(n=170, bottom=100.0, top=115.0, breakout=True):
    """A prior decline, then a range between 100 and 115 with three touches of the top and four of the bottom, then a close through the top."""
    c = list(np.linspace(150, 108, 60))
    pattern = [108, 114, 110, 101, 106, 114.5, 109, 100.5, 106, 114, 108, 101, 107, 113, 109, 106, 108, 110, 108, 109]
    for v in pattern:
        c += [v] * 4
    c = np.array(c[:n - 8] if breakout else c, float)
    if breakout: c = np.concatenate([c, [116.5, 118, 119, 121, 122, 123, 125, 126]])
    h = c + 0.4; l = c - 0.4
    for i in range(len(c)):                                                                       # make the touches real swing extremes
        if abs(c[i] - 114) <= 1 and c[i] > 113: h[i] = top
        if abs(c[i] - 100.5) <= 1: l[i] = bottom
    return c, h, l


def test_a_well_defined_range_breakout_is_found_with_its_trade_plan():
    c, h, l = synthetic_range()
    r = R.find_range(h, l, c, P.DAILY)
    assert r is not None and r["status"] == "BREAKOUT" and r["side"] == 1
    assert r["nt"] >= 3 and r["nb"] >= 2 and r["switches"] >= 3 and r["crossings"] >= 4
    assert r["prior"] == "down" and r["cont"] is False                                         # a break up out of a range that followed a decline reverses the trend
    assert r["stop_mid"] == r["mid"] and abs(r["target"] - (r["level"] + r["height"])) < 1e-9
    assert 7 <= r["height_pct"] <= 40


def test_a_drifting_series_and_a_range_with_one_touch_are_not_ranges():
    n = 170; drift = np.linspace(100, 160, n)
    assert R.find_range(drift + 0.4, drift - 0.4, drift, P.DAILY) is None
    c = np.concatenate([np.full(60, 100.0), np.linspace(100, 112, 40), np.full(70, 112.0)])
    assert R.find_range(c + 0.3, c - 0.3, c, P.DAILY) is None
