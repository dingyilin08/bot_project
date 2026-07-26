import unittest

from Game_main.g10_shop import DEFAULT_SHOP_ITEMS, STAMINA_POTION_ITEM_ID, parse_name_num


class ShopCatalogTests(unittest.TestCase):
    def test_default_items_have_unique_names_and_ids(self):
        self.assertEqual(len(DEFAULT_SHOP_ITEMS), len({item["name"] for item in DEFAULT_SHOP_ITEMS}))
        self.assertEqual(len(DEFAULT_SHOP_ITEMS), len({item["item_id"] for item in DEFAULT_SHOP_ITEMS}))
        self.assertTrue(all(item["price"] > 0 and item["daily_limit"] > 0 for item in DEFAULT_SHOP_ITEMS))
        self.assertIn(STAMINA_POTION_ITEM_ID, {item["item_id"] for item in DEFAULT_SHOP_ITEMS})

    def test_parse_name_num_accepts_only_positive_quantity(self):
        self.assertEqual(parse_name_num("体力药-2"), ("体力药", 2))
        self.assertEqual(parse_name_num(" 体力药 - 1 "), ("体力药", 1))
        self.assertEqual(parse_name_num("体力药"), (None, None))
        self.assertEqual(parse_name_num("体力药-0"), (None, None))
        self.assertEqual(parse_name_num("体力药-abc"), (None, None))
