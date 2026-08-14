# -*- coding: utf-8 -*-
"""角色轮回重生指令。"""

import logging

from func.pd_func import reg_xz_func
from Game_domain.reincarnation_service import (
    ROLE_ATTRIBUTE_NAMES,
    ReincarnationError,
    get_reincarnation_preview,
    reincarnate_active_role,
)


logger = logging.getLogger(__name__)


def _format_inheritance(preview):
    inherited = preview["inherited_attributes"]
    keys = ("gongji", "fangyu", "qixue", "fali", "sudu")
    first = " | ".join(f"{ROLE_ATTRIBUTE_NAMES[key]}+{inherited[key]}" for key in keys)
    rate_keys = ("baoji", "baoshang", "shanbi", "mingzhong", "pofang", "xixue")
    second = " | ".join(
        f"{ROLE_ATTRIBUTE_NAMES[key]}+{inherited[key] / 100:g}%" for key in rate_keys
    )
    return f"> {first}\n> {second}"


def render_reincarnation_preview(preview):
    return (
        "##### 🔄 轮回重生\n\n"
        f"**当前角色：** [{preview['id']}.{preview['name']}]\n"
        f"**轮回世数：** 第{preview['reincarnation_count']}世 → 第{preview['next_reincarnation']}世\n"
        "**重生等级：** 100级 → 1级（经验归零）\n\n"
        "**本次继承的10%裸属性：**\n"
        f"{_format_inheritance(preview)}\n\n"
        "> 重生属性为角色1级模板属性加上上述轮回遗泽。装备、本源、技能、灵兽及其他养成均会保留。\n\n"
        "⚠️ 轮回完成后不可撤销，请确认是否继续。\n\n"
        "<qqbot-cmd-input text='轮回重生 确认' show='确认轮回' /> | "
        "<qqbot-cmd-input text='当前角色' show='暂不轮回' />"
    )


def render_reincarnation_success(preview):
    return (
        "##### ✨ 轮回成功\n\n"
        f"[{preview['id']}.{preview['name']}]已褪去旧身，踏入**第{preview['next_reincarnation']}世**。\n\n"
        f"**当前境界：** {preview['stage']}\n"
        "**当前等级：** 1级\n"
        "**当前经验：** 0\n\n"
        "**已继承上一世10%裸属性：**\n"
        f"{_format_inheritance(preview)}\n\n"
        "<qqbot-cmd-input text='当前角色' show='查看重生属性' /> | "
        "<qqbot-cmd-input text='参悟' show='重新修行' />"
    )


@reg_xz_func
async def reincarnation(uid, qz, confirmation=""):
    try:
        if str(confirmation or "").strip() != "确认":
            preview = await get_reincarnation_preview(uid)
            return {"type": "markdown", "content": render_reincarnation_preview(preview)}
        result = await reincarnate_active_role(uid)
        return {"type": "markdown", "content": render_reincarnation_success(result)}
    except ReincarnationError as exc:
        return {
            "type": "markdown",
            "content": (
                f"{qz}##### 轮回未成\n\n{exc}\n\n"
                "<qqbot-cmd-input text='当前角色' show='查看当前角色' />"
            ),
        }
    except Exception:
        logger.exception("角色轮回指令执行失败 uid=%s", uid)
        return {
            "type": "markdown",
            "content": (
                f"{qz}##### 轮回失败\n\n轮回数据处理失败，请稍后重试；角色数据未发生变化。\n\n"
                "<qqbot-cmd-input text='当前角色' show='查看当前角色' />"
            ),
        }
