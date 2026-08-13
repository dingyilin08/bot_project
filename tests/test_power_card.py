# -*- coding: utf-8 -*-
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageFont

import output_main
from Tool import power_card
from Tool.power_card import CARD_SIZE, IMAGES_DIR, ROLE_IMAGE_FILES, render_power_card


def sample_card_data():
    return {
        "player_name": "凌霄道友",
        "role_name": "王林",
        "stage": "化神境",
        "level": 72,
        "total_power": 2_684_300,
        "rank": 12,
        "total_players": 1986,
        "stats": {
            "攻击": 185420, "防御": 96280, "气血": 1286000,
            "法力": 80600, "速度": 2420, "暴击": "38.65%",
        },
        "components": [
            {"label": "基础", "value": 856000, "percent": 31.9},
            {"label": "等级", "value": 310000, "percent": 11.5},
            {"label": "装备", "value": 690000, "percent": 25.7},
            {"label": "本源", "value": 364000, "percent": 13.6},
            {"label": "技能", "value": 180000, "percent": 6.7},
            {"label": "灵兽", "value": 284300, "percent": 10.6},
        ],
        "benyuan": "古神本源 Lv.24",
        "equipment": "太古套装6件",
        "skills": "寂灭指 / 黄泉升窍诀 / 因果印",
        "beast": "九曜玄麟 · 仙品",
    }


class PowerCardRenderTests(unittest.TestCase):
    def test_role_art_assets_are_available(self):
        self.assertTrue((IMAGES_DIR / "power_card_background.png").is_file())
        for filename in ROLE_IMAGE_FILES.values():
            self.assertTrue((IMAGES_DIR / filename).is_file(), filename)

    def test_production_font_candidates_include_noto_cjk(self):
        self.assertTrue(power_card.PACKAGED_FONT_PATH.is_file())
        self.assertLess(power_card.PACKAGED_FONT_PATH.stat().st_size, 20_000_000)
        self.assertTrue(any("NotoSansCJK" in item for item in power_card.FONT_CANDIDATES["regular"]))
        self.assertTrue(any("NotoSerifCJK" in item for item in power_card.FONT_CANDIDATES["display"]))

    def test_packaged_font_contains_card_punctuation(self):
        font = ImageFont.truetype(power_card.PACKAGED_FONT_PATH, size=32)
        missing_glyph = bytes(font.getmask("\U0010ffff"))
        for character in "·「」『』，。！？：；（）【】《》、—…":
            with self.subTest(character=character):
                self.assertNotEqual(missing_glyph, bytes(font.getmask(character)))

    def test_runtime_cache_path_only_accepts_fingerprinted_cards(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_name = "power_card_" + "a" * 24 + ".jpg"
            valid_path = Path(temp_dir) / valid_name
            valid_path.write_bytes(b"jpeg")
            with patch.object(power_card, "POWER_CARD_CACHE_DIR", Path(temp_dir)):
                self.assertEqual(valid_path, power_card.cached_power_card_path(valid_name))
                self.assertIsNone(power_card.cached_power_card_path("../secret.jpg"))
                self.assertIsNone(power_card.cached_power_card_path("power_card_bad.jpg"))

    def test_render_uses_content_cache_and_expected_dimensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = render_power_card(sample_card_data(), output_dir=temp_dir)
            first_mtime = first.stat().st_mtime_ns
            second = render_power_card(sample_card_data(), output_dir=temp_dir)
            self.assertEqual(first, second)
            self.assertEqual(first_mtime, second.stat().st_mtime_ns)
            self.assertGreater(first.stat().st_size, 20_000)
            with Image.open(first) as image:
                self.assertEqual(CARD_SIZE, image.size)
                self.assertEqual("JPEG", image.format)


class PowerCardCommandTests(unittest.TestCase):
    def test_power_image_command_is_registered(self):
        self.assertEqual(("战力图片", ""), asyncio.run(output_main.jiance("战力图片")))

    @patch("output_main.is_image_mode", return_value=False)
    def test_forced_power_card_survives_gm_image_mode_off(self, _mock_mode):
        content = "![战力仙鉴](https://example.invalid/card.jpg)"
        result = output_main.apply_image_mode({
            "type": "markdown",
            "content": content,
            "force_image": True,
        })
        self.assertEqual(content, result["content"])
        self.assertNotIn("force_image", result)

    @patch("output_main.is_image_mode", return_value=False)
    def test_other_images_are_still_filtered(self, _mock_mode):
        result = output_main.apply_image_mode({
            "type": "markdown",
            "content": "说明\n![普通图片](https://example.invalid/a.jpg)",
        })
        self.assertEqual("说明\n", result["content"])


if __name__ == "__main__":
    unittest.main()
