# -*- coding: utf-8 -*-
import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from Game_domain.web_auth_service import (
    ADMIN_SCOPE,
    PLAYER_SCOPE,
    SessionIdentity,
    WebAuthError,
    digest_secret,
    exchange_link_code,
    normalize_link_code,
    verify_csrf,
)
from Game_web.presentation import adapt_game_response, dispatch_web_command
from Game_web.routes import ADMIN_SESSION_COOKIE, PLAYER_SESSION_COOKIE
from Game_main import g24_gm
from output_main import jiance


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _ExchangeCursor:
    def __init__(self, link_row=(91,)):
        self.link_row = link_row
        self.calls = []
        self.rowcount = 0

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        self.calls.append((statement, params))
        self.rowcount = 1 if statement.startswith("UPDATE web_link_code") else 0

    async def fetchone(self):
        if self.calls[-1][0].startswith("SELECT id FROM web_link_code"):
            return self.link_row
        return None


class _Connection:
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


class WebAuthTests(unittest.TestCase):
    SECRET = "test-web-auth-secret-that-is-at-least-32-bytes"

    def test_link_code_normalization_and_digest(self):
        self.assertEqual("ABCD234567", normalize_link_code("abcd-234 567"))
        self.assertNotEqual("ABCD234567", digest_secret("ABCD234567", secret=self.SECRET))
        self.assertNotEqual(
            digest_secret("ABCD234567", secret=self.SECRET),
            digest_secret("ABCD234567", secret=self.SECRET + "x"),
        )
        with self.assertRaises(WebAuthError):
            normalize_link_code("O0-I1")

    def test_csrf_is_bound_to_session(self):
        csrf = "csrf-token"
        identity = SessionIdentity(
            uid=10001,
            player_name="道友",
            scope=PLAYER_SCOPE,
            csrf_hash=digest_secret(csrf, secret=self.SECRET),
        )
        with patch.dict(os.environ, {"WEB_AUTH_SECRET": self.SECRET}):
            verify_csrf(identity, csrf)
            with self.assertRaises(WebAuthError):
                verify_csrf(identity, "wrong")

    def test_exchange_consumes_code_and_stores_only_hashes(self):
        cursor = _ExchangeCursor()
        connection = _Connection(cursor)
        with patch.dict(os.environ, {"WEB_AUTH_SECRET": self.SECRET}), patch(
            "Game_domain.web_auth_service.connect_mysql", return_value=connection
        ):
            credentials = asyncio.run(
                exchange_link_code(10001, "ABCD-234567", PLAYER_SCOPE)
            )

        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertEqual(10001, credentials.uid)
        statements = [sql for sql, _ in cursor.calls]
        self.assertTrue(any(sql.startswith("INSERT INTO web_session") for sql in statements))
        self.assertTrue(any(sql.startswith("UPDATE web_link_code") for sql in statements))
        all_params = repr([params for _, params in cursor.calls])
        self.assertNotIn("ABCD234567", all_params)
        self.assertNotIn(credentials.token, all_params)
        self.assertNotIn(credentials.csrf_token, all_params)

    def test_admin_exchange_rechecks_permanent_admin(self):
        with patch.dict(os.environ, {"WEB_AUTH_SECRET": self.SECRET}), patch(
            "Game_domain.web_auth_service.is_admin", return_value=False
        ):
            with self.assertRaisesRegex(WebAuthError, "管理员权限无效"):
                asyncio.run(exchange_link_code(10001, "ABCD234567", ADMIN_SCOPE))


class WebPresentationTests(unittest.TestCase):
    def test_qq_command_tags_become_deduplicated_web_actions(self):
        result = adapt_game_response({
            "type": "markdown",
            "content": (
                "##### 今日修行\n\n"
                "<qqbot-cmd-input text='签到' show='每日签到' /> | "
                "<qqbot-cmd-input text='签到' show='每日签到' />"
            ),
        })
        self.assertNotIn("qqbot-cmd", result["content"])
        self.assertIn("每日签到", result["content"])
        self.assertEqual([{"label": "每日签到", "command": "签到"}], result["actions"])

    def test_player_web_blocks_gm_commands_before_identity_lookup(self):
        with self.assertRaisesRegex(ValueError, "不能执行管理指令"):
            asyncio.run(dispatch_web_command(10001, "GM发放仙玉 10002-10"))

    def test_qq_binding_commands_are_registered(self):
        self.assertEqual(("网页绑定", ""), asyncio.run(jiance("网页绑定")))
        self.assertEqual(("GM网页绑定", ""), asyncio.run(jiance("GM网页绑定")))

    def test_gm_menu_exposes_isolated_web_admin_link(self):
        with patch.object(g24_gm, "is_admin", return_value=True), patch.object(
            g24_gm, "is_image_mode", return_value=False
        ):
            result = asyncio.run(g24_gm.gm_menu.__wrapped__(10001, ""))
        self.assertIn("GM网页绑定", result["content"])
        commands = [
            entry["command"] if isinstance(entry, dict) else entry[0]
            for entry in result["keyboard_commands"]
        ]
        self.assertIn("GM网页绑定", commands)


class WebPortalStructureTests(unittest.TestCase):
    def test_routes_and_isolated_cookie_names_exist(self):
        paths = {route.path for route in main.app.routes if hasattr(route, "path")}
        self.assertTrue({
            "/play",
            "/admin",
            "/api/web/auth/link",
            "/api/web/command",
            "/api/admin/auth/link",
            "/api/admin/grants/item",
            "/api/admin/grants/xianyu",
        }.issubset(paths))
        self.assertNotEqual(PLAYER_SESSION_COOKIE, ADMIN_SESSION_COOKIE)

    def test_migration_and_player_ui_cover_security_and_clear_actions(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "数据库源文件" / "p15_web_portal.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS web_link_code", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS web_session", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS web_admin_audit", migration)
        self.assertIn("UNIQUE KEY uk_web_session_hash", migration)
        player_html = (root / "web_static" / "play.html").read_text(encoding="utf-8")
        for label in ("今日修行", "角色道体", "秘境战斗", "药园丹炉", "诸天灵契"):
            self.assertIn(label, player_html)


if __name__ == "__main__":
    unittest.main()
