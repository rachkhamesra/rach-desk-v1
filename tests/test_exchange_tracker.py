import pandas as pd

import exchange_tracker
import webpage


def test_build_uses_same_weekday_and_monthly_average():
    dates = pd.bdate_range("2025-01-01", periods=50)
    history = pd.DataFrame({"date": dates, "premium_turnover_cr": range(100, 150)})
    prices = pd.Series(range(500, 550), index=dates)
    out = exchange_tracker.build(history, prices)
    assert out["available"]
    assert out["asof"] == dates[-1]
    assert out["same_weekday"].iloc[-1].date == dates[-1]
    assert out["monthly"].iloc[-1]["count"] > 0
    assert len(out["commentary"]) == 3
    html = webpage.tab_exchange({"exchange_tracker": out})
    assert "5D ROLLING PREMIUM TURNOVER" in html
    assert "AVERAGE DAILY PREMIUM TURNOVER" in html


def test_build_handles_empty_history():
    out = exchange_tracker.build(pd.DataFrame(), pd.Series(dtype=float))
    assert not out["available"]
