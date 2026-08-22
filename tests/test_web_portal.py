# -*- coding: utf-8 -*-
import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from fastapi import HTTPException
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
from Game_web.routes import ADMIN_SESSION_COOKIE, PLAYER_SESSION_COOKIE, player_page
from Game_web.portal_service import (
    list_player_dungeons,
    list_player_inventory,
    list_player_roles,
)
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


class _PortalCursor:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    async def fetchone(self):
        return (2,)

    async def fetchall(self):
        statement = self.calls[-1][0]
        if "FROM user_role" in statement:
            return [(10001, "韩立", 12, 345, "结丹境", "凡人修仙传", 1, 900, 800, 4800, 400, 108)]
        return [
            (2, "赤焰砂", 2, "火焰结晶", "挑战副本", 5),
            (34, "吸掌卷轴", 3, "技能卷轴", "挑战副本", 1),
        ]


class _DungeonPortalCursor:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    async def fetchone(self):
        statement = self.calls[-1][0]
        if statement.startswith("SELECT dungeon_num FROM user_zt"):
            return (7,)
        if statement.startswith("SELECT id,`name`,dengji,world FROM user_role"):
            return (88, "韩立", 22, "凡人修仙传")
        if statement.startswith("SELECT udp.dungeon_id"):
            return (
                23,
                "乱星海海域",
                2,
                3,
                '[{"index":1,"name":"海妖","type":"normal","description":"逐浪而来","defeated":false}]',
                0,
                0.75,
                2,
                6,
            )
        if statement.startswith("SELECT 1 FROM battle_session"):
            return (1,)
        if statement.startswith("SELECT COUNT(*) FROM data_dungeon"):
            return (2,)
        return None

    async def fetchall(self):
        return [
            (23, "乱星海海域", "凡人修仙传", 20, "结丹", "出海除妖", 500, 200, 1),
            (3, "塔戈尔沙漠", "斗破苍穹", 20, "大斗师", "沙海异火", 500, 200, 0),
        ]


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

    def test_keyboard_commands_supply_fixed_battle_actions(self):
        result = adapt_game_response({
            "type": "markdown",
            "content": "##### 回合战斗",
            "keyboard_commands": [
                {"command": "战斗行动 普攻", "label": "普通攻击", "style": 1},
                ("战斗行动 防御", "防御"),
            ],
        })
        self.assertEqual(
            [
                {"label": "普通攻击", "command": "战斗行动 普攻"},
                {"label": "防御", "command": "战斗行动 防御"},
            ],
            result["actions"],
        )

    def test_parameterized_action_keeps_input_requirement(self):
        result = adapt_game_response({
            "type": "markdown",
            "content": "<qqbot-cmd-input text='选择角色 ' show='选择角色*' />",
        })
        self.assertEqual(
            [{"label": "选择角色", "command": "选择角色", "requires_input": True}],
            result["actions"],
        )

    def test_player_web_blocks_gm_commands_before_identity_lookup(self):
        with self.assertRaisesRegex(ValueError, "不能执行管理指令"):
            asyncio.run(dispatch_web_command(10001, "GM发放仙玉 10002-10"))

    def test_player_binding_command_follows_feature_switch(self):
        with patch.dict(os.environ, {"WEB_PLAYER_PORTAL_ENABLED": "false"}):
            self.assertEqual(("", ""), asyncio.run(jiance("网页绑定")))
        with patch.dict(os.environ, {"WEB_PLAYER_PORTAL_ENABLED": "true"}):
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


class WebPortalServiceTests(unittest.TestCase):
    def test_structured_roles_and_inventory_are_scoped_to_uid(self):
        cursor = _PortalCursor()
        connection = _Connection(cursor)
        with patch("Game_web.portal_service.connect_mysql", return_value=connection):
            roles = asyncio.run(list_player_roles(10001))
            inventory = asyncio.run(list_player_inventory(10001, page=1, page_size=40))

        self.assertEqual("韩立", roles[0]["name"])
        self.assertTrue(roles[0]["active"])
        self.assertEqual(2, inventory["total"])
        self.assertEqual("赤焰砂", inventory["items"][0]["name"])
        uid_params = [params for sql, params in cursor.calls if "uid=%s" in sql]
        self.assertTrue(uid_params)
        self.assertTrue(all(params[0] == 10001 for params in uid_params))

    def test_structured_dungeons_include_progress_and_cross_world_state(self):
        cursor = _DungeonPortalCursor()
        connection = _Connection(cursor)
        with patch("Game_web.portal_service.connect_mysql", return_value=connection):
            data = asyncio.run(list_player_dungeons(10001, page=1, page_size=12))

        self.assertEqual(7, data["remaining_attempts"])
        self.assertTrue(data["battle_active"])
        self.assertEqual("海妖", data["active_progress"]["monsters"][0]["name"])
        self.assertEqual(75, data["active_progress"]["player_hp_percent"])
        self.assertFalse(data["dungeons"][0]["cross_world"])
        self.assertTrue(data["dungeons"][1]["cross_world"])
        uid_scoped = [params for sql, params in cursor.calls if "uid=%s" in sql or "id=%s" in sql]
        self.assertTrue(uid_scoped)
        self.assertTrue(all(params[0] == 10001 for params in uid_scoped))


class WebPortalStructureTests(unittest.TestCase):
    def test_disabled_player_portal_returns_not_found(self):
        with patch.dict(os.environ, {"WEB_PLAYER_PORTAL_ENABLED": "false"}):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(player_page())
        self.assertEqual(404, raised.exception.status_code)

    def test_routes_and_isolated_cookie_names_exist(self):
        paths = {route.path for route in main.app.routes if hasattr(route, "path")}
        self.assertTrue({
            "/play",
            "/admin",
            "/api/web/auth/link",
            "/api/web/command",
            "/api/web/roles",
            "/api/web/inventory",
            "/api/web/dungeons",
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
