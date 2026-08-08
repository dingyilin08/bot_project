import asyncio
from pathlib import Path
import unittest

from Game_domain.spirit_beast_rules import calculate_spirit_beast_power
from Game_main.g12_spirit_beast import (
    apply_beast_snapshot_to_entity,
    combat_bonus,
    origin_synergy,
    origin_synergy_effect,
    parse_beast_role_binding,
)
from Tool.combat_system import CombatEntity
from Tool.tool_power import calculate_role_spirit_beast_power
from output_main import jiance


class _BeastPowerCursor:
    def __init__(self, row):
        self.row = row
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, sql, params):
        self.executed.append((sql, params))

    async def fetchone(self):
        return self.row


class _BeastPowerConnection:
    def __init__(self, row):
        self.db_cursor = _BeastPowerCursor(row)

    def cursor(self):
        return self.db_cursor


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

    def test_role_binding_parser_keeps_optional_role_id(self):
        self.assertEqual(parse_beast_role_binding("12"), (12, None))
        self.assertEqual(parse_beast_role_binding("12 10014"), (12, 10014))
        self.assertEqual(parse_beast_role_binding("12-10014"), (12, 10014))
        with self.assertRaises(ValueError):
            parse_beast_role_binding("12 10014 3")

    def test_command_parser_preserves_two_binding_ids(self):
        self.assertEqual(
            asyncio.run(jiance("灵兽出战 12 10014")),
            ("灵兽出战", "12 10014"),
        )

    def test_beast_power_uses_aptitude_bond_and_contract(self):
        minimum = calculate_spirit_beast_power(
            {"aptitude": 60, "bond_exp": 0, "role": "STRIKER"}
        )
        maximum = calculate_spirit_beast_power(
            {"aptitude": 100, "bond_exp": 1000, "role": "HEALER"}
        )
        self.assertEqual(minimum["power"], 2100)
        self.assertEqual(maximum["power"], 4900)
        self.assertEqual(maximum["bond_level"], 10)

    def test_role_binding_migration_contains_unique_slot_and_power_column(self):
        project_root = Path(__file__).resolve().parents[1]
        sql = (project_root / "数据库源文件" / "p7_role_spirit_beast.sql").read_text(encoding="utf-8")
        self.assertIn("equipped_role_id", sql)
        self.assertIn("uk_spirit_beast_role", sql)
        self.assertIn("power_beast", sql)

    def test_role_power_reads_only_the_requested_role_binding(self):
        conn = _BeastPowerConnection((7, 80, 350, "玄甲龟", "GUARDIAN"))
        power, details = asyncio.run(calculate_role_spirit_beast_power(conn, 10014, 100007))
        self.assertEqual(power, 3260)
        self.assertEqual(details["name"], "玄甲龟")
        sql, params = conn.db_cursor.executed[0]
        self.assertIn("equipped_role_id", sql)
        self.assertEqual(params, (100007, 10014))
