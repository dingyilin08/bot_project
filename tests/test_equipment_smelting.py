import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from Game_main import g7_equip
from Tool.combat_system import CombatEntity, Skill
from output_main import jiance


class _SmeltCursor:
    def __init__(self, jade_count=1):
        self._row = None
        self._rows = []
        self.rowcount = 0
        self.lastrowid = 901
        self.jade_count = jade_count
        self.jade_deductions = 0
        self.created = False
        self.furnace_cleared = False

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        self.rowcount = 0
        if statement.startswith("SELECT equip_id_1, equip_id_2, equip_id_3"):
            self._row = (11, 12, 13)
        elif statement.startswith("SELECT ue.id, ue.equip_id, ue.quality"):
            self._rows = [
                (11, 1, "精品", 0, 1, 1),
                (12, 2, "精品", 0, 1, 1),
                (13, 3, "精品", 0, 1, 1),
            ]
        elif statement.startswith("SELECT id, name, set_name, part, min_level FROM data_equip"):
            self._row = (1, "坊市玄铁·斩", "坊市玄铁套", "weapon", 1)
        elif statement.startswith("UPDATE user_item SET item_num = item_num - 1"):
            self.rowcount = 1 if self.jade_count else 0
            self.jade_deductions += self.rowcount
        elif statement.startswith("DELETE FROM user_item"):
            self.rowcount = 1
        elif statement.startswith("INSERT INTO user_equip"):
            self.created = True
            self.rowcount = 1
        elif statement.startswith("DELETE FROM user_equip"):
            self.rowcount = 3
        elif statement.startswith("DELETE FROM user_directional_smelt"):
            self.furnace_cleared = True
            self.rowcount = 1
        else:
            raise AssertionError(f"未预期的熔炼 SQL：{statement}")

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return self._rows


class _CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    async def __aenter__(self):
        return self.cursor

    async def __aexit__(self, *_args):
        return False


class _SmeltConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def cursor(self):
        return _CursorContext(self.cursor_value)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _FurnaceCursor:
    def __init__(self):
        self.state = [None, None, None]
        self._row = None
        self._rows = []
        self.rowcount = 0
        self.equipment = {
            489: (489, "玄铁戒", "精品", 0),
            934: (934, "青玉佩", "精品", 0),
            958: (958, "星纹链", "精品", 0),
        }

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        self._row = None
        self._rows = []
        self.rowcount = 0
        if statement.startswith("INSERT INTO user_directional_smelt"):
            self.rowcount = 1
        elif statement.startswith("SELECT equip_id_1, equip_id_2, equip_id_3"):
            self._row = tuple(self.state)
        elif statement.startswith("SELECT ue.id, de.name, ue.quality, ue.is_equipped"):
            self._row = self.equipment.get(int(params[1]))
        elif statement.startswith("UPDATE user_directional_smelt SET equip_id_"):
            slot_no = int(statement.split("equip_id_", 1)[1][0])
            self.state[slot_no - 1] = int(params[0])
            self.rowcount = 1
        elif statement.startswith("SELECT ue.id, de.name, ue.quality"):
            self._rows = [self.equipment[int(equip_id)][:3] for equip_id in params[1:]]
        else:
            raise AssertionError(f"未预期的定向熔炉 SQL：{statement}")

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return self._rows


