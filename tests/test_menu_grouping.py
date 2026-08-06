import unittest

from Game_main import g0_menu
from output_main import jiance


class MenuGroupingTests(unittest.IsolatedAsyncioTestCase):
    async def test_progression_menus_expose_real_effect_actions(self):
        party = (await g0_menu.show_party_menu.__wrapped__(1, ""))["content"]
        self.assertIn("锋矢·前列伤害+8%", party)
        self.assertIn("队伍战斗行动 技能 1", party)
        self.assertIn("队伍战斗行动 调息", party)

        estate = (await g0_menu.show_estate_menu.__wrapped__(1, ""))["content"]
        for command in ("洞府升级 聚灵阵", "洞府升级 炼器台", "洞府升级 灵兽园", "洞府升级 藏经阁"):
            self.assertIn(command, estate)

        sect = (await g0_menu.show_sect_menu.__wrapped__(1, ""))["content"]
        for research in ("丹道", "阵法", "御器", "秘境"):
            self.assertIn(f"宗门投票 {research}", sect)

        activities = (await g0_menu.show_activity_menu.__wrapped__(1, ""))["content"]
        self.assertIn("因果印记", activities)
        self.assertIn("赛季奖励", activities)

        beasts = (await g0_menu.show_spirit_beast_menu.__wrapped__(1, ""))["content"]
        self.assertIn("洞府", beasts)

        special = (await g0_menu.show_role_special_menu.__wrapped__(1, ""))["content"]
        self.assertIn("专属组合 背包", special)

    async def test_new_system_menus_are_parameterless_commands(self):
        for command in ("队伍菜单", "灵兽菜单", "洞府菜单", "专属养成菜单", "祈愿菜单", "资源菜单", "坊市菜单", "活动菜单", "道途", "道途状态"):
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
        self.assertIn("text='坊市菜单'", content)
        self.assertIn("text='活动菜单'", content)
        self.assertIn("text='邀请菜单'", content)
        self.assertIn("text='日常任务'", content)
        self.assertIn("text='签到'", content)
        self.assertIn("text='攻略'", content)
        self.assertNotIn("text='队伍创建'", content)
        self.assertNotIn("text='灵兽寻访'", content)
        self.assertNotIn("text='世界BOSS'", content)


async def _async_value(value):
    return value
