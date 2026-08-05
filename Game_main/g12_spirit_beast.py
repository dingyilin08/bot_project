# -*- coding: utf-8 -*-
"""P1 灵兽系统：寻访、收藏、出战与战斗协同。"""

from datetime import date
from hashlib import sha256
from random import Random

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


MAX_BEASTS = 4  # 1 只出战 + 3 只灵兽园收藏
TEMPERAMENTS = ("勇猛", "沉稳", "灵慧", "狡黠")
ROLE_LABELS = {"STRIKER": "输出·追击", "GUARDIAN": "护法·护盾", "HEALER": "灵医·疗愈", "DISRUPTOR": "扰敌·迟滞"}
SPIRIT_BEAST_SNAPSHOT_VERSION = 1


def _clamp(value, lower, upper):
    return max(lower, min(upper, value))


def combat_bonus(profile):
    """将灵兽资质映射为透明、有限的战斗加成，不写入角色基础属性。"""
    if not profile:
        return {}
    aptitude = _clamp(int(profile["aptitude"]), 60, 100)
    amount = 4 + (aptitude - 60) // 5
    role = profile["role"]
    if role == "STRIKER":
        return {"buff_type": "attack_up", "value": amount, "label": "追击灵契"}
    if role == "GUARDIAN":
        return {"buff_type": "defense_up", "value": amount, "label": "护法灵契"}
    if role == "HEALER":
        return {"buff_type": "heal_over_time", "value": max(2, amount // 2), "label": "灵医回春"}
    return {"buff_type": "speed_up", "value": amount, "label": "扰敌灵契"}


def origin_synergy_effect(origin_name, profile):
    """返回可冻结到 PVE 快照的本源协同。

    协同只有四种白名单机器码，不会把玩家文本直接解释成战斗数值。
    旧数据没有本字段时仍只保留基础灵契。
    """
    if not profile:
        return {}
    origin_name = origin_name or ""
    role = profile["role"]
    if any(word in origin_name for word in ("异火", "炎", "焰")) and role == "STRIKER":
        return {
            "code": "FIRE_STRIKER",
            "label": "异火协同：本场首个成功施加灼烧的火行技能，灼烧 +1 回合。",
            "burn_duration_bonus": 1,
            "max_triggers": 1,
        }
    if "轮回" in origin_name and role == "HEALER":
        return {
            "code": "REINCARNATION_HEALER",
            "label": "轮回协同：本场首次气血不高于 30% 时，回复 5% 最大气血。",
            "threshold": 30,
            "heal_percent": 5,
            "max_triggers": 1,
        }
    if any(word in origin_name for word in ("掌天", "青元")) and role == "GUARDIAN":
        return {
            "code": "TREASURE_GUARDIAN",
            "label": "掌天协同：本场首次获得护盾时，护盾减伤强度 +5 个百分点。",
            "shield_bonus": 5,
            "max_triggers": 1,
        }
    if role == "DISRUPTOR":
        return {
            "code": "DISRUPTOR_INITIATIVE",
            "label": "扰敌协同：灵契速度增益直接参与本场开场先手判定。",
            "max_triggers": 0,
        }
    return {}


def origin_synergy(origin_name, profile):
    """根据角色本源返回与实际战斗规则一致的展示文本。"""
    effect = origin_synergy_effect(origin_name, profile)
    if effect:
        return effect["label"]
    if not profile:
        return ""
    return "当前本源未触发额外协同；基础灵契仍正常生效。"


async def _active_profile(uid, cursor):
    await cursor.execute("""
        SELECT ub.id, ub.aptitude, ub.temperament, ub.bond_exp,
               db.name, db.role, db.element, db.passive_name, db.description
        FROM user_spirit_beast ub JOIN data_spirit_beast db ON db.id = ub.beast_id
        WHERE ub.uid = %s AND ub.is_active = 1 LIMIT 1
    """, (uid,))
    row = await cursor.fetchone()
    if not row:
        return None
    keys = ("id", "aptitude", "temperament", "bond_exp", "name", "role", "element", "passive_name", "description")
    return dict(zip(keys, row))


async def get_active_beast_profile(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _active_profile(uid, cursor)
            if profile:
                profile["origin_name"] = await _origin_name(uid, cursor)
            return profile


async def get_active_beast_snapshot(uid, cursor):
    """使用调用方事务冻结出战灵兽，供单人/队伍 PVE 共用。"""
    profile = await _active_profile(uid, cursor)
    if not profile:
        return None
    origin_name = await _origin_name(uid, cursor)
    bonus = combat_bonus(profile)
    synergy = origin_synergy_effect(origin_name, profile)
    return {
        "schema_version": SPIRIT_BEAST_SNAPSHOT_VERSION,
        "instance_id": int(profile["id"]),
        "name": profile["name"],
        "role": profile["role"],
        "element": profile["element"],
        "origin_name": origin_name,
        "combat_bonus": dict(bonus),
        "synergy": dict(synergy),
        "triggered": 0,
        "events": [],
    }


async def apply_active_beast_to_entity(uid, entity):
    """向战斗实体注入可序列化 Buff，供 battle_session 重启后恢复。"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            snapshot = await get_active_beast_snapshot(uid, cursor)
    return apply_beast_snapshot_to_entity(snapshot, entity)


def apply_beast_snapshot_to_entity(snapshot, entity):
    """将已冻结灵兽快照注入实体，避免战斗创建后再次读取实时数据库。"""
    if not snapshot:
        return None
    from Tool.combat_system import Buff
    bonus = snapshot["combat_bonus"]
    entity.add_buff(Buff(bonus["buff_type"], bonus["value"], 99, snapshot["name"], bonus["label"]))
    entity.role_data["spirit_beast"] = snapshot
    return snapshot


async def _current_capacity(uid, cursor):
    """读取灵兽园容量；缺失洞府旧数据时安全回落到 4 只。"""
    from Game_main.g14_estate import read_estate_levels, spirit_beast_capacity

    levels = await read_estate_levels(uid, cursor, ensure_rows=False)
    return spirit_beast_capacity(levels.get("beast_garden", 1))


def _capacity_notice(count, capacity):
    if int(count) <= int(capacity):
        return ""
    return f"已超出当前容量 {count}/{capacity}；旧灵兽会保留，扩建灵兽园前无法继续寻访。"


async def _origin_name(uid, cursor):
    await cursor.execute("""
        SELECT b.name FROM user_role r
        LEFT JOIN user_benyuan b ON b.id = r.by_id AND b.uid = r.uid
        WHERE r.uid = %s AND r.is_chuzhan = 1 LIMIT 1
    """, (uid,))
    row = await cursor.fetchone()
    return row[0] if row else ""


def _beast_lines(profile, origin_name=""):
    bonus = combat_bonus(profile)
    lines = [f"**#{profile['id']} {profile['name']}**｜{ROLE_LABELS.get(profile['role'], profile['role'])}",
             f"> 资质：{profile['aptitude']} | 性格：{profile['temperament']} | 血脉：{profile['element']}",
             f"> 灵契：{bonus['label']}（{bonus['value']}%）",
             f"> 被动：{profile['passive_name']}｜{profile['description']}"]
    if origin_name:
        lines.append(f"> {origin_synergy(origin_name, profile)}")
    return lines


@reg_xz_func
async def spirit_beast_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT ub.id, ub.aptitude, ub.temperament, ub.bond_exp, db.name, db.role,
                       db.element, db.passive_name, db.description, ub.is_active
                FROM user_spirit_beast ub JOIN data_spirit_beast db ON db.id = ub.beast_id
                WHERE ub.uid = %s ORDER BY ub.is_active DESC, ub.obtained_at ASC
            """, (uid,))
            rows = await cursor.fetchall()
            origin_name = await _origin_name(uid, cursor)
            capacity = await _current_capacity(uid, cursor)
    output = "##### 🐾 灵兽园\n\n" + f"收藏：{len(rows)}/{capacity}｜出战灵兽会在副本回合战斗中提供灵契。\n\n"
    capacity_warning = _capacity_notice(len(rows), capacity)
    if capacity_warning:
        output += f"> ⚠️ {capacity_warning}\n\n"
    if not rows:
        output += "尚无灵兽。完成一次副本后，可每日进行一次灵兽寻访。\n\n"
    else:
        for row in rows:
            keys = ("id", "aptitude", "temperament", "bond_exp", "name", "role", "element", "passive_name", "description", "is_active")
            profile = dict(zip(keys, row))
            output += ("**【出战中】**\n" if profile.pop("is_active") else "")
            output += "\n".join(_beast_lines(profile, origin_name)) + "\n\n"
    output += "<qqbot-cmd-input text='灵兽寻访' show='灵兽寻访' /> | <qqbot-cmd-input text='灵兽图鉴' show='灵兽图鉴' />\n\n"
    output += "<qqbot-cmd-input text='灵兽出战 ' show='灵兽出战 灵兽编号*' /> | <qqbot-cmd-input text='洞府' show='查看容量与升级' />\n\n"
    output += "<qqbot-cmd-input text='灵兽菜单' show='灵兽功能说明' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def spirit_beast_catalog(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id, name, role, element, passive_name, description FROM data_spirit_beast ORDER BY id")
            rows = await cursor.fetchall()
            capacity = await _current_capacity(uid, cursor)
    output = f"##### 🐾 灵兽图鉴\n\n**当前灵兽园容量：{capacity}只**\n\n"
    for beast_id, name, role, element, passive_name, description in rows:
        output += f"**{name}**｜{ROLE_LABELS.get(role, role)}｜{element}\n> {passive_name}：{description}\n\n"
    output += "来源：完成副本后每日可进行一次灵兽寻访；灵兽不在商城出售。\n\n<qqbot-cmd-input text='灵兽' show='返回灵兽园' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def seek_spirit_beast(uid, qz):
    """每日一次；须先完成当天任意副本，防止绕过 PVE 循环。"""
    today = date.today()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT 1 FROM user_dungeon_drop WHERE uid = %s AND DATE(drop_time) = %s LIMIT 1", (uid, today))
            if not await cursor.fetchone():
                return {"type": "markdown", "content": "今日尚未完成副本。先挑战一次怪物，再来寻访灵兽吧。\n<qqbot-cmd-input text='副本列表' show='查看副本' />"}
            await cursor.execute("SELECT 1 FROM user_spirit_beast_capture WHERE uid = %s AND capture_date = %s", (uid, today))
            if await cursor.fetchone():
                return {"type": "markdown", "content": "今日已完成灵兽寻访，请明日再来。\n<qqbot-cmd-input text='灵兽' show='查看灵兽园' />"}
            capacity = await _current_capacity(uid, cursor)
            await cursor.execute("SELECT COUNT(*) FROM user_spirit_beast WHERE uid = %s", (uid,))
            owned_count = int((await cursor.fetchone())[0])
            if owned_count >= capacity:
                warning = _capacity_notice(owned_count, capacity)
                message = warning or f"灵兽园已满（{owned_count}/{capacity}）。升级洞府灵兽园后可扩展容量。"
                return {"type": "markdown", "content": message}
            await cursor.execute("SELECT id, name FROM data_spirit_beast ORDER BY id")
            templates = await cursor.fetchall()
            if not templates:
                return {"type": "markdown", "content": "灵兽图鉴尚未初始化，请管理员执行 P1 灵兽数据库迁移。"}
            rng = Random(sha256(f"{uid}:{today.isoformat()}".encode()).hexdigest())
            beast_id, name = rng.choice(templates)
            aptitude, temperament = rng.randint(70, 95), rng.choice(TEMPERAMENTS)
            await cursor.execute("INSERT INTO user_spirit_beast (uid, beast_id, aptitude, temperament, is_active) VALUES (%s, %s, %s, %s, 0)", (uid, beast_id, aptitude, temperament))
            instance_id = cursor.lastrowid
            await cursor.execute("INSERT INTO user_spirit_beast_capture (uid, capture_date, beast_instance_id) VALUES (%s, %s, %s)", (uid, today, instance_id))
            await conn.commit()
    return {"type": "markdown", "content": f"##### ✨ 灵兽寻访成功\n\n你与 **{name}** 结下灵契！\n> 资质：{aptitude}｜性格：{temperament}\n\n<qqbot-cmd-input text='灵兽出战 {instance_id}' show='设为出战灵兽' /> | <qqbot-cmd-input text='灵兽' show='查看灵兽园' />"}


@reg_xz_func
async def set_active_spirit_beast(uid, qz, beast_text):
    try:
        beast_id = int(str(beast_text).strip())
    except ValueError:
        return {"type": "markdown", "content": "灵兽编号错误，请发送：灵兽出战 灵兽编号"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT id FROM user_spirit_beast WHERE id = %s AND uid = %s", (beast_id, uid))
            if not await cursor.fetchone():
                return {"type": "markdown", "content": "未找到这只灵兽，请从灵兽园中选择。"}
            capacity = await _current_capacity(uid, cursor)
            await cursor.execute("SELECT COUNT(*) FROM user_spirit_beast WHERE uid = %s", (uid,))
            owned_count = int((await cursor.fetchone())[0])
            await cursor.execute("UPDATE user_spirit_beast SET is_active = 0 WHERE uid = %s", (uid,))
            await cursor.execute("UPDATE user_spirit_beast SET is_active = 1 WHERE id = %s AND uid = %s", (beast_id, uid))
            await conn.commit()
    warning = _capacity_notice(owned_count, capacity)
    suffix = f"\n> ⚠️ {warning}" if warning else ""
    return {"type": "markdown", "content": f"已设置出战灵兽；下一场新开启的副本战斗将立即获得它的灵契。{suffix}\n<qqbot-cmd-input text='灵兽' show='查看灵兽园' />"}
