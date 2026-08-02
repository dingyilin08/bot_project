import asyncio
import re
import unittest

import output_main
from Game_main.g28_player_guide import (
    beginner_guide,
    combat_guide,
    guide_directory,
    resource_guide,
    role_guide,
)
from output_main import jiance


GUIDES = (
    ("攻略", guide_directory, "攻略阁"),
    ("开荒攻略", beginner_guide, "开荒攻略"),
    ("角色攻略", role_guide, "角色攻略"),
    ("战斗攻略", combat_guide, "战斗攻略"),
    ("资源攻略", resource_guide, "资源攻略"),
)


class PlayerGuideTests(unittest.TestCase):
    def test_directory_links_to_four_guides(self):
        content = asyncio.run(guide_directory(1))["content"]
        for command in ("开荒攻略", "角色攻略", "战斗攻略", "资源攻略"):
            self.assertIn(f"text='{command}'", content)

    def test_each_guide_is_markdown_with_navigation(self):
        for _, handler, title in GUIDES:
            response = asyncio.run(handler(1))
            self.assertEqual(response["type"], "markdown")
            self.assertIn(title, response["content"])
            self.assertIn("qqbot-cmd-input", response["content"])
            if handler is not guide_directory:
                self.assertIn("text='攻略'", response["content"])

    def test_every_interactive_button_uses_a_registered_command(self):
        for _, handler, _ in GUIDES:
            content = asyncio.run(handler(1))["content"]
            commands = re.findall(r"<qqbot-cmd-input text='([^']+)'", content)
            self.assertTrue(commands)
            for command in commands:
                parsed, _ = asyncio.run(jiance(command))
                self.assertTrue(parsed, f"未注册的攻略按钮：{command}")

    def test_legacy_new_player_guide_alias_remains_registered(self):
        self.assertEqual(asyncio.run(jiance("新手攻略")), ("新手攻略", ""))


class PlayerGuideRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_guide_commands_are_parameterless(self):
        for command, _, _ in GUIDES:
            self.assertEqual(await jiance(command), (command, ""))

    async def test_content_dispatches_to_the_four_guides(self):
        original = output_main.openid_to_uid

        async def fake_openid_to_uid(openid):
            return 1

        output_main.openid_to_uid = fake_openid_to_uid
        try:
            for command, _, title in GUIDES:
                response = await output_main.content(command, "", "test-openid")
                self.assertIn(title, response["content"])
            legacy = await output_main.content("新手攻略", "", "test-openid")
            self.assertIn("开荒攻略", legacy["content"])
        finally:
            output_main.openid_to_uid = original


if __name__ == "__main__":
    unittest.main()
