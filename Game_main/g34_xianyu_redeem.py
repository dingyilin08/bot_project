# -*- coding: utf-8 -*-
"""仙玉兑换码 QQ 指令交互层。"""

from func.pd_func import pd_reg_func
from Game_domain.gm_service import GMError
from Game_domain.xianyu_redeem_service import (
    XIANYU_REDEEM_TIERS,
    XianyuRedeemError,
    create_redeem_codes,
    parse_generate_request,
    redeem_xianyu_code,
)


def _button(command, label=None):
    return f"<qqbot-cmd-input text='{command}' show='{label or command}' />"


def _result(content, commands=()):
    return {
        "type": "markdown",
        "content": content,
        "keyboard_commands": list(commands),
    }


@pd_reg_func
async def redeem_xianyu(uid, qz, value):
    if not str(value or "").strip():
        tiers = "｜".join(str(item) for item in XIANYU_REDEEM_TIERS)
        return _result(
            "##### 🎁 仙玉兑换\n\n"
            f"支持档位：**{tiers} 仙玉**\n\n"
            "发送：`兑换 兑换码`\n"
            "> 每个兑换码只能成功使用一次，仙玉将直接进入账户余额。\n\n"
            f"{_button('兑换 ', '填写兑换码*')} | {_button('主菜单', '主菜单')}",
            (
                {"command": "兑换 ", "label": "填写兑换码*", "complete": False},
                ("主菜单", "主菜单"),
            ),
        )
    try:
        data = await redeem_xianyu_code(uid, value)
        return _result(
            "##### ✅ 兑换成功\n\n"
            f"获得：**{data['amount']} 仙玉**\n"
            f"仙玉余额：{data['balance_before']} → **{data['balance_after']}**\n\n"
            f"{_button('仙玉祈愿', '前往祈愿')} | {_button('主菜单', '主菜单')}",
            (("仙玉祈愿", "前往祈愿"), ("主菜单", "主菜单")),
        )
    except XianyuRedeemError as error:
        return _result(
            "##### ⚠️ 兑换未生效\n\n"
            f"{error}\n\n"
            f"{_button('兑换 ', '重新填写*')} | {_button('主菜单', '主菜单')}",
            (
                {"command": "兑换 ", "label": "重新填写*", "complete": False},
                ("主菜单", "主菜单"),
            ),
        )


@pd_reg_func
async def gm_create_xianyu_redeem_codes(uid, qz, value):
    try:
        amount, count = parse_generate_request(value)
        data = await create_redeem_codes(uid, amount, count)
        code_lines = "\n".join(f"> `{code}`" for code in data["codes"])
        return _result(
            "##### ✅ 仙玉兑换码已生成\n\n"
            f"档位：**{data['amount']}仙玉**｜数量：**{data['count']}**\n"
            f"批次：`{data['batch_id']}`\n\n"
            f"{code_lines}\n\n"
            "> 兑换码为一次性资产，请仅发送给目标玩家。\n\n"
            f"{_button('GM生成兑换码 ', '继续生成*')} | {_button('GM菜单', 'GM菜单')}",
            (
                {"command": "GM生成兑换码 ", "label": "继续生成*", "complete": False},
                ("GM菜单", "GM菜单"),
            ),
        )
    except (GMError, XianyuRedeemError) as error:
        return _result(
            "##### ⚠️ 兑换码生成失败\n\n"
            f"{error}\n\n"
            f"{_button('GM生成兑换码 ', '重新生成*')} | {_button('GM菜单', 'GM菜单')}",
            (
                {"command": "GM生成兑换码 ", "label": "重新生成*", "complete": False},
                ("GM菜单", "GM菜单"),
            ),
        )
