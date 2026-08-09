import unittest

from Game_domain.dungeon_reward_rules import (
    ENHANCE_BASE_COST_BY_DUNGEON_LEVEL,
    FULL_CLEAR_BATTLE_COUNT,
    FULL_CLEAR_ENHANCE_COST_MULTIPLIER,
    allocate_full_clear_total,
    calculate_encounter_currency,
    calculate_full_clear_currency,
)


class DungeonRewardRulesTests(unittest.TestCase):
    def test_lingshi_curve_tracks_equipment_enhance_costs(self):
        for min_level, enhance_cost in ENHANCE_BASE_COST_BY_DUNGEON_LEVEL.items():
            _, lingshi = calculate_full_clear_currency(100, 1, min_level)
            self.assertEqual(
                lingshi,
                enhance_cost * FULL_CLEAR_ENHANCE_COST_MULTIPLIER,
            )

    def test_top_dungeon_has_reasonable_full_clear_income(self):
        exp, lingshi = calculate_full_clear_currency(300_000, 25_000, 90)
        self.assertEqual(exp, 6_750_000)
        self.assertEqual(lingshi, 2_400_000)
        self.assertEqual(lingshi * 20, 48_000_000)

    def test_manual_encounters_sum_to_exact_sweep_total(self):
        expected = calculate_full_clear_currency(300_000, 25_000, 90)
        encounters = [
            calculate_encounter_currency(300_000, 25_000, 90, index)
            for index in range(1, FULL_CLEAR_BATTLE_COUNT + 1)
        ]
        self.assertEqual(sum(value[0] for value in encounters), expected[0])
        self.assertEqual(sum(value[1] for value in encounters), expected[1])

    def test_integer_allocator_preserves_small_and_large_totals(self):
        for total in (0, 1, 37, 1000, 2_400_000, 6_750_000):
            rewards = allocate_full_clear_total(total)
            self.assertEqual(len(rewards), FULL_CLEAR_BATTLE_COUNT)
            self.assertEqual(sum(rewards), total)
            self.assertTrue(all(value >= 0 for value in rewards))

    def test_reward_curve_is_monotonic(self):
        rewards = [
            calculate_full_clear_currency(100, 1, level)[1]
            for level in ENHANCE_BASE_COST_BY_DUNGEON_LEVEL
        ]
        self.assertEqual(rewards, sorted(rewards))
        self.assertEqual(len(rewards), len(set(rewards)))


if __name__ == "__main__":
    unittest.main()
