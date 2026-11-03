import json, os

import pandas as pd

import nse
import run


def day_entry(bse):
    return dict(deliv=pd.DataFrame(), cm=pd.DataFrame(), fo=pd.DataFrame(), nifty=1.0, bse=bse)


def test_nothing_new_logic():
    done = {"asof": "2026-11-02", "complete": True}
    assert run.nothing_new(done, pd.Timestamp("2026-11-02"), True)            # live with BSE: skip
    assert run.nothing_new(done, pd.Timestamp("2026-11-02"), False)           # cannot get worse: skip
    assert not run.nothing_new(done, pd.Timestamp("2026-11-03"), False)       # a new session: build
    nse_only = {"asof": "2026-11-02", "complete": False}
    assert run.nothing_new(nse_only, pd.Timestamp("2026-11-02"), False)       # still waiting for BSE: skip
    assert not run.nothing_new(nse_only, pd.Timestamp("2026-11-02"), True)    # BSE arrived: rebuild
    assert not run.nothing_new({}, pd.Timestamp("2026-11-02"), True)          # nothing published yet


def test_marker_round_trip(tmp_path):
    assert run.previously_published(str(tmp_path)) == {}
    (tmp_path / run.MARKER).write_text(json.dumps({"asof": "2026-11-02", "complete": False}))
    assert run.previously_published(str(tmp_path)) == {"asof": "2026-11-02", "complete": False}


def test_every_day_without_bse_is_retried_until_it_has_data():
    days = pd.bdate_range("2026-09-01", periods=30)
    parsed = {d: day_entry(pd.DataFrame({"dq": [1]})) for d in days}
    parsed[days[0]] = day_entry(None)
    parsed[days[-1]] = day_entry(None)        # newest day, BSE not out yet
    assert nse.recent_without_bse(parsed) == {days[0], days[-1]}


def test_bse_delivery_dates_without_a_leading_zero_are_accepted(tmp_path):
    import io, zipfile
    for day, text in ((pd.Timestamp("2026-11-02"), "2112026"), (pd.Timestamp("2026-10-30"), "30102026"), (pd.Timestamp("2026-11-09"), "9112026"), (pd.Timestamp("2026-11-11"), "9112026")):
        root = str(tmp_path / f"{day:%Y%m%d}")
        for kind, name, content in (("bsedel", "d.txt", f"DATE|SCRIP CODE|DELIVERY QTY|DAY'S VOLUME\n{text}|500325|40|100\n"),
                                    ("bsecm", "c.csv", "FinInstrmId,ISIN\n500325,INE002A01018\n")):
            p = nse.path(root, kind, day); os.makedirs(os.path.dirname(p), exist_ok=True)
            if kind == "bsedel":
                with zipfile.ZipFile(p, "w") as z: z.writestr(name, content)
            else:
                open(p, "w").write(content)
        cm = pd.DataFrame({"isin": ["INE002A01018"]}, index=["RELIANCE"])
        out = nse.read_bse(root, day, cm)
        if day == pd.Timestamp("2026-11-11"): assert out is None            # a file stamped with another date is still rejected
        else: assert out is not None and out.loc["RELIANCE", "dq"] == 40, text


def test_sync_asks_for_bse_again_for_a_day_parsed_without_it(tmp_path, monkeypatch):
    d = pd.Timestamp("2026-11-02")
    pd.to_pickle({d: day_entry(None)}, tmp_path / "parsed.pkl")
    calls = []
    monkeypatch.setattr(nse, "download", lambda kind, day, root: calls.append(kind) or "404")
    assert nse.sync(str(tmp_path), d, d) == [d]
    assert sorted(calls) == ["bsecm", "bsedel"]                                # NSE files are not fetched again


def test_parse_all_fills_in_bse_once_published(tmp_path, monkeypatch):
    d = pd.Timestamp("2026-11-02"); root = str(tmp_path)
    pd.to_pickle({d: day_entry(None)}, tmp_path / "parsed.pkl")
    for kind in ("cm", "fo", "idx", "bsedel", "bsecm"):
        p = nse.path(root, kind, d); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write("x")
    bse = pd.DataFrame({"dq": [5.0], "vol": [9.0]}, index=["AAA"])
    monkeypatch.setattr(nse, "read_bse", lambda root, day, cm: bse)
    out = nse.parse_all(root, [d])
    assert out[d]["bse"] is bse or out[d]["bse"].equals(bse)
    assert pd.read_pickle(tmp_path / "parsed.pkl")[d]["bse"] is not None


def test_morning_retry_rules():
    today = pd.Timestamp("2026-11-03"); last = pd.Timestamp("2026-11-02")
    done = {"asof": "2026-11-02", "complete": True, "built_on": "2026-11-03", "mcx_latest": "2026-11-02"}
    never = lambda: (_ for _ in ()).throw(AssertionError("MCX must not be asked"))
    assert not run.can_skip({**done, "asof": "2026-11-01"}, last, True, today, True, never)          # a newer session: build (MCX is not even asked)
    assert run.can_skip(done, last, True, today, True, lambda: "2026-11-02")                         # built today, MCX unchanged: skip
    assert not run.can_skip(done, last, True, today, True, lambda: "2026-11-03")                     # MCX posted a newer day: build
    assert not run.can_skip({**done, "built_on": "2026-11-02"}, last, True, today, True, never)      # the 6 AM run never happened: a daily retry builds
    assert run.can_skip({**done, "built_on": "2026-11-02"}, last, True, today, False, lambda: "2026-11-02")   # an evening retry does not need a build today
    assert not run.can_skip({k: v for k, v in done.items() if k != "mcx_latest"}, last, True, today, True, lambda: "2026-11-02")  # older marker: build once to record MCX
