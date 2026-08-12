# -*- coding: utf-8 -*-
"""战力仙鉴图片的本地渲染器。

模板和角色立绘均来自项目 ``images`` 目录；玩家请求时只做 Pillow 合成，
不会调用网络绘图服务。输出文件按数据指纹缓存，相同数据可直接复用。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = PROJECT_ROOT / "images"
BACKGROUND_PATH = IMAGES_DIR / "power_card_background.png"
PACKAGED_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSansCJKsc-Regular.otf"
POWER_CARD_CACHE_DIR = Path(
    os.getenv("POWER_CARD_CACHE_DIR", str(Path(tempfile.gettempdir()) / "qq-rpg-power-cards"))
)
CARD_SIZE = (1080, 1350)
TEMPLATE_VERSION = "power-card-v1.1"

ROLE_IMAGE_FILES = {
    "萧炎": "xiaoyan.png",
    "王林": "wanglin.png",
    "韩立": "hanli.png",
    "石昊": "shihao.png",
    "叶凡": "yefan.png",
    # 历史素材文件名为 mengzhuan.png，保留兼容。
    "孟川": "mengzhuan.png",
}

FONT_CANDIDATES = {
    "regular": (
        str(PACKAGED_FONT_PATH),
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ),
    "bold": (
        str(PACKAGED_FONT_PATH),
        "C:/Windows/Fonts/msyhbd.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ),
    "display": (
        "C:/Windows/Fonts/STXINGKA.TTF",
        "C:/Windows/Fonts/simkai.ttf",
        str(PACKAGED_FONT_PATH),
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ),
}


@lru_cache(maxsize=64)
def _font(size: int, style: str = "regular") -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES.get(style, FONT_CANDIDATES["regular"]):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError("未找到可用的中文字体，请安装 Noto Sans CJK 或文泉驿正黑")


def _number(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def format_number(value: Any) -> str:
    """为图片压缩大数字，同时保留小数辨识度。"""
    number = _number(value)
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿"
    if abs(number) >= 10_000:
        digits = 1 if abs(number) < 1_000_000 else 0
        return f"{number / 10_000:.{digits}f}万"
    return f"{number:,}"


def _short_text(value: Any, limit: int, default: str = "未配置") -> str:
    text = str(value or default).strip().replace("\n", " ")
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def _rounded_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill=(247, 252, 249, 218),
    outline=(80, 155, 145, 180),
    radius=20,
    width=2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _fit_role_image(role_path: Path) -> Image.Image:
    role = Image.open(role_path).convert("RGB")
    role = ImageEnhance.Color(role).enhance(0.92)
    role = ImageEnhance.Contrast(role).enhance(0.94)
    portrait = ImageOps.fit(role, (395, 800), method=Image.Resampling.LANCZOS, centering=(0.5, 0.48))
    veil = Image.new("RGBA", portrait.size, (244, 252, 250, 0))
    veil_alpha = Image.new("L", portrait.size, 0)
    alpha_pixels = veil_alpha.load()
    for y in range(portrait.height):
        bottom_fade = max(0, min(100, int((y - 680) * 0.84)))
        for x in range(portrait.width):
            edge_fade = max(0, int((x - 330) * 1.45))
            alpha_pixels[x, y] = min(120, max(bottom_fade, edge_fade))
    veil.putalpha(veil_alpha)
    portrait = Image.alpha_composite(portrait.convert("RGBA"), veil)
    mask = Image.new("L", portrait.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, portrait.width - 1, portrait.height - 1), 24, fill=255)
    portrait.putalpha(mask)
    return portrait


def _draw_label_value(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    value: Any,
    *,
    width: int = 220,
) -> None:
    draw.text((x, y), label, font=_font(23), fill=(70, 105, 103))
    value_text = _short_text(value, 13)
    value_font = _font(27, "bold")
    value_box = draw.textbbox((0, 0), value_text, font=value_font)
    draw.text((x + width - (value_box[2] - value_box[0]), y - 2), value_text, font=value_font, fill=(30, 73, 79))


def _asset_fingerprint(path: Path) -> str:
    if not path.is_file():
        return "missing"
    stat = path.stat()
    return f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"


def power_card_cache_name(data: dict[str, Any], images_dir: Path | str = IMAGES_DIR) -> str:
    """返回不暴露 UID 的稳定缓存文件名。"""
    images_path = Path(images_dir)
    role_path = images_path / ROLE_IMAGE_FILES.get(str(data.get("role_name")), "")
    payload = {
        "template": TEMPLATE_VERSION,
        "data": data,
        "background": _asset_fingerprint(images_path / BACKGROUND_PATH.name),
        "role": _asset_fingerprint(role_path),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"power_card_{hashlib.sha256(encoded).hexdigest()[:24]}.jpg"


def cached_power_card_path(filename: str) -> Path | None:
    """安全解析运行时卡片；仅允许渲染器生成的指纹文件名。"""
    if not re.fullmatch(r"power_card_[0-9a-f]{24}\.jpg", str(filename or "")):
        return None
    candidate = POWER_CARD_CACHE_DIR / filename
    return candidate if candidate.is_file() else None


def render_power_card(
    data: dict[str, Any],
    *,
    images_dir: Path | str = IMAGES_DIR,
    output_dir: Path | str | None = None,
) -> Path:
    """渲染并缓存一张 1080×1350 JPEG 战力仙鉴。"""
    images_path = Path(images_dir)
    output_path = Path(output_dir) if output_dir else POWER_CARD_CACHE_DIR
    output_path.mkdir(parents=True, exist_ok=True)
    target = output_path / power_card_cache_name(data, images_path)
    if target.is_file() and target.stat().st_size > 20_000:
        return target

    background_path = images_path / BACKGROUND_PATH.name
    if not background_path.is_file():
        raise FileNotFoundError(f"战力图片模板不存在：{background_path}")
    canvas = ImageOps.fit(
        Image.open(background_path).convert("RGB"),
        CARD_SIZE,
        method=Image.Resampling.LANCZOS,
    ).convert("RGBA")

    role_name = str(data.get("role_name") or "未知角色")
    role_path = images_path / ROLE_IMAGE_FILES.get(role_name, "")
    if role_path.is_file():
        canvas.alpha_composite(_fit_role_image(role_path), (66, 286))

    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    ink = (24, 69, 77)
    jade = (39, 139, 128)
    gold = (181, 133, 52)
    muted = (82, 112, 108)

    # 顶部题签
    title = "问道诸天 · 战力仙鉴"
    title_font = _font(57, "display")
    title_box = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((1080 - (title_box[2] - title_box[0])) / 2, 57), title, font=title_font, fill=ink)
    subtitle = f"{_short_text(data.get('player_name'), 12, '无名道友')}  ·  当前出战阵容"
    subtitle_font = _font(22)
    subtitle_box = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    draw.text(((1080 - (subtitle_box[2] - subtitle_box[0])) / 2, 129), subtitle, font=subtitle_font, fill=muted)

    # 左侧角色题名
    _rounded_panel(draw, (76, 1000, 454, 1106), fill=(239, 249, 246, 230), outline=(188, 145, 57, 205), radius=18)
    role_font = _font(42, "bold")
    role_box = draw.textbbox((0, 0), role_name, font=role_font)
    draw.text((265 - (role_box[2] - role_box[0]) / 2, 1011), role_name, font=role_font, fill=ink)
    role_meta = f"{_short_text(data.get('stage'), 10, '未定境')}  ·  Lv.{_number(data.get('level'))}"
    meta_font = _font(20)
    meta_box = draw.textbbox((0, 0), role_meta, font=meta_font)
    draw.text((265 - (meta_box[2] - meta_box[0]) / 2, 1064), role_meta, font=meta_font, fill=muted)

    # 右侧总战力与排名
    _rounded_panel(draw, (552, 286, 1042, 435), fill=(246, 252, 249, 226), outline=(188, 145, 57, 205), radius=22)
    draw.text((583, 307), "当前总战力", font=_font(24), fill=muted)
    total_text = format_number(data.get("total_power"))
    draw.text((580, 336), total_text, font=_font(52, "bold"), fill=(27, 107, 103))
    rank = _number(data.get("rank"))
    total_players = _number(data.get("total_players"))
    rank_text = f"全服第 {rank or '-'} 名 / {total_players or '-'} 人"
    draw.text((1012, 398), rank_text, font=_font(18), fill=gold, anchor="ra")

    # 当前属性
    _rounded_panel(draw, (552, 454, 1042, 675), radius=20)
    draw.text((580, 471), "当前角色属性", font=_font(28, "bold"), fill=ink)
    draw.line((580, 510, 1014, 510), fill=(104, 175, 164, 130), width=2)
    stats = data.get("stats") or {}
    stat_items = (
        ("攻击", stats.get("攻击", 0)), ("防御", stats.get("防御", 0)),
        ("气血", stats.get("气血", 0)), ("法力", stats.get("法力", 0)),
        ("速度", stats.get("速度", 0)), ("暴击", stats.get("暴击", "0%")),
    )
    for index, (label, value) in enumerate(stat_items):
        col = index % 2
        row = index // 2
        _draw_label_value(draw, 580 + col * 225, 526 + row * 47, label, value, width=198)

    # 六项战力构成
    _rounded_panel(draw, (552, 693, 1042, 1020), radius=20)
    draw.text((580, 710), "战力构成", font=_font(28, "bold"), fill=ink)
    components = data.get("components") or []
    values = [_number(item.get("value")) for item in components]
    max_value = max(values or [1]) or 1
    bar_colors = ((54, 146, 137), (72, 159, 184), (197, 151, 63), (118, 145, 194), (165, 106, 181), (92, 160, 102))
    for index, item in enumerate(components[:6]):
        y = 758 + index * 40
        label = _short_text(item.get("label"), 6, "分项")
        value = _number(item.get("value"))
        percent = float(item.get("percent") or 0)
        draw.text((580, y), label, font=_font(20), fill=ink)
        draw.rounded_rectangle((668, y + 5, 861, y + 23), 9, fill=(209, 225, 220, 190))
        bar_width = max(5, int(193 * value / max_value)) if value else 0
        if bar_width:
            draw.rounded_rectangle((668, y + 5, 668 + bar_width, y + 23), 9, fill=bar_colors[index])
        draw.text((880, y - 1), format_number(value), font=_font(19, "bold"), fill=ink)
        draw.text((1014, y + 1), f"{percent:.1f}%", font=_font(16), fill=muted, anchor="ra")

    # 养成摘要
    _rounded_panel(draw, (552, 1037, 1042, 1163), radius=19)
    draw.text((580, 1052), "养成概览", font=_font(25, "bold"), fill=ink)
    draw.text((580, 1090), f"本源  {_short_text(data.get('benyuan'), 13)}", font=_font(19), fill=muted)
    draw.text((805, 1090), f"装备  {_short_text(data.get('equipment'), 12)}", font=_font(19), fill=muted)
    draw.text((580, 1122), f"技能  {_short_text(data.get('skills'), 29)}", font=_font(18), fill=muted)

    # 底栏
    beast = _short_text(data.get("beast"), 22, "暂无主契灵兽")
    draw.text((84, 1260), f"主契灵兽  ·  {beast}", font=_font(21, "bold"), fill=ink)
    draw.text((996, 1260), "战力数据实时结算", font=_font(18), fill=muted, anchor="ra")
    draw.text((540, 1304), "发送「战力图片」可随时刷新", font=_font(18), fill=(83, 124, 119), anchor="mm")

    canvas = Image.alpha_composite(canvas, overlay).convert("RGB")
    temp = output_path / f".{target.name}.{os.getpid()}.{uuid4().hex}.tmp"
    try:
        canvas.save(temp, format="JPEG", quality=88, optimize=True, progressive=True, subsampling=1)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)
    return target
