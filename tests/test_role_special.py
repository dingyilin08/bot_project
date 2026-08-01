# -*- coding: utf-8 -*-
import unittest

from Game_domain.role_special_catalog import get_role_spec, validate_role_spec
from Game_domain.role_special_service import world_boss_contribution
from Tool.combat_system import CombatEntity, CombatManager
from Tool.qq_keyboard import attach_keyboard, extract_keyboard


def entity(name, hp=1000, entity_type="player", role_special=None):
    role_data = {
        "qixue": hp, "gongji": 1000, "fangyu": 100, "sudu": 100,
        "baoji": 0, "baoshang": 15000, "shanbi": 0, "mingzhong": 10000,
        "pofang": 0, "xixue": 0, "max_fali": 100, "entity_type": entity_type,
    }
    if role_special:
        role_data["role_special"] = role_special
    return CombatEntity(name, role_data, [])


class RoleSpecialCatalogTests(unittest.TestCase):
    def test_xiao_yan_catalog_has_original_growth_shape(self):
        spec = get_role_spec("萧炎")
        validate_role_spec(spec)
        self.assertEqual(9, len(spec["abilities"]))
        self.assertEqual(5, len(spec["stages"]))
        self.assertEqual("焚诀", spec["growth_name"])
        self.assertEqual({4, 5}, {item["rarity"] for item in spec["abilities"]})

    def test_wang_lin_uses_concepts_and_eight_ancient_god_stars(self):
        spec = get_role_spec("王林")
        validate_role_spec(spec)
        self.assertEqual("古神星点", spec["growth_name"])
        self.assertEqual(8, len(spec["stages"]))
        self.assertIn("轮回本源", {item["name"] for item in spec["abilities"]})

    def test_han_li_reaches_seventy_two_swords_and_unlocks_combo_at_thirty_six(self):
        spec = get_role_spec("韩立")
        validate_role_spec(spec)
        self.assertEqual(4, spec["combo_min_stage"])
        self.assertEqual("七十二口飞剑", spec["stages"][-1]["name"])
        self.assertIn("大庚剑阵", {item["name"] for item in spec["abilities"]})


class RoleSpecialCombatTests(unittest.TestCase):
    def test_special_active_is_once_per_battle_and_boss_capped(self):
        special = {
            "role_id": 10001, "role_name": "萧炎",
            "active": {"id": 1, "name": "帝炎", "multiplier": 2.0, "effect": {"type": "DAMAGE"}},
            "passive": None,
        }
        manager = CombatManager(entity("萧炎", role_special=special), entity("Boss", hp=1000, entity_type="boss"))
        valid, _ = manager.validate_player_action({"action_type": "SPECIAL"})
        self.assertTrue(valid)
        before = manager.enemy.hp
        manager.resolve_round({"action_type": "SPECIAL"})
        self.assertLessEqual(before - manager.enemy.hp, 30)
        valid, reason = manager.validate_player_action({"action_type": "SPECIAL"})
        self.assertFalse(valid)
        self.assertIn("已经施放", reason)
        restored = CombatManager.from_snapshot(manager.to_snapshot())
        self.assertTrue(restored.role_special["used"])

    def test_special_passive_is_snapshotted(self):
        special = {
            "role_id": 10001, "role_name": "萧炎", "active": None,
            "passive": {"id": 2, "name": "骨灵冷火", "effect": {"type": "ENEMY_ATTACK_DOWN", "value": 10, "duration": 1}},
        }
        manager = CombatManager(entity("萧炎", role_special=special), entity("敌人"))
        manager.initialize()
        self.assertTrue(manager.role_special["passive_triggered"])
        self.assertTrue(manager.enemy.has_buff("attack_down"))

    def test_world_boss_special_obeys_three_percent_cap(self):
        special = {"role_name": "萧炎", "active": {"name": "帝炎", "multiplier": 2.0}}
        damage, note = world_boss_contribution(special, combat_power=999999, max_hp=1_000_000)
        self.assertEqual(30_000, damage)
        self.assertIn("帝炎", note)


class QQKeyboardTests(unittest.TestCase):
    MARKDOWN = "操作：<qqbot-cmd-input text='角色养成' show='角色养成' /> | <qqbot-cmd-input text='装备专属 ' show='装备专属*' />"

    def test_group_buttons_never_direct_send(self):
        content, keyboard = extract_keyboard(self.MARKDOWN, is_group=True)
        self.assertNotIn("qqbot-cmd-input", content)
        buttons = keyboard["content"]["rows"][0]["buttons"]
        self.assertFalse(buttons[0]["action"]["enter"])
        self.assertFalse(buttons[1]["action"]["enter"])

    def test_c2c_only_complete_command_direct_sends(self):
        _, keyboard = extract_keyboard(self.MARKDOWN, is_group=False)
        buttons = keyboard["content"]["rows"][0]["buttons"]
        self.assertTrue(buttons[0]["action"]["enter"])
        self.assertFalse(buttons[1]["action"]["enter"])

    def test_markdown_result_is_upgraded(self):
        result = attach_keyboard({"type": "markdown", "content": self.MARKDOWN}, is_group=True)
        self.assertEqual("markdown_keyboard", result["type"])
        self.assertIn("keyboard", result)


if __name__ == "__main__":
    unittest.main()
