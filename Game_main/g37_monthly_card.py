# -*- coding: utf-8 -*-
"""月卡玩家入口与 GM 兑换码交互。"""

from func.pd_func import pd_reg_func
from Game_domain.gm_service import GMError
from Game_domain.monthly_card_service import (
    MONTHLY_CARD_ACTIVATION_XIANYU,
    MONTHLY_CARD_DAILY_LINGSHI,
    MONTHLY_CARD_DAILY_XIANYU,
    MONTHLY_CARD_DAYS,
    MONTHLY_CARD_MAX_REMAINING_DAYS,
    MonthlyCardError,
    claim_monthly_card,
    create_monthly_card_codes,
    get_monthly_card_status,
    parse_generate_count,
    redeem_monthly_card_code,
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
async def monthly_card_home(uid, qz):
    status = await get_monthly_card_status(uid)
    lines = [
        "##### 🌙 问道月卡",
        "",
        f"> 激活即得 **{MONTHLY_CARD_ACTIVATION_XIANYU}仙玉**，并开启 **{MONTHLY_CARD_DAYS}个自然日**领取期。",
        f"> 每日可领：**{MONTHLY_CARD_DAILY_XIANYU}仙玉 + {MONTHLY_CARD_DAILY_LINGSHI}灵石**。",
        "> 每个自然日限领一次，漏领不补；续卡顺延，有效期最多累计180天。",
        "",
    ]
    if status["active"]:
        state = "✅ 今日已领取" if status["claimed_today"] else "🎁 今日可领取"
        lines.extend((
            "**当前权益**",
            f"> 状态：**生效中**｜{state}",
            f"> 到期日：**{status['expires_on']}**｜含今日剩余 **{status['remaining_days']}天**",
            f"> 累计激活：{status['total_days_activated']}天｜累计领取：{status['total_days_claimed']}天",
        ))
    else:
        expired = f"（上次到期：{status['expires_on']}）" if status["expires_on"] else ""
        lines.extend((
            "**当前权益**",
            f"> 状态：**未激活或已到期**{expired}",
            "> 获得月卡码后发送“月卡兑换 月卡码”即可激活。",
        ))
    if status["recent_claims"]:
        lines.extend(("", "**近期领取**"))
        lines.extend(
            f"> {row[0]}｜仙玉 +{int(row[1])}｜灵石 +{int(row[2])}"
            for row in status["recent_claims"]
        )
    lines.extend((
        "",
        f"{_button('领取月卡', '领取今日奖励')} | {_button('月卡兑换 ', '填写月卡码*')} | {_button('活动菜单', '活动菜单')}",
    ))
    return _result(
        "\n".join(lines),
        (
            ("领取月卡", "领取今日奖励"),
            {"command": "月卡兑换 ", "label": "填写月卡码*", "complete": False},
            ("活动菜单", "活动菜单"),
        ),
    )


@pd_reg_func
async def monthly_card_claim(uid, qz):
    try:
        data = await claim_monthly_card(uid)
        return _result(
            "##### ✅ 月卡奖励已领取\n\n"
            f"仙玉：**+{data['reward_xianyu']}**｜当前 {data['xianyu_after']}\n"
            f"灵石：**+{data['reward_lingshi']}**｜当前 {data['lingshi_after']}\n\n"
            f"> 月卡到期：{data['expires_on']}｜含今日剩余 {data['remaining_days']}天\n\n"
            f"{_button('月卡', '查看月卡')} | {_button('今日修行', '今日修行')}",
            (("月卡", "查看月卡"), ("今日修行", "今日修行")),
        )
    except MonthlyCardError as error:
        return _result(
            "##### ⚠️ 月卡奖励未领取\n\n"
            f"{error}\n\n"
            f"{_button('月卡', '查看月卡')} | {_button('月卡兑换 ', '填写月卡码*')}",
            (
                ("月卡", "查看月卡"),
                {"command": "月卡兑换 ", "label": "填写月卡码*", "complete": False},
            ),
        )


@pd_reg_func
async def monthly_card_redeem(uid, qz, value):
    if not str(value or "").strip():
        return _result(
            "##### 🎫 月卡激活\n\n"
            "发送：`月卡兑换 月卡码`\n\n"
            f"> 每枚月卡码增加{MONTHLY_CARD_DAYS}天权益并立即发放{MONTHLY_CARD_ACTIVATION_XIANYU}仙玉；"
            f"有效期最多累计{MONTHLY_CARD_MAX_REMAINING_DAYS}天。\n\n"
            f"{_button('月卡兑换 ', '填写月卡码*')} | {_button('月卡', '查看月卡')}",
            (
                {"command": "月卡兑换 ", "label": "填写月卡码*", "complete": False},
                ("月卡", "查看月卡"),
            ),
        )
    try:
        data = await redeem_monthly_card_code(uid, value)
        return _result(
            "##### ✅ 月卡激活成功\n\n"
            f"有效期：**+{data['days']}天**｜到期日：**{data['expires_on']}**\n"
            f"激活奖励：**{data['activation_xianyu']}仙玉**\n"
            f"仙玉余额：{data['balance_before']} → **{data['balance_after']}**\n\n"
            "> 激活当天即可领取今日月卡奖励。\n\n"
            f"{_button('领取月卡', '领取今日奖励')} | {_button('月卡', '查看月卡')}",
            (("领取月卡", "领取今日奖励"), ("月卡", "查看月卡")),
        )
    except MonthlyCardError as error:
        return _result(
            "##### ⚠️ 月卡未激活\n\n"
            f"{error}\n\n"
            f"{_button('月卡兑换 ', '重新填写*')} | {_button('月卡', '查看月卡')}",
            (
                {"command": "月卡兑换 ", "label": "重新填写*", "complete": False},
                ("月卡", "查看月卡"),
            ),
        )


@pd_reg_func
async def gm_create_monthly_card_codes(uid, qz, value):
    try:
        count = parse_generate_count(value)
        data = await create_monthly_card_codes(uid, count)
        code_lines = "\n".join(f"> `{code}`" for code in data["codes"])
        return _result(
            "##### ✅ 月卡码已生成\n\n"
            f"权益：**{data['days']}天**｜激活奖励：**{data['activation_xianyu']}仙玉**｜数量：**{data['count']}**\n"
            f"批次：`{data['batch_id']}`\n\n"
            f"{code_lines}\n\n"
            "> 月卡码为一次性资产，请仅发送给目标玩家。\n\n"
            f"{_button('GM生成月卡码 ', '继续生成*')} | {_button('GM菜单', 'GM菜单')}",
            (
                {"command": "GM生成月卡码 ", "label": "继续生成*", "complete": False},
                ("GM菜单", "GM菜单"),
            ),
        )
    except (GMError, MonthlyCardError) as error:
        return _result(
            "##### ⚠️ 月卡码生成失败\n\n"
            f"{error}\n\n"
            f"{_button('GM生成月卡码 ', '重新生成*')} | {_button('GM菜单', 'GM菜单')}",
            (
                {"command": "GM生成月卡码 ", "label": "重新生成*", "complete": False},
                ("GM菜单", "GM菜单"),
            ),
        )
