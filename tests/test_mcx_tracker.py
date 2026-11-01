import pandas as pd

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


def test_official_summary_row_uses_reported_premium_only():
    row = ["OPTFUT", "29 Oct 2026", "33503335", "459323503.31", "1281519.43"]
    parsed = mcx_tracker.parse_official_summary_row(row, "2026-10-29")
    assert parsed["date"] == pd.Timestamp("2026-10-29")
    assert parsed["premium_value_lakh"] == 1281519.43
    assert pd.isna(parsed["futures_notional_lakh"])


def test_load_appends_only_official_summary_rows(tmp_path, monkeypatch):
    pd.DataFrame([{"date": "2026-10-28", "premium_value_lakh": 930133.33,
                   "futures_notional_lakh": 3920605.93}]).to_csv(tmp_path / mcx_tracker.CACHE, index=False)
    official = pd.DataFrame([{"date": pd.Timestamp("2026-10-29"), "premium_value_lakh": 1281519.43,
                              "futures_notional_lakh": float("nan")}])
    monkeypatch.setattr(mcx_tracker, "fetch_official_summaries", lambda dates: (official, []))
    monkeypatch.setattr(mcx_tracker, "fetch_expiries", lambda: pd.DataFrame(columns=["date", "symbol", "name"]))
    history, _, status = mcx_tracker.load(tmp_path, pd.Timestamp("2026-10-29"))
    assert history.date.max() == pd.Timestamp("2026-10-29")
    assert history.iloc[-1].premium_value_lakh == 1281519.43
    assert "Official MCX Summary Report refreshed" in status
