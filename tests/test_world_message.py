# -*- coding: utf-8 -*-
import asyncio
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from Game_domain.gm_service import GMError
from Game_domain import world_message_service as service
from Game_main import g27_world_message
from Tool import qq_reply_footer as footer
from Tool.qq_keyboard import attach_keyboard
from Tool.qq_official_group import OFFICIAL_GROUP_NOTICE
from output_main import jiance


class _RotationCursor:
    def __init__(self, state, messages, events=None):
        self.state = state
        self.messages = messages
        self.events = list(events or [])
        self.result = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, sql, params=()):
        statement = " ".join(sql.split())
        self.result = None
        if statement.startswith("SELECT id,content FROM world_message_event_queue"):
            self.result = self.events[0] if self.events else None
            return
        if statement.startswith("UPDATE world_message_event_queue"):
            if self.events and int(params[0]) == int(self.events[0][0]):
                self.events.pop(0)
            return
        if statement.startswith("INSERT IGNORE INTO world_message_state"):
            return
        if "SELECT next_source,last_message_id" in statement:
            self.result = (self.state["next_source"], self.state["last_message_id"])
            return
        if "SELECT id,content FROM world_message" in statement and "id>%s" in statement:
            last_id = int(params[0])
            self.result = next(
                (item for item in self.messages if item[0] > last_id), None
            )
            return
        if "SELECT id,content FROM world_message" in statement:
            self.result = self.messages[0] if self.messages else None
            return
        if "SET next_source=%s,last_message_id=%s" in statement:
            self.state["next_source"] = int(params[0])
            self.state["last_message_id"] = int(params[1])
            return
        if "SET next_source=%s" in statement:
            self.state["next_source"] = int(params[0])
            return
        raise AssertionError(f"未处理的 SQL：{statement}")

    async def fetchone(self):
        return self.result


class _RotationConnection:
    def __init__(self, state, messages, events=None):
        self.cursor_instance = _RotationCursor(state, messages, events)
        self.commits = 0

    def cursor(self):
        return self.cursor_instance

    async def commit(self):
        self.commits += 1


class _ScriptedCursor:
    def __init__(self, fetchone_values=(), lastrowid=0):
        self.fetchone_values = list(fetchone_values)
        self.lastrowid = lastrowid
        self.executions = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, sql, params=()):
        self.executions.append((" ".join(sql.split()), params))

    async def fetchone(self):
        return self.fetchone_values.pop(0) if self.fetchone_values else None


class _ScriptedConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.commits = 0

    def cursor(self):
        return self.cursor_instance

    async def commit(self):
        self.commits += 1


