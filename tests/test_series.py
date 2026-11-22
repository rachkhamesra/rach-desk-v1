import io, os, zipfile
import numpy as np, pandas as pd
import nse


def write_cm(root, d, rows):
    os.makedirs(os.path.join(root, "raw", "cm"), exist_ok=True)
    df = pd.DataFrame(rows, columns=["TckrSymb", "SctySrs", "ISIN", "OpnPric", "HghPric", "LwPric", "ClsPric", "PrvsClsgPric"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z: z.writestr("cm.csv", df.to_csv(index=False))
    open(nse.path(root, "cm", d), "wb").write(buf.getvalue())


def write_deliv(root, d, rows):
    os.makedirs(os.path.join(root, "raw", "deliv"), exist_ok=True)
    df = pd.DataFrame(rows, columns=["SYMBOL", "SERIES", "DATE1", "TTL_TRD_QNTY", "TURNOVER_LACS", "DELIV_QTY"])
    df.to_csv(nse.path(root, "deliv", d), index=False)


D = pd.Timestamp("2026-06-01")
CM = [("AAA", "EQ", "IN1", 10, 11, 9, 10.5, 10), ("PFOCUS", "BE", "IN2", 200, 230, 195, 228.4, 220), ("ZED", "BZ", "IN3", 5, 6, 4, 5.5, 5),
      ("SMEX", "SM", "IN4", 50, 52, 49, 51, 50), ("BLK", "BL", "IN5", 70, 71, 69, 70, 70), ("BLK", "EQ", "IN5", 70, 71, 69, 70, 70), ("DUP", "BE", "IN6", 1, 1, 1, 1, 1), ("DUP", "EQ", "IN6", 2, 2, 2, 2, 2)]


def test_trade_for_trade_stocks_keep_their_prices_and_other_boards_stay_out(tmp_path):
    write_cm(str(tmp_path), D, CM); cm = nse.read_cm(str(tmp_path), D)
    assert {"AAA", "PFOCUS", "ZED", "BLK", "DUP"} <= set(cm.index) and "SMEX" not in cm.index                      # BE and BZ kept; SME board out
    assert cm.loc["PFOCUS", "close"] == 228.4 and cm.loc["PFOCUS", "isin"] == "IN2"
    assert cm.loc["BLK", "close"] == 70 and cm.index.is_unique                                                      # the block-deal row is dropped, the stock's own EQ row stays
    assert cm.loc["DUP", "close"] == 2                                                                              # EQ wins if a symbol is in two series


def test_in_trade_for_trade_every_share_traded_is_a_delivered_share(tmp_path):
    rows = [("AAA", "EQ", "01-Jun-2026", 1000, 20.0, 400), ("PFOCUS", "BE", "01-Jun-2026", 150057, 342.7, "-"), ("ZED", "BZ", "01-Jun-2026", 900, 1.0, "-"), ("SMEX", "SM", "01-Jun-2026", 5, 0.1, 5)]
    write_deliv(str(tmp_path), D, rows); dv = nse.read_deliv(str(tmp_path), D)
    assert dv.loc["AAA", "dq"] == 400                                                                                # an ordinary stock keeps its reported delivery
    assert dv.loc["PFOCUS", "dq"] == 150057 == dv.loc["PFOCUS", "tq"] and dv.loc["ZED", "dq"] == 900                  # no intraday trading allowed: the whole volume is delivery
    assert abs(dv.loc["PFOCUS", "turn_cr"] - 3.427) < 1e-9 and "SMEX" not in dv.index and dv.index.is_unique


def test_the_parsed_cache_is_discarded_when_the_parser_changes(tmp_path):
    root = str(tmp_path); parsed = {pd.Timestamp("2026-06-01"): dict(deliv=None, cm=None, fo=None, nifty=1.0, bse=None)}
    assert nse.load_parsed(root) == {}                                                                              # nothing cached yet
    nse.save_parsed(root, parsed); assert list(nse.load_parsed(root)) == list(parsed)
    open(os.path.join(root, "parsed.version"), "w").write(str(nse.PARSER_VERSION - 1)); assert nse.load_parsed(root) == {}      # parsed by an older parser: start again from the raw files
    os.remove(os.path.join(root, "parsed.version")); assert nse.load_parsed(root) == {}                              # an old cache with no version file is also stale


def make_day(rows_cm, rows_deliv=None, rows_fo=None):
    cm = pd.DataFrame([dict(isin=i, open=1.0, high=1.0, low=1.0, close=c, prev=c) for _, i, c in rows_cm], index=[s for s, _, _ in rows_cm])
    dv = pd.DataFrame([dict(dq=1.0, tq=2.0, turn_cr=0.1) for _ in rows_cm], index=[s for s, _, _ in rows_cm])
    fo = pd.DataFrame([dict(oi=5.0, doi=1.0, lot=10.0, fut=c) for _, _, c in rows_cm], index=[s for s, _, _ in rows_cm])
    return dict(cm=cm, deliv=dv, fo=fo, nifty=1.0, bse=None)


def test_a_renamed_stock_is_one_stock_with_its_whole_history():
    d = pd.bdate_range("2025-04-01", periods=6)
    parsed = {d[0]: make_day([("ZOMATO", "INE758T01015", 100.0), ("TCS", "INE467B01029", 50.0)]), d[1]: make_day([("ZOMATO", "INE758T01015", 101.0), ("TCS", "INE467B01029", 51.0)]),
              d[2]: make_day([("ZOMATO", "INE758T01015", 102.0), ("TCS", "INE467B01029", 52.0)]),
              d[3]: make_day([("ETERNAL", "INE758T01015", 103.0), ("TCS", "INE467B01029", 53.0)]), d[4]: make_day([("ETERNAL", "INE758T01015", 104.0), ("TCS", "INE467B01029", 54.0)]),
              d[5]: make_day([("ETERNAL", "INE758T01015", 105.0), ("TCS", "INE467B01029", 55.0)])}
    assert nse.symbol_aliases(parsed) == {"ZOMATO": "ETERNAL"}
    out = nse.canonical(parsed)
    assert out.aliases == {"ZOMATO": "ETERNAL"}
    assert all("ETERNAL" in out[x]["cm"].index and "ZOMATO" not in out[x]["cm"].index for x in d)                     # every day under the current name
    assert [out[x]["cm"].loc["ETERNAL", "close"] for x in d] == [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]             # one unbroken series
    assert "ETERNAL" in out[d[0]]["deliv"].index and "ETERNAL" in out[d[1]]["fo"].index                                  # delivery and futures follow the rename
    assert all(out[x]["cm"].index.is_unique for x in d) and list(out[d[0]]["cm"].index.sort_values()) == ["ETERNAL", "TCS"]
    assert "ZOMATO" in parsed[d[0]]["cm"].index                                                                          # the cached frames are not changed


def test_two_symbols_on_one_isin_at_the_same_time_are_not_a_rename():
    d = pd.bdate_range("2025-04-01", periods=3)
    parsed = {x: make_day([("AAA", "INE000A01010", 10.0), ("AAAB", "INE000A01010", 10.0)]) for x in d}                  # one ISIN, two symbols traded together
    assert nse.symbol_aliases(parsed) == {}
    parsed[d[2]] = make_day([("AAA", "INE000A01010", 10.0)])
    assert nse.symbol_aliases(parsed) == {}                                                                            # they overlapped before: still not a rename
    a = {d[0]: make_day([("OLD", "INE111B01010", 5.0)]), d[1]: make_day([("MID", "INE111B01010", 6.0)]), d[2]: make_day([("NEW", "INE111B01010", 7.0)])}
    assert nse.symbol_aliases(a) == {"OLD": "NEW", "MID": "NEW"}                                                       # two renames in a row all point to the latest name
