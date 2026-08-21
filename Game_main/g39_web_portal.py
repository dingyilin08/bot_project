# -*- coding: utf-8 -*-
"""QQ 侧签发网页版一次性绑定码。"""

import logging

from config import DOMAIN
from func.pd_func import pd_reg_func
from Game_domain.web_auth_service import (
    ADMIN_SCOPE,
    PLAYER_SCOPE,
    WebAuthError,
    issue_link_code,
)


LOGGER = logging.getLogger(__name__)


def _binding_message(result: dict, *, admin: bool) -> dict:
    title = "管理端绑定" if admin else "网页版绑定"
    path = "/admin" if admin else "/play"
    minutes = max(1, int(result["expires_in"]) // 60)
    content = (
        f"##### 🔐 {title}\n\n"
        f"**UID：** {result['uid']}\n\n"
        f"**一次性绑定码：** `{result['code']}`\n\n"
        f"> 绑定码 {minutes} 分钟内有效，使用一次后立即失效。请勿转发或截图公开。\n\n"
        f"网页入口：{DOMAIN}{path}"
    )
    return {"type": "markdown", "content": content}


@pd_reg_func
async def web_player_link(uid, qz):
    try:
        return _binding_message(await issue_link_code(uid, PLAYER_SCOPE), admin=False)
    except WebAuthError as exc:
        return {"type": "markdown", "content": f"##### 网页绑定失败\n\n{exc}"}
    except Exception:
        LOGGER.exception("创建玩家网页绑定码失败: uid=%s", uid)
        return {
            "type": "markdown",
            "content": "##### 网页绑定失败\n\n网页服务尚未完成初始化，请联系管理员执行 p15_web_portal.sql。",
        }


@pd_reg_func
async def web_admin_link(uid, qz):
    try:
        return _binding_message(await issue_link_code(uid, ADMIN_SCOPE), admin=True)
    except WebAuthError as exc:
        return {"type": "markdown", "content": f"##### 管理端绑定失败\n\n{exc}"}
    except Exception:
        LOGGER.exception("创建管理端网页绑定码失败: uid=%s", uid)
        return {
            "type": "markdown",
            "content": "##### 管理端绑定失败\n\n网页服务尚未完成初始化，请先执行 p15_web_portal.sql。",
        }
