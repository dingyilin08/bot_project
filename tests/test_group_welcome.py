# -*- coding: utf-8 -*-
import json
import unittest

from Tool.qq_group_welcome import (
    REGISTER_COMMAND_PREFIX,
    build_group_welcome_message,
)


class GroupWelcomeMessageTests(unittest.TestCase):
    def setUp(self):
        self.result = build_group_welcome_message()

    def test_intro_covers_current_game_and_onboarding(self):
        content = self.result["content"]
        self.assertIn("问道诸天", content)
        for role_name in ("萧炎", "王林", "韩立", "石昊", "叶凡", "孟川"):
            self.assertIn(role_name, content)
        for feature in (
            "修炼", "养成", "副本", "战斗", "药园", "炼丹", "灵兽", "洞府",
            "组队", "宗门", "世界 Boss", "赛季",
        ):
            self.assertIn(feature, content)

        self.assertIn("1-8 字昵称", content)
        self.assertIn("注册游戏 云澈", content)
        self.assertIn("选择角色", content)

    def test_builder_returns_final_network_payload(self):
        self.assertEqual("markdown_keyboard", self.result["type"])
        self.assertIsInstance(self.result["content"], str)
        self.assertNotIn("keyboard_commands", self.result)
        self.assertIsInstance(self.result["keyboard"], dict)
        # 网络层可直接 JSON 序列化，不含 SDK 对象或协程。
        encoded = json.dumps(self.result, ensure_ascii=False)
        self.assertIn("注册游戏", encoded)

    def test_registration_button_uses_group_command_action(self):
        rows = self.result["keyboard"]["content"]["rows"]
        self.assertEqual(1, len(rows))
        self.assertEqual(1, len(rows[0]["buttons"]))

        button = rows[0]["buttons"][0]
        self.assertEqual("注册游戏", button["render_data"]["label"])
        self.assertEqual("注册游戏", button["render_data"]["visited_label"])

        action = button["action"]
        self.assertEqual(2, action["type"])
        self.assertEqual({"type": 2}, action["permission"])
        self.assertEqual(REGISTER_COMMAND_PREFIX, action["data"])
        self.assertEqual("注册游戏 云澈", f'{action["data"]} 云澈')
        self.assertIs(False, action["enter"])
        self.assertIs(False, action["reply"])

    def test_each_call_returns_an_independent_keyboard(self):
        self.result["keyboard"]["content"]["rows"][0]["buttons"][0]["action"]["data"] = "changed"
        fresh = build_group_welcome_message()
        action = fresh["keyboard"]["content"]["rows"][0]["buttons"][0]["action"]
        self.assertEqual(REGISTER_COMMAND_PREFIX, action["data"])


if __name__ == "__main__":
    unittest.main()
