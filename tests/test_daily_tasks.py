import asyncio
import unittest
from pathlib import Path

from Game_main.g25_daily_tasks import (
    DAILY_ALL_XIANYU,
    DAILY_TASKS,
    DAILY_XIANYU_PER_TASK,
    task_by_key,
)
from output_main import jiance


class DailyTaskTests(unittest.TestCase):
    def test_five_tasks_and_total_xianyu_are_consistent(self):
        self.assertEqual(5, len(DAILY_TASKS))
        self.assertEqual(300, DAILY_ALL_XIANYU)
        self.assertEqual(DAILY_ALL_XIANYU, len(DAILY_TASKS) * DAILY_XIANYU_PER_TASK)

    def test_task_key_supports_number_and_code(self):
        self.assertEqual("CULTIVATION", task_by_key("1")[0])
        self.assertEqual("ALCHEMY", task_by_key("alchemy")[0])
        self.assertIsNone(task_by_key("0"))

    def test_daily_commands_are_parsed(self):
        self.assertEqual(("日常任务", ""), asyncio.run(jiance("日常任务")))
        self.assertEqual(("日常领取", "3"), asyncio.run(jiance("日常领取 3")))
        self.assertEqual(("日常领取", "全部"), asyncio.run(jiance("日常领取 全部")))

    def test_migration_contains_idempotent_progress_and_bonus_tables(self):
        sql = (Path(__file__).resolve().parents[1] / "数据库源文件" / "p2_daily_tasks.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS user_daily_task_progress", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS user_daily_task_bonus", sql)
        self.assertIn("UNIQUE KEY uk_daily_task", sql)
        self.assertIn("UNIQUE KEY uk_daily_task_bonus", sql)


if __name__ == "__main__":
    unittest.main()
