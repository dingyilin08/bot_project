import unittest

from Game_domain.role_special_intro import render_role_special_intro
from Game_domain.role_trait_service import (
    ROLE_TRAITS,
    adjusted_start_timestamp,
    apply_battle_hp,
    apply_enhance_success_rate,
    apply_lingshi_output,
    apply_production_duration,
    heaven_pity_limit,
    trait_description,
)


class RoleTraitRuleTests(unittest.TestCase):
    def test_all_six_roles_have_account_traits(self):
        self.assertEqual(
            set(ROLE_TRAITS),
            {"萧炎", "韩立", "王林", "叶凡", "石昊", "孟川"},
        )
        for role_name in ROLE_TRAITS:
            self.assertIn("拥有即生效", trait_description(role_name))
            self.assertIn("拥有特性", render_role_special_intro(role_name))

    def test_production_traits_reduce_duration_by_twenty_percent(self):
        self.assertEqual(5760, apply_production_duration(7200, True))
        self.assertEqual(2880, apply_production_duration(3600, True))
        self.assertEqual(7200, apply_production_duration(7200, False))
        self.assertEqual(8560, adjusted_start_timestamp(10000, 7200, True))

    def test_wang_lin_increases_account_battle_hp(self):
        self.assertEqual(12000, apply_battle_hp(10000, True))
        self.assertEqual(10000, apply_battle_hp(10000, False))

    def test_ye_fan_increases_system_lingshi_output(self):
        self.assertEqual(120, apply_lingshi_output(100, True))
        self.assertEqual(100, apply_lingshi_output(100, False))
        self.assertEqual(0, apply_lingshi_output(0, True))

    def test_shi_hao_adds_ten_percentage_points_with_cap(self):
        self.assertEqual(7500, apply_enhance_success_rate(6500, True))
        self.assertEqual(10000, apply_enhance_success_rate(9500, True))
        self.assertEqual(6500, apply_enhance_success_rate(6500, False))

    def test_meng_chuan_changes_heaven_pity_to_fifty(self):
        self.assertEqual(50, heaven_pity_limit(True))
        self.assertEqual(60, heaven_pity_limit(False))


if __name__ == "__main__":
    unittest.main()
