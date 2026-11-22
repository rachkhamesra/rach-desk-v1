import unittest

import metrics
import pandas as pd


class CashAccumulationEpisodeTest(unittest.TestCase):
    def test_tracking_and_confirmed_signals_are_exclusive(self):
        base = pd.Series([True, True, False])
        above = pd.Series([True, False, True])
        confirmed, tracking = metrics.split_cash_signals(base, above)
        self.assertEqual(confirmed.tolist(), [True, False, False])
        self.assertEqual(tracking.tolist(), [False, True, False])

    def test_new_table_appearance_is_only_flagged_on_entry_day(self):
        self.assertTrue(metrics.appeared_today([False, False, True]))
        self.assertFalse(metrics.appeared_today([False, True, True]))
        self.assertFalse(metrics.appeared_today([True, False]))
        self.assertTrue(metrics.appeared_today([True, False, False, False, True]))
        self.assertFalse(metrics.appeared_today([False, True], min_days=2))
        self.assertTrue(metrics.appeared_today([False, True, True], min_days=2))

    def test_one_and_two_signal_days_are_counted(self):
        self.assertEqual(metrics.episode_state([False, True])["days"], 1)
        self.assertEqual(metrics.episode_state([True, True])["days"], 2)

    def test_setup_remains_for_two_day_cooldown(self):
        state = metrics.episode_state([True, False, False])
        self.assertEqual((state["days"], state["cooldown"]), (1, 2))
        self.assertIsNone(metrics.episode_state([True, False, False, False]))

    def test_signal_resumes_same_episode_during_cooldown(self):
        state = metrics.episode_state([True, False, False, True])
        self.assertEqual((state["days"], state["cooldown"]), (2, 0))



class CarryLastTradeTest(unittest.TestCase):
    def test_gaps_of_any_length_are_filled_but_never_past_the_last_trade(self):
        import numpy as np
        nan = np.nan
        adj = pd.DataFrame({"THIN": [10, nan, nan, nan, nan, nan, nan, nan, 12, 13, nan],          # a seven-session gap in the middle, and one missing session at the end
                            "GONE": [5, 5.5, nan, nan, nan, nan, nan, nan, nan, nan, nan],          # delisted: no trade after the second session
                            "LATE": [nan, nan, nan, 7, 7, 7, 7, 7, 7, 7, 7]})                       # listed on the fourth session: nothing before it
        C, quiet = metrics.carry_last_trade(adj)
        self.assertEqual(C["THIN"].tolist(), [10, 10, 10, 10, 10, 10, 10, 10, 12, 13, 13])           # no hole in the middle
        self.assertEqual(quiet["THIN"].tolist(), [False] + [True] * 7 + [False, False, True])
        self.assertEqual(C["GONE"].iloc[:2].tolist(), [5, 5.5]); self.assertEqual(C["GONE"].iloc[2:7].tolist(), [5.5] * 5)      # the old five-session carry still applies
        self.assertTrue(C["GONE"].iloc[7:].isna().all())                                              # but a delisted stock does not run on to today
        self.assertTrue(C["LATE"].iloc[:3].isna().all() and not quiet["LATE"].any())                  # nothing is invented before a listing


if __name__ == "__main__":
    unittest.main()
