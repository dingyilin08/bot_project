# -*- coding: utf-8 -*-
import os
"""
全局配置文件
更换域名时只需修改本文件中的 DOMAIN，所有图片URL、外链地址实时生效
"""

# ==================== 域名配置 ====================
# 服务器域名（图片URL、Webhook等所有外链均基于此域名）
DOMAIN = os.getenv("BOT_DOMAIN", "https://botgame.icu").rstrip("/")

# ==================== 图片配置 ====================
# 图片访问基础URL（完整图片地址 = IMG_BASE_URL + "/" + 图片文件名）
IMG_BASE_URL = f"{DOMAIN}/images"

# ==================== 管理员配置 ====================
# 管理员密令（用于图片模式切换等管理员功能的校验口令）
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# 图片模式开关（运行时可变状态）
# True = 正常图片模式（回复中加载图片）；False = 纯文字回复模式（不加载图片）
# 注意：该状态保存在内存中，服务重启后自动恢复为图片模式
_IMAGE_MODE_ENABLED = True


def is_image_mode() -> bool:
    """当前是否为图片模式（True=加载图片，False=纯文字模式）"""
    return _IMAGE_MODE_ENABLED


def set_image_mode(enabled: bool):
    """切换图片/纯文字模式（管理员功能，需密令验证）"""
    global _IMAGE_MODE_ENABLED
    _IMAGE_MODE_ENABLED = enabled
