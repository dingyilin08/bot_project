# -*- coding: utf-8 -*-
import unittest
import asyncio
from unittest.mock import AsyncMock, patch

import output_main
from Game_domain.role_special_catalog import get_role_spec, validate_role_spec
from Game_domain.role_special_intro import render_role_special_intro
from Game_domain.role_special_service import world_boss_contribution
from Game_main.g22_role_special import render_collection, render_target_selection, role_special_target
from Tool.combat_system import CombatEntity, CombatManager
from Tool.qq_keyboard import attach_keyboard, extract_keyboard
from output_main import jiance


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
    def test_role_special_intro_describes_xiao_yan_growth_and_entry(self):
        intro = render_role_special_intro("萧炎")
        self.assertIn("专属战斗养成玩法", intro)
        self.assertIn("焚诀", intro)
        self.assertIn("异火融合", intro)
        self.assertIn("萧炎养成", intro)

    def test_role_special_intro_is_available_for_all_six_roles_only(self):
        for role_name in ("萧炎", "王林", "韩立", "石昊", "叶凡", "孟川"):
            self.assertIn(role_name, render_role_special_intro(role_name, include_actions=False))
        self.assertIsNone(render_role_special_intro("不存在的角色"))

    def test_role_special_intro_command_keeps_generic_guide_compatible(self):
        self.assertEqual(("玩法介绍", "萧炎"), asyncio.run(jiance("玩法介绍 萧炎")))
        self.assertEqual(("玩法介绍", ""), asyncio.run(jiance("玩法介绍")))

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

    def test_shi_hao_requires_unique_cave_and_excludes_final_projection(self):
        spec = get_role_spec("石昊")
        validate_role_spec(spec)
        self.assertEqual("唯一洞天", spec["stages"][-1]["name"])
        self.assertEqual(12, spec["combo_min_stage"])
        self.assertIn("SH_ART_09", spec["non_combinable_codes"])

    def test_ye_fan_keeps_disputed_secrets_out_of_pool(self):
        spec = get_role_spec("叶凡")
        validate_role_spec(spec)
        disabled = {item["name"] for item in spec["abilities"] if not item.get("enabled", True)}
        self.assertEqual({"临字秘", "数秘"}, disabled)
        self.assertEqual("四极秘境", spec["stages"][3]["name"])
        self.assertTrue(spec["fixed_combos"])

    def test_meng_chuan_requires_real_scroll_for_blade_inference(self):
        spec = get_role_spec("孟川")
        validate_role_spec(spec)
        self.assertTrue(spec["requires_scroll"])
        self.assertEqual(8, len(spec["stages"]))
        self.assertEqual("时空刀印", spec["abilities"][-1]["name"])


class RoleSpecialCombatTests(unittest.TestCase):
    def test_special_active_is_once_per_battle_and_boss_capped(self):
        special = {
            "role_id": 10001, "role_name": "萧炎",
            "active": {"id": 1, "name": "帝炎", "multiplier": 2.0, "effect": {"type": "DAMAGE"}},
            "passive": None,
        }
        manager = CombatManager(entity("萧炎", role_special=special), entity("Boss", hp=1000, entity_type="boss"))
        manager.player.speed = 1000
        manager.enemy.speed = 1
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

    def test_inline_markup_stays_in_original_position_by_default(self):
        result = attach_keyboard({"type": "markdown", "content": self.MARKDOWN}, is_group=True)
        self.assertEqual("markdown", result["type"])
        self.assertEqual(self.MARKDOWN, result["content"])
        self.assertNotIn("keyboard", result)

    def test_plain_string_with_inline_markup_is_sent_as_markdown(self):
        result = attach_keyboard(self.MARKDOWN, is_group=True)
        self.assertEqual("markdown", result["type"])
        self.assertEqual(self.MARKDOWN, result["content"])

    def test_explicit_primary_actions_add_keyboard_without_removing_inline_markup(self):
        result = attach_keyboard({
            "type": "markdown",
            "content": self.MARKDOWN,
            "keyboard_commands": [
                ("战斗行动 普攻", "普通攻击"),
                ("战斗行动 防御", "防御"),
            ],
        }, is_group=True)
        self.assertEqual("markdown_keyboard", result["type"])
        self.assertIn("keyboard", result)
        self.assertEqual(self.MARKDOWN, result["content"])
        self.assertNotIn("keyboard_commands", result)


