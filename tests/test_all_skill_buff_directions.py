import unittest
from unittest.mock import patch

from Game_domain.role_special_catalog import iter_role_specs
from Game_main.g4_benyuan import BENYUAN_SKILL_SEED
from Tool.combat_system import (
    CombatEntity,
    CombatManager,
    ENEMY_BUFF_TYPES,
    SELF_BUFF_TYPES,
    Skill,
)


def entity(name, *, hp=10_000, entity_type="player", role_special=None):
    role_data = {
        "name": name,
        "qixue": hp,
        "gongji": 1_000,
        "fangyu": 100,
        "sudu": 100,
        "baoji": 0,
        "baoshang": 0,
        "shanbi": 0,
        "mingzhong": 100_000,
        "pofang": 0,
        "xixue": 0,
        "max_fali": 10_000,
        "entity_type": entity_type,
    }
    if role_special:
        role_data["role_special"] = role_special
    return CombatEntity(name, role_data, [])


class AllSkillBuffDirectionTests(unittest.TestCase):
    def test_every_supported_buff_type_uses_semantic_target_at_execution(self):
        self.assertFalse(SELF_BUFF_TYPES & ENEMY_BUFF_TYPES)
        for index, buff_type in enumerate(sorted(SELF_BUFF_TYPES), 1):
            with self.subTest(buff_type=buff_type):
                skill = Skill(
                    index, f"增益-{buff_type}", 2, "enemy", 0, 0,
                    buff_type=buff_type, buff_value=10, buff_duration=2,
                    buff_target=2,
                )
                # 模拟旧快照在构造后再次污染目标，执行器仍须纠正。
                skill.buff_target = 2
                player, enemy = entity("玩家"), entity("敌方", entity_type="normal")
                skill.execute(player, enemy)
                self.assertTrue(player.buffs)
                self.assertFalse(enemy.buffs)

        offset = len(SELF_BUFF_TYPES)
        for index, buff_type in enumerate(sorted(ENEMY_BUFF_TYPES), offset + 1):
            with self.subTest(buff_type=buff_type):
                skill = Skill(
                    index, f"减益-{buff_type}", 2, "self", 0, 0,
                    buff_type=buff_type, buff_value=10, buff_duration=2,
                    buff_target=1,
                )
                skill.buff_target = 1
                player, enemy = entity("玩家"), entity("敌方", entity_type="normal")
                skill.execute(player, enemy)
                self.assertFalse(player.buffs)
                self.assertTrue(enemy.buffs)

    def test_every_default_benyuan_skill_applies_to_expected_side(self):
        for data in BENYUAN_SKILL_SEED:
            with self.subTest(skill=data["skill_name"]):
                skill = Skill(
                    data["id"], data["skill_name"], data["skill_type"], "enemy",
                    data["value"], data["is_percent"], cooldown=data["cooldown"],
                    buff_type=data["buff_type"], buff_value=data["buff_value"],
                    buff_duration=data["buff_duration"], buff_target=data["buff_target"],
                )
                player, enemy = entity("玩家"), entity("敌方", entity_type="normal")
                with patch("Tool.combat_system.random.random", return_value=0.5):
                    skill.execute(player, enemy)
                expected = player if data["buff_target"] == 1 else enemy
                other = enemy if expected is player else player
                self.assertTrue(expected.buffs)
                self.assertFalse(other.buffs)

    def test_every_role_special_directional_effect_uses_correct_side(self):
        for spec in iter_role_specs():
            for ability in spec["abilities"]:
                if not ability.get("enabled", True):
                    continue
                effect = ability.get("effect") or {}
                effect_type = str(effect.get("type") or "").upper()
                special = {
                    "role_name": spec["role_name"],
                    "active": ability if ability["kind"] == "ACTIVE" else None,
                    "passive": ability if ability["kind"] == "PASSIVE" else None,
                }
                manager = CombatManager(
                    entity(spec["role_name"], role_special=special),
                    entity("敌方", entity_type="normal"),
                )
                with self.subTest(role=spec["role_name"], ability=ability["name"]):
                    manager.initialize()
                    if ability["kind"] == "PASSIVE":
                        if effect.get("trigger") == "LOW_HP":
                            manager.player.hp = manager.player.max_hp // 10
                            manager._apply_role_special_conditional_passive()
                        if effect_type == "ENEMY_ATTACK_DOWN":
                            self.assertTrue(manager.enemy.has_buff("attack_down"))
                            self.assertFalse(manager.player.has_buff("attack_down"))
                        elif effect_type in {"PLAYER_DEFENSE_UP", "PLAYER_SPEED_UP", "PLAYER_SHIELD"}:
                            self.assertTrue(manager.player.buffs)
                            self.assertFalse(manager.enemy.buffs)
                        continue

                    manager.player.hp = manager.player.max_hp // 2
                    manager.role_special["battle_intent"] = 5
                    manager.round = 1
                    hp_before = manager.player.hp
                    manager._execute_role_special()
                    for key, expected_buff in (
                        ("burn", "burning"),
                        ("resilience_down", "defense_down"),
                        ("healing_down", "healing_down"),
                        ("speed_down", "speed_down"),
                    ):
                        if effect.get(key):
                            self.assertTrue(manager.enemy.has_buff(expected_buff))
                            self.assertFalse(manager.player.has_buff(expected_buff))
                    if effect.get("shield_percent"):
                        self.assertTrue(manager.player.has_buff("shield"))
                        self.assertFalse(manager.enemy.has_buff("shield"))
                    if effect_type == "DAMAGE_HEAL":
                        self.assertGreaterEqual(manager.player.hp, hp_before)


if __name__ == "__main__":
    unittest.main()
