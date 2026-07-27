# -*- coding: utf-8 -*-
"""P1 队伍与阵法：同群编队的持久化入口。"""

from uuid import uuid4

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


MAX_MEMBERS = 4
FORMATIONS = {
    "锋矢": {"summary": "前列伤害 +8%，受到伤害 +5%", "positions": ("前列", "后列")},
    "玄武": {"summary": "全队防御 +8%，速度 -3%", "positions": ("前列", "后列")},
    "流云": {"summary": "全队速度 +8%，治疗效果 -5%", "positions": ("前列", "后列")},
}


def parse_formation(value):
    """解析“阵法-位置”，同时限制玩家可见的固定配置。"""
    parts = [part.strip() for part in str(value or "").split("-", 1)]
    if len(parts) != 2 or parts[0] not in FORMATIONS or parts[1] not in FORMATIONS[parts[0]]["positions"]:
        return None
    return tuple(parts)


async def _party_for_member(uid, cursor):
    await cursor.execute("""
        SELECT p.id, p.party_code, p.group_openid, p.leader_uid, p.formation, p.state
        FROM party p JOIN party_member pm ON pm.party_id = p.id
        WHERE pm.uid = %s AND pm.member_state = 'ACTIVE' AND p.state = 'LOBBY'
        ORDER BY p.created_at DESC LIMIT 1 FOR UPDATE
    """, (uid,))
    row = await cursor.fetchone()
    if not row:
        return None
    return dict(zip(("id", "party_code", "group_openid", "leader_uid", "formation", "state"), row))


async def _render_party(party_id, cursor, notice=""):
    await cursor.execute("""
        SELECT p.party_code, p.leader_uid, p.formation, pm.uid, pm.ready, pm.position
        FROM party p JOIN party_member pm ON pm.party_id = p.id
        WHERE p.id = %s AND pm.member_state = 'ACTIVE' ORDER BY pm.joined_at
    """, (party_id,))
    rows = await cursor.fetchall()
    if not rows:
        return {"type": "markdown", "content": "队伍不存在或已解散。"}
    code, leader_uid, formation = rows[0][0], rows[0][1], rows[0][2]
    output = f"##### ⚔️ 队伍 {code}\n\n"
    output += f"**阵法：{formation}**｜{FORMATIONS[formation]['summary']}\n"
    output += f"**成员：{len(rows)}/{MAX_MEMBERS}**\n\n"
    for _, _, _, member_uid, ready, position in rows:
        leader = "（队长）" if member_uid == leader_uid else ""
        output += f"> UID {member_uid}{leader}｜{position}｜{'✅ 已准备' if ready else '⌛ 未准备'}\n"
    if notice:
        output += f"\n> {notice}\n"
    output += "\n<qqbot-cmd-input text='队伍准备' show='确认准备' /> | <qqbot-cmd-input text='队伍离开' show='离开队伍' />\n\n"
    output += "<qqbot-cmd-input text='布阵 ' show='布阵 阵法-位置*' />\n"
    output += "示例：布阵 玄武-前列。秘境将在队伍全部准备且至少 2 人时开放。"
    return {"type": "markdown", "content": output}


def _need_group(group_openid):
    if group_openid:
        return None
    return {"type": "markdown", "content": "队伍功能仅可在群聊中使用，以确保同群协作与队伍归属正确。"}


@reg_xz_func
async def party_create(uid, qz, group_openid):
    error = _need_group(group_openid)
    if error:
        return error
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            if await _party_for_member(uid, cursor):
                return {"type": "markdown", "content": "你已在一个招募中的队伍中，请先离开或查看队伍。"}
            code = uuid4().hex[:8].upper()
            await cursor.execute("INSERT INTO party (party_code, group_openid, leader_uid, formation, state, max_members) VALUES (%s, %s, %s, '锋矢', 'LOBBY', %s)", (code, group_openid, uid, MAX_MEMBERS))
            party_id = cursor.lastrowid
            await cursor.execute("INSERT INTO party_member (party_id, uid, ready, position, member_state) VALUES (%s, %s, 0, '前列', 'ACTIVE')", (party_id, uid))
            await conn.commit()
            return await _render_party(party_id, cursor, "队伍已创建，将队伍码发送给同群道友加入。")


