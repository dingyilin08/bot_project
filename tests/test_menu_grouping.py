import unittest

from Game_main import g0_menu
from output_main import jiance


class MenuGroupingTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_system_menus_are_parameterless_commands(self):
        for command in ("队伍菜单", "灵兽菜单", "洞府菜单", "专属养成菜单", "祈愿菜单", "资源菜单", "活动菜单", "道途", "道途状态"):
            self.assertEqual((await jiance(command))[0], command)

    async def test_main_menu_uses_system_entries_not_operation_buttons(self):
        original_player = g0_menu.get_player_basic_info
        original_role = g0_menu.get_current_role_info
        g0_menu.get_player_basic_info = lambda uid: _async_value({"name": "测试", "lingshi": 1, "xianyu": 0})
        g0_menu.get_current_role_info = lambda uid: _async_value(None)
        try:
            content = (await g0_menu.show_main_menu.__wrapped__(1, ""))["content"]
        finally:
            g0_menu.get_player_basic_info = original_player
            g0_menu.get_current_role_info = original_role
        self.assertIn("text='队伍菜单'", content)
        self.assertIn("text='灵兽菜单'", content)
        self.assertIn("text='洞府菜单'", content)
        self.assertIn("text='专属养成菜单'", content)
        self.assertIn("text='祈愿菜单'", content)
        self.assertIn("text='资源菜单'", content)
        self.assertIn("text='活动菜单'", content)
        self.assertIn("text='日常任务'", content)
        self.assertIn("text='签到'", content)
        self.assertNotIn("text='队伍创建'", content)
        self.assertNotIn("text='灵兽寻访'", content)
        self.assertNotIn("text='世界BOSS'", content)


async def _async_value(value):
    return value
