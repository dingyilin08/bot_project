import unittest

from Tool.combat_system import CombatEntity, CombatManager, Skill


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
        restored = CombatManager.from_snapshot(manager.to_snapshot())
        self.assertEqual(restored.boss_tianji, manager.boss_tianji)


if __name__ == "__main__":
    unittest.main()
