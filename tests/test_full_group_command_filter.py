import unittest
from unittest.mock import patch

import output_main


class FullGroupCommandFilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_chat_and_empty_messages_are_ignored(self):
        self.assertFalse(await output_main.should_reply_to_full_group_message("大家晚上好"))
        self.assertFalse(await output_main.should_reply_to_full_group_message("  "))

    async def test_exact_and_parameterized_game_commands_are_routed(self):
        self.assertTrue(await output_main.should_reply_to_full_group_message("菜单"))
        self.assertTrue(await output_main.should_reply_to_full_group_message("挑战副本 1"))
        self.assertTrue(await output_main.should_reply_to_full_group_message("购买商品 灵草培育液"))

    async def test_pending_admin_verification_is_routed(self):
        with patch.dict(
            output_main.img_mode_pwd_pending,
            {"member-openid-1": {"uid": 100001, "action": "auth"}},
            clear=True,
        ):
            self.assertTrue(
                await output_main.should_reply_to_full_group_message(
                    "temporary-secret", "member-openid-1"
                )
            )


if __name__ == "__main__":
    unittest.main()
