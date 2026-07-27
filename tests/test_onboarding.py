import asyncio
import unittest

from Game_main.g16_onboarding import TASKS, task_by_key
from output_main import jiance


class OnboardingTests(unittest.TestCase):
    def test_task_keys_support_number_and_code(self):
        self.assertEqual(task_by_key("1")[0], "ROLE")
        self.assertEqual(task_by_key("battle")[0], "BATTLE")
        self.assertIsNone(task_by_key("0"))
        self.assertEqual(len(TASKS), 7)

    def test_onboarding_commands_are_parsed(self):
        self.assertEqual(asyncio.run(jiance("问道札记")), ("问道札记", ""))
        self.assertEqual(asyncio.run(jiance("札记领取 3")), ("札记领取", "3"))
        self.assertEqual(asyncio.run(jiance("道途建议")), ("道途建议", ""))
