import pandas as pd
import requests

import mcx_tracker
import webpage


def test_mcx_build_adds_upcoming_expiries_and_charts():
    dates = pd.bdate_range("2025-11-03", periods=255)
    history = pd.DataFrame({"date": dates, "premium_value_lakh": range(500000, 500255),
                            "futures_notional_lakh": range(5000000, 5000255)})
    prices = pd.Series(range(1000, 1255), index=dates)
    ref = dates[-1]
    expiries = pd.DataFrame({"date": [ref, ref + pd.Timedelta(days=15)],
                             "symbol": ["GOLDM", "CRUDEOIL"], "name": ["Gold Mini", "Crude Oil"]})
    out = mcx_tracker.build(history, prices, expiries, ref, "verified")
    assert out["available"]
    assert any("Gold Mini options expiry today" in x for x in out["commentary"])
    assert any("Crude Oil options expiry in 15D" in x for x in out["commentary"])
    bucket = mcx_tracker.month_week(ref.day)
    assert out["comparison_title"].startswith(f"WEEK {bucket}")
    assert out["comparison_count_label"] == "MONTHS"
    assert len(out["comparison"]) > 1
    assert any(f"Week {bucket}" in x and "prior" in x for x in out["commentary"])
    html = webpage.tab_mcx({"mcx_tracker": out})
    assert "MCX Exchange Tracker" in html
    assert "MCX OPTFUT PREMIUM TURNOVER" in html
    assert "verified" in html


def test_mcx_month_week_boundaries():
    assert [mcx_tracker.month_week(day) for day in (1, 8, 9, 16, 17, 24, 25, 31)] == [1, 1, 2, 2, 3, 3, 4, 4]


def test_bhavcopy_reconstructs_option_premium_across_quote_units():
    rows = [
        {"Instrument Name": "OPTFUT", "Strike Price": "1300", "Close": "2.96",
         "Volume(In 000's)": "1467.500 KGS", "Value(Lacs)": "19123.91"},
        {"Instrument Name": "OPTFUT", "Strike Price": "142000", "Close": "2297.50",
         "Volume(In 000's)": "190.000 GRMS", "Value(Lacs)": "27428.61"},
        {"Instrument Name": "FUTCOM", "Strike Price": "0", "Close": "100",
         "Volume(In 000's)": "1.000 KGS", "Value(Lacs)": "123.45"},
    ]
    out = mcx_tracker.summarize_bhavcopy(rows, "2026-10-28").iloc[0]
    assert abs(out.premium_value_lakh - 495.02) < 1e-6
    assert out.futures_notional_lakh == 123.45


def test_load_uses_bhavcopy_when_history_endpoint_is_blocked(tmp_path, monkeypatch):
    pd.DataFrame({"date": ["2026-10-28"], "premium_value_lakh": [930133.33],
                  "futures_notional_lakh": [3920605.93]}).to_csv(tmp_path / mcx_tracker.CACHE, index=False)
    monkeypatch.setattr(mcx_tracker, "fetch_history", lambda *a, **k: (_ for _ in ()).throw(requests.HTTPError("403")))
    monkeypatch.setattr(mcx_tracker, "fetch_bhavcopy_days", lambda dates: pd.DataFrame({
        "date": [pd.Timestamp("2026-10-29")], "premium_value_lakh": [1_100_000.0],
        "futures_notional_lakh": [4_000_000.0]}))
    monkeypatch.setattr(mcx_tracker, "fetch_expiries", lambda: pd.DataFrame(columns=["date", "symbol", "name"]))
    history, _, status = mcx_tracker.load(str(tmp_path), pd.Timestamp("2026-10-29"), log=lambda *_: None)
    assert history.date.max() == pd.Timestamp("2026-10-29")
    assert history.iloc[-1].premium_value_lakh == 1_100_000.0
    assert status == "Official MCX bhavcopy refreshed through 29 Oct 2026"
