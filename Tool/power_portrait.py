# -*- coding: utf-8 -*-
"""玩家战力立绘的附件解析、安全下载与本地规范化。"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
import re
import socket
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
from PIL import Image, ImageOps, UnidentifiedImageError


def _default_portrait_dir() -> Path:
    configured = os.getenv("POWER_PORTRAIT_DIR")
    if configured:
        return Path(configured)
    # 旧生产环境已经配置并授权 GM_STATE_FILE 所在共享目录；在尚未补充
    # POWER_PORTRAIT_DIR 时沿用该位置，避免发布切换或服务重启丢失立绘。
    gm_state_file = os.getenv("GM_STATE_FILE")
    if gm_state_file and Path(gm_state_file).is_absolute():
        return Path(gm_state_file).parent / "power_portraits"
    return Path(tempfile.gettempdir()) / "qq-rpg-power-portraits"


POWER_PORTRAIT_DIR = _default_portrait_dir()
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 36_000_000
MIN_IMAGE_SIDE = 300
NORMALIZED_LONG_SIDE = 2400
PORTRAIT_NAME_RE = re.compile(r"portrait_[0-9a-f]{32}\.jpg")


class PowerPortraitError(Exception):
    """可直接展示给玩家或 GM 的立绘业务错误。"""


def _attachment_value(attachment: Any, *names: str):
    for name in names:
        if isinstance(attachment, dict):
            value = attachment.get(name)
        else:
            value = getattr(attachment, name, None)
        if value not in (None, ""):
            return value
    return None


def image_attachments(attachments) -> list[dict]:
    """兼容 Webhook 字典与 botpy 对象，提取 QQ 图片附件。"""
    result = []
    for attachment in attachments or ():
        content_type = str(
            _attachment_value(attachment, "content_type", "type") or ""
        ).lower()
        filename = str(
            _attachment_value(attachment, "filename", "file_name", "name") or ""
        )
        url = str(
            _attachment_value(
                attachment, "url", "download_url", "file_url", "resource_url"
            )
            or ""
        ).strip()
        if url.startswith("//"):
            url = "https:" + url
        looks_like_image = content_type.startswith("image/") or content_type == "image"
        if not looks_like_image and filename:
            looks_like_image = Path(filename).suffix.lower() in {
                ".jpg", ".jpeg", ".png", ".webp"
            }
        if looks_like_image and url:
            result.append({
                "content_type": content_type,
                "filename": filename,
                "url": url,
                "width": _attachment_value(attachment, "width"),
                "height": _attachment_value(attachment, "height"),
                "size": _attachment_value(attachment, "size"),
            })
    return result


def portrait_file_path(storage_key: str, *, storage_dir: Path | str | None = None) -> Path | None:
    """只解析服务生成的随机文件名，避免目录穿越。"""
    name = str(storage_key or "")
    if not PORTRAIT_NAME_RE.fullmatch(name):
        return None
    root = Path(storage_dir) if storage_dir else POWER_PORTRAIT_DIR
    candidate = root / name
    return candidate if candidate.is_file() else None


def remove_portrait_file(storage_key: str, *, storage_dir: Path | str | None = None) -> None:
    path = portrait_file_path(storage_key, storage_dir=storage_dir)
    if path:
        try:
            path.unlink()
        except OSError:
            pass


def _public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _validate_remote_url(url: str) -> None:
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PowerPortraitError("QQ 图片附件地址无效，请重新发送图片。")
    if parsed.username or parsed.password:
        raise PowerPortraitError("图片附件地址不受支持。")
    try:
        if not _public_ip(parsed.hostname):
            raise PowerPortraitError("图片附件地址不受支持。")
        return
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise PowerPortraitError("暂时无法读取 QQ 图片，请稍后重试。") from exc
    addresses = {item[4][0] for item in infos}
    if not addresses or not all(_public_ip(address) for address in addresses):
        raise PowerPortraitError("图片附件地址不受支持。")


async def _download_image_bytes(url: str) -> tuple[bytes, str]:
    timeout = aiohttp.ClientTimeout(total=12, connect=4, sock_read=6)
    current_url = url
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for _ in range(4):
            await _validate_remote_url(current_url)
            try:
                async with session.get(
                    current_url,
                    allow_redirects=False,
                    headers={"User-Agent": "qq-rpg-power-portrait/1.0"},
                ) as response:
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise PowerPortraitError("QQ 图片附件跳转地址无效。")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status != 200:
                        raise PowerPortraitError("QQ 图片下载失败，请重新发送。")

                    declared_size = response.headers.get("Content-Length")
                    if declared_size and int(declared_size) > MAX_DOWNLOAD_BYTES:
                        raise PowerPortraitError("图片不能超过 8MB。")
                    chunks = bytearray()
                    async for chunk in response.content.iter_chunked(128 * 1024):
                        chunks.extend(chunk)
                        if len(chunks) > MAX_DOWNLOAD_BYTES:
                            raise PowerPortraitError("图片不能超过 8MB。")
                    if not chunks:
                        raise PowerPortraitError("收到的图片为空，请重新发送。")
                    return bytes(chunks), str(response.headers.get("Content-Type") or "")
            except PowerPortraitError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                raise PowerPortraitError("暂时无法读取 QQ 图片，请稍后重试。") from exc
    raise PowerPortraitError("QQ 图片附件跳转次数过多。")


def normalize_portrait_bytes(
    raw: bytes,
    storage_key: str,
    *,
    storage_dir: Path | str | None = None,
) -> dict:
    """验证真实图片格式并原子写入统一 JPEG 文件。"""
    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise PowerPortraitError("图片不能超过 8MB。")
    try:
        with Image.open(BytesIO(raw)) as source:
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            width, height = source.size
            if min(width, height) < MIN_IMAGE_SIDE:
                raise PowerPortraitError("图片尺寸过小，宽和高都需要至少 300 像素。")
            if width * height > MAX_IMAGE_PIXELS:
                raise PowerPortraitError("图片分辨率过大，请压缩后重新上传。")
            image = ImageOps.exif_transpose(source).convert("RGB")
            if max(image.size) > NORMALIZED_LONG_SIDE:
                image.thumbnail(
                    (NORMALIZED_LONG_SIDE, NORMALIZED_LONG_SIDE),
                    Image.Resampling.LANCZOS,
                )
            normalized_width, normalized_height = image.size
            root = Path(storage_dir) if storage_dir else POWER_PORTRAIT_DIR
            root.mkdir(parents=True, exist_ok=True)
            target = root / storage_key
            temporary = root / f".{storage_key}.tmp"
            image.save(temporary, format="JPEG", quality=92, optimize=True)
            os.replace(temporary, target)
    except PowerPortraitError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PowerPortraitError("文件不是有效的 JPG、PNG 或 WebP 图片。") from exc

    return {
        "storage_key": storage_key,
        "width": normalized_width,
        "height": normalized_height,
        "file_size": target.stat().st_size,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


async def download_and_store_portrait(
    attachment: dict,
    storage_key: str,
    *,
    storage_dir: Path | str | None = None,
) -> dict:
    try:
        if int(attachment.get("size") or 0) > MAX_DOWNLOAD_BYTES:
            raise PowerPortraitError("图片不能超过 8MB。")
    except (TypeError, ValueError):
        pass
    raw, response_content_type = await _download_image_bytes(attachment["url"])
    declared = str(attachment.get("content_type") or response_content_type).lower()
    if declared and not declared.startswith("image/") and declared != "image":
        raise PowerPortraitError("仅支持 JPG、PNG 或 WebP 图片。")
    return await asyncio.to_thread(
        normalize_portrait_bytes,
        raw,
        storage_key,
        storage_dir=storage_dir,
    )
