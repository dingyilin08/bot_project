import unittest

from Game_main.g19_sect import DAILY_CONTRIBUTION, parse_research, week_key


class SectTests(unittest.TestCase):
    def test_research_is_limited_to_public_pve_options(self):
        self.assertEqual(parse_research("丹道"), "丹道")
        self.assertIsNone(parse_research("PVP伤害"))

    def test_week_key_is_stable(self):
        self.assertEqual(week_key(__import__("datetime").date(2026, 1, 1)), "2026-W01")
        self.assertEqual(DAILY_CONTRIBUTION, 20)
