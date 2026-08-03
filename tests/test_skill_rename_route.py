import unittest

import output_main
from Game_main.g5_skill import parse_skill_rename_param


class SkillRenameParserTests(unittest.TestCase):
    def test_parse_valid_name(self):
        self.assertEqual(parse_skill_rename_param(" 10001-烈焰斩 "), (10001, "烈焰斩", None))

    def test_parse_rejects_invalid_id_empty_placeholder_and_long_name(self):
        for value in (
            "烈焰斩",
            "0-烈焰斩",
            "1-",
            "1-未命名",
            "1-" + "道" * 31,
            "1-烈焰斩\n<qqbot-cmd-input>",
        ):
            with self.subTest(value=value):
                skill_id, name, error = parse_skill_rename_param(value)
                self.assertIsNone(skill_id)
                self.assertIsNone(name)
                self.assertTrue(error)


class SkillRenameRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_parser_preserves_name_separator(self):
        self.assertEqual(
            await output_main.jiance("技能命名 10001-烈焰斩"),
            ("技能命名", "10001-烈焰斩"),
        )

    async def test_content_routes_to_rename_handler(self):
        original_uid = output_main.openid_to_uid
        original_rename = output_main.rename_skill
        calls = []

        async def fake_uid(_openid):
            return 7001

        async def fake_rename(uid, param):
            calls.append((uid, param))
            return {"type": "markdown", "content": "命名完成"}

        output_main.openid_to_uid = fake_uid
        output_main.rename_skill = fake_rename
        try:
            result = await output_main.content("技能命名", "10001-烈焰斩", "openid")
        finally:
            output_main.openid_to_uid = original_uid
            output_main.rename_skill = original_rename

        self.assertEqual(result["content"], "命名完成")
        self.assertEqual(calls, [(7001, "10001-烈焰斩")])


if __name__ == "__main__":
    unittest.main()
