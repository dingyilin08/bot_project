import unittest

from Game_main.g14_estate import (
    apply_cultivation_duration,
    build_estate_effect_snapshot,
    claim_reward,
    cultivation_duration_reduction_bp,
    forge_success_bonus_bp,
    normalize_estate_levels,
    scripture_skill_effect_bonus_bp,
    spirit_beast_capacity,
    upgrade_cost,
)
from Game_main.g7_equip import (
    apply_enhance_cost_discount,
    calc_equip_sell_info,
    get_enhance_cost,
    get_enhance_success_rate_bp,
    get_research_enhance_discount_bp,
)


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

    def test_level_reader_whitelists_names_codes_and_clamps_dirty_values(self):
        levels = normalize_estate_levels(
            [("聚灵阵", 99), ("forge_table", 0), ("未知建筑", 10), ("藏经阁", "6")]
        )
        self.assertEqual(
            levels,
            {
                "spirit_array": 10,
                "forge_table": 1,
                "beast_garden": 1,
                "scripture_library": 6,
            },
        )

    def test_all_estate_rules_have_exact_boundaries(self):
        self.assertEqual(cultivation_duration_reduction_bp(1), 0)
        self.assertEqual(cultivation_duration_reduction_bp(10), 1800)
        self.assertEqual(apply_cultivation_duration(120, 10), 99)
        self.assertEqual(apply_cultivation_duration(30, 10), 30)
        self.assertEqual(forge_success_bonus_bp(1), 0)
        self.assertEqual(forge_success_bonus_bp(10), 450)
        self.assertEqual([spirit_beast_capacity(level) for level in (1, 3, 4, 6, 7, 9, 10)], [4, 4, 5, 5, 6, 6, 7])
        self.assertEqual(scripture_skill_effect_bonus_bp(10), 450)

    def test_effect_snapshot_uses_stable_codes_and_rule_version(self):
        snapshot = build_estate_effect_snapshot(
            {"聚灵阵": 10, "炼器台": 8, "灵兽园": 4, "藏经阁": 3}
        )
        self.assertEqual(snapshot["rule_version"], "estate.v1")
        self.assertEqual(snapshot["levels"]["spirit_array"], 10)
        self.assertEqual(snapshot["effects"]["cultivation_duration_reduction_bp"], 1800)
        self.assertEqual(snapshot["effects"]["forge_success_bonus_bp"], 350)
        self.assertEqual(snapshot["effects"]["spirit_beast_capacity"], 5)
        self.assertEqual(snapshot["effects"]["pve_skill_effect_bonus_bp"], 100)

    def test_forge_bonus_uses_basis_points_and_caps_at_one_hundred_percent(self):
        self.assertEqual(get_enhance_success_rate_bp(10, 1), 800)
        self.assertEqual(get_enhance_success_rate_bp(10, 10), 1250)
        self.assertEqual(get_enhance_success_rate_bp(1, 10), 10000)

    def test_only_whitelisted_artifact_research_reduces_cost(self):
        active = {
            "research_type": "御器",
            "effect": {"code": "SECT_ARTIFACT", "enhance_discount_bp": 500},
        }
        self.assertEqual(get_research_enhance_discount_bp(active), 500)
        self.assertEqual(
            get_research_enhance_discount_bp(
                {"research_type": "御器", "effect": {"code": "UNSAFE", "enhance_discount_bp": 9999}}
            ),
            0,
        )
        self.assertEqual(apply_enhance_cost_discount(101, 500), 96)
        self.assertEqual(apply_enhance_cost_discount(1, 500), 1)

    def test_artifact_discount_cannot_arbitrage_nominal_sell_refund(self):
        previous_refund = 0
        paid_total = 0
        for target_level in range(1, 11):
            nominal = get_enhance_cost(1, target_level)
            paid_total += apply_enhance_cost_discount(nominal, 500)
            sell_info = calc_equip_sell_info(1, "凡品", target_level)
            self.assertEqual(
                sell_info["enhance_total_cost"],
                sum(get_enhance_cost(1, level) for level in range(1, target_level + 1)),
            )
            self.assertLessEqual(sell_info["enhance_refund"] - previous_refund, apply_enhance_cost_discount(nominal, 500))
            self.assertLessEqual(sell_info["enhance_refund"], paid_total)
            previous_refund = sell_info["enhance_refund"]
