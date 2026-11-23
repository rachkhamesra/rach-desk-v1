import numpy as np, pandas as pd
import webpage


def M_with(values):
    idx = pd.bdate_range("2026-01-01", periods=len(values))
    return {"nifty": pd.Series(values, index=idx)}


def test_the_regime_level_follows_nifty_against_its_50_and_100_day_averages():
    up = M_with(np.linspace(100, 200, 150))
    assert webpage.regime(up)["level"] == 0
    # a rise, then a fall that takes it under the 50-day average but not the 100-day
    v = np.concatenate([np.linspace(100, 200, 100), np.linspace(200, 190, 50)]); g = webpage.regime(M_with(v))
    assert g["level"] == 1 and g["d50"] < 0 < g["d100"]
    down = np.concatenate([np.linspace(100, 200, 100), np.linspace(200, 120, 50)])
    assert webpage.regime(M_with(down))["level"] == 2
    assert webpage.regime(M_with(np.linspace(100, 110, 40))) is None                         # too little history to say


def test_only_breakouts_are_marked_and_only_when_the_market_is_weak():
    ok, caution, weak = M_with(np.linspace(100, 200, 150)), M_with(np.concatenate([np.linspace(100, 200, 100), np.linspace(200, 190, 50)])), M_with(np.concatenate([np.linspace(100, 200, 100), np.linspace(200, 120, 50)]))
    assert webpage.regime_badge(ok, "BREAKOUT") == ""
    assert "NIFTY &lt; 50DMA" in webpage.regime_badge(caution, "BREAKOUT") or "NIFTY < 50DMA" in webpage.regime_badge(caution, "BREAKOUT")
    assert "100DMA" in webpage.regime_badge(weak, "BREAKOUT")
    assert webpage.regime_badge(weak, "BREAKDOWN") == "" and webpage.regime_badge(weak, "SETUP") == ""
    assert "below its 100-day" in webpage.regime_banner(weak)
