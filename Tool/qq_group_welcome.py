# -*- coding: utf-8 -*-
"""QQ 群聊入群欢迎消息的纯业务构造。"""

from typing import Any, Dict

from Tool.qq_keyboard import attach_keyboard


REGISTER_COMMAND_PREFIX = "注册游戏"

GROUP_WELCOME_MARKDOWN = """##### 🌌 欢迎来到《问道诸天》

> 这是一款群聊回合制修仙 RPG。萧炎、王林、韩立、石昊、叶凡、孟川六大主角各有专属本源、技能与养成路线；参悟修炼、强化装备，在诸天中不断成长。

**⚔️ 诸天历练**
> 挑战多波副本与策略战斗，在药园种植灵草、开炉炼丹，寻访灵兽并经营洞府。

**🤝 同道争锋**
> 与群友组队探索道途、建设宗门，合力迎战世界 Boss，并参与赛季成长。

**✨ 新道友入门**
> 点击下方「注册游戏」，在输入框中的 `注册游戏` 后补充一个空格和 **1-8 字昵称**再发送，例如 `注册游戏 云澈`；注册成功后按提示选择角色。"""


def build_group_welcome_message() -> Dict[str, Any]:
    """返回可由 QQ 群消息网络层直接发送的 Markdown + Keyboard。"""
    message = {
        "type": "markdown",
        "content": GROUP_WELCOME_MARKDOWN,
        "keyboard_commands": [
            {
                "label": "注册游戏",
                "command": REGISTER_COMMAND_PREFIX,
                "complete": False,
                "style": 1,
            }
        ],
    }
    return attach_keyboard(message, is_group=True)
