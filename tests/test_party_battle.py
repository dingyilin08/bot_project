import asyncio
import json
from pathlib import Path
import unittest

from Game_main.g17_party_battle import (
    _actions_from_rows,
    _damage_modifiers,
    _finish_battle,
    _incoming_modifier,
    _resolve_round_if_ready,
    _session_fields,
    apply_basis_points,
    damage_after_defense,
    effective_attack,
    effective_defense,
    effective_speed,
    normalize_action,
    parse_action,
    resolve_party_round,
    round_should_resolve,
    select_front_target,
    upgrade_snapshot,
    validate_action_for_member,
)


def _member(uid, name, **changes):
    member = {
        "uid": uid,
        "name": name,
        "position": "前列",
        "hp": 100,
        "max_hp": 100,
        "attack": 30,
        "defense": 10,
        "speed": 20,
        "mana": 100,
        "max_mana": 100,
        "skills": [],
        "cooldowns": {},
        "buffs": [],
    }
    member.update(changes)
    return member


class _RewardCursor:
    def __init__(self):
        self.rowcount = 0
        self.reward_keys = set()
        self.currency_updates = []
        self.queries = []
        self.round_keys = set()

    async def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params))
        if "INSERT IGNORE INTO party_battle_reward" in normalized:
            key = (params[0], params[1], "LINGSHI")
            self.rowcount = 0 if key in self.reward_keys else 1
            self.reward_keys.add(key)
        elif "INSERT IGNORE INTO party_battle_round_log" in normalized:
            key = (params[0], params[1])
            self.rowcount = 0 if key in self.round_keys else 1
            self.round_keys.add(key)
        elif "UPDATE user_zt SET lingshi" in normalized:
            self.currency_updates.append(params)
            self.rowcount = 1
        else:
            self.rowcount = 1

