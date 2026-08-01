import random
import unittest

from Game_main.g1_role import _item_info_button
from Game_main.g4_benyuan import (
    _benyuan_material_requirements,
    _lock_and_consume_benyuan_materials,
)
from Game_main.g6_dungeon import _dungeon_reward_battle_id
from Tool.tool_canwu import canwu_remaining_seconds, roll_canwu_duration


class InventoryCursor:
    def __init__(self, inventory):
        self.inventory = dict(inventory)
        self.rowcount = 0
        self._fetchone = None
        self.statements = []

    async def execute(self, sql, params=None):
        compact_sql = " ".join(sql.split())
        self.statements.append((compact_sql, params))
        if compact_sql.startswith("SELECT item_num"):
            uid, item_id = params
            amount = self.inventory.get((uid, item_id))
            self._fetchone = (amount,) if amount is not None else None
            self.rowcount = 1 if amount is not None else 0
        elif compact_sql.startswith("UPDATE user_item"):
            amount, uid, item_id, minimum = params
            current = self.inventory.get((uid, item_id), 0)
            if current >= minimum:
                self.inventory[(uid, item_id)] = current - amount
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif compact_sql.startswith("DELETE FROM user_item"):
            uid, item_id = params
            if self.inventory.get((uid, item_id)) == 0:
                self.inventory.pop((uid, item_id), None)
                self.rowcount = 1
            else:
                self.rowcount = 0

    async def fetchone(self):
        return self._fetchone


class ReportedBugfixTests(unittest.IsolatedAsyncioTestCase):
    def test_canwu_duration_is_always_between_30_and_120_seconds(self):
        rng = random.Random(20260801)
        durations = [roll_canwu_duration(rng) for _ in range(500)]
        self.assertGreaterEqual(min(durations), 30)
        self.assertLessEqual(max(durations), 120)
        self.assertGreater(len(set(durations)), 1)

    def test_legacy_canwu_uses_old_duration_and_new_duration_is_persisted(self):
        self.assertEqual(canwu_remaining_seconds(1000, None, 1100), 1100)
        self.assertEqual(canwu_remaining_seconds(1000, 60, 1035), 25)

    def test_real_battle_session_id_prevents_cross_run_reward_collision(self):
        progress = {"start_time": "2026-08-01 12:00:00", "wave": 1}
        first = _dungeon_reward_battle_id(1, 2, progress, 1, "battle-run-a")
        second = _dungeon_reward_battle_id(1, 2, progress, 1, "battle-run-b")
        self.assertEqual(first, "battle-run-a")
        self.assertEqual(second, "battle-run-b")
        self.assertNotEqual(first, second)

    def test_item_bag_button_displays_only_item_name(self):
        self.assertEqual(
            _item_info_button("冰灵焰草"),
            "<qqbot-cmd-input text='物品信息 冰灵焰草' show='冰灵焰草' />",
        )

    def test_level_59_benyuan_uses_the_third_stage_material(self):
        requirements, is_stage = _benyuan_material_requirements(
            59, (101, 102, 103), (201, 202, 203)
        )
        self.assertTrue(is_stage)
        self.assertEqual(requirements, [(101, 3), (102, 2), (103, 1)])

    async def test_benyuan_missing_later_material_deducts_nothing(self):
        cursor = InventoryCursor({(7, 101): 10, (7, 102): 1})
        before = dict(cursor.inventory)
        missing = await _lock_and_consume_benyuan_materials(
            cursor, 7, [(101, 3), (102, 2)]
        )
        self.assertEqual(missing, [(102, 2, 1)])
        self.assertEqual(cursor.inventory, before)
        self.assertFalse(any(sql.startswith("UPDATE user_item") for sql, _ in cursor.statements))

    async def test_benyuan_materials_are_consumed_only_after_full_validation(self):
        cursor = InventoryCursor({(7, 101): 3, (7, 102): 2, (7, 103): 1})
        missing = await _lock_and_consume_benyuan_materials(
            cursor, 7, [(101, 3), (102, 2), (103, 1)]
        )
        self.assertEqual(missing, [])
        self.assertEqual(cursor.inventory, {})


if __name__ == "__main__":
    unittest.main()
