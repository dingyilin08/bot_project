# -*- coding: utf-8 -*-
"""P2 问道札记：用真实行为事件驱动的新手七步引导。"""

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


TASKS = (
    ("ROLE", "选择初始角色", "选择并出战第一位角色。", "选择角色 角色名", 20),
    ("CULTIVATION", "开始参悟", "让出战角色开始一次参悟。", "参悟", 20),
    ("BATTLE", "首次手动战斗", "在副本中完成一次怪物战斗。", "副本菜单", 35),
    ("FARM", "播种灵草", "在药园成功播种一格药田。", "药园菜单", 25),
    ("ALCHEMY", "开启炼丹", "成功开始一炉丹药炼制。", "炼丹菜单", 30),
    ("SHOP", "了解便利商店", "购买一次商城便利道具。", "商城", 15),
    ("TEAM", "群组协作", "在群聊中确认一次队伍准备。", "队伍菜单", 35),
)
TASK_BY_CODE = {task[0]: task for task in TASKS}


def task_by_key(value):
    """支持玩家以编号或内部任务码领取札记奖励。"""
    text = str(value or "").strip().upper()
    if text.isdigit() and 1 <= int(text) <= len(TASKS):
        return TASKS[int(text) - 1]
    return TASK_BY_CODE.get(text)


async def record_onboarding_event(uid, code):
    """由既有玩法在成功提交后调用；迁移未部署时不阻塞原玩法。"""
    if code not in TASK_BY_CODE:
        return False
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    INSERT INTO user_onboarding_progress (uid, task_code, completed_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
                """, (uid, code))
                await conn.commit()
        return True
    except Exception:
        return False


async def _ensure_tasks(uid, cursor):
    for code, *_ in TASKS:
        await cursor.execute("INSERT IGNORE INTO user_onboarding_progress (uid, task_code) VALUES (%s, %s)", (uid, code))
    # 为迁移前已注册的玩家补记可从现有账号状态可靠推断的两项。
    await cursor.execute("SELECT is_chushi, is_canwu FROM user_zt WHERE id = %s", (uid,))
    account = await cursor.fetchone()
    if account:
        for code, done in (("ROLE", account[0]), ("CULTIVATION", account[1])):
            if done:
                await cursor.execute("UPDATE user_onboarding_progress SET completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP) WHERE uid = %s AND task_code = %s", (uid, code))


@reg_xz_func
async def onboarding_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_tasks(uid, cursor)
            await cursor.execute("SELECT task_code, completed_at, claimed_at FROM user_onboarding_progress WHERE uid = %s", (uid,))
            progress = {row[0]: (row[1], row[2]) for row in await cursor.fetchall()}
            await conn.commit()
    completed = sum(1 for code, *_ in TASKS if progress.get(code, (None,))[0])
    output = "##### 📖 问道札记\n\n"
    output += f"完成进度：**{completed}/{len(TASKS)}**。札记只记录真实玩法行为；完成后可领取灵石引导奖励。\n\n"
    for index, (code, title, description, command, reward) in enumerate(TASKS, 1):
        done_at, claimed_at = progress.get(code, (None, None))
        state = "✅ 已领取" if claimed_at else ("🎁 可领取" if done_at else "⬜ 未完成")
        output += f"**{index}. {title}**　{state}\n> {description}｜奖励 {reward} 灵石\n"
        if done_at and not claimed_at:
            output += f"> <qqbot-cmd-input text='札记领取 {index}' show='领取奖励' />\n"
        elif not done_at:
            output += f"> <qqbot-cmd-input text='{command}' show='前往完成' />\n"
    output += "\n<qqbot-cmd-input text='道途建议' show='查看道途建议' /> | <qqbot-cmd-input text='主菜单' show='主菜单' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def onboarding_claim(uid, qz, task_key):
    task = task_by_key(task_key)
    if not task:
        return {"type": "markdown", "content": "任务编号错误，请发送“问道札记”查看可领取奖励。"}
    code, title, _, _, reward = task
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_tasks(uid, cursor)
            await cursor.execute("SELECT completed_at, claimed_at FROM user_onboarding_progress WHERE uid = %s AND task_code = %s FOR UPDATE", (uid, code))
            completed_at, claimed_at = await cursor.fetchone()
            if not completed_at:
                await conn.rollback()
                return {"type": "markdown", "content": f"「{title}」尚未完成，请先发送“问道札记”查看下一步。"}
            if claimed_at:
                await conn.rollback()
                return {"type": "markdown", "content": f"「{title}」奖励已领取，请继续完成其他札记。"}
            await cursor.execute("UPDATE user_onboarding_progress SET claimed_at = CURRENT_TIMESTAMP WHERE uid = %s AND task_code = %s AND claimed_at IS NULL", (uid, code))
            await cursor.execute("UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s", (reward, uid))
            await conn.commit()
    return {"type": "markdown", "content": f"##### 🎁 札记奖励\n\n完成：{title}\n获得：**{reward} 灵石**\n\n<qqbot-cmd-input text='问道札记' show='继续札记' />"}


@reg_xz_func
async def onboarding_advice(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_tasks(uid, cursor)
            await cursor.execute("SELECT task_code, completed_at FROM user_onboarding_progress WHERE uid = %s", (uid,))
            completed = {row[0] for row in await cursor.fetchall() if row[1]}
            await conn.commit()
    next_task = next((task for task in TASKS if task[0] not in completed), None)
    if next_task:
        _, title, description, command, _ = next_task
        content = f"##### 🧭 道途建议\n\n你当前最适合先完成：**{title}**\n> {description}\n\n<qqbot-cmd-input text='{command}' show='前往完成' />"
    else:
        content = "##### 🧭 道途建议\n\n你已完成全部新手札记。建议先提升本源、完善技能与装备，再在群聊中组队挑战三千道途。\n\n<qqbot-cmd-input text='副本菜单' show='副本挑战' /> | <qqbot-cmd-input text='队伍菜单' show='队伍菜单' />"
    return {"type": "markdown", "content": content}
