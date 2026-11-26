import numpy as np
import pandas as pd
import nse_tracker as T


def fo_frame():
    # one index put and one stock call: transfer value = (strike + premium) x contracts x lot
    rows = [dict(FinInstrmTp="IDO", StrkPric=25000.0, TtlTradgVol=1000, NewBrdLotQty=75, TtlTrfVal=(25000 + 40) * 1000 * 75),
            dict(FinInstrmTp="STO", StrkPric=1000.0, TtlTradgVol=500, NewBrdLotQty=250, TtlTrfVal=(1000 + 12) * 500 * 250),
            dict(FinInstrmTp="IDF", StrkPric=np.nan, TtlTradgVol=9, NewBrdLotQty=75, TtlTrfVal=1e9),                 # futures are not options
            dict(FinInstrmTp="IDO", StrkPric=24000.0, TtlTradgVol=0, NewBrdLotQty=75, TtlTrfVal=0.0)]               # an option that did not trade
    return pd.DataFrame(rows)


def test_equity_premium_turnover_is_transfer_value_less_strike_notional():
    s = T.equity_summary(fo_frame())
    assert round(s["idx_premium_cr"], 6) == round(40 * 1000 * 75 / 1e7, 6) and s["idx_contracts"] == 1000
    assert round(s["stk_premium_cr"], 6) == round(12 * 500 * 250 / 1e7, 6)
    assert round(s["idx_notional_cr"], 3) == round(25000 * 1000 * 75 / 1e7, 3)
    assert T.equity_summary(pd.DataFrame({"FinInstrmTp": ["STF"]})) is None


def co_frame(mult=100, sym="CRUDEOIL", expiry="2026-12-09", vol=300, strike=7000.0, prem=130.0):
    row = dict(FinInstrmTp="FUO", TckrSymb=sym, OptnTp="PE", XpryDt=expiry, StrkPric=strike, TtlTradgVol=vol, TtlTrfVal=(strike + prem) * vol * mult, HghPric=prem + 10, LwPric=prem - 10, ClsPric=prem, TtlNbOfTxsExctd=40)
    idle = dict(row, TtlTradgVol=0, TtlTrfVal=0.0, TckrSymb="GOLD", XpryDt="2026-11-27")
    return pd.DataFrame([row, idle])


def test_the_contract_multiplier_is_inferred_and_snapped_to_a_known_size():
    for mult in (100, 1250, 10, 1):
        t = co_frame(mult=mult).iloc[:1]
        assert T.infer_multiplier(t) == mult
    out = dict(T.commodity_summary(co_frame(mult=100)))
    assert round(out["CRUDEOIL"]["premium_cr"], 6) == round(130 * 300 * 100 / 1e7, 6) and out["CRUDEOIL"]["contracts"] == 300
    assert out["GOLD"]["contracts"] == 0 and out["GOLD"]["expiries"] == "2026-11-27"                  # a listed but idle commodity still gets a row


def test_expiry_day_and_the_session_before_are_found_from_each_commodities_own_expiry_dates():
    dates = pd.to_datetime(["2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11"])
    co = pd.DataFrame([dict(date=d, underlying="CRUDEOIL", contracts=10.0, premium_cr=1.0, notional_cr=50.0, trades=5.0, expiries="2026-11-10|2026-12-09") for d in dates])
    k = T.commodity_days(co).set_index("date")["kind"]
    assert k[pd.Timestamp("2026-11-10")] == "E" and k[pd.Timestamp("2026-11-09")] == "E-1" and k[pd.Timestamp("2026-11-06")] == "other"


def test_the_commodity_analysis_splits_a_month_into_expiry_day_the_day_before_and_the_rest():
    dates = pd.bdate_range("2026-10-01", "2026-11-13")
    prem = {pd.Timestamp("2026-10-08"): 400.0, pd.Timestamp("2026-10-07"): 100.0, pd.Timestamp("2026-11-10"): 600.0, pd.Timestamp("2026-11-09"): 200.0}
    co = pd.DataFrame([dict(date=d, underlying="CRUDEOIL", contracts=10.0, premium_cr=prem.get(d, 5.0), notional_cr=1.0, trades=1.0, expiries="2026-10-08|2026-11-10") for d in dates])
    C = T.build_commodity(co); m = C["monthly"].set_index("month")
    assert m.loc["2026-10", "p_E"] == 400.0 and m.loc["2026-10", "p_E-1"] == 100.0 and round(m.loc["2026-10", "share_ee1"], 1) == round(500 / m.loc["2026-10", "premium"] * 100, 1)
    assert list(C["events"]["expiry"]) == [pd.Timestamp("2026-10-08"), pd.Timestamp("2026-11-10")] and C["events"]["prem_p"].tolist() == [100.0, 200.0]
    assert len(C["cumulative"]["2026-11"]) == 10 and C["commentary"]


def test_the_nse_share_price_is_read_from_the_bse_bhavcopy():
    csv = b"TckrSymb,FinInstrmNm,ClsPric\nRELIANCE,RELIANCE INDUSTRIES,1500.5\nNSE,National Stock Exchange of Ind,2317.65\nNSE,SOMETHING ELSE,9.0\n"
    assert T.share_close(csv) == 2317.65
    assert T.share_close(b"TckrSymb,FinInstrmNm,ClsPric\nRELIANCE,RELIANCE INDUSTRIES,1500.5\n") is None


def test_nse_share_of_nse_plus_mcx_is_a_rolling_three_month_ratio_that_starts_when_a_window_is_full():
    days = pd.bdate_range("2026-01-01", "2026-06-30")
    eq = pd.DataFrame({"date": days, "idx_premium_cr": 800.0, "stk_premium_cr": 100.0})
    co = pd.DataFrame({"date": days, "underlying": "CRUDEOIL", "premium_cr": 10.0})
    mcx = pd.DataFrame({"date": days, "premium_turnover_cr": 100.0})
    sh = T.share_of_combined(eq, co, mcx)
    assert sh["date"].iloc[0] >= pd.Timestamp("2026-01-01") + pd.Timedelta(days=92)                 # no point without a full three months of both
    assert "share_all" not in sh.columns                                                          # equity options are not compared with MCX
    assert round(sh["share_commodity"].iloc[-1], 6) == round(10 / (10 + 100) * 100, 6)
    assert T.share_of_combined(eq, co, None) is None and T.share_of_combined(eq, co, mcx.iloc[:5]) is None   # too little MCX history
