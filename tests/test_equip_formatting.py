import unittest

from Game_main.g7_equip import format_equip_bag_markdown, format_equip_detail_markdown


def make_equip():
    return {
        "id": 82,
        "part": "武器",
        "quality": "凡品",
        "level": 0,
        "template_name": "测试装备",
        "set_name": "测试套装",
        "min_level": 1,
        "create_time": "2026-08-03 12:29",
        "base_gongji": 0,
        "base_fangyu": 0,
        "base_qixue": 0,
        "base_fali": 0,
        "base_sudu": 0,
        "base_baoji": 0,
        "base_baoshang": 0,
        "base_shanbi": 0,
        "base_mingzhong": 0,
        "base_pofang": 0,
        "base_xixue": 0,
    }


class EquipFormattingTests(unittest.TestCase):
    def test_bag_buttons_use_short_labels_and_keep_complete_commands(self):
        unequipped = {**make_equip(), "is_equipped": False}
        equipped = {**make_equip(), "id": 83, "part": "weapon", "is_equipped": True}
        content = format_equip_bag_markdown(
            [unequipped, equipped],
            1,
            1,
            {"id": 1, "name": "测试角色", "level": 1},
        )

        self.assertIn("text='穿戴装备 82' show='穿戴'", content)
        self.assertIn("text='装备详情 82' show='详情'", content)
        self.assertIn("text='强化装备 82' show='强化'", content)
        self.assertIn("text='出售装备 82' show='出售'", content)
        self.assertIn("text='卸下装备 武器' show='卸下'", content)

    def test_detail_buttons_format_for_unequipped_item(self):
        content = format_equip_detail_markdown(make_equip(), {})

        self.assertIn("穿戴装备 82", content)
        self.assertIn("强化装备 82", content)
        self.assertIn("出售装备 82", content)

    def test_detail_buttons_format_for_equipped_item(self):
        content = format_equip_detail_markdown(
            make_equip(), {}, equipped_info={"id": 7, "name": "测试角色", "level": 1}
        )

        self.assertIn("卸下装备", content)
        self.assertIn("强化装备 82", content)


if __name__ == "__main__":
    unittest.main()
