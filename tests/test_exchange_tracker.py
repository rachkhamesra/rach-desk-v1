import pandas as pd
from types import SimpleNamespace

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
    assert html.index('excomment') < html.index('exlayout')
    assert "AVERAGE DAILY PREMIUM TURNOVER" in html


def test_build_handles_empty_history():
    out = exchange_tracker.build(pd.DataFrame(), pd.Series(dtype=float))
    assert not out["available"]


def test_bhavcopy_fallback_reproduces_options_premium_turnover():
    csv = ("FinInstrmTp,TtlTrfVal,StrkPric,TtlTradgVol\n"
           "IDO,74500000,74000,1000\n"
           "STO,5250000,5000,1000\n"
           "IDF,99999999,0,1\n")

    class Session:
        def get(self, *args, **kwargs):
            return SimpleNamespace(content=csv.encode(), raise_for_status=lambda: None)

    out = exchange_tracker.fetch_day_bhavcopy("2026-10-29", Session())
    assert out.iloc[0].premium_turnover_cr == 0.075
