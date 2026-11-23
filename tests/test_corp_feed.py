import numpy as np, pandas as pd
import corp, corp_feed

RAW = [dict(symbol="CUB", exDate="12-Jun-2026", subject="Bonus 1:3"),
       dict(symbol="SPL", exDate="01-Jul-2026", subject="Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share"),
       dict(symbol="DIV", exDate="01-Jul-2026", subject="Dividend - Rs 5 Per Share"),
       dict(symbol="DEM", exDate="01-Jul-2026", subject="Demerger"),
       dict(symbol="BAD", exDate="not a date", subject="Bonus 1:1")]


def test_ratios_follow_how_nse_writes_them():
    f = corp_feed.factor
    assert f("Bonus 1:3") == 0.75 and abs(f("Bonus 2:1") - 1 / 3) < 1e-9 and f("Bonus 1:1") == 0.5 and abs(f("Bonus 1:10") - 10 / 11) < 1e-9
    assert f("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share") == 0.1
    assert f("Face Value Split (Sub-Division) - From Rs 5/- Per Share To Rs 2/- Per Share") == 0.4
    assert f("Face Value Consolidation - From Re 1/- Per Share To Rs 10/- Per Share") == 10
    for s in ("Dividend - Rs 5 Per Share", "Demerger", "Rights 1:4 @ Premium Rs 50/-", "Buy Back", "", None): assert f(s) is None


def test_rows_keep_only_bonus_and_split_with_a_real_date():
    df = corp_feed.rows(RAW)
    assert set(df.symbol) == {"CUB", "SPL"} and df.loc[df.symbol == "CUB", "ratio"].iloc[0] == 0.75 and (df.source == "nse").all()
    assert df.loc[df.symbol == "CUB", "date"].iloc[0] == pd.Timestamp("2026-06-12")


def test_load_caches_refreshes_recent_and_survives_a_failed_fetch(tmp_path):
    seen = []
    def ok(a, b): seen.append((a, b)); return RAW
    first = corp_feed.load(str(tmp_path), "2025-09-08", "2026-11-20", fetch=ok, log=lambda *x: None)
    assert len(first) == 2 and seen[0][0] == pd.Timestamp("2025-09-08")                    # first run reads the whole window
    n = len(seen); corp_feed.load(str(tmp_path), "2025-09-08", "2026-11-21", fetch=ok, log=lambda *x: None)
    assert len(seen) == n + 1 and seen[n][0] == pd.Timestamp("2026-11-21") - pd.Timedelta(days=corp_feed.REFRESH_DAYS)      # later runs only re-read the recent window
    def boom(a, b): raise RuntimeError("blocked")
    msgs = []; again = corp_feed.load(str(tmp_path), "2025-09-08", "2026-11-22", fetch=boom, log=msgs.append)
    assert len(again) == 2 and msgs and "cached" in msgs[0]                                   # a failure keeps what was cached


def test_extending_the_history_backwards_fetches_the_older_span_once(tmp_path):
    seen = []
    def ok(a, b): seen.append((a, b)); return RAW
    corp_feed.load(str(tmp_path), "2025-09-08", "2026-11-20", fetch=ok, log=lambda *x: None)
    seen.clear(); corp_feed.load(str(tmp_path), "2024-06-01", "2026-11-21", fetch=ok, log=lambda *x: None)
    assert seen[0][0] == pd.Timestamp("2024-06-01") and seen[-2][1] <= pd.Timestamp("2025-09-08") and all((b - a).days <= 180 for a, b in seen)      # older span in chunks, ending where the cache began
    seen.clear(); corp_feed.load(str(tmp_path), "2024-06-01", "2026-11-22", fetch=ok, log=lambda *x: None)
    assert len(seen) == 1                                                                      # afterwards only the recent window is re-read


def world(drop=0.7855, turnover_spike=True):
    dates = pd.bdate_range("2026-05-01", periods=60); rng = np.random.default_rng(2)
    px = 250 * np.cumprod(1 + rng.normal(0, .004, 60)); t = list(dates).index(pd.Timestamp("2026-06-12")); px[t:] *= drop
    close = pd.DataFrame({"CUB": px, "OTHER": 100 * np.cumprod(1 + rng.normal(0, .004, 60))}, index=dates)
    isin = pd.DataFrame("X", index=dates, columns=close.columns); lot = pd.DataFrame(np.nan, index=dates, columns=close.columns)
    turn = pd.DataFrame(40.0, index=dates, columns=close.columns)
    if turnover_spike: turn.iloc[t - 3:t + 1, 0] = 140.0                                   # bonus-news trading before and on the ex-date
    return close, isin, lot, turn


def test_the_cub_miss_is_fixed_by_the_exchange_row():
    close, isin, lot, turn = world()
    assert len(corp.find_events(close, isin, lot, turn, None)) == 0                         # price-only detection misses it: ratio 0.7855 is past the cut-off
    feed = corp_feed.rows([dict(symbol="CUB", exDate="12-Jun-2026", subject="Bonus 1:3")])
    ev = corp.find_events(close, isin, lot, turn, feed)
    assert len(ev) == 1 and ev.iloc[0]["decision"] == "accepted" and ev.iloc[0]["factor"] == 0.75 and ev.iloc[0]["date"] == pd.Timestamp("2026-06-12")
    F = corp.factors(close.index, list(close.columns), ev)
    adj = close["CUB"] * F["CUB"]
    assert abs(adj.iloc[list(close.index).index(pd.Timestamp("2026-06-12"))] / adj.iloc[list(close.index).index(pd.Timestamp("2026-06-11"))] - 1) < .06      # the 21% cliff is gone


def test_exchange_rows_cannot_invent_an_adjustment():
    close, isin, lot, turn = world(drop=1.0)                                                # the price never fell
    feed = corp_feed.rows([dict(symbol="CUB", exDate="12-Jun-2026", subject="Bonus 1:3"), dict(symbol="MISSING", exDate="12-Jun-2026", subject="Bonus 1:1")])
    assert len(corp.find_events(close, isin, lot, turn, feed)) == 0


def test_exchange_ratio_replaces_a_price_estimate_for_the_same_event():
    close, isin, lot, turn = world(drop=0.5 * 0.99, turnover_spike=False)                   # a 1:5 split seen at ratio .495 and found by price alone
    est = corp.find_events(close, isin, lot, turn, None); assert len(est) == 1
    feed = corp_feed.rows([dict(symbol="CUB", exDate="12-Jun-2026", subject="Bonus 1:1")])
    ev = corp.find_events(close, isin, lot, turn, feed); assert len(ev) == 1 and ev.iloc[0]["factor"] == 0.5 and ev.iloc[0]["decision"] == "accepted"


def test_a_split_and_a_bonus_on_the_same_ex_date_multiply():
    df = corp_feed.rows([dict(symbol="AHCL", exDate="24-Apr-2026", subject="Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"),
                         dict(symbol="AHCL", exDate="24-Apr-2026", subject="Bonus 1:1")])
    assert len(df) == 1 and abs(df.iloc[0]["ratio"] - 0.1) < 1e-9 and "Bonus 1:1" in df.iloc[0]["note"] and "Split" in df.iloc[0]["note"]
