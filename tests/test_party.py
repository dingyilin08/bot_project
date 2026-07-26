import unittest

from Game_main.g13_party import FORMATIONS, parse_formation


class PartyTests(unittest.TestCase):
    def test_parse_formation_accepts_supported_layout(self):
        self.assertEqual(parse_formation("玄武-前列"), ("玄武", "前列"))
        self.assertIn("流云", FORMATIONS)

    def test_parse_formation_rejects_invalid_values(self):
        self.assertIsNone(parse_formation("未知-前列"))
        self.assertIsNone(parse_formation("玄武"))
