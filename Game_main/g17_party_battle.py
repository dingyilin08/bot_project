# -*- coding: utf-8 -*-
"""P1 群队伍统一回合结算：所有成员提交后按同一快照结算。"""

from hashlib import sha256
from random import Random
from uuid import uuid4

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


ACTION_LABELS = {"普攻": "ATTACK", "防御": "DEFEND", "调息": "MEDITATE"}


def normalize_action(value):
    return ACTION_LABELS.get(str(value or "").strip())


def resolve_party_round(members, actions, enemy, seed):
    """确定性统一结算；传入/返回均为可 JSON 序列化快照。"""
    rng = Random(sha256(str(seed).encode()).hexdigest())
    members = [dict(member) for member in members]
    enemy = dict(enemy)
    logs = []
    for member in members:
        member["defending"] = False
    for member in sorted((item for item in members if item["hp"] > 0), key=lambda item: (-item["speed"], item["uid"])):
        action = actions.get(str(member["uid"]), "DEFEND")
        if action == "DEFEND":
            member["defending"] = True
            logs.append(f"{member['name']}采取防御姿态。")
        elif action == "MEDITATE":
            member["mana"] = min(member["max_mana"], member["mana"] + 25)
            logs.append(f"{member['name']}调息回灵。")
        else:
            damage = max(1, int(member["attack"] * (0.9 + rng.random() * 0.2)))
            enemy["hp"] -= damage
            logs.append(f"{member['name']}造成{damage}点伤害。")
        if enemy["hp"] <= 0:
            break
    if enemy["hp"] > 0:
        living = [item for item in members if item["hp"] > 0]
        if living:
            target = min(living, key=lambda item: (item["hp"] / max(1, item["max_hp"]), item["uid"]))
            damage = max(1, int(enemy["attack"] * (0.9 + rng.random() * 0.2)))
            if target["defending"]:
                damage = max(1, int(damage * 0.55))
            target["hp"] -= damage
            logs.append(f"{enemy['name']}攻击{target['name']}，造成{damage}点伤害。")
    return members, enemy, logs


