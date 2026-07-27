import unittest

from Game_main.g21_season import reward_for_xp, season_days_left, season_key


class SeasonTests(unittest.TestCase):
    def test_eight_week_key_and_days_are_bounded(self):
        self.assertEqual(season_key(__import__('datetime').date(2026, 1, 1)), '2026-S1')
        self.assertGreaterEqual(season_days_left(__import__('datetime').date(2026, 1, 1)), 0)

    def test_rewards_are_cosmetic_milestones(self):
        self.assertEqual(reward_for_xp(19), [])
        self.assertEqual(reward_for_xp(60)[-1][0], 60)
