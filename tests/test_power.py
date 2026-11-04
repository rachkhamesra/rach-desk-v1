import datetime as dt
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import power
from nppdgr.owners import OwnerMap
from nppdgr.parse_dgr2 import parse_dgr2

FIX = Path(__file__).parent / "fixtures"
D26, D24, D22 = (dt.date(2026, 10, 30), dt.date(2024, 10, 30), dt.date(2022, 10, 30))


def fixture_fetch(calls=None):
    def fetch(day, n, raw, force=False):
        if calls is not None: calls.append((day, force))
        src = FIX / f"dgr2-{day:%Y-%m-%d}.xls"
        if not src.exists(): return None, "missing"
        dst = Path(raw) / src.name; shutil.copy(src, dst)          # refresh deletes what it parsed, so never hand it the fixture itself
        return dst, "ok"
    return fetch


def test_one_day_reduces_without_losing_generation():
    parsed = parse_dgr2(FIX / "dgr2-2026-10-30.xls")
    fleet, owner, st, units = power.aggregate(parsed, OwnerMap())
    total = sum(s["actual_mu"] or 0 for s in parsed.stations)
    assert abs(fleet["actual_mu"].sum() - total) < 1e-6 and abs(owner["actual_mu"].sum() - total) < 1e-6
    assert fleet["n"].sum() == len(parsed.stations) == 542
    ntpc = owner[(owner["owner"] == "NTPC") & (owner["fuel"] == "THERMAL")].iloc[0]
    assert ntpc["mw"] > 50000 and 0 < ntpc["coal_mw"] <= ntpc["mw"] and 0 < ntpc["coal_mwdays"] / ntpc["coal_mw"] < 60


def test_refresh_stores_days_and_does_not_refetch_history(tmp_path):
    calls = []
    f, o = power.refresh(str(tmp_path), D26, start=D22, log=lambda *a: None, fetch=fixture_fetch(calls), pause=0)
    assert sorted(f["date"].unique()) == ["2022-10-30", "2024-10-30", "2026-10-30"]
    n = len(calls); calls.clear()
    power.refresh(str(tmp_path), D26, start=D22, log=lambda *a: None, fetch=fixture_fetch(calls), pause=0)
    assert len(calls) == power.RETRY_WINDOW + 1                                          # only the last 12 days: stored history and old gaps are left alone
    assert all(force == ((D26 - day).days <= power.RECENT_DAYS) for day, force in calls)  # the newest days are re-downloaded (the portal revises them)
    assert n > len(calls)


def test_a_bad_file_is_recorded_and_the_other_days_still_load(tmp_path):
    def fetch(day, n, raw, force=False):
        if day == D24:
            bad = Path(raw) / "x.xls"; bad.write_bytes(b"\xd0\xcf\x11\xe0 not a real workbook"); return bad, "ok"
        return fixture_fetch()(day, n, raw, force)
    f, _ = power.refresh(str(tmp_path), D26, start=D22, log=lambda *a: None, fetch=fetch, pause=0)
    assert sorted(f["date"].unique()) == ["2022-10-30", "2026-10-30"]
    import json
    assert "2024-10-30" in json.loads((tmp_path / "power" / "status.json").read_text())["problems"]


def test_time_budget_stops_cleanly_and_keeps_what_it_has(tmp_path):
    logs = []
    power.refresh(str(tmp_path), D26, start=D22, budget_s=0, log=logs.append, fetch=fixture_fetch(), pause=0)
    assert any("time budget" in x for x in logs)


def test_build_aligns_years_and_keeps_only_totals_and_companies(tmp_path):
    power.refresh(str(tmp_path), D26, start=D22, log=lambda *a: None, fetch=fixture_fetch(), pause=0)
    out = power.build(str(tmp_path))
    assert out["asof"] == "2026-10-30" and out["years"] == [2026, 2025, 2024] and out["n_days"] == 3
    assert set(out["series"]) == {"ALL", "THERMAL", "HYDRO"}                               # no regions, states, stations or outage tables
    assert not {"cards", "stations", "units"} & set(out)
    allc = out["series"]["ALL"]
    assert abs(allc["years"]["2026"][-1] - 4249.4) < .1 and len(allc["years"]["2026"]) == 303   # 30 Oct is day 303 of a 365-day year
    assert allc["years"]["2024"][302] is not None and allc["years"]["2025"][302] is None        # only the days we stored are filled
    assert out["series"]["THERMAL"]["years"]["2026"][-1] > 2000
    assert out["owners"] == [] and out["companies"] == []                                        # three stored days are too few to rank a company
    assert not (tmp_path / "power" / "stations_last.csv").exists()
    assert power.build(str(tmp_path / "nothing")) is None