class PartyBattleTests(unittest.TestCase):
    def test_actions_are_limited_to_public_choices(self):
        self.assertEqual(normalize_action('普攻'), 'ATTACK')
        self.assertEqual(normalize_action('防御'), 'DEFEND')
        self.assertEqual(normalize_action('技能 2'), 'SKILL')
        self.assertEqual(parse_action('技能 2')["payload"], {"skill_slot": 2})
        self.assertIsNone(normalize_action('技能'))

    def test_same_snapshot_and_seed_resolve_identically(self):
        members = [{"uid": 1, "name": "甲", "hp": 100, "max_hp": 100, "attack": 30, "defense": 10, "speed": 20, "mana": 10, "max_mana": 10}, {"uid": 2, "name": "乙", "hp": 100, "max_hp": 100, "attack": 20, "defense": 10, "speed": 10, "mana": 10, "max_mana": 10}]
        enemy = {"name": "守关者", "hp": 120, "max_hp": 120, "attack": 20}
        first = resolve_party_round(members, {"1": "ATTACK", "2": "DEFEND"}, enemy, 'seed')
        second = resolve_party_round(members, {"1": "ATTACK", "2": "DEFEND"}, enemy, 'seed')
        self.assertEqual(first, second)

    def test_round_timeout_uses_default_defense_for_missing_members(self):
        alive = [{"uid": 1}, {"uid": 2}]
        self.assertFalse(round_should_resolve({"1": "ATTACK"}, alive, False))
        self.assertTrue(round_should_resolve({"1": "ATTACK"}, alive, True))

    def test_dead_or_unknown_action_does_not_count_as_alive_submission(self):
        alive = [_member(1, "甲"), _member(2, "乙")]
        actions = {"1": "ATTACK", "999": "ATTACK"}
        self.assertFalse(round_should_resolve(actions, alive, False))
        self.assertTrue(round_should_resolve({**actions, "2": "DEFEND"}, alive, False))

    def test_formation_basis_points_and_stat_cap_are_exact(self):
        self.assertEqual(apply_basis_points(101, 10800), 109)
        member = _member(
            1,
            "甲",
            attack=100,
            defense=100,
            speed=100,
            side="PLAYER",
            pve_attack_bp=999999,
            pve_defense_bp=300,
            pve_speed_bp=300,
        )
        self.assertEqual(effective_attack(member), 110)
        self.assertEqual(effective_defense(member, "玄武"), 111)
        self.assertEqual(effective_speed(member, "流云"), 111)
        self.assertEqual(damage_after_defense(100, 200, random_factor_bp=10000), 80)
        self.assertEqual(_damage_modifiers({"position": "前列", "party_damage_bp": 0}, "锋矢"), 10800)
        self.assertEqual(_damage_modifiers({"position": "后列", "party_damage_bp": 0}, "锋矢"), 10000)
        self.assertEqual(_incoming_modifier({"position": "前列"}, "锋矢"), 10500)

    def test_front_row_must_fall_before_back_row_can_be_selected(self):
        front = {"id": "front", "position": "前列", "hp": 1, "max_hp": 100}
        back = {"id": "back", "position": "后列", "hp": 1, "max_hp": 100}
        self.assertIs(select_front_target([front, back], "back"), front)
        front["hp"] = 0
        self.assertIs(select_front_target([front, back], "back"), back)

    def test_skill_rejects_missing_mana_and_cooldown(self):
        skill = {
            "id": 7,
            "slot": 1,
            "name": "回春",
            "skill_type": 3,
            "value": 50,
            "is_percent": 0,
            "mana_cost": 30,
            "cooldown": 2,
        }
        member = _member(1, "甲", mana=20, skills=[skill])
        action = {"type": "SKILL", "payload": {"skill_slot": 1}}
        self.assertIn("法力不足", validate_action_for_member(member, action))
        member["mana"] = 100
        member["cooldowns"] = {"7": 2}
        self.assertIn("冷却中", validate_action_for_member(member, action))

    def test_heal_caps_at_max_hp_and_flowing_cloud_reduces_amount(self):
        heal_skill = {
            "id": 7,
            "slot": 1,
            "name": "回春",
            "skill_type": 3,
            "value": 50,
            "is_percent": 0,
            "mana_cost": 20,
            "cooldown": 2,
            "buff_target": 1,
        }
        healer = _member(1, "医者", position="前列", skills=[heal_skill], speed=30)
        ally = _member(2, "伤者", position="后列", hp=10, speed=20)
        enemy = {
            "id": "enemy",
            "name": "守关者",
            "position": "前列",
            "hp": 1000,
            "max_hp": 1000,
            "attack": 1,
            "defense": 0,
            "speed": 1,
        }
        members, _, _ = resolve_party_round(
            [healer, ally],
            {"1": {"type": "SKILL", "payload": {"skill_slot": 1}}, "2": "DEFEND"},
            [enemy],
            "heal",
            "流云",
        )
        healed = next(item for item in members if item["uid"] == 2)
        caster = next(item for item in members if item["uid"] == 1)
        self.assertEqual(healed["hp"], 57)  # floor(50 * 95%) = 47
        self.assertEqual(caster["mana"], 80)
        self.assertEqual(caster["cooldowns"], {"7": 2})

    def test_enemy_and_players_share_speed_order_with_stable_ids(self):
        member = _member(1, "慢修", speed=10)
        enemy = {
            "id": "fast",
            "name": "快敌",
            "hp": 100,
            "max_hp": 100,
            "attack": 10,
            "defense": 0,
            "speed": 20,
            "position": "前列",
        }
        _, _, logs = resolve_party_round([member], {"1": "ATTACK"}, [enemy], "speed", "锋矢")
        self.assertTrue(logs[0].startswith("快敌攻击"))

    def test_v1_snapshot_is_read_without_mutating_original_shape(self):
        old = {
            "members": [_member(1, "旧友")],
            "enemy": {"name": "旧敌", "hp": 10, "max_hp": 10, "attack": 1, "formation": "玄武"},
        }
        upgraded = upgrade_snapshot(old)
        self.assertEqual(upgraded["schema_version"], 2)
        self.assertEqual(upgraded["source_schema_version"], 1)
        self.assertEqual(upgraded["formation"], "玄武")
        self.assertEqual(upgraded["enemies"][0]["name"], "旧敌")
        self.assertEqual(upgrade_snapshot(upgraded)["source_schema_version"], 1)
        self.assertIn("enemy", old)

    def test_seven_session_columns_are_unpacked_explicitly(self):
        fields = _session_fields(("s", 9, 3, "ACTIVE", "{}", None, 0))
        self.assertEqual(fields["round_no"], 3)
        with self.assertRaises(ValueError):
            _session_fields(("s", 9, 3, "ACTIVE", "{}"))

    def test_action_payload_reader_supports_old_null_rows(self):
        actions = _actions_from_rows(((1, "SKILL", '{"skill_slot": 2}'), (2, "DEFEND", None)))
        self.assertEqual(actions["1"]["payload"]["skill_slot"], 2)
        self.assertEqual(actions["2"]["payload"], {})

    def test_reward_ledger_prevents_duplicate_currency_grant(self):
        cursor = _RewardCursor()
        snapshot = {"members": [_member(1, "甲"), _member(2, "乙")], "enemies": []}
        asyncio.run(_finish_battle(cursor, "session", 5, "COMPLETED", snapshot, []))
        asyncio.run(_finish_battle(cursor, "session", 5, "COMPLETED", snapshot, []))
        self.assertEqual(len(cursor.currency_updates), 2)
        self.assertTrue(any("UPDATE party SET state = 'LOBBY'" in query for query, _ in cursor.queries))
        self.assertTrue(any("UPDATE party_member SET ready = 0" in query for query, _ in cursor.queries))

    def test_replayed_resolved_round_cannot_duplicate_reward(self):
        cursor = _RewardCursor()
        member = _member(1, "甲", attack=9999, speed=99)
        snapshot = {
            "schema_version": 2,
            "rule_version": "party-pve.v2",
            "formation": "锋矢",
            "members": [member],
            "enemies": [{
                "id": "front",
                "name": "纸人",
                "position": "前列",
                "hp": 1,
                "max_hp": 1,
                "attack": 1,
                "defense": 0,
                "speed": 0,
            }],
        }
        session = ("stable", 9, 1, "ACTIVE", json.dumps(snapshot, ensure_ascii=False), None, 0)
        actions = {"1": {"type": "ATTACK", "payload": {}}}
        asyncio.run(_resolve_round_if_ready(None, cursor, session, actions))
        asyncio.run(_resolve_round_if_ready(None, cursor, session, actions))
        self.assertEqual(cursor.round_keys, {("stable", 1)})
        self.assertEqual(len(cursor.currency_updates), 1)

    def test_migration_has_active_unique_and_idempotent_ledgers(self):
        sql = (Path(__file__).parents[1] / "数据库源文件" / "p3_party_battle_v2.sql").read_text(encoding="utf-8")
        self.assertIn("uk_party_battle_active_party", sql)
        self.assertIn("uk_party_battle_round_result", sql)
        self.assertIn("uk_party_battle_reward", sql)
        self.assertIn("mana_cost", sql)
