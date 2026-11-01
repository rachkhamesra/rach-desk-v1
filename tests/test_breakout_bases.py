import numpy as np
import pandas as pd

import metrics
import webpage


def sample_market():
    dates = pd.bdate_range("2026-04-01", periods=140)
    wave = 105 + 5 * np.sin(np.arange(140) * 2 * np.pi / 20)
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
    assert row.range_width <= 18
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
