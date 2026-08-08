import unittest
from unittest.mock import patch

from Game_main import g7_equip
from Tool.combat_system import CombatEntity, Skill


class _SmeltCursor:
    def __init__(self, jade_count=1):
        self._row = None
        self._rows = []
        self.rowcount = 0
        self.lastrowid = 901
        self.jade_count = jade_count
        self.jade_deductions = 0
        self.created = False

    async def execute(self, sql, params=None):
        statement = " ".join(sql.split())
        self.rowcount = 0
        if statement.startswith("SELECT ue.id, ue.equip_id, ue.quality"):
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


class EquipmentSmeltingTests(unittest.IsolatedAsyncioTestCase):
    def test_parser_requires_three_distinct_positive_ids(self):
        self.assertEqual(g7_equip.parse_smelt_equip_ids("1-2-3"), [1, 2, 3])
        for value in ("1-2", "1-1-2", "1-0-2", "a-2-3"):
            with self.subTest(value=value):
                self.assertIsNone(g7_equip.parse_smelt_equip_ids(value))

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
            result = await g7_equip.directional_smelt_equip.__wrapped__(7, "", "武器 11-12-13")
        finally:
            g7_equip.connect_mysql = original_connect
        self.assertIn("需要1个定枢玉", result["content"])
        self.assertFalse(cursor.created)
        self.assertEqual(conn.commits, 0)


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
