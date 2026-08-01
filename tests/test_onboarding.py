import asyncio
import unittest

from Game_main.g16_onboarding import ONBOARDING_ALL_XIANYU, ONBOARDING_XIANYU_PER_TASK, TASKS, task_by_key
from output_main import jiance


class OnboardingTests(unittest.TestCase):
    def test_task_keys_support_number_and_code(self):
        self.assertEqual(task_by_key("1")[0], "ROLE")
        self.assertEqual(task_by_key("battle")[0], "BATTLE")
        self.assertIsNone(task_by_key("0"))
        self.assertEqual(len(TASKS), 7)
        self.assertEqual(2020, len(TASKS) * ONBOARDING_XIANYU_PER_TASK + ONBOARDING_ALL_XIANYU)

    def test_onboarding_commands_are_parsed(self):
        self.assertEqual(asyncio.run(jiance("问道札记")), ("问道札记", ""))
        self.assertEqual(asyncio.run(jiance("札记领取 3")), ("札记领取", "3"))
        self.assertEqual(asyncio.run(jiance("札记领取 全部")), ("札记领取", "全部"))
        self.assertEqual(asyncio.run(jiance("道途建议")), ("道途建议", ""))
