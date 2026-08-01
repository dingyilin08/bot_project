import csv
import re
import unittest
from collections import Counter
from pathlib import Path

from Game_main.g9_yaoyuan import _is_breakthrough_pill_name


CATALOG_SQL = (
    Path(__file__).resolve().parents[1]
    / "数据库源文件"
    / "p0_yaoyuan_schema_and_catalog.sql"
)
BREAKTHROUGH_SQL = (
    Path(__file__).resolve().parents[1]
    / "数据库源文件"
    / "p0_breakthrough_pill_recipes.sql"
)


def _insert_rows(sql_text, table_name):
    pattern = re.compile(
        rf"INSERT INTO {table_name}\b.*?\nVALUES\n(?P<rows>.*?)(?=^ON DUPLICATE KEY UPDATE|^START TRANSACTION;)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(sql_text)
    if not match:
        raise AssertionError(f"找不到 {table_name} 的静态 INSERT 数据块")

    rows = []
    for raw_line in match.group("rows").splitlines():
        line = raw_line.strip()
        if not line.startswith("("):
            continue
        line = line.rstrip(",;")
        parsed = next(csv.reader([line[1:-1]], delimiter=",", quotechar="'", skipinitialspace=True))
        rows.append([value.strip() for value in parsed])
    return rows


class YaoyuanCatalogSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = CATALOG_SQL.read_text(encoding="utf-8")
        cls.herbs = _insert_rows(cls.sql, "data_herb")
        cls.pills = _insert_rows(cls.sql, "data_pill")
        cls.recipes = _insert_rows(cls.sql, "data_recipe")

    def test_world_catalog_counts_are_complete(self):
        expected_worlds = {
            "斗破苍穹", "仙逆", "凡人修仙传", "完美世界", "遮天", "沧元图"
        }
        self.assertEqual(Counter(row[5] for row in self.herbs), {world: 8 for world in expected_worlds})
        self.assertEqual(Counter(row[8] for row in self.pills), {world: 4 for world in expected_worlds})
        self.assertEqual(Counter(row[7] for row in self.recipes), {world: 4 for world in expected_worlds})

    def test_each_world_has_two_herbs_per_tier(self):
        tier_counts = Counter((row[5], int(row[4])) for row in self.herbs)
        self.assertTrue(tier_counts)
        self.assertTrue(all(count == 2 for count in tier_counts.values()))
        self.assertEqual(len(tier_counts), 24)

    def test_recipe_references_stay_inside_their_world(self):
        herb_world = {int(row[0]): row[5] for row in self.herbs}
        pill_world = {int(row[0]): row[8] for row in self.pills}
        referenced_herbs = set()

        for row in self.recipes:
            recipe_world = row[7]
            pill_id = int(row[2])
            self.assertEqual(pill_world[pill_id], recipe_world)
            for herb_id in map(int, row[3].split("|")):
                referenced_herbs.add(herb_id)
                self.assertEqual(herb_world[herb_id], recipe_world)

        self.assertEqual(referenced_herbs, set(herb_world))

    def test_pill_effects_are_supported_and_well_formed(self):
        supported = {
            "gongji", "fangyu", "qixue", "fali", "sudu", "baoji",
            "baoshang", "shanbi", "mingzhong", "pofang", "xixue",
            "exp", "sell",
        }
        for row in self.pills:
            effect_types = row[3].split(",")
            effect_values = row[4].split(",")
            self.assertEqual(len(effect_types), len(effect_values), row[1])
            self.assertTrue(set(effect_types) <= supported, row[1])
            for value in effect_values:
                float(value)

    def test_catalog_ids_and_item_ids_are_unique(self):
        for rows, item_index in ((self.herbs, 6), (self.pills, 9)):
            ids = [int(row[0]) for row in rows]
            item_ids = [int(row[item_index]) for row in rows]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(len(item_ids), len(set(item_ids)))

        herb_items = {int(row[6]) for row in self.herbs}
        pill_items = {int(row[9]) for row in self.pills}
        self.assertTrue(herb_items.isdisjoint(pill_items))

    def test_inventory_mapping_and_mysql57_compatibility_are_present(self):
        self.assertEqual(self.sql.count("INSERT INTO data_item"), 2)
        self.assertNotIn("ADD COLUMN IF NOT EXISTS", self.sql)
        self.assertIn("information_schema.COLUMNS", self.sql)
        self.assertIn("INSERT INTO data_seed", self.sql)


class BreakthroughRecipeSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_sql = CATALOG_SQL.read_text(encoding="utf-8")
        cls.sql = BREAKTHROUGH_SQL.read_text(encoding="utf-8")
        cls.herbs = _insert_rows(cls.base_sql, "data_herb")
        cls.rows = _insert_rows(cls.sql, "tmp_breakthrough_recipe")

    def test_all_breakthrough_items_have_recipes(self):
        self.assertEqual(len(self.rows), 54)
        self.assertEqual({int(row[1]) for row in self.rows}, set(range(153, 207)))
        self.assertEqual(len({int(row[0]) for row in self.rows}), 54)
        self.assertEqual(len({row[2] for row in self.rows}), 54)

    def test_each_world_has_nine_breakthrough_stages(self):
        world_counts = Counter(row[3] for row in self.rows)
        self.assertEqual(len(world_counts), 6)
        self.assertTrue(all(count == 9 for count in world_counts.values()))

    def test_breakthrough_ingredients_stay_inside_their_world(self):
        herb_world = {int(row[0]): row[5] for row in self.herbs}
        for row in self.rows:
            for herb_id in map(int, row[4].split("|")):
                self.assertEqual(herb_world[herb_id], row[3], row[2])

    def test_breakthrough_pills_cannot_be_directly_consumed(self):
        self.assertTrue(_is_breakthrough_pill_name("[穹]斗师破境丹"))
        self.assertFalse(_is_breakthrough_pill_name("三纹青灵丹"))
        self.assertIn("_is_breakthrough_pill_name(pill[\"name\"])", (
            Path(__file__).resolve().parents[1] / "Game_main" / "g9_yaoyuan.py"
        ).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
