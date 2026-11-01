import unittest

import numpy as np
import pandas as pd

import results


class ResultsSignalsTest(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2026-06-01", "2026-10-27")
        self.symbols = ["HIT", "QUIET"]
        shape = (len(self.dates), len(self.symbols))
        self.M = {
            "dates": list(self.dates),
            "syms": self.symbols,
            "RAT": pd.DataFrame(np.tile([1.20, 0.80], (shape[0], 1)), index=self.dates, columns=self.symbols),
            "zmove": pd.DataFrame(np.tile([0.90, 0.20], (shape[0], 1)), index=self.dates, columns=self.symbols),
            "ret1": pd.DataFrame(np.tile([0.01, -0.002], (shape[0], 1)), index=self.dates, columns=self.symbols),
        }

    def test_declared_event_uses_only_three_prior_sessions(self):
        actual = pd.DataFrame([{"symbol": "HIT", "declared_at": pd.Timestamp("2026-10-27 17:00"), "source_url": ""}])
        rows = results.build_signals(self.M, pd.DataFrame(), actual)
        self.assertEqual([x["lag"] for x in rows[0]["sessions"]], [3, 2, 1])
        self.assertTrue(all(x["hit"] for x in rows[0]["sessions"]))
        self.assertTrue(all(x["date"] < pd.Timestamp("2026-10-27") for x in rows[0]["sessions"]))

    def test_upcoming_event_does_not_mislabel_unobserved_sessions(self):
        calendar = pd.DataFrame([{"symbol": "HIT", "meeting_date": pd.Timestamp("2026-11-03"),
                                  "announced_at": pd.Timestamp("2026-10-20"), "source_url": ""}])
        rows = results.build_signals(self.M, calendar, pd.DataFrame())
        self.assertEqual(rows[0]["sessions"], [])

    def test_both_conditions_are_required(self):
        actual = pd.DataFrame([{"symbol": "QUIET", "declared_at": pd.Timestamp("2026-10-27 17:00"), "source_url": ""}])
        rows = results.build_signals(self.M, pd.DataFrame(), actual)
        self.assertFalse(any(x["hit"] for x in rows[0]["sessions"]))


if __name__ == "__main__":
    unittest.main()


def test_result_meeting_filter_and_period_parsing():
    assert results.is_result_meeting("Financial Results/Dividend", "")
    assert results.is_result_meeting("Board Meeting Intimation", "to consider the Unaudited Financial results for the Quarterly ended September 2026")
    assert not results.is_result_meeting("Fund Raising", "To consider Fund Raising")
    assert results.period_of("approve results for the Half Yearly ended September 2026 .") == "Half Yearly ended September 2026"
    assert results.period_of("nothing here") == ""


def test_reschedule_replaces_older_date_but_next_quarter_is_kept():
    import pandas as pd
    cal = pd.DataFrame([
        dict(symbol="AAA", meeting_date=pd.Timestamp("2026-11-05"), announced_at=pd.Timestamp("2026-10-20")),
        dict(symbol="AAA", meeting_date=pd.Timestamp("2026-11-12"), announced_at=pd.Timestamp("2026-11-02")),   # rescheduled later
        dict(symbol="AAA", meeting_date=pd.Timestamp("2027-02-10"), announced_at=pd.Timestamp("2027-02-01")),   # next quarter
        dict(symbol="BBB", meeting_date=pd.Timestamp("2026-11-06"), announced_at=pd.Timestamp("2026-10-30"))])
    out = results.latest_meetings(cal)
    assert [(r.symbol, f"{r.meeting_date:%Y-%m-%d}") for r in out.itertuples()] == [("BBB", "2026-11-06"), ("AAA", "2026-11-12"), ("AAA", "2027-02-10")]
