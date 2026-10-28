import pandas as pd

import exchange_tracker
import webpage


def test_build_uses_same_weekday_and_monthly_average():
    dates = pd.bdate_range("2024-01-01", periods=500)
    history = pd.DataFrame({"date": dates, "premium_turnover_cr": range(100, 600)})
    prices = pd.Series(range(500, 1000), index=dates)
    out = exchange_tracker.build(history, prices)
    assert out["available"]
    assert out["asof"] == dates[-1]
    assert out["same_weekday"].iloc[-1].date == dates[-1]
    assert out["same_weekday"].date.dt.year.nunique() == 1
    assert (out["same_weekday"].date.dt.year == dates[-1].year).all()
    assert len(out["same_weekday"]) > 13
    assert out["monthly"].iloc[-1]["count"] > 0
    assert len(out["commentary"]) == 3
    html = webpage.tab_exchange({"exchange_tracker": out})
    assert "5D ROLLING PREMIUM TURNOVER" in html
    assert "3M" in html and "6M" in html and "1YR" in html and "2YR" in html
    assert f"{out['weekday'].upper()}S · YTD" in html
    assert html.count('class="exgridline"') == 25
    assert html.count('class="exbargrid"') == 10
    assert "VS YTD AVG" in html
    assert html.index('class="excomment"') < html.index('class="exright"')
    assert "AVERAGE DAILY PREMIUM TURNOVER" in html


def test_build_handles_empty_history():
    out = exchange_tracker.build(pd.DataFrame(), pd.Series(dtype=float))
    assert not out["available"]
