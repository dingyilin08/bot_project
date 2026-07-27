import unittest
from Game_main.g17_party_battle import normalize_action, resolve_party_round

class PartyBattleTests(unittest.TestCase):
    def test_actions_are_limited_to_public_choices(self):
        self.assertEqual(normalize_action('普攻'), 'ATTACK')
        self.assertEqual(normalize_action('防御'), 'DEFEND')
        self.assertIsNone(normalize_action('技能'))

    def test_same_snapshot_and_seed_resolve_identically(self):
        members = [{"uid": 1, "name": "甲", "hp": 100, "max_hp": 100, "attack": 30, "defense": 10, "speed": 20, "mana": 10, "max_mana": 10}, {"uid": 2, "name": "乙", "hp": 100, "max_hp": 100, "attack": 20, "defense": 10, "speed": 10, "mana": 10, "max_mana": 10}]
        enemy = {"name": "守关者", "hp": 120, "max_hp": 120, "attack": 20}
        first = resolve_party_round(members, {"1": "ATTACK", "2": "DEFEND"}, enemy, 'seed')
        second = resolve_party_round(members, {"1": "ATTACK", "2": "DEFEND"}, enemy, 'seed')
        self.assertEqual(first, second)
