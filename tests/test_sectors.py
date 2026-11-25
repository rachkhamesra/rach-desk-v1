import numpy as np, pandas as pd
import sectors


def M_fake():
    idx = pd.bdate_range("2026-10-01", periods=10)
    rat = pd.DataFrame({"HDFCLIFE": 1.5, "SBILIFE": 1.4, "ICICILIFE": 0.8, "HDFCBANK": 1.0, "AXISBANK": 1.0, "TCS": 1.0}, index=idx)
    bases = pd.DataFrame({"sym": ["HDFCLIFE", "SBILIFE", "HDFCBANK", "TCS"], "stage": ["near", "near", "near", "building"]})
    pat = {"daily": {"found": {"ascending": [dict(sym="ICICILIFE", status="SETUP"), dict(sym="AXISBANK", status="BREAKOUT", brk_ratio=2.0), dict(sym="TCS", status="FORMING")],
                               "rectangle": [], "descending": [dict(sym="HDFCBANK", status="SETUP")]}}}
    return {"RAT": rat, "breakout_bases": bases, "patterns": pat}


GROUPS = {"HDFCLIFE": "Life insurers", "SBILIFE": "Life insurers", "ICICILIFE": "Life insurers", "HDFCBANK": "Private banks", "AXISBANK": "Private banks", "TCS": "IT services"}


def test_three_stocks_near_a_breakout_in_one_group_make_a_cluster_with_delivery_read_alongside():
    cl = sectors.clusters(M_fake(), GROUPS)
    assert [c["group"] for c in cl] == ["Life insurers"]                                    # two private banks are not enough; TCS is only building; a descending SETUP is not a breakout
    c = cl[0]; assert c["n_near"] == 3 and c["n_broke"] == 0 and c["hot"] == 2
    assert round(c["avg5"], 2) == 1.23 and c["tone"] == "NORMAL"
    assert [m["sym"] for m in c["members"]] == ["HDFCLIFE", "SBILIFE", "ICICILIFE"]         # strongest delivery first


def test_a_fresh_breakout_counts_and_a_stock_without_a_group_never_clusters():
    M = M_fake(); M["breakout_bases"] = pd.concat([M["breakout_bases"], pd.DataFrame({"sym": ["HDFCBANK2"], "stage": ["near"]})], ignore_index=True)
    cl = sectors.clusters(M, dict(GROUPS, HDFCBANK="Private banks", **{"KOTAK": "Private banks"}), min_size=2)
    assert {c["group"] for c in cl} == {"Life insurers", "Private banks"}
    banks = next(c for c in cl if c["group"] == "Private banks"); assert banks["n_broke"] == 1 and banks["members"][0]["sym"] == "AXISBANK"
    assert sectors.by_symbol(cl)["SBILIFE"]["group"] == "Life insurers"


def test_the_group_file_is_readable_and_has_the_life_insurers():
    g = sectors.load()
    assert g["HDFCLIFE"] == g["SBILIFE"] == g["ICICILIFE"] == "Life insurers" and len(g) > 300


def test_a_mini_chart_is_drawn_from_the_panels_and_left_out_when_there_is_too_little_history():
    import webpage
    n = 120; idx = pd.bdate_range("2026-01-01", periods=n); px = pd.Series(100 + np.cumsum(np.sin(np.arange(n) / 5.0)), index=idx)
    df = lambda s: pd.DataFrame({"AAA": s})
    M = {"T": n - 1, "O": df(px), "H": df(px + 1), "L": df(px - 1), "C": df(px), "DQ": df(pd.Series(1000.0 + np.arange(n), index=idx)), "RAT": df(pd.Series(1.3, index=idx)),
         "ma": {k: df(px.rolling(k, min_periods=1).mean()) for k in (50, 100, 200)}}
    svg = webpage.mini_chart(M, "AAA")
    assert svg.startswith("<svg") and svg.count("<polyline") == 3 and 'class="basevol hot"' in svg and svg.count("<rect") > 70
    assert webpage.mini_chart(M, "ZZZ") == ""
