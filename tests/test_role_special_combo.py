# -*- coding: utf-8 -*-

import json
import unittest
from unittest.mock import AsyncMock, patch

import aiomysql

import Game_domain.role_special_service as service
from Game_domain.role_special_combo_rules import (
    COMBO_RULE_VERSION,
    apply_combo_to_battle_special,
    build_combo_battle_snapshot,
    sanitize_combo_effect,
)
from Game_main.g22_role_special import _parse_combo_action, render_combo_bag
from Tool.combat_system import CombatEntity, CombatManager


def entity(name, hp=1000, entity_type="player", role_special=None):
    role_data = {
        "qixue": hp,
        "gongji": 1000,
        "fangyu": 100,
        "sudu": 100,
        "baoji": 0,
        "baoshang": 15000,
        "shanbi": 0,
        "mingzhong": 10000,
        "pofang": 0,
        "xixue": 0,
        "max_fali": 100,
        "entity_type": entity_type,
    }
    if role_special:
        role_data["role_special"] = role_special
    return CombatEntity(name, role_data, [])


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class BaseCursor:
    def __init__(self):
        self.statements = []
        self.rowcount = 0
        self._fetchone = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetchone(self):
        return self._fetchone

    async def fetchall(self):
        return []


class EquipCursor(BaseCursor):
    def __init__(self, *, equipped_slot=None, status="ACTIVE", exists=True):
        super().__init__()
        self.equipped_slot = equipped_slot
        self.status = status
        self.exists = exists

    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.statements.append((compact, params))
        if compact.startswith("SELECT id,custom_name,combo_type"):
            self._fetchone = None if not self.exists else (
                12,
                "焚天三玄变",
                "异火融合",
                1.2,
                json.dumps({"type": "DAMAGE", "defense_ignore": 8}),
                self.equipped_slot,
                self.status,
            )
            self.rowcount = 1 if self.exists else 0
        elif compact.startswith("UPDATE user_role_special_combo SET equipped_slot=NULL"):
            self._fetchone = None
            self.rowcount = 1
        elif compact.startswith("UPDATE user_role_special_combo SET equipped_slot=1"):
            self._fetchone = None
            self.rowcount = 1
        else:
            raise AssertionError(f"未处理的组合装备SQL：{compact}")


class LoadoutCursor(BaseCursor):
    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.statements.append((compact, params))
        if compact.startswith("SELECT p.growth_stage"):
            self._fetchone = (
                5,
                9,
                "帝炎",
                2.0,
                json.dumps({"type": "DAMAGE"}),
                4,
                "骨灵冷火",
                json.dumps({"type": "ENEMY_ATTACK_DOWN", "value": 10}),
                "{}",
            )
        elif compact.startswith("SELECT id,custom_name,combo_type"):
            self._fetchone = (
                12,
                "焚天三玄变",
                "异火融合",
                1.25,
                json.dumps({"type": "DAMAGE", "defense_ignore": 8}),
            )
        else:
            raise AssertionError(f"未处理的组合快照SQL：{compact}")


class SchemaCursor(BaseCursor):
    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.statements.append((compact, params))
        if compact.startswith("SELECT COUNT(*) FROM information_schema"):
            self._fetchone = (0,)
        elif compact.startswith("ALTER TABLE user_role_special_combo"):
            self._fetchone = None
        else:
            raise AssertionError(f"未处理的兼容SQL：{compact}")


class LegacyBattleCursor(BaseCursor):
    async def execute(self, sql, params=None):
        raise aiomysql.OperationalError(1054, "Unknown column 'equipped_slot'")


