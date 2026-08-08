import json
import unittest
from unittest.mock import AsyncMock, patch

import Game_main.g2_canwu as canwu_module
import Game_main.g7_equip as equip_module
import Game_main.g14_estate as estate_module


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0
        self.commit_statement_count = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor

    async def commit(self):
        self.commits += 1
        self.commit_statement_count = len(self._cursor.statements)

    async def rollback(self):
        self.rollbacks += 1


class BaseCursor:
    def __init__(self):
        self.statements = []
        self.rowcount = 0
        self._fetchone = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetchone(self):
        return self._fetchone

    async def fetchall(self):
        return []


class EstateLevelCursor(BaseCursor):
    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.statements.append((compact, params))
        self.rowcount = 1

    async def fetchall(self):
        return [
            ("聚灵阵", 12),
            ("炼器台", 4),
            ("恶意建筑", 10),
        ]


class ClaimSchemaCursor(BaseCursor):
    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.statements.append((compact, params))
        self.rowcount = 1

    async def fetchall(self):
        return [("reward_lingshi",)]


class CanwuCursor(BaseCursor):
    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.statements.append((compact, params))
        self.rowcount = 1
        if compact.startswith("SELECT id, `name`, dengji, exp FROM user_role"):
            self._fetchone = (10, "萧炎", 1, 0)
        elif compact.startswith("SELECT is_canwu, cw_role"):
            self._fetchone = (0, 0, 0, 0, "openid")
        elif compact.startswith("UPDATE user_zt SET is_canwu = 1"):
            self._fetchone = None
        else:
            raise AssertionError(f"未处理的参悟SQL：{compact}")


class ClaimCursor(BaseCursor):
    def __init__(self, insert_succeeds=True):
        super().__init__()
        self.insert_succeeds = insert_succeeds

    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.statements.append((compact, params))
        if compact.startswith("INSERT IGNORE INTO user_estate_claim"):
            self.rowcount = 1 if self.insert_succeeds else 0
        elif compact.startswith("INSERT INTO user_spirit_beast_wallet"):
            self.rowcount = 1
        elif compact.startswith("UPDATE user_zt SET lingshi = lingshi +"):
            self.rowcount = 1
        else:
            raise AssertionError(f"未处理的洞府领奖SQL：{compact}")


class EnhanceCursor(BaseCursor):
    def __init__(self):
        super().__init__()
        self._lingshi_reads = 0

    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.statements.append((compact, params))
        self.rowcount = 1
        if compact.startswith("SELECT ue.id, ue.uid"):
            self._fetchone = (
                1, 7, 301, 1, "凡品", 0, 0, None,
                "试锋剑", "试锋套", "weapon", 1,
                100, 10, 1000, 20, 5, 1, 1, 1, 1, 1, 0, None,
            )
        elif compact.startswith("SELECT lingshi FROM user_zt"):
            self._lingshi_reads += 1
            self._fetchone = (10000 if self._lingshi_reads == 1 else 9050,)
        elif compact.startswith("UPDATE user_equip SET level"):
            self._fetchone = None
        elif compact.startswith("UPDATE user_zt SET lingshi = lingshi -"):
            self._fetchone = None
        elif compact.startswith("SELECT id, `name`, dengji, world FROM user_role"):
            self._fetchone = None
        else:
            raise AssertionError(f"未处理的强化SQL：{compact}")


class EstateEffectIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_level_reader_uses_allowlist_defaults_and_row_lock(self):
        cursor = EstateLevelCursor()
        levels = await estate_module.read_estate_levels(7, cursor, for_update=True)

        self.assertEqual(levels["spirit_array"], 10)
        self.assertEqual(levels["forge_table"], 4)
        self.assertEqual(levels["beast_garden"], 1)
        self.assertNotIn("恶意建筑", levels)
        select_sql, select_params = cursor.statements[-1]
        self.assertTrue(select_sql.endswith("FOR UPDATE"))
        self.assertEqual(select_params, (7,))
        for _, params in cursor.statements[:-1]:
            self.assertEqual(params[0], 7)
            self.assertIn(params[1], estate_module.BUILDINGS)

    async def test_old_claim_table_gets_only_missing_snapshot_columns(self):
        cursor = ClaimSchemaCursor()
        with patch.object(estate_module, "_ESTATE_CLAIM_SCHEMA_READY", False):
            await estate_module.ensure_estate_claim_snapshot_columns(cursor)

        alter_sql = [sql for sql, _ in cursor.statements if sql.startswith("ALTER TABLE")]
        self.assertEqual(len(alter_sql), 2)
        self.assertTrue(any("`levels_json`" in sql for sql in alter_sql))
        self.assertTrue(any("`rule_version`" in sql for sql in alter_sql))
        self.assertFalse(any("`reward_lingshi`" in sql for sql in alter_sql))

    async def test_estate_home_displays_all_current_real_effects(self):
        cursor = BaseCursor()
        connection = FakeConnection(cursor)
        levels = {
            "spirit_array": 10,
            "forge_table": 10,
            "beast_garden": 10,
            "scripture_library": 10,
        }
        with (
            patch.object(estate_module, "connect_mysql", lambda: connection),
            patch.object(estate_module, "read_estate_levels", AsyncMock(return_value=levels)),
        ):
            result = await estate_module.estate_home.__wrapped__(7, "")

        self.assertIn("参悟时长 -18%", result["content"])
        self.assertIn("强化成功率 +4.5个百分点", result["content"])
        self.assertIn("灵兽容量 7只", result["content"])
        self.assertIn("已装备技能效果 +4.5%", result["content"])
        self.assertEqual(connection.commits, 1)

    async def test_canwu_persists_adjusted_duration_as_start_snapshot(self):
        cursor = CanwuCursor()
        connection = FakeConnection(cursor)
        with (
            patch.object(canwu_module, "connect_mysql", lambda: connection),
            patch.object(canwu_module, "ensure_canwu_duration_column", AsyncMock()),
            patch.object(
                canwu_module,
                "read_estate_levels",
                AsyncMock(return_value={
                    "spirit_array": 10,
                    "forge_table": 1,
                    "beast_garden": 1,
                    "scripture_library": 1,
                }),
            ),
            patch.object(canwu_module, "roll_canwu_duration", return_value=120),
            patch.object(canwu_module.random, "randint", return_value=400),
            patch.object(canwu_module.time, "time", return_value=1000),
            patch.object(canwu_module, "up_need_exp", AsyncMock(return_value=1000)),
            patch.object(canwu_module, "all_write_command", AsyncMock(return_value="")),
            patch("Game_main.g16_onboarding.record_onboarding_event", AsyncMock()),
            patch("Game_main.g25_daily_tasks.record_daily_event", AsyncMock()),
        ):
            result = await canwu_module.canwu_role.__wrapped__(7, "")

        start_update = next(
            params for sql, params in cursor.statements
            if sql.startswith("UPDATE user_zt SET is_canwu = 1")
        )
        self.assertEqual(start_update, (10, 1000, 99, 200, 7))
        self.assertIn("本次已冻结", result["content"])
        self.assertEqual(connection.commits, 1)

    async def test_claim_records_reward_levels_and_rule_in_same_transaction(self):
        cursor = ClaimCursor()
        connection = FakeConnection(cursor)
        levels = {
            "spirit_array": 2,
            "forge_table": 3,
            "beast_garden": 4,
            "scripture_library": 5,
        }
        with (
            patch.object(estate_module, "connect_mysql", lambda: connection),
            patch.object(estate_module, "ensure_estate_claim_snapshot_columns", AsyncMock()),
            patch.object(estate_module, "read_estate_levels", AsyncMock(return_value=levels)),
        ):
            result = await estate_module.estate_claim.__wrapped__(7, "", "稳健")

        insert_sql, insert_params = next(
            statement for statement in cursor.statements
            if statement[0].startswith("INSERT IGNORE INTO user_estate_claim")
        )
        self.assertIn("reward_lingshi", insert_sql)
        self.assertEqual(insert_params[3], 132)
        self.assertEqual(json.loads(insert_params[4]), levels)
        self.assertEqual(insert_params[5], estate_module.ESTATE_RULE_VERSION)
        lingshi_update = next(
            statement for statement in cursor.statements
            if statement[0].startswith("UPDATE user_zt SET lingshi = lingshi +")
        )
        self.assertEqual(lingshi_update[1], (132, 7))
        beast_reward = next(
            statement for statement in cursor.statements
            if statement[0].startswith("INSERT INTO user_spirit_beast_wallet")
        )
        self.assertEqual(beast_reward[1], (7, 60))
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertIn("132", result["content"])

    async def test_duplicate_claim_rolls_back_without_granting_reward(self):
        cursor = ClaimCursor(insert_succeeds=False)
        connection = FakeConnection(cursor)
        with (
            patch.object(estate_module, "connect_mysql", lambda: connection),
            patch.object(estate_module, "ensure_estate_claim_snapshot_columns", AsyncMock()),
            patch.object(
                estate_module,
                "read_estate_levels",
                AsyncMock(return_value={code: 1 for code in estate_module.BUILDING_CODE_TO_NAME}),
            ),
        ):
            result = await estate_module.estate_claim.__wrapped__(7, "", "稳健")

        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)
        self.assertFalse(any(sql.startswith("UPDATE user_zt") for sql, _ in cursor.statements))
        self.assertIn("今日已收取", result["content"])

    async def test_enhancement_applies_estate_rate_and_sect_cost_atomically(self):
        cursor = EnhanceCursor()
        connection = FakeConnection(cursor)
        artifact_research = {
            "research_type": "御器",
            "effect": {"code": "SECT_ARTIFACT", "enhance_discount_bp": 500},
        }
        with (
            patch.object(equip_module, "connect_mysql", lambda: connection),
            patch.object(
                equip_module,
                "read_estate_levels",
                AsyncMock(return_value={
                    "spirit_array": 1,
                    "forge_table": 10,
                    "beast_garden": 1,
                    "scripture_library": 1,
                }),
            ),
            patch.object(equip_module, "get_active_research", AsyncMock(return_value=artifact_research)),
            patch.object(equip_module.random, "randint", return_value=1),
            patch("Tool.tool_power.update_role_power", AsyncMock()),
        ):
            result = await equip_module.enhance_equip.__wrapped__(7, "", "1")

        cost_update = next(
            params for sql, params in cursor.statements
            if sql.startswith("UPDATE user_zt SET lingshi = lingshi -")
        )
        self.assertEqual(cost_update, (950, 7))
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertIn("炼器台 Lv.10", result["content"])
        self.assertIn("本次 94.5%", result["content"])
        self.assertIn("宗门御器：消耗 -5%", result["content"])
        self.assertIn("标称1000，实付950", result["content"])


if __name__ == "__main__":
    unittest.main()
