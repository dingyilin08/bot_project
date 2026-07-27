import unittest

from Game_main.g20_world_boss import boss_phase, contribution_for, parse_action


class WorldBossTests(unittest.TestCase):
    def test_assist_is_a_valid_low_power_contribution(self):
        self.assertEqual(parse_action("辅助"), "辅助")
        self.assertGreaterEqual(contribution_for("辅助", 1)[1], 1200)

    def test_phase_transitions_are_stable(self):
        self.assertEqual(boss_phase(1_000_000), 1)
        self.assertEqual(boss_phase(660_000), 2)
        self.assertEqual(boss_phase(330_000), 3)