class RoleSpecialComboRuleTests(unittest.TestCase):
    def test_effect_allowlist_clamps_values_and_drops_unknown_fields(self):
        effect = sanitize_combo_effect({
            "type": "DAMAGE_HEAL",
            "defense_ignore": 99,
            "heal_percent": 99,
            "clear_dot": 1,
            "script": "DROP TABLE player",
        })
        self.assertEqual(effect["mode"], "ACTIVE_OVERRIDE")
        self.assertEqual(effect["defense_ignore"], 15)
        self.assertEqual(effect["heal_percent"], 10)
        self.assertEqual(effect["type"], "DAMAGE_HEAL")
        self.assertIn("COMBO_DEFENSE_PIERCE", effect["effect_codes"])
        self.assertNotIn("script", effect)

    def test_supported_inherited_passive_becomes_single_trigger_override(self):
        effect = sanitize_combo_effect({
            "type": "PLAYER_DEFENSE_UP",
            "source_kind": "PASSIVE",
            "value": 99,
            "duration": 99,
        })
        self.assertEqual(effect["mode"], "PASSIVE_OVERRIDE")
        self.assertEqual(effect["effect_code"], "COMBO_PLAYER_DEFENSE_UP")
        self.assertEqual(effect["value"], 15)
        self.assertEqual(effect["duration"], 3)

    def test_snapshot_caps_multiplier_and_has_machine_rule_version(self):
        snapshot = build_combo_battle_snapshot({
            "id": 7,
            "name": "越界组合",
            "combo_type": "异火融合",
            "multiplier": 999,
            "effect": {"type": "DAMAGE", "defense_ignore": 8},
        })
        self.assertEqual(snapshot["rule_version"], COMBO_RULE_VERSION)
        self.assertEqual(snapshot["multiplier_bp"], 20000)
        self.assertEqual(snapshot["multiplier"], 2.0)
        self.assertEqual(snapshot["max_uses"], 1)

    def test_active_combo_reuses_real_once_per_battle_executor_and_restores(self):
        base = {
            "role_id": 100,
            "role_name": "萧炎",
            "active": {"id": 9, "name": "帝炎", "multiplier": 2.0, "effect": {"type": "DAMAGE"}},
            "passive": None,
        }
        combo = build_combo_battle_snapshot({
            "id": 12,
            "name": "焚天三玄变",
            "combo_type": "异火融合",
            "multiplier": 1.25,
            "effect": {"type": "DAMAGE", "defense_ignore": 8},
        })
        special = apply_combo_to_battle_special(base, combo)
        self.assertEqual(special["base_active"]["name"], "帝炎")
        self.assertEqual(special["active"]["combo_id"], 12)

        manager = CombatManager(
            entity("萧炎", role_special=special),
            entity("Boss", hp=1000, entity_type="boss"),
        )
        manager.player.speed = 1000
        manager.enemy.speed = 1
        self.assertTrue(manager.validate_player_action({"action_type": "SPECIAL"})[0])
        manager.resolve_round({"action_type": "SPECIAL"})
        self.assertTrue(manager.role_special["used"])
        self.assertEqual(manager.role_special["events"][0]["id"], -12)
        self.assertFalse(manager.validate_player_action({"action_type": "SPECIAL"})[0])
        restored = CombatManager.from_snapshot(manager.to_snapshot())
        self.assertEqual(restored.role_special["combo"]["id"], 12)
        self.assertTrue(restored.role_special["used"])

    def test_passive_combo_reuses_real_battle_start_executor(self):
        combo = build_combo_battle_snapshot({
            "id": 13,
            "name": "玄甲合道",
            "combo_type": "本源合道",
            "multiplier": 1.0,
            "effect": {
                "type": "PLAYER_DEFENSE_UP",
                "source_kind": "PASSIVE",
                "value": 12,
                "duration": 2,
            },
        })
        special = apply_combo_to_battle_special(
            {"role_id": 101, "role_name": "王林", "active": None, "passive": None},
            combo,
        )
        manager = CombatManager(entity("王林", role_special=special), entity("敌人"))
        manager.initialize()
        self.assertTrue(manager.role_special["passive_triggered"])
        self.assertTrue(manager.player.has_buff("defense_up"))

    def test_reused_command_parser_supports_bag_equip_and_create(self):
        self.assertEqual(_parse_combo_action("背包"), ("LIST", None))
        self.assertEqual(_parse_combo_action("装备-12"), ("EQUIP", 12))
        self.assertEqual(_parse_combo_action("1-2-3-焚天"), ("CREATE", "1-2-3-焚天"))

    def test_combo_bag_renders_one_click_equip_button(self):
        result = render_combo_bag({
            "role_name": "萧炎",
            "items": [{
                "id": 12,
                "name": "焚天三玄变",
                "combo_type": "异火融合",
                "multiplier": 1.25,
                "effect": sanitize_combo_effect({"type": "DAMAGE", "defense_ignore": 8}),
                "equipped": False,
            }],
        })
        self.assertIn("专属组合 装备-12", result["content"])
        self.assertIn("COMBO_DEFENSE_PIERCE", result["content"])


class RoleSpecialComboTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_switch_clears_previous_then_equips_one_in_same_transaction(self):
        cursor = EquipCursor()
        connection = FakeConnection(cursor)
        with (
            patch.object(service, "connect_mysql", lambda: connection),
            patch.object(service, "ensure_combo_equipment_schema", AsyncMock()),
            patch.object(service, "_active_role", AsyncMock(return_value=(100, 1, "萧炎"))),
        ):
            result = await service.equip_combo(7, 12)

        updates = [statement for statement in cursor.statements if statement[0].startswith("UPDATE")]
        self.assertEqual(len(updates), 2)
        self.assertIn("equipped_slot=NULL", updates[0][0])
        self.assertIn("equipped_slot=1", updates[1][0])
        self.assertEqual(updates[0][1], (7, 100))
        self.assertEqual(updates[1][1], (12, 7, 100))
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertFalse(result["idempotent"])

    async def test_equipping_same_combo_is_idempotent_without_updates(self):
        cursor = EquipCursor(equipped_slot=1)
        connection = FakeConnection(cursor)
        with (
            patch.object(service, "connect_mysql", lambda: connection),
            patch.object(service, "ensure_combo_equipment_schema", AsyncMock()),
            patch.object(service, "_active_role", AsyncMock(return_value=(100, 1, "萧炎"))),
        ):
            result = await service.equip_combo(7, 12)

        self.assertTrue(result["idempotent"])
        self.assertFalse(any(sql.startswith("UPDATE") for sql, _ in cursor.statements))
        self.assertEqual(connection.commits, 1)

    async def test_cross_role_or_missing_combo_rolls_back_without_clearing_current(self):
        cursor = EquipCursor(exists=False)
        connection = FakeConnection(cursor)
        with (
            patch.object(service, "connect_mysql", lambda: connection),
            patch.object(service, "ensure_combo_equipment_schema", AsyncMock()),
            patch.object(service, "_active_role", AsyncMock(return_value=(100, 1, "萧炎"))),
        ):
            with self.assertRaisesRegex(service.RoleSpecialError, "不属于当前出战角色"):
                await service.equip_combo(7, 999)

        self.assertEqual(connection.rollbacks, 1)
        self.assertFalse(any(sql.startswith("UPDATE") for sql, _ in cursor.statements))

    async def test_sealed_combo_cannot_replace_current_equipment(self):
        cursor = EquipCursor(status="SEALED")
        connection = FakeConnection(cursor)
        with (
            patch.object(service, "connect_mysql", lambda: connection),
            patch.object(service, "ensure_combo_equipment_schema", AsyncMock()),
            patch.object(service, "_active_role", AsyncMock(return_value=(100, 1, "萧炎"))),
        ):
            with self.assertRaisesRegex(service.RoleSpecialError, "已封存"):
                await service.equip_combo(7, 12)

        self.assertEqual(connection.rollbacks, 1)
        self.assertFalse(any(sql.startswith("UPDATE") for sql, _ in cursor.statements))

    async def test_loadout_queries_only_equipped_combo_and_overrides_active_snapshot(self):
        cursor = LoadoutCursor()
        with patch.object(service, "ensure_combo_equipment_schema", AsyncMock()):
            special = await service.load_battle_special(cursor, 7, 100, "萧炎")

        combo_sql = cursor.statements[-1][0]
        self.assertIn("equipped_slot=1", combo_sql)
        self.assertIn("LIMIT 1", combo_sql)
        self.assertEqual(special["combo"]["id"], 12)
        self.assertEqual(special["active"]["combo_id"], 12)
        self.assertEqual(special["base_active"]["name"], "帝炎")

    async def test_legacy_table_does_not_run_ddl_inside_battle_transaction(self):
        self.assertIsNone(await service.load_equipped_combo(LegacyBattleCursor(), 7, 100))

    async def test_old_combo_table_gets_nullable_slot_and_unique_constraint(self):
        cursor = SchemaCursor()
        with patch.object(service, "_COMBO_EQUIPMENT_SCHEMA_READY", False):
            await service.ensure_combo_equipment_schema(cursor)

        alters = [sql for sql, _ in cursor.statements if sql.startswith("ALTER TABLE")]
        self.assertEqual(len(alters), 2)
        self.assertTrue(any("ADD COLUMN equipped_slot" in sql for sql in alters))
        self.assertTrue(any("ADD UNIQUE KEY uk_role_combo_equipped" in sql for sql in alters))


if __name__ == "__main__":
    unittest.main()
