# -*- coding: utf-8 -*-
import asyncio
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import main
from Game_domain.dao_heart_service import (
    BUFF_DURATION,
    DaoHeartError,
    apply_basis_points,
    choose_daily_path,
    deterministic_event,
)
from Game_main.g40_dao_heart import render_dao_heart_state
from output_main import jiance


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _DaoHeartCursor:
    def __init__(self, daily=None):
        self.calls = []
        self.daily = daily
        self.rowcount = 0

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        self.calls.append((statement, params))
        self.rowcount = 1 if statement.startswith("UPDATE dao_heart_daily") else 0

    async def fetchone(self):
        statement = self.calls[-1][0]
        if statement == "SELECT CURDATE()":
            return (date(2026, 8, 21),)
        if statement.startswith("SELECT `name`,lingshi FROM user_zt"):
            return ("道友", 1000)
        if statement.startswith("SELECT clarity,courage,compassion"):
            return (1, 2, 3, None, 0, None)
        if statement.startswith("SELECT event_key,event_version,event_seed"):
            return self.daily
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


class DaoHeartRuleTests(unittest.TestCase):
    def test_event_seed_is_reproducible(self):
        first = deterministic_event(10001, date(2026, 8, 21))
        second = deterministic_event(10001, "2026-08-21")
        self.assertEqual(first["key"], second["key"])
        self.assertEqual(first["seed"], second["seed"])
        self.assertEqual(16, len(first["seed"]))

    def test_basis_point_effects_are_capped_and_keep_minimum(self):
        self.assertEqual(112, apply_basis_points(100, 1200, increase=True))
        self.assertEqual(90, apply_basis_points(100, 1000, increase=False))
        self.assertEqual(30, apply_basis_points(31, 5000, increase=False, minimum=30))

    def test_qq_state_has_three_clear_choices(self):
        event = deterministic_event(10001, "2026-08-21")
        state = {
            "event": {
                "title": event["title"],
                "description": event["description"],
                "seed": event["seed"],
                "choices": [
                    {
                        "label": label,
                        "tendency": tendency,
                        "description": "抉择说明",
                        "reward": {"lingshi": 60},
                        "buff": "今日参悟增益",
                    }
                    for label, tendency in (("守心观照", "清明"), ("迎难问锋", "勇毅"), ("济人渡厄", "仁心"))
                ],
            },
            "tendencies": {"clarity": 0, "courage": 0, "compassion": 0},
            "chosen": False,
        }
        content = render_dao_heart_state(state)["content"]
        for tendency in ("清明", "勇毅", "仁心"):
            self.assertIn(f"道心抉择 {tendency}", content)


class DaoHeartTransactionTests(unittest.TestCase):
    def test_choice_grants_once_and_writes_reward_ledger(self):
        cursor = _DaoHeartCursor()
        connection = _Connection(cursor)
        with patch("Game_domain.dao_heart_service.connect_mysql", return_value=connection):
            result = asyncio.run(
                choose_daily_path(10001, "clarity", request_id="web-dao-1")
            )

        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertEqual(1060, result["balance_after"])
        self.assertEqual(BUFF_DURATION, result["buff"]["code"])
        statements = [sql for sql, _ in cursor.calls]
        self.assertTrue(any(sql.startswith("INSERT IGNORE INTO reward_ledger") for sql in statements))
        self.assertTrue(any(sql.startswith("UPDATE dao_heart_daily") for sql in statements))

    def test_second_choice_replays_without_another_grant(self):
        stored = {
            "choice_label": "守心观照",
            "tendencies": {"clarity": 3, "courage": 2, "compassion": 3},
            "reward": {"lingshi": 60},
            "buff": {"code": BUFF_DURATION, "text": "今日参悟时长缩短 10%"},
        }
        daily = ("rain_pavilion", 1, "0123456789abcdef", "clarity", json.dumps(stored, ensure_ascii=False))
        cursor = _DaoHeartCursor(daily=daily)
        connection = _Connection(cursor)
        with patch("Game_domain.dao_heart_service.connect_mysql", return_value=connection):
            result = asyncio.run(choose_daily_path(10001, "courage", request_id="retry"))

        self.assertTrue(result["replayed"])
        self.assertTrue(connection.rolled_back)
        self.assertFalse(any(sql.startswith("UPDATE user_zt SET lingshi") for sql, _ in cursor.calls))

    def test_invalid_choice_is_rejected_before_database(self):
        with self.assertRaises(DaoHeartError):
            asyncio.run(choose_daily_path(10001, "greed"))


class DaoHeartIntegrationTests(unittest.TestCase):
    def test_commands_and_web_routes_are_registered(self):
        self.assertEqual(("道心问境", ""), asyncio.run(jiance("道心问境")))
        self.assertEqual(("道心抉择", "清明"), asyncio.run(jiance("道心抉择 清明")))
        paths = {route.path for route in main.app.routes if hasattr(route, "path")}
        self.assertIn("/api/web/dao-heart", paths)
        self.assertIn("/api/web/dao-heart/choice", paths)

    def test_migration_has_daily_uniqueness_and_audit_fields(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "数据库源文件" / "p16_dao_heart.sql").read_text(encoding="utf-8")
        self.assertIn("UNIQUE KEY `uk_dao_heart_uid_date`", migration)
        self.assertIn("`event_seed`", migration)
        self.assertIn("`request_id`", migration)
        self.assertIn("`active_buff_expires_at`", migration)


if __name__ == "__main__":
    unittest.main()
