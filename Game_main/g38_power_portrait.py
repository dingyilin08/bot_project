# -*- coding: utf-8 -*-
"""玩家战力立绘上传、状态查询与 GM 审核交互。"""

import re

from config import IMG_BASE_URL
from func.pd_func import pd_reg_func, reg_xz_func
from Game_domain.gm_service import GMError
from Game_domain.power_portrait_service import (
    PowerPortraitError,
    approve_submission,
    begin_upload_intent,
    consume_upload_intent,
    get_submission,
    has_upload_intent,
    pending_submissions,
    portrait_status,
    reject_submission,
    submit_portrait,
)
from Tool.power_portrait import image_attachments, portrait_file_path
from Tool.tool_user import openid_to_uid


def _button(command, label=None):
    return f"<qqbot-cmd-input text='{command}' show='{label or command}' />"


def _result(content, commands=(), *, force_image=False):
    result = {
        "type": "markdown",
        "content": content,
        "keyboard_commands": list(commands),
    }
    if force_image:
        result["force_image"] = True
    return result


def _time_text(value):
    if not value:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M") if hasattr(value, "strftime") else str(value)


async def resolve_power_portrait_message(user_content, openid, attachments):
    """玩家点过上传入口后，下一条纯图片消息自动按立绘提交处理。"""
    if not image_attachments(attachments):
        return user_content
    uid = await openid_to_uid(openid)
    if uid and has_upload_intent(uid):
        return "更换战力立绘"
    return user_content


async def is_waiting_for_power_portrait(openid, attachments) -> bool:
    if not image_attachments(attachments):
        return False
    uid = await openid_to_uid(openid)
    return bool(uid and has_upload_intent(uid))


@reg_xz_func
async def power_portrait_upload(uid, qz, attachments=None, request_id=None):
    images = image_attachments(attachments)
    if not images:
        begin_upload_intent(uid)
        return _result(
            "##### 🖼️ 更换战力立绘\n\n"
            "> 请在 **5 分钟内直接发送一张图片**，也可以把“更换战力立绘”作为图片文字说明一起发送。\n\n"
            "**上传要求**\n"
            "- JPG、PNG 或 WebP，最大 8MB\n"
            "- 宽和高均不少于 300 像素\n"
            "- 建议使用竖版、人物主体居中的清晰立绘\n\n"
            "> 图片提交后进入 GM 审核。审核通过前，战力图片继续展示当前已通过立绘；从未通过过自定义立绘时继续展示角色默认立绘。\n\n"
            f"{_button('立绘状态', '查看审核状态')} | {_button('战力图片', '查看当前战力图片')}",
            (("立绘状态", "审核状态"), ("战力图片", "当前战力图片")),
        )
    consume_upload_intent(uid)
    try:
        submission = await submit_portrait(uid, attachments, request_id=request_id)
    except PowerPortraitError as error:
        return _result(
            f"##### ⚠️ 立绘提交失败\n\n{error}\n\n"
            f"{_button('更换战力立绘', '重新上传')} | {_button('立绘状态', '查看状态')}",
            (("更换战力立绘", "重新上传"), ("立绘状态", "查看状态")),
        )
    return _result(
        "##### ✅ 立绘已提交审核\n\n"
        f"审核编号：**#{submission['id']}**\n"
        f"图片尺寸：{submission['width']} × {submission['height']}\n\n"
        "> 审核通过前不会展示这张图片，当前战力立绘保持不变。新提交会替换尚未审核的旧提交。\n\n"
        f"{_button('立绘状态', '查看审核状态')} | {_button('战力图片', '查看当前效果')}",
        (("立绘状态", "审核状态"), ("战力图片", "当前效果")),
    )


@reg_xz_func
async def power_portrait_status(uid, qz):
    try:
        data = await portrait_status(uid)
    except PowerPortraitError as error:
        return _result(f"##### ⚠️ 立绘状态读取失败\n\n{error}")
    latest = data["latest"]
    active_text = "已使用审核通过的自定义立绘" if data["using_custom"] else "正在使用角色默认立绘"
    if not latest:
        detail = "> 你还没有提交过自定义立绘。"
    else:
        status_text = {
            "PENDING": "等待 GM 审核",
            "APPROVED": "审核通过",
            "REJECTED": "审核未通过",
            "SUPERSEDED": "已被新提交替换",
        }.get(latest["status"], latest["status"])
        detail = (
            f"最近提交：**#{latest['id']}**\n\n"
            f"审核状态：**{status_text}**\n\n"
            f"提交时间：{_time_text(latest['created_at'])}"
        )
        if latest["reject_reason"]:
            detail += f"\n\n原因：{latest['reject_reason']}"
    return _result(
        f"##### 🖼️ 战力立绘状态\n\n当前展示：**{active_text}**\n\n{detail}\n\n"
        f"{_button('更换战力立绘', '上传新立绘')} | {_button('战力图片', '查看战力图片')}",
        (("更换战力立绘", "上传新立绘"), ("战力图片", "战力图片")),
    )


