import unittest
from unittest.mock import AsyncMock, patch

from Game_domain.dungeon_daily_limit import (
    DAILY_DUNGEON_ATTEMPT_LIMIT,
    get_daily_attempt_status,
    increase_daily_attempt_limit,
    remaining_daily_attempts,
)


class DungeonDailyLimitTests(unittest.TestCase):
    def test_base_attempts_are_shared_twenty(self):
        self.assertEqual(DAILY_DUNGEON_ATTEMPT_LIMIT, 20)
        self.assertEqual(remaining_daily_attempts(0), 20)
        self.assertEqual(remaining_daily_attempts(19), 1)
        self.assertEqual(remaining_daily_attempts(20), 0)

    def test_stamina_potion_expansion_has_no_gameplay_cap(self):
        self.assertEqual(remaining_daily_attempts(20, 25), 5)
        self.assertEqual(remaining_daily_attempts(20, 40), 20)
        self.assertEqual(remaining_daily_attempts(20, 999), 979)
        self.assertEqual(remaining_daily_attempts(80, 40), 0)


class _UnlimitedAttemptCursor:
    def __init__(self, used=20, attempt_limit=999):
        self.used = used
        self.attempt_limit = attempt_limit
        self._row = None
        self.rowcount = 0

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        self._row = None
        self.rowcount = 0
        if statement.startswith("SELECT id FROM user_zt"):
            self._row = (params[0],)
        elif statement.startswith("INSERT IGNORE INTO user_dungeon_daily_usage"):
            self.rowcount = 0
        elif statement.startswith("SELECT used_count,attempt_limit"):
            self._row = (self.used, self.attempt_limit)
        elif statement.startswith("UPDATE user_dungeon_daily_usage"):
            self.attempt_limit = int(params[0])
            self.rowcount = 1
        elif statement.startswith("UPDATE user_zt"):
            self.rowcount = 1
        else:
            raise AssertionError(f"未预期的历练额度 SQL：{statement}")

    async def fetchone(self):
        return self._row


class DungeonDailyUnlimitedUsageTests(unittest.IsolatedAsyncioTestCase):
    async def test_increase_can_continue_beyond_previous_cap(self):
        cursor = _UnlimitedAttemptCursor(attempt_limit=999)
        with patch(
            "Game_domain.dungeon_daily_limit.has_active_monthly_card",
            AsyncMock(return_value=False),
        ):
            result = await increase_daily_attempt_limit(cursor, 7, 50)

        self.assertEqual(result["limit"], 1049)
        self.assertEqual(result["added"], 50)
        self.assertEqual(result["remaining"], 1029)
        self.assertEqual(cursor.attempt_limit, 1049)

    async def test_monthly_card_adds_five_without_changing_stored_limit(self):
        cursor = _UnlimitedAttemptCursor(used=3, attempt_limit=20)
        with patch(
            "Game_domain.dungeon_daily_limit.has_active_monthly_card",
            AsyncMock(return_value=True),
        ):
            result = await get_daily_attempt_status(cursor, 7)

        self.assertEqual(result["stored_limit"], 20)
        self.assertEqual(result["monthly_card_bonus"], 5)
        self.assertEqual(result["limit"], 25)
        self.assertEqual(result["remaining"], 22)


if __name__ == "__main__":
    unittest.main()
