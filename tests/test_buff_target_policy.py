import unittest
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "数据库源文件"
    / "p3_buff_target_policy.sql"
)


class BuffTargetPolicyTests(unittest.TestCase):
    def setUp(self):
        self.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_positive_buffs_target_the_caster(self):
        positive_section = self.sql.split("-- 负面状态", 1)[0]
        self.assertIn("set buff_target = 1", positive_section)
        for buff_type in (
            "attack_up",
            "defense_up",
            "shield",
            "heal_over_time",
            "pofang_up",
        ):
            self.assertIn(f"'{buff_type}'", positive_section)

    def test_debuffs_target_the_opponent(self):
        debuff_section = self.sql.split("-- 负面状态", 1)[1]
        self.assertIn("set buff_target = 2", debuff_section)
        for buff_type in (
            "attack_down",
            "burning",
            "silence",
            "stun",
            "death_sentence",
        ):
            self.assertIn(f"'{buff_type}'", debuff_section)

    def test_only_duration_buffs_are_retargeted(self):
        self.assertEqual(2, self.sql.count("where buff_duration > 0"))


if __name__ == "__main__":
    unittest.main()
