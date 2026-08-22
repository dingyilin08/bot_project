# -*- coding: utf-8 -*-
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import output_main
from Game_domain import account_deletion_service
from Game_domain.account_deletion_service import (
    AccountDeletionError,
    allocate_player_uid,
    build_user_delete_statement,
    delete_player_account,
    validate_account_deletion_roles,
    was_openid_deleted,
)
from Game_main.g41_account_deletion import render_account_deletion_preview
from output_main import jiance


class AccountDeletionRuleTests(unittest.TestCase):
    def test_requires_selected_roles_and_all_roles_below_level_ten(self):
        with self.assertRaisesRegex(AccountDeletionError, "尚未选择角色"):
            validate_account_deletion_roles([])
        with self.assertRaisesRegex(AccountDeletionError, "最高角色已达到10级"):
            validate_account_deletion_roles([(1, "韩立", 9, 1), (2, "王林", 10, 0)])

        summary = validate_account_deletion_roles(
            [(1, "韩立", 9, 1), (2, "王林", 7, 0)]
        )
        self.assertEqual(2, summary["role_count"])
        self.assertEqual(9, summary["highest_role_level"])
        self.assertEqual("韩立", summary["active_role"]["name"])

    def test_dynamic_delete_sql_quotes_only_safe_schema_identifiers(self):
        sql, count = build_user_delete_statement("user_market_order", ("owner_uid", "uid"))
        self.assertEqual(
            "DELETE FROM `user_market_order` WHERE `owner_uid`=%s OR `uid`=%s",
            sql,
        )
        self.assertEqual(2, count)
        with self.assertRaises(RuntimeError):
            build_user_delete_statement("user_zt; DROP TABLE user_zt", ("uid",))

    def test_preview_copy_has_irreversible_confirmation(self):
        content = render_account_deletion_preview(
            {
                "uid": 100001,
                "player_name": "测试道友",
                "role_count": 1,
                "highest_role_level": 9,
            }
        )
        self.assertIn("永久删除账号", content)
        self.assertIn("删号 确认删除", content)
        self.assertIn("不可恢复", content)
        self.assertIn("奖励、兑换、交易与管理审计流水会保留", content)

    def test_migration_keeps_only_hashed_openid_audit(self):
        migration = (
            Path(__file__).parents[1] / "数据库源文件" / "p17_account_deletion.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("account_deletion_log", migration)
        self.assertIn("openid_hash CHAR(64)", migration)
        self.assertNotIn("openid VARCHAR", migration)


class AccountDeletionRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_parser_accepts_preview_and_exact_confirmation(self):
        self.assertEqual(("删号", ""), await jiance("删号"))
        self.assertEqual(("删号", "确认删除"), await jiance("删号 确认删除"))

    async def test_command_routes_confirmation_to_handler(self):
        calls = []

        async def fake_uid(_openid):
            return 100001

        async def fake_delete(uid, confirmation):
            calls.append((uid, confirmation))
            return {"type": "markdown", "content": "ok"}

        with patch.object(output_main, "openid_to_uid", fake_uid), patch.object(
            output_main, "delete_account", fake_delete
        ):
            result = await output_main.content("删号", "确认删除", "openid")
        self.assertEqual("ok", result["content"])
        self.assertEqual([(100001, "确认删除")], calls)


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, *_args):
        return False