@pd_reg_func
async def gm_power_portrait_queue(uid, qz):
    try:
        from Game_domain.gm_service import require_admin

        require_admin(uid)
        rows = await pending_submissions()
    except (GMError, PowerPortraitError) as error:
        return _result(f"##### ⚠️ GM 立绘审核\n\n{error}\n\n{_button('GM菜单', 'GM菜单')}")
    if not rows:
        content = "##### ✅ GM 立绘审核\n\n当前没有待审核立绘。"
    else:
        lines = []
        for item in rows:
            lines.append(
                f"**#{item['id']}**｜{item['player_name']}（UID {item['uid']}）｜"
                f"{item['width']}×{item['height']}｜{_time_text(item['created_at'])}\n"
                f"{_button('GM查看立绘 ' + str(item['id']), '查看并审核 #' + str(item['id']))}"
            )
        content = "##### 🛡️ GM 立绘审核队列\n\n" + "\n\n".join(lines)
    return _result(
        content + f"\n\n{_button('GM立绘审核', '刷新队列')} | {_button('GM菜单', 'GM菜单')}",
        (("GM立绘审核", "刷新队列"), ("GM菜单", "GM菜单")),
    )


def _positive_id(value, command):
    text = str(value or "").strip()
    if not re.fullmatch(r"\d+", text) or int(text) <= 0:
        raise PowerPortraitError(f"格式：{command} 审核编号")
    return int(text)


@pd_reg_func
async def gm_power_portrait_view(uid, qz, value):
    try:
        from Game_domain.gm_service import require_admin

        require_admin(uid)
        submission_id = _positive_id(value, "GM查看立绘")
        item = await get_submission(submission_id)
        if not item:
            raise PowerPortraitError("未找到该立绘审核单。")
        if not portrait_file_path(item["storage_key"]):
            raise PowerPortraitError("图片文件已清理或缺失，无法预览。")
    except (GMError, PowerPortraitError) as error:
        return _result(f"##### ⚠️ 无法查看立绘\n\n{error}\n\n{_button('GM立绘审核', '返回审核队列')}")

    image_url = f"{IMG_BASE_URL}/{item['storage_key']}"
    status_text = {
        "PENDING": "待审核", "APPROVED": "已通过", "REJECTED": "已驳回",
        "SUPERSEDED": "已替换",
    }.get(item["status"], item["status"])
    content = (
        f"![玩家立绘审核 #{item['id']} #720px #900px]({image_url})\n\n"
        f"##### 审核单 #{item['id']}\n\n"
        f"玩家：**{item['player_name']}**（UID {item['uid']}）\n\n"
        f"状态：**{status_text}**｜尺寸：{item['width']} × {item['height']}｜"
        f"大小：{item['file_size'] // 1024}KB\n\n"
    )
    commands = (("GM立绘审核", "审核队列"),)
    if item["status"] == "PENDING":
        content += (
            f"{_button('GM通过立绘 ' + str(item['id']), '审核通过')} | "
            f"{_button('GM驳回立绘 ' + str(item['id']) + '-', '驳回并填写原因*')}\n\n"
            "> 审核通过后玩家下一次生成战力图片即使用此立绘。驳回格式：GM驳回立绘 编号-原因"
        )
        commands = (
            ("GM通过立绘 " + str(item["id"]), "审核通过"),
            {
                "command": "GM驳回立绘 " + str(item["id"]) + "-",
                "label": "驳回并填原因*",
                "complete": False,
                "style": 1,
            },
            ("GM立绘审核", "审核队列"),
        )
    else:
        content += _button("GM立绘审核", "返回审核队列")
    return _result(content, commands, force_image=True)


@pd_reg_func
async def gm_power_portrait_approve(uid, qz, value):
    try:
        submission_id = _positive_id(value, "GM通过立绘")
        item = await approve_submission(uid, submission_id)
    except (GMError, PowerPortraitError) as error:
        return _result(f"##### ⚠️ 审核未生效\n\n{error}\n\n{_button('GM立绘审核', '审核队列')}")
    return _result(
        f"##### ✅ 立绘审核通过\n\n审核单：**#{item['id']}**\n"
        f"玩家：**{item['player_name']}（UID {item['uid']}）**\n\n"
        "> 玩家下一次发送“战力图片”时将使用该立绘。\n\n"
        f"{_button('GM立绘审核', '继续审核')} | {_button('GM菜单', 'GM菜单')}",
        (("GM立绘审核", "继续审核"), ("GM菜单", "GM菜单")),
    )


@pd_reg_func
async def gm_power_portrait_reject(uid, qz, value):
    matched = re.fullmatch(r"(\d+)-(.+)", str(value or "").strip())
    if not matched:
        return _result(
            "##### ⚠️ 审核未生效\n\n格式：GM驳回立绘 审核编号-原因\n"
            "示例：GM驳回立绘 12-人物主体不清晰\n\n"
            f"{_button('GM立绘审核', '审核队列')}"
        )
    try:
        item = await reject_submission(uid, int(matched.group(1)), matched.group(2))
    except (GMError, PowerPortraitError) as error:
        return _result(f"##### ⚠️ 审核未生效\n\n{error}\n\n{_button('GM立绘审核', '审核队列')}")
    return _result(
        f"##### ✅ 立绘已驳回\n\n审核单：**#{item['id']}**\n"
        f"玩家：**{item['player_name']}（UID {item['uid']}）**\n"
        f"原因：{item['reject_reason']}\n\n"
        f"{_button('GM立绘审核', '继续审核')} | {_button('GM菜单', 'GM菜单')}",
        (("GM立绘审核", "继续审核"), ("GM菜单", "GM菜单")),
    )
