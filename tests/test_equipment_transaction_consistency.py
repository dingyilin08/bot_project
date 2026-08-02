import asyncio
import inspect
import unittest
from decimal import Decimal

from Game_domain.equipment_rules import (
    EQUIPMENT_ENHANCE_BONUS_PER_LEVEL,
    EQUIPMENT_SET_BONUS,
)
from Game_main.g7_equip import calc_equip_final_attrs
from Tool import tool_power


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, sql, params=None):
        return None

    async def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _Cursor(self.rows)


def _equipment_row(*, set_name="测试套装", level=0, quality="凡品", gongji=100):
    return (
        1, level, quality,
        gongji, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        set_name, "测试装备", "weapon",
    )


class EquipmentTransactionConsistencyTests(unittest.TestCase):
    def test_display_and_power_share_enhance_rule(self):
        attrs = calc_equip_final_attrs({
            "quality": "凡品", "level": 1,
            "base_gongji": 100, "base_fangyu": 0, "base_qixue": 0,
            "base_fali": 0, "base_sudu": 0, "base_baoji": 0,
            "base_baoshang": 0, "base_shanbi": 0, "base_mingzhong": 0,
            "base_pofang": 0, "base_xixue": 0,
        })
        self.assertEqual(0.10, EQUIPMENT_ENHANCE_BONUS_PER_LEVEL)
        self.assertEqual(110, attrs["gongji"])

        power, _ = asyncio.run(
            tool_power.calculate_equip_power(
                _Connection([_equipment_row(level=1)]), role_id=1, uid=1
            )
        )
        self.assertEqual(110, power)

    def test_display_and_power_share_set_rule(self):
        rows = [_equipment_row(), _equipment_row()]
        power, set_info = asyncio.run(
            tool_power.calculate_equip_power(_Connection(rows), role_id=1, uid=1)
        )
        self.assertEqual(0.20, EQUIPMENT_SET_BONUS[2])
        self.assertEqual(240, power)
        self.assertEqual(0.20, set_info["set_bonus"])

    def test_power_refresh_never_commits_caller_transaction(self):
        source = inspect.getsource(tool_power.update_role_power)
        self.assertNotIn("await conn.commit()", source)

    def test_mysql_decimal_attributes_can_be_used_in_power_formula(self):
        power = asyncio.run(tool_power.calculate_base_power({
            "gongji": Decimal("100.0"), "fangyu": Decimal("50.0"),
            "qixue": Decimal("0"), "fali": Decimal("0"), "sudu": Decimal("0"),
            "baoji": Decimal("0"), "baoshang": Decimal("0"),
            "shanbi": Decimal("0"), "mingzhong": Decimal("0"),
            "pofang": Decimal("0"), "xixue": Decimal("0"),
        }))
        self.assertEqual(140, power)

    def test_connection_context_explicitly_rolls_back_on_exception(self):
        from sql import mysql

        source = inspect.getsource(mysql.connect_mysql)
        self.assertIn("except BaseException", source)
        self.assertIn("await conn.rollback()", source)