class _DeletionCursor:
    def __init__(self, role_level=9):
        self.role_level = role_level
        self.executed = []
        self._rows = []
        self.rowcount = 0

    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.executed.append((compact, params))
        self.rowcount = 0
        if compact.startswith("SELECT COUNT(*) FROM information_schema.TABLES"):
            self._rows = [(1,)]
        elif compact.startswith("SELECT id,openid,`name` FROM user_zt"):
            self._rows = [(100001, "opaque-openid", "测试道友")]
        elif compact.startswith("SELECT id,`name`,dengji,is_chuzhan FROM user_role"):
            self._rows = [(91, "韩立", self.role_level, 1)]
        elif compact.startswith("SELECT storage_key FROM power_portrait_submission"):
            self._rows = []
        elif compact.startswith("SELECT id FROM user_spirit_beast_v2"):
            self._rows = []
        elif compact.startswith("SELECT id FROM party WHERE"):
            self._rows = []
        elif compact.startswith("SELECT id FROM expedition_session WHERE"):
            self._rows = []
        elif compact.startswith("SELECT id FROM sect WHERE"):
            self._rows = []
        elif compact.startswith("SELECT c.TABLE_NAME,c.COLUMN_NAME"):
            self._rows = [
                ("user_item", "uid"),
                ("user_role", "uid"),
                ("web_session", "uid"),
            ]
        elif compact.startswith("DELETE FROM `"):
            self._rows = []
            self.rowcount = 1
        elif compact.startswith("INSERT INTO account_deletion_log"):
            self._rows = []
            self.rowcount = 1
        elif compact == "DELETE FROM user_zt WHERE id=%s":
            self._rows = []
            self.rowcount = 1
        elif compact.startswith("CREATE TABLE IF NOT EXISTS account_deletion_log"):
            self._rows = []
        else:
            raise AssertionError(f"unexpected SQL: {compact}")

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self, role_level=9):
        self.fake_cursor = _DeletionCursor(role_level)
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def cursor(self):
        return _CursorContext(self.fake_cursor)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class AccountDeletionTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_deletion_commits_all_player_rows_then_main_account(self):
        connection = _Connection()
        with patch.object(
            account_deletion_service, "connect_mysql", return_value=connection
        ), patch("Tool.power_portrait.remove_portrait_file") as remove_file:
            result = await delete_player_account(100001)

        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertEqual(3, result["deleted_rows"])
        statements = [sql for sql, _ in connection.fake_cursor.executed]
        self.assertEqual("DELETE FROM user_zt WHERE id=%s", statements[-1])
        self.assertTrue(any("INSERT INTO account_deletion_log" in sql for sql in statements))
        self.assertFalse(any("reward_ledger" in sql for sql in statements))
        remove_file.assert_not_called()

    async def test_level_change_rolls_back_without_deleting_account(self):
        connection = _Connection(role_level=10)
        with patch.object(
            account_deletion_service, "connect_mysql", return_value=connection
        ):
            with self.assertRaises(AccountDeletionError):
                await delete_player_account(100001)
        self.assertTrue(connection.rolled_back)
        self.assertFalse(connection.committed)
        self.assertFalse(
            any(
                sql == "DELETE FROM user_zt WHERE id=%s"
                for sql, _ in connection.fake_cursor.executed
            )
        )


class _AllocationCursor:
    def __init__(self, deleted=True):
        self.deleted = deleted
        self.executed = []
        self._row = None

    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.executed.append((compact, params))
        if compact.startswith("SELECT COUNT(*) FROM information_schema.TABLES"):
            self._row = (1,)
        elif compact.startswith("SELECT GREATEST("):
            self._row = (100321,)
        elif compact.startswith("SELECT 1 FROM account_deletion_log"):
            self._row = (1,) if self.deleted else None
        else:
            self._row = None

    async def fetchone(self):
        return self._row


class AccountDeletionRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_uid_allocation_never_uses_account_count(self):
        cursor = _AllocationCursor()
        self.assertEqual(100321, await allocate_player_uid(cursor))
        sql = " ".join(statement for statement, _ in cursor.executed)
        self.assertIn("MAX(id)", sql)
        self.assertIn("MAX(last_uid)", sql)
        self.assertNotIn("COUNT(*)", sql)

    async def test_returning_player_lookup_hashes_openid(self):
        cursor = _AllocationCursor(deleted=True)
        self.assertTrue(await was_openid_deleted(cursor, "private-openid"))
        lookup = next(
            params
            for statement, params in cursor.executed
            if statement.startswith("SELECT 1 FROM account_deletion_log")
        )
        self.assertNotEqual("private-openid", lookup[0])
        self.assertEqual(64, len(lookup[0]))


if __name__ == "__main__":
    unittest.main()
