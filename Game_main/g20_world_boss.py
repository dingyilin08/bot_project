# -*- coding: utf-8 -*-
"""P2 世界 Boss：低战力可通过辅助和净化获得参与奖励。"""
from datetime import date

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql
from Game_main.g15_expedition import get_causal_mark_snapshot
from Game_main.g21_season import get_active_season_effect, record_season_event
from Game_domain.role_special_service import (
    RoleSpecialError,
    grant_world_insight,
    world_boss_contribution,
    world_boss_loadout,
)


MAX_CHALLENGES = 3
BOSS_HP = 1_000_000
ACTIONS = {"挑战": "伤害", "辅助": "辅助", "净化": "净化", "专属": "专属"}


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


def apply_pve_damage_bonus(damage, *snapshots):
    """世界 Boss 单次行动的开战快照；总攻击增幅硬限制为 10%。"""
    total_bp = sum(max(0, int((snapshot or {}).get("attack_bp", 0))) for snapshot in snapshots)
    total_bp = min(total_bp, 1_000)
    return max(0, int(damage)) * (10_000 + total_bp) // 10_000, total_bp


def apply_world_pve_bonus(damage, support, causal_effect, season_effect):
    """把属性式开战效果映射到世界 Boss 的一次性伤害/协作贡献。"""
    causal_effect = causal_effect or {}
    season_effect = season_effect or {}
    # 世界 Boss 没有持续角色血条与行动条，因此赛季防御/速度天象按同值
    # 转为本次贡献效率；这样每一种合法天象都真实覆盖这个 PVE 入口。
    season_bp = int(season_effect.get("value_bp", 0)) if season_effect.get("active") else 0
    damage_bp = min(1_000, max(0, int(causal_effect.get("attack_bp", 0))) + season_bp)
    support_bp = min(1_000, max(0, int(causal_effect.get("defense_bp", 0))) + season_bp)
    damage = max(0, int(damage)) * (10_000 + damage_bp) // 10_000
    support = max(0, int(support)) * (10_000 + support_bp) // 10_000
    return damage, support, damage_bp, support_bp


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
    weakness_labels = ("攻伐", "守御", "生息", "控场", "破阵")
    output += f"万灵弱点：**{weakness_labels[date.today().isocalendar()[1] % 5]}**｜命中后灵兽贡献效率+5%\n"
    if personal:
        output += f"个人伤害：{personal[0]:,}｜辅助贡献：{personal[1]:,}\n"
    output += "\n> 低战力可选择辅助或净化，达到参与档即可获得完整基础奖励。"
    if notice:
        output += f"\n> {notice}\n"
    output += "\n> 贡献操作使用消息下方按钮；排行与奖励入口保留在正文中。\n"
    output += "<qqbot-cmd-input text='世界排行' show='世界排行' /> | <qqbot-cmd-input text='世界奖励' show='领取奖励' />"
    return {
        "type": "markdown",
        "content": output,
        "keyboard_commands": [
            {"command": "世界挑战 挑战", "label": "发起挑战", "style": 1},
            {"command": "世界挑战 辅助", "label": "施放辅助", "style": 1},
            {"command": "世界挑战 净化", "label": "净化法则", "style": 1},
            {"command": "世界挑战 专属", "label": "专属一击", "style": 1},
        ],
    }


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
        return {"type": "markdown", "content": "请选择：世界挑战 挑战/辅助/净化/专属。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            run = await _active_run(cursor, True)
            remain = await _remaining_attempts(cursor, run[0], uid)
            if remain <= 0:
                return {"type": "markdown", "content": "本周世界 Boss 挑战次数已用完。"}
            power = await _combat_power(cursor, uid)
            special_note = ""
            if action == "专属":
                try:
                    loadout = await world_boss_loadout(cursor, uid)
                    damage, special_note = world_boss_contribution(loadout, power, run[3])
                    support = 0
                except RoleSpecialError as error:
                    return {"type": "markdown", "content": f"专属挑战未生效：{error}"}
            else:
                damage, support = contribution_for(action, power)
            causal_effect = await get_causal_mark_snapshot(uid, cursor)
            season_effect = await get_active_season_effect(cursor)
            damage, support, damage_bonus_bp, support_bonus_bp = apply_world_pve_bonus(
                damage, support, causal_effect, season_effect
            )
            phase = boss_phase(run[4], run[3])
            if action == "净化" and phase >= 2:
                support += 800
            from Game_main.g33_spirit_beast_v2 import world_boss_beast_modifier
            beast_modifier = await world_boss_beast_modifier(uid, cursor)
            if beast_modifier["bonus_bp"]:
                damage = damage * (10_000 + beast_modifier["bonus_bp"]) // 10_000
                support = support * (10_000 + beast_modifier["bonus_bp"]) // 10_000
            if run[4] <= 0:
                return {"type": "markdown", "content": "本周世界 Boss 已被讨伐，请领取奖励并等待下周。"}
            await cursor.execute("INSERT INTO world_boss_contribution (run_id, uid, action_type, damage, support) VALUES (%s, %s, %s, %s, %s)", (run[0], uid, action, damage, support))
            await cursor.execute("UPDATE world_boss_run SET current_hp = GREATEST(0, current_hp - %s) WHERE id = %s", (damage, run[0]))
            await cursor.execute("SELECT id, run_key, boss_name, max_hp, current_hp, law_name FROM world_boss_run WHERE id = %s", (run[0],))
            run = await cursor.fetchone()
            await cursor.execute("SELECT COALESCE(SUM(damage), 0), COALESCE(SUM(support), 0) FROM world_boss_contribution WHERE run_id = %s AND uid = %s", (run[0], uid))
            personal = await cursor.fetchone()
            await conn.commit()
    await record_season_event(uid, "WORLD_BOSS")
    from Game_main.g33_spirit_beast_v2 import record_spirit_beast_world_boss
    await record_spirit_beast_world_boss(uid, action)
    note = f"{special_note or action}成功：伤害 +{damage:,}，辅助贡献 +{support:,}。"
    shown_bonus_bp = damage_bonus_bp if damage else support_bonus_bp
    if shown_bonus_bp:
        note += f" PVE 开战/贡献加成 +{shown_bonus_bp / 100:.0f}%。"
    if beast_modifier["bonus_bp"]:
        note += (
            f" 万灵弱点「{beast_modifier['label']}」命中，"
            f"{beast_modifier['main_name']}贡献效率 +5%。"
        )
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
    insight = None
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
    insight = await grant_world_insight(run_key=run[1], uid=uid)
    content = f"领取世界 Boss「{tier}」奖励成功：灵石 +{reward}。"
    if insight:
        content += f"\n获得{insight['role_name']}角色感悟：本体感悟 +2、感悟精华 +10、组合核心 +1。"
        if insight.get("extra_name"):
            content += f"\n{insight['extra_name']} +1。"
    return {"type": "markdown", "content": content}
