import asyncio
import unittest

from Game_main.g0_menu import show_update_log
from output_main import jiance


class UpdateLogTests(unittest.TestCase):
    def test_update_log_can_be_parsed_as_a_parameterless_command(self):
        self.assertEqual(asyncio.run(jiance("更新日志")), ("更新日志", ""))

    def test_update_log_mentions_current_version_and_features(self):
        response = asyncio.run(show_update_log(1))
        content = response["content"]
        self.assertIn("v1.22", content)
        self.assertIn("灵兽园", content)
        self.assertIn("队伍", content)