def test_company_series_follow_each_owner_across_years():
    rows = []
    for d in pd.date_range("2024-01-01", "2026-10-30"):
        rows.append(dict(date=f"{d:%Y-%m-%d}", owner="NTPC", fuel="THERMAL", n=1, mw=5000, actual_mu=100.0 + d.year - 2024, outage_mw=0, coal_mw=0, coal_mwdays=0))
        rows.append(dict(date=f"{d:%Y-%m-%d}", owner="NTPC", fuel="HYDRO", n=1, mw=500, actual_mu=5.0, outage_mw=0, coal_mw=0, coal_mwdays=0))
        rows.append(dict(date=f"{d:%Y-%m-%d}", owner="Adani Power", fuel="THERMAL", n=1, mw=900, actual_mu=40.0, outage_mw=0, coal_mw=0, coal_mwdays=0))
    out = power.company_series(pd.DataFrame(rows), ["NTPC", "Adani Power"], pd.Timestamp("2026-10-30"), [2026, 2025, 2024])
    ntpc, adani = out
    assert ntpc["symbol"] == "NTPC" and adani["symbol"] == "ADANIPOWER"
    assert ntpc["years"]["2024"][0] == 105.0 and ntpc["years"]["2025"][0] == 106.0 and ntpc["years"]["2026"][0] == 107.0   # all fuels added together
    assert len(ntpc["years"]["2026"]) == 303 and len(ntpc["years"]["2025"]) == 365 and adani["years"]["2026"][10] == 40.0


def test_owner_table_compares_the_same_weekdays_a_year_earlier():
    rows = []
    for i in range(60):                                         # 60 days ending 2026-10-30, plus the same stretch a year (364 days) earlier
        for off, mu in ((0, 100.0), (364, 80.0)):
            d = pd.Timestamp("2026-10-30") - pd.Timedelta(days=i + off)
            rows.append(dict(date=f"{d:%Y-%m-%d}", owner="NTPC", fuel="THERMAL", n=1, mw=5000, actual_mu=mu, outage_mw=100, coal_mw=5000, coal_mwdays=5000 * 10))
            rows.append(dict(date=f"{d:%Y-%m-%d}", owner="Other", fuel="THERMAL", n=1, mw=100, actual_mu=1, outage_mw=0, coal_mw=0, coal_mwdays=0))
            rows.append(dict(date=f"{d:%Y-%m-%d}", owner="STATE: Gujarat", fuel="THERMAL", n=1, mw=900, actual_mu=20, outage_mw=0, coal_mw=0, coal_mwdays=0))
    out = power.owner_rows(pd.DataFrame(rows), pd.Timestamp("2026-10-30"))
    assert [r["owner"] for r in out] == ["NTPC"]                # neither "Other" nor a state-owned generator is ranked as a company
    r = out[0]
    assert r["symbol"] == "NTPC" and r["mu"] == 100.0 and r["yoy"] == 25.0 and r["coal"] == 10.0 and "outage" not in r
    assert abs(r["plf"] - 100 * 1000 / (5000 * 24) * 100) < .1


@pytest.mark.parametrize("day", ["2022-10-30", "2024-10-30", "2026-10-30"])
def test_every_report_vintage_gets_sector_and_fuel_labels(day):
    parsed = parse_dgr2(FIX / f"dgr2-{day}.xls")
    fleet, owner, st, units = power.aggregate(parsed, OwnerMap())
    assert (st["fuel"] != "").all() and (st["sector"] != "").all()                       # labels sit in a different column in each vintage
    by = fleet.groupby("fuel")["actual_mu"].sum()
    assert set(by.index) >= {"THERMAL", "HYDRO", "NUCLEAR"} and by["THERMAL"] > 1800 and by["THERMAL"] > 5 * by["HYDRO"]
    assert abs(by.sum() - sum(s["actual_mu"] or 0 for s in parsed.stations)) < 1e-6


def test_history_stored_by_an_older_parser_is_reloaded(tmp_path):
    folder = tmp_path / "power"; folder.mkdir()
    pd.DataFrame([dict(date="2024-10-30", region="X", sector="", fuel="", n=1, mw=1, actual_mu=1, prog_mu=1, outage_mw=0, coal_mw=0, coal_mwdays=0)]).to_csv(folder / "fleet.csv", index=False)
    (folder / "status.json").write_text('{"missing": {}, "problems": {}}')                  # no version: written before the labels were fixed
    f, _ = power.refresh(str(tmp_path), D26, start=D24, log=lambda *a: None, fetch=fixture_fetch(), pause=0)
    assert (f["fuel"] != "").all() and f[f["date"] == "2024-10-30"]["actual_mu"].sum() > 4000


def test_a_portal_that_keeps_failing_stops_the_download_for_this_build(tmp_path):
    calls = []
    def down(day, n, raw, force=False):
        calls.append(day); raise RuntimeError("timed out")
    logs = []
    power.refresh(str(tmp_path), D26, start=D22, log=logs.append, fetch=down, pause=0)
    assert len(calls) == power.MAX_DOWNLOAD_FAILS and any("failed in a row" in m for m in logs)
