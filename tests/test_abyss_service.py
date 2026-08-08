import unittest
from unittest.mock import AsyncMock, patch

from Game_domain.abyss_service import _run_from_row, is_role_locked_by_abyss
from Game_domain.battle_models import BattleSession
from Game_main.g11_battle import _settle_finished_battle


class _LockCursor:
    def __init__(self, row):
        self.row = row
        self.sql = ""
        self.params = None

    async def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())
        self.params = params

    async def fetchone(self):
        return self.row


class AbyssServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_run_row_decodes_all_snapshots(self):
        row = (
            "run-1", 1, "NORMAL", 12, 10001, "仙逆", 12, "seed", "FIGHTING",
            2, 7, "0.75", 3, '{"name":"王林"}', '{"attack_bp":100}',
            '{"required_exp":2000}', None, None, None,
        )
        run = _run_from_row(row)
        self.assertEqual(run["role_snapshot"]["name"], "王林")
        self.assertEqual(run["effect_snapshot"]["attack_bp"], 100)
        self.assertEqual(run["reward_snapshot"]["required_exp"], 2000)
        self.assertEqual(run["player_hp_ratio"], 0.75)

    async def test_role_lock_only_queries_started_run_states(self):
        cursor = _LockCursor((1,))
        self.assertTrue(await is_role_locked_by_abyss(100001, cursor))
        self.assertIn("FIGHTING", cursor.sql)
        self.assertIn("QUALIFIED", cursor.sql)
        self.assertNotIn("'READY'", cursor.sql)
        self.assertEqual(cursor.params, (100001,))

    async def test_battle_dispatches_abyss_without_touching_dungeon_settlement(self):
        session = BattleSession.new(owner_uid=1, battle_type="ABYSS", snapshot={})
        expected = {"type": "markdown", "content": "深渊结算"}
        with patch("Game_main.g32_abyss.settle_abyss_battle", AsyncMock(return_value=expected)) as settle:
            result = await _settle_finished_battle(1, session)
        self.assertEqual(result, expected)
        settle.assert_awaited_once_with(1, session)


if __name__ == "__main__":
    unittest.main()
