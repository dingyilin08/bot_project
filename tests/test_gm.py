# -*- coding: utf-8 -*-
import asyncio
import os
import tempfile
import unittest
from pathlib import Path

import yaml

from Game_domain import gm_state
from Game_domain.gm_service import (
    GMError,
    authenticate_admin,
    parse_item_grant,
    parse_xianyu_grant,
)
from Game_main import g24_gm
import output_main
from output_main import jiance, redact_sensitive_content
from Tool.qq_keyboard import attach_keyboard


class GMStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = gm_state.STATE_PATH
        gm_state.STATE_PATH = Path(self.temp_dir.name) / "gm_state.yaml"

    def tearDown(self):
        gm_state.STATE_PATH = self.original_path
        self.temp_dir.cleanup()

    def test_admin_and_image_mode_survive_yaml_reload(self):
        self.assertFalse(gm_state.is_admin(10001))
        self.assertTrue(gm_state.get_image_mode())
        self.assertTrue(gm_state.grant_admin(10001))
        self.assertTrue(gm_state.set_image_mode(False))
        data = yaml.safe_load(gm_state.STATE_PATH.read_text(encoding="utf-8"))
        self.assertEqual([10001], data["admins"])
        self.assertFalse(data["image_mode_enabled"])
        self.assertTrue(gm_state.is_admin(10001))
        self.assertFalse(gm_state.get_image_mode())

    def test_correct_password_permanently_grants_admin(self):
        authenticate_admin(10002, "Secret42", "secret42")
        self.assertTrue(gm_state.is_admin(10002))
        with self.assertRaises(GMError):
            authenticate_admin(10003, "wrong", "secret42")
        self.assertFalse(gm_state.is_admin(10003))

    def test_empty_server_password_never_authenticates(self):
        with self.assertRaises(GMError):
            authenticate_admin(10001, "", "")

    def test_production_default_uses_shared_directory_not_release_directory(self):
        original_shared = gm_state.PRODUCTION_SHARED_LOG_DIR
        original_path = os.environ.pop("GM_STATE_FILE", None)
        try:
            gm_state.PRODUCTION_SHARED_LOG_DIR = Path(self.temp_dir.name)
            self.assertEqual(
                Path(self.temp_dir.name) / "gm_state.yaml",
                gm_state._default_state_path(),
            )
            os.environ["GM_STATE_FILE"] = "gm_state.yaml"
            self.assertEqual(
                Path(self.temp_dir.name) / "gm_state.yaml",
                gm_state._default_state_path(),
            )
        finally:
            gm_state.PRODUCTION_SHARED_LOG_DIR = original_shared
            if original_path is None:
                os.environ.pop("GM_STATE_FILE", None)
            else:
                os.environ["GM_STATE_FILE"] = original_path


class GMCommandTests(unittest.TestCase):
    def test_grant_parsers(self):
        self.assertEqual((10086, "九转丹", 5), parse_item_grant("10086-九转丹-5"))
        self.assertEqual((10086, "12", 8), parse_item_grant("10086-12-8"))
        self.assertEqual((10086, 1600), parse_xianyu_grant("10086-1600"))
        with self.assertRaises(GMError):
            parse_item_grant("10086-九转丹-0")
        with self.assertRaises(GMError):
            parse_xianyu_grant("10086--1")

    def test_commands_are_registered(self):
        self.assertEqual(("GM菜单", ""), asyncio.run(jiance("GM菜单")))
        self.assertEqual(("GM验证", "密令"), asyncio.run(jiance("GM验证 密令")))
        self.assertEqual(("GM发放物品", "10086-九转丹-5"),
                         asyncio.run(jiance("GM发放物品 10086-九转丹-5")))
        self.assertEqual(("GM发放仙玉", "10086-1600"),
                         asyncio.run(jiance("GM发放仙玉 10086-1600")))

    def test_sensitive_commands_are_redacted_from_logs(self):
        original = output_main.ADMIN_PASSWORD
        output_main.ADMIN_PASSWORD = "Secret42"
        try:
            self.assertEqual("[GM密令已隐藏]", redact_sensitive_content("secret42"))
            self.assertEqual("GM验证 [密令已隐藏]", redact_sensitive_content("GM验证 secret42"))
            self.assertEqual("关闭图片模式 [密令已隐藏]", redact_sensitive_content("关闭图片模式 secret42"))
            self.assertEqual("GM发放仙玉 10086-60", redact_sensitive_content("GM发放仙玉 10086-60"))
        finally:
            output_main.ADMIN_PASSWORD = original

    def test_gm_menu_declares_real_message_buttons(self):
        original_admin = g24_gm.is_admin
        original_mode = g24_gm.is_image_mode
        g24_gm.is_admin = lambda uid: True
        g24_gm.is_image_mode = lambda: False
        try:
            result = asyncio.run(g24_gm.gm_menu.__wrapped__(10001, ""))
            result = attach_keyboard(result, is_group=False)
        finally:
            g24_gm.is_admin = original_admin
            g24_gm.is_image_mode = original_mode
        self.assertEqual("markdown_keyboard", result["type"])
        buttons = [button for row in result["keyboard"]["content"]["rows"] for button in row["buttons"]]
        self.assertEqual("GM发放物品", buttons[0]["action"]["data"])
        self.assertFalse(buttons[0]["action"]["enter"])

    def test_migration_contains_audited_idempotent_operation_table(self):
        root = Path(__file__).resolve().parents[1]
        migration = next(root.rglob("p1_gm.sql")).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS gm_operation_log", migration)
        self.assertIn("UNIQUE KEY uk_gm_operation_request", migration)


if __name__ == "__main__":
    unittest.main()
