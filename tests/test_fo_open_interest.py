import pandas as pd
import nse


def fo(rows):
    cols = ["FinInstrmTp", "TckrSymb", "XpryDt", "FininstrmActlXpryDt", "OpnIntrst", "ChngInOpnIntrst", "NewBrdLotQty", "ClsPric"]
    return pd.DataFrame(rows, columns=cols)


def test_the_series_expiring_on_the_session_is_taken_out_of_the_close_and_counted_as_leaving():
    # Blue Star on its November expiry (23 Nov): the file still lists the expiring series with the open interest it had going into the close
    df = fo([["STF", "BLUESTARCO", "2026-11-23", "2026-11-23", 1_273_025, -163_475, 325, 1796.1],
             ["STF", "BLUESTARCO", "2026-12-29", "2026-12-29", 3_898_700, 129_025, 325, 1779.4],
             ["STF", "BLUESTARCO", "2027-01-25", "2027-01-25", 14_700, 1_750, 350, 1761.2],
             ["IDF", "NIFTY", "2026-11-25", "2026-11-25", 5, 5, 75, 1.0]])
    r = nse.fo_open_interest(df, "2026-11-23").loc["BLUESTARCO"]
    assert r["oi"] == 3_898_700 + 14_700                                                        # 39.1 lakh, not 51.9 lakh
    prev_close = (1_273_025 + 163_475) + (3_898_700 - 129_025) + (14_700 - 1_750)                  # every contract's open interest at the previous close
    assert r["doi"] == r["oi"] - prev_close                                                     # the whole expiring series counts as having left on the expiry day
    assert r["lot"] == 325 and r["fut"] == 1779.4                                               # lot and price come from the nearest continuing contract
    assert "NIFTY" not in nse.fo_open_interest(df, "2026-11-23").index                          # futures on stocks only


def test_the_next_session_then_reads_the_real_change_and_a_normal_day_is_unchanged():
    after = fo([["STF", "BLUESTARCO", "2026-12-29", "2026-12-29", 3_856_125, -42_575, 325, 1832.8],
                ["STF", "BLUESTARCO", "2027-01-25", "2027-01-25", 23_100, 8_400, 350, 1828.1]])
    r = nse.fo_open_interest(after, "2026-11-25").loc["BLUESTARCO"]
    assert r["oi"] == 3_879_225 and r["doi"] == -42_575 + 8_400                                 # nothing expires: the plain sums, as before
    assert abs(r["oi"] / 3_913_400 - 1) < 0.01                                                  # down about 1% on the previous close, not 25%


def test_a_symbol_with_only_an_expiring_contract_ends_the_day_at_zero_and_keeps_its_lot():
    df = fo([["STF", "XYZ", "2026-11-23", "2026-11-23", 500, -100, 100, 50.0]])
    r = nse.fo_open_interest(df, "2026-11-23").loc["XYZ"]
    assert r["oi"] == 0 and r["doi"] == -600 and r["lot"] == 100
