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
        self.assertIn("v1.23", content)
        self.assertIn("三十日签到", content)
        self.assertIn("角色专属战斗养成", content)
        self.assertIn("灵兽园", content)
        self.assertIn("队伍", content)

    def test_update_log_does_not_expose_implementation_or_deployment_details(self):
        content = asyncio.run(show_update_log(1))["content"]
        for term in ("数据库", "迁移", "部署", "快照", "幂等", "接口", "后端"):
            self.assertNotIn(term, content)
