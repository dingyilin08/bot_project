import asyncio
import unittest

from Game_main.g35_daily_compass import build_daily_compass
from output_main import jiance


class DailyCompassViewTests(unittest.TestCase):
    def test_claimable_rewards_take_priority(self):
        response = build_daily_compass({
            "role_name": "韩立",
            "role_level": 20,
            "cultivation": {"state": "claimable", "remaining": 0, "exp": 1234},
            "daily": {
                "completed": 2,
                "total": 5,
                "unclaimed": 1,
                "pending": ["DUNGEON", "FARM", "ALCHEMY"],
                "bonus_claimed": False,
            },
            "active_dungeon": None,
        })
        content = response["content"]
        self.assertIn("领取参悟经验", content)
        self.assertIn("领取日常奖励", content)
        self.assertIn("今日修行", content)

    def test_running_dungeon_is_visible(self):
        response = build_daily_compass({
            "role_name": "叶凡",
            "role_level": 50,
            "cultivation": {"state": "running", "remaining": 65, "exp": 0},
            "daily": None,
            "active_dungeon": {"dungeon_id": 8, "wave": 2, "total_waves": 3},
        })
        self.assertIn("副本进行中", response["content"])
        self.assertIn("继续副本", response["content"])


class DailyCompassCommandTests(unittest.TestCase):
    def test_command_is_registered_without_parameter(self):
        self.assertEqual(asyncio.run(jiance("今日修行")), ("今日修行", ""))
