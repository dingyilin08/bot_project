import unittest

from Game_main.g12_spirit_beast import combat_bonus, origin_synergy


class SpiritBeastTests(unittest.TestCase):
    def test_combat_bonus_is_bounded_and_role_specific(self):
        bonus = combat_bonus({"aptitude": 1000, "role": "STRIKER"})
        self.assertEqual(bonus["buff_type"], "attack_up")
        self.assertEqual(bonus["value"], 12)

    def test_origin_synergy_describes_matching_origin(self):
        self.assertIn("异火协同", origin_synergy("异火本源", {"role": "STRIKER"}))

    def test_missing_profile_has_no_bonus(self):
        self.assertEqual(combat_bonus(None), {})
