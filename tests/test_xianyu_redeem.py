import unittest
from pathlib import Path

import output_main
from Game_domain.xianyu_redeem_service import (
    XIANYU_REDEEM_TIERS,
    XianyuRedeemError,
    display_redeem_code,
    generate_redeem_code,
    normalize_redeem_code,
    parse_generate_request,
)
from Game_main import g0_menu
from Game_main import g24_gm
from output_main import jiance


class XianyuRedeemRuleTests(unittest.TestCase):
    def test_supported_tiers_match_design(self):
        self.assertEqual(XIANYU_REDEEM_TIERS, (600, 1800, 3000, 6800, 15000))

    def test_code_generation_and_normalization(self):
        codes = {generate_redeem_code() for _ in range(100)}
        self.assertEqual(len(codes), 100)
        for code in codes:
            self.assertRegex(code, r"^XY[A-HJ-NP-Z2-9]{12}$")
            displayed = display_redeem_code(code)
            self.assertRegex(displayed, r"^XY-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$")
            self.assertEqual(normalize_redeem_code(displayed.lower()), code)

    def test_generate_request_only_accepts_fixed_tiers_and_safe_batch_size(self):
        self.assertEqual(parse_generate_request("600 5"), (600, 5))
        self.assertEqual(parse_generate_request("15000-20"), (15000, 20))
        for value in ("500 1", "600 0", "600 21", "600"):
            with self.assertRaises(XianyuRedeemError):
                parse_generate_request(value)

    def test_invalid_player_code_is_rejected(self):
        for value in ("", "XY-1234", "NOT-A-REDEEM-CODE", "XY-ABCI-EFGH-JKLM"):
            with self.assertRaises(XianyuRedeemError):
                normalize_redeem_code(value)

    def test_migration_defines_unique_code_and_redemption_log(self):
        sql_path = Path(__file__).parents[1] / "数据库源文件" / "p11_xianyu_redeem.sql"
        sql = sql_path.read_text(encoding="utf-8")
        self.assertIn("xianyu_redeem_code", sql)
        self.assertIn("user_xianyu_redeem_log", sql)
        self.assertIn("UNIQUE KEY uk_xianyu_redeem_code", sql)
        self.assertIn("UNIQUE KEY uk_xianyu_redeem_log_code", sql)


class XianyuRedeemCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_parser_accepts_space_plus_and_admin_generation(self):
        code = "XY-ABCD-EFGH-JKLM"
        self.assertEqual(await jiance(f"兑换 {code}"), ("兑换", code))
        self.assertEqual(await jiance(f"兑换+{code}"), ("兑换", code))
        self.assertEqual(
            await jiance("GM生成兑换码 600 5"),
            ("GM生成兑换码", "600 5"),
        )

    async def test_player_command_routes_to_redeem_handler(self):
        original_uid = output_main.openid_to_uid
        original_redeem = output_main.redeem_xianyu
        calls = []

        async def fake_uid(_openid):
            return 10001

        async def fake_redeem(uid, code):
            calls.append((uid, code))
            return {"type": "markdown", "content": "ok"}

        output_main.openid_to_uid = fake_uid
        output_main.redeem_xianyu = fake_redeem
        try:
            result = await output_main.content(
                "兑换", "XY-ABCD-EFGH-JKLM", "openid"
            )
        finally:
            output_main.openid_to_uid = original_uid
            output_main.redeem_xianyu = original_redeem
        self.assertEqual(result["content"], "ok")
        self.assertEqual(calls, [(10001, "XY-ABCD-EFGH-JKLM")])

    async def test_activity_and_gm_menus_expose_entries(self):
        activity = (await g0_menu.show_activity_menu.__wrapped__(1, ""))["content"]
        self.assertIn("text='兑换 '", activity)

        original_admin = g24_gm.is_admin
        g24_gm.is_admin = lambda _uid: True
        try:
            gm_menu = (await g24_gm.gm_menu.__wrapped__(100007, ""))["content"]
        finally:
            g24_gm.is_admin = original_admin
        self.assertIn("text='GM生成兑换码 '", gm_menu)


if __name__ == "__main__":
    unittest.main()
