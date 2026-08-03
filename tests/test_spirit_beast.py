import unittest

from Game_main.g12_spirit_beast import (
    apply_beast_snapshot_to_entity,
    combat_bonus,
    origin_synergy,
    origin_synergy_effect,
)
from Tool.combat_system import CombatEntity


class SpiritBeastTests(unittest.TestCase):
    def test_combat_bonus_is_bounded_and_role_specific(self):
        bonus = combat_bonus({"aptitude": 1000, "role": "STRIKER"})
        self.assertEqual(bonus["buff_type"], "attack_up")
        self.assertEqual(bonus["value"], 12)

    def test_origin_synergy_describes_matching_origin(self):
        self.assertIn("异火协同", origin_synergy("异火本源", {"role": "STRIKER"}))

    def test_missing_profile_has_no_bonus(self):
        self.assertEqual(combat_bonus(None), {})

    def test_origin_synergy_rules_use_bounded_machine_codes(self):
        self.assertEqual(
            origin_synergy_effect("异火本源", {"role": "STRIKER"})["code"],
            "FIRE_STRIKER",
        )
        self.assertEqual(
            origin_synergy_effect("轮回本源", {"role": "HEALER"})["heal_percent"],
            5,
        )
        self.assertEqual(
            origin_synergy_effect("掌天瓶", {"role": "GUARDIAN"})["shield_bonus"],
            5,
        )

    def test_frozen_snapshot_is_injected_without_a_second_database_read(self):
        entity = CombatEntity(
            "测试角色",
            {"qixue": 100, "gongji": 20, "fangyu": 10, "sudu": 10, "baoji": 0, "baoshang": 0,
             "shanbi": 0, "mingzhong": 10_000, "pofang": 0, "xixue": 0},
            [],
        )
        snapshot = {
            "name": "赤焰狐",
            "combat_bonus": {"buff_type": "attack_up", "value": 12, "label": "输出灵契"},
            "synergy": {"code": "FIRE_STRIKER"},
        }
        self.assertIs(apply_beast_snapshot_to_entity(snapshot, entity), snapshot)
        self.assertEqual(entity.role_data["spirit_beast"]["synergy"]["code"], "FIRE_STRIKER")
        self.assertTrue(entity.has_buff("attack_up"))
