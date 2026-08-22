# -*- coding: utf-8 -*-
"""低等级玩家删号指令。"""

import logging

from func.pd_func import reg_xz_func
from Game_domain.account_deletion_service import (
    ACCOUNT_DELETION_LEVEL_LIMIT,
    AccountDeletionError,
    delete_player_account,
    get_account_deletion_preview,
)


LOGGER = logging.getLogger(__name__)
CONFIRMATION_TEXT = "确认删除"


def render_account_deletion_preview(preview: dict) -> str:
    return (
        "##### ⚠️ 永久删除账号\n\n"
        f"**UID：** {preview['uid']}\n"
        f"**玩家：** {preview['player_name']}\n"
        f"**已拥有角色：** {preview['role_count']}名\n"
        f"**最高角色等级：** {preview['highest_role_level']}级\n\n"
        "> 删除后，角色、货币、背包、装备、修炼、灵兽、队伍关系和玩法进度均不可恢复；"
        "奖励、兑换、交易与管理审计流水会保留。\n\n"
        f"> 只有所有角色均未达到{ACCOUNT_DELETION_LEVEL_LIMIT}级时可以删号，确认时会再次校验。\n\n"
        f"<qqbot-cmd-input text='删号 {CONFIRMATION_TEXT}' show='确认永久删号' /> | "
        "<qqbot-cmd-input text='角色菜单' show='取消并返回' />"
    )


@reg_xz_func
async def delete_account(uid, qz, confirmation=""):
    try:
        if str(confirmation or "").strip() != CONFIRMATION_TEXT:
            preview = await get_account_deletion_preview(uid)
            return {
                "type": "markdown",
                "content": render_account_deletion_preview(preview),
            }
        result = await delete_player_account(uid)
        return {
            "type": "markdown",
            "content": (
                "##### ✅ 账号已删除\n\n"
                f"UID `{result['uid']}` 的游戏账号与可重置数据已经永久删除。\n\n"
                "> 如需重新游玩，请发送“注册游戏 玩家名”。"
            ),
        }
    except AccountDeletionError as exc:
        return {
            "type": "markdown",
            "content": (
                f"{qz}##### 无法删号\n\n{exc}\n\n"
                "<qqbot-cmd-input text='角色菜单' show='返回角色菜单' />"
            ),
        }
    except Exception:
        LOGGER.exception("玩家删号失败 uid=%s", uid)
        return {
            "type": "markdown",
            "content": (
                f"{qz}##### 删号失败\n\n数据清理未完成，账号保持原状，请稍后重试。\n\n"
                "<qqbot-cmd-input text='角色菜单' show='返回角色菜单' />"
            ),
        }
