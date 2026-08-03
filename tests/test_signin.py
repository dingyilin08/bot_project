import asyncio
import unittest

from Game_main.g26_signin import (
    CYCLE_DAYS,
    DAILY_REWARDS,
    ITEM_NAMES,
    MILESTONE_REWARDS,
    _grant_reward,
    _repair_signin_log_auto_increment,
    combine_rewards,
    cycle_reward_total,
    milestone_for_day,
    next_cycle_position,
    reward_for_day,
    signin_reward_preview,
)
from output_main import jiance


class _RewardCursor:
    def __init__(self, *, rowcount=1):
        self.rowcount = rowcount
        self.calls = []

    async def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))


class _AutoIncrementCursor:
    def __init__(self, *, auto_increment, max_id):
        self.auto_increment = auto_increment
        self.max_id = max_id
        self.calls = []

    async def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    async def fetchone(self):
        if "information_schema.TABLES" in self.calls[-1][0]:
            return (self.auto_increment,)
        return (self.max_id,)


class SigninRuleTests(unittest.TestCase):
    def test_thirty_day_schedule_is_complete_and_uses_known_items(self):
        self.assertEqual(len(DAILY_REWARDS), CYCLE_DAYS)
        for day in range(1, CYCLE_DAYS + 1):
            reward = reward_for_day(day)
            self.assertGreater(
                reward["lingshi"] + reward["xianyu"] + len(reward["items"]),
                0,
            )
            for item in reward["items"]:
                self.assertIn(item["item_id"], ITEM_NAMES)
                self.assertGreater(item["amount"], 0)

    def test_seven_day_and_thirty_day_milestones_are_explicit(self):
        self.assertEqual(set(MILESTONE_REWARDS), {7, 14, 21, 28, 30})
        for day in (7, 14, 21, 28):
            self.assertEqual(milestone_for_day(day)["kind"], "WEEKLY")
        self.assertEqual(milestone_for_day(30)["kind"], "MONTHLY")
        self.assertIsNone(milestone_for_day(29))

    def test_cycle_rolls_only_after_day_thirty(self):
        self.assertEqual(next_cycle_position(1, 0), (1, 1))
        self.assertEqual(next_cycle_position(2, 29), (2, 30))
        self.assertEqual(next_cycle_position(2, 30), (3, 1))

    def test_invalid_cycle_days_are_rejected(self):
        for day in (0, 31):
            with self.assertRaises(ValueError):
                reward_for_day(day)
        with self.assertRaises(ValueError):
            next_cycle_position(0, 0)

    def test_full_cycle_reward_matches_balance_budget(self):
        total = cycle_reward_total()
        self.assertEqual(total["lingshi"], 5030)
        self.assertEqual(total["xianyu"], 1500)
        item_totals = {item["item_id"]: item["amount"] for item in total["items"]}
        self.assertEqual(item_totals, {1: 4, 208: 8, 209: 8, 210: 9})

    def test_reward_combination_merges_same_item(self):
        combined = combine_rewards(reward_for_day(29), milestone_for_day(28)["reward"])
        item_totals = {item["item_id"]: item["amount"] for item in combined["items"]}
        self.assertEqual(item_totals[1], 2)

    def test_preview_discloses_milestones_and_total(self):
        response = asyncio.run(signin_reward_preview.__wrapped__(1, ""))
        content = response["content"]
        self.assertIn("七日累签礼", content)
        self.assertIn("三十日圆满礼", content)
        self.assertIn("灵石 ×5030", content)
        self.assertIn("仙玉 ×1500", content)

    def test_item_only_reward_does_not_require_currency_rowcount(self):
        cursor = _RewardCursor(rowcount=0)
        reward = reward_for_day(2)

        asyncio.run(_grant_reward(cursor, 100001, reward))

        self.assertFalse(any("UPDATE user_zt" in sql for sql, _ in cursor.calls))
        self.assertTrue(any("INSERT INTO user_item" in sql for sql, _ in cursor.calls))

    def test_currency_reward_still_rejects_missing_player_assets(self):
        cursor = _RewardCursor(rowcount=0)

        with self.assertRaisesRegex(RuntimeError, "玩家资产不存在"):
            asyncio.run(_grant_reward(cursor, 100001, reward_for_day(1)))

    def test_stale_signin_log_auto_increment_is_repaired(self):
        cursor = _AutoIncrementCursor(auto_increment=100007, max_id=100007)

        asyncio.run(_repair_signin_log_auto_increment(cursor))

        self.assertTrue(any("AUTO_INCREMENT = 100008" in sql for sql, _ in cursor.calls))

    def test_current_signin_log_auto_increment_is_left_unchanged(self):
        cursor = _AutoIncrementCursor(auto_increment=100008, max_id=100007)

        asyncio.run(_repair_signin_log_auto_increment(cursor))

        self.assertFalse(any("ALTER TABLE user_signin_log" in sql for sql, _ in cursor.calls))


class SigninRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_signin_commands_are_parameterless(self):
        for command in ("签到", "签到记录", "签到奖励"):
            self.assertEqual(await jiance(command), (command, ""))


if __name__ == "__main__":
    unittest.main()
