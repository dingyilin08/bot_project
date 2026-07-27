import unittest
from Game_main.g18_alchemy_study import quality_weights, tolerance_multiplier
class AlchemyStudyTests(unittest.TestCase):
 def test_quality_weights_are_public_and_sum_to_100(self):
  self.assertEqual(sum(quality_weights('均衡', 20).values()),100)
  self.assertGreater(quality_weights('冒险', 30)['圆满'], quality_weights('冒险',0)['圆满'])
 def test_tolerance_has_a_floor(self):
  self.assertEqual(tolerance_multiplier(0),100); self.assertEqual(tolerance_multiplier(99),40)
