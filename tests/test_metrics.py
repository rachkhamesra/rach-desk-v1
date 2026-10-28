/Users/rachitkhamesra/.zprofile:2: no such file or directory: /opt/homebrew/bin/brew
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


if __name__ == "__main__":
    unittest.main()
