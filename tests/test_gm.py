# -*- coding: utf-8 -*-
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from Game_domain import gm_state
from Game_domain.gm_service import (
    GMError,
    authenticate_admin,
    grant_all_currency,
    parse_global_grant,
    parse_item_grant,
    parse_xianyu_grant,
)
from Game_main import g24_gm
import output_main
from output_main import jiance, redact_sensitive_content
from Tool.qq_keyboard import attach_keyboard


class _GlobalGrantCursor:
    def __init__(self, *, existing=None, player_count=2):
        self.existing = existing
        self.player_count = player_count
        self.rowcount = 0
        self.calls = []

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        self.calls.append((statement, params))
        if statement.startswith("UPDATE user_zt SET"):
            self.rowcount = self.player_count

    async def fetchone(self):
        statement = self.calls[-1][0]
        if "FROM gm_operation_log" in statement:
            return self.existing
        if statement.startswith("SELECT COUNT(*) FROM user_zt"):
            return (self.player_count,)
        return None


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _GlobalGrantConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return _CursorContext(self.cursor_instance)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class GMStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = gm_state.STATE_PATH
        gm_state.STATE_PATH = Path(self.temp_dir.name) / "gm_state.yaml"

    def tearDown(self):
        gm_state.STATE_PATH = self.original_path
        self.temp_dir.cleanup()

    def test_admin_and_image_mode_survive_yaml_reload(self):
        self.assertFalse(gm_state.is_admin(10001))
        self.assertTrue(gm_state.get_image_mode())
        self.assertTrue(gm_state.grant_admin(10001))
        self.assertTrue(gm_state.set_image_mode(False))
        data = yaml.safe_load(gm_state.STATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual([10001], data["admins"])
        self.assertFalse(data["image_mode_enabled"])
        self.assertTrue(gm_state.is_admin(10001))
        self.assertFalse(gm_state.get_image_mode())

    def test_correct_password_permanently_grants_admin(self):
        authenticate_admin(10002, "Secret42", "secret42")
        self.assertTrue(gm_state.is_admin(10002))
        with self.assertRaises(GMError):
            authenticate_admin(10003, "wrong", "secret42")
        self.assertFalse(gm_state.is_admin(10003))

    def test_empty_server_password_never_authenticates(self):
        with self.assertRaises(GMError):
            authenticate_admin(10001, "", "")

    def test_production_default_uses_shared_directory_not_release_directory(self):
        original_shared = gm_state.PRODUCTION_SHARED_LOG_DIR
        original_path = os.environ.pop("GM_STATE_FILE", None)
        try:
            gm_state.PRODUCTION_SHARED_LOG_DIR = Path(self.temp_dir.name)
            self.assertEqual(
                Path(self.temp_dir.name) / "gm_state.yaml",
                gm_state._default_state_path(),
            )
            os.environ["GM_STATE_FILE"] = "gm_state.yaml"
            self.assertEqual(
                Path(self.temp_dir.name) / "gm_state.yaml",
                gm_state._default_state_path(),
            )
        finally:
            gm_state.PRODUCTION_SHARED_LOG_DIR = original_shared
            if original_path is None:
                os.environ.pop("GM_STATE_FILE", None)
            else:
                os.environ["GM_STATE_FILE"] = original_path


class GMCommandTests(unittest.TestCase):
    def test_grant_parsers(self):
        self.assertEqual((10086, "九转丹", 5), parse_item_grant("10086-九转丹-5"))
        self.assertEqual((10086, "12", 8), parse_item_grant("10086-12-8"))
        self.assertEqual((10086, 1600), parse_xianyu_grant("10086-1600"))
        self.assertEqual(500, parse_global_grant("500", "GM全服发放灵石"))
        with self.assertRaises(GMError):
            parse_item_grant("10086-九转丹-0")
        with self.assertRaises(GMError):
            parse_xianyu_grant("10086--1")
        with self.assertRaises(GMError):
            parse_global_grant("0", "GM全服发放灵石")

    def test_commands_are_registered(self):
        self.assertEqual(("GM菜单", ""), asyncio.run(jiance("GM菜单")))
        self.assertEqual(("GM验证", "密令"), asyncio.run(jiance("GM验证 密令")))
        self.assertEqual(("GM发放物品", "10086-九转丹-5"),
                         asyncio.run(jiance("GM发放物品 10086-九转丹-5")))
        self.assertEqual(("GM发放仙玉", "10086-1600"),
                         asyncio.run(jiance("GM发放仙玉 10086-1600")))
        self.assertEqual(("GM全服发放灵石", "500"),
                         asyncio.run(jiance("GM全服发放灵石 500")))
        self.assertEqual(("GM全服发放仙玉", "1600"),
                         asyncio.run(jiance("GM全服发放仙玉 1600")))
        self.assertEqual(("GM世界消息", ""), asyncio.run(jiance("GM世界消息")))
        self.assertEqual(
            ("GM世界消息添加", "副本前，记得检查技能！"),
            asyncio.run(jiance("GM世界消息添加 副本前，记得检查技能！")),
        )

    def test_sensitive_commands_are_redacted_from_logs(self):
        original = output_main.ADMIN_PASSWORD
        output_main.ADMIN_PASSWORD = "Secret42"
        try:
            self.assertEqual("[GM密令已隐藏]", redact_sensitive_content("secret42"))
            self.assertEqual("GM验证 [密令已隐藏]", redact_sensitive_content("GM验证 secret42"))
            self.assertEqual("关闭图片模式 [密令已隐藏]", redact_sensitive_content("关闭图片模式 secret42"))
            self.assertEqual("GM发放仙玉 10086-60", redact_sensitive_content("GM发放仙玉 10086-60"))
        finally:
            output_main.ADMIN_PASSWORD = original

    def test_gm_menu_declares_real_message_buttons(self):
        original_admin = g24_gm.is_admin
        original_mode = g24_gm.is_image_mode
        g24_gm.is_admin = lambda uid: True
        g24_gm.is_image_mode = lambda: False
        try:
            result = asyncio.run(g24_gm.gm_menu.__wrapped__(10001, ""))
            result = attach_keyboard(result, is_group=False)
        finally:
            g24_gm.is_admin = original_admin
            g24_gm.is_image_mode = original_mode
        self.assertEqual("markdown_keyboard", result["type"])
        buttons = [button for row in result["keyboard"]["content"]["rows"] for button in row["buttons"]]
        self.assertEqual("GM发放物品", buttons[0]["action"]["data"])
        self.assertFalse(buttons[0]["action"]["enter"])
        commands = [button["action"]["data"] for button in buttons]
        self.assertIn("GM世界消息", commands)
        self.assertIn("GM全服发放灵石", commands)

    def test_global_grant_updates_every_player_and_audits_once(self):
        cursor = _GlobalGrantCursor(player_count=3)
        connection = _GlobalGrantConnection(cursor)
        with patch("Game_domain.gm_service.is_admin", return_value=True), patch(
            "Game_domain.gm_service.connect_mysql", return_value=connection
        ):
            result = asyncio.run(grant_all_currency(
                operator_uid=10001, currency="lingshi", amount=200, request_id="global-lingshi"
            ))

        self.assertTrue(connection.committed)
        self.assertEqual(3, result["recipient_count"])
        self.assertEqual(600, result["total_amount"])
        self.assertIn(
            ("UPDATE user_zt SET lingshi=lingshi+%s", (200,)),
            cursor.calls,
        )
        self.assertTrue(any("INSERT INTO reward_ledger" in sql for sql, _ in cursor.calls))
        self.assertTrue(any("INSERT INTO gm_operation_log" in sql for sql, _ in cursor.calls))

    def test_global_grant_reuses_existing_request_result(self):
        cached = {"operation": "GRANT_ALL_XIANYU", "recipient_count": 3}
        cursor = _GlobalGrantCursor(existing=("SUCCESS", json.dumps(cached)))
        connection = _GlobalGrantConnection(cursor)
        with patch("Game_domain.gm_service.is_admin", return_value=True), patch(
            "Game_domain.gm_service.connect_mysql", return_value=connection
        ):
            result = asyncio.run(grant_all_currency(
                operator_uid=10001, currency="xianyu", amount=200, request_id="global-xianyu"
            ))

        self.assertEqual(cached, result)
        self.assertFalse(any("UPDATE user_zt SET" in sql for sql, _ in cursor.calls))

    def test_migration_contains_audited_idempotent_operation_table(self):
        root = Path(__file__).resolve().parents[1]
        migration = next(root.rglob("p1_gm.sql")).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS gm_operation_log", migration)
        self.assertIn("UNIQUE KEY uk_gm_operation_request", migration)


if __name__ == "__main__":
    unittest.main()
