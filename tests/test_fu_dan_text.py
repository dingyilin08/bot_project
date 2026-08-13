# -*- coding: utf-8 -*-
import unittest

from Game_domain.player_text import sanitize_player_content
from Game_main.g9_yaoyuan import _format_pill_attr_changes


class FuDanTextTests(unittest.TestCase):
    def test_base_attributes_use_player_facing_names(self):
        lines = _format_pill_attr_changes({"gongji": 38, "fangyu": 7})
        content = "\n".join(lines)

        self.assertEqual("> 攻击 + 38\n> 防御 + 7", content)
        self.assertEqual(content, sanitize_player_content(content))
        self.assertNotIn("未命名奖励", content)

    def test_rate_attributes_keep_percentage_units(self):
        lines = _format_pill_attr_changes({"baoji": 108, "xixue": 25})

        self.assertEqual(["> 暴击 + 1.08%", "> 吸血 + 0.25%"], lines)

    def test_unknown_attribute_never_leaks_internal_key(self):
        lines = _format_pill_attr_changes({"future_attr_key": 3})

        self.assertEqual(["> 属性 + 3"], lines)


if __name__ == "__main__":
    unittest.main()
