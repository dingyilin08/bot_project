import asyncio
import unittest

from Game_main.g26_signin import (
    CYCLE_DAYS,
    DAILY_REWARDS,
    ITEM_NAMES,
    MILESTONE_REWARDS,
    combine_rewards,
    cycle_reward_total,
    milestone_for_day,
    next_cycle_position,
    reward_for_day,
    signin_reward_preview,
)
from output_main import jiance


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


class SigninRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_signin_commands_are_parameterless(self):
        for command in ("签到", "签到记录", "签到奖励"):
            self.assertEqual(await jiance(command), (command, ""))


if __name__ == "__main__":
    unittest.main()
