# -*- coding: utf-8 -*-
import unittest

from Game_domain.player_text import (
    format_effect_codes,
    format_reward_map,
    format_unlock_effects,
    player_resource_name,
    sanitize_player_content,
)
from Game_main.g33_spirit_beast_v2 import dispatch_reward_text
from Game_main.g22_role_special import render_combo_bag


class PlayerTextTests(unittest.TestCase):
    def test_spirit_beast_rewards_use_player_facing_names(self):
        text = format_reward_map({
            "soul_fragment": 1,
            "beast_material": 5,
            "spirit_essence": 40,
        })
        self.assertEqual(text, "兽魂碎片+1、基础兽材+5、御兽灵息+40")
        self.assertNotIn("soul_fragment", text)
        self.assertNotIn("beast_material", text)
        self.assertNotIn("spirit_essence", text)

    def test_unknown_internal_reward_key_is_never_echoed(self):
        text = format_reward_map({"new_internal_reward": 3})
        self.assertEqual(text, "未命名奖励+3")
        self.assertNotIn("new_internal_reward", text)
        self.assertEqual(player_resource_name("new_internal_reward"), "未命名奖励")

    def test_dispatch_display_matches_actual_herb_conversion(self):
        text = dispatch_reward_text({
            "spirit_essence": 40,
            "herb_token": 5,
            "beast_material": 5,
        })
        self.assertEqual(text, "御兽灵息+50、基础兽材+5")
        self.assertNotIn("herb_token", text)

    def test_output_safety_net_replaces_known_and_unknown_reward_keys(self):
        text = sanitize_player_content(
            "获得：soul_fragment+1、future_reward_key+2、beast_material+5"
        )
        self.assertEqual(text, "获得：兽魂碎片+1、未命名奖励+2、基础兽材+5")
        self.assertNotIn("future_reward_key", text)

    def test_effect_and_growth_codes_use_gameplay_descriptions(self):
        self.assertEqual(
            format_effect_codes(["COMBO_ACTIVE_STRIKE", "COMBO_BURN"]),
            "专属一击、灼烧",
        )
        self.assertEqual(
            format_unlock_effects({"sword_count": 72, "passive_slots": 2}),
            "凝成72口飞剑、扩展被动槽",
        )
        text = sanitize_player_content("规则：COMBO_UNKNOWN_EFFECT")
        self.assertEqual(text, "规则：未命名效果")

    def test_combo_bag_never_displays_effect_codes(self):
        content = render_combo_bag({
            "role_name": "萧炎",
            "items": [{
                "id": 1,
                "name": "焚天三合",
                "combo_type": "异火连携",
                "multiplier": 1.2,
                "equipped": False,
                "effect": {"mode": "ACTIVE_OVERRIDE", "effect_codes": [
                    "COMBO_ACTIVE_STRIKE", "COMBO_BURN",
                ]},
            }],
        })["content"]
        self.assertIn("效果：专属一击、灼烧", content)
        self.assertNotIn("COMBO_", content)


if __name__ == "__main__":
    unittest.main()
