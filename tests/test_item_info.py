import asyncio
import unittest

from Game_main.g1_role import _format_pill_effect, _query_item_info, _render_item_info
from output_main import jiance


class FakeCursor:
    def __init__(self, fetchone_results, fetchall_results=()):
        self.fetchone_results = list(fetchone_results)
        self.fetchall_results = list(fetchall_results)
        self.queries = []

    async def execute(self, sql, params=None):
        self.queries.append((" ".join(sql.split()), params))

    async def fetchone(self):
        return self.fetchone_results.pop(0)

    async def fetchall(self):
        return self.fetchall_results.pop(0)


class ItemInfoTests(unittest.TestCase):
    def test_command_parser_recognizes_item_info_with_name(self):
        self.assertEqual(
            asyncio.run(jiance("物品信息 冰灵焰草种子")),
            ("物品信息", "冰灵焰草种子"),
        )

    def test_command_parser_keeps_brackets_in_item_name(self):
        self.assertEqual(
            asyncio.run(jiance("物品信息 [穹]斗师破境丹")),
            ("物品信息", "[穹]斗师破境丹"),
        )

    def test_query_supports_seed_catalog(self):
        cursor = FakeCursor(
            [None, ("冰灵焰草种子", "冰灵焰草", 1000, 1, "斗破苍穹")],
            [[("data_seed",), ("data_herb",), ("data_pill",), ("data_recipe",)]],
        )
        info = asyncio.run(_query_item_info(cursor, "冰灵焰草种子"))
        self.assertEqual(info["type"], "种子")
        self.assertIn("1000 灵石", info["access"])
        self.assertIn(("成熟产物", "冰灵焰草"), info["details"])

    def test_query_supports_herb_catalog_and_seed_access(self):
        cursor = FakeCursor(
            [
                None,
                None,
                (1, "冰灵焰草", "蕴含冰火之力的药草。", 100, 1, "斗破苍穹"),
                ("冰灵焰草种子",),
            ],
            [[("data_seed",), ("data_herb",), ("data_pill",), ("data_recipe",)]],
        )
        info = asyncio.run(_query_item_info(cursor, "冰灵焰草"))
        self.assertEqual(info["type"], "药材")
        self.assertIn("冰灵焰草种子", info["access"])
        self.assertIn(("出售价格", "100 灵石/株"), info["details"])

    def test_query_supports_pill_catalog_and_recipe_access(self):
        cursor = FakeCursor(
            [
                None,
                None,
                None,
                (1, "九转丹", "淬炼体魄。", "qixue", "50", 0, 1000, 1, None),
            ],
            [
                [("data_seed",), ("data_herb",), ("data_pill",), ("data_recipe",)],
                [("九转丹方", "1|2", 10, 200, None)],
                [(1, "冰灵焰草"), (2, "赤炎苔")],
            ],
        )
        info = asyncio.run(_query_item_info(cursor, "九转丹"))
        self.assertEqual(info["type"], "丹药")
        self.assertIn(("服用效果", "气血 +50"), info["details"])
        self.assertIn("冰灵焰草 + 赤炎苔", info["access"])
        self.assertIn("消耗 200 灵石", info["access"])

    def test_legacy_standard_pill_works_without_alchemy_tables(self):
        cursor = FakeCursor(
            [("[穹]斗师破境丹", 4, "突破斗师境所需丹药。", "挑战对应世界副本概率掉落")],
            [[]],
        )
        info = asyncio.run(_query_item_info(cursor, "[穹]斗师破境丹"))
        self.assertEqual(info["type"], "丹药")
        self.assertIn("挑战对应世界副本", info["access"])

    def test_pill_effect_supports_multiple_attributes(self):
        self.assertEqual(
            _format_pill_effect("qixue,gongji", "80,8", False),
            "气血 +80、攻击 +8",
        )
        self.assertEqual(_format_pill_effect("baoji", "0.1", True), "暴击 +0.1%")

    def test_render_item_info_contains_details_and_access(self):
        content = _render_item_info({
            "name": "冰灵焰草种子",
            "type": "种子",
            "description": "播种后可收获冰灵焰草。",
            "access": "前往种子商店购买，单价 1000 灵石。",
            "details": [("所属世界", "斗破苍穹"), ("品阶", "凡品")],
            "commands": [],
        })
        self.assertIn("**物品类型：** 种子", content)
        self.assertIn("**所属世界：** 斗破苍穹", content)
        self.assertIn("**获取途径：**", content)
        self.assertIn("种子商店购买", content)


if __name__ == "__main__":
    unittest.main()
