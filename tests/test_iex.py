import pandas as pd

import iex
import power

HTML = """<html><table><thead><tr><th>Date</th><th>Purchase Bid (MWh)</th><th>Sell Bid (MWh)</th><th>MCV (MWh)</th><th>Final Scheduled Volume (MWh)</th><th>MCP (Rs/MWh) *</th><th>Weighted MCP (Rs/MWh)</th></tr></thead>
<tbody><tr class="x"><td class="c">01-10-2026</td><td>924540.63</td><td>319886.67</td><td>165473.29</td><td>165679.12</td><td>7426.52</td><td>4626.10</td></tr>
<tr><td>02-10-2026</td><td>761,483.58</td><td>358837.83</td><td>154080.61</td><td>154668.98</td><td>7169.79</td><td>4428.22</td></tr>
<tr><td>junk</td><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td></tr></tbody></table>
<table><thead><tr><th>Summary</th><th>Purchase Bid (MWh)</th></tr></thead><tbody><tr><td>Total</td><td>25036316.48</td></tr></tbody></table></html>"""


def frame(a, b, price=4000.0):
    days = pd.date_range(a, b)
    return pd.DataFrame(dict(date=days, purchase_bid_mwh=1.0, sell_bid_mwh=1.0, mcv_mwh=150000.0, scheduled_mwh=150000.0, mcp=price + 500, wmcp=price))


def test_parse_reads_the_daily_table_and_ignores_summary_rows_and_junk():
    df = iex.parse(HTML)
    assert list(df["date"]) == [pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-02")]
    assert df.iloc[0]["wmcp"] == 4626.10 and df.iloc[1]["purchase_bid_mwh"] == 761483.58     # thousands separators are tolerated
    assert len(iex.parse("<html>blocked by a bot check</html>")) == 0


def test_month_ranges_run_newest_first_and_stop_at_today():
    r = iex.month_ranges(pd.Timestamp("2026-09-15"), pd.Timestamp("2026-11-06"))
    assert [(a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")) for a, b in r] == [("2026-11-01", "2026-11-06"), ("2026-10-01", "2026-10-31"), ("2026-09-15", "2026-09-30")]


def test_refresh_fetches_every_month_once_then_only_the_newest_two_each_day(tmp_path):
    calls = []
    def fetch(a, b, log=print): calls.append((a, b)); return frame(a, b)
    quiet = dict(log=lambda *x: None, pause=0, fetch=fetch)
    df = iex.refresh(str(tmp_path), "2026-11-06", start=pd.Timestamp("2026-08-01"), **quiet)
    assert len(calls) == 4 and calls[0][0] == pd.Timestamp("2026-11-01") and len(df) == 98            # Aug 1 to Nov 6
    calls.clear(); iex.refresh(str(tmp_path), "2026-11-06", start=pd.Timestamp("2026-08-01"), **quiet)
    assert calls == []                                                                                 # nothing to do the same day
    iex.refresh(str(tmp_path), "2026-11-07", start=pd.Timestamp("2026-08-01"), **quiet)
    assert [c[0].strftime("%Y-%m") for c in calls] == ["2026-11", "2026-10"]                         # a new day: the two newest months only, older ones are complete


def test_failures_stop_the_download_and_keep_what_is_stored(tmp_path):
    state = {"n": 0}
    def fetch(a, b, log=print):
        state["n"] += 1
        return frame(a, b) if state["n"] == 1 else None
    logs = []
    df = iex.refresh(str(tmp_path), "2026-11-06", start=pd.Timestamp("2026-06-01"), log=logs.append, pause=0, fetch=fetch)
    assert state["n"] == 3 and len(df) == 6 and any("repeated failures" in m for m in logs)           # one good month, two failures, then it stops
    assert pd.read_csv(tmp_path / "power" / "iex_dam.csv")["date"].nunique() == 6


def test_power_block_converts_units_and_aligns_years(tmp_path):
    folder = tmp_path / "power"; folder.mkdir()
    df = pd.concat([frame("2024-01-01", "2024-12-31", 4000.0), frame("2025-01-01", "2025-12-31", 5000.0), frame("2026-01-01", "2026-11-06", 6000.0)])
    df.to_csv(folder / "iex_dam.csv", index=False)
    out = power.iex_block(str(tmp_path))
    assert out["years"] == [2026, 2025, 2024] and out["asof"] == "2026-11-06"
    assert out["price"]["2026"][0] == 6.0 and out["price"]["2025"][0] == 5.0 and len(out["price"]["2026"]) == 310     # Rs/MWh to Rs/kWh; 6 Nov is day 310
    assert out["volume"]["2026"][-1] == 150.0 and out["latest"] == dict(date="2026-11-06", wmcp=6.0, mcp=6.5, mcv=150.0)
    assert power.iex_block(str(tmp_path / "missing")) is None
