import numpy as np
import pandas as pd

import metrics
import webpage


def sample_market():
    dates = pd.bdate_range("2026-04-01", periods=140)
    wave = 105 + 3.5 * np.sin(np.arange(140) * 2 * np.pi / 20)
    wave[-20:] = 105 + 2 * np.sin(np.arange(20) * 2 * np.pi / 20)
    wave[-1] = 108.5
    close = pd.DataFrame({"BASE": wave}, index=dates)
    open_ = close.shift(1).fillna(close).add(.15)
    high = pd.DataFrame({"BASE": np.maximum(open_["BASE"], close["BASE"]) + 1}, index=dates)
    low = pd.DataFrame({"BASE": np.minimum(open_["BASE"], close["BASE"]) - 1}, index=dates)
    delivery = pd.DataFrame({"BASE": np.full(140, 1_000_000.0)}, index=dates)
    ratio = pd.DataFrame({"BASE": np.ones(140)}, index=dates)
    ratio.iloc[-2:, 0] = [1.35, 1.4]
    return dates, open_, high, low, close, delivery, ratio


def test_breakout_base_detects_near_breakout_with_delivery():
    dates, open_, high, low, close, delivery, ratio = sample_market()
    out = metrics.breakout_bases(close, high, low, delivery, ratio, ["BASE"], len(dates) - 1)
    assert len(out) == 1
    row = out.iloc[0]
    assert row.stage == "near"
    assert row.range_width <= 10
    assert row.touches >= 2
    assert row.delivery_days == 2


def test_breakout_base_page_has_three_stages_and_real_candles():
    dates, open_, high, low, close, delivery, ratio = sample_market()
    bases = metrics.breakout_bases(close, high, low, delivery, ratio, ["BASE"], len(dates) - 1)
    market = {"T": len(dates) - 1, "dates": list(dates), "O": open_, "H": high, "L": low, "C": close,
              "DQ": delivery, "RAT": ratio, "breakout_bases": bases, "unresolved": set(), "results": []}
    html = webpage.tab_breakout_bases(market)
    assert "NEAR BREAKOUT" in html and "FRESH BREAKOUT" in html and "BUILDING A BASE" in html
    assert "Candlestick consolidation chart for BASE" in html
    assert "basezone" in html and "basevol hot" in html
    assert "DELIVERY DAYS" in html
    assert 'data-base-filter="compression"' in html
    assert 'data-base-filter="delivery"' in html


def test_base_without_delivery_is_retained_for_optional_filtering():
    dates, open_, high, low, close, delivery, ratio = sample_market()
    ratio.iloc[:, 0] = 0.8
    delivery.iloc[-5:, 0] = 500_000
    out = metrics.breakout_bases(close, high, low, delivery, ratio, ["BASE"], len(dates) - 1)
    assert len(out) == 1
    assert not bool(out.iloc[0].delivery_ok)


def test_followthrough_measures_forward_returns_without_lookahead():
    dates, open_, high, low, close, delivery, ratio = sample_market()
    nifty = np.full(len(dates), 100.0)
    out = metrics.base_followthrough(close, high, low, delivery, ratio, ["BASE"], len(dates) - 1, nifty=nifty)
    assert len(out) and set(out.sym) == {"BASE"}
    row = out[out.r5.notna()].iloc[0]
    assert np.isclose(row.r5, close["BASE"].iloc[int(row.t) + 5] / close["BASE"].iloc[int(row.t)] * 100 - 100)
    assert np.isclose(row.x5, row.r5)                                   # flat benchmark, so excess equals the return
    last = out.sort_values("t").iloc[-1]
    assert np.isnan(last.r20) and last.fail20 is None        # the horizon has not happened yet
    assert (out.groupby("stage").t.diff().dropna() > 10).all()  # repeat appearances inside the cooldown are one signal
    cut = len(dates) - 30                                     # a shorter history gives identical earlier signals
    short = metrics.base_followthrough(close.iloc[:cut + 1], high.iloc[:cut + 1], low.iloc[:cut + 1],
                                       delivery.iloc[:cut + 1], ratio.iloc[:cut + 1], ["BASE"], cut, nifty=nifty[:cut + 1])
    early = out[out.t <= cut].reset_index(drop=True)[["t", "stage", "quality"]]
    assert early.equals(short[["t", "stage", "quality"]].reset_index(drop=True))
