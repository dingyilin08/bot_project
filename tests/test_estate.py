import unittest

from Game_main.g14_estate import claim_reward, upgrade_cost


class EstateTests(unittest.TestCase):
    def test_upgrade_cost_is_public_and_bounded(self):
        self.assertEqual(upgrade_cost("聚灵阵", 2), 120)
        self.assertIsNone(upgrade_cost("聚灵阵", 11))

    def test_stable_claim_is_deterministic(self):
        levels = {"聚灵阵": 1, "炼器台": 1, "灵兽园": 1, "藏经阁": 1}
        self.assertEqual(claim_reward(levels, "稳健", 7, "2026-07-26"), (52, "稳定收取，没有额外风险。"))

    def test_adventure_claim_replays_identically(self):
        levels = {"聚灵阵": 2, "炼器台": 1, "灵兽园": 1, "藏经阁": 1}
        self.assertEqual(claim_reward(levels, "冒险", 7, "2026-07-26"), claim_reward(levels, "冒险", 7, "2026-07-26"))
