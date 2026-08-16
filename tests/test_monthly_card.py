import unittest
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import output_main
from Game_domain import monthly_card_service as monthly_service
from Game_domain.monthly_card_service import (
    MONTHLY_CARD_ACTIVATION_XIANYU,
    MONTHLY_CARD_DAILY_LINGSHI,
    MONTHLY_CARD_DAILY_XIANYU,
    MONTHLY_CARD_DAYS,
    MONTHLY_CARD_MAX_REMAINING_DAYS,
    MONTHLY_CARD_TITLE,
    MonthlyCardError,
    calculate_stacked_expiry,
    display_monthly_card_code,
    generate_monthly_card_code,
    monthly_card_display_name,
    monthly_card_login_message,
    normalize_monthly_card_code,
    parse_generate_count,
    remaining_days,
    record_monthly_card_player_activity,
    should_announce_monthly_card_login,
)
from Game_main import g0_menu, g24_gm
from output_main import jiance


class _ActivityCursor:
    def __init__(self, row):
        self.row = row
        self.result = None
        self.rowcount = 0
        self.executions = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, sql, params=()):
        statement = " ".join(sql.split())
        self.executions.append((statement, params))
        self.result = None
        self.rowcount = 1
        if statement.startswith("SELECT uz.id,uz.`name`"):
            self.result = self.row

    async def fetchone(self):
        return self.result


class _ActivityConnection:
    def __init__(self, row):
        self.cursor_instance = _ActivityCursor(row)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


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

    def test_monthly_title_and_login_copy_are_safe_and_exact(self):
        self.assertEqual(MONTHLY_CARD_TITLE, "月华玩家")
        self.assertEqual(monthly_card_display_name("凌霄"), "「月华玩家」凌霄")
        self.assertEqual(
            monthly_card_login_message("凌*霄[]"),
            "尊贵的月华玩家凌霄已上线！",
        )

    def test_login_announcement_requires_six_hours_offline_and_daily_limit(self):
        now = datetime(2026, 8, 16, 12, 0, 0)
        self.assertTrue(should_announce_monthly_card_login(now, None, None))
        self.assertFalse(
            should_announce_monthly_card_login(
                now, now - timedelta(hours=5, minutes=59), None
            )
        )
        self.assertTrue(
            should_announce_monthly_card_login(
                now, now - timedelta(hours=6), None
            )
        )
        self.assertFalse(
            should_announce_monthly_card_login(
                now,
                now - timedelta(hours=8),
                datetime(2026, 8, 16, 8, 0, 0),
            )
        )

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
        self.assertIn("user_monthly_card_presence", sql)
        self.assertIn("world_message_event_queue", sql)
        self.assertIn("UNIQUE KEY uk_monthly_card_code", sql)
        self.assertIn("UNIQUE KEY uk_monthly_card_activation_code", sql)
        self.assertIn("UNIQUE KEY uk_monthly_card_daily_claim (uid, claim_date)", sql)
        self.assertIn("UNIQUE KEY uk_world_message_event_key", sql)


class MonthlyCardCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_player_login_is_queued_once_and_cached(self):
        today = date(2026, 8, 16)
        now = datetime(2026, 8, 16, 12, 0, 0)
        connection = _ActivityConnection(
            (10001, "凌霄", date(2026, 9, 1), None, None, today, now)
        )

        @asynccontextmanager
        async def fake_connect_mysql():
            yield connection

        old_ready = monthly_service._MONTHLY_CARD_SCHEMA_READY
        monthly_service._MONTHLY_CARD_SCHEMA_READY = True
        monthly_service._presence_check_cache.clear()
        try:
            with patch.object(monthly_service, "connect_mysql", fake_connect_mysql):
                first = await record_monthly_card_player_activity("openid-1")
                second = await record_monthly_card_player_activity("openid-1")
        finally:
            monthly_service._MONTHLY_CARD_SCHEMA_READY = old_ready
            monthly_service._presence_check_cache.clear()

        self.assertEqual("尊贵的月华玩家凌霄已上线！", first)
        self.assertIsNone(second)
        self.assertEqual(1, connection.commits)
        statements = [sql for sql, _ in connection.cursor_instance.executions]
        self.assertTrue(any("INSERT INTO user_monthly_card_presence" in sql for sql in statements))
        self.assertTrue(any("INSERT IGNORE INTO world_message_event_queue" in sql for sql in statements))

    async def test_active_member_title_is_shown_in_main_menu(self):
        original_player = g0_menu.get_player_basic_info
        original_role = g0_menu.get_current_role_info

        async def fake_player(_uid):
            return {
                "name": "凌霄",
                "lingshi": 100,
                "xianyu": 200,
                "monthly_card_active": True,
            }

        async def fake_role(_uid):
            return None

        g0_menu.get_player_basic_info = fake_player
        g0_menu.get_current_role_info = fake_role
        try:
            content = (await g0_menu.show_main_menu.__wrapped__(1, ""))["content"]
        finally:
            g0_menu.get_player_basic_info = original_player
            g0_menu.get_current_role_info = original_role

        self.assertIn("**玩家：** 「月华玩家」凌霄", content)

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
