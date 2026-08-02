# -*- coding: utf-8 -*-
from copy import deepcopy
import unittest

from Tool.qq_official_group import (
    OFFICIAL_GROUP_NOTICE,
    append_official_group_notice,
    attach_official_group_notice,
)


class OfficialGroupNoticeTests(unittest.TestCase):
    def test_plain_text_gets_notice_at_the_end(self):
        result = attach_official_group_notice("道友，今日签到成功。")

        self.assertEqual(
            f"道友，今日签到成功。\n\n{OFFICIAL_GROUP_NOTICE}",
            result,
        )

    def test_empty_text_becomes_notice(self):
        self.assertEqual(
            OFFICIAL_GROUP_NOTICE,
            attach_official_group_notice(""),
        )

    def test_markdown_dict_gets_notice_without_mutating_input(self):
        payload = {
            "type": "markdown",
            "content": "##### 角色信息",
            "trace_id": "trace-1",
        }
        original = deepcopy(payload)

        result = attach_official_group_notice(payload)

        self.assertIsNot(payload, result)
        self.assertEqual(original, payload)
        self.assertEqual("markdown", result["type"])
        self.assertEqual("trace-1", result["trace_id"])
        self.assertEqual(
            f"##### 角色信息\n\n{OFFICIAL_GROUP_NOTICE}",
            result["content"],
        )

    def test_markdown_keyboard_gets_notice_without_mutating_input(self):
        payload = {
            "type": "markdown_keyboard",
            "content": "请选择下一步操作",
            "keyboard": {
                "content": {
                    "rows": [{"buttons": [{"action": {"data": "角色信息"}}]}],
                },
            },
        }
        original = deepcopy(payload)

        result = attach_official_group_notice(payload)

        self.assertIsNot(payload, result)
        self.assertEqual(original, payload)
        self.assertEqual(original["keyboard"], result["keyboard"])
        self.assertEqual(
            f"请选择下一步操作\n\n{OFFICIAL_GROUP_NOTICE}",
            result["content"],
        )

    def test_append_is_idempotent_including_trailing_whitespace(self):
        once = append_official_group_notice("领取奖励成功")
        self.assertEqual(once, append_official_group_notice(once))

        with_trailing_whitespace = f"{once}  \n\t"
        self.assertEqual(
            with_trailing_whitespace,
            append_official_group_notice(with_trailing_whitespace),
        )

    def test_notice_mentioned_only_in_body_is_still_appended(self):
        content = f"可加入{OFFICIAL_GROUP_NOTICE}交流。\n这里还有后续正文。"

        result = append_official_group_notice(content)

        self.assertEqual(f"{content}\n\n{OFFICIAL_GROUP_NOTICE}", result)
        self.assertEqual(2, result.count(OFFICIAL_GROUP_NOTICE))

    def test_none_and_unknown_values_are_returned_unchanged(self):
        self.assertIsNone(attach_official_group_notice(None))

        unknown_object = object()
        self.assertIs(
            unknown_object,
            attach_official_group_notice(unknown_object),
        )

        unknown_mapping = {"type": "image", "content": {"url": "image.png"}}
        self.assertIs(
            unknown_mapping,
            attach_official_group_notice(unknown_mapping),
        )


if __name__ == "__main__":
    unittest.main()
