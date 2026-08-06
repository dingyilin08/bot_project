from pathlib import Path
import unittest

from Game_main.g31_invitation import (
    INVITE_CODE_LENGTH,
    ONBOARDING_REWARD,
    REGISTER_REWARD,
    generate_invite_code,
    normalize_invite_code,
    parse_registration_input,
)
from Game_main.g0_menu import show_activity_menu, show_update_log
from Game_main.g31_invitation import invitation_menu
from output_main import jiance


class InvitationRuleTests(unittest.IsolatedAsyncioTestCase):
    def test_invite_code_has_eight_uppercase_letters(self):
        code = generate_invite_code()
        self.assertEqual(len(code), INVITE_CODE_LENGTH)
        self.assertRegex(code, r"^[A-Z]{8}$")
        self.assertEqual(normalize_invite_code("abcdefgh"), "ABCDEFGH")
        with self.assertRaises(ValueError):
            normalize_invite_code("ABC12345")

    def test_registration_accepts_optional_invite_code(self):
        self.assertEqual(parse_registration_input("云澈"), ("云澈", None))
        self.assertEqual(parse_registration_input("云澈 ABCDEFGH"), ("云澈", "ABCDEFGH"))
        self.assertEqual(parse_registration_input("云澈-abcdefgh"), ("云澈", "ABCDEFGH"))
        with self.assertRaises(ValueError):
            parse_registration_input("云澈 ABC")

    async def test_invitation_commands_and_registration_keep_arguments(self):
        for command in ("邀请菜单", "我的邀请码", "邀请列表", "领取邀请奖励"):
            self.assertEqual(await jiance(command), (command, ""))
        self.assertEqual(
            await jiance("注册游戏 云澈 ABCDEFGH"),
            ("注册游戏", "云澈 ABCDEFGH"),
        )

    async def test_activity_and_update_log_expose_invitation(self):
        activity = (await show_activity_menu.__wrapped__(1, ""))["content"]
        self.assertIn("邀请菜单", activity)
        invitation = (await invitation_menu.__wrapped__(1, ""))["content"]
        for command in ("我的邀请码", "邀请列表", "领取邀请奖励"):
            self.assertIn(command, invitation)
        update_log = (await show_update_log(1))["content"]
        self.assertIn("v1.25", update_log)
        self.assertIn("道友邀请开放", update_log)

    def test_schema_enforces_unique_codes_and_reward_once(self):
        root = Path(__file__).resolve().parents[1]
        schema = (root / "数据库源文件" / "p2_invitation.sql").read_text(encoding="utf-8")
        self.assertIn("UNIQUE KEY uk_invitation_code", schema)
        self.assertIn("UNIQUE KEY uk_invitation_reward", schema)
        self.assertIn("reward_eligible", schema)
        self.assertEqual(REGISTER_REWARD, {"lingshi": 1600, "xianyu": 500})
        self.assertEqual(ONBOARDING_REWARD, {"lingshi": 0, "xianyu": 1000})
