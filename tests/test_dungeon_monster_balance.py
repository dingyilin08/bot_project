import asyncio
import unittest
from pathlib import Path

from Game_main.g6_dungeon import (
    DUNGEON_BASE_STATS,
    apply_solo_pve_stat_effects,
    generate_monster_attr_by_ratio,
    solo_pve_effect_snapshot,
)


class DungeonMonsterBalanceTests(unittest.TestCase):
    def test_monster_hp_is_deterministic_and_independent_of_player_attributes(self):
        monster = {"hp_ratio": 1.2, "atk_ratio": 1.0, "def_ratio": 1.0}
        first = asyncio.run(generate_monster_attr_by_ratio(30, monster, 30, 1, {"qixue": 1}))
        second = asyncio.run(generate_monster_attr_by_ratio(30, monster, 99, 1, {"qixue": 999999}))
        self.assertEqual(first["qixue"], second["qixue"])
        self.assertEqual(7200, first["qixue"])

    def test_wave_and_cross_world_hp_modifiers_are_explicit(self):
        boss = {"hp_ratio": 2.9, "atk_ratio": 1.0, "def_ratio": 1.0}
        wave_one = asyncio.run(generate_monster_attr_by_ratio(50, boss, 50, 1))
        wave_three = asyncio.run(generate_monster_attr_by_ratio(50, boss, 50, 3))
        cross_world = asyncio.run(generate_monster_attr_by_ratio(50, boss, 50, 1, is_different_world=True))
        self.assertEqual(36250, wave_one["qixue"])
        self.assertEqual(41687, wave_three["qixue"])
        self.assertEqual(41687, cross_world["qixue"])

    def test_base_hp_scales_monotonically_with_dungeon_level(self):
        values = [stats[2] for _, stats in sorted(DUNGEON_BASE_STATS.items())]
        self.assertEqual(values, sorted(values))

    def test_high_level_curve_has_no_50_to_60_cliff(self):
        level_50 = DUNGEON_BASE_STATS[50]
        level_60 = DUNGEON_BASE_STATS[60]
        self.assertLessEqual(level_60[0] / level_50[0], 1.10)
        self.assertLessEqual(level_60[1] / level_50[1], 1.10)
        self.assertLessEqual(level_60[2] / level_50[2], 1.10)

    def test_late_game_secondary_stats_remain_below_hard_caps(self):
        level_90 = DUNGEON_BASE_STATS[90]
        self.assertLessEqual(level_90[4], 2500)
        self.assertLessEqual(level_90[6], 1500)
        self.assertLessEqual(level_90[8], 1000)

    def test_migration_normalizes_legacy_self_buffs_and_boss_hp(self):
        sql = (Path(__file__).resolve().parents[1] / "数据库源文件" / "p2_combat_target_and_hp_normalization.sql").read_text(encoding="utf-8")
        self.assertIn("SET buff_target = 1", sql)
        self.assertIn("WHERE buff_target = 0", sql)
        self.assertIn("WHEN 50 THEN 4.20", sql)
        self.assertIn("WHERE m.type = 'boss'", sql)

    def test_data_driven_balance_migration_caps_boss_and_late_normal_stats(self):
        sql = (Path(__file__).resolve().parents[1] / "数据库源文件" / "p3_monster_balance_20260804.sql").read_text(encoding="utf-8")
        self.assertIn("WHEN 50 THEN 2.90", sql)
        self.assertIn("WHEN 50 THEN 1.55", sql)
        self.assertIn("LEAST(m.atk_ratio, 1.50)", sql)
        self.assertIn("d.min_level >= 60", sql)

    def test_causal_and_season_effects_are_frozen_without_scaling_monsters(self):
        effect = solo_pve_effect_snapshot(
            {"marks": ("遗宝因果", "丹师善缘"), "attack_bp": 300, "defense_bp": 300},
            {"active": True, "name": "厚土", "attack_bp": 0, "defense_bp": 300, "speed_bp": 300},
        )
        self.assertEqual((effect["attack_bp"], effect["defense_bp"], effect["speed_bp"]), (300, 600, 300))
        self.assertEqual(apply_solo_pve_stat_effects(100, 100, 100, effect), (103, 106, 103))
        capped = solo_pve_effect_snapshot(
            {"attack_bp": 9_999, "defense_bp": 9_999},
            {"attack_bp": 9_999, "defense_bp": 9_999, "speed_bp": 9_999},
        )
        self.assertEqual(apply_solo_pve_stat_effects(100, 100, 100, capped), (110, 110, 110))


if __name__ == "__main__":
    unittest.main()