async def _active_party(uid, group_openid, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(f"""
        SELECT p.id, p.group_openid, p.leader_uid, p.formation
        FROM party p JOIN party_member pm ON pm.party_id = p.id
        WHERE pm.uid = %s AND pm.member_state = 'ACTIVE' AND p.group_openid = %s AND p.state = 'LOBBY'
        LIMIT 1{suffix}
    """, (uid, group_openid))
    return await cursor.fetchone()


async def _load_session(uid, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(f"""
        SELECT b.id, b.party_id, b.round_no, b.state, b.snapshot_json
        FROM party_battle_session b JOIN party_battle_member bm ON bm.session_id = b.id
        WHERE bm.uid = %s AND b.state = 'ACTIVE' LIMIT 1{suffix}
    """, (uid,))
    return await cursor.fetchone()


def _render(session_id, round_no, snapshot, submitted, notice=""):
    enemy = snapshot["enemy"]
    members = snapshot["members"]
    output = f"##### ⚔️ 队伍战斗｜第 {round_no} 回合\n\n"
    output += f"**敌方：{enemy['name']}** HP {max(0, enemy['hp'])}/{enemy['max_hp']}\n\n"
    for member in members:
        state = "已提交" if str(member["uid"]) in submitted else "等待行动"
        output += f"> {member['name']}：HP {max(0, member['hp'])}/{member['max_hp']}｜{state}\n"
    if notice:
        output += f"\n> {notice}\n"
    output += "\n<qqbot-cmd-input text='队伍战斗行动 普攻' show='普攻' /> | <qqbot-cmd-input text='队伍战斗行动 防御' show='防御' /> | <qqbot-cmd-input text='队伍战斗行动 调息' show='调息' />\n\n"
    output += "<qqbot-cmd-input text='队伍战斗状态' show='刷新战斗' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def party_battle_start(uid, qz, group_openid):
    if not group_openid:
        return {"type": "markdown", "content": "队伍战斗仅可在群聊中开启。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            party = await _active_party(uid, group_openid, cursor, lock=True)
            if not party or party[2] != uid:
                return {"type": "markdown", "content": "请由已创建队伍的队长在群内开启队伍战斗。"}
            party_id, _, _, formation = party
            await cursor.execute("SELECT uid, ready FROM party_member WHERE party_id = %s AND member_state = 'ACTIVE'", (party_id,))
            rows = await cursor.fetchall()
            if len(rows) < 2 or not all(row[1] for row in rows):
                return {"type": "markdown", "content": "队伍战斗需要至少两名成员且全员准备。"}
            await cursor.execute("""
                SELECT r.uid, r.name, r.qixue, r.gongji, r.fangyu, r.sudu, r.fali
                FROM user_role r JOIN party_member pm ON pm.uid = r.uid
                WHERE pm.party_id = %s AND pm.member_state = 'ACTIVE' AND r.is_chuzhan = 1
            """, (party_id,))
            role_rows = await cursor.fetchall()
            if len(role_rows) != len(rows):
                return {"type": "markdown", "content": "请确保所有队员均有出战角色后再开启。"}
            members = [{"uid": row[0], "name": row[1], "hp": int(row[2]), "max_hp": int(row[2]), "attack": int(row[3]), "defense": int(row[4]), "speed": int(row[5]), "mana": int(row[6]), "max_mana": int(row[6])} for row in role_rows]
            total_hp = sum(item["max_hp"] for item in members)
            total_atk = sum(item["attack"] for item in members)
            snapshot = {"members": members, "enemy": {"name": "道途守关者", "hp": int(total_hp * 0.75), "max_hp": int(total_hp * 0.75), "attack": max(1, int(total_atk / len(members) * 0.55)), "formation": formation}}
            session_id = uuid4().hex
            import json
            await cursor.execute("INSERT INTO party_battle_session (id, party_id, round_no, state, snapshot_json) VALUES (%s, %s, 1, 'ACTIVE', %s)", (session_id, party_id, json.dumps(snapshot, ensure_ascii=False)))
            for member in members:
                await cursor.execute("INSERT INTO party_battle_member (session_id, uid) VALUES (%s, %s)", (session_id, member["uid"]))
            await conn.commit()
    return _render(session_id, 1, snapshot, set(), "队伍战斗已开启，等待全员行动。")


@reg_xz_func
async def party_battle_status(uid, qz, group_openid):
    import json
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            session = await _load_session(uid, cursor)
            if not session:
                return {"type": "markdown", "content": "当前没有进行中的队伍战斗。"}
            await cursor.execute("SELECT uid FROM party_battle_action WHERE session_id = %s AND round_no = %s", (session[0], session[2]))
            submitted = {str(row[0]) for row in await cursor.fetchall()}
            return _render(session[0], session[2], json.loads(session[4]), submitted)


@reg_xz_func
async def party_battle_action(uid, qz, group_openid, action_text):
    action = normalize_action(action_text)
    if not action:
        return {"type": "markdown", "content": "行动错误，请使用：队伍战斗行动 普攻/防御/调息。"}
    import json
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            session = await _load_session(uid, cursor, lock=True)
            if not session:
                return {"type": "markdown", "content": "当前没有进行中的队伍战斗。"}
            session_id, party_id, round_no, _, raw = session
            await cursor.execute("INSERT INTO party_battle_action (session_id, round_no, uid, action_type) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE action_type = VALUES(action_type)", (session_id, round_no, uid, action))
            await cursor.execute("SELECT uid, action_type FROM party_battle_action WHERE session_id = %s AND round_no = %s", (session_id, round_no))
            actions = {str(row[0]): row[1] for row in await cursor.fetchall()}
            snapshot = json.loads(raw)
            alive = [member for member in snapshot["members"] if member["hp"] > 0]
            if len(actions) < len(alive):
                await conn.commit()
                return _render(session_id, round_no, snapshot, set(actions), "已记录你的行动，等待其他道友。")
            members, enemy, logs = resolve_party_round(snapshot["members"], actions, snapshot["enemy"], f"{session_id}:{round_no}")
            snapshot.update({"members": members, "enemy": enemy})
            if enemy["hp"] <= 0:
                await cursor.execute("UPDATE party_battle_session SET state = 'COMPLETED', snapshot_json = %s WHERE id = %s", (json.dumps(snapshot, ensure_ascii=False), session_id))
                for member in members:
                    await cursor.execute("UPDATE user_zt SET lingshi = lingshi + 60 WHERE id = %s", (member["uid"],))
                await conn.commit()
                return {"type": "markdown", "content": "##### 🏆 队伍战斗胜利\n\n" + "\n".join(f"> {line}" for line in logs) + "\n\n每位参战道友获得 **60 灵石**。"}
            if not any(member["hp"] > 0 for member in members):
                await cursor.execute("UPDATE party_battle_session SET state = 'FAILED', snapshot_json = %s WHERE id = %s", (json.dumps(snapshot, ensure_ascii=False), session_id))
                await conn.commit()
                return {"type": "markdown", "content": "##### 队伍战斗结束\n\n全员力竭，本次未获得胜利奖励。"}
            await cursor.execute("UPDATE party_battle_session SET round_no = round_no + 1, snapshot_json = %s WHERE id = %s", (json.dumps(snapshot, ensure_ascii=False), session_id))
            await conn.commit()
            return _render(session_id, round_no + 1, snapshot, set(), "\n".join(logs))
