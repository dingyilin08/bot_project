import unittest

from Game_domain.dungeon_daily_limit import (
    DAILY_DUNGEON_ATTEMPT_LIMIT,
    MAX_DUNGEON_ATTEMPT_LIMIT,
    remaining_daily_attempts,
)


class DungeonDailyLimitTests(unittest.TestCase):
    def test_base_attempts_are_shared_twenty(self):
        self.assertEqual(DAILY_DUNGEON_ATTEMPT_LIMIT, 20)
        self.assertEqual(remaining_daily_attempts(0), 20)
        self.assertEqual(remaining_daily_attempts(19), 1)
        self.assertEqual(remaining_daily_attempts(20), 0)

    def test_stamina_potion_can_expand_but_not_exceed_forty(self):
        self.assertEqual(MAX_DUNGEON_ATTEMPT_LIMIT, 40)
        self.assertEqual(remaining_daily_attempts(20, 25), 5)
        self.assertEqual(remaining_daily_attempts(20, 40), 20)
        self.assertEqual(remaining_daily_attempts(20, 999), 20)
        self.assertEqual(remaining_daily_attempts(80, 40), 0)


if __name__ == "__main__":
    unittest.main()
