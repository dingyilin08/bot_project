# -*- coding: utf-8 -*-
"""世界消息库的 GM 指令交互层。"""

from func.pd_func import pd_reg_func
from Game_domain.gm_service import GMError
from Game_domain.world_message_service import (
    add_world_message,
    delete_world_message,
    list_world_messages,
    parse_world_message_id,
    parse_world_message_update,
    set_world_message_enabled,
    update_world_message,
)


def _button(command, label=None, *, complete=True):
    return {
        "command": command,
        "label": label or command,
        "complete": complete,
        "style": 1,
    }


def _result(content, commands=()):
    return {"type": "markdown", "content": content, "keyboard_commands": list(commands)}


def _error(error):
    return _result(
        f"##### ⚠️ 世界消息操作未生效\n\n{error}",
        ((_button("GM世界消息", "返回消息库")),),
    )


def _manage_buttons():
    return (
        _button("GM世界消息添加 ", "添加消息*", complete=False),
        _button("GM世界消息修改 ", "修改消息*", complete=False),
        _button("GM世界消息启用 ", "启用消息*", complete=False),
        _button("GM世界消息停用 ", "停用消息*", complete=False),
        _button("GM世界消息删除 ", "删除消息*", complete=False),
        _button("GM菜单", "GM菜单"),
    )


@pd_reg_func
async def gm_world_message_menu(uid, qz):
    try:
        rows = await list_world_messages(uid)
    except GMError as error:
        return _error(error)

    content = "##### 🌏 世界消息库\n\n"
    content += "> 普通回复会在官方群提示和已启用世界消息之间交替展示。\n\n"
    if not rows:
        content += "当前消息库为空，请添加第一条攻略小贴士。"
    else:
        for item in rows:
            status = "✅ 启用" if item["enabled"] else "⏸️ 停用"
            content += f"**#{item['id']}｜{status}**\n> {item['content']}\n\n"
        content += f"共显示 **{len(rows)}** 条消息。"
    content += (
        "\n\n> 添加：GM世界消息添加 内容"
        "\n> 修改：GM世界消息修改 ID-新内容"
        "\n> 启停/删除：GM世界消息启用、停用或删除 ID"
    )
    return _result(content, _manage_buttons())


@pd_reg_func
async def gm_world_message_add(uid, qz, value):
    try:
        data = await add_world_message(uid, value)
        if data["created"]:
            action = "已添加并启用"
        elif data["restored"]:
            action = "已有记录已恢复并启用"
        else:
            action = "相同内容已经存在且处于启用状态"
        return _result(
            f"##### ✅ 世界消息已保存\n\n消息 **#{data['id']}**：{action}\n> {data['content']}",
            _manage_buttons(),
        )
    except GMError as error:
        return _error(error)


@pd_reg_func
async def gm_world_message_update(uid, qz, value):
    try:
        message_id, content = parse_world_message_update(value)
        data = await update_world_message(uid, message_id, content)
        return _result(
            f"##### ✅ 世界消息已修改\n\n消息 **#{data['id']}**\n> {data['content']}",
            _manage_buttons(),
        )
    except GMError as error:
        return _error(error)


async def _set_enabled(uid, value, enabled):
    try:
        data = await set_world_message_enabled(
            uid, parse_world_message_id(value), enabled
        )
        state = "启用" if data["enabled"] else "停用"
        detail = f"已{state}" if data["changed"] else f"原本就是{state}状态"
        return _result(
            f"##### ✅ 世界消息{state}\n\n消息 **#{data['id']}**：{detail}\n> {data['content']}",
            _manage_buttons(),
        )
    except GMError as error:
        return _error(error)


@pd_reg_func
async def gm_world_message_enable(uid, qz, value):
    return await _set_enabled(uid, value, True)


@pd_reg_func
async def gm_world_message_disable(uid, qz, value):
    return await _set_enabled(uid, value, False)


@pd_reg_func
async def gm_world_message_delete(uid, qz, value):
    try:
        data = await delete_world_message(uid, parse_world_message_id(value))
        detail = "已从轮播库软删除" if data["changed"] else "此前已经删除"
        return _result(
            f"##### ✅ 世界消息已删除\n\n消息 **#{data['id']}**：{detail}\n> {data['content']}",
            _manage_buttons(),
        )
    except GMError as error:
        return _error(error)
