# -*- coding: utf-8 -*-
"""P2 世界 Boss：低战力可通过辅助和净化获得参与奖励。"""
from datetime import date

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


MAX_CHALLENGES = 3
BOSS_HP = 1_000_000
ACTIONS = {"挑战": "伤害", "辅助": "辅助", "净化": "净化"}


def run_key(today=None):
    today = today or date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def parse_action(value):
    return ACTIONS.get(str(value or "").strip())


def boss_phase(current_hp, max_hp=BOSS_HP):
    ratio = max(0, current_hp) / max(1, max_hp)
    return 1 if ratio > .66 else 2 if ratio > .33 else 3


def contribution_for(action, combat_power):
    combat_power = max(1, int(combat_power))
    if action == "伤害":
        return min(50_000, max(800, combat_power * 2)), 0
    if action == "辅助":
        return 0, min(8_000, max(1_200, combat_power // 2))
    return 0, min(10_000, max(1_500, combat_power // 2 + 500))


async def _active_run(cursor, lock=False):
    key = run_key()
    await cursor.execute("INSERT INTO world_boss_run (run_key, boss_name, max_hp, current_hp, law_name) VALUES (%s, '诸天魔渊主', %s, %s, '五行轮转') ON DUPLICATE KEY UPDATE run_key = VALUES(run_key)", (key, BOSS_HP, BOSS_HP))
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(f"SELECT id, run_key, boss_name, max_hp, current_hp, law_name FROM world_boss_run WHERE run_key = %s LIMIT 1{suffix}", (key,))
    return await cursor.fetchone()


async def _remaining_attempts(cursor, run_id, uid):
    await cursor.execute("SELECT COUNT(*) FROM world_boss_contribution WHERE run_id = %s AND uid = %s", (run_id, uid))
    return max(0, MAX_CHALLENGES - (await cursor.fetchone())[0])


async def _combat_power(cursor, uid):
    await cursor.execute("SELECT COALESCE(SUM(gongji + fangyu + qixue / 10 + fali / 10), 0) FROM user_role WHERE uid = %s AND is_chuzhan = 1", (uid,))
    row = await cursor.fetchone()
    return max(1, int(row[0] or 1))


def _render(run, remain, personal=None, notice=""):
    run_id, key, name, max_hp, current_hp, law = run
    phase = boss_phase(current_hp, max_hp)
    output = f"##### 🌌 世界Boss｜{name}\n\n"
    output += f"周期：{key}｜阶段 {phase}/3｜法则：{law}\n"
    output += f"HP：{max(0, current_hp):,}/{max_hp:,}｜本周剩余挑战：{remain}/{MAX_CHALLENGES}\n"
    if personal:
        output += f"个人伤害：{personal[0]:,}｜辅助贡献：{personal[1]:,}\n"
    output += "\n> 低战力可选择辅助或净化，达到参与档即可获得完整基础奖励。"
    if notice:
        output += f"\n> {notice}\n"
    output += "\n<qqbot-cmd-input text='世界挑战 挑战' show='发起挑战' /> | <qqbot-cmd-input text='世界挑战 辅助' show='施放辅助' />\n"
    output += "<qqbot-cmd-input text='世界挑战 净化' show='净化法则' /> | <qqbot-cmd-input text='世界排行' show='世界排行' /> | <qqbot-cmd-input text='世界奖励' show='领取奖励' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def world_boss_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            run = await _active_run(cursor)
            remain = await _remaining_attempts(cursor, run[0], uid)
            await cursor.execute("SELECT COALESCE(SUM(damage), 0), COALESCE(SUM(support), 0) FROM world_boss_contribution WHERE run_id = %s AND uid = %s", (run[0], uid))
            personal = await cursor.fetchone()
    return _render(run, remain, personal)


@reg_xz_func
async def world_boss_challenge(uid, qz, action_text):
    action = parse_action(action_text)
    if not action:
        return {"type": "markdown", "content": "请选择：世界挑战 挑战/辅助/净化。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            run = await _active_run(cursor, True)
            remain = await _remaining_attempts(cursor, run[0], uid)
            if remain <= 0:
                return {"type": "markdown", "content": "本周世界 Boss 挑战次数已用完。"}
            power = await _combat_power(cursor, uid)
            damage, support = contribution_for(action, power)
            phase = boss_phase(run[4], run[3])
            if action == "净化" and phase >= 2:
                support += 800
            if run[4] <= 0:
                return {"type": "markdown", "content": "本周世界 Boss 已被讨伐，请领取奖励并等待下周。"}
            await cursor.execute("INSERT INTO world_boss_contribution (run_id, uid, action_type, damage, support) VALUES (%s, %s, %s, %s, %s)", (run[0], uid, action, damage, support))
            await cursor.execute("UPDATE world_boss_run SET current_hp = GREATEST(0, current_hp - %s) WHERE id = %s", (damage, run[0]))
            await cursor.execute("SELECT id, run_key, boss_name, max_hp, current_hp, law_name FROM world_boss_run WHERE id = %s", (run[0],))
            run = await cursor.fetchone()
            await cursor.execute("SELECT COALESCE(SUM(damage), 0), COALESCE(SUM(support), 0) FROM world_boss_contribution WHERE run_id = %s AND uid = %s", (run[0], uid))
            personal = await cursor.fetchone()
            await conn.commit()
    note = f"{action}成功：伤害 +{damage:,}，辅助贡献 +{support:,}。"
    if run[4] <= 0:
        note += " 诸天魔渊主已被讨伐！"
    return _render(run, remain - 1, personal, note)


@reg_xz_func
async def world_boss_rank(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            run = await _active_run(cursor)
            await cursor.execute("SELECT uid, SUM(damage) AS damage, SUM(support) AS support FROM world_boss_contribution WHERE run_id = %s GROUP BY uid ORDER BY (SUM(damage) + SUM(support)) DESC, uid LIMIT 10", (run[0],))
            rows = await cursor.fetchall()
    output = "##### 🌌 世界Boss排行\n\n"
    output += "\n".join(f"> {idx}. UID {row[0]}｜伤害 {row[1]:,}｜辅助 {row[2]:,}" for idx, row in enumerate(rows, 1)) if rows else "> 尚无人参与。"
    output += "\n\n<qqbot-cmd-input text='世界BOSS' show='返回世界Boss' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def world_boss_reward(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            run = await _active_run(cursor, True)
            await cursor.execute("SELECT COALESCE(SUM(damage), 0), COALESCE(SUM(support), 0) FROM world_boss_contribution WHERE run_id = %s AND uid = %s", (run[0], uid))
            damage, support = await cursor.fetchone()
            total = int(damage) + int(support)
            if total < 1_200:
                return {"type": "markdown", "content": "累计贡献达到 1200 后可领取参与奖励；辅助与净化同样计入。"}
            tier = "讨伐" if run[4] <= 0 else "参与"
            reward = 120 if tier == "讨伐" else 60
            await cursor.execute("INSERT IGNORE INTO world_boss_reward_log (run_id, uid, reward_tier, reward_lingshi) VALUES (%s, %s, %s, %s)", (run[0], uid, tier, reward))
            if cursor.rowcount <= 0:
                return {"type": "markdown", "content": "本周期该档世界 Boss 奖励已领取。"}
            await cursor.execute("UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s", (reward, uid))
            await conn.commit()
    return {"type": "markdown", "content": f"领取世界 Boss「{tier}」奖励成功：灵石 +{reward}。"}
