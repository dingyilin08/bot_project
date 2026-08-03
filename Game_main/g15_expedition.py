# -*- coding: utf-8 -*-
"""P1 三千道途：可恢复的群组异步秘境。"""

from datetime import datetime, timedelta
from hashlib import sha256
from random import Random
from uuid import uuid4

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


MAX_NODES = 6
SESSION_MINUTES = 20
VOTE_SECONDS = 120

NODES = (
    ("战斗", ("破阵", "守势")),
    ("奇遇", ("救援", "交易")),
    ("药圃", ("采集", "静修")),
    ("遗宝", ("夺宝", "参悟")),
    ("疗愈", ("调息", "探脉")),
    ("Boss", ("破局", "稳守")),
)

# 因果印记的层数只记录玩家经历，战斗效果按“是否持有”计算，避免重复刷取
# 造成永久滚雪球。数值统一用基点（10000 = 100%），供各 PVE 入口快照。
CAUSAL_MARK_EFFECTS = {
    "丹师善缘": {
        "defense_bp": 300,
        "attack_bp": 0,
        "description": "PVE 开战时防御提高 3%",
    },
    "遗宝因果": {
        "defense_bp": 0,
        "attack_bp": 300,
        "description": "PVE 开战时攻击提高 3%",
    },
}


def causal_mark_effects(mark_rows):
    """把印记历史归一为可冻结的 PVE 加成；同名印记只生效一次。"""
    owned = {}
    for row in mark_rows or ():
        if isinstance(row, str):
            name, stacks = row, 1
        else:
            name = str(row[0])
            stacks = max(1, int(row[1] or 1)) if len(row) > 1 else 1
        if name in CAUSAL_MARK_EFFECTS:
            owned[name] = max(owned.get(name, 0), stacks)

    attack_bp = sum(CAUSAL_MARK_EFFECTS[name]["attack_bp"] for name in owned)
    defense_bp = sum(CAUSAL_MARK_EFFECTS[name]["defense_bp"] for name in owned)
    return {
        "rule_version": 1,
        "attack_bp": min(attack_bp, 300),
        "defense_bp": min(defense_bp, 300),
        "marks": tuple(sorted(owned)),
        "stacks": owned,
    }


async def get_causal_mark_snapshot(uid, cursor):
    """读取玩家印记并生成战斗开始时使用的不可变规则快照。"""
    await cursor.execute(
        "SELECT mark_name, stack_count FROM user_causal_mark WHERE uid = %s ORDER BY mark_name",
        (uid,),
    )
    return causal_mark_effects(await cursor.fetchall())


def node_options(node_no):
    """返回固定路线节点，令断线恢复时的选择与展示保持一致。"""
    return NODES[min(max(int(node_no), 1), MAX_NODES) - 1]


def normalize_vote(value, node_no):
    value = str(value or "").strip()
    return value if value in node_options(node_no)[1] else None


def resolve_choice(votes, node_no):
    """多数票优先；平票以稳定哈希破除，避免重复结算改变结果。"""
    options = node_options(node_no)[1]
    counts = {option: list(votes).count(option) for option in options}
    if counts[options[0]] == counts[options[1]]:
        return options[int(sha256(f"node:{node_no}:{'|'.join(sorted(votes))}".encode()).hexdigest(), 16) % 2]
    return max(options, key=counts.get)


def outcome(node_no, choice, session_id):
    """生成确定性节点结果。奖励只在已锁定的节点日志不存在时发放。"""
    node_type, options = node_options(node_no)
    rng = Random(sha256(f"{session_id}:{node_no}:{choice}".encode()).hexdigest())
    bonus = rng.randint(0, 12)
    reward = 18 + node_no * 7 + bonus
    mark = None
    if node_type == "奇遇" and choice == "救援":
        mark, reward = "丹师善缘", reward + 8
    elif node_type == "遗宝" and choice == "夺宝":
        mark, reward = "遗宝因果", reward + 15
    elif node_type == "Boss":
        if choice == "破局":
            reward += 35
        else:
            reward += 12
    summary = {
        "战斗": "斩开拦路妖影，队伍灵息更为凝练。",
        "奇遇": "因果在此刻留下了可追溯的痕迹。",
        "药圃": "灵植的气息补足了接下来的道途。",
        "遗宝": "古修遗留的选择改变了终局的风险与收益。",
        "疗愈": "短暂休整后，队伍重整道心。",
        "Boss": "秘境核心已定，诸位各自获得本次道途馈赠。",
    }[node_type]
    return reward, mark, summary


