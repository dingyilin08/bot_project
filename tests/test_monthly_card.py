import unittest
from datetime import date
from pathlib import Path

import output_main
from Game_domain.monthly_card_service import (
    MONTHLY_CARD_ACTIVATION_XIANYU,
    MONTHLY_CARD_DAILY_LINGSHI,
    MONTHLY_CARD_DAILY_XIANYU,
    MONTHLY_CARD_DAYS,
    MONTHLY_CARD_MAX_REMAINING_DAYS,
    MonthlyCardError,
    calculate_stacked_expiry,
    display_monthly_card_code,
    generate_monthly_card_code,
    normalize_monthly_card_code,
    parse_generate_count,
    remaining_days,
)
from Game_main import g0_menu, g24_gm
from output_main import jiance


class MonthlyCardRuleTests(unittest.TestCase):
    def test_reward_budget_is_explicit(self):
        self.assertEqual(MONTHLY_CARD_DAYS, 30)
        self.assertEqual(MONTHLY_CARD_ACTIVATION_XIANYU, 600)
        self.assertEqual(MONTHLY_CARD_DAILY_XIANYU, 100)
        self.assertEqual(MONTHLY_CARD_DAILY_LINGSHI, 200)
        self.assertEqual(
            MONTHLY_CARD_ACTIVATION_XIANYU
            + MONTHLY_CARD_DAYS * MONTHLY_CARD_DAILY_XIANYU,
            3600,
        )
        self.assertEqual(MONTHLY_CARD_DAYS * MONTHLY_CARD_DAILY_LINGSHI, 6000)

    def test_code_generation_and_normalization(self):
        codes = {generate_monthly_card_code() for _ in range(100)}
        self.assertEqual(len(codes), 100)
        for code in codes:
            self.assertRegex(code, r"^MC[A-HJ-NP-Z2-9]{12}$")
            displayed = display_monthly_card_code(code)
            self.assertRegex(
                displayed,
                r"^MC-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$",
            )
            self.assertEqual(normalize_monthly_card_code(displayed.lower()), code)

    def test_invalid_codes_and_batch_sizes_are_rejected(self):
        for value in ("", "MC-1234", "MC-ABCI-EFGH-JKLM", "NOT-A-CARD"):
            with self.assertRaises(MonthlyCardError):
                normalize_monthly_card_code(value)
        self.assertEqual(parse_generate_count("1"), 1)
        self.assertEqual(parse_generate_count("20"), 20)
        for value in ("", "0", "21", "1 2", "abc"):
            with self.assertRaises(MonthlyCardError):
                parse_generate_count(value)

    def test_activation_day_counts_as_first_day_and_renewal_stacks(self):
        today = date(2026, 8, 16)
        first_expiry = calculate_stacked_expiry(today, None)
        self.assertEqual(first_expiry, date(2026, 9, 14))
        self.assertEqual(remaining_days(today, first_expiry), 30)

        renewed_expiry = calculate_stacked_expiry(today, first_expiry)
        self.assertEqual(renewed_expiry, date(2026, 10, 14))
        self.assertEqual(remaining_days(today, renewed_expiry), 60)

    def test_expired_card_restarts_today_and_stacking_cap_is_enforced(self):
        today = date(2026, 8, 16)
        self.assertEqual(
            calculate_stacked_expiry(today, date(2026, 8, 15)),
            date(2026, 9, 14),
        )
        max_expiry = calculate_stacked_expiry(
            today, None, MONTHLY_CARD_MAX_REMAINING_DAYS
        )
        self.assertEqual(remaining_days(today, max_expiry), 180)
        with self.assertRaisesRegex(MonthlyCardError, "最多累计180天"):
            calculate_stacked_expiry(today, max_expiry, 1)

    def test_migration_has_activation_and_daily_idempotency_keys(self):
        sql_path = Path(__file__).parents[1] / "数据库源文件" / "p13_monthly_card.sql"
        sql = sql_path.read_text(encoding="utf-8")
        self.assertIn("monthly_card_redeem_code", sql)
        self.assertIn("user_monthly_card", sql)
        self.assertIn("user_monthly_card_activation_log", sql)
        self.assertIn("user_monthly_card_claim_log", sql)
        self.assertIn("UNIQUE KEY uk_monthly_card_code", sql)
        self.assertIn("UNIQUE KEY uk_monthly_card_activation_code", sql)
        self.assertIn("UNIQUE KEY uk_monthly_card_daily_claim (uid, claim_date)", sql)


class MonthlyCardCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_parser_accepts_monthly_card_commands_and_preserves_codes(self):
        code = "MC-ABCD-EFGH-JKLM"
        self.assertEqual(await jiance("月卡"), ("月卡", ""))
        self.assertEqual(await jiance("领取月卡"), ("领取月卡", ""))
        self.assertEqual(await jiance(f"月卡兑换 {code}"), ("月卡兑换", code))
        self.assertEqual(await jiance(f"月卡兑换+{code}"), ("月卡兑换", code))
        self.assertEqual(
            await jiance("GM生成月卡码 5"),
            ("GM生成月卡码", "5"),
        )

    async def test_routes_call_the_expected_monthly_card_handlers(self):
        original_uid = output_main.openid_to_uid
        original_home = output_main.monthly_card_home
        original_claim = output_main.monthly_card_claim
        original_redeem = output_main.monthly_card_redeem
        original_gm_create = output_main.gm_create_monthly_card_codes
        calls = []

        async def fake_uid(_openid):
            return 10001

        async def fake_home(uid):
            calls.append(("home", uid))
            return {"type": "markdown", "content": "home"}

        async def fake_claim(uid):
            calls.append(("claim", uid))
            return {"type": "markdown", "content": "claim"}

        async def fake_redeem(uid, code):
            calls.append(("redeem", uid, code))
            return {"type": "markdown", "content": "redeem"}

        async def fake_gm_create(uid, count):
            calls.append(("gm", uid, count))
            return {"type": "markdown", "content": "gm"}

        output_main.openid_to_uid = fake_uid
        output_main.monthly_card_home = fake_home
        output_main.monthly_card_claim = fake_claim
        output_main.monthly_card_redeem = fake_redeem
        output_main.gm_create_monthly_card_codes = fake_gm_create
        try:
            await output_main.content("月卡", "", "openid")
            await output_main.content("领取月卡", "", "openid")
            await output_main.content("月卡兑换", "MC-ABCD-EFGH-JKLM", "openid")
            await output_main.content("GM生成月卡码", "5", "openid")
        finally:
            output_main.openid_to_uid = original_uid
            output_main.monthly_card_home = original_home
            output_main.monthly_card_claim = original_claim
            output_main.monthly_card_redeem = original_redeem
            output_main.gm_create_monthly_card_codes = original_gm_create

        self.assertEqual(calls, [
            ("home", 10001),
            ("claim", 10001),
            ("redeem", 10001, "MC-ABCD-EFGH-JKLM"),
            ("gm", 10001, "5"),
        ])

    async def test_activity_and_gm_menus_expose_monthly_card_entries(self):
        activity = (await g0_menu.show_activity_menu.__wrapped__(1, ""))["content"]
        self.assertIn("text='月卡'", activity)
        self.assertIn("text='领取月卡'", activity)

        original_admin = g24_gm.is_admin
        g24_gm.is_admin = lambda _uid: True
        try:
            gm_menu = (await g24_gm.gm_menu.__wrapped__(100007, ""))["content"]
        finally:
            g24_gm.is_admin = original_admin
        self.assertIn("text='GM生成月卡码 '", gm_menu)


if __name__ == "__main__":
    unittest.main()
