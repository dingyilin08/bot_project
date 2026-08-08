import unittest

from Game_domain.abyss_rules import (
    abyss_monster_multiplier,
    abyss_rating,
    abyss_tier_index,
    abyss_tier_min_level,
    build_abyss_monster_stats,
    calculate_abyss_layer_reward,
    calculate_reward_delta,
    placement_target,
    select_wave_templates,
)


class AbyssRuleTests(unittest.TestCase):
    def test_layer_tier_caps_at_tenth_world_dungeon(self):
        expected = {1: (0, 1), 10: (0, 1), 11: (1, 10), 90: (8, 80), 91: (9, 90), 999: (9, 90)}
        for layer, value in expected.items():
            self.assertEqual((abyss_tier_index(layer), abyss_tier_min_level(layer)), value)

    def test_rating_boundaries_are_inclusive(self):
        self.assertEqual([abyss_rating(value) for value in (9, 10, 19, 20, 29, 30)], [0, 1, 1, 2, 2, 3])

    def test_layer_and_cross_world_multipliers_stack(self):
        self.assertAlmostEqual(abyss_monster_multiplier(1), 1.05)
        self.assertAlmostEqual(abyss_monster_multiplier(1, True), 1.26)
        monster = {
            "type": "normal", "hp_ratio": 2, "atk_ratio": 1, "def_ratio": 1,
            "spd_ratio": 1, "crit_ratio": 1, "crit_dmg_ratio": 1,
            "dodge_ratio": 1, "hit_ratio": 1,
        }
        stats = build_abyss_monster_stats(1, monster, cross_world=True)
        self.assertEqual(stats["gongji"], 693)
        self.assertEqual(stats["qixue"], 7056)

    def test_reward_and_upgrade_delta(self):
        one = calculate_abyss_layer_reward(101600, 10, 1)
        three = calculate_abyss_layer_reward(101600, 10, 3)
        self.assertEqual(one, {"exp": 100, "lingshi": 450, "xianyu": 30})
        self.assertEqual(three, {"exp": 100, "lingshi": 750, "xianyu": 90})
        self.assertEqual(
            calculate_reward_delta(101600, 10, 1, 3, exp_rewarded=True),
            {"exp": 0, "lingshi": 300, "xianyu": 60},
        )

    def test_level_one_hundred_has_no_exp_reward(self):
        self.assertEqual(calculate_abyss_layer_reward(0, 100, 3)["exp"], 0)

    def test_placement_is_one_to_one_from_level_fifty(self):
        with self.assertRaises(ValueError):
            placement_target(49)
        self.assertEqual(placement_target(50), 50)
        self.assertEqual(placement_target(100), 100)

    def test_wave_is_stable_four_normal_and_one_boss(self):
        normals = [{"id": 1, "type": "normal"}, {"id": 2, "type": "normal"}]
        bosses = [{"id": 3, "type": "boss"}]
        first = select_wave_templates(normals, bosses, rng_seed="fixed", wave_no=2)
        second = select_wave_templates(normals, bosses, rng_seed="fixed", wave_no=2)
        self.assertEqual(first, second)
        self.assertEqual([item["type"] for item in first], ["normal"] * 4 + ["boss"])


if __name__ == "__main__":
    unittest.main()