@reg_xz_func
async def party_join(uid, qz, group_openid, code_text):
    error = _need_group(group_openid)
    if error:
        return error
    code = str(code_text or "").strip().upper()
    if len(code) != 8 or not code.isalnum():
        return {"type": "markdown", "content": "队伍码错误，请发送：队伍加入 8位队伍码"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            if await _party_for_member(uid, cursor):
                return {"type": "markdown", "content": "你已在一个招募中的队伍中，请先离开当前队伍。"}
            await cursor.execute("SELECT id, group_openid, max_members FROM party WHERE party_code = %s AND state = 'LOBBY' FOR UPDATE", (code,))
            party = await cursor.fetchone()
            if not party or party[1] != group_openid:
                return {"type": "markdown", "content": "未找到本群可加入的招募队伍，请核对队伍码。"}
            party_id, _, max_members = party
            await cursor.execute("SELECT COUNT(*) FROM party_member WHERE party_id = %s AND member_state = 'ACTIVE'", (party_id,))
            if (await cursor.fetchone())[0] >= max_members:
                return {"type": "markdown", "content": "该队伍已满，请等待新队伍。"}
            await cursor.execute("INSERT INTO party_member (party_id, uid, ready, position, member_state) VALUES (%s, %s, 0, '后列', 'ACTIVE')", (party_id, uid))
            await conn.commit()
            return await _render_party(party_id, cursor, "已加入队伍，请选择阵法位置后确认准备。")


@reg_xz_func
async def party_info(uid, qz, group_openid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            party = await _party_for_member(uid, cursor)
            if not party:
                return {"type": "markdown", "content": "当前没有招募中的队伍。\n<qqbot-cmd-input text='队伍创建' show='创建队伍' />"}
            return await _render_party(party["id"], cursor)


@reg_xz_func
async def party_ready(uid, qz, group_openid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            party = await _party_for_member(uid, cursor)
            if not party:
                return {"type": "markdown", "content": "当前没有可准备的队伍。"}
            await cursor.execute("UPDATE party_member SET ready = 1 WHERE party_id = %s AND uid = %s AND member_state = 'ACTIVE'", (party["id"], uid))
            await conn.commit()
            await cursor.execute("SELECT COUNT(*), SUM(ready) FROM party_member WHERE party_id = %s AND member_state = 'ACTIVE'", (party["id"],))
            count, ready_count = await cursor.fetchone()
            notice = "全员准备完成，可由队长开启三千道途。" if count >= 2 and count == ready_count else "准备状态已更新，等待其他道友。"
            from Game_main.g16_onboarding import record_onboarding_event
            await record_onboarding_event(uid, "TEAM")
            return await _render_party(party["id"], cursor, notice)


@reg_xz_func
async def party_formation(uid, qz, group_openid, formation_text):
    selected = parse_formation(formation_text)
    if not selected:
        return {"type": "markdown", "content": "布阵格式错误，请使用：布阵 锋矢/玄武/流云-前列/后列"}
    formation, position = selected
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            party = await _party_for_member(uid, cursor)
            if not party:
                return {"type": "markdown", "content": "请先创建或加入队伍。"}
            if party["leader_uid"] != uid and formation != party["formation"]:
                return {"type": "markdown", "content": "仅队长可更换阵法；所有成员均可调整自己的前后列位置。"}
            if party["leader_uid"] == uid:
                await cursor.execute("UPDATE party SET formation = %s WHERE id = %s", (formation, party["id"]))
            await cursor.execute("UPDATE party_member SET position = %s, ready = 0 WHERE party_id = %s AND uid = %s", (position, party["id"], uid))
            await conn.commit()
            return await _render_party(party["id"], cursor, f"已调整为{formation}-{position}；阵法变更后需重新准备。")


@reg_xz_func
async def party_leave(uid, qz, group_openid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            party = await _party_for_member(uid, cursor)
            if not party:
                return {"type": "markdown", "content": "当前没有可离开的招募队伍。"}
            await cursor.execute("UPDATE party_member SET member_state = 'LEFT', left_at = CURRENT_TIMESTAMP WHERE party_id = %s AND uid = %s", (party["id"], uid))
            await cursor.execute("SELECT uid FROM party_member WHERE party_id = %s AND member_state = 'ACTIVE' ORDER BY joined_at LIMIT 1", (party["id"],))
            successor = await cursor.fetchone()
            if successor:
                await cursor.execute("UPDATE party SET leader_uid = %s WHERE id = %s", (successor[0], party["id"]))
            else:
                await cursor.execute("UPDATE party SET state = 'DISBANDED' WHERE id = %s", (party["id"],))
            await conn.commit()
    return {"type": "markdown", "content": "已离开队伍。"}
