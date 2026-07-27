import unittest
from unittest.mock import patch

from Tool.combat_system import Buff, CombatEntity, CombatManager, Skill


def entity(name, *, hp=100, attack=20, defense=10, speed=100, entity_type="player", skills=None):
    return CombatEntity(name, {
        "name": name,
        "qixue": hp,
        "gongji": attack,
        "fangyu": defense,
        "sudu": speed,
        "baoji": 0,
        "baoshang": 0,
        "shanbi": 0,
        "mingzhong": 10000,
        "pofang": 0,
        "xixue": 0,
        "max_fali": 100,
        "entity_type": entity_type,
    }, skills or [])


def attack_skill(skill_id, name, element):
    return Skill(skill_id, name, 1, "enemy", 1, 0, element=element)


class P0CombatRulesTests(unittest.TestCase):
    def test_water_then_fire_triggers_vaporize(self):
        water = attack_skill(1, "Water Art", "WATER")
        fire = attack_skill(2, "Fire Art", "FIRE")
        manager = CombatManager(
            entity("Player", skills=[water, fire]),
            entity("Target", hp=1000, speed=1, entity_type="normal"),
        )

        # 固定命中随机数：本用例只验证五行反应，不应受闪避概率影响。
        with patch("Tool.combat_system.random.random", return_value=0.5):
            manager.resolve_round({"action_type": "SKILL", "skill_id": 1})
            self.assertTrue(manager.enemy.has_buff("wet"))
            hp_after_water = manager.enemy.hp
            manager.resolve_round({"action_type": "SKILL", "skill_id": 2})
        self.assertFalse(manager.enemy.has_buff("wet"))
        self.assertLess(manager.enemy.hp, hp_after_water)
        self.assertTrue(any(log["type"] == "reaction" for log in manager.combat_log))

    def test_defend_meditate_and_artifact_are_real_actions(self):
        manager = CombatManager(entity("Player"), entity("Target", hp=1000, speed=1, entity_type="normal"))
        manager.resolve_round({"action_type": "DEFEND"})
        self.assertTrue(manager.player.has_buff("defense_up"))

        manager.player.mana = 0
        manager.resolve_round({"action_type": "MEDITATE"})
        self.assertGreater(manager.player.mana, 0)
        valid, reason = manager.validate_player_action({"action_type": "ARTIFACT"})
        self.assertTrue(valid, reason)
        mana_before = manager.player.mana
        manager.resolve_round({"action_type": "ARTIFACT"})
        self.assertLess(manager.player.mana, mana_before)

    def test_boss_telegraph_can_be_broken_by_counter_element(self):
        metal = attack_skill(1, "Metal Art", "METAL")
        manager = CombatManager(
            entity("Player", skills=[metal]),
            entity("Boss", hp=100, speed=1, entity_type="boss"),
        )
        manager.enemy.hp = 70

        manager.resolve_round({"action_type": "SKILL", "skill_id": 1})
        log_types = [log["type"] for log in manager.combat_log]
        self.assertIn("boss_telegraph", log_types)
        self.assertIn("boss_break", log_types)
        self.assertFalse(manager.enemy.has_buff("defense_up"))

    def test_tianji_state_survives_snapshot(self):
        manager = CombatManager(entity("Player"), entity("Boss", hp=100, entity_type="boss"))
        manager.boss_tianji = {"triggered": ["first"], "intent": {"name": "Guard", "broken": False}}
        manager.dao_heart = {"value": 5, "cap": 5, "last_element": "WATER", "stored": True}
        restored = CombatManager.from_snapshot(manager.to_snapshot())
        self.assertEqual(restored.boss_tianji, manager.boss_tianji)
        self.assertEqual(restored.dao_heart, manager.dao_heart)

    def test_same_element_skills_accumulate_and_spend_dao_heart(self):
        water = attack_skill(1, "Water Art", "WATER")
        manager = CombatManager(
            entity("Player", skills=[water]),
            entity("Target", hp=1000, attack=1, speed=1, entity_type="normal"),
        )
        with patch("Tool.combat_system.random.random", return_value=0.5):
            for _ in range(3):
                manager.resolve_round({"action_type": "SKILL", "skill_id": 1})

        self.assertEqual(manager.dao_heart["value"], 3)
        manager.resolve_round({"action_type": "DAO_HEART_BURST"})
        self.assertEqual(manager.dao_heart["value"], 0)
        self.assertTrue(any(log["type"] == "dao_heart" for log in manager.combat_log))

    def test_element_reaction_is_limited_per_target_per_round_and_persists(self):
        fire = attack_skill(1, "Fire Art", "FIRE")
        manager = CombatManager(entity("Player", skills=[fire]), entity("Target", hp=1000, entity_type="normal"))
        manager.enemy.add_buff(Buff("wet", 0, 2))
        manager.reaction_targets_this_round.add("Target")
        manager._apply_elemental_effect(manager.player, manager.enemy, fire, {"is_dodge": False})
        self.assertTrue(manager.enemy.has_buff("wet"))
        self.assertTrue(any(log["type"] == "reaction_guard" for log in manager.combat_log))
        self.assertEqual(CombatManager.from_snapshot(manager.to_snapshot()).reaction_targets_this_round, {"Target"})

    def test_custom_boss_mechanic_controls_counter_and_drop_weight(self):
        water = attack_skill(1, "Water Art", "WATER")
        boss = entity("Boss", hp=100, speed=1, entity_type="boss")
        boss.role_data["boss_mechanics"] = [{
            "stage": "ward", "threshold": 0.8, "name": "自定义护体", "counter_element": "WATER",
            "counter_name": "水行", "effect": "defense_up", "value": 10, "duration": 1, "drop_weight": 27,
        }]
        manager = CombatManager(entity("Player", skills=[water]), boss)
        manager.enemy.hp = 70
        with patch("Tool.combat_system.random.random", return_value=0.5):
            manager.resolve_round({"action_type": "SKILL", "skill_id": 1})
        self.assertIn("ward", manager.boss_tianji["broken_stages"])
        self.assertEqual(manager.boss_tianji["reward_weight_bonus"], 27)


if __name__ == "__main__":
    unittest.main()
