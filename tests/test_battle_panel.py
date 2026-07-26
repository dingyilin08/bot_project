import unittest

from Game_domain.battle_models import BattleSession
from Game_main.g11_battle import _parse_action, render_battle_panel
from Tool.combat_system import CombatEntity, CombatManager, Skill


def entity(name, entity_type="player", skills=None):
    return CombatEntity(name, {
        "name": name, "qixue": 100, "gongji": 10, "fangyu": 10,
        "sudu": 10, "baoji": 0, "baoshang": 0, "shanbi": 0,
        "mingzhong": 10000, "pofang": 0, "xixue": 0, "max_fali": 100,
        "entity_type": entity_type,
    }, skills or [])


class BattlePanelTests(unittest.TestCase):
    def test_action_parser_supports_p0_actions_and_skills(self):
        self.assertEqual(_parse_action("调息"), ("MEDITATE", None))
        self.assertEqual(_parse_action("御器"), ("ARTIFACT", None))
        self.assertEqual(_parse_action("道心爆发"), ("DAO_HEART_BURST", None))
        self.assertEqual(_parse_action("技能-12"), ("SKILL", 12))

    def test_panel_exposes_commands_and_boss_counter(self):
        skill = Skill(12, "Water Art", 1, "enemy", 1, 0, element="WATER")
        manager = CombatManager(entity("Player", skills=[skill]), entity("Boss", "boss"))
        manager.initialize()
        manager.boss_tianji["intent"] = {
            "name": "Guard", "counter_name": "Metal", "counter_element": "METAL", "broken": False,
        }
        manager.dao_heart["value"] = 3
        session = BattleSession.new(owner_uid=1, battle_type="SOLO_DUNGEON", snapshot=manager.to_snapshot())

        panel = render_battle_panel(session)["content"]
        self.assertIn("战斗行动 调息", panel)
        self.assertIn("战斗行动 技能-12", panel)
        self.assertIn("战斗行动 道心爆发", panel)
        self.assertIn("Boss 天机", panel)


if __name__ == "__main__":
    unittest.main()
