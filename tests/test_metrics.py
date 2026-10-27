import unittest

import metrics


class CashAccumulationEpisodeTest(unittest.TestCase):
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