def _need_group(group_openid):
    if not group_openid:
        return {"type": "markdown", "content": "三千道途仅可在群聊中开启，以便记录队伍与异步投票。"}
    return None


async def _session_for_member(uid, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(f"""
        SELECT e.id, e.party_id, e.group_openid, e.leader_uid, e.state, e.current_node,
               e.node_deadline, e.session_deadline
        FROM expedition_session e JOIN expedition_member em ON em.session_id = e.id
        WHERE em.uid = %s AND em.member_state = 'ACTIVE' AND e.state = 'ACTIVE'
        ORDER BY e.created_at DESC LIMIT 1{suffix}
    """, (uid,))
    row = await cursor.fetchone()
    if not row:
        return None
    fields = ("id", "party_id", "group_openid", "leader_uid", "state", "current_node", "node_deadline", "session_deadline")
    return dict(zip(fields, row))


async def _members(session_id, cursor):
    await cursor.execute("SELECT uid, last_vote FROM expedition_member WHERE session_id = %s AND member_state = 'ACTIVE' ORDER BY joined_at", (session_id,))
    return await cursor.fetchall()


async def _render(session, cursor, notice=""):
    node_type, options = node_options(session["current_node"])
    members = await _members(session["id"], cursor)
    await cursor.execute("SELECT uid, vote_choice FROM expedition_vote WHERE session_id = %s AND node_no = %s", (session["id"], session["current_node"]))
    voted = {uid: choice for uid, choice in await cursor.fetchall()}
    remaining = max(0, int((session["node_deadline"] - datetime.now()).total_seconds()))
    output = f"##### 🧭 三千道途｜第 {session['current_node']}/{MAX_NODES} 节\n\n"
    output += f"**当前节点：{node_type}**　投票剩余约 {remaining // 60:02d}:{remaining % 60:02d}\n"
    output += f"> 路线抉择：**{options[0]}** 或 **{options[1]}**。全员投票后立即结算；超时者沿用上次偏好。\n\n"
    output += "**同行道友**\n"
    for uid, _ in members:
        output += f"> UID {uid}：{'已投「' + voted[uid] + '」' if uid in voted else '等待抉择'}\n"
    if notice:
        output += f"\n> {notice}\n"
    output += f"\n<qqbot-cmd-input text='道途投票 {options[0]}' show='选择{options[0]}' /> | <qqbot-cmd-input text='道途投票 {options[1]}' show='选择{options[1]}' />\n\n"
    output += "<qqbot-cmd-input text='道途状态' show='刷新道途' /> | <qqbot-cmd-input text='道途离开' show='退出本次道途' />"
    return {"type": "markdown", "content": output}


async def _finish_node(session, cursor):
    """在会话行锁内完成一次节点，凭唯一日志保证奖励幂等。"""
    node_no = int(session["current_node"])
    await cursor.execute("SELECT uid, vote_choice FROM expedition_vote WHERE session_id = %s AND node_no = %s", (session["id"], node_no))
    votes = dict(await cursor.fetchall())
    members = await _members(session["id"], cursor)
    options = node_options(node_no)[1]
    selected = [votes.get(uid) or last_vote or options[0] for uid, last_vote in members]
    choice = resolve_choice(selected, node_no)
    reward, mark, summary = outcome(node_no, choice, session["id"])
    await cursor.execute("""
        INSERT IGNORE INTO expedition_node_log (session_id, node_no, node_type, selected_choice, reward_lingshi, summary)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (session["id"], node_no, node_options(node_no)[0], choice, reward, summary))
    if cursor.rowcount:
        for uid, _ in members:
            await cursor.execute("UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s", (reward, uid))
            if mark:
                await cursor.execute("""
                    INSERT INTO user_causal_mark (uid, mark_name, stack_count, last_session_id)
                    VALUES (%s, %s, 1, %s)
                    ON DUPLICATE KEY UPDATE stack_count = stack_count + 1, last_session_id = VALUES(last_session_id)
                """, (uid, mark, session["id"]))
    if node_no >= MAX_NODES:
        await cursor.execute("UPDATE expedition_session SET state = 'COMPLETED', completed_at = CURRENT_TIMESTAMP WHERE id = %s", (session["id"],))
        await cursor.execute("UPDATE party SET state = 'LOBBY' WHERE id = %s", (session["party_id"],))
        await cursor.execute("UPDATE party_member SET ready = 0 WHERE party_id = %s AND member_state = 'ACTIVE'", (session["party_id"],))
        session["state"] = "COMPLETED"
        return f"第 {node_no} 节「{choice}」结算：每人获得 {reward} 灵石。{summary} 本次三千道途已完成！"
    deadline = datetime.now() + timedelta(seconds=VOTE_SECONDS)
    await cursor.execute("UPDATE expedition_session SET current_node = current_node + 1, node_deadline = %s WHERE id = %s", (deadline, session["id"]))
    session["current_node"] += 1
    session["node_deadline"] = deadline
    return f"第 {node_no} 节选择「{choice}」：每人获得 {reward} 灵石。{summary} 已进入下一节点。"


async def _advance_if_due(session, cursor):
    if session["session_deadline"] <= datetime.now():
        await cursor.execute("UPDATE expedition_session SET state = 'EXPIRED', completed_at = CURRENT_TIMESTAMP WHERE id = %s", (session["id"],))
        await cursor.execute("UPDATE party SET state = 'LOBBY' WHERE id = %s", (session["party_id"],))
        session["state"] = "EXPIRED"
        return "本次道途已超过 20 分钟，队伍已安全返回。"
    if session["node_deadline"] <= datetime.now():
        return await _finish_node(session, cursor)
    return ""


@reg_xz_func
async def expedition_menu(uid, qz, group_openid):
    error = _need_group(group_openid)
    if error:
        return error
    mark_rows = ()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            session = await _session_for_member(uid, cursor, lock=True)
            if session:
                notice = await _advance_if_due(session, cursor)
                await conn.commit()
                if session["state"] == "ACTIVE":
                    return await _render(session, cursor, notice)
            await cursor.execute(
                "SELECT mark_name, stack_count FROM user_causal_mark WHERE uid = %s ORDER BY mark_name",
                (uid,),
            )
            mark_rows = await cursor.fetchall()
    output = "##### 🧭 三千道途\n\n"
    output += "2~4 名已准备的同群道友，可在 20 分钟内完成 6 个异步节点。每人每节点只需投票一次，离线时会沿用上次偏好。\n\n"
    output += "**节点：** 战斗、奇遇、药圃、遗宝、疗愈、Boss\n"
    effects = causal_mark_effects(mark_rows)
    if effects["marks"]:
        output += "**已生效印记：** " + "、".join(effects["marks"]) + "\n"
        output += f"> PVE 开战快照：攻击 +{effects['attack_bp'] / 100:.0f}%｜防御 +{effects['defense_bp'] / 100:.0f}%（层数只记录经历）\n\n"
    else:
        output += "**因果印记：** 救援丹师、夺取遗宝可留下印记，并在 PVE 开战时提供实际加成。\n\n"
    output += "<qqbot-cmd-input text='道途开启' show='队长开启道途' /> | <qqbot-cmd-input text='因果印记' show='查看因果印记' /> | <qqbot-cmd-input text='队伍菜单' show='返回队伍菜单' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def causal_marks(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT mark_name, stack_count FROM user_causal_mark WHERE uid = %s ORDER BY mark_name",
                (uid,),
            )
            rows = await cursor.fetchall()
    effects = causal_mark_effects(rows)
    output = "##### 🪶 因果印记\n\n"
    if not rows:
        output += "尚未留下因果印记。进入三千道途，在奇遇与遗宝节点作出选择即可获得。\n\n"
    else:
        for name, stacks in rows:
            rule = CAUSAL_MARK_EFFECTS.get(name)
            description = rule["description"] if rule else "只记录这段经历"
            output += f"> **{name}** ×{int(stacks)}：{description}\n"
        output += "\n印记层数会永久记录经历，但同名战斗效果不会叠加。\n\n"
    output += f"当前 PVE 加成：攻击 +{effects['attack_bp'] / 100:.0f}%｜防御 +{effects['defense_bp'] / 100:.0f}%\n\n"
    output += "<qqbot-cmd-input text='道途' show='返回三千道途' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def expedition_start(uid, qz, group_openid):
    error = _need_group(group_openid)
    if error:
        return error
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT p.id, p.leader_uid, COUNT(pm.uid), SUM(pm.ready)
                FROM party p JOIN party_member pm ON pm.party_id = p.id
                WHERE p.group_openid = %s AND p.leader_uid = %s AND p.state = 'LOBBY' AND pm.member_state = 'ACTIVE'
                GROUP BY p.id, p.leader_uid ORDER BY p.created_at DESC LIMIT 1 FOR UPDATE
            """, (group_openid, uid))
            party = await cursor.fetchone()
            if not party:
                return {"type": "markdown", "content": "请先创建队伍；只有队长可开启三千道途。"}
            party_id, _, member_count, ready_count = party
            if member_count < 2 or member_count != ready_count:
                return {"type": "markdown", "content": "三千道途需要 2~4 名同群道友全部准备后才能开启。"}
            session_id = uuid4().hex
            now = datetime.now()
            await cursor.execute("""
                INSERT INTO expedition_session (id, party_id, group_openid, leader_uid, state, current_node, node_deadline, session_deadline)
                VALUES (%s, %s, %s, %s, 'ACTIVE', 1, %s, %s)
            """, (session_id, party_id, group_openid, uid, now + timedelta(seconds=VOTE_SECONDS), now + timedelta(minutes=SESSION_MINUTES)))
            await cursor.execute("SELECT uid FROM party_member WHERE party_id = %s AND member_state = 'ACTIVE'", (party_id,))
            for (member_uid,) in await cursor.fetchall():
                await cursor.execute("INSERT INTO expedition_member (session_id, uid) VALUES (%s, %s)", (session_id, member_uid))
            await cursor.execute("UPDATE party SET state = 'EXPEDITION' WHERE id = %s", (party_id,))
            session = {"id": session_id, "party_id": party_id, "group_openid": group_openid, "leader_uid": uid, "state": "ACTIVE", "current_node": 1, "node_deadline": now + timedelta(seconds=VOTE_SECONDS), "session_deadline": now + timedelta(minutes=SESSION_MINUTES)}
            await conn.commit()
            return await _render(session, cursor, "道途已开启，首个节点等待全员抉择。")


@reg_xz_func
async def expedition_vote(uid, qz, group_openid, choice_text):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            session = await _session_for_member(uid, cursor, lock=True)
            if not session or session["group_openid"] != group_openid:
                return {"type": "markdown", "content": "当前没有可投票的三千道途；请先在队伍准备完成后开启。"}
            notice = await _advance_if_due(session, cursor)
            if notice and session["state"] != "ACTIVE":
                await conn.commit()
                return {"type": "markdown", "content": notice}
            choice = normalize_vote(choice_text, session["current_node"])
            if not choice:
                options = " / ".join(node_options(session["current_node"])[1])
                return {"type": "markdown", "content": f"本节点可选择：{options}"}
            await cursor.execute("""
                INSERT INTO expedition_vote (session_id, node_no, uid, vote_choice)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE vote_choice = VALUES(vote_choice), voted_at = CURRENT_TIMESTAMP
            """, (session["id"], session["current_node"], uid, choice))
            await cursor.execute("UPDATE expedition_member SET last_vote = %s WHERE session_id = %s AND uid = %s", (choice, session["id"], uid))
            await cursor.execute("SELECT COUNT(*) FROM expedition_vote WHERE session_id = %s AND node_no = %s", (session["id"], session["current_node"]))
            voted_count = (await cursor.fetchone())[0]
            member_count = len(await _members(session["id"], cursor))
            if voted_count >= member_count:
                notice = await _finish_node(session, cursor)
            await conn.commit()
            if session["state"] != "ACTIVE":
                return {"type": "markdown", "content": f"##### 🏁 三千道途完成\n\n{notice}\n\n<qqbot-cmd-input text='队伍菜单' show='返回队伍菜单' />"}
            return await _render(session, cursor, notice or f"已记录你的选择「{choice}」，等待其他道友。")


@reg_xz_func
async def expedition_leave(uid, qz, group_openid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            session = await _session_for_member(uid, cursor, lock=True)
            if not session or session["group_openid"] != group_openid:
                return {"type": "markdown", "content": "当前没有可退出的三千道途。"}
            await cursor.execute("UPDATE expedition_member SET member_state = 'LEFT', left_at = CURRENT_TIMESTAMP WHERE session_id = %s AND uid = %s", (session["id"], uid))
            await cursor.execute("SELECT COUNT(*) FROM expedition_member WHERE session_id = %s AND member_state = 'ACTIVE'", (session["id"],))
            if (await cursor.fetchone())[0] < 2:
                await cursor.execute("UPDATE expedition_session SET state = 'ABANDONED', completed_at = CURRENT_TIMESTAMP WHERE id = %s", (session["id"],))
                await cursor.execute("UPDATE party SET state = 'LOBBY' WHERE id = %s", (session["party_id"],))
                notice = "队伍人数不足，本次三千道途已安全结束；已结算的节点奖励不会回收。"
            else:
                notice = "你已离开本次道途，已结算的节点奖励不会回收。"
            await conn.commit()
    return {"type": "markdown", "content": notice}