class RoleSpecialTargetTests(unittest.TestCase):
    TARGET_DATA = {
        "role_name": "萧炎",
        "items": [
            {"id": 101, "name": "帝炎", "rarity": 5, "enabled": True, "lore": "万火归一。"},
            {"id": 102, "name": "佛怒火莲", "rarity": 5, "enabled": False, "lore": "暂未开放。"},
            {"id": 103, "name": "青莲地心火", "rarity": 4, "enabled": True, "lore": "青莲之火。"},
        ],
    }

    def test_target_selection_only_lists_enabled_five_star_abilities(self):
        content = render_target_selection(self.TARGET_DATA)["content"]
        self.assertIn("专属定向 101", content)
        self.assertIn("定向·帝炎", content)
        self.assertNotIn("专属定向 102", content)
        self.assertNotIn("专属定向 103", content)

    def test_bare_target_command_opens_selection_instead_of_parsing_empty_int(self):
        with patch("Game_main.g22_role_special.collection", new=AsyncMock(return_value=self.TARGET_DATA)):
            result = asyncio.run(role_special_target.__wrapped__(1, "", ""))
        self.assertIn("五星能力定向", result["content"])
        self.assertNotIn("invalid literal", result["content"])

    def test_invalid_target_value_returns_player_facing_format_help(self):
        result = asyncio.run(role_special_target.__wrapped__(1, "", "帝炎"))
        self.assertEqual("定向设置失败：格式：专属定向 五星能力编号。", result["content"])
        self.assertNotIn("invalid literal", result["content"])


class RoleSpecialCollectionRenderTests(unittest.TestCase):
    COLLECTION_DATA = {
        "role_name": "萧炎",
        "spec": {"drop_name": "异火"},
        "items": [
            {"id": 101, "name": "帝炎", "rarity": 5, "kind": "ACTIVE", "multiplier": 2.0,
             "lore": "万火归一。", "fragments": 10, "cost": 10, "unlocked": True, "slot": "ACTIVE", "enabled": True},
            {"id": 102, "name": "佛怒火莲", "rarity": 5, "kind": "ACTIVE", "multiplier": 1.8,
             "lore": "火莲绽放。", "fragments": 4, "cost": 10, "unlocked": False, "slot": None, "enabled": True},
            {"id": 103, "name": "青莲地心火", "rarity": 4, "kind": "PASSIVE", "multiplier": 0.5,
             "lore": "青莲之火。", "fragments": 0, "cost": 6, "unlocked": False, "slot": None, "enabled": True},
            {"id": 104, "name": "陨落心炎", "rarity": 4, "kind": "PASSIVE", "multiplier": 0.6,
             "lore": "心火淬体。", "fragments": 6, "cost": 6, "unlocked": True, "slot": "PASSIVE", "enabled": True},
            {"id": 105, "name": "虚无吞炎", "rarity": 5, "kind": "PASSIVE", "multiplier": 0.9,
             "lore": "吞纳万物。", "fragments": 0, "cost": 10, "unlocked": False, "slot": None, "enabled": True},
        ],
    }

    def test_collection_uses_compact_cards_and_only_renders_requested_page(self):
        content = render_collection(self.COLLECTION_DATA, page=2)["content"]

        self.assertIn("收集进度：**2/5** 已点亮｜第 **2/2** 页", content)
        self.assertIn("**#105｜虚无吞炎**｜★★★★★", content)
        self.assertIn("碎片 0/10", content)
        self.assertNotIn("#101｜帝炎", content)
        self.assertIn("text='专属图鉴 1'", content)
        self.assertIn("text='专属图鉴 2'", content)

    def test_collection_marks_equipped_slot_and_clamps_invalid_page(self):
        first_page = render_collection(self.COLLECTION_DATA, page=0)["content"]
        last_page = render_collection(self.COLLECTION_DATA, page=999)["content"]

        self.assertIn("装备：主动槽", first_page)
        self.assertIn("装备：被动槽", first_page)
        self.assertIn("第 **2/2** 页", last_page)


class RoleSpecialCollectionRouteTests(unittest.TestCase):
    def test_collection_page_command_is_parsed(self):
        self.assertEqual(("专属图鉴", "2"), asyncio.run(jiance("专属图鉴 2")))

    def test_collection_route_passes_page_suffix_to_handler(self):
        with patch("output_main.openid_to_uid", new=AsyncMock(return_value=1)), \
             patch("output_main.role_special_collection", new=AsyncMock(return_value="ok")) as handler:
            result = asyncio.run(output_main.content("专属图鉴", "2", "openid"))

        self.assertEqual("ok", result)
        handler.assert_awaited_once_with(1, "2")


if __name__ == "__main__":
    unittest.main()
