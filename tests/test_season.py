import unittest
from datetime import date, datetime
from unittest.mock import patch

import aiomysql
import output_main
import Game_main.g21_season as season_module

from Game_main.g21_season import (
    cosmetic_catalog,
    cosmetic_identity,
    default_season_rule,
    reward_for_xp,
    season_days_left,
    season_effect_snapshot,
    season_key,
    season_period,
)


class SeasonConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor

    async def commit(self):
        self.commits += 1


class SeasonRewardCursor:
    def __init__(self, xp=60):
        self.xp = xp
        self.last_sql = ""
        self.rowcount = 0
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params=None):
        self.last_sql = " ".join(sql.split())
        self.statements.append((self.last_sql, params))
        self.rowcount = 1
        # 模拟旧版本已有 reward_log，但还没有真实 user_cosmetic 的补发场景。
        if self.last_sql.startswith("INSERT IGNORE INTO season_reward_log"):
            self.rowcount = 0

    async def fetchone(self):
        if self.last_sql.startswith("SELECT id, season_key"):
            return (8, "2026-S4", "五行天象", date(2026, 8, 12), date(2026, 6, 18))
        if self.last_sql.startswith("SELECT xp FROM user_season_progress"):
            return (self.xp,)
        return None

    async def fetchall(self):
        return ()


class SeasonEquipCursor:
    def __init__(self):
        self.last_sql = ""
        self.statements = []
        self.rowcount = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params=None):
        self.last_sql = " ".join(sql.split())
        self.statements.append((self.last_sql, params))
        self.rowcount = 1

    async def fetchone(self):
        if self.last_sql.startswith("SELECT c.cosmetic_type"):
            return ("TITLE", "诸天行者")
        return None


class MissingCosmeticTableCursor:
    async def execute(self, sql, params=None):
        raise aiomysql.ProgrammingError(1146, "Table does not exist")


class ActiveEffectCursor:
    def __init__(self):
        self.params = None

    async def execute(self, sql, params=None):
        self.params = params

    async def fetchone(self):
        return ("PVE_ATTACK_UP", 300, "锐金", "攻击提高", 1)


class SeasonTests(unittest.TestCase):
    def test_eight_week_key_and_days_are_bounded(self):
        self.assertEqual(season_key(date(2026, 1, 1)), '2026-S1')
        self.assertEqual(season_days_left(date(2026, 1, 1)), 55)
        self.assertEqual(season_period(date(2026, 2, 25))["key"], "2026-S1")
        self.assertEqual(season_period(date(2026, 2, 26))["key"], "2026-S2")
        self.assertEqual(season_key(datetime(2026, 2, 26, 18, 30)), "2026-S2")

    def test_year_end_period_remains_a_full_non_overlapping_block(self):
        period = season_period(date(2026, 12, 31))
        self.assertEqual((period["ends_on"] - period["starts_on"]).days, 55)
        self.assertEqual(season_key(date(2027, 1, 1)), period["key"])
        self.assertEqual(season_key(date(2027, 1, 28)), "2027-S1")

    def test_rewards_are_cosmetic_milestones(self):
        self.assertEqual(reward_for_xp(19), [])
        self.assertEqual(reward_for_xp(60)[-1][0], 60)
        catalog = cosmetic_catalog("2026-S1")
        self.assertEqual(catalog[0]["code"], "2026-S1-CLOUD-FRAME")
        self.assertEqual({item["cosmetic_type"] for item in catalog}, {"FRAME", "TITLE", "AURA"})
        prefix, aura = cosmetic_identity({
            "TITLE": {"name": "诸天行者"},
            "FRAME": {"name": "流云纹头像框"},
            "AURA": {"name": "五行流光"},
        })
        self.assertEqual(prefix, "「诸天行者」〔流云纹头像框〕")
        self.assertEqual(aura, "五行流光")

    def test_season_effect_uses_allowlist_and_hard_cap(self):
        allowed = season_effect_snapshot("PVE_ATTACK_UP", 900)
        self.assertTrue(allowed["active"])
        self.assertEqual(allowed["attack_bp"], 500)
        unknown = season_effect_snapshot("FREE_TEXT_DAMAGE", 99999)
        self.assertFalse(unknown["active"])
        self.assertEqual(unknown["attack_bp"], 0)
        self.assertEqual(default_season_rule("2026-S1")[0], "PVE_ATTACK_UP")
        self.assertEqual(default_season_rule("2026-S2")[0], "PVE_DEFENSE_UP")
        self.assertEqual(default_season_rule("2026-S3")[0], "PVE_SPEED_UP")


class ProgressionDisplayRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_cosmetic_code_survives_global_command_parser(self):
        self.assertEqual(
            await output_main.jiance("赛季佩戴 2026-S1-cloud-frame"),
            ("赛季佩戴", "2026-S1-CLOUD-FRAME"),
        )

    async def test_causal_and_cosmetic_commands_are_routed(self):
        originals = (
            output_main.openid_to_uid,
            output_main.causal_marks,
            output_main.season_cosmetics,
            output_main.season_equip_cosmetic,
        )
        calls = []

        async def fake_uid(_openid):
            return 6001

        async def fake_marks(uid):
            calls.append(("marks", uid))
            return "marks"

        async def fake_cosmetics(uid):
            calls.append(("cosmetics", uid))
            return "cosmetics"

        async def fake_equip(uid, code):
            calls.append(("equip", uid, code))
            return "equipped"

        output_main.openid_to_uid = fake_uid
        output_main.causal_marks = fake_marks
        output_main.season_cosmetics = fake_cosmetics
        output_main.season_equip_cosmetic = fake_equip
        try:
            self.assertEqual(await output_main.content("因果印记", "", "openid"), "marks")
            self.assertEqual(await output_main.content("赛季装扮", "", "openid"), "cosmetics")
            self.assertEqual(
                await output_main.content("赛季佩戴", "2026-S1-CLOUD-FRAME", "openid"),
                "equipped",
            )
        finally:
            (
                output_main.openid_to_uid,
                output_main.causal_marks,
                output_main.season_cosmetics,
                output_main.season_equip_cosmetic,
            ) = originals

        self.assertEqual(
            calls,
            [
                ("marks", 6001),
                ("cosmetics", 6001),
                ("equip", 6001, "2026-S1-CLOUD-FRAME"),
            ],
        )


class SeasonAssetTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_effect_window_uses_exact_datetime_instead_of_day_start(self):
        cursor = ActiveEffectCursor()
        moment = datetime(2026, 8, 2, 15, 30, 45)
        snapshot = await season_module._load_active_effect(
            cursor,
            (8, "2026-S4", "五行天象", date(2026, 8, 12), date(2026, 6, 18)),
            moment,
        )
        self.assertEqual(cursor.params, (8, moment, moment))
        self.assertTrue(snapshot["active"])

    async def test_core_role_display_survives_before_cosmetic_migration(self):
        self.assertEqual(
            await season_module.get_equipped_cosmetics(7001, MissingCosmeticTableCursor()),
            {},
        )

    async def test_pve_start_survives_before_season_runtime_migration(self):
        snapshot = await season_module.get_active_season_effect(MissingCosmeticTableCursor())
        self.assertFalse(snapshot["active"])
        self.assertTrue(snapshot["migration_pending"])

    async def test_reward_log_entitlements_are_backfilled_as_real_assets(self):
        cursor = SeasonRewardCursor(xp=60)
        connection = SeasonConnection(cursor)
        with patch.object(season_module, "connect_mysql", lambda: connection):
            result = await season_module.season_rewards.__wrapped__(7001, "")

        asset_inserts = [
            params for sql, params in cursor.statements
            if sql.startswith("INSERT IGNORE INTO user_cosmetic ")
        ]
        self.assertEqual(len(asset_inserts), 2)
        self.assertTrue(all(params[0] == 7001 and params[2] == 8 for params in asset_inserts))
        self.assertEqual(connection.commits, 1)
        self.assertIn("装扮已入库", result["content"])

    async def test_equip_replaces_only_the_same_cosmetic_type_atomically(self):
        cursor = SeasonEquipCursor()
        connection = SeasonConnection(cursor)
        with patch.object(season_module, "connect_mysql", lambda: connection):
            result = await season_module.season_equip_cosmetic.__wrapped__(
                7001,
                "",
                "2026-s4-heaven-walker",
            )

        equip_sql, equip_params = next(
            (sql, params) for sql, params in cursor.statements
            if sql.startswith("INSERT INTO user_cosmetic_equipped")
        )
        self.assertIn("ON DUPLICATE KEY UPDATE", equip_sql)
        self.assertEqual(equip_params, (7001, "TITLE", "2026-S4-HEAVEN-WALKER"))
        self.assertEqual(connection.commits, 1)
        self.assertIn("诸天行者", result["content"])
