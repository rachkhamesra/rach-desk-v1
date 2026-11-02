import numpy as np
import pandas as pd

import heat


def synthetic(last="2026-10-27", bump=1.0, bump_year=2026):
    idx = pd.date_range("1991-01-01", last)
    mean = 25 + 8 * np.sin(2 * np.pi * (idx.dayofyear - 100) / 365.25)
    mean = mean + np.where(idx.year == bump_year, bump, 0.0)
    return pd.DataFrame({"mean": mean, "max": mean + 6}, index=idx)


CITY = dict(name="Testville", state="X", region="North", lat=1.0, lon=2.0)


def test_city_config_has_25_cities_in_four_regions():
    cities = heat.load_cities()
    assert len(cities) == 25 and len({c["name"] for c in cities}) == 25
    assert {c["region"] for c in cities} == set(heat.REGIONS)


def test_oni_months_use_the_centre_month_of_each_season():
    got = heat.parse_oni("SEAS  YR   TOTAL  ANOM\n DJF 2026  26.1  -0.20\n JAS 2026  29.12  2.16\n NDJ 2025  25.0 -0.5\n")
    assert got == {"2026-01": -0.2, "2026-08": 2.16, "2025-12": -0.5}


def test_feb_29_never_appears_and_the_current_year_stops_at_its_last_day():
    df = synthetic("2026-10-27")
    last = pd.Timestamp("2026-10-27")
    for year in (2026, 2025, 2024):
        arrs = heat.year_arrays(df, year, last)
        assert len(arrs["mean"]) == (300 if year == 2026 else 365)             # 27 Oct is day 300 of a 365-day year
    leap = heat.year_arrays(df, 2024, last)["mean"]
    assert leap[59] == round(float(df.loc["2024-03-01", "mean"]), 1)            # Mar 1 sits at index 59 in every year
    assert heat.year_arrays(df, 2025, last)["mean"][59] == round(float(df.loc["2025-03-01", "mean"]), 1)


def test_a_warmer_year_shows_up_in_every_measure():
    c = heat.build_city(synthetic(bump=1.0), CITY)
    assert abs(c["ytd"] - 1.0) < .05 and abs(c["last30"] - 1.0) < .1
    assert c["cmp"]["p1"] == dict(year=2025, gap=1.0, warmer=100)
    assert abs(c["cmp"]["p2"]["gap"] - 1.0) < .05                              # 2024 is a leap year, so the sine drifts a hair
    summer = c["seasons"]["summer"]
    assert summer["label"] == "2026" and not summer["partial"] and abs(summer["d_prev"] - 1.0) < .05 and abs(summer["d_norm"] - 1.0) < .1
    winter = c["seasons"]["winter"]
    assert winter["label"] == "2025–26" and abs(winter["d_prev"] - 59 / 90) < .05   # only its Jan-Feb days (59 of 90) fall in the 2026 bump
    assert len(c["grid"]) == 18 and abs(c["grid"][-2] - 1.0) < .1              # the last full month (the part-month at the end leans warm)


def test_matched_range_uses_only_days_both_years_have():
    assert heat.matched([10, None, 12, 14], [9, 9, None, 10]) == (2.5, 100)
    assert heat.matched([None], [1]) == (None, None)


def test_in_progress_season_is_compared_over_the_same_days_only():
    df = synthetic("2026-04-15")
    s = heat.build_city(df, CITY)["seasons"]["summer"]
    assert s["partial"] and s["days"] == 46                                    # Mar 1 to Apr 15
    assert abs(s["d_prev"] - 1.0) < .05


def test_years_follow_the_data_not_the_calendar():
    df = synthetic("2027-01-20", bump_year=2027)
    c = heat.build_city(df, CITY)
    assert sorted(c["years"]) == ["2025", "2026", "2027"] and len(c["years"]["2027"]["mean"]) == 20


def test_refresh_fetches_everything_once_then_only_recent_days_and_survives_failures(tmp_path):
    calls = []
    def fetcher(city, start, end, log=print):
        calls.append((city["name"], start, end))
        return None if city["name"] == "Bad" else synthetic(f"{end:%Y-%m-%d}").loc[start:end]
    cities = [CITY, dict(CITY, name="Bad")]
    f1 = heat.refresh(str(tmp_path), "2026-11-02", cities=cities, fetcher=fetcher, sleep=lambda s: None)
    assert set(f1) == {"Testville"} and calls[0][1] == pd.Timestamp("1991-01-01")      # no cache: full history; failure with no cache: skipped
    n = len(calls)
    heat.refresh(str(tmp_path), "2026-11-02", cities=cities, fetcher=fetcher, sleep=lambda s: None)
    assert len(calls) == n + 1 and calls[-1][0] == "Bad"                                 # fetched today already: only the failed city retries
    f3 = heat.refresh(str(tmp_path), "2026-11-03", cities=[CITY], fetcher=fetcher, sleep=lambda s: None)
    assert (calls[-1][2] - calls[-1][1]).days == heat.REFRESH_DAYS and f3["Testville"].index.min() == pd.Timestamp("1991-01-01")
    assert f3["Testville"].index.is_monotonic_increasing and not f3["Testville"].index.has_duplicates


def test_regions_average_their_cities_and_missing_data_is_dropped():
    frames = {"Testville": synthetic(bump=1.0), "Coolton": synthetic(bump=-1.0)}
    cities = [CITY, dict(CITY, name="Coolton", region="South"), dict(CITY, name="Nodata", region="East")]
    out = heat.build(frames, {"2026-08": 2.16}, cities=cities)
    assert [c["name"] for c in out["cities"]] == ["Testville", "Coolton"]
    assert set(out["regions"]) == {"North", "South"} and abs(out["all"]["ytd"]) < .05
    assert out["regions"]["North"]["p1"] == 1.0 and out["regions"]["South"]["p1"] == -1.0
    assert heat.build({}, None, cities=cities) is None
