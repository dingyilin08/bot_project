import unittest

from Game_main.g19_sect import (
    DAILY_CONTRIBUTION,
    get_active_research,
    parse_research,
    previous_week_key,
    research_effect,
    sect_dungeon_material_extra,
    week_key,
)


class ResearchCursor:
    def __init__(self, member=True):
        self.member = member
        self.last_sql = ""
        self.last_params = None
        self.settled = False
        self.inserts = []

    async def execute(self, sql, params=None):
        self.last_sql = " ".join(sql.split())
        self.last_params = params
        if self.last_sql.startswith("INSERT INTO sect_research"):
            self.settled = True
            self.inserts.append(params)

    async def fetchone(self):
        if self.last_sql.startswith("SELECT sm.sect_id"):
            return (44,) if self.member else None
        if self.last_sql.startswith("SELECT research_type FROM sect_research"):
            return ("丹道",) if self.settled else None
        return None

    async def fetchall(self):
        if self.last_sql.startswith("SELECT research_type, COUNT(*)"):
            # 数据库返回顺序不能左右平票结果。
            return (("阵法", 2), ("丹道", 2))
        return ()


class SectTests(unittest.TestCase):
    def test_research_is_limited_to_public_pve_options(self):
        self.assertEqual(parse_research("丹道"), "丹道")
        self.assertIsNone(parse_research("PVP伤害"))

    def test_week_key_is_stable(self):
        self.assertEqual(week_key(__import__("datetime").date(2026, 1, 1)), "2026-W01")
        self.assertEqual(DAILY_CONTRIBUTION, 20)

    def test_previous_week_key_handles_iso_year_boundary(self):
        date = __import__("datetime").date
        self.assertEqual(previous_week_key(date(2026, 1, 1)), "2025-W52")
        self.assertEqual(previous_week_key(date(2026, 1, 8)), "2026-W01")

    def test_research_effects_are_machine_readable_and_return_copies(self):
        first = research_effect("秘境")
        self.assertEqual(first["code"], "SECT_DUNGEON")
        self.assertEqual(first["material_extra_chance_bp"], 1000)
        first["material_extra_chance_bp"] = 0
        self.assertEqual(research_effect("秘境")["material_extra_chance_bp"], 1000)
        self.assertEqual(research_effect("不存在"), {})

    def test_dungeon_material_extra_is_deterministic_and_bounded(self):
        first = sect_dungeon_material_extra(7, "battle-a", 1001, 1000)
        self.assertEqual(first, sect_dungeon_material_extra(7, "battle-a", 1001, 1000))
        self.assertIn(first, (0, 1))
        self.assertEqual(sect_dungeon_material_extra(7, "battle-a", 1001, 0), 0)
        self.assertEqual(sect_dungeon_material_extra(7, "battle-a", 1001, 10000), 1)


class ActiveResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_previous_week_tie_settles_by_public_order_and_returns_snapshot(self):
        cursor = ResearchCursor()
        snapshot = await get_active_research(
            7001,
            cursor,
            __import__("datetime").date(2026, 1, 8),
        )
        self.assertEqual(snapshot["vote_week"], "2026-W01")
        self.assertEqual(snapshot["research_type"], "丹道")
        self.assertEqual(snapshot["effect"]["extra_output_chance_bp"], 500)
        self.assertEqual(cursor.inserts[0], (44, "2026-W01", "丹道", 2))

    async def test_player_without_active_sect_has_no_effect(self):
        self.assertIsNone(await get_active_research(7001, ResearchCursor(member=False)))
