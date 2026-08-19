# -*- coding: utf-8 -*-
import asyncio
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

import output_main
from Game_main import g38_power_portrait
from Game_domain import power_portrait_service
from Tool import power_portrait


def image_bytes(size=(900, 1400), color=(65, 125, 190), image_format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=image_format)
    return buffer.getvalue()


class PowerPortraitFileTests(unittest.TestCase):
    def test_extracts_webhook_and_botpy_image_attachments(self):
        attachments = [
            {
                "content_type": "image/png",
                "url": "https://example.com/a.png",
                "filename": "a.png",
                "width": 900,
            },
            SimpleNamespace(
                content_type="image/jpeg",
                url="//example.com/b.jpg",
                filename="b.jpg",
            ),
            {"content_type": "audio/ogg", "url": "https://example.com/a.ogg"},
        ]
        result = power_portrait.image_attachments(attachments)
        self.assertEqual(2, len(result))
        self.assertEqual("a.png", result[0]["filename"])
        self.assertEqual("https://example.com/b.jpg", result[1]["url"])

    def test_normalizes_valid_image_and_only_resolves_safe_random_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            key = "portrait_" + "a" * 32 + ".jpg"
            metadata = power_portrait.normalize_portrait_bytes(
                image_bytes(), key, storage_dir=temp_dir
            )
            self.assertEqual((900, 1400), (metadata["width"], metadata["height"]))
            self.assertEqual(
                Path(temp_dir) / key,
                power_portrait.portrait_file_path(key, storage_dir=temp_dir),
            )
            self.assertIsNone(
                power_portrait.portrait_file_path("../secret.jpg", storage_dir=temp_dir)
            )
            with Image.open(Path(temp_dir) / key) as stored:
                self.assertEqual("JPEG", stored.format)

    def test_rejects_fake_or_too_small_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            key = "portrait_" + "b" * 32 + ".jpg"
            with self.assertRaises(power_portrait.PowerPortraitError):
                power_portrait.normalize_portrait_bytes(b"not-an-image", key, storage_dir=temp_dir)
            with self.assertRaises(power_portrait.PowerPortraitError):
                power_portrait.normalize_portrait_bytes(
                    image_bytes((200, 600)), key, storage_dir=temp_dir
                )

    def test_download_rejects_non_image_declared_content_type(self):
        attachment = {
            "url": "https://example.com/file.bin",
            "content_type": "application/octet-stream",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            power_portrait,
            "_download_image_bytes",
            AsyncMock(return_value=(image_bytes(), "image/png")),
        ):
            with self.assertRaises(power_portrait.PowerPortraitError):
                asyncio.run(
                    power_portrait.download_and_store_portrait(
                        attachment,
                        "portrait_" + "c" * 32 + ".jpg",
                        storage_dir=temp_dir,
                    )
                )


class PowerPortraitCommandTests(unittest.TestCase):
    def test_commands_are_registered(self):
        self.assertEqual(
            ("更换战力立绘", ""), asyncio.run(output_main.jiance("更换战力立绘"))
        )
        self.assertEqual(
            ("立绘状态", ""), asyncio.run(output_main.jiance("立绘状态"))
        )
        self.assertEqual(
            ("GM驳回立绘", "12-人物主体不清晰"),
            asyncio.run(output_main.jiance("GM驳回立绘 12-人物主体不清晰")),
        )

    def test_player_route_forwards_qq_attachments_and_request_id(self):
        attachments = [{"content_type": "image/png", "url": "https://example.com/a.png"}]
        handler = AsyncMock(return_value={"type": "markdown", "content": "ok"})
        with patch.object(output_main, "openid_to_uid", AsyncMock(return_value=10001)), patch.object(
            output_main, "power_portrait_upload", handler
        ):
            result = asyncio.run(
                output_main.content(
                    "更换战力立绘",
                    "",
                    "OPENID",
                    request_id="MSG-1",
                    attachments=attachments,
                )
            )
        self.assertEqual("ok", result["content"])
        handler.assert_awaited_once_with(
            10001, attachments=attachments, request_id="MSG-1"
        )

    def test_upload_intent_turns_next_plain_image_into_upload_command(self):
        power_portrait_service.begin_upload_intent(10002)
        attachment = [{"content_type": "image/jpeg", "url": "https://example.com/a.jpg"}]
        with patch.object(
            g38_power_portrait, "openid_to_uid", AsyncMock(return_value=10002)
        ):
            command = asyncio.run(
                g38_power_portrait.resolve_power_portrait_message(
                    "", "OPENID", attachment
                )
            )
        self.assertEqual("更换战力立绘", command)
        self.assertTrue(power_portrait_service.has_upload_intent(10002))
        power_portrait_service.consume_upload_intent(10002)

    def test_plain_group_image_is_accepted_while_upload_intent_is_active(self):
        power_portrait_service.begin_upload_intent(10004)
        attachment = [{"content_type": "image/jpeg", "url": "https://example.com/a.jpg"}]
        with patch.object(
            g38_power_portrait, "openid_to_uid", AsyncMock(return_value=10004)
        ):
            should_reply = asyncio.run(
                output_main.should_reply_to_full_group_message(
                    "", "OPENID", attachment
                )
            )
        self.assertTrue(should_reply)
        power_portrait_service.consume_upload_intent(10004)

    def test_upload_without_attachment_explains_default_image_behavior(self):
        result = asyncio.run(
            g38_power_portrait.power_portrait_upload.__wrapped__(10003, "", None, None)
        )
        self.assertIn("5 分钟内直接发送一张图片", result["content"])
        self.assertIn("审核通过前", result["content"])
        self.assertTrue(power_portrait_service.has_upload_intent(10003))
        power_portrait_service.consume_upload_intent(10003)

    @patch("output_main.is_image_mode", return_value=False)
    def test_gm_review_image_survives_global_image_mode_off(self, _mock_mode):
        result = output_main.apply_image_mode(
            {
                "type": "markdown",
                "content": "![待审立绘](https://example.invalid/portrait.jpg)",
                "force_image": True,
            }
        )
        self.assertIn("![待审立绘]", result["content"])


class PowerPortraitMigrationTests(unittest.TestCase):
    def test_migration_contains_audit_and_queue_indexes(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "数据库源文件"
            / "p14_power_portrait.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS power_portrait_submission", migration)
        self.assertIn("platform_request_id", migration)
        self.assertIn("reviewed_by", migration)
        self.assertIn("idx_power_portrait_queue", migration)
        self.assertNotIn("DROP TABLE", migration.upper())


if __name__ == "__main__":
    unittest.main()
