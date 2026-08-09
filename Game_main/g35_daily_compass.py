# -*- coding: utf-8 -*-
"""今日修行：把分散玩法收拢为玩家当前可执行的少量目标。"""

import logging
import time

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql
from Tool.tool_canwu import canwu_remaining_seconds, ensure_canwu_duration_column
from Game_main.g25_daily_tasks import (
    DAILY_TASKS,
    _bonus_claimed,
    _daily_progress,
    _ensure_today_tasks,
    ensure_daily_task_schema,
)


logger = logging.getLogger(__name__)

TASK_ACTIONS = {
    "CULTIVATION": ("参悟", "开始参悟"),
    "DUNGEON": ("副本菜单", "进行历练"),
    "SHOP": ("商城", "补给整备"),
    "FARM": ("药园菜单", "播种灵草"),
    "ALCHEMY": ("炼丹菜单", "开启炼丹"),
}


def _button(command, label):
    return f"<qqbot-cmd-input text='{command}' show='{label}' />"


def _format_seconds(seconds):
    seconds = max(0, int(seconds or 0))
    minutes, second = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours}时{minute}分"
    if minutes:
        return f"{minutes}分{second}秒"
    return f"{second}秒"


def build_daily_compass(snapshot):
    """纯展示构造，方便在无数据库环境下验证玩家看到的优先级。"""
    role_name = snapshot["role_name"]
    role_level = snapshot["role_level"]
    cultivation = snapshot["cultivation"]
    daily = snapshot.get("daily")
    active_dungeon = snapshot.get("active_dungeon")

    lines = [
        "##### 🧭 今日修行",
        "",
        f"**出战角色：** {role_name} Lv.{role_level}",
        "> 先领取已完成的奖励，再完成最靠前的目标；这里仅保留你现在能直接做的事。",
        "",
    ]
    actions = []

    if cultivation["state"] == "claimable":
        lines.append(f"**参悟已完成**｜可领取 **{cultivation['exp']}** 经验")
        actions.append(("领取参悟经验", "领取参悟经验"))
    elif cultivation["state"] == "running":
        lines.append(f"**参悟进行中**｜剩余 {_format_seconds(cultivation['remaining'])}")
        actions.append(("参悟状态", "查看参悟状态"))
    else:
        lines.append("**参悟空闲**｜开始一次参悟，保持经验稳定增长")
        actions.append(("参悟", "开始参悟"))

    if active_dungeon:
        lines.append(
            f"**副本进行中**｜#{active_dungeon['dungeon_id']} 第"
            f"{active_dungeon['wave']}/{active_dungeon['total_waves']}波"
        )
        actions.append(("战斗状态", "继续副本"))

    if daily is None:
        lines.append("**日常任务**｜暂无法读取进度，可进入日常任务页查看。")
        actions.append(("日常任务", "查看日常任务"))
    else:
        completed = daily["completed"]
        total = daily["total"]
        lines.append(f"**日常任务**｜{completed}/{total} 已完成｜{daily['unclaimed']} 项奖励待领取")
        if daily["unclaimed"]:
            actions.append(("日常领取 全部", "领取日常奖励"))
        else:
            next_task = next((code for code in daily["pending"] if code in TASK_ACTIONS), None)
            if next_task:
                actions.append(TASK_ACTIONS[next_task])
            elif completed == total and not daily["bonus_claimed"]:
                actions.append(("日常领取 全部", "领取全勤礼包"))

    # 一屏最多给三个高优先级操作，避免又把“指引”做成新的长菜单。
    unique_actions = []
    for action in actions:
        if action not in unique_actions:
            unique_actions.append(action)
        if len(unique_actions) == 3:
            break

    lines.extend(("", "***", "**现在就做**", " | ".join(_button(*action) for action in unique_actions)))
    lines.extend((
        "",
        "**常用收取**",
        f"{_button('收回', '一键收回')} | {_button('洞府', '洞府收取')} | {_button('灵兽派遣', '灵兽派遣')}",
        "",
        f"{_button('日常任务', '日常任务')} | {_button('主菜单', '主菜单')} | {_button('活动菜单', '今日活动')}",
    ))
    return {"type": "markdown", "content": "\n".join(lines)}


async def _read_daily_snapshot(uid, cursor):
    try:
        await ensure_daily_task_schema(cursor)
        await _ensure_today_tasks(uid, cursor)
        progress = await _daily_progress(uid, cursor)
        bonus_claimed = await _bonus_claimed(uid, cursor)
    except Exception:
        # 日常迁移异常不应让“今日修行”整体失效；页面仍可引导玩家进入基础玩法。
        logger.exception("读取日常任务进度失败")
        return None

    completed = [code for code, *_ in DAILY_TASKS if progress.get(code, (None, None))[0]]
    unclaimed = [
        code for code, *_ in DAILY_TASKS
        if progress.get(code, (None, None))[0] and not progress.get(code, (None, None))[1]
    ]
    return {
        "completed": len(completed),
        "total": len(DAILY_TASKS),
        "unclaimed": len(unclaimed),
        "pending": [code for code, *_ in DAILY_TASKS if code not in completed],
        "bonus_claimed": bonus_claimed,
    }


@reg_xz_func
async def daily_compass_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_canwu_duration_column(cursor)
            await cursor.execute(
                "SELECT name, dengji FROM user_role WHERE uid=%s AND is_chuzhan=1 LIMIT 1",
                (uid,),
            )
            role = await cursor.fetchone()
            await cursor.execute(
                "SELECT is_canwu, cw_timestamp, cw_duration, cw_exp FROM user_zt WHERE id=%s LIMIT 1",
                (uid,),
            )
            cultivation_row = await cursor.fetchone()
            await cursor.execute(
                """
                SELECT dungeon_id, wave, total_waves FROM user_dungeon_progress
                WHERE uid=%s AND status='fighting' ORDER BY start_time DESC LIMIT 1
                """,
                (uid,),
            )
            dungeon = await cursor.fetchone()
            daily = await _read_daily_snapshot(uid, cursor)
            await conn.commit()

    if not role:
        return {
            "type": "markdown",
            "content": "##### 🧭 今日修行\n\n当前没有可用的出战角色，请先返回角色菜单确认角色状态。\n\n"
            + _button("角色菜单", "角色菜单"),
        }

    is_cultivating, timestamp, duration, exp = cultivation_row
    remaining = canwu_remaining_seconds(timestamp, duration, int(time.time())) if is_cultivating else 0
    cultivation = {
        "state": "claimable" if is_cultivating and remaining <= 0 else ("running" if is_cultivating else "idle"),
        "remaining": remaining,
        "exp": exp or 0,
    }
    return build_daily_compass({
        "role_name": role[0],
        "role_level": role[1],
        "cultivation": cultivation,
        "daily": daily,
        "active_dungeon": (
            {"dungeon_id": dungeon[0], "wave": dungeon[1], "total_waves": dungeon[2]}
            if dungeon else None
        ),
    })
