import numpy as np
import pandas as pd

import backtest as bt


def make_world(effect, seed=1, noise=0.012):
    """Generation and IEX price with slow swings, a Nifty, and one stock whose daily return follows yesterday's GEN_YOY signal by `effect`."""
    rng = np.random.default_rng(seed)
    days = pd.date_range("2022-12-01", "2026-11-06")
    ar = lambda: pd.Series(np.cumsum(rng.normal(0, 1, len(days))) * 0.02 + np.sin(np.arange(len(days)) / 40.0), index=days)
    gen = 100 + 8 * ar(); iexp = 4000 + 400 * ar()
    sig = bt.make_signals(gen, iexp)["GEN_YOY"]
    td = pd.bdate_range("2023-09-01", "2026-11-06")
    s = sig.reindex(td).ffill().fillna(0.0)
    s = (s - s.mean()) / s.std()
    r = effect * 0.01 * s.shift(1).fillna(0) + rng.normal(0, noise, len(td))
    nifty = pd.Series(10000 * np.exp(np.cumsum(rng.normal(0.0003, 0.008, len(td)))), index=td)
    stock = pd.Series(100 * np.exp(np.cumsum(r)), index=td)
    prices = pd.DataFrame({"NTPC.NS": stock, "ADANIPOWER.NS": stock, "ADANIGREEN.NS": stock, "NHPC.NS": stock, "JSWENERGY.NS": stock, bt.NIFTY: nifty})
    return gen, iexp, prices


def test_verdict_rules():
    assert bt.verdict(2.5, 2.4, .2, 1.0, 50) == "WORKS"
    assert bt.verdict(-.3, 2.4, -.01, 1.0, 50) == "SOMETIMES WORKS"          # the 10-day sign disagrees: not a clean WORKS
    assert bt.verdict(.2, 1.3, .1, 1.0, 50) == "SOMETIMES WORKS"
    assert bt.verdict(2.2, .2, .1, 1.0, 50) == "SOMETIMES WORKS"             # strong over 10 days only
    assert bt.verdict(.1, .7, .1, .5, 50) == "COULD WORK"
    assert bt.verdict(.1, .2, .0, .1, 50) == "DOESN'T WORK"
    assert bt.verdict(-1.0, -1.0, -.1, -.5, 50) == "DOESN'T WORK"
    assert bt.verdict(-.5, -1.8, -.1, -1.0, 50) == "INVERSE"
    assert bt.verdict(2.5, 2.4, .2, 1.0, 5) == "NO DATA" and bt.verdict(np.nan, np.nan, np.nan, 0, 50) == "NO DATA"


def test_a_planted_relationship_is_found_and_its_reverse_is_called_inverse():
    gen, iexp, prices = make_world(effect=1.0)
    res = bt.run({"NTPC": gen}, iexp, prices)
    rows = {r["signal"]: r for r in res["years"]["2025"]["rows"] if r["stock"] == "NTPC"}
    assert rows["GEN_YOY"]["verdict"] in ("WORKS", "SOMETIMES WORKS") and rows["GEN_YOY"]["t20"] > 1 and rows["GEN_YOY"]["ic20"] > 0
    gen, iexp, prices = make_world(effect=-1.0)
    rows = {r["signal"]: r for r in bt.run({"NTPC": gen}, iexp, prices)["years"]["2025"]["rows"] if r["stock"] == "NTPC"}
    assert rows["GEN_YOY"]["verdict"] == "INVERSE" and rows["GEN_YOY"]["ic20"] < 0


def test_noise_is_not_called_a_relationship():
    gen, iexp, prices = make_world(effect=0.0, seed=7)
    res = bt.run({t: gen for t, _, _ in bt.STOCKS if t != "ADANIGREEN"}, iexp, prices)
    for y in ("2024", "2025", "2026"):
        assert res["years"][y]["counts"]["WORKS"] <= 2                        # about 0.4 expected by chance; never a pile of them


def test_missing_series_are_reported_not_invented():
    gen, iexp, prices = make_world(effect=0.0)
    res = bt.run({"NTPC": gen, "ADANIGREEN": None}, iexp, prices)
    green = [r for r in res["years"]["2025"]["rows"] if r["stock"] == "ADANIGREEN"]
    assert {r["signal"]: r["verdict"] for r in green}["GEN_YOY"] == "NO DATA" and {r["signal"]: r["verdict"] for r in green}["BOTH"] == "NO DATA"
    assert "no generation series" in next(r for r in green if r["signal"] == "GEN_YOY")["note"]
    assert next(r for r in green if r["signal"] == "PX_YOY")["verdict"] != "NO DATA"      # the price signal still runs
    assert bt.run({}, iexp, None) is None


