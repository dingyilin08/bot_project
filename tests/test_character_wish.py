# -*- coding: utf-8 -*-
import asyncio
import unittest
from pathlib import Path

from Game_domain.character_wish_service import (
    WISH_EXP_DIVISOR, _ledger_source_id, choose_by_rarity, choose_main_reward,
)
from Game_main.g16_onboarding import ONBOARDING_ALL_XIANYU, ONBOARDING_XIANYU_PER_TASK, TASKS
from Game_main.g23_character_wish import render_home
from Tool.qq_keyboard import attach_keyboard
from output_main import jiance


class FixedRandom:
    def __init__(self, rolls):
        self.rolls = iter(rolls)

    def randint(self, start, end):
        value = next(self.rolls)
        assert start <= value <= end
        return value

    def choice(self, values):
        return values[0]


class CharacterWishRuleTests(unittest.TestCase):
    def test_each_draw_grants_one_fifteenth_of_required_experience(self):
        self.assertEqual(15, WISH_EXP_DIVISOR)

    def test_long_request_id_is_safe_for_reward_ledger_source_id(self):
        source_id = _ledger_source_id("x" * 200)
        self.assertLessEqual(len(source_id), 64)
        self.assertEqual(source_id, _ledger_source_id("x" * 200))

    RATES = {"herb": 3000, "pill": 3000, "special4": 2500,
             "special5": 1000, "role_fragment": 500}

    def test_normal_pool_probability_boundaries(self):
        expected = ((1, "HERB"), (3001, "PILL"), (6001, "SPECIAL_4"),
                    (8501, "SPECIAL_5"), (9501, "ROLE_FRAGMENT"))
        for roll, reward_type in expected:
            self.assertEqual(reward_type, choose_main_reward(FixedRandom([roll]), self.RATES))

    def test_full_roster_removes_character_fragment_and_normalizes(self):
        self.assertEqual("SPECIAL_5", choose_main_reward(FixedRandom([9500]), self.RATES, full_roster=True))

    def test_item_selection_uses_rarity_before_equal_item_choice(self):
        rows = [(11, "凡草甲", 1), (12, "凡草乙", 1), (99, "仙草", 4)]
        chosen = choose_by_rarity(FixedRandom([101]), rows, {1: 100, 4: 5})
        self.assertEqual((99, "仙草", 4), chosen)

    def test_onboarding_xianyu_total_is_2020(self):
        self.assertEqual(60, ONBOARDING_XIANYU_PER_TASK)
        self.assertEqual(1600, ONBOARDING_ALL_XIANYU)
        self.assertEqual(2020, len(TASKS) * ONBOARDING_XIANYU_PER_TASK + ONBOARDING_ALL_XIANYU)

    def test_wish_commands_are_parsed(self):
        self.assertEqual(("仙玉祈愿", ""), asyncio.run(jiance("仙玉祈愿")))
        self.assertEqual(("仙玉祈愿", "10次"), asyncio.run(jiance("仙玉祈愿 10次")))
        self.assertEqual(("祈愿定向", "王林"), asyncio.run(jiance("祈愿定向 王林")))
        self.assertEqual(("合成角色", "王林"), asyncio.run(jiance("合成角色 王林")))

    def test_home_declares_real_message_buttons(self):
        data = {
            "pool": {"name": "诸天角色祈愿", "single_cost": 160, "ten_cost": 1500,
                     "pity_limit": 80},
            "pity": {"pity": 7, "full_type": None}, "xianyu": 1600,
            "role": {"name": "萧炎", "level": 1}, "owned": 1, "roster_total": 6,
            "full_roster": False, "target_name": "王林", "unowned_roles": ["王林"],
            "owned_roles": ["萧炎"], "full_role_name": None,
        }
        result = attach_keyboard(render_home(data), is_group=False)
        self.assertEqual("markdown_keyboard", result["type"])
        buttons = [button for row in result["keyboard"]["content"]["rows"] for button in row["buttons"]]
        self.assertEqual("仙玉祈愿 1次", buttons[0]["action"]["data"])
        self.assertTrue(buttons[0]["action"]["enter"])

    def test_migration_contains_idempotent_pool_seed_and_all_tables(self):
        sql = (Path(__file__).resolve().parents[1] / "数据库源文件" / "p1_character_wish.sql").read_text(encoding="utf-8")
        for table in ("character_wish_pool", "character_wish_order", "character_wish_result",
                      "character_wish_pity", "user_character_fragment", "character_compose_order",
                      "user_onboarding_bonus"):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
        self.assertIn("ON DUPLICATE KEY UPDATE", sql)


if __name__ == "__main__":
    unittest.main()
