import asyncio
import unittest

from Game_main import g7_equip
from output_main import jiance


class _BatchSellCursor:
    def __init__(self, rows=None, has_yefan=True, delete_count=None, balance=1000):
        self.rows = list(rows or [])
        self.has_yefan = has_yefan
        self.delete_count = len(self.rows) if delete_count is None else delete_count
        self.balance = balance
        self.rowcount = 0
        self._row = None
        self.deleted_ids = []
        self.selection_sql = ''

    async def execute(self, sql, params=None):
        statement = ' '.join(sql.split())
        self.rowcount = 0
        self._row = None
        if statement.startswith('SELECT ue.id, ue.quality'):
            self.selection_sql = statement
        elif statement.startswith('SELECT 1 FROM user_role'):
            self._row = (1,) if self.has_yefan else None
        elif statement.startswith('DELETE FROM user_equip'):
            self.deleted_ids = list(params[1:1 + len(self.rows)])
            self.rowcount = self.delete_count
        elif statement.startswith('UPDATE user_zt SET lingshi'):
            self.balance += int(params[0])
            self.rowcount = 1
        elif statement.startswith('SELECT lingshi FROM user_zt'):
            self._row = (self.balance,)
        else:
            raise AssertionError(f'未预期的一键出售 SQL：{statement}')

    async def fetchall(self):
        return self.rows

    async def fetchone(self):
        return self._row


class _CursorContext:
    def __init__(self, cursor):
        self.cursor_value = cursor

    async def __aenter__(self):
        return self.cursor_value

    async def __aexit__(self, *_args):
        return False


class _BatchSellConnection:
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


class EquipmentBatchSellTests(unittest.IsolatedAsyncioTestCase):
    def test_command_parser_accepts_default_and_quality_scope(self):
        self.assertEqual(asyncio.run(jiance('一键出售')), ('一键出售', ''))
        self.assertEqual(asyncio.run(jiance('一键出售 凡品')), ('一键出售', '凡品'))

    def test_scope_parser_defaults_to_safe_qualities(self):
        self.assertEqual(g7_equip.parse_batch_sell_qualities(''), ('凡品', '良品'))
        self.assertEqual(g7_equip.parse_batch_sell_qualities('-良品'), ('良品',))
        self.assertIsNone(g7_equip.parse_batch_sell_qualities('精品'))

    async def test_batch_sell_is_atomic_and_applies_lingshi_trait(self):
        rows = [
            (101, '凡品', 0, 1),
            (102, '良品', 0, 10),
        ]
        cursor = _BatchSellCursor(rows=rows, has_yefan=True)
        conn = _BatchSellConnection(cursor)
        original_connect = g7_equip.connect_mysql
        g7_equip.connect_mysql = lambda: conn
        try:
            result = await g7_equip.batch_sell_equip.__wrapped__(7, '', '')
        finally:
            g7_equip.connect_mysql = original_connect

        expected_base = sum(
            g7_equip.calc_equip_sell_info(row[3], row[1], row[2])['total_price']
            for row in rows
        )
        expected_credit = expected_base * 120 // 100
        self.assertEqual(cursor.deleted_ids, [101, 102])
        self.assertEqual(cursor.balance, 1000 + expected_credit)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)
        self.assertIn('COALESCE(ue.is_equipped, 0) = 0', cursor.selection_sql)
        self.assertIn('COALESCE(ue.level, 0) = 0', cursor.selection_sql)
        self.assertIn('一键出售成功', result['content'])
        self.assertIn('叶凡特性', result['content'])
        self.assertIn('已自动保留', result['content'])

    async def test_empty_scope_does_not_commit(self):
        cursor = _BatchSellCursor(rows=[])
        conn = _BatchSellConnection(cursor)
        original_connect = g7_equip.connect_mysql
        g7_equip.connect_mysql = lambda: conn
        try:
            result = await g7_equip.batch_sell_equip.__wrapped__(7, '', '凡品')
        finally:
            g7_equip.connect_mysql = original_connect

        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 1)
        self.assertIn('没有可出售', result['content'])

    async def test_changed_equipment_state_rolls_back_without_credit(self):
        rows = [(101, '凡品', 0, 1), (102, '良品', 0, 10)]
        cursor = _BatchSellCursor(rows=rows, delete_count=1)
        conn = _BatchSellConnection(cursor)
        original_connect = g7_equip.connect_mysql
        g7_equip.connect_mysql = lambda: conn
        try:
            result = await g7_equip.batch_sell_equip.__wrapped__(7, '', '')
        finally:
            g7_equip.connect_mysql = original_connect

        self.assertEqual(cursor.balance, 1000)
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 1)
        self.assertIn('装备状态已变化', result['content'])

    def test_equipment_bag_exposes_batch_sell_button(self):
        role = {'id': 1, 'name': '测试角色', 'level': 1}
        content = g7_equip.format_equip_bag_markdown([], 1, 1, role)
        self.assertIn("text='一键出售'", content)


if __name__ == '__main__':
    unittest.main()
