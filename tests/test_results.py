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
