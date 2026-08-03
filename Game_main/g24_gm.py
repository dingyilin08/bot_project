# -*- coding: utf-8 -*-
"""GM 指令交互层。"""

from config import ADMIN_PASSWORD, is_image_mode, set_image_mode
from func.pd_func import pd_reg_func
from Game_domain.gm_service import (
    GMError,
    authenticate_admin,
    grant_all_currency,
    grant_item,
    grant_xianyu,
    parse_global_grant,
    parse_item_grant,
    parse_xianyu_grant,
    require_admin,
)
from Game_domain.gm_state import is_admin


def _button(command, label=None):
    return f"<qqbot-cmd-input text='{command}' show='{label or command}' />"


def _result(content, commands=()):
    return {"type": "markdown", "content": content, "keyboard_commands": list(commands)}


def _error(error):
    return _result(
        f"##### ⚠️ GM 操作未生效\n\n{error}\n\n{_button('GM菜单', '返回GM菜单')}",
        (("GM菜单", "返回GM菜单"),),
    )


@pd_reg_func
async def gm_menu(uid, qz):
    if not is_admin(uid):
        return _result(
            "##### 🔒 GM 管理\n\n当前 UID 尚未获得管理员权限。验证成功后权限会永久写入 YAML，服务重启后仍然有效。\n\n"
            + _button("GM验证", "验证管理员密令"),
            (("GM验证", "验证密令"), ("主菜单", "主菜单")),
        )
    mode = "图片回复模式" if is_image_mode() else "纯文字回复模式"
    content = "##### 🛠️ GM 管理菜单\n\n"
    content += f"管理员 UID：**{uid}**｜当前：**{mode}**\n\n"
    content += f"{_button('GM发放物品 ', '发放物品*')} | {_button('GM发放仙玉 ', '发放仙玉*')}\n"
    content += f"{_button('GM全服发放灵石 ', '全服发灵石*')} | {_button('GM全服发放仙玉 ', '全服发仙玉*')}\n\n"
    content += f"{_button('关闭图片模式', '关闭图片')} | {_button('开启图片模式', '开启图片')}\n\n"
    content += f"{_button('GM世界消息', '世界消息库')}\n\n"
    content += "> 物品格式：GM发放物品 目标UID-物品名称或编号-数量\n"
    content += "> 仙玉格式：GM发放仙玉 目标UID-数量\n"
    content += "> 全服格式：GM全服发放灵石 数量，或 GM全服发放仙玉 数量\n\n"
    content += _button("主菜单", "主菜单")
    return _result(content, (
        {"command": "GM发放物品 ", "label": "发放物品*", "complete": False, "style": 1},
        {"command": "GM发放仙玉 ", "label": "发放仙玉*", "complete": False, "style": 1},
        {"command": "GM全服发放灵石 ", "label": "全服发灵石*", "complete": False, "style": 3},
        {"command": "GM全服发放仙玉 ", "label": "全服发仙玉*", "complete": False, "style": 3},
        ("关闭图片模式", "关闭图片"), ("开启图片模式", "开启图片"),
        ("GM世界消息", "世界消息库"),
        ("主菜单", "主菜单"),
    ))


@pd_reg_func
async def gm_auth(uid, qz, value):
    try:
        already_admin = is_admin(uid)
        authenticate_admin(uid, value, ADMIN_PASSWORD)
        message = "管理员身份已经有效。" if already_admin else "密令正确，当前 UID 已永久设为管理员。"
        return _result(
            f"##### ✅ GM 验证成功\n\n{message}\n权限已写入 `gm_state.yaml`，重启服务无需再次验证。\n\n{_button('GM菜单', '进入GM菜单')}",
            (("GM菜单", "进入GM菜单"),),
        )
    except GMError as error:
        return _error(error)


