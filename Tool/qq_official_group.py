# -*- coding: utf-8 -*-
"""为所有玩家可见的机器人回复追加官方群提示。"""

from typing import Any, Dict


OFFICIAL_GROUP_NUMBER = "760693073"
OFFICIAL_GROUP_NOTICE = f"官方群群号：{OFFICIAL_GROUP_NUMBER}"


def append_official_group_notice(text):
    """向文本末尾幂等追加官方群提示。"""
    if not isinstance(text, str):
        return text

    content = text.rstrip()
    if content.endswith(OFFICIAL_GROUP_NOTICE):
        return text
    if not content:
        return OFFICIAL_GROUP_NOTICE
    return f"{content}\n\n{OFFICIAL_GROUP_NOTICE}"


def attach_official_group_notice(result):
    """兼容纯文本和 Markdown/Keyboard 业务返回值。"""
    if isinstance(result, str):
        return append_official_group_notice(result)
    if not isinstance(result, dict) or not isinstance(result.get("content"), str):
        return result

    upgraded: Dict[str, Any] = dict(result)
    upgraded["content"] = append_official_group_notice(result["content"])
    return upgraded
