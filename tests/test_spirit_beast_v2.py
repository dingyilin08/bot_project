import asyncio
import unittest
from pathlib import Path

from Game_domain.spirit_beast_v2_rules import (
    TEMPLATES,
    WORLDS,
    choose_template,
    feed_plan,
    formation_resonance,
    return_refund,
    roll_quality,
)
from Tool.combat_system import CombatEntity, CombatManager
from output_main import jiance


class SpiritBeastV2RuleTests(unittest.TestCase):
    def test_catalog_contains_four_common_and_eighteen_world_beasts(self):
        common = [row for row in TEMPLATES if row[2] == "诸天通用"]
        core = [row for row in TEMPLATES if row[2] in WORLDS]
        self.assertEqual(len(TEMPLATES), 22)
        self.assertEqual(len(common), 4)
        self.assertEqual(len(core), 18)
        for world in WORLDS:
            self.assertEqual(len([row for row in core if row[2] == world]), 3)

    def test_identification_hard_pity(self):
        self.assertEqual(roll_quality("稳定", 9, 0, 9999), "地品")
        self.assertEqual(roll_quality("稳定", 0, 59, 0), "天品")

    def test_template_selection_prefers_unowned_candidate(self):
        first = choose_template("斗气大陆", "地品", 7, "one", ())
        second = choose_template(
            "斗气大陆", "地品", 7, "two", (first[0],)
        )
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(second[2], "斗气大陆")

    def test_feed_respects_role_and_stage_caps(self):
        result = feed_plan(9, 0, 100, role_level=50, stage=0)
        self.assertEqual(result["level"], 10)
        self.assertEqual(result["cap"], 10)
        self.assertLess(result["used"], 100)

    def test_world_and_mixed_resonance_are_mutually_exclusive(self):
        world = formation_resonance(
            ["大荒", "大荒", "北斗星域"], ["雷", "土", "风"]
        )
        mixed = formation_resonance(
            ["斗气大陆", "大荒", "北斗星域"], ["火", "雷", "风"]
        )
        self.assertEqual(world["type"], "WORLD")
        self.assertEqual(world["count"], 2)
        self.assertEqual(mixed["type"], "ELEMENT")

    def test_return_refund_grows_monotonically(self):
        low = return_refund(10, 1)
        high = return_refund(30, 3)
        self.assertGreater(high["spirit_essence"], low["spirit_essence"])
        self.assertGreater(high["beast_material"], low["beast_material"])

    def test_new_commands_preserve_space_separated_arguments(self):
        cases = {
            "灵兽技能卸下 1001 2": ("灵兽技能卸下", "1001 2"),
            "灵兽一键照料 静观": ("灵兽一键照料", "静观"),
            "灵兽派遣领取 全部": ("灵兽派遣领取", "全部"),
            "灵兽批量归真确认 ABC123": ("灵兽批量归真确认", "ABC123"),
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(asyncio.run(jiance(message)), expected)

    def test_migration_preserves_old_assets_and_creates_v2_tables(self):
        sql = (
            Path(__file__).resolve().parents[1]
            / "数据库源文件"
            / "p8_spirit_beast_v2.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("user_spirit_beast_v2", sql)
        self.assertIn("SELECT id,uid,beast_id", sql)
        self.assertIn("user_spirit_beast_formation", sql)
        self.assertIn("spirit_beast_reward_ledger", sql)
        self.assertIn("(3200,'基础兽材'", sql)


class SpiritBeastV2CombatTests(unittest.TestCase):
    @staticmethod
    def _entity(name, hp=1000, attack=200, defense=100, speed=100, kind="player"):
        return CombatEntity(name, {
            "qixue": hp, "gongji": attack, "fangyu": defense,
            "sudu": speed, "baoji": 0, "baoshang": 0,
            "shanbi": 0, "mingzhong": 10000, "pofang": 0,
            "xixue": 0, "max_fali": 100, "entity_type": kind,
        })

    def test_main_contract_follows_up_and_survives_snapshot_restore(self):
        player = self._entity("玩家")
        enemy = self._entity("首领", hp=2000, kind="boss")
        beast = {
            "schema_version": 2,
            "main": {
                "id": 101, "name": "紫晶翼狮", "role": "STRIKER",
                "effect": {"value": 6}, "skills": [],
            },
            "formation": [], "synergy": {},
            "spirit_body": {"maximum": 500, "current": 500},
        }
        player.role_data["spirit_beast"] = beast
        manager = CombatManager(player, enemy)
        manager.resolve_round({"action_type": "DEFEND"})
        self.assertTrue(any(
            item["type"] == "spirit_beast_followup"
            for item in manager.combat_log
        ))
        restored = CombatManager.from_snapshot(manager.to_snapshot())
        self.assertEqual(restored.spirit_beast["main"]["id"], 101)
        self.assertIn("spirit_body", restored.spirit_beast)


if __name__ == "__main__":
    unittest.main()
