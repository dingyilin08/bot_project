import unittest

from Game_main.g20_world_boss import _render, boss_phase, contribution_for, parse_action


class WorldBossTests(unittest.TestCase):
    def test_world_boss_uses_keyboard_for_contribution_and_inline_text_for_navigation(self):
        result = _render((1, "2026-W31", "诸天魔渊主", 1_000_000, 800_000, "五行轮转"), 3)
        commands = [item["command"] for item in result["keyboard_commands"]]
        self.assertEqual(4, len(commands))
        self.assertIn("世界挑战 挑战", commands)
        self.assertNotIn("text='世界挑战 挑战'", result["content"])
        self.assertIn("<qqbot-cmd-input text='世界排行'", result["content"])

    def test_assist_is_a_valid_low_power_contribution(self):
        self.assertEqual(parse_action("辅助"), "辅助")
        self.assertGreaterEqual(contribution_for("辅助", 1)[1], 1200)

    def test_phase_transitions_are_stable(self):
        self.assertEqual(boss_phase(1_000_000), 1)
        self.assertEqual(boss_phase(660_000), 2)
        self.assertEqual(boss_phase(330_000), 3)
