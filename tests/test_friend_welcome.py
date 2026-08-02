# -*- coding: utf-8 -*-
import unittest

from Tool.qq_group_welcome import (
    REGISTER_COMMAND_PREFIX,
    build_friend_welcome_message,
    build_group_welcome_message,
)
from Tool.qq_official_group import OFFICIAL_GROUP_NOTICE


class FriendWelcomeMessageTests(unittest.TestCase):
    @staticmethod
    def _registration_button(message):
        rows = message["keyboard"]["content"]["rows"]
        return rows[0]["buttons"][0]

    def test_group_and_friend_welcome_both_include_official_group(self):
        for builder in (build_group_welcome_message, build_friend_welcome_message):
            with self.subTest(builder=builder.__name__):
                content = builder()["content"]
                self.assertIn("官方群群号：760693073", content)
                self.assertTrue(content.rstrip().endswith(OFFICIAL_GROUP_NOTICE))

    def test_friend_copy_welcomes_player_and_explains_registration(self):
        content = build_friend_welcome_message()["content"]

        self.assertIn("欢迎添加《问道诸天》", content)
        self.assertIn("注册游戏", content)
        self.assertIn("1-8 字昵称", content)
        self.assertIn("注册游戏 云澈", content)
        self.assertIn("选择角色", content)

    def test_group_and_friend_registration_buttons_allow_everyone(self):
        for builder in (build_group_welcome_message, build_friend_welcome_message):
            with self.subTest(builder=builder.__name__):
                message = builder()
                self.assertEqual("markdown_keyboard", message["type"])
                self.assertNotIn("keyboard_commands", message)

                button = self._registration_button(message)
                self.assertEqual("注册游戏", button["render_data"]["label"])
                self.assertEqual(2, button["action"]["type"])
                self.assertEqual({"type": 2}, button["action"]["permission"])
                self.assertEqual(REGISTER_COMMAND_PREFIX, button["action"]["data"])

    def test_friend_registration_button_waits_for_player_name(self):
        action = self._registration_button(
            build_friend_welcome_message(),
        )["action"]

        # 好友场景本可直接发送；这里仍为 False，证明 complete=False 生效。
        self.assertIs(False, action["enter"])
        self.assertIs(False, action["reply"])
        self.assertEqual("注册游戏 云澈", f'{action["data"]} 云澈')

    def test_each_builder_call_returns_independent_data(self):
        for builder in (build_group_welcome_message, build_friend_welcome_message):
            with self.subTest(builder=builder.__name__):
                first = builder()
                second = builder()

                self.assertIsNot(first, second)
                self.assertIsNot(first["keyboard"], second["keyboard"])
                self._registration_button(first)["action"]["data"] = "已修改"
                first["content"] = "已修改"

                self.assertEqual(
                    REGISTER_COMMAND_PREFIX,
                    self._registration_button(second)["action"]["data"],
                )
                self.assertNotEqual("已修改", second["content"])


if __name__ == "__main__":
    unittest.main()
