# -*- coding: utf-8 -*-
import os
from Game_domain.gm_state import get_image_mode, set_image_mode as persist_image_mode
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


def is_web_player_portal_enabled() -> bool:
    """玩家网页入口默认关闭，仅在部署环境显式开启。"""

    return os.getenv("WEB_PLAYER_PORTAL_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

def is_image_mode() -> bool:
    """当前是否为图片模式；状态持久化到 gm_state.yaml。"""
    return get_image_mode()


def set_image_mode(enabled: bool):
    """切换图片/纯文字模式并永久保存。"""
    return persist_image_mode(enabled)
