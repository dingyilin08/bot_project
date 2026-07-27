import unittest
from Game_main.g18_alchemy_study import quality_weights, tolerance_multiplier, tolerance_factor, roll_alchemy_outcome
class AlchemyStudyTests(unittest.TestCase):
 def test_quality_weights_are_public_and_sum_to_100(self):
  self.assertEqual(sum(quality_weights('均衡', 20).values()),100)
  self.assertGreater(quality_weights('冒险', 30)['圆满'], quality_weights('冒险',0)['圆满'])
 def test_tolerance_has_a_floor(self):
  self.assertEqual(tolerance_multiplier(0),100); self.assertEqual(tolerance_multiplier(99),40)
 def test_tolerance_is_applied_per_pill(self):
  self.assertEqual(tolerance_factor(0, 2), 0.925)
 def test_fire_style_changes_actual_outcome(self):
  self.assertEqual(roll_alchemy_outcome('保守', 0, 96), (False, None, 0))
  self.assertEqual(roll_alchemy_outcome('冒险', 0, 84), (False, None, 0))
  self.assertGreaterEqual(roll_alchemy_outcome('冒险', 30, 50)[2], 1)