class EquipmentSmeltingTests(unittest.IsolatedAsyncioTestCase):
    def test_parser_requires_three_distinct_positive_ids(self):
        self.assertEqual(g7_equip.parse_smelt_equip_ids("1-2-3"), [1, 2, 3])
        for value in ("1-2", "1-1-2", "1-0-2", "a-2-3"):
            with self.subTest(value=value):
                self.assertIsNone(g7_equip.parse_smelt_equip_ids(value))

    def test_directional_commands_survive_global_normalization(self):
        cases = {
            "定向熔炉": ("定向熔炉", ""),
            "定向放置1-489": ("定向放置1", "-489"),
            "定向放置2-934": ("定向放置2", "-934"),
            "定向放置3-958": ("定向放置3", "-958"),
            "部位定向 饰品": ("部位定向", "饰品"),
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(asyncio.run(jiance(command)), expected)

    def test_directional_id_parser_accepts_hyphen_suffix(self):
        self.assertEqual(g7_equip.parse_directional_equip_id("-489"), 489)
        self.assertEqual(g7_equip.parse_directional_equip_id(" 489 "), 489)
        for value in ("", "-", "0", "--1", "489-934"):
            with self.subTest(value=value):
                self.assertIsNone(g7_equip.parse_directional_equip_id(value))

    def test_directional_furnace_panel_exposes_three_slots_and_parts(self):
        empty = g7_equip._directional_furnace_markdown((None, None, None))["content"]
        for slot in (1, 2, 3):
            self.assertIn(f"定向放置{slot}-装备编号", empty)
        full = g7_equip._directional_furnace_markdown(
            (489, 934, 958),
            {
                489: {"name": "玄铁戒", "quality": "精品"},
                934: {"name": "青玉佩", "quality": "精品"},
                958: {"name": "星纹链", "quality": "精品"},
            },
        )["content"]
        self.assertIn("部位定向 饰品", full)
        self.assertIn("[489] 玄铁戒", full)

    async def test_open_and_place_directional_furnace_material(self):
        cursor = _FurnaceCursor()
        conn = _SmeltConnection(cursor)
        original_connect = g7_equip.connect_mysql
        g7_equip.connect_mysql = lambda: conn
        try:
            opened = await g7_equip.open_directional_smelt_furnace.__wrapped__(7, "")
            placed = await g7_equip.place_directional_smelt_equip.__wrapped__(
                7, "", "1", "-489"
            )
        finally:
            g7_equip.connect_mysql = original_connect
        self.assertIn("槽位1：未放置", opened["content"])
        self.assertIn("装备 [489] 已放入槽位1", placed["content"])
        self.assertIn("[489] 玄铁戒", placed["content"])
        self.assertEqual(cursor.state, [489, None, None])
        self.assertEqual(conn.commits, 2)

    async def test_regular_smelt_creates_same_quality_item_without_jade(self):
        cursor = _SmeltCursor()
        conn = _SmeltConnection(cursor)
        original_connect = g7_equip.connect_mysql
        original_choice = g7_equip.random.choice
        g7_equip.connect_mysql = lambda: conn
        g7_equip.random.choice = lambda _parts: "weapon"
        try:
            result = await g7_equip.smelt_equip.__wrapped__(7, "", "11-12-13")
        finally:
            g7_equip.connect_mysql = original_connect
            g7_equip.random.choice = original_choice
        self.assertIn("装备熔炼成功", result["content"])
        self.assertIn("精品", result["content"])
        self.assertTrue(cursor.created)
        self.assertEqual(cursor.jade_deductions, 0)
        self.assertEqual(conn.commits, 1)

    async def test_directional_smelt_requires_jade_before_consuming_equipment(self):
        cursor = _SmeltCursor(jade_count=0)
        conn = _SmeltConnection(cursor)
        original_connect = g7_equip.connect_mysql
        g7_equip.connect_mysql = lambda: conn
        try:
            result = await g7_equip.target_directional_smelt_part.__wrapped__(7, "", "武器")
        finally:
            g7_equip.connect_mysql = original_connect
        self.assertIn("需要1个定枢玉", result["content"])
        self.assertFalse(cursor.created)
        self.assertFalse(cursor.furnace_cleared)
        self.assertEqual(conn.commits, 0)

    async def test_directional_smelt_clears_furnace_only_after_success(self):
        cursor = _SmeltCursor()
        conn = _SmeltConnection(cursor)
        original_connect = g7_equip.connect_mysql
        g7_equip.connect_mysql = lambda: conn
        try:
            result = await g7_equip.target_directional_smelt_part.__wrapped__(7, "", "饰品")
        finally:
            g7_equip.connect_mysql = original_connect
        self.assertIn("定向熔炼成功", result["content"])
        self.assertTrue(cursor.created)
        self.assertTrue(cursor.furnace_cleared)
        self.assertEqual(cursor.jade_deductions, 1)
        self.assertEqual(conn.commits, 1)

    def test_directional_furnace_migration_is_idempotent(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "数据库源文件"
            / "p9_directional_smelt_furnace.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS user_directional_smelt", migration)
        self.assertIn("PRIMARY KEY (uid)", migration)


class FusedSkillCombatTests(unittest.TestCase):
    def test_fused_skill_deals_damage_applies_buff_and_consumes_mana(self):
        role = {
            "name": "玩家", "qixue": 1000, "gongji": 500, "fangyu": 50, "sudu": 100,
            "baoji": 0, "baoshang": 0, "shanbi": 0, "mingzhong": 100000,
            "pofang": 0, "xixue": 0, "max_fali": 100,
        }
        attacker = CombatEntity("玩家", role, [])
        defender = CombatEntity("敌人", {**role, "name": "敌人", "max_fali": 0}, [])
        skill = Skill(999, "融合剑诀", 1, "enemy", 300, 0, mana_cost=25, buff_type="defense_down", buff_value=30, buff_duration=2, buff_target=2)
        with patch("Tool.combat_system.random.random", return_value=0), patch("Tool.combat_system.random.uniform", return_value=1):
            result = skill.execute(attacker, defender)
        self.assertGreater(result["damage"], 0)
        self.assertEqual(attacker.mana, 75)
        self.assertTrue(defender.has_buff("defense_down"))
