from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from Game_main import g0_menu, g32_abyss
from output_main import jiance


RUN = {
    "run_uuid": "run-1", "uid": 1, "run_type": "NORMAL", "layer_no": 21,
    "role_id": None, "source_world": "仙逆", "source_dungeon_id": 13,
    "rng_seed": "seed", "state": "READY", "wave_no": 1, "kill_count": 0,
    "player_hp_ratio": 1.0, "version": 0, "role_snapshot": {},
    "effect_snapshot": {}, "reward_snapshot": {}, "settlement": {},
}


class AbyssCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_commands_keep_optional_arguments(self):
        expected = {
            "深渊": ("深渊", ""),
            "深渊菜单": ("深渊菜单", ""),
            "深渊预览 21": ("深渊预览", "21"),
            "挑战深渊 21": ("挑战深渊", "21"),
            "深渊怪物": ("深渊怪物", ""),
            "挑战深渊怪物 5": ("挑战深渊怪物", "5"),
            "深渊结算": ("深渊结算", ""),
            "离开深渊": ("离开深渊", ""),
            "深渊定级 开始": ("深渊定级", "开始"),
            "深渊排行 2": ("深渊排行", "2"),
        }
        for text, parsed in expected.items():
            self.assertEqual(await jiance(text), parsed)

    async def test_preview_is_compact_and_exposes_text_and_keyboard_actions(self):
        dashboard = {"profile": {"highest_cleared_layer": 20, "total_kills": 60}, "role": {"id": 1, "name": "王林", "level": 50, "world": "仙逆"}, "run": RUN}
        with patch.object(g32_abyss, "create_preview", AsyncMock(return_value=RUN)), patch.object(
            g32_abyss, "get_dashboard", AsyncMock(return_value=dashboard)
        ), patch.object(g32_abyss, "get_source_dungeon", AsyncMock(return_value={"name": "尸阴宗分舵"})), patch.object(
            g32_abyss, "get_world_role_names", AsyncMock(return_value=["王林"])
        ):
            result = await g32_abyss.abyss_preview.__wrapped__(1, "", "21")
        content = result["content"]
        self.assertIn("深渊预览｜第21层", content)
        self.assertIn("挑战深渊 21", content)
        self.assertIn("同界，无跨界增幅", content)
        self.assertLess(len(content.splitlines()), 25)
        self.assertIn("挑战深渊 21", [item["command"] for item in result["keyboard_commands"]])

    async def test_monster_page_uses_one_line_per_monster_and_buttons(self):
        run = dict(RUN, state="FIGHTING", role_snapshot={"world": "仙逆"})
        monsters = [
            {"slot_no": index, "name": f"怪物{index}", "type": "boss" if index == 5 else "normal", "state": "READY"}
            for index in range(1, 6)
        ]
        with patch.object(g32_abyss, "get_active_run", AsyncMock(return_value=run)), patch.object(
            g32_abyss, "get_run_monsters", AsyncMock(return_value=monsters)
        ):
            result = await g32_abyss._render_monsters(1)
        for index in range(1, 6):
            self.assertIn(f"挑战深渊怪物 {index}", result["content"])
        self.assertIn("首领", result["content"])
        self.assertLessEqual(len(result["keyboard_commands"]), 10)

    async def test_activity_and_dungeon_menus_link_to_abyss(self):
        activity = (await g0_menu.show_activity_menu.__wrapped__(1, ""))["content"]
        self.assertIn("text='深渊'", activity)
        self.assertIn("text='深渊排行'", activity)
        with patch.object(g0_menu, "get_current_role_info", AsyncMock(return_value=None)), patch(
            "Game_main.g6_dungeon.get_daily_remaining_count", AsyncMock(return_value=20)
        ):
            dungeon = (await g0_menu.show_dungeon_menu.__wrapped__(1, ""))["content"]
        self.assertIn("轮海深渊", dungeon)

    def test_schema_has_active_run_and_reward_safety_fields(self):
        root = Path(__file__).resolve().parents[1]
        schema = (root / "数据库源文件" / "p6_abyss.sql").read_text(encoding="utf-8")
        self.assertIn("UNIQUE KEY `uk_abyss_active_uid`", schema)
        self.assertIn("UNIQUE KEY `uk_abyss_wave_slot`", schema)
        self.assertIn("reward_snapshot_json", schema)
        self.assertIn("settlement_json", schema)


if __name__ == "__main__":
    unittest.main()
