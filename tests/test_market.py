import unittest

from Game_main.g30_market import (
    MARKET_EXPIRE_HOURS,
    _render_order_lines,
    calculate_market_fee,
    category_for_item,
    market_help,
    parse_item_quantity_price,
    parse_order_quantity,
    show_market_menu,
)
import output_main
from output_main import jiance


class MarketTests(unittest.IsolatedAsyncioTestCase):
    def test_market_order_rows_only_show_category_quantity_and_unit_price(self):
        rows = [
            (101, 10001, "SELL", "束灵符", "消耗品", 10, 500, 0, 3600),
            (102, 10001, "BUY", "渡厄丹", "丹药", 3, 800, 2400, 1800),
        ]
        content = "\n".join(_render_order_lines(rows, 10001, is_owner_view=True))

        self.assertIn("类别：消耗品｜数量：10｜单价：500 灵石", content)
        self.assertIn("类别：丹药｜数量：3｜单价：800 灵石", content)
        self.assertEqual(content.count("show='下架'"), 2)
        for hidden_text in ("束灵符", "渡厄丹", "卖家：", "买家：", "剩余：", "总价："):
            self.assertNotIn(hidden_text, content)

    def test_market_fee_and_categories(self):
        self.assertEqual(calculate_market_fee(100), 8)
        self.assertEqual(calculate_market_fee(19), 1)
        self.assertEqual(category_for_item("渡厄丹", 4), "丹药")
        self.assertEqual(category_for_item("赤焰砂", 2), "材料")
        self.assertEqual(category_for_item("束灵符", 3), "消耗品")
        self.assertEqual(category_for_item("火球术卷轴", 3), "神通")

    def test_listing_and_purchase_order_parameter_formats(self):
        self.assertEqual(parse_item_quantity_price("束灵符 10 500000"), ("束灵符", 10, 500000))
        self.assertEqual(parse_item_quantity_price("束灵符-10-500000"), ("束灵符", 10, 500000))
        self.assertEqual(
            parse_item_quantity_price("束灵符 500000 10", price_first=True),
            ("束灵符", 10, 500000),
        )
        self.assertEqual(parse_order_quantity("126 5", "坊市购买"), (126, 5))
        with self.assertRaises(ValueError):
            parse_item_quantity_price("束灵符 0 500")

    async def test_market_commands_keep_player_spaces(self):
        self.assertEqual(await jiance("坊市"), ("坊市", ""))
        self.assertEqual(await jiance("坊市 搜 束灵符"), ("坊市", "搜 束灵符"))
        self.assertEqual(await jiance("坊市 分类 丹药"), ("坊市", "分类 丹药"))
        self.assertEqual(await jiance("坊市上架 束灵符 10 500000"), ("坊市上架", "束灵符 10 500000"))
        self.assertEqual(await jiance("坊市收购 束灵符 500000 10"), ("坊市收购", "束灵符 500000 10"))
        self.assertEqual(await jiance("坊市购买 126 5"), ("坊市购买", "126 5"))
        self.assertEqual(await jiance("坊市出售 126 5"), ("坊市出售", "126 5"))

    async def test_market_menu_exposes_complete_entry_points(self):
        content = (await show_market_menu.__wrapped__(1, ""))["content"]
        for command in ("坊市列表", "坊市上架 ", "坊市购买 ", "坊市收购 ", "坊市出售 ", "我的摊位", "坊市交易记录"):
            self.assertIn(command, content)
        self.assertIn(str(MARKET_EXPIRE_HOURS), content)

        help_content = (await market_help.__wrapped__(1, ""))["content"]
        self.assertIn("蓝色指令可直接点击发送", help_content)
        self.assertIn("text='坊市上架 '", help_content)
        self.assertIn("text='坊市收购 '", help_content)
        self.assertIn("text='坊市底价 '", help_content)

    async def test_market_dispatch_does_not_require_undefined_prefix(self):
        original_uid = output_main.openid_to_uid
        original_home = output_main.market_home

        async def fake_uid(_openid):
            return 10001

        async def fake_home(uid, param):
            self.assertEqual((uid, param), (10001, ""))
            return {"type": "markdown", "content": "ok"}

        output_main.openid_to_uid = fake_uid
        output_main.market_home = fake_home
        try:
            result = await output_main.content("坊市", "", "test-openid")
        finally:
            output_main.openid_to_uid = original_uid
            output_main.market_home = original_home
        self.assertEqual(result["content"], "ok")
