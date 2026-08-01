import unittest

from Game_main.g1_role import _breakthrough_succeeds, _display_rate_bonus


class RoleBreakthroughTests(unittest.TestCase):
    def test_roll_at_or_below_rate_succeeds(self):
        self.assertTrue(_breakthrough_succeeds(1, 90))
        self.assertTrue(_breakthrough_succeeds(90, 90))

    def test_roll_above_rate_fails(self):
        self.assertFalse(_breakthrough_succeeds(91, 90))
        self.assertFalse(_breakthrough_succeeds(100, 90))

    def test_rate_is_clamped_to_percentage_range(self):
        self.assertTrue(_breakthrough_succeeds(100, 150))
        self.assertFalse(_breakthrough_succeeds(1, -10))

    def test_breakthrough_rate_bonus_uses_panel_percentage_unit(self):
        self.assertEqual("0.2%", _display_rate_bonus(20))
        self.assertEqual("20%", _display_rate_bonus(2000))


if __name__ == "__main__":
    unittest.main()
