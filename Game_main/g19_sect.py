# -*- coding: utf-8 -*-
"""P2 宗门议事与师徒契约：无资产转移的异步协作玩法。"""
from datetime import date

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


RESEARCHES = {"丹道": "炼丹产量展示加成", "阵法": "队伍战斗伤害上限加成", "御器": "装备强化灵石减免", "秘境": "副本掉落展示加成"}
DAILY_CONTRIBUTION = 20


def week_key(today=None):
    today = today or date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def parse_research(value):
    value = str(value or "").strip()
    return value if value in RESEARCHES else None


async def _sect_for_user(uid, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(f"""
        SELECT s.id, s.name, s.leader_uid, sm.contribution, sm.role
        FROM sect s JOIN sect_member sm ON sm.sect_id = s.id
        WHERE sm.uid = %s AND sm.member_state = 'ACTIVE' LIMIT 1{suffix}
    """, (uid,))
    return await cursor.fetchone()


async def _settle_previous_votes(sect_id, cursor):
    """惰性结算已过周的投票，重复调用由唯一键保证幂等。"""
    await cursor.execute("SELECT DISTINCT week_key FROM sect_vote WHERE sect_id = %s AND week_key < %s", (sect_id, week_key()))
    for (past_week,) in await cursor.fetchall():
        await cursor.execute("SELECT id FROM sect_research WHERE sect_id = %s AND week_key = %s", (sect_id, past_week))
        if await cursor.fetchone():
            continue
        await cursor.execute("SELECT research_type, COUNT(*) FROM sect_vote WHERE sect_id = %s AND week_key = %s GROUP BY research_type ORDER BY COUNT(*) DESC, research_type LIMIT 1", (sect_id, past_week))
        winner = await cursor.fetchone()
        if winner:
            await cursor.execute("INSERT INTO sect_research (sect_id, week_key, research_type, vote_count) VALUES (%s, %s, %s, %s)", (sect_id, past_week, winner[0], winner[1]))


async def _render_sect(sect, cursor, notice=""):
    sect_id, name, leader_uid, contribution, role = sect
    await cursor.execute("SELECT COUNT(*) FROM sect_member WHERE sect_id = %s AND member_state = 'ACTIVE'", (sect_id,))
    member_count = (await cursor.fetchone())[0]
    await cursor.execute("SELECT research_type, COUNT(*) FROM sect_vote WHERE sect_id = %s AND week_key = %s GROUP BY research_type ORDER BY COUNT(*) DESC, research_type", (sect_id, week_key()))
    votes = await cursor.fetchall()
    await cursor.execute("SELECT week_key, research_type FROM sect_research WHERE sect_id = %s ORDER BY week_key DESC LIMIT 1", (sect_id,))
    latest_research = await cursor.fetchone()
    vote_text = "、".join(f"{item[0]} {item[1]}票" for item in votes) or "尚无人投票"
    output = f"##### 🏯 宗门｜{name}\n\n"
    output += f"成员：{member_count}/30｜你的贡献：{contribution}｜身份：{role}\n"
    output += f"本周议题：{vote_text}\n> 每周结算票数最高的研究，仅提供 PVE 小型便利，不影响玩家对战。\n"
    if latest_research:
        output += f"上周研究：{latest_research[1]}（{latest_research[0]}）\n"
    if notice:
        output += f"\n> {notice}\n"
    output += "\n<qqbot-cmd-input text='宗门委托' show='完成宗门委托' /> | <qqbot-cmd-input text='宗门投票 丹道' show='投票：丹道' />\n"
    output += "<qqbot-cmd-input text='师徒进度' show='师徒进度' /> | <qqbot-cmd-input text='宗门列表' show='宗门列表' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def sect_menu(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sect = await _sect_for_user(uid, cursor)
            if sect:
                await _settle_previous_votes(sect[0], cursor)
                result = await _render_sect(sect, cursor)
                await conn.commit()
                return result
    return {"type": "markdown", "content": "##### 🏯 宗门\n\n尚未加入宗门。\n\n<qqbot-cmd-input text='宗门列表' show='查看宗门' /> | <qqbot-cmd-input text='宗门创建 ' show='创建宗门*' />"}


@reg_xz_func
async def sect_create(uid, qz, name):
    name = str(name or "").strip()
    if not (2 <= len(name) <= 16):
        return {"type": "markdown", "content": "宗门名称需为 2-16 个字符。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            if await _sect_for_user(uid, cursor):
                return {"type": "markdown", "content": "你已在宗门中，请先退出后再创建。"}
            try:
                await cursor.execute("INSERT INTO sect (name, leader_uid) VALUES (%s, %s)", (name, uid))
            except Exception:
                return {"type": "markdown", "content": "宗门名称已存在或数据库迁移尚未部署。"}
            sect_id = cursor.lastrowid
            await cursor.execute("INSERT INTO sect_member (sect_id, uid, role, contribution, member_state) VALUES (%s, %s, '掌门', 0, 'ACTIVE')", (sect_id, uid))
            await conn.commit()
            return await _render_sect((sect_id, name, uid, 0, "掌门"), cursor, "宗门已创建。")


@reg_xz_func
async def sect_list(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT s.id, s.name, COUNT(sm.uid) AS member_count
                FROM sect s LEFT JOIN sect_member sm ON sm.sect_id = s.id AND sm.member_state = 'ACTIVE'
                GROUP BY s.id, s.name ORDER BY member_count DESC, s.id DESC LIMIT 10
            """)
            rows = await cursor.fetchall()
    output = "##### 🏯 宗门列表\n\n"
    output += "\n".join(f"> [{row[0]}] {row[1]}｜成员 {row[2]}/30｜<qqbot-cmd-input text='宗门申请 {row[0]}' show='申请加入' />" for row in rows) if rows else "> 暂无宗门，可创建第一个宗门。"
    output += "\n\n<qqbot-cmd-input text='宗门创建 ' show='创建宗门*' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def sect_apply(uid, qz, sect_id_text):
    try:
        sect_id = int(str(sect_id_text).strip())
    except ValueError:
        return {"type": "markdown", "content": "请使用：宗门申请 宗门编号。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            if await _sect_for_user(uid, cursor, True):
                return {"type": "markdown", "content": "你已在宗门中。"}
            await cursor.execute("SELECT id, name, leader_uid FROM sect WHERE id = %s FOR UPDATE", (sect_id,))
            target = await cursor.fetchone()
            if not target:
                return {"type": "markdown", "content": "未找到该宗门。"}
            await cursor.execute("SELECT COUNT(*) FROM sect_member WHERE sect_id = %s AND member_state = 'ACTIVE'", (sect_id,))
            if (await cursor.fetchone())[0] >= 30:
                return {"type": "markdown", "content": "该宗门成员已满。"}
            await cursor.execute("INSERT INTO sect_member (sect_id, uid, role, contribution, member_state) VALUES (%s, %s, '成员', 0, 'ACTIVE')", (sect_id, uid))
            await conn.commit()
            return await _render_sect((sect_id, target[1], target[2], 0, "成员"), cursor, "申请已通过，欢迎入门。")


@reg_xz_func
async def sect_commission(uid, qz):
    today = date.today()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sect = await _sect_for_user(uid, cursor, True)
            if not sect:
                return {"type": "markdown", "content": "请先加入宗门。"}
            await cursor.execute("SELECT id FROM sect_task_log WHERE sect_id = %s AND uid = %s AND task_date = %s LIMIT 1", (sect[0], uid, today))
            if await cursor.fetchone():
                return {"type": "markdown", "content": "今日宗门委托已完成，明日再来。"}
            await cursor.execute("INSERT INTO sect_task_log (sect_id, uid, task_date, contribution) VALUES (%s, %s, %s, %s)", (sect[0], uid, today, DAILY_CONTRIBUTION))
            await cursor.execute("UPDATE sect_member SET contribution = contribution + %s WHERE sect_id = %s AND uid = %s", (DAILY_CONTRIBUTION, sect[0], uid))
            await cursor.execute("UPDATE user_zt SET lingshi = lingshi + 30 WHERE id = %s", (uid,))
            await conn.commit()
            from Game_main.g21_season import record_season_event
            await record_season_event(uid, "SECT")
            return await _render_sect((sect[0], sect[1], sect[2], sect[3] + DAILY_CONTRIBUTION, sect[4]), cursor, "完成今日委托：贡献 +20，灵石 +30。")


@reg_xz_func
async def sect_vote(uid, qz, research):
    research = parse_research(research)
    if not research:
        return {"type": "markdown", "content": "研究方向仅可选：丹道、阵法、御器、秘境。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sect = await _sect_for_user(uid, cursor, True)
            if not sect:
                return {"type": "markdown", "content": "请先加入宗门。"}
            await _settle_previous_votes(sect[0], cursor)
            await cursor.execute("INSERT INTO sect_vote (sect_id, uid, week_key, research_type) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE research_type = VALUES(research_type)", (sect[0], uid, week_key(), research))
            await conn.commit()
            return await _render_sect(sect, cursor, f"已投票支持「{research}」，本周内可改投。")


async def _role_level(cursor, uid):
    await cursor.execute("SELECT MAX(dengji) FROM user_role WHERE uid = %s", (uid,))
    row = await cursor.fetchone()
    return int(row[0] or 0)


@reg_xz_func
async def apprentice_request(uid, qz, master_uid_text):
    try:
        master_uid = int(str(master_uid_text).strip())
    except ValueError:
        return {"type": "markdown", "content": "请使用：拜师 师父UID。"}
    if master_uid == uid:
        return {"type": "markdown", "content": "不可拜自己为师。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            if await _role_level(cursor, master_uid) < await _role_level(cursor, uid) + 10:
                return {"type": "markdown", "content": "师父需至少高出你 10 级。"}
            await cursor.execute("SELECT id FROM master_apprentice WHERE apprentice_uid = %s AND state IN ('PENDING', 'ACTIVE')", (uid,))
            if await cursor.fetchone():
                return {"type": "markdown", "content": "你已有生效或待确认的师徒申请。"}
            await cursor.execute("INSERT INTO master_apprentice (master_uid, apprentice_uid, state, target_progress) VALUES (%s, %s, 'PENDING', 7)", (master_uid, uid))
            await conn.commit()
    return {"type": "markdown", "content": "拜师申请已发送。请师父发送：收徒 你的UID。"}


@reg_xz_func
async def apprentice_accept(uid, qz, apprentice_uid_text):
    try:
        apprentice_uid = int(str(apprentice_uid_text).strip())
    except ValueError:
        return {"type": "markdown", "content": "请使用：收徒 徒弟UID。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) FROM master_apprentice WHERE master_uid = %s AND state = 'ACTIVE'", (uid,))
            if (await cursor.fetchone())[0] >= 3:
                return {"type": "markdown", "content": "最多同时收 3 名徒弟。"}
            await cursor.execute("UPDATE master_apprentice SET state = 'ACTIVE', accepted_at = CURRENT_TIMESTAMP, last_active_at = CURRENT_TIMESTAMP WHERE master_uid = %s AND apprentice_uid = %s AND state = 'PENDING'", (uid, apprentice_uid))
            if cursor.rowcount <= 0:
                return {"type": "markdown", "content": "未找到该徒弟的待确认申请。"}
            await conn.commit()
    return {"type": "markdown", "content": "师徒契约已生效。徒弟可每日发送「师徒修行」推进目标。"}


@reg_xz_func
async def apprentice_practice(uid, qz):
    today = date.today()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id, master_uid, progress, target_progress, last_active_at FROM master_apprentice WHERE apprentice_uid = %s AND state = 'ACTIVE' FOR UPDATE", (uid,))
            contract = await cursor.fetchone()
            if not contract:
                return {"type": "markdown", "content": "当前没有生效的师徒契约。"}
            if contract[4] and contract[4].date() == today:
                return {"type": "markdown", "content": "今日已完成师徒修行。"}
            progress = min(contract[3], contract[2] + 1)
            await cursor.execute("UPDATE master_apprentice SET progress = %s, last_active_at = CURRENT_TIMESTAMP WHERE id = %s", (progress, contract[0]))
            await cursor.execute("UPDATE user_zt SET lingshi = lingshi + 20 WHERE id IN (%s, %s)", (uid, contract[1]))
            await conn.commit()
    return {"type": "markdown", "content": f"师徒修行完成，双方各得 20 灵石。契约进度：{progress}/{contract[3]}。"}


@reg_xz_func
async def apprentice_progress(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT master_uid, apprentice_uid, state, progress, target_progress FROM master_apprentice WHERE (master_uid = %s OR apprentice_uid = %s) AND state IN ('PENDING', 'ACTIVE') ORDER BY id DESC LIMIT 6", (uid, uid))
            rows = await cursor.fetchall()
    output = "##### 🤝 师徒进度\n\n"
    output += "\n".join(f"> 师父 {row[0]}｜徒弟 {row[1]}｜{row[2]}｜进度 {row[3]}/{row[4]}" for row in rows) if rows else "> 当前无师徒契约。"
    output += "\n\n<qqbot-cmd-input text='师徒修行' show='师徒修行' />"
    return {"type": "markdown", "content": output}
