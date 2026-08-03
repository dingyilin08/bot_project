import unittest

from Game_main.g20_world_boss import (
    _render,
    apply_pve_damage_bonus,
    apply_world_pve_bonus,
    boss_phase,
    contribution_for,
    parse_action,
)


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

    def test_causal_and_season_pve_bonus_stack_with_a_cap(self):
        damage, bonus = apply_pve_damage_bonus(
            10_000,
            {"attack_bp": 300},
            {"attack_bp": 500},
        )
        self.assertEqual((damage, bonus), (10_800, 800))
        self.assertEqual(
            apply_pve_damage_bonus(10_000, {"attack_bp": 9_999}),
            (11_000, 1_000),
        )

    def test_every_season_stat_has_a_real_world_boss_contribution_effect(self):
        for stat in ("attack_bp", "defense_bp", "speed_bp"):
            season = {
                "active": True,
                "value_bp": 300,
                stat: 300,
            }
            with self.subTest(stat=stat):
                damage, support, damage_bp, support_bp = apply_world_pve_bonus(
                    10_000,
                    2_000,
                    {"attack_bp": 300, "defense_bp": 300},
                    season,
                )
                self.assertEqual((damage, support), (10_600, 2_120))
                self.assertEqual((damage_bp, support_bp), (600, 600))