class WorldMessageValidationTests(unittest.TestCase):
    def test_content_normalization_and_update_parser(self):
        self.assertEqual(
            "副本前 记得检查技能！",
            service.normalize_world_message_content("  副本前\n记得检查技能！  "),
        )
        self.assertEqual(
            (12, "副本前-记得检查技能！"),
            service.parse_world_message_update("12-副本前-记得检查技能！"),
        )
        with self.assertRaises(service.WorldMessageError):
            service.normalize_world_message_content("")
        with self.assertRaises(service.WorldMessageError):
            service.normalize_world_message_content("道" * 181)
        with self.assertRaises(service.WorldMessageError):
            service.parse_world_message_id("0")

    def test_world_message_commands_preserve_spaces_and_punctuation(self):
        self.assertEqual(("GM世界消息", ""), asyncio.run(jiance("GM世界消息")))
        self.assertEqual(
            ("GM世界消息添加", "副本前，记得检查技能！"),
            asyncio.run(jiance("GM世界消息添加 副本前，记得检查技能！")),
        )
        self.assertEqual(
            ("GM世界消息修改", "12-每天先签到，再做日常。"),
            asyncio.run(jiance("GM世界消息修改 12-每天先签到，再做日常。")),
        )

    def test_non_admin_cannot_write_message_library(self):
        with patch.object(
            service, "require_admin", side_effect=GMError("你不是管理员")
        ):
            with self.assertRaisesRegex(GMError, "你不是管理员"):
                asyncio.run(service.add_world_message(10001, "攻略消息"))

    def test_migration_contains_library_state_and_seed_messages(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "数据库源文件" / "p2_world_message.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS world_message", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS world_message_state", migration)
        self.assertIn("世界BOSS", migration)


class WorldMessageRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_inserts_parameterized_message_and_commits(self):
        cursor = _ScriptedCursor(fetchone_values=[None], lastrowid=9)
        connection = _ScriptedConnection(cursor)

        @asynccontextmanager
        async def fake_connect_mysql():
            yield connection

        with patch.object(service, "require_admin", lambda uid: None), patch.object(
            service, "connect_mysql", fake_connect_mysql
        ):
            result = await service.add_world_message(10001, "每天先签到。")

        self.assertEqual(9, result["id"])
        self.assertTrue(result["created"])
        self.assertEqual(1, connection.commits)
        insert_sql, insert_params = cursor.executions[-1]
        self.assertIn("INSERT INTO world_message", insert_sql)
        self.assertNotIn("每天先签到。", insert_sql)
        self.assertEqual("每天先签到。", insert_params[0])
        self.assertEqual(64, len(insert_params[1]))

    async def test_add_restores_matching_soft_deleted_message_without_duplicate(self):
        cursor = _ScriptedCursor(
            fetchone_values=[(4, "记得收丹。", 0, 1)], lastrowid=99
        )
        connection = _ScriptedConnection(cursor)

        @asynccontextmanager
        async def fake_connect_mysql():
            yield connection

        with patch.object(service, "require_admin", lambda uid: None), patch.object(
            service, "connect_mysql", fake_connect_mysql
        ):
            result = await service.add_world_message(10001, "记得收丹。")

        self.assertEqual(4, result["id"])
        self.assertFalse(result["created"])
        self.assertTrue(result["restored"])
        self.assertIn("UPDATE world_message", cursor.executions[-1][0])
        self.assertEqual(1, connection.commits)

    async def test_repeated_soft_delete_is_idempotent(self):
        cursor = _ScriptedCursor(fetchone_values=[("旧攻略", 1)])
        connection = _ScriptedConnection(cursor)

        @asynccontextmanager
        async def fake_connect_mysql():
            yield connection

        with patch.object(service, "require_admin", lambda uid: None), patch.object(
            service, "connect_mysql", fake_connect_mysql
        ):
            result = await service.delete_world_message(10001, 3)

        self.assertFalse(result["changed"])
        self.assertEqual(1, len(cursor.executions))
        self.assertEqual(1, connection.commits)


class ReplyFooterTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_and_world_notice_slots_are_formatted(self):
        async def official_slot():
            return None

        async def world_slot():
            return "每天先签到，再完成日常任务。"

        with patch.object(footer, "next_world_message_slot", official_slot):
            official = await footer.append_rotating_reply_notice("领取成功")
        with patch.object(footer, "next_world_message_slot", world_slot):
            world = await footer.append_rotating_reply_notice("领取成功")

        self.assertTrue(official.endswith(OFFICIAL_GROUP_NOTICE))
        self.assertTrue(world.endswith("🌏 世界消息：每天先签到，再完成日常任务。"))

    async def test_existing_footer_is_idempotent_and_skips_database_slot(self):
        calls = 0

        async def unexpected_slot():
            nonlocal calls
            calls += 1
            return "不应读取"

        content = f"欢迎加入\n\n{OFFICIAL_GROUP_NOTICE}"
        with patch.object(footer, "next_world_message_slot", unexpected_slot):
            result = await footer.append_rotating_reply_notice(content)

        self.assertEqual(content, result)
        self.assertEqual(0, calls)

    async def test_dict_attachment_preserves_keyboard_without_mutating_input(self):
        async def world_slot():
            return "先查看角色属性再规划养成。"

        payload = {"type": "markdown_keyboard", "content": "角色属性", "keyboard": {}}
        with patch.object(footer, "next_world_message_slot", world_slot):
            result = await footer.attach_rotating_reply_notice(payload)

        self.assertEqual("角色属性", payload["content"])
        self.assertIs(payload["keyboard"], result["keyboard"])
        self.assertIn("🌏 世界消息：", result["content"])


class WorldMessageRotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_temporary_login_event_is_published_before_regular_rotation(self):
        state = {"next_source": service.OFFICIAL_SLOT, "last_message_id": None}
        connection = _RotationConnection(
            state,
            [(1, "攻略一")],
            events=[(9, "尊贵的月华玩家凌霄已上线！")],
        )

        @asynccontextmanager
        async def fake_connect_mysql():
            yield connection

        with patch.object(service, "connect_mysql", fake_connect_mysql):
            first = await service.next_world_message_slot()
            second = await service.next_world_message_slot()

        self.assertEqual("尊贵的月华玩家凌霄已上线！", first)
        self.assertIsNone(second)
        self.assertEqual(2, connection.commits)

    async def test_global_slots_alternate_and_world_messages_round_robin(self):
        state = {"next_source": service.OFFICIAL_SLOT, "last_message_id": None}
        connection = _RotationConnection(state, [(1, "攻略一"), (2, "攻略二")])

        @asynccontextmanager
        async def fake_connect_mysql():
            yield connection

        with patch.object(service, "connect_mysql", fake_connect_mysql):
            values = [await service.next_world_message_slot() for _ in range(4)]

        self.assertEqual([None, "攻略一", None, "攻略二"], values)
        self.assertEqual(service.OFFICIAL_SLOT, state["next_source"])
        self.assertEqual(2, state["last_message_id"])
        self.assertEqual(4, connection.commits)


class WorldMessageGMViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_gm_menu_lists_status_and_declares_management_buttons(self):
        async def fake_list(uid):
            return [
                {
                    "id": 7,
                    "content": "每天先签到。",
                    "enabled": True,
                    "created_by": uid,
                    "updated_by": uid,
                }
            ]

        with patch.object(g27_world_message, "list_world_messages", fake_list):
            result = await g27_world_message.gm_world_message_menu.__wrapped__(10001, "")
        result = attach_keyboard(result, is_group=False)

        self.assertIn("#7｜✅ 启用", result["content"])
        buttons = [
            button
            for row in result["keyboard"]["content"]["rows"]
            for button in row["buttons"]
        ]
        commands = [button["action"]["data"] for button in buttons]
        self.assertIn("GM世界消息添加", commands)
        self.assertIn("GM世界消息修改", commands)
        self.assertFalse(buttons[0]["action"]["enter"])


if __name__ == "__main__":
    unittest.main()
