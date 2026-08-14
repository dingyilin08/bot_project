import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import output_main
from Game_domain import reincarnation_service
from Game_domain.game_version import PLAYER_VERSION
from Game_domain.reincarnation_service import (
    MAX_REINCARNATION,
    ROLE_ATTRIBUTE_COLUMNS,
    ReincarnationError,
    calculate_reincarnation_attributes,
    validate_reincarnation,
)
from Game_main.g36_reincarnation import (
    render_reincarnation_preview,
    render_reincarnation_success,
)
from Game_main.g7_equip import can_role_wear_equipment, format_wear_result_markdown
from output_main import jiance


def _attributes(value):
    return {column: value for column in ROLE_ATTRIBUTE_COLUMNS}


class ReincarnationRuleTests(unittest.TestCase):
    def test_reincarnated_roles_ignore_equipment_level_requirements(self):
        self.assertFalse(can_role_wear_equipment(1, 90, 1))
        self.assertTrue(can_role_wear_equipment(90, 90, 1))
        self.assertTrue(can_role_wear_equipment(1, 90, 2))
        self.assertTrue(can_role_wear_equipment(1, 90, 9))

    def test_wear_result_explains_reincarnation_level_bypass(self):
        content = format_wear_result_markdown(
            {
                "id": 10001,
                "name": "王林",
                "level": 1,
                "reincarnation_count": 2,
            },
            {
                "part": "weapon",
                "template_name": "九阶仙剑",
                "quality": "仙品",
                "level": 0,
                "min_level": 90,
            },
            attrs_change={},
        )
        self.assertIn("第2世不受装备等级限制", content)

    def test_rebirth_uses_template_plus_ten_percent_of_current_base_stats(self):
        current = _attributes(999)
        template = _attributes(100)
        reborn, inherited = calculate_reincarnation_attributes(current, template)
        self.assertEqual(inherited, _attributes(99))
        self.assertEqual(reborn, _attributes(199))

    def test_rebirth_rounds_inheritance_down_and_never_accepts_negative_stats(self):
        current = _attributes(109)
        current["xixue"] = -5
        template = _attributes(20)
        reborn, inherited = calculate_reincarnation_attributes(current, template)
        self.assertEqual(inherited["gongji"], 10)
        self.assertEqual(reborn["gongji"], 30)
        self.assertEqual(inherited["xixue"], 0)
        self.assertEqual(reborn["xixue"], 20)

    def test_role_must_be_level_100_and_below_ninth_life(self):
        with self.assertRaisesRegex(ReincarnationError, "达到100级"):
            validate_reincarnation({"dengji": 99, "reincarnation_count": 1})
        with self.assertRaisesRegex(ReincarnationError, "已至第9世"):
            validate_reincarnation(
                {"dengji": 100, "reincarnation_count": MAX_REINCARNATION}
            )
        validate_reincarnation({"dengji": 100, "reincarnation_count": 8})

    def test_player_copy_contains_confirmation_and_persistence_rules(self):
        preview = {
            "id": 10001,
            "name": "王林",
            "reincarnation_count": 1,
            "next_reincarnation": 2,
            "stage": "凝气境",
            "inherited_attributes": _attributes(100),
        }
        content = render_reincarnation_preview(preview)
        self.assertIn("第1世 → 第2世", content)
        self.assertIn("轮回重生 确认", content)
        self.assertIn("装备、本源、技能、灵兽及其他养成均会保留", content)
        success = render_reincarnation_success(preview)
        self.assertIn("第2世", success)
        self.assertIn("1级", success)

    def test_migration_adds_default_first_life_column(self):
        sql = (
            Path(__file__).parents[1] / "数据库源文件" / "p12_reincarnation.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("reincarnation_count", sql)
        self.assertIn("NOT NULL DEFAULT 1", sql)
        self.assertEqual(PLAYER_VERSION, "v1.28")


class ReincarnationRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_parser_accepts_preview_and_confirm_commands(self):
        self.assertEqual(await jiance("轮回重生"), ("轮回重生", ""))
        self.assertEqual(await jiance("轮回重生 确认"), ("轮回重生", "确认"))

    async def test_command_routes_confirmation_to_handler(self):
        original_uid = output_main.openid_to_uid
        original_handler = output_main.reincarnation
        calls = []

        async def fake_uid(_openid):
            return 10001

        async def fake_handler(uid, confirmation):
            calls.append((uid, confirmation))
            return {"type": "markdown", "content": "ok"}

        output_main.openid_to_uid = fake_uid
        output_main.reincarnation = fake_handler
        try:
            result = await output_main.content("轮回重生", "确认", "openid")
        finally:
            output_main.openid_to_uid = original_uid
            output_main.reincarnation = original_handler
        self.assertEqual(result["content"], "ok")
        self.assertEqual(calls, [(10001, "确认")])


class _FakeCursor:
    def __init__(self):
        self.rowcount = 0
        self._row = None
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.executed.append((compact, params))
        self.rowcount = 0
        if "FROM abyss_run" in compact:
            self._row = None
        elif "SELECT is_canwu, cw_role FROM user_zt" in compact:
            self._row = (0, 0)
        elif "FROM user_role" in compact and "is_chuzhan = 1" in compact:
            self._row = (10001, "王林", 100, 777, 1, *([1000] * 11))
        elif "FROM data_role" in compact:
            self._row = (*([100] * 11), 2)
        elif "SELECT stage_1 FROM data_stage" in compact:
            self._row = ("凝气",)
        elif compact.startswith("UPDATE user_role SET"):
            self._row = None
            self.rowcount = 1
        else:
            raise AssertionError(f"unexpected SQL: {compact}")

    async def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self):
        self.fake_cursor = _FakeCursor()
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class ReincarnationTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_resets_level_and_updates_power_in_one_transaction(self):
        connection = _FakeConnection()
        with (
            patch.object(reincarnation_service, "connect_mysql", return_value=connection),
            patch.object(
                reincarnation_service, "ensure_reincarnation_schema", AsyncMock()
            ),
            patch(
                "Game_domain.abyss_service.is_role_locked_by_abyss",
                AsyncMock(return_value=False),
            ),
            patch("Tool.tool_power.update_role_power", AsyncMock()) as update_power,
        ):
            result = await reincarnation_service.reincarnate_active_role(100001)

        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertEqual(result["next_reincarnation"], 2)
        update_power.assert_awaited_once_with(connection, 100001)
        update = next(
            entry
            for entry in connection.fake_cursor.executed
            if entry[0].startswith("UPDATE user_role SET")
        )
        self.assertIn("dengji = 1", update[0])
        self.assertIn("exp = 0", update[0])
        self.assertIn("reincarnation_count = reincarnation_count + 1", update[0])
        # 1级模板100 + 上一世1000的10%，11项新裸属性均为200。
        self.assertEqual(update[1][1:12], tuple([200] * 11))


if __name__ == "__main__":
    unittest.main()
