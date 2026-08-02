# -*- coding: utf-8 -*-
"""QQ 机器人群聊与好友欢迎消息的纯业务构造。"""

from typing import Any, Dict

from Tool.qq_keyboard import attach_keyboard
from Tool.qq_official_group import attach_official_group_notice


REGISTER_COMMAND_PREFIX = "注册游戏"

GROUP_WELCOME_MARKDOWN = """##### 🌌 欢迎来到《问道诸天》

> 这是一款群聊回合制修仙 RPG。萧炎、王林、韩立、石昊、叶凡、孟川六大主角各有专属本源、技能与养成路线；参悟修炼、强化装备，在诸天中不断成长。

**⚔️ 诸天历练**
> 挑战多波副本与策略战斗，在药园种植灵草、开炉炼丹，寻访灵兽并经营洞府。

**🤝 同道争锋**
> 与群友组队探索道途、建设宗门，合力迎战世界 Boss，并参与赛季成长。

**✨ 新道友入门**
> 点击下方「注册游戏」，在输入框中的 `注册游戏` 后补充一个空格和 **1-8 字昵称**再发送，例如 `注册游戏 云澈`；注册成功后按提示选择角色。"""

FRIEND_WELCOME_MARKDOWN = """##### 🌌 欢迎添加《问道诸天》

> 这是一款回合制修仙 RPG。你可以收集萧炎、王林、韩立、石昊、叶凡、孟川六大主角，参悟修炼、挑战副本，体验药园炼丹、灵兽洞府、宗门组队和世界 Boss 等玩法。

**✨ 开始游戏**
> 点击下方「注册游戏」，在输入框中的 `注册游戏` 后补充一个空格和 **1-8 字昵称**再发送，例如 `注册游戏 云澈`；注册成功后按提示选择角色。"""


def _build_welcome_message(content: str, *, is_group: bool) -> Dict[str, Any]:
    message = {
        "type": "markdown",
        "content": content,
        "keyboard_commands": [
            {
                "label": "注册游戏",
                "command": REGISTER_COMMAND_PREFIX,
                "complete": False,
                "style": 1,
            }
        ],
    }
    result = attach_keyboard(message, is_group=is_group)
    return attach_official_group_notice(result)


def build_group_welcome_message() -> Dict[str, Any]:
    """返回机器人加入群聊时的 Markdown + Keyboard。"""
    return _build_welcome_message(GROUP_WELCOME_MARKDOWN, is_group=True)


def build_friend_welcome_message() -> Dict[str, Any]:
    """返回玩家新添加机器人时的 Markdown + Keyboard。"""
    return _build_welcome_message(FRIEND_WELCOME_MARKDOWN, is_group=False)
