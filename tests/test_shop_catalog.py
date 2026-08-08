import unittest

from Game_main.g10_shop import (
    DEFAULT_SHOP_ITEMS,
    DIRECTIONAL_SMELTING_JADE_ITEM_ID,
    STAMINA_POTION_ITEM_ID,
    parse_name_num,
)
from Game_main.g9_yaoyuan import _parse_name_num
from Tool.tool_command import pagination_controls


class ShopCatalogTests(unittest.TestCase):
    def test_default_items_have_unique_names_and_ids(self):
        self.assertEqual(len(DEFAULT_SHOP_ITEMS), len({item["name"] for item in DEFAULT_SHOP_ITEMS}))
        self.assertEqual(len(DEFAULT_SHOP_ITEMS), len({item["item_id"] for item in DEFAULT_SHOP_ITEMS}))
        self.assertTrue(all(item["price"] > 0 for item in DEFAULT_SHOP_ITEMS))
        self.assertTrue(all(item["daily_limit"] > 0 or item["weekly_limit"] > 0 for item in DEFAULT_SHOP_ITEMS))
        self.assertIn(STAMINA_POTION_ITEM_ID, {item["item_id"] for item in DEFAULT_SHOP_ITEMS})
        jade = next(item for item in DEFAULT_SHOP_ITEMS if item["item_id"] == DIRECTIONAL_SMELTING_JADE_ITEM_ID)
        self.assertEqual(jade["weekly_limit"], 2)
        self.assertEqual(jade["daily_limit"], 0)

    def test_parse_name_num_defaults_to_one_and_rejects_invalid_quantity(self):
        self.assertEqual(parse_name_num("体力药-2"), ("体力药", 2))
        self.assertEqual(parse_name_num(" 体力药 - 1 "), ("体力药", 1))
        self.assertEqual(parse_name_num("体力药"), ("体力药", 1))
        self.assertEqual(parse_name_num("体力药-"), ("体力药", 1))
        self.assertEqual(parse_name_num("体力药-0"), (None, None))
        self.assertEqual(parse_name_num("体力药-abc"), (None, None))

    def test_seed_and_pill_quantity_defaults_to_one(self):
        self.assertEqual(_parse_name_num("灵草种子"), ("灵草种子", 1))
        self.assertEqual(_parse_name_num("丹药-"), ("丹药", 1))

    def test_pagination_buttons_use_clear_labels_and_clamped_commands(self):
        controls = pagination_controls("物品背包", 2, 3)
        self.assertIn("text='物品背包 1' show='上一页'", controls)
        self.assertIn("text='物品背包' show='跳转【页数】'", controls)
        self.assertIn("text='物品背包 3' show='下一页'", controls)
        first_page = pagination_controls("物品背包", 1, 3)
        self.assertIn("text='物品背包 1' show='上一页'", first_page)
