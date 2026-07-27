# -*- coding: utf-8 -*-
"""P2 八周赛季：只记录临时进度与外观资格，不改动永久数值。"""
from datetime import date, timedelta

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


EVENT_XP = {"DUNGEON": 8, "SECT": 5, "WORLD_BOSS": 10}
REWARDS = ((20, "云纹外观凭证"), (60, "诸天称号凭证"), (120, "赛季纪念外观凭证"))


def season_key(today=None):
    today = today or date.today()
    return f"{today.year}-S{((today.timetuple().tm_yday - 1) // 56) + 1}"


def season_days_left(today=None):
    today = today or date.today()
    start_day = ((today.timetuple().tm_yday - 1) // 56) * 56 + 1
    return max(0, start_day + 55 - today.timetuple().tm_yday)


def reward_for_xp(xp):
    return [item for item in REWARDS if int(xp) >= item[0]]


async def _current_season(cursor):
    key = season_key()
    await cursor.execute("INSERT INTO season (season_key, name, starts_on, ends_on) VALUES (%s, '五行天象', CURDATE(), DATE_ADD(CURDATE(), INTERVAL 56 DAY)) ON DUPLICATE KEY UPDATE season_key = VALUES(season_key)", (key,))
    await cursor.execute("SELECT id, season_key, name, ends_on FROM season WHERE season_key = %s", (key,))
    return await cursor.fetchone()


async def record_season_event(uid, source):
    """由真实玩法调用；同一来源每天仅计一次，异常不影响原玩法。"""
    xp = EVENT_XP.get(source)
    if not xp:
        return
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                season = await _current_season(cursor)
                await cursor.execute("INSERT IGNORE INTO season_task_log (season_id, uid, source, task_date, xp) VALUES (%s, %s, %s, CURDATE(), %s)", (season[0], uid, source, xp))
                if cursor.rowcount:
                    await cursor.execute("INSERT INTO user_season_progress (season_id, uid, xp) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE xp = xp + VALUES(xp)", (season[0], uid, xp))
                await conn.commit()
    except Exception:
        pass


@reg_xz_func
async def season_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            season = await _current_season(cursor)
            await cursor.execute("SELECT xp FROM user_season_progress WHERE season_id = %s AND uid = %s", (season[0], uid))
            row = await cursor.fetchone()
            xp = int(row[0]) if row else 0
            await cursor.execute("SELECT rule_name, rule_text FROM season_rule WHERE season_id = %s AND scope = 'PVE' LIMIT 1", (season[0],))
            rule = await cursor.fetchone()
            await conn.commit()
    output = f"##### ✨ 赛季｜{season[2]}\n\n赛季编号：{season[1]}｜剩余 {season_days_left()} 天\n"
    output += f"赛季经验：{xp}｜当前主题：{rule[0] if rule else '五行轮转'}\n"
    output += f"> {rule[1] if rule else '仅在 PVE 生效；赛季结束后不保留数值加成。'}\n\n"
    output += "进度来源：每日首次副本通关 +8、宗门委托 +5、世界 Boss +10。\n"
    output += "奖励为外观/称号资格，不提供不可追赶的永久数值。\n\n"
    output += "<qqbot-cmd-input text='赛季任务' show='赛季任务' /> | <qqbot-cmd-input text='赛季奖励' show='赛季奖励' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def season_tasks(uid, qz):
    return {"type": "markdown", "content": "##### ✨ 赛季任务\n\n> 每日首次副本通关：+8 赛季经验\n> 每日首次宗门委托：+5 赛季经验\n> 每日首次世界 Boss 贡献：+10 赛季经验\n\n完成对应真实玩法后自动计入，无需额外领取。\n\n<qqbot-cmd-input text='赛季' show='赛季主页' />"}


@reg_xz_func
async def season_rewards(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            season = await _current_season(cursor)
            await cursor.execute("SELECT xp FROM user_season_progress WHERE season_id = %s AND uid = %s", (season[0], uid))
            row = await cursor.fetchone()
            xp = int(row[0]) if row else 0
            eligible = reward_for_xp(xp)
            granted = []
            for threshold, name in eligible:
                await cursor.execute("INSERT IGNORE INTO season_reward_log (season_id, uid, reward_tier, reward_name) VALUES (%s, %s, %s, %s)", (season[0], uid, threshold, name))
                if cursor.rowcount:
                    granted.append(name)
            await conn.commit()
    if granted:
        return {"type": "markdown", "content": "赛季奖励已登记：" + "、".join(granted) + "。该奖励为外观/称号资格，不改变角色属性。"}
    next_item = next((item for item in REWARDS if xp < item[0]), None)
    return {"type": "markdown", "content": f"暂无可领取的赛季奖励。当前经验 {xp}；下一档：{next_item[0] if next_item else '已全部领取'}。"}
