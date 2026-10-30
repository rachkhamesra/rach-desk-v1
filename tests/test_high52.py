import numpy as np
import pandas as pd

import webpage


def test_52_week_high_screen_has_both_groups_and_three_column_cards():
    dates = pd.bdate_range("2025-11-01", periods=253)
    close = pd.DataFrame({"FUTURE": np.linspace(100, 160, 253), "CASH": np.linspace(50, 90, 253)}, index=dates)
    delivery = pd.DataFrame({"FUTURE": np.linspace(1_000, 2_000, 253), "CASH": np.linspace(800, 1_400, 253)}, index=dates)
    ratio = delivery / delivery.shift(1).rolling(20, min_periods=15).mean()
    highs = pd.DataFrame([
        {"sym": "FUTURE", "fo": True, "day_high": 162, "prior_high": 160, "close": 160, "close_from_high": -1.23, "px1d": 1.2, "ratio": 1.4},
        {"sym": "CASH", "fo": False, "day_high": 92, "prior_high": 90, "close": 90, "close_from_high": -2.17, "px1d": .8, "ratio": 1.3},
    ])
    market = {"T": 252, "dates": list(dates), "C": close, "DQ": delivery, "RAT": ratio,
              "high52": highs, "market_cap_cr": {"CASH": 18000}, "unresolved": set(), "results": []}
    html = webpage.tab_52w_highs(market)
    assert "F&amp;O" in html and "NON F&amp;O" in html
    assert "FUTURE" in html and "CASH" in html
    assert html.count('class="h52card"') == 2
    assert "h52grid" in html
    assert "&lt; ₹10,000 CR" in html and "₹10,000–30,000 CR" in html and "&gt; ₹30,000 CR" in html
    assert 'data-mcap="10to30"' in html