def test_signals_use_only_what_was_public():
    gen, iexp, prices = make_world(effect=0.0)
    base = bt.make_signals(gen, iexp)
    cut = pd.Timestamp("2025-06-30")
    leak = gen.copy(); leak[leak.index > cut] += 1000                       # change generation after the cut date
    changed = bt.make_signals(leak, iexp)
    before = base["GEN_YOY"].index[base["GEN_YOY"].index < cut + pd.Timedelta(days=bt.GEN_LAG)]
    assert base["GEN_YOY"].reindex(before).equals(changed["GEN_YOY"].reindex(before))          # nothing after the cut reaches an earlier day
    assert not base["GEN_YOY"].loc[cut + pd.Timedelta(days=bt.GEN_LAG + 5):].equals(changed["GEN_YOY"].loc[cut + pd.Timedelta(days=bt.GEN_LAG + 5):])


def test_prices_download_weekly_and_survive_failures(tmp_path):
    calls = []
    def fetcher(sym, start, end):
        calls.append(sym)
        if sym == "NHPC.NS": return None
        idx = pd.bdate_range("2023-09-01", "2026-11-06")
        return pd.Series(np.linspace(100, 200, len(idx)), index=idx)
    quiet = lambda *a: None
    df = bt.refresh_prices(str(tmp_path), "2026-11-06", log=quiet, fetcher=fetcher)
    assert len(calls) == 6 and "NHPC.NS" not in df and bt.NIFTY in df
    n = len(calls); bt.refresh_prices(str(tmp_path), "2026-11-07", log=quiet, fetcher=fetcher)
    assert len(calls) == n + 6                                                  # the failed symbol means no "fetched" mark: it tries again
    ok = lambda sym, a, b: pd.Series(np.linspace(100, 200, 800), index=pd.bdate_range("2023-09-01", periods=800))
    bt.refresh_prices(str(tmp_path), "2026-11-08", log=quiet, fetcher=ok); calls.clear()
    bt.refresh_prices(str(tmp_path), "2026-11-12", log=quiet, fetcher=fetcher)
    assert calls == []                                                          # fetched within the last 7 days: no requests


def test_thresholds_find_a_planted_level_effect_and_none_in_noise():
    gen, iexp, prices = make_world(effect=1.0)
    G = {t: gen for t in ("NTPC", "ADANIPOWER", "NHPC", "JSWENERGY")}; G["ADANIGREEN"] = None
    thr = bt.thresholds(G, iexp, prices)
    assert set(thr) <= {k for k, _, _ in bt.SIGNALS} and thr
    for t in thr.values():
        assert [b["label"] for b in t["bands"]] == [x[2] for x in bt.BANDS] and all(c["se"] > 0 for c in t["cuts"])
    noise = bt.thresholds(G, iexp, make_world(effect=0.0)[2])
    res = bt.run(G, iexp, prices); out = bt.summarise(res, thr)
    assert set(out["years"]) == {"2024", "2025", "2026"} and "strongest" in out and isinstance(out["strong_enough"], bool)
    assert bt.summarise(bt.run(G, iexp, make_world(effect=0.0)[2]), noise)["years"]["2025"]["WORKS"] <= 2


def test_the_power_tab_panels_show_works_held_doesnt_and_threshold():
    import webpage
    gen, iexp, prices = make_world(effect=1.0)
    G = {t: gen for t in ("NTPC", "ADANIPOWER", "NHPC", "JSWENERGY")}; G["ADANIGREEN"] = None
    summ = bt.summarise(bt.run(G, iexp, prices), bt.thresholds(G, iexp, prices)); summ["generated"] = "2026-11-06"
    html = webpage.backtest_panels(summ)
    for text in ("What works", "Held in more than one year", "What doesn", "Is there a threshold?", "VERY EXPERIMENTAL", "Run on a local machine"): assert text in html
    assert html.count("<svg") >= 3 and "<table" not in html
    assert "has not been run" in webpage.backtest_panels(None)


def test_saved_results_round_trip(tmp_path):
    assert bt.load_saved(str(tmp_path / "missing.json")) is None
    (tmp_path / "r.json").write_text('{"years": {}}'); assert bt.load_saved(str(tmp_path / "r.json")) == {"years": {}}


def test_nhpc_is_scored_against_all_india_hydro_and_says_so():
    gen, iexp, prices = make_world(effect=0.0)
    res = bt.run({"NTPC": gen, "NHPC": gen}, iexp, prices)
    rows = [r for r in res["years"]["2025"]["rows"] if r["stock"] == "NHPC"]
    gen_rows = [r for r in rows if r["signal"] in ("GEN_YOY", "GEN_MOM")]
    assert gen_rows and all("hydro" in r["note"] and r["verdict"] != "NO DATA" for r in gen_rows)
    assert not any("hydro" in r["note"] for r in rows if r["signal"] in ("PX_YOY", "PX_MOM"))      # the price signals are not a proxy
    assert not any("reservoir" in i[0].lower() for i in bt.IDEAS)
