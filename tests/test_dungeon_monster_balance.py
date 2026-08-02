import asyncio
import unittest
from pathlib import Path

from Game_main.g6_dungeon import DUNGEON_BASE_STATS, generate_monster_attr_by_ratio


class DungeonMonsterBalanceTests(unittest.TestCase):
    def test_monster_hp_is_deterministic_and_independent_of_player_attributes(self):
        monster = {"hp_ratio": 1.2, "atk_ratio": 1.0, "def_ratio": 1.0}
        first = asyncio.run(generate_monster_attr_by_ratio(30, monster, 30, 1, {"qixue": 1}))
        second = asyncio.run(generate_monster_attr_by_ratio(30, monster, 99, 1, {"qixue": 999999}))
        self.assertEqual(first["qixue"], second["qixue"])
        self.assertEqual(7200, first["qixue"])

    def test_wave_and_cross_world_hp_modifiers_are_explicit(self):
        boss = {"hp_ratio": 4.2, "atk_ratio": 1.0, "def_ratio": 1.0}
        wave_one = asyncio.run(generate_monster_attr_by_ratio(50, boss, 50, 1))
        wave_three = asyncio.run(generate_monster_attr_by_ratio(50, boss, 50, 3))
        cross_world = asyncio.run(generate_monster_attr_by_ratio(50, boss, 50, 1, is_different_world=True))
        self.assertEqual(63000, wave_one["qixue"])
        self.assertEqual(72450, wave_three["qixue"])
        self.assertEqual(72450, cross_world["qixue"])

    def test_base_hp_scales_monotonically_with_dungeon_level(self):
        values = [stats[2] for _, stats in sorted(DUNGEON_BASE_STATS.items())]
        self.assertEqual(values, sorted(values))

    def test_migration_normalizes_legacy_self_buffs_and_boss_hp(self):
        sql = (Path(__file__).resolve().parents[1] / "数据库源文件" / "p2_combat_target_and_hp_normalization.sql").read_text(encoding="utf-8")
        self.assertIn("SET buff_target = 1", sql)
        self.assertIn("WHERE buff_target = 0", sql)
        self.assertIn("WHEN 50 THEN 4.20", sql)
        self.assertIn("WHERE m.type = 'boss'", sql)


if __name__ == "__main__":
    unittest.main()