@pd_reg_func
async def gm_grant_item(uid, qz, value, request_id=None):
    try:
        target_uid, item_key, amount = parse_item_grant(value)
        data = await grant_item(operator_uid=uid, target_uid=target_uid,
                                item_key=item_key, amount=amount, request_id=request_id)
        return _result(
            f"##### ✅ GM 物品发放成功\n\n目标：**{data['target_name']}（{data['target_uid']}）**\n"
            f"物品：**{data['item_name']} × {data['amount']}**\n"
            f"背包数量：{data['balance_before']} → **{data['balance_after']}**\n\n"
            f"{_button('GM发放物品 ', '继续发放*')} | {_button('GM菜单', 'GM菜单')}",
            (("GM发放物品 ", "继续发放*"), ("GM菜单", "GM菜单")),
        )
    except GMError as error:
        return _error(error)


@pd_reg_func
async def gm_grant_xianyu(uid, qz, value, request_id=None):
    try:
        target_uid, amount = parse_xianyu_grant(value)
        data = await grant_xianyu(operator_uid=uid, target_uid=target_uid,
                                  amount=amount, request_id=request_id)
        return _result(
            f"##### ✅ GM 仙玉发放成功\n\n目标：**{data['target_name']}（{data['target_uid']}）**\n"
            f"发放：**{data['amount']}仙玉**\n余额：{data['balance_before']} → **{data['balance_after']}**\n\n"
            f"{_button('GM发放仙玉 ', '继续发放*')} | {_button('GM菜单', 'GM菜单')}",
            (("GM发放仙玉 ", "继续发放*"), ("GM菜单", "GM菜单")),
        )
    except GMError as error:
        return _error(error)


@pd_reg_func
async def gm_grant_all_lingshi(uid, qz, value, request_id=None):
    try:
        amount = parse_global_grant(value, "GM全服发放灵石")
        data = await grant_all_currency(
            operator_uid=uid, currency="lingshi", amount=amount, request_id=request_id
        )
        return _result(
            f"##### ✅ GM 全服灵石发放成功\n\n每名玩家：**{data['amount_per_player']} 灵石**\n"
            f"发放人数：**{data['recipient_count']}**\n累计发放：**{data['total_amount']} 灵石**\n\n"
            f"{_button('GM全服发放灵石 ', '继续发放*')} | {_button('GM菜单', 'GM菜单')}",
            (("GM全服发放灵石 ", "继续发放*"), ("GM菜单", "GM菜单")),
        )
    except GMError as error:
        return _error(error)


@pd_reg_func
async def gm_grant_all_xianyu(uid, qz, value, request_id=None):
    try:
        amount = parse_global_grant(value, "GM全服发放仙玉")
        data = await grant_all_currency(
            operator_uid=uid, currency="xianyu", amount=amount, request_id=request_id
        )
        return _result(
            f"##### ✅ GM 全服仙玉发放成功\n\n每名玩家：**{data['amount_per_player']} 仙玉**\n"
            f"发放人数：**{data['recipient_count']}**\n累计发放：**{data['total_amount']} 仙玉**\n\n"
            f"{_button('GM全服发放仙玉 ', '继续发放*')} | {_button('GM菜单', 'GM菜单')}",
            (("GM全服发放仙玉 ", "继续发放*"), ("GM菜单", "GM菜单")),
        )
    except GMError as error:
        return _error(error)


@pd_reg_func
async def gm_image_mode(uid, qz, enabled, password=""):
    try:
        if not is_admin(uid):
            authenticate_admin(uid, password, ADMIN_PASSWORD)
        require_admin(uid)
        changed = set_image_mode(bool(enabled))
        mode = "图片回复模式" if enabled else "纯文字回复模式"
        message = f"已切换为**{mode}**。" if changed else f"当前已经是**{mode}**。"
        return _result(
            f"##### ✅ GM 图片模式\n\n{message}\n该状态已写入 YAML，服务重启后继续生效。\n\n{_button('GM菜单', '返回GM菜单')}",
            (("GM菜单", "返回GM菜单"),),
        )
    except GMError as error:
        return _error(error)
