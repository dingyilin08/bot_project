import unittest

import output_main
from Game_main.g10_shop import (
    DEFAULT_SHOP_ITEMS,
    DUNGEON_SWEEP_TICKET_DAILY_LIMIT,
    DUNGEON_SWEEP_TICKET_ITEM_ID,
)
from Game_main.g29_dungeon_sweep import (
    build_sweep_reward_plan,
    calculate_full_clear_currency,
    parse_dungeon_id,
)
from Game_main.g6_dungeon import LINGSHI_MULTIPLIER
from output_main import jiance


class DungeonSweepTests(unittest.TestCase):
    def test_ticket_price_and_daily_limit_match_design(self):
        ticket = next(
            item for item in DEFAULT_SHOP_ITEMS
            if item["item_id"] == DUNGEON_SWEEP_TICKET_ITEM_ID
        )
        self.assertEqual(ticket["name"], "扫荡副本券")
        self.assertEqual(ticket["price"], 800)
        self.assertEqual(ticket["daily_limit"], DUNGEON_SWEEP_TICKET_DAILY_LIMIT)
        self.assertEqual(ticket["daily_limit"], 20)

    def test_parse_dungeon_id_only_accepts_positive_integer(self):
        self.assertEqual(parse_dungeon_id(" 12 "), 12)
        self.assertIsNone(parse_dungeon_id(""))
        self.assertIsNone(parse_dungeon_id("副本一"))
        self.assertIsNone(parse_dungeon_id(0))
        self.assertIsNone(parse_dungeon_id(-1))

    def test_full_clear_currency_matches_fifteen_manual_victories(self):
        exp, lingshi = calculate_full_clear_currency(150, 150)

        def expected(base):
            total = 0
            for kill in range(1, 16):
                boss = 2 if kill % 5 == 0 else 1
                streak = 1.5 if kill >= 15 else 1.35 if kill >= 10 else 1.2 if kill >= 5 else 1.1 if kill >= 3 else 1
                total += int(base * boss * streak)
            return total

        self.assertEqual(exp, expected(150))
        self.assertEqual(LINGSHI_MULTIPLIER, 1)
        self.assertEqual(lingshi, expected(10))

    def test_reward_plan_is_deterministic_and_includes_completion_drops(self):
        dungeon = {
            "reward_exp": 150,
            "reward_lingshi": 150,
            "reward_benyuan": 301,
            "rate_benyuan": 100,
            "reward_skill": "302|303",
            "rate_skill": 100,
            "reward_pojing_dan": 304,
            "rate_pojing_dan": 100,
            "reward_cl_boss": "305|306",
            "reward_cl_normal": "307|308",
        }
        equipments = ({"id": 99, "name": "试炼剑"},)
        first = build_sweep_reward_plan(dungeon, equipments, "same-request")
        second = build_sweep_reward_plan(dungeon, equipments, "same-request")
        self.assertEqual(first, second)
        self.assertEqual(first["item_totals"][301], 3)
        self.assertEqual(first["item_totals"][302], 3)
        self.assertEqual(first["item_totals"][303], 3)
        self.assertEqual(first["item_totals"][304], 1)
        self.assertGreaterEqual(first["item_totals"][307] + first["item_totals"][308], 12)
        self.assertEqual(first["equipment"]["equip_id"], 99)


class DungeonSweepCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_sweep_command_supports_list_and_dungeon_suffix(self):
        self.assertEqual(await jiance("扫荡副本"), ("扫荡副本", ""))
        self.assertEqual(await jiance("扫荡副本 12"), ("扫荡副本", "12"))

    async def test_content_routes_list_and_single_sweep_with_request_id(self):
        original_uid = output_main.openid_to_uid
        original_list = output_main.dungeon_sweep_list
        original_sweep = output_main.sweep_dungeon
        calls = []

        async def fake_uid(_openid):
            return 10001

        async def fake_list(uid):
            calls.append(("list", uid))
            return "list-result"

        async def fake_sweep(uid, dungeon_id, request_id=None):
            calls.append(("sweep", uid, dungeon_id, request_id))
            return "sweep-result"

        output_main.openid_to_uid = fake_uid
        output_main.dungeon_sweep_list = fake_list
        output_main.sweep_dungeon = fake_sweep
        try:
            self.assertEqual(
                await output_main.content("扫荡副本", "", "openid"),
                "list-result",
            )
            self.assertEqual(
                await output_main.content("扫荡副本", "12", "openid", request_id="msg-1"),
                "sweep-result",
            )
        finally:
            output_main.openid_to_uid = original_uid
            output_main.dungeon_sweep_list = original_list
            output_main.sweep_dungeon = original_sweep

        self.assertEqual(calls, [("list", 10001), ("sweep", 10001, "12", "msg-1")])


if __name__ == "__main__":
    unittest.main()
