# -*- coding: utf-8 -*-
"""为普通机器人回复追加官方群/世界消息轮换尾注。"""

from typing import Any, Dict

from Game_domain.world_message_service import next_world_message_slot
from Tool.qq_official_group import OFFICIAL_GROUP_NOTICE


WORLD_MESSAGE_PREFIX = "🌏 世界消息："


def format_world_message_notice(content: str) -> str:
    return f"{WORLD_MESSAGE_PREFIX}{content}"


def has_reply_footer(text: str) -> bool:
    if not isinstance(text, str):
        return False
    footer = text.rstrip().rsplit("\n\n", 1)[-1]
    return footer == OFFICIAL_GROUP_NOTICE or footer.startswith(WORLD_MESSAGE_PREFIX)


async def append_rotating_reply_notice(text):
    """幂等追加下一个回复尾注；数据库不可用时服务层返回官方群槽位。"""
    if not isinstance(text, str):
        return text
    if has_reply_footer(text):
        return text

    content = text.rstrip()
    world_message = await next_world_message_slot()
    notice = (
        format_world_message_notice(world_message)
        if world_message
        else OFFICIAL_GROUP_NOTICE
    )
    if not content:
        return notice
    return f"{content}\n\n{notice}"


async def attach_rotating_reply_notice(result):
    """兼容纯文本及 Markdown/Keyboard 业务返回值。"""
    if isinstance(result, str):
        return await append_rotating_reply_notice(result)
    if not isinstance(result, dict) or not isinstance(result.get("content"), str):
        return result

    upgraded: Dict[str, Any] = dict(result)
    upgraded["content"] = await append_rotating_reply_notice(result["content"])
    return upgraded
