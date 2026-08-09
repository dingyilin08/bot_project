# -*- coding: utf-8 -*-
"""《诸天灵契》V2：寻踪、养成、灵阵、秘境、派遣、传记与长期协作。"""

from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import math

from Game_domain.spirit_beast_v2_rules import (
    QUALITY_RANK, ROLE_BUFF, ROLE_LABELS, RULE_VERSION, SKILL_BY_ID, SKILLS,
    SLOTS, STAGE_COSTS, STAGE_MATERIALS, STAGES, TEMPLATE_BY_ID,
    TEMPLATE_BY_NAME, TEMPLATES, TEMPERAMENTS, WORLDS, WORLD_ROLE,
    aptitude_average, bond_level, calculate_v2_power, choose_template,
    deterministic_rng, dispatch_reward, feed_plan, formation_resonance,
    generate_aptitudes, realm_reward, return_refund, roll_quality,
    stage_name, unlocked_slots, week_key,
)
from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


WALLET_COLUMNS = {
    "beast_trace", "soul_stone", "spirit_essence", "beast_material",
    "wash_dew", "bloodline_essence", "skill_page", "story_token",
    "nameplate", "soul_fragment",
}
DISPATCH_TYPES = ("巡山", "采药", "探矿", "寻迹")
REALM_ROUTES = ("血脉", "技能", "羁绊")
STORY_THRESHOLDS = (2, 4, 6, 8)


def _md(content):
    return {"type": "markdown", "content": content}


def _parts(value):
    return str(value or "").replace("【", "").replace("】", "").split()


def _token(uid, action, *values):
    raw = ":".join([str(uid), action, *(str(value) for value in values), datetime.now().isoformat()])
    return sha256(raw.encode("utf-8")).hexdigest()[:32]


def _display_name(profile):
    return profile.get("nickname") or profile.get("name") or "未知灵兽"


def collection_capacity(garden_level):
    level = max(1, min(10, int(garden_level or 1)))
    return 4 + (level - 1) // 3


def _apply_returned_quality(profile):
    if int(profile.get("bloodline_nodes", 0) or 0) >= 6:
        profile["quality"] = {
            "灵品": "玄品", "玄品": "地品",
        }.get(profile.get("quality"), profile.get("quality"))
    return profile


def formation_combat_effect(profile):
    """生成稳定的主契战斗效果契约，展示字段与数值字段必须同时存在。"""
    buff_type, cap = ROLE_BUFF.get(profile["role"], ("attack_up", 5))
    average = aptitude_average((
        profile["apt_spirit"], profile["apt_body"],
        profile["apt_soul"], profile["apt_speed"],
    ))
    temperament_roles = {
        "勇猛": {"STRIKER"}, "沉稳": {"GUARDIAN"},
        "灵慧": {"HEALER", "BREAKER"}, "机敏": {"DISRUPTOR"},
    }
    temperament_bonus = int(
        profile["role"] in temperament_roles.get(profile["temperament"], set())
    )
    return {
        "buff_type": buff_type,
        "value": min(
            cap,
            4 + (average - 60) // 8
            + int(profile["bloodline_nodes"]) // 2
            + temperament_bonus,
        ),
        "code": profile["talent_code"],
        "label": f"{ROLE_LABELS.get(profile['role'], '主契')}灵契",
    }


async def _ensure_user(uid, cursor):
    await cursor.execute("INSERT IGNORE INTO user_spirit_beast_wallet(uid) VALUES(%s)", (uid,))
    await cursor.execute("INSERT IGNORE INTO user_spirit_beast_pity(uid) VALUES(%s)", (uid,))


async def _current_role(uid, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        f"SELECT id,name,dengji,is_chuzhan FROM user_role "
        f"WHERE uid=%s AND is_chuzhan=1 LIMIT 1{suffix}",
        (uid,),
    )
    return await cursor.fetchone()


async def _owned_role(uid, role_id, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        f"SELECT id,name,dengji,is_chuzhan FROM user_role "
        f"WHERE uid=%s AND id=%s LIMIT 1{suffix}",
        (uid, role_id),
    )
    return await cursor.fetchone()


async def _garden_level(uid, cursor):
    await cursor.execute(
        "SELECT level FROM user_estate_building "
        "WHERE uid=%s AND building_type='灵兽园' LIMIT 1",
        (uid,),
    )
    row = await cursor.fetchone()
    return max(1, min(10, int(row[0] if row else 1)))


async def _wallet(uid, cursor, lock=False):
    await _ensure_user(uid, cursor)
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        "SELECT beast_trace,soul_stone,spirit_essence,beast_material,wash_dew,"
        "bloodline_essence,skill_page,story_token,nameplate,soul_fragment "
        f"FROM user_spirit_beast_wallet WHERE uid=%s{suffix}",
        (uid,),
    )
    row = await cursor.fetchone()
    keys = (
        "beast_trace", "soul_stone", "spirit_essence", "beast_material",
        "wash_dew", "bloodline_essence", "skill_page", "story_token",
        "nameplate", "soul_fragment",
    )
    wallet = dict(zip(keys, (int(value or 0) for value in row)))
    await cursor.execute(
        f"SELECT item_num FROM user_item WHERE uid=%s AND item_id=3200{suffix}",
        (uid,),
    )
    material = await cursor.fetchone()
    # 基础兽材以普通背包为唯一库存源，才能安全参与坊市交易。
    wallet["beast_material"] = int(material[0] or 0) if material else 0
    return wallet


async def _wallet_change(cursor, uid, changes):
    changes = {
        key: int(value) for key, value in changes.items()
        if key in WALLET_COLUMNS and int(value) != 0
    }
    material_change = int(changes.pop("beast_material", 0))
    if not changes and not material_change:
        return True
    await _ensure_user(uid, cursor)
    if material_change > 0:
        await cursor.execute("""
            INSERT INTO user_item(uid,item_id,item_num) VALUES(%s,3200,%s)
            ON DUPLICATE KEY UPDATE item_num=item_num+VALUES(item_num)
        """, (uid, material_change))
    elif material_change < 0:
        await cursor.execute("""
            UPDATE user_item SET item_num=item_num-%s
            WHERE uid=%s AND item_id=3200 AND item_num>=%s
        """, (-material_change, uid, -material_change))
        if cursor.rowcount <= 0:
            return False
    if not changes:
        return True
    setters = ",".join(f"{key}={key}+%s" for key in changes)
    conditions = [f"{key}>=%s" for key, value in changes.items() if value < 0]
    params = list(changes.values()) + [uid] + [
        -value for value in changes.values() if value < 0
    ]
    sql = f"UPDATE user_spirit_beast_wallet SET {setters} WHERE uid=%s"
    if conditions:
        sql += " AND " + " AND ".join(conditions)
    await cursor.execute(sql, tuple(params))
    return cursor.rowcount > 0


async def _count_beasts(uid, cursor):
    await cursor.execute(
        "SELECT COUNT(*) FROM user_spirit_beast_v2 WHERE uid=%s", (uid,)
    )
    return int((await cursor.fetchone())[0])


async def _refresh_current_power(conn, uid):
    """所有可能改变主契战力的事务都从同一聚合入口刷新。"""
    from Tool.tool_power import update_role_power
    await update_role_power(conn, uid)


async def _load_beast(uid, beast_id, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(f"""
        SELECT b.id,b.uid,b.template_id,b.nickname,b.level,b.level_exp,b.stage,
               b.temperament,b.bond_exp,b.locked,b.initial_contract,
               t.name,t.world,t.quality,t.role_code,t.element,t.talent_code,
               t.talent_name,t.description,a.spirit,a.body,a.soul,a.speed,
               a.highest_total,a.miss_count,COALESCE(bl.nodes,0)
        FROM user_spirit_beast_v2 b
        JOIN spirit_beast_template t ON t.id=b.template_id
        JOIN user_spirit_beast_aptitude a ON a.beast_id=b.id
        LEFT JOIN user_spirit_beast_bloodline bl
          ON bl.uid=b.uid AND bl.template_id=b.template_id
        WHERE b.uid=%s AND b.id=%s LIMIT 1{suffix}
    """, (uid, beast_id))
    row = await cursor.fetchone()
    if not row:
        return None
    keys = (
        "id", "uid", "template_id", "nickname", "level", "level_exp", "stage",
        "temperament", "bond_exp", "locked", "initial_contract", "name",
        "world", "quality", "role", "element", "talent_code", "talent_name",
        "description", "apt_spirit", "apt_body", "apt_soul", "apt_speed",
        "highest_total", "miss_count", "bloodline_nodes",
    )
    return _apply_returned_quality(dict(zip(keys, row)))


async def _active_preset(uid, role_id, cursor):
    await cursor.execute(
        "SELECT active_preset FROM user_spirit_beast_setting "
        "WHERE uid=%s AND role_id=%s",
        (uid, role_id),
    )
    row = await cursor.fetchone()
    return int(row[0]) if row else 1


async def _is_dispatched(beast_id, cursor):
    await cursor.execute(
        "SELECT id,dispatch_type,started_at,ends_at,reward_json "
        "FROM spirit_beast_dispatch "
        "WHERE beast_id=%s AND state='ACTIVE' LIMIT 1",
        (beast_id,),
    )
    return await cursor.fetchone()


async def _formation_rows(uid, role_id, cursor, preset=None):
    preset = preset or await _active_preset(uid, role_id, cursor)
    await cursor.execute("""
        SELECT f.slot_type,b.id,b.nickname,b.level,b.stage,b.temperament,
               b.bond_exp,t.id,t.name,t.world,t.quality,t.role_code,t.element,
               t.talent_code,t.talent_name,t.description,
               a.spirit,a.body,a.soul,a.speed,
               COALESCE(bl.nodes,0)
        FROM user_spirit_beast_formation f
        JOIN user_spirit_beast_v2 b ON b.id=f.beast_id AND b.uid=f.uid
        JOIN spirit_beast_template t ON t.id=b.template_id
        JOIN user_spirit_beast_aptitude a ON a.beast_id=b.id
        LEFT JOIN user_spirit_beast_bloodline bl
          ON bl.uid=b.uid AND bl.template_id=b.template_id
        WHERE f.uid=%s AND f.role_id=%s AND f.preset_no=%s
        ORDER BY FIELD(f.slot_type,'主契','护契','辅契')
    """, (uid, role_id, preset))
    keys = (
        "slot", "id", "nickname", "level", "stage", "temperament", "bond_exp",
        "template_id", "name", "world", "quality", "role", "element",
        "talent_code", "talent_name", "description", "apt_spirit", "apt_body",
        "apt_soul", "apt_speed", "bloodline_nodes",
    )
    return [
        _apply_returned_quality(dict(zip(keys, row)))
        for row in await cursor.fetchall()
    ]


async def _create_beast(uid, template, cursor, nonce, initial=False):
    temperament = deterministic_rng("temperament", uid, nonce).choice(TEMPERAMENTS)
    await cursor.execute(
        "INSERT INTO user_spirit_beast_v2"
        "(uid,template_id,temperament,initial_contract) VALUES(%s,%s,%s,%s)",
        (uid, template[0], temperament, 1 if initial else 0),
    )
    beast_id = int(cursor.lastrowid)
    values = generate_aptitudes(uid, f"new:{beast_id}:{nonce}", template[3])
    await cursor.execute(
        "INSERT INTO user_spirit_beast_aptitude"
        "(beast_id,spirit,body,soul,speed,highest_total) "
        "VALUES(%s,%s,%s,%s,%s,%s)",
        (beast_id, *values, sum(values)),
    )
    await cursor.execute("""
        INSERT INTO user_spirit_beast_codex
            (uid,template_id,obtained_count,highest_aptitude,memorial)
        VALUES(%s,%s,1,%s,%s)
        ON DUPLICATE KEY UPDATE
            obtained_count=obtained_count+1,
            highest_aptitude=GREATEST(highest_aptitude,VALUES(highest_aptitude))
    """, (uid, template[0], sum(values), 1 if initial else 0))
    return beast_id, values, temperament


async def load_formation_snapshot(uid, role_id, cursor):
    """冻结一主两辅、技能、共鸣与角色协同；只返回白名单机器码。"""
    if role_id is None:
        role = await _current_role(uid, cursor)
        role_id = int(role[0]) if role else None
    if role_id is None:
        return None
    rows = await _formation_rows(uid, int(role_id), cursor)
    if not rows:
        return None
    resonance = formation_resonance(
        [row["world"] for row in rows], [row["element"] for row in rows]
    )
    role = await _owned_role(uid, int(role_id), cursor)
    role_name = role[1] if role else ""
    for profile in rows:
        profile["bond_level"] = bond_level(profile["bond_exp"])
        profile["effect"] = formation_combat_effect(profile)
        await cursor.execute("""
            SELECT s.id,s.name,s.category,s.effect_code,s.effect_value,
                   s.cooldown,s.trigger_limit
            FROM user_spirit_beast_skill_slot slot
            JOIN spirit_beast_skill s ON s.id=slot.skill_id
            WHERE slot.beast_id=%s ORDER BY slot.priority,slot.slot_no
        """, (profile["id"],))
        profile["skills"] = [
            {
                "id": item[0], "name": item[1], "category": item[2],
                "code": item[3], "value": item[4],
                "cooldown": item[5], "limit": item[6],
            }
            for item in await cursor.fetchall()
        ]
        if int(profile["bloodline_nodes"]) >= 3:
            bloodline_codes = {
                "STRIKER": "SKILL_ATTACK",
                "GUARDIAN": "SKILL_SHIELD",
                "HEALER": "SKILL_HEAL",
                "DISRUPTOR": "SKILL_SPEED",
                "BREAKER": "SKILL_BREAK",
            }
            profile["skills"].insert(0, {
                "id": -int(profile["template_id"]),
                "name": f"{profile['talent_name']}·血脉",
                "category": "血脉",
                "code": bloodline_codes[profile["role"]],
                "value": min(10, 3 + int(profile["bloodline_nodes"])),
                "cooldown": 99,
                "limit": 1,
            })
        profile["skill_count"] = sum(
            int(skill["id"]) > 0 for skill in profile["skills"]
        )
        profile["power"] = calculate_v2_power(profile)["power"]
    main = next((row for row in rows if row["slot"] == "主契"), rows[0])
    same_world = (
        main["world"] != "诸天通用"
        and WORLD_ROLE.get(main["world"]) == role_name
    )
    synergy_codes = {
        "萧炎": ("FIRE_STRIKER", {"burn_duration_bonus": 1}),
        "王林": ("REINCARNATION_DEBUFF", {"toughness_value": 3}),
        "石昊": ("WILDERNESS_WILL", {"will_value": 3}),
        "叶凡": ("FORMATION_INSIGHT", {"hint": 1}),
        "韩立": ("ARTIFACT_SOUL_BREAK", {"break_value": 5}),
        "孟川": ("FIRST_STRIKE_CHASE", {"damage_percent": 3}),
    }
    synergy_code, synergy_values = synergy_codes.get(role_name, ("", {}))
    synergy = {
        "active": same_world,
        "role": role_name,
        "world": main["world"],
        "code": synergy_code if same_world else "",
        "value": 5 if same_world else 0,
        **(synergy_values if same_world else {}),
    }
    return {
        "schema_version": 2,
        "rule_version": RULE_VERSION,
        "role_id": int(role_id),
        "main": main,
        "formation": rows,
        "resonance": resonance,
        "role_synergy": synergy,
        "instance_id": int(main["id"]),
        "name": _display_name(main),
        "role": main["role"],
        "element": main["element"],
        "combat_bonus": main["effect"],
        "synergy": synergy,
        "spirit_body": {
            "maximum": max(100, int(main["power"]) // 8),
            "current": max(100, int(main["power"]) // 8),
        },
        "bond_synergy": {
            "active": int(main["bond_level"]) >= 10,
            "code": "LIFE_AND_DEATH",
            "value": 3 if int(main["bond_level"]) >= 10 else 0,
        },
        "triggered": 0,
        "events": [],
    }


@reg_xz_func
async def spirit_beast_v2_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_user(uid, cursor)
            role = await _current_role(uid, cursor)
            wallet = await _wallet(uid, cursor)
            count = await _count_beasts(uid, cursor)
            garden = await _garden_level(uid, cursor)
            formation = await _formation_rows(uid, role[0], cursor) if role else []
            await conn.commit()
    output = "##### 🐾 诸天灵契\n\n"
    if formation:
        main = next(
            (row for row in formation if row["slot"] == "主契"), formation[0]
        )
        resonance = formation_resonance(
            [row["world"] for row in formation],
            [row["element"] for row in formation],
        )
        output += (
            f"主契：**#{main['id']} {_display_name(main)}**｜"
            f"{stage_name(main['stage'])} Lv.{main['level']}\n"
        )
        output += (
            f"灵阵：{resonance['world']} {resonance['count']}/3｜"
            f"{'共鸣已激活' if resonance['value'] else '等待搭配'}\n"
        )
    else:
        output += "主契：尚未配置｜完成初契或在阵容中上阵灵兽\n"
    output += (
        f"收藏：{count}/{collection_capacity(garden)}｜灵兽园 Lv.{garden}\n"
        f"兽踪：{wallet['beast_trace']}｜兽魂石：{wallet['soul_stone']}｜"
        f"御兽灵息：{wallet['spirit_essence']}\n\n"
    )
    if count == 0:
        output += "> 首次副本后可从四只通用灵兽中任选一只完成初契。\n\n"
        output += (
            "<qqbot-cmd-input text='灵兽初契 ' show='选择初契灵兽*' /> | "
        )
    output += (
        "<qqbot-cmd-input text='我的灵兽' show='我的灵兽' /> | "
        "<qqbot-cmd-input text='灵兽寻踪' show='今日寻踪' />\n\n"
        "<qqbot-cmd-input text='灵兽阵容' show='配置灵阵' /> | "
        "<qqbot-cmd-input text='万灵秘境' show='万灵秘境' />\n\n"
        "<qqbot-cmd-input text='灵兽派遣' show='灵兽派遣' /> | "
        "<qqbot-cmd-input text='灵兽周记' show='灵兽周记' /> | "
        "<qqbot-cmd-input text='灵兽图鉴' show='六界图鉴' />"
    )
    if garden >= 10:
        output += "\n\n<qqbot-cmd-input text='灵兽一键照料' show='一键照料主契' />"
    return _md(output)


@reg_xz_func
async def beast_starter_contract(uid, qz, value):
    name = str(value or "").strip()
    starter_names = ("赤焰灵狐", "玄甲龟", "青木鹿", "寒翎雀")
    if name not in starter_names:
        return _md(
            "请选择初契伙伴：\n\n"
            "<qqbot-cmd-input text='灵兽初契 赤焰灵狐' show='攻伐·赤焰灵狐' /> | "
            "<qqbot-cmd-input text='灵兽初契 玄甲龟' show='守御·玄甲龟' />\n\n"
            "<qqbot-cmd-input text='灵兽初契 青木鹿' show='生息·青木鹿' /> | "
            "<qqbot-cmd-input text='灵兽初契 寒翎雀' show='控场·寒翎雀' />"
        )
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role = await _current_role(uid, cursor, True)
            if not role:
                return _md("请先让一名角色出战。")
            await cursor.execute(
                "SELECT COUNT(*) FROM user_spirit_beast_v2 WHERE uid=%s FOR UPDATE",
                (uid,),
            )
            if int((await cursor.fetchone())[0]) > 0:
                return _md("你已完成初契，后续灵兽请通过世界寻踪与鉴灵获得。")
            await cursor.execute(
                "SELECT 1 FROM user_dungeon_drop WHERE uid=%s LIMIT 1", (uid,)
            )
            if not await cursor.fetchone():
                return _md(
                    "完成首次副本后，万灵古印才会回应你的初契。\n"
                    "<qqbot-cmd-input text='副本列表' show='前往副本' />"
                )
            beast_id, values, temperament = await _create_beast(
                uid, TEMPLATE_BY_NAME[name], cursor, "starter", True
            )
            await cursor.execute("""
                INSERT INTO user_spirit_beast_setting
                    (uid,role_id,starter_claimed,free_return_until)
                VALUES(%s,%s,1,%s)
                ON DUPLICATE KEY UPDATE
                    starter_claimed=1,
                    free_return_until=VALUES(free_return_until)
            """, (uid, role[0], date.today() + timedelta(days=7)))
            await cursor.execute("""
                INSERT INTO user_spirit_beast_formation
                    (uid,role_id,preset_no,slot_type,beast_id)
                VALUES(%s,%s,1,'主契',%s)
            """, (uid, role[0], beast_id))
            await _refresh_current_power(conn, uid)
            await conn.commit()
    return _md(
        f"##### ✨ 初契已成\n\n**#{beast_id} {name}** 愿与你同行。\n"
        f"> 性情：{temperament}｜四维总评：{sum(values)}\n\n"
        f"<qqbot-cmd-input text='灵兽详情 {beast_id}' show='查看伙伴' /> | "
        "<qqbot-cmd-input text='灵兽阵容' show='查看灵阵' />"
    )


@reg_xz_func
async def beast_list(uid, qz, value=""):
    try:
        page = max(1, int(str(value or "1").strip()))
    except ValueError:
        page = 1
    size = 6
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            count = await _count_beasts(uid, cursor)
            garden = await _garden_level(uid, cursor)
            total_pages = max(1, math.ceil(count / size))
            page = min(page, total_pages)
            await cursor.execute("""
                SELECT b.id,b.nickname,b.level,b.stage,b.bond_exp,t.name,t.quality,
                       t.role_code,MIN(f.slot_type),MIN(d.dispatch_type),MIN(d.ends_at)
                FROM user_spirit_beast_v2 b
                JOIN spirit_beast_template t ON t.id=b.template_id
                LEFT JOIN user_spirit_beast_formation f
                  ON f.uid=b.uid AND f.beast_id=b.id
                LEFT JOIN spirit_beast_dispatch d
                  ON d.beast_id=b.id AND d.state='ACTIVE'
                WHERE b.uid=%s
                GROUP BY b.id,b.nickname,b.level,b.stage,b.bond_exp,t.name,
                         t.quality,t.role_code
                ORDER BY (MIN(f.slot_type)='主契') DESC,b.id
                LIMIT %s OFFSET %s
            """, (uid, size, (page - 1) * size))
            rows = await cursor.fetchall()
    output = (
        f"##### 🐾 我的灵兽｜{page}/{total_pages}\n\n"
        f"收藏：{count}/{collection_capacity(garden)}\n\n"
    )
    for (
        beast_id, nickname, level, stage, bond, name, quality, role_code,
        slot, dispatch_type, ends_at,
    ) in rows:
        status = slot or (f"{dispatch_type}中" if dispatch_type else "休息")
        output += (
            f"**#{beast_id} {nickname or name}**｜{quality}｜"
            f"{stage_name(stage)}{level}\n"
            f"> {ROLE_LABELS.get(role_code, role_code)}·{status}｜"
            f"羁绊{bond_level(bond)}\n"
            f"<qqbot-cmd-input text='灵兽详情 {beast_id}' "
            f"show='查看#{beast_id}' />\n\n"
        )
    output += "<qqbot-cmd-input text='灵兽批量归真' show='批量归真普通灵兽' />"
    if not rows:
        output += "> 尚无灵兽，完成首次副本后进行初契。\n\n"
    output += (
        f"<qqbot-cmd-input text='我的灵兽 {max(1, page-1)}' show='上一页' /> | "
        f"<qqbot-cmd-input text='我的灵兽 {min(total_pages, page+1)}' show='下一页' /> | "
        "<qqbot-cmd-input text='灵兽' show='返回主页' />"
    )
    return _md(output)


@reg_xz_func
async def beast_detail(uid, qz, value):
    try:
        beast_id = int(str(value).strip())
    except ValueError:
        return _md("指令：灵兽详情 灵兽编号")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor)
            if not profile:
                return _md("未找到这只灵兽。")
            dispatched = await _is_dispatched(beast_id, cursor)
            await cursor.execute("""
                SELECT slot.slot_no,s.name,s.category
                FROM user_spirit_beast_skill_slot slot
                JOIN spirit_beast_skill s ON s.id=slot.skill_id
                WHERE slot.beast_id=%s ORDER BY slot.slot_no
            """, (beast_id,))
            skills = await cursor.fetchall()
    profile["skill_count"] = len(skills)
    power = calculate_v2_power(profile)
    output = (
        f"##### 🐾 #{beast_id} {_display_name(profile)}\n\n"
        f"{profile['quality']}｜{profile['world']}｜"
        f"{ROLE_LABELS.get(profile['role'], profile['role'])}｜{profile['element']}\n"
        f"境界：{stage_name(profile['stage'])} Lv.{profile['level']}｜"
        f"性情：{profile['temperament']}｜战力：{power['power']}\n"
        f"羁绊：Lv.{power['bond_level']}（{profile['bond_exp']}）｜"
        f"血脉：{profile['bloodline_nodes']}/6\n"
        f"四维：灵力{profile['apt_spirit']}｜体魄{profile['apt_body']}｜"
        f"神魂{profile['apt_soul']}｜迅捷{profile['apt_speed']}\n\n"
        f"**天赋·{profile['talent_name']}**\n> {profile['description']}\n"
    )
    if skills:
        output += "\n传承：" + "｜".join(
            f"槽{row[0]} {row[1]}" for row in skills
        ) + "\n"
    if dispatched:
        output += (
            f"\n> 派遣中：{dispatched[1]}，结束于 "
            f"{dispatched[3]:%m-%d %H:%M}\n"
        )
    if profile["initial_contract"]:
        output += "\n> 纪念标记：初代灵契\n"
    output += (
        f"\n<qqbot-cmd-input text='灵兽培养 {beast_id}' show='培养' /> | "
        f"<qqbot-cmd-input text='灵兽血脉 {beast_id}' show='血脉' /> | "
        f"<qqbot-cmd-input text='灵兽技能 {beast_id}' show='技能' />\n\n"
        f"<qqbot-cmd-input text='灵兽洗髓 {beast_id}' show='洗髓预览' /> | "
        f"<qqbot-cmd-input text='灵兽传记 {beast_id}' show='传记' /> | "
        f"<qqbot-cmd-input text='灵兽归真 {beast_id}' show='归真预览' />"
    )
    return _md(output)


@reg_xz_func
async def beast_codex(uid, qz, value=""):
    world = str(value or "").strip()
    if world and world not in WORLDS and world != "诸天通用":
        return _md("世界仅可选：" + "、".join(WORLDS))
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            params = [uid]
            where = "WHERE t.enabled=1"
            if world:
                where += " AND t.world=%s"
                params.append(world)
            await cursor.execute(f"""
                SELECT t.id,t.name,t.world,t.quality,t.role_code,t.talent_name,
                       COALESCE(c.obtained_count,0),
                       COALESCE(c.research_level,0)
                FROM spirit_beast_template t
                LEFT JOIN user_spirit_beast_codex c
                  ON c.template_id=t.id AND c.uid=%s
                {where}
                ORDER BY FIELD(
                    t.world,'诸天通用','斗气大陆','仙罡星域','大荒',
                    '北斗星域','人界灵界','沧元界'
                ),t.id
            """, tuple(params))
            rows = await cursor.fetchall()
    output = f"##### 📜 灵兽图鉴{'｜'+world if world else ''}\n\n"
    for _, name, item_world, quality, role_code, talent, owned, research in rows:
        state = f"已结契×{owned}｜研究{research}" if owned else "未相逢"
        output += (
            f"**{name}**｜{quality}｜{ROLE_LABELS.get(role_code, role_code)}\n"
            f"> {item_world}｜{talent}｜{state}\n"
        )
    output += "\n" + " | ".join(
        f"<qqbot-cmd-input text='灵兽图鉴 {item}' show='{item}' />"
        for item in WORLDS[:3]
    )
    output += "\n\n" + " | ".join(
        f"<qqbot-cmd-input text='灵兽图鉴 {item}' show='{item}' />"
        for item in WORLDS[3:]
    )
    return _md(output)


@reg_xz_func
async def beast_trace(uid, qz, value=""):
    world = str(value or "").strip()
    if not world:
        return _md(
            "##### 🧭 六界寻踪\n\n选择追踪世界，随后从稳定、稀有、未知"
            "三条线索中选择。\n\n"
            + " | ".join(
                f"<qqbot-cmd-input text='灵兽寻踪 {item}' show='{item}' />"
                for item in WORLDS
            )
        )
    if world not in WORLDS:
        return _md("未知世界，可选：" + "、".join(WORLDS))
    today = date.today()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            wallet = await _wallet(uid, cursor, True)
            await cursor.execute("""
                SELECT id,world,clue_type,state
                FROM spirit_beast_trace
                WHERE uid=%s AND trace_date=%s FOR UPDATE
            """, (uid, today))
            existing = await cursor.fetchone()
            if existing:
                if existing[2]:
                    return _md(
                        f"今日已选择{existing[2]}线索，状态：{existing[3]}。\n"
                        "<qqbot-cmd-input text='灵兽鉴定' show='前往鉴灵' />"
                    )
                world = existing[1]
            else:
                if wallet["beast_trace"] <= 0:
                    return _md(
                        "今日没有诸天兽踪。亲手完整通关一次副本可获得1枚。\n"
                        "<qqbot-cmd-input text='副本列表' show='前往副本' />"
                    )
                seed = sha256(f"trace:{uid}:{today}:{world}".encode()).hexdigest()
                await cursor.execute("""
                    INSERT INTO spirit_beast_trace
                        (uid,trace_date,world,seed)
                    VALUES(%s,%s,%s,%s)
                """, (uid, today, world, seed))
            await conn.commit()
    return _md(
        f"##### 🧭 {world}灵影\n\n"
        "**稳定线索**：灵/玄品，额外培养材料\n"
        "**稀有线索**：地品概率提高\n"
        "**未知线索**：世界可能改变，天品与奇遇概率提高\n\n"
        "<qqbot-cmd-input text='灵兽线索 稳定' show='稳定线索' /> | "
        "<qqbot-cmd-input text='灵兽线索 稀有' show='稀有线索' /> | "
        "<qqbot-cmd-input text='灵兽线索 未知' show='未知线索' />"
    )


@reg_xz_func
async def beast_trace_choose(uid, qz, value):
    clue = str(value or "").strip()
    if clue not in ("稳定", "稀有", "未知"):
        return _md("请选择：灵兽线索 稳定/稀有/未知")
    today = date.today()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_user(uid, cursor)
            await cursor.execute("""
                SELECT id,world,clue_type,state FROM spirit_beast_trace
                WHERE uid=%s AND trace_date=%s FOR UPDATE
            """, (uid, today))
            trace = await cursor.fetchone()
            if not trace:
                return _md("请先发送“灵兽寻踪 世界”发现灵影。")
            if trace[2]:
                return _md("今日线索已经锁定，不能重复选择。")
            changes = {
                "beast_trace": -1,
                "soul_stone": 1,
                "spirit_essence": 30 if clue == "稳定" else 0,
            }
            if not await _wallet_change(cursor, uid, changes):
                return _md("诸天兽踪不足。")
            event = "古印回应了你的选择，一枚兽魂石已凝成。"
            if clue == "未知":
                event = "裂隙另一端传来陌生回应，鉴灵世界可能发生变化。"
            await cursor.execute("""
                UPDATE spirit_beast_trace
                SET clue_type=%s,state='READY',event_text=%s WHERE id=%s
            """, (clue, event, trace[0]))
            await conn.commit()
    extra = "、御兽灵息×30" if clue == "稳定" else ""
    return _md(
        f"##### ✅ 线索已锁定\n\n{event}\n> 获得兽魂石×1{extra}\n\n"
        "<qqbot-cmd-input text='灵兽鉴定' show='鉴定兽魂' />"
    )


@reg_xz_func
async def beast_identify(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            wallet = await _wallet(uid, cursor, True)
            if wallet["soul_stone"] <= 0:
                return _md(
                    "兽魂石不足。通过寻踪、万灵秘境、世界Boss和周记获得。"
                )
            await cursor.execute("""
                SELECT world,clue_type,state,seed FROM spirit_beast_trace
                WHERE uid=%s AND state='READY'
                ORDER BY id DESC LIMIT 1 FOR UPDATE
            """, (uid,))
            trace = await cursor.fetchone()
            if not trace:
                return _md("当前没有可鉴定的寻踪兽魂。")
            await cursor.execute("""
                SELECT ten_count,sixty_count,total_identify
                FROM user_spirit_beast_pity WHERE uid=%s FOR UPDATE
            """, (uid,))
            ten_count, sixty_count, total = (
                int(value) for value in await cursor.fetchone()
            )
            rng = deterministic_rng("identify", uid, total + 1, trace[3])
            quality = roll_quality(
                trace[1], ten_count, sixty_count, rng.randrange(10000)
            )
            world = rng.choice(WORLDS) if trace[1] == "未知" else trace[0]
            await cursor.execute("""
                SELECT template_id FROM user_spirit_beast_codex
                WHERE uid=%s AND obtained_count>0
            """, (uid,))
            owned_ids = [int(row[0]) for row in await cursor.fetchall()]
            template = choose_template(
                world, quality, uid, total + 1, owned_ids
            )
            await _wallet_change(cursor, uid, {"soul_stone": -1})
            new_ten = (
                0 if QUALITY_RANK[quality] >= QUALITY_RANK["地品"]
                else ten_count + 1
            )
            new_sixty = 0 if quality == "天品" else sixty_count + 1
            await cursor.execute("""
                UPDATE user_spirit_beast_pity
                SET ten_count=%s,sixty_count=%s,total_identify=total_identify+1
                WHERE uid=%s
            """, (new_ten, new_sixty, uid))
            await cursor.execute("""
                UPDATE spirit_beast_trace SET state='IDENTIFIED'
                WHERE uid=%s AND state='READY'
            """, (uid,))
            if template[0] in owned_ids:
                token = _token(uid, "duplicate", template[0], total)
                payload = json.dumps(
                    {"name": template[1], "quality": quality, "world": template[2]},
                    ensure_ascii=False,
                )
                await cursor.execute("""
                    INSERT INTO spirit_beast_pending_choice
                        (uid,choice_type,template_id,payload_json,token,expires_at)
                    VALUES(%s,'DUPLICATE',%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        template_id=VALUES(template_id),
                        payload_json=VALUES(payload_json),
                        token=VALUES(token),expires_at=VALUES(expires_at)
                """, (
                    uid, template[0], payload, token,
                    datetime.now() + timedelta(hours=24),
                ))
                await conn.commit()
                return _md(
                    f"##### ✨ 鉴灵｜重复灵影\n\n发现 **{quality}·{template[1]}**！\n"
                    "> 不会自动炼化，请在24小时内选择去向。\n\n"
                    "<qqbot-cmd-input text='灵兽重复 留存' show='结契留存' /> | "
                    "<qqbot-cmd-input text='灵兽重复 精魄' show='化为精魄' /> | "
                    "<qqbot-cmd-input text='灵兽重复 古印' show='录入古印' />"
                )
            garden = await _garden_level(uid, cursor)
            if await _count_beasts(uid, cursor) >= collection_capacity(garden):
                await _wallet_change(
                    cursor, uid, {"bloodline_essence": 5, "soul_fragment": 10}
                )
                await conn.commit()
                return _md(
                    f"灵兽园已满，新的 **{template[1]}** 灵影已安全化为"
                    "血脉精华×5、兽魂碎片×10。"
                )
            beast_id, values, temperament = await _create_beast(
                uid, template, cursor, total + 1
            )
            await conn.commit()
    return _md(
        f"##### ✨ 鉴灵成功\n\n与 **{quality}·{template[1]}** 缔结灵契！\n"
        f"> #{beast_id}｜{template[2]}｜{ROLE_LABELS[template[4]]}\n"
        f"> 四维总评：{sum(values)}｜性情：{temperament}\n\n"
        f"<qqbot-cmd-input text='灵兽详情 {beast_id}' show='查看灵兽' /> | "
        f"<qqbot-cmd-input text='灵兽上阵 {beast_id} 主契' show='设为主契' />"
    )


@reg_xz_func
async def beast_duplicate_choice(uid, qz, value):
    choice = str(value or "").strip()
    if choice not in ("留存", "精魄", "古印"):
        return _md("请选择：灵兽重复 留存/精魄/古印")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT template_id,payload_json,token,expires_at
                FROM spirit_beast_pending_choice
                WHERE uid=%s AND choice_type='DUPLICATE' FOR UPDATE
            """, (uid,))
            pending = await cursor.fetchone()
            if not pending or pending[3] < datetime.now():
                return _md("重复灵影选择已失效，请重新鉴灵。")
            template = TEMPLATE_BY_ID[int(pending[0])]
            if choice == "留存":
                garden = await _garden_level(uid, cursor)
                if await _count_beasts(uid, cursor) >= collection_capacity(garden):
                    return _md(
                        "灵兽园已满。请选择精魄或古印，或先升级灵兽园。"
                    )
                beast_id, _, _ = await _create_beast(
                    uid, template, cursor, pending[2]
                )
                result = f"已保留为独立灵兽 #{beast_id}。"
            elif choice == "精魄":
                amount = 8 + QUALITY_RANK[template[3]] * 4
                await cursor.execute("""
                    INSERT INTO user_spirit_beast_bloodline
                        (uid,template_id,essence)
                    VALUES(%s,%s,%s)
                    ON DUPLICATE KEY UPDATE essence=essence+VALUES(essence)
                """, (uid, template[0], amount))
                await _wallet_change(
                    cursor, uid,
                    {"bloodline_essence": QUALITY_RANK[template[3]]},
                )
                result = (
                    f"化为{template[1]}精魄×{amount}，并获得"
                    f"血脉精华×{QUALITY_RANK[template[3]]}。"
                )
            else:
                await cursor.execute("""
                    UPDATE user_spirit_beast_codex
                    SET research_level=LEAST(10,research_level+1)
                    WHERE uid=%s AND template_id=%s
                """, (uid, template[0]))
                await _wallet_change(cursor, uid, {"story_token": 2})
                result = (
                    f"已录入万灵古印，{template[1]}研究等级+1、故事信物+2。"
                )
            await cursor.execute("""
                DELETE FROM spirit_beast_pending_choice
                WHERE uid=%s AND choice_type='DUPLICATE'
            """, (uid,))
            await cursor.execute("""
                INSERT IGNORE INTO spirit_beast_reward_ledger
                    (uid,business_key,action_type,payload_json)
                VALUES(%s,%s,'DUPLICATE',%s)
            """, (
                uid, f"duplicate:{pending[2]}",
                json.dumps({"choice": choice}, ensure_ascii=False),
            ))
            await conn.commit()
    return _md(
        f"##### ✅ 重复灵影已处理\n\n{result}\n"
        "<qqbot-cmd-input text='灵兽' show='返回灵兽主页' />"
    )


@reg_xz_func
async def beast_cultivate(uid, qz, value):
    try:
        beast_id = int(str(value).strip())
    except ValueError:
        return _md("指令：灵兽培养 灵兽编号")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor)
            if not profile:
                return _md("未找到这只灵兽。")
            wallet = await _wallet(uid, cursor)
    cap = min(70, (int(profile["stage"]) + 1) * 10)
    return _md(
        f"##### 🌱 {_display_name(profile)}培养\n\n"
        f"境界：{stage_name(profile['stage'])}｜等级：{profile['level']}/{cap}\n"
        f"经验：{profile['level_exp']}｜灵息：{wallet['spirit_essence']}｜"
        f"兽材：{wallet['beast_material']}\n\n"
        f"<qqbot-cmd-input text='灵兽喂养 {beast_id} 1' show='喂养1' /> | "
        f"<qqbot-cmd-input text='灵兽喂养 {beast_id} 10' show='喂养10' /> | "
        f"<qqbot-cmd-input text='灵兽喂养 {beast_id} 最大' show='喂养最大' />\n\n"
        f"<qqbot-cmd-input text='灵兽突破 {beast_id}' show='境界突破' /> | "
        f"<qqbot-cmd-input text='灵兽照料 {beast_id} 抚摸' show='今日照料' /> | "
        f"<qqbot-cmd-input text='灵兽详情 {beast_id}' show='返回详情' />"
    )


@reg_xz_func
async def beast_feed(uid, qz, value):
    parts = _parts(value)
    if len(parts) != 2 or not parts[0].isdigit():
        return _md("指令：灵兽喂养 灵兽编号 数量（支持1、5、10、最大）")
    beast_id = int(parts[0])
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile:
                return _md("未找到这只灵兽。")
            if await _is_dispatched(beast_id, cursor):
                return _md("派遣中的灵兽不能喂养。")
            role = await _current_role(uid, cursor)
            if not role:
                return _md("请先让一名角色出战，灵兽等级不能超过角色等级。")
            wallet = await _wallet(uid, cursor, True)
            amount = (
                wallet["spirit_essence"]
                if parts[1] == "最大"
                else (int(parts[1]) if parts[1].isdigit() else 0)
            )
            if amount <= 0:
                return _md("喂养数量错误。")
            plan = feed_plan(
                profile["level"], profile["level_exp"], amount,
                int(role[2]), int(profile["stage"]),
            )
            if plan["used"] <= 0:
                return _md(
                    "已达到角色等级或境界上限；整十级后可进行境界突破。"
                )
            if not await _wallet_change(
                cursor, uid, {"spirit_essence": -plan["used"]}
            ):
                return _md("御兽灵息不足。")
            await cursor.execute("""
                UPDATE user_spirit_beast_v2 SET level=%s,level_exp=%s
                WHERE id=%s AND uid=%s
            """, (plan["level"], plan["exp"], beast_id, uid))
            await _refresh_current_power(conn, uid)
            await conn.commit()
    return _md(
        f"##### 🌱 喂养完成\n\n消耗御兽灵息×{plan['used']}\n"
        f"{_display_name(profile)}：Lv.{profile['level']} → **Lv.{plan['level']}**\n\n"
        f"<qqbot-cmd-input text='灵兽培养 {beast_id}' show='继续培养' />"
    )


@reg_xz_func
async def beast_breakthrough(uid, qz, value):
    try:
        beast_id = int(str(value).strip())
    except ValueError:
        return _md("指令：灵兽突破 灵兽编号")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile:
                return _md("未找到这只灵兽。")
            stage = int(profile["stage"])
            if stage >= 6:
                return _md("已达太古境，不再无限升阶。")
            if int(profile["level"]) < (stage + 1) * 10:
                return _md(f"需要先达到 Lv.{(stage + 1) * 10}。")
            cost_lingshi = STAGE_COSTS[stage]
            material = STAGE_MATERIALS[stage]
            if not await _wallet_change(
                cursor, uid, {"beast_material": -material}
            ):
                return _md(f"基础兽材不足，需要{material}。")
            await cursor.execute("""
                UPDATE user_zt SET lingshi=lingshi-%s
                WHERE id=%s AND lingshi>=%s
            """, (cost_lingshi, uid, cost_lingshi))
            if cursor.rowcount <= 0:
                await conn.rollback()
                return _md(f"灵石不足，需要{cost_lingshi}。")
            await cursor.execute("""
                UPDATE user_spirit_beast_v2 SET stage=stage+1
                WHERE id=%s AND uid=%s
            """, (beast_id, uid))
            await _refresh_current_power(conn, uid)
            await conn.commit()
    unlocks = (
        "传承技能槽一", "血脉系统与第一形态", "辅契效果与技能槽二",
        "返祖品质资格", "世界共鸣强化与第二形态", "终局外观与羁绊结局",
    )
    return _md(
        f"##### ✨ 境界突破\n\n{_display_name(profile)}晋入 "
        f"**{stage_name(stage + 1)}境**！\n> 解锁：{unlocks[stage]}\n"
        f"> 消耗：兽材{material}、灵石{cost_lingshi}\n\n"
        f"<qqbot-cmd-input text='灵兽培养 {beast_id}' show='继续培养' />"
    )


@reg_xz_func
async def beast_wash(uid, qz, value):
    parts = _parts(value)
    if not parts or not parts[0].isdigit():
        return _md("指令：灵兽洗髓 灵兽编号 [锁灵力/体魄/神魂/迅捷]")
    beast_id = int(parts[0])
    locked = parts[1].replace("锁", "") if len(parts) > 1 else ""
    lock_index = {"灵力": 0, "体魄": 1, "神魂": 2, "迅捷": 3}.get(locked)
    if locked and lock_index is None:
        return _md("可锁定：灵力、体魄、神魂、迅捷。")
    dew_cost = 1 + (1 if lock_index is not None else 0)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile:
                return _md("未找到这只灵兽。")
            if not await _wallet_change(cursor, uid, {"wash_dew": -dew_cost}):
                return _md(
                    f"洗髓露不足，本次需要{dew_cost}。通过周记、秘境和宗门获得。"
                )
            await cursor.execute("""
                UPDATE user_zt SET lingshi=lingshi-500
                WHERE id=%s AND lingshi>=500
            """, (uid,))
            if cursor.rowcount <= 0:
                await conn.rollback()
                return _md("灵石不足，洗髓需要500灵石。")
            old = [
                int(profile[key])
                for key in ("apt_spirit", "apt_body", "apt_soul", "apt_speed")
            ]
            minimum = sum(old) + 2 if int(profile["miss_count"]) >= 9 else 0
            nonce = f"wash:{beast_id}:{profile['miss_count']}:{datetime.now().isoformat()}"
            new = list(
                generate_aptitudes(uid, nonce, profile["quality"], minimum)
            )
            if lock_index is not None:
                new[lock_index] = old[lock_index]
            token = _token(uid, "wash", beast_id, *new)
            await cursor.execute("""
                UPDATE user_spirit_beast_aptitude
                SET pending_spirit=%s,pending_body=%s,pending_soul=%s,
                    pending_speed=%s,pending_token=%s,pending_at=NOW()
                WHERE beast_id=%s
            """, (*new, token, beast_id))
            await conn.commit()
    labels = ("灵力", "体魄", "神魂", "迅捷")
    compare = "｜".join(
        f"{labels[index]} {old[index]}→{new[index]}" for index in range(4)
    )
    return _md(
        f"##### 🧬 洗髓预览\n\n{compare}\n总评：{sum(old)} → **{sum(new)}**\n"
        f"> 已消耗洗髓露{dew_cost}、灵石500；确认只决定是否替换。\n\n"
        f"<qqbot-cmd-input text='灵兽洗髓确认 {token}' show='采用新资质' /> | "
        f"<qqbot-cmd-input text='灵兽洗髓取消 {token}' show='保留旧资质' />"
    )


async def _wash_finish(uid, token, accept):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT a.beast_id,a.spirit,a.body,a.soul,a.speed,
                       a.highest_total,a.miss_count,a.pending_spirit,
                       a.pending_body,a.pending_soul,a.pending_speed
                FROM user_spirit_beast_aptitude a
                JOIN user_spirit_beast_v2 b ON b.id=a.beast_id
                WHERE b.uid=%s AND a.pending_token=%s FOR UPDATE
            """, (uid, token))
            row = await cursor.fetchone()
            if not row or row[7] is None:
                return _md("洗髓令牌无效或已使用。")
            old_total = sum(int(value) for value in row[1:5])
            new_values = tuple(int(value) for value in row[7:11])
            new_total = sum(new_values)
            if accept:
                miss = 0 if new_total > old_total else min(10, int(row[6]) + 1)
                await cursor.execute("""
                    UPDATE user_spirit_beast_aptitude
                    SET spirit=%s,body=%s,soul=%s,speed=%s,
                        highest_total=GREATEST(highest_total,%s),miss_count=%s,
                        pending_spirit=NULL,pending_body=NULL,pending_soul=NULL,
                        pending_speed=NULL,pending_token=NULL,pending_at=NULL
                    WHERE beast_id=%s
                """, (*new_values, new_total, miss, row[0]))
                result = f"已采用新资质，总评 {old_total}→{new_total}。"
            else:
                await cursor.execute("""
                    UPDATE user_spirit_beast_aptitude
                    SET miss_count=LEAST(10,miss_count+1),
                        pending_spirit=NULL,pending_body=NULL,pending_soul=NULL,
                        pending_speed=NULL,pending_token=NULL,pending_at=NULL
                    WHERE beast_id=%s
                """, (row[0],))
                result = "已保留旧资质；未提升计数已经记录。"
            if accept:
                await _refresh_current_power(conn, uid)
            await conn.commit()
    return _md(
        f"##### ✅ 洗髓结算\n\n{result}\n"
        f"<qqbot-cmd-input text='灵兽详情 {row[0]}' show='查看灵兽' />"
    )


@reg_xz_func
async def beast_wash_confirm(uid, qz, token):
    return await _wash_finish(uid, str(token).strip(), True)


@reg_xz_func
async def beast_wash_cancel(uid, qz, token):
    return await _wash_finish(uid, str(token).strip(), False)


@reg_xz_func
async def beast_bloodline(uid, qz, value):
    try:
        beast_id = int(str(value).strip())
    except ValueError:
        return _md("指令：灵兽血脉 灵兽编号")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor)
            if not profile:
                return _md("未找到这只灵兽。")
            await cursor.execute("""
                SELECT nodes,essence FROM user_spirit_beast_bloodline
                WHERE uid=%s AND template_id=%s
            """, (uid, profile["template_id"]))
            row = await cursor.fetchone() or (0, 0)
            wallet = await _wallet(uid, cursor)
    node_names = (
        "血脉初鸣", "灵纹显化", "古血苏醒",
        "真形蜕变", "万灵共鸣", "返祖归真",
    )
    output = (
        f"##### 🩸 {_display_name(profile)}血脉\n\n"
        f"进度：{row[0]}/6｜灵种精魄：{row[1]}｜"
        f"通用精华：{wallet['bloodline_essence']}\n"
    )
    for index, name in enumerate(node_names, 1):
        output += f"> {'✅' if index <= row[0] else '◇'} {index}.{name}\n"
    if int(profile["stage"]) < 2:
        output += "\n> 凝丹境解锁血脉系统。"
    else:
        output += (
            f"\n<qqbot-cmd-input text='灵兽血脉激活 {beast_id}' "
            "show='激活下一节点' />"
        )
    return _md(output)


@reg_xz_func
async def beast_bloodline_activate(uid, qz, value):
    try:
        beast_id = int(str(value).strip())
    except ValueError:
        return _md("指令：灵兽血脉激活 灵兽编号")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile or int(profile["stage"]) < 2:
                return _md("未找到灵兽，或尚未达到凝丹境。")
            await cursor.execute("""
                INSERT IGNORE INTO user_spirit_beast_bloodline(uid,template_id)
                VALUES(%s,%s)
            """, (uid, profile["template_id"]))
            await cursor.execute("""
                SELECT nodes,essence FROM user_spirit_beast_bloodline
                WHERE uid=%s AND template_id=%s FOR UPDATE
            """, (uid, profile["template_id"]))
            nodes, essence = (int(value) for value in await cursor.fetchone())
            if nodes >= 6:
                return _md("六个血脉节点已全部激活。")
            specific_cost, common_cost = 4 + nodes * 2, 2 + nodes
            if essence < specific_cost:
                return _md(
                    f"灵种精魄不足，需要{specific_cost}；重复灵兽可转化精魄。"
                )
            if not await _wallet_change(
                cursor, uid, {"bloodline_essence": -common_cost}
            ):
                return _md(f"血脉精华不足，需要{common_cost}。")
            await cursor.execute("""
                UPDATE user_spirit_beast_bloodline
                SET nodes=nodes+1,essence=essence-%s
                WHERE uid=%s AND template_id=%s
            """, (specific_cost, uid, profile["template_id"]))
            await _refresh_current_power(conn, uid)
            await conn.commit()
    return _md(
        f"##### ✨ 血脉觉醒\n\n{_display_name(profile)}已激活第{nodes + 1}节点。\n"
        f"> 消耗灵种精魄{specific_cost}、血脉精华{common_cost}\n"
        "> 同名灵兽共享此血脉进度。\n\n"
        f"<qqbot-cmd-input text='灵兽血脉 {beast_id}' show='查看血脉' />"
    )


@reg_xz_func
async def beast_skills(uid, qz, value):
    try:
        beast_id = int(str(value).strip())
    except ValueError:
        return _md("指令：灵兽技能 灵兽编号")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor)
            if not profile:
                return _md("未找到这只灵兽。")
            await cursor.execute("""
                SELECT s.id,s.name,s.category,COALESCE(slot.slot_no,0)
                FROM user_spirit_beast_skill_book book
                JOIN spirit_beast_skill s ON s.id=book.skill_id
                LEFT JOIN user_spirit_beast_skill_slot slot
                  ON slot.beast_id=%s AND slot.skill_id=s.id
                WHERE book.uid=%s ORDER BY s.id
            """, (beast_id, uid))
            rows = await cursor.fetchall()
            wallet = await _wallet(uid, cursor)
    max_slots = (
        0 if int(profile["stage"]) < 1
        else (1 if int(profile["stage"]) < 3 else 2)
    )
    output = (
        f"##### 📖 {_display_name(profile)}技能\n\n"
        f"天赋：**{profile['talent_name']}**｜"
        f"血脉技能：{'已解锁' if profile['bloodline_nodes'] >= 3 else '节点3解锁'}\n"
        f"传承槽：{max_slots}/2｜残页：{wallet['skill_page']}\n\n"
    )
    for skill_id, name, category, slot in rows:
        output += (
            f"> #{skill_id} {name}｜{category}｜"
            f"{'槽' + str(slot) if slot else '书库'}\n"
        )
    output += (
        "\n<qqbot-cmd-input text='灵兽技能参悟 ' show='参悟技能编号*' />"
    )
    if max_slots:
        output += (
            f" | <qqbot-cmd-input text='灵兽技能装配 {beast_id} ' "
            "show='装配 技能编号 槽位*' />"
        )
        output += (
            f" | <qqbot-cmd-input text='灵兽技能卸下 {beast_id} ' "
            "show='卸下 槽位*' />"
        )
    return _md(output)


@reg_xz_func
async def beast_skill_learn(uid, qz, value):
    try:
        skill_id = int(str(value).strip())
    except ValueError:
        skill_id = 0
    skill = SKILL_BY_ID.get(skill_id)
    if not skill:
        lines = [
            f"> #{row[0]} {row[1]}｜{row[2]}｜残页{row[7]}"
            for row in SKILLS
        ]
        return _md(
            "##### 📚 灵契书库\n\n" + "\n".join(lines)
            + "\n\n发送：灵兽技能参悟 技能编号"
        )
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT 1 FROM user_spirit_beast_skill_book
                WHERE uid=%s AND skill_id=%s
            """, (uid, skill_id))
            if await cursor.fetchone():
                return _md("该技能已在书库中，可无损装配给灵兽。")
            if not await _wallet_change(
                cursor, uid, {"skill_page": -skill[7]}
            ):
                return _md(f"灵契残页不足，需要{skill[7]}。")
            await cursor.execute("""
                UPDATE user_zt SET lingshi=lingshi-800
                WHERE id=%s AND lingshi>=800
            """, (uid,))
            if cursor.rowcount <= 0:
                await conn.rollback()
                return _md("灵石不足，技能参悟需要800灵石。")
            await cursor.execute("""
                INSERT INTO user_spirit_beast_skill_book(uid,skill_id)
                VALUES(%s,%s)
            """, (uid, skill_id))
            await conn.commit()
    return _md(
        f"##### ✨ 参悟成功\n\n**{skill[1]}** 已永久进入灵契书库。\n"
        "> 技能可在灵兽之间无损装卸。"
    )


@reg_xz_func
async def beast_skill_equip(uid, qz, value):
    parts = _parts(value)
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return _md("指令：灵兽技能装配 灵兽编号 技能编号 槽位（1/2）")
    beast_id, skill_id, slot = map(int, parts)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile:
                return _md("未找到这只灵兽。")
            max_slots = (
                0 if int(profile["stage"]) < 1
                else (1 if int(profile["stage"]) < 3 else 2)
            )
            if slot < 1 or slot > max_slots:
                return _md(f"当前境界仅开放{max_slots}个传承技能槽。")
            await cursor.execute("""
                SELECT s.name
                FROM user_spirit_beast_skill_book b
                JOIN spirit_beast_skill s ON s.id=b.skill_id
                WHERE b.uid=%s AND b.skill_id=%s
            """, (uid, skill_id))
            row = await cursor.fetchone()
            if not row:
                return _md("该技能尚未进入你的灵契书库。")
            await cursor.execute("""
                DELETE FROM user_spirit_beast_skill_slot
                WHERE beast_id=%s AND (slot_no=%s OR skill_id=%s)
            """, (beast_id, slot, skill_id))
            await cursor.execute("""
                INSERT INTO user_spirit_beast_skill_slot
                    (beast_id,slot_no,skill_id,priority)
                VALUES(%s,%s,%s,%s)
            """, (beast_id, slot, skill_id, slot))
            await _refresh_current_power(conn, uid)
            await conn.commit()
    return _md(
        f"已将 **{row[0]}** 装配到 {_display_name(profile)} 的传承槽{slot}。"
    )


@reg_xz_func
async def beast_skill_unequip(uid, qz, value):
    parts = _parts(value)
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in ("1", "2"):
        return _md("指令：灵兽技能卸下 灵兽编号 槽位（1/2）")
    beast_id, slot = int(parts[0]), int(parts[1])
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile:
                return _md("未找到这只灵兽。")
            await cursor.execute("""
                SELECT s.name FROM user_spirit_beast_skill_slot slot
                JOIN spirit_beast_skill s ON s.id=slot.skill_id
                WHERE slot.beast_id=%s AND slot.slot_no=%s
            """, (beast_id, slot))
            row = await cursor.fetchone()
            if not row:
                return _md(f"{_display_name(profile)}的传承槽{slot}当前为空。")
            await cursor.execute("""
                DELETE FROM user_spirit_beast_skill_slot
                WHERE beast_id=%s AND slot_no=%s
            """, (beast_id, slot))
            await _refresh_current_power(conn, uid)
            await conn.commit()
    return _md(
        f"已无损卸下 **{row[0]}**；技能仍永久保存在灵契书库。\n"
        f"<qqbot-cmd-input text='灵兽技能 {beast_id}' show='返回技能页' />"
    )


@reg_xz_func
async def beast_care(uid, qz, value):
    parts = _parts(value)
    if not parts or not parts[0].isdigit():
        return _md("指令：灵兽照料 灵兽编号 抚摸/静观/讲道/竞速")
    beast_id = int(parts[0])
    interaction = parts[1] if len(parts) > 1 else "抚摸"
    mapping = {
        "抚摸": "沉稳", "静观": "灵慧", "讲道": "勇猛", "竞速": "机敏",
    }
    if interaction not in mapping:
        return _md("互动可选：抚摸、静观、讲道、竞速。")
    today, yesterday = date.today(), date.today() - timedelta(days=1)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile:
                return _md("未找到这只灵兽。")
            await cursor.execute("""
                SELECT cared FROM spirit_beast_daily_activity
                WHERE uid=%s AND activity_date=%s FOR UPDATE
            """, (uid, today))
            row = await cursor.fetchone()
            if row and row[0]:
                return _md("今日已完成首次照料，明日再来。")
            await cursor.execute("""
                SELECT interaction_type,interaction_streak
                FROM spirit_beast_daily_activity
                WHERE uid=%s AND activity_date=%s
            """, (uid, yesterday))
            previous = await cursor.fetchone()
            streak = (
                int(previous[1]) + 1
                if previous and previous[0] == interaction else 1
            )
            await cursor.execute("""
                INSERT INTO spirit_beast_daily_activity
                    (uid,activity_date,cared,interaction_type,interaction_streak)
                VALUES(%s,%s,1,%s,%s)
                ON DUPLICATE KEY UPDATE
                    cared=1,interaction_type=VALUES(interaction_type),
                    interaction_streak=VALUES(interaction_streak)
            """, (uid, today, interaction, streak))
            await cursor.execute("""
                UPDATE user_spirit_beast_v2
                SET bond_exp=bond_exp+20,
                    temperament=IF(%s>=3,%s,temperament)
                WHERE id=%s AND uid=%s
            """, (streak, mapping[interaction], beast_id, uid))
            await _wallet_change(cursor, uid, {"spirit_essence": 20})
            await cursor.execute("""
                INSERT INTO spirit_beast_weekly_journal
                    (uid,week_key,care_count)
                VALUES(%s,%s,1)
                ON DUPLICATE KEY UPDATE care_count=care_count+1
            """, (uid, week_key()))
            await _refresh_current_power(conn, uid)
            await conn.commit()
    changed = (
        f"连续{streak}天同类互动，性情已转为{mapping[interaction]}。"
        if streak >= 3
        else f"连续{streak}/3天可定向改变为{mapping[interaction]}。"
    )
    return _md(
        f"##### 💞 今日照料\n\n{_display_name(profile)}回应了你的{interaction}。\n"
        f"> 羁绊经验+20｜御兽灵息+20\n> {changed}"
    )


@reg_xz_func
async def beast_one_click_care(uid, qz, value=""):
    interaction = str(value or "").strip() or "抚摸"
    if interaction not in ("抚摸", "静观", "讲道", "竞速"):
        return _md("一键照料互动可选：抚摸、静观、讲道、竞速。")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            if await _garden_level(uid, cursor) < 10:
                return _md("灵兽园达到 Lv.10 后解锁一键照料。")
            role = await _current_role(uid, cursor)
            if not role:
                return _md("请先让一名角色出战。")
            rows = await _formation_rows(uid, role[0], cursor)
            main = next((row for row in rows if row["slot"] == "主契"), None)
            if not main:
                return _md("当前角色尚未设置主契，请先配置灵兽阵容。")
    return await beast_care.__wrapped__(uid, qz, f"{main['id']} {interaction}")


@reg_xz_func
async def beast_formation(uid, qz, value=""):
    try:
        role_id = int(str(value).strip()) if str(value or "").strip() else None
    except ValueError:
        return _md("指令：灵兽阵容 [角色编号]")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role = (
                await _owned_role(uid, role_id, cursor)
                if role_id else await _current_role(uid, cursor)
            )
            if not role:
                return _md("未找到目标角色，请先让角色出战或提供自有角色编号。")
            preset = await _active_preset(uid, role[0], cursor)
            rows = await _formation_rows(uid, role[0], cursor, preset)
            garden = await _garden_level(uid, cursor)
    slots = unlocked_slots(garden)
    resonance = formation_resonance(
        [row["world"] for row in rows], [row["element"] for row in rows]
    )
    output = f"##### 🔯 {role[1]}灵阵｜预设{preset}\n\n"
    for slot in SLOTS:
        row = next((item for item in rows if item["slot"] == slot), None)
        if slot not in slots:
            needed = 4 if slot == "护契" else 7
            output += f"**{slot}**：灵兽园 Lv.{needed} 解锁\n"
        elif row:
            output += (
                f"**{slot}**：#{row['id']} {_display_name(row)}｜"
                f"{row['quality']}·{ROLE_LABELS[row['role']]}\n"
            )
        else:
            output += f"**{slot}**：空\n"
    output += (
        f"\n共鸣：**{resonance['world']}**｜效果强度{resonance['value']}%\n\n"
        "<qqbot-cmd-input text='灵兽上阵 ' show='上阵 编号 位置*' /> | "
        "<qqbot-cmd-input text='灵兽预设 1' show='预设1' />"
    )
    if garden >= 10:
        output += (
            " | <qqbot-cmd-input text='灵兽预设 2' show='预设2' /> | "
            "<qqbot-cmd-input text='灵兽预设 3' show='预设3' />"
        )
    return _md(output)


@reg_xz_func
async def beast_formation_set(uid, qz, value):
    parts = _parts(value)
    if (
        len(parts) not in (2, 3)
        or not parts[0].isdigit()
        or parts[1] not in SLOTS
    ):
        return _md("指令：灵兽上阵 灵兽编号 主契/护契/辅契 [角色编号]")
    beast_id, slot = int(parts[0]), parts[1]
    target_role = (
        int(parts[2]) if len(parts) == 3 and parts[2].isdigit() else None
    )
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile:
                return _md("未找到这只灵兽。")
            if await _is_dispatched(beast_id, cursor):
                return _md("派遣中的灵兽不能上阵。")
            role = (
                await _owned_role(uid, target_role, cursor, True)
                if target_role else await _current_role(uid, cursor, True)
            )
            if not role:
                return _md("未找到目标角色。")
            garden = await _garden_level(uid, cursor)
            if slot not in unlocked_slots(garden):
                return _md(f"灵兽园等级不足，{slot}尚未解锁。")
            preset = await _active_preset(uid, role[0], cursor)
            await cursor.execute("""
                INSERT IGNORE INTO user_spirit_beast_setting(uid,role_id)
                VALUES(%s,%s)
            """, (uid, role[0]))
            await cursor.execute("""
                DELETE FROM user_spirit_beast_formation
                WHERE uid=%s AND role_id=%s AND preset_no=%s
                  AND (slot_type=%s OR beast_id=%s)
            """, (uid, role[0], preset, slot, beast_id))
            await cursor.execute("""
                INSERT INTO user_spirit_beast_formation
                    (uid,role_id,preset_no,slot_type,beast_id)
                VALUES(%s,%s,%s,%s,%s)
            """, (uid, role[0], preset, slot, beast_id))
            if slot == "主契" and int(role[3]):
                from Tool.tool_power import update_role_power
                await update_role_power(conn, uid)
            await conn.commit()
    return _md(
        f"##### ✅ 灵阵更新\n\n**#{beast_id} {_display_name(profile)}** "
        f"已进入 {role[1]} 的{slot}位。\n"
        "> 新开启的PVE将冻结此阵容。\n\n"
        f"<qqbot-cmd-input text='灵兽阵容 {role[0]}' show='查看灵阵' />"
    )


@reg_xz_func
async def beast_preset(uid, qz, value):
    try:
        preset = int(str(value).strip())
    except ValueError:
        preset = 0
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role = await _current_role(uid, cursor, True)
            if not role:
                return _md("请先让角色出战。")
            garden = await _garden_level(uid, cursor)
            maximum = 3 if garden >= 10 else 1
            if preset < 1 or preset > maximum:
                return _md(
                    f"当前可用预设为1—{maximum}；灵兽园Lv.10解锁三套。"
                )
            await cursor.execute("""
                INSERT INTO user_spirit_beast_setting
                    (uid,role_id,active_preset)
                VALUES(%s,%s,%s)
                ON DUPLICATE KEY UPDATE active_preset=VALUES(active_preset)
            """, (uid, role[0], preset))
            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)
            await conn.commit()
    return _md(
        f"已切换至灵阵预设{preset}，只影响下一场新开启的战斗。\n"
        "<qqbot-cmd-input text='灵兽阵容' show='查看灵阵' />"
    )


@reg_xz_func
async def set_active_spirit_beast(uid, qz, value):
    """兼容旧指令；V2中“出战”等价于设置主契。"""
    parts = _parts(value)
    if not parts:
        return _md("指令：灵兽出战 灵兽编号 [角色编号]")
    target = f"{parts[0]} 主契" + (
        f" {parts[1]}" if len(parts) > 1 else ""
    )
    return await beast_formation_set.__wrapped__(uid, qz, target)


@reg_xz_func
async def beast_formation_remove(uid, qz, value):
    parts = _parts(value)
    if not parts or parts[0] not in SLOTS:
        return _md("指令：灵兽下阵 主契/护契/辅契 [角色编号]")
    slot = parts[0]
    target_role = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role = (
                await _owned_role(uid, target_role, cursor, True)
                if target_role else await _current_role(uid, cursor, True)
            )
            if not role:
                return _md("未找到目标角色。")
            preset = await _active_preset(uid, role[0], cursor)
            await cursor.execute("""
                DELETE FROM user_spirit_beast_formation
                WHERE uid=%s AND role_id=%s AND preset_no=%s AND slot_type=%s
            """, (uid, role[0], preset, slot))
            if cursor.rowcount <= 0:
                return _md(f"{slot}当前为空。")
            if slot == "主契" and int(role[3]):
                from Tool.tool_power import update_role_power
                await update_role_power(conn, uid)
            await conn.commit()
    return _md(
        f"{role[1]}预设{preset}的{slot}已下阵。绑定数据以外的养成不会丢失。"
    )


@reg_xz_func
async def beast_lock(uid, qz, value):
    parts = _parts(value)
    if not parts or not parts[0].isdigit():
        return _md("指令：灵兽锁定 灵兽编号 [锁定/解锁]")
    beast_id = int(parts[0])
    action = parts[1] if len(parts) > 1 else "锁定"
    locked = 0 if action == "解锁" else 1
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                UPDATE user_spirit_beast_v2 SET locked=%s
                WHERE id=%s AND uid=%s
            """, (locked, beast_id, uid))
            if cursor.rowcount <= 0:
                return _md("未找到这只灵兽。")
            await conn.commit()
    return _md(f"#{beast_id}已{action}；高价值批量操作会默认排除锁定灵兽。")


@reg_xz_func
async def beast_season(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT s.id,s.season_key,COALESCE(p.xp,0)
                FROM season s LEFT JOIN user_season_progress p
                  ON p.season_id=s.id AND p.uid=%s
                WHERE CURDATE() BETWEEN s.starts_on AND s.ends_on
                ORDER BY s.id DESC LIMIT 1
            """, (uid,))
            row = await cursor.fetchone()
            season_id, season_code, xp = (row if row else (0, "本期", 0))
            xp = int(xp or 0)
            granted = []
            milestones = (
                (20, {"story_token": 2}, "故事信物×2"),
                (60, {"nameplate": 1}, "灵兽改名牌×1"),
                (120, {"story_token": 5}, "故事信物×5"),
            )
            for tier, reward, label in milestones:
                if not season_id or xp < tier:
                    continue
                await cursor.execute("""
                    INSERT IGNORE INTO spirit_beast_reward_ledger
                        (uid,business_key,action_type,payload_json)
                    VALUES(%s,%s,'SEASON',%s)
                """, (
                    uid, f"beast-season:{season_id}:{tier}",
                    json.dumps(reward, ensure_ascii=False),
                ))
                if cursor.rowcount:
                    await _wallet_change(cursor, uid, reward)
                    granted.append(label)
            await conn.commit()
    grant_text = (
        "\n本次领取：" + "、".join(granted) + "\n"
        if granted else "\n已达成的灵兽里程碑奖励均已入库。\n"
    )
    return _md(
        f"##### 🌠 灵兽赛季｜{season_code}\n\n本赛季经验：{xp}\n{grant_text}"
        "> 灵兽赛季不出售限定战力；赛季经验沿用副本、宗门和世界Boss真实进度。\n"
        "> 里程碑提供改名牌、故事信物与纪念外观，战斗养成仍来自玩法。\n\n"
        "<qqbot-cmd-input text='赛季' show='赛季主页' /> | "
        "<qqbot-cmd-input text='灵兽周记' show='灵兽周记' /> | "
        "<qqbot-cmd-input text='万灵秘境' show='万灵秘境' />"
    )


@reg_xz_func
async def beast_dispatch_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT d.id,b.id,COALESCE(b.nickname,t.name),
                       d.dispatch_type,d.ends_at
                FROM spirit_beast_dispatch d
                JOIN user_spirit_beast_v2 b ON b.id=d.beast_id
                JOIN spirit_beast_template t ON t.id=b.template_id
                WHERE d.uid=%s AND d.state='ACTIVE'
                ORDER BY d.ends_at
            """, (uid,))
            rows = await cursor.fetchall()
    output = (
        "##### 🏞️ 灵兽派遣\n\n未上阵灵兽可执行4—12小时派遣；"
        "取消按已完成时间结算。\n\n"
    )
    for dispatch_id, beast_id, name, kind, ends_at in rows:
        remain = max(0, int((ends_at - datetime.now()).total_seconds()))
        output += (
            f"**#{beast_id} {name}**｜{kind}｜"
            f"剩余{remain // 3600:02d}:{remain % 3600 // 60:02d}\n"
            f"<qqbot-cmd-input text='灵兽派遣领取 {dispatch_id}' "
            f"show='结算#{beast_id}' /> | "
            f"<qqbot-cmd-input text='灵兽派遣取消 {dispatch_id}' "
            f"show='取消#{beast_id}' />\n\n"
        )
    if not rows:
        output += "> 当前没有派遣中的灵兽。\n\n"
    output += (
        "<qqbot-cmd-input text='灵兽派遣领取 全部' show='领取全部已完成' />\n\n"
        "发送：灵兽派遣开始 灵兽编号 巡山/采药/探矿/寻迹 4/8/12"
    )
    return _md(output)


@reg_xz_func
async def beast_dispatch_start(uid, qz, value):
    parts = _parts(value)
    if (
        len(parts) != 3 or not parts[0].isdigit()
        or parts[1] not in DISPATCH_TYPES or not parts[2].isdigit()
    ):
        return _md(
            "指令：灵兽派遣开始 灵兽编号 巡山/采药/探矿/寻迹 4/8/12"
        )
    beast_id, kind, hours = int(parts[0]), parts[1], int(parts[2])
    if hours not in (4, 8, 12):
        return _md("派遣时长仅可选4、8、12小时。")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile:
                return _md("未找到这只灵兽。")
            await cursor.execute("""
                SELECT 1 FROM user_spirit_beast_formation
                WHERE uid=%s AND beast_id=%s LIMIT 1
            """, (uid, beast_id))
            if await cursor.fetchone():
                return _md("已进入任一灵阵预设的灵兽不能派遣。")
            if await _is_dispatched(beast_id, cursor):
                return _md("这只灵兽已经在派遣中。")
            garden = await _garden_level(uid, cursor)
            reward = dispatch_reward(kind, hours, garden, profile)
            now = datetime.now()
            await cursor.execute("""
                INSERT INTO spirit_beast_dispatch
                    (uid,beast_id,dispatch_type,started_at,ends_at,reward_json)
                VALUES(%s,%s,%s,%s,%s,%s)
            """, (
                uid, beast_id, kind, now, now + timedelta(hours=hours),
                json.dumps(reward, ensure_ascii=False),
            ))
            await conn.commit()
    return _md(
        f"##### 🏞️ 派遣开始\n\n{_display_name(profile)}前往{kind}，"
        f"预计{hours}小时后归来。\n> 奖励已冻结，重启不会改变。\n"
        "<qqbot-cmd-input text='灵兽派遣' show='查看派遣' />"
    )


async def _dispatch_finish(uid, dispatch_id, cancel):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT id,beast_id,started_at,ends_at,reward_json
                FROM spirit_beast_dispatch
                WHERE id=%s AND uid=%s AND state='ACTIVE' FOR UPDATE
            """, (dispatch_id, uid))
            row = await cursor.fetchone()
            if not row:
                return _md("派遣不存在或已经结算。")
            now = datetime.now()
            if not cancel and now < row[3]:
                return _md("派遣尚未结束，可等待完成或取消后按进度结算。")
            total = max(1, int((row[3] - row[2]).total_seconds()))
            ratio = (
                1.0 if now >= row[3]
                else max(0.0, min(1.0, (now - row[2]).total_seconds() / total))
            )
            reward = (
                json.loads(row[4]) if isinstance(row[4], str) else dict(row[4])
            )
            reward = {
                key: int(value * ratio) for key, value in reward.items()
            }
            wallet_rewards = {
                key: value for key, value in reward.items()
                if key in WALLET_COLUMNS
            }
            await _wallet_change(cursor, uid, wallet_rewards)
            if reward.get("lingshi"):
                await cursor.execute(
                    "UPDATE user_zt SET lingshi=lingshi+%s WHERE id=%s",
                    (reward["lingshi"], uid),
                )
            if reward.get("herb_token"):
                await _wallet_change(
                    cursor, uid,
                    {"spirit_essence": reward["herb_token"] * 2},
                )
            state = "CANCELLED" if cancel else "CLAIMED"
            await cursor.execute("""
                UPDATE spirit_beast_dispatch SET state=%s
                WHERE id=%s AND state='ACTIVE'
            """, (state, dispatch_id))
            await cursor.execute("""
                INSERT INTO spirit_beast_weekly_journal
                    (uid,week_key,dispatch_count)
                VALUES(%s,%s,1)
                ON DUPLICATE KEY UPDATE dispatch_count=dispatch_count+1
            """, (uid, week_key()))
            await conn.commit()
    reward_text = "、".join(
        f"{key}+{value}" for key, value in reward.items() if value
    ) or "无（派遣时间过短）"
    return _md(
        f"##### ✅ 派遣结算\n\n进度：{ratio * 100:.0f}%｜获得：{reward_text}\n"
        "<qqbot-cmd-input text='灵兽派遣' show='返回派遣' />"
    )


@reg_xz_func
async def beast_dispatch_claim(uid, qz, value):
    if str(value or "").strip() == "全部":
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("""
                    SELECT id FROM spirit_beast_dispatch
                    WHERE uid=%s AND state='ACTIVE' AND ends_at<=NOW()
                    ORDER BY id
                """, (uid,))
                ids = [int(row[0]) for row in await cursor.fetchall()]
        if not ids:
            return _md("当前没有已完成且可领取的派遣。")
        results = []
        for dispatch_id in ids:
            result = await _dispatch_finish(uid, dispatch_id, False)
            results.append(result["content"].replace("##### ✅ 派遣结算\n\n", ""))
        return _md("##### ✅ 批量派遣结算\n\n" + "\n\n".join(results))
    dispatch_id = int(str(value).strip()) if str(value).strip().isdigit() else 0
    return await _dispatch_finish(uid, dispatch_id, False)


@reg_xz_func
async def beast_dispatch_cancel(uid, qz, value):
    dispatch_id = int(str(value).strip()) if str(value).strip().isdigit() else 0
    return await _dispatch_finish(uid, dispatch_id, True)


def _realm_worlds(day=None):
    index = (day or date.today()).isocalendar()[1] % len(WORLDS)
    return WORLDS[index], WORLDS[(index + 1) % len(WORLDS)]


@reg_xz_func
async def beast_realm(uid, qz):
    worlds = _realm_worlds()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT COUNT(*) FROM spirit_beast_realm_log
                WHERE uid=%s AND week_key=%s
            """, (uid, week_key()))
            used = int((await cursor.fetchone())[0])
    return _md(
        f"##### 🌌 万灵秘境\n\n本周主题：**{worlds[0]}、{worlds[1]}**｜"
        f"次数：{used}/3\n\n"
        "**血脉路线**：高压首领，产出血脉精华\n"
        "**技能路线**：破局考验，产出灵契残页\n"
        "**羁绊路线**：难度较低，产出故事信物\n\n"
        "<qqbot-cmd-input text='万灵秘境挑战 血脉' show='挑战血脉路线' /> | "
        "<qqbot-cmd-input text='万灵秘境挑战 技能' show='挑战技能路线' /> | "
        "<qqbot-cmd-input text='万灵秘境挑战 羁绊' show='挑战羁绊路线' />"
    )


@reg_xz_func
async def beast_realm_challenge(uid, qz, value):
    route = str(value or "").strip()
    if route not in REALM_ROUTES:
        return _md("路线可选：血脉、技能、羁绊。")
    worlds = _realm_worlds()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role = await _current_role(uid, cursor)
            if not role:
                return _md("请先让角色出战并配置主契。")
            snapshot = await load_formation_snapshot(uid, role[0], cursor)
            if not snapshot:
                return _md("请先配置主契灵兽。")
            await cursor.execute("""
                SELECT COUNT(*) FROM spirit_beast_realm_log
                WHERE uid=%s AND week_key=%s FOR UPDATE
            """, (uid, week_key()))
            attempt = int((await cursor.fetchone())[0]) + 1
            if attempt > 3:
                return _md("本周万灵秘境次数已用完。")
            world = worlds[(attempt - 1) % 2]
            formation_power = sum(
                int(item["power"]) for item in snapshot["formation"]
            )
            required = {
                "血脉": 7000, "技能": 5500, "羁绊": 3500,
            }[route] + attempt * 500
            won = formation_power >= required
            reward = (
                realm_reward(route, world, uid, f"{week_key()}:{attempt}")
                if won else {}
            )
            await cursor.execute("""
                INSERT INTO spirit_beast_realm_log
                    (uid,week_key,attempt_no,world,route,won,reward_json)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
            """, (
                uid, week_key(), attempt, world, route, 1 if won else 0,
                json.dumps(reward, ensure_ascii=False),
            ))
            if won:
                await _wallet_change(cursor, uid, reward)
            await conn.commit()
    if not won:
        consume = (
            "本周首次失败保护生效，本次记录不占用挑战次数。"
            if attempt == 1 else "本次挑战次数已消耗。"
        )
        if attempt == 1:
            async with connect_mysql() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("""
                        DELETE FROM spirit_beast_realm_log
                        WHERE uid=%s AND week_key=%s AND attempt_no=1 AND won=0
                    """, (uid, week_key()))
                    await conn.commit()
        return _md(
            f"##### ⚔️ 秘境未破\n\n灵阵战力{formation_power}，"
            f"路线建议{required}。\n> {consume}\n"
            "<qqbot-cmd-input text='灵兽阵容' show='调整灵阵' />"
        )
    reward_text = "、".join(
        f"{key}+{amount}" for key, amount in reward.items()
    )
    return _md(
        f"##### ✅ 秘境通关\n\n破解{world}·{route}路线！\n"
        f"> {reward_text}\n"
        "<qqbot-cmd-input text='万灵秘境' show='返回秘境' />"
    )


@reg_xz_func
async def beast_biography(uid, qz, value):
    try:
        beast_id = int(str(value).strip())
    except ValueError:
        return _md("指令：灵兽传记 灵兽编号")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor)
            if not profile:
                return _md("未找到这只灵兽。")
            level = bond_level(profile["bond_exp"])
            await cursor.execute("""
                SELECT story_chapter,story_choice
                FROM user_spirit_beast_codex
                WHERE uid=%s AND template_id=%s
            """, (uid, profile["template_id"]))
            codex = await cursor.fetchone() or (0, None)
    available = sum(level >= threshold for threshold in STORY_THRESHOLDS)
    titles = ("初见", "同行", "抉择", "归真")
    output = (
        f"##### 📖 {_display_name(profile)}传记\n\n羁绊 Lv.{level}｜"
        f"已完成 {codex[0]}/4｜可读 {available}/4\n"
    )
    for index, title in enumerate(titles, 1):
        state = "✅" if index <= codex[0] else (
            "📜" if index <= available else "🔒"
        )
        output += f"> {state} 第{index}章·{title}\n"
    if int(codex[0]) < available:
        output += (
            f"\n古印展开第{int(codex[0]) + 1}章。你选择如何回应？\n"
            f"<qqbot-cmd-input text='灵兽传记选择 {beast_id} 守望' "
            "show='守望同行' /> | "
            f"<qqbot-cmd-input text='灵兽传记选择 {beast_id} 自由' "
            "show='尊重自由' /> | "
            f"<qqbot-cmd-input text='灵兽传记选择 {beast_id} 求道' "
            "show='共同求道' />"
        )
    return _md(output)


@reg_xz_func
async def beast_biography_choose(uid, qz, value):
    parts = _parts(value)
    if (
        len(parts) != 2 or not parts[0].isdigit()
        or parts[1] not in ("守望", "自由", "求道")
    ):
        return _md("指令：灵兽传记选择 灵兽编号 守望/自由/求道")
    beast_id, choice = int(parts[0]), parts[1]
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile:
                return _md("未找到这只灵兽。")
            available = sum(
                bond_level(profile["bond_exp"]) >= threshold
                for threshold in STORY_THRESHOLDS
            )
            await cursor.execute("""
                SELECT story_chapter FROM user_spirit_beast_codex
                WHERE uid=%s AND template_id=%s FOR UPDATE
            """, (uid, profile["template_id"]))
            chapter = int((await cursor.fetchone())[0])
            if chapter >= available:
                return _md("当前没有可推进的传记章节。")
            await cursor.execute("""
                UPDATE user_spirit_beast_codex
                SET story_chapter=story_chapter+1,
                    story_choice=CONCAT(COALESCE(story_choice,''),%s)
                WHERE uid=%s AND template_id=%s
            """, (f"{chapter + 1}:{choice};", uid, profile["template_id"]))
            await conn.commit()
    return _md(
        f"##### 📖 传记推进\n\n你选择了“{choice}”。"
        "选择会进入纪念文本，但不改变核心战力。\n"
        f"<qqbot-cmd-input text='灵兽传记 {beast_id}' show='继续阅读' />"
    )


@reg_xz_func
async def beast_return(uid, qz, value):
    try:
        beast_id = int(str(value).strip())
    except ValueError:
        return _md("指令：灵兽归真 灵兽编号")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor)
            if not profile:
                return _md("未找到这只灵兽。")
            await cursor.execute("""
                SELECT 1 FROM user_spirit_beast_formation
                WHERE uid=%s AND beast_id=%s LIMIT 1
            """, (uid, beast_id))
            if await cursor.fetchone():
                return _md("请先将灵兽移出所有灵阵预设，再进行归真。")
            if await _is_dispatched(beast_id, cursor):
                return _md("请先结算派遣。")
            refund = return_refund(profile["level"], profile["stage"])
            token = _token(uid, "return", beast_id)
            payload = json.dumps(refund, ensure_ascii=False)
            await cursor.execute("""
                INSERT INTO spirit_beast_pending_choice
                    (uid,choice_type,beast_id,template_id,payload_json,
                     token,expires_at)
                VALUES(%s,'RETURN',%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                    beast_id=VALUES(beast_id),template_id=VALUES(template_id),
                    payload_json=VALUES(payload_json),token=VALUES(token),
                    expires_at=VALUES(expires_at)
            """, (
                uid, beast_id, profile["template_id"], payload, token,
                datetime.now() + timedelta(minutes=10),
            ))
            await conn.commit()
    risk = (
        "\n> ⚠️ 高价值灵兽已启用二次确认。"
        if (
            QUALITY_RANK[profile["quality"]] >= 3 or profile["locked"]
            or bond_level(profile["bond_exp"]) >= 5 or profile["nickname"]
        ) else ""
    )
    return _md(
        f"##### ⚠️ 灵兽归真预览\n\n对象：#{beast_id} "
        f"{_display_name(profile)}｜{profile['quality']}｜"
        f"羁绊{bond_level(profile['bond_exp'])}\n"
        f"返还：御兽灵息{refund['spirit_essence']}、"
        f"基础兽材{refund['beast_material']}\n"
        f"保留：血脉、羁绊、传记、图鉴最高资质与技能书库{risk}\n\n"
        f"<qqbot-cmd-input text='灵兽归真确认 {token}' show='确认归真' /> | "
        f"<qqbot-cmd-input text='灵兽归真取消 {token}' show='取消归真' />"
    )


@reg_xz_func
async def beast_return_confirm(uid, qz, token):
    token = str(token or "").strip()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT beast_id,payload_json,expires_at
                FROM spirit_beast_pending_choice
                WHERE uid=%s AND choice_type='RETURN' AND token=%s FOR UPDATE
            """, (uid, token))
            pending = await cursor.fetchone()
            if not pending or pending[2] < datetime.now():
                return _md("归真令牌无效或已过期。")
            profile = await _load_beast(uid, pending[0], cursor, True)
            if not profile:
                return _md("灵兽已不存在，本次没有重复处理。")
            refund = (
                json.loads(pending[1])
                if isinstance(pending[1], str) else dict(pending[1])
            )
            await cursor.execute("""
                INSERT IGNORE INTO spirit_beast_return_log(uid,week_key)
                VALUES(%s,%s)
            """, (uid, week_key()))
            await cursor.execute("""
                SELECT return_count FROM spirit_beast_return_log
                WHERE uid=%s AND week_key=%s FOR UPDATE
            """, (uid, week_key()))
            return_count = int((await cursor.fetchone())[0])
            await cursor.execute("""
                SELECT MAX(free_return_until) FROM user_spirit_beast_setting
                WHERE uid=%s
            """, (uid,))
            free_until = (await cursor.fetchone())[0]
            fee = 0 if return_count < 3 or (
                free_until and free_until >= date.today()
            ) else 2000
            if fee:
                await cursor.execute("""
                    UPDATE user_zt SET lingshi=lingshi-%s
                    WHERE id=%s AND lingshi>=%s
                """, (fee, uid, fee))
                if cursor.rowcount <= 0:
                    return _md("本周前三次免费归真已用完，本次需要2000灵石。")
            await _wallet_change(cursor, uid, refund)
            await cursor.execute(
                "DELETE FROM user_spirit_beast_skill_slot WHERE beast_id=%s",
                (pending[0],),
            )
            await cursor.execute(
                "DELETE FROM user_spirit_beast_aptitude WHERE beast_id=%s",
                (pending[0],),
            )
            await cursor.execute("""
                DELETE FROM user_spirit_beast_v2 WHERE id=%s AND uid=%s
            """, (pending[0], uid))
            await cursor.execute("""
                DELETE FROM spirit_beast_pending_choice
                WHERE uid=%s AND choice_type='RETURN'
            """, (uid,))
            await cursor.execute("""
                INSERT IGNORE INTO spirit_beast_reward_ledger
                    (uid,business_key,action_type,payload_json)
                VALUES(%s,%s,'RETURN',%s)
            """, (uid, f"return:{token}", json.dumps(refund, ensure_ascii=False)))
            await cursor.execute("""
                UPDATE spirit_beast_return_log SET return_count=return_count+1
                WHERE uid=%s AND week_key=%s
            """, (uid, week_key()))
            await conn.commit()
    return _md(
        f"##### ✅ 归真完成\n\n#{pending[0]}已回归万灵古印。"
        "培养资源100%返还，羁绊与灵种血脉永久保留。\n"
        "<qqbot-cmd-input text='我的灵兽' show='返回收藏' />"
    )


@reg_xz_func
async def beast_return_cancel(uid, qz, token):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                DELETE FROM spirit_beast_pending_choice
                WHERE uid=%s AND choice_type='RETURN' AND token=%s
            """, (uid, str(token).strip()))
            await conn.commit()
    return _md("已取消归真，灵兽和全部养成数据保持不变。")


@reg_xz_func
async def beast_batch_return(uid, qz):
    """只选择低价值、未锁定、未命名且未上阵/派遣的灵兽。"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT b.id,b.level,b.stage
                FROM user_spirit_beast_v2 b
                JOIN spirit_beast_template t ON t.id=b.template_id
                WHERE b.uid=%s AND b.locked=0 AND b.nickname IS NULL
                  AND b.bond_exp<500 AND t.quality IN ('灵品','玄品')
                  AND NOT EXISTS (
                    SELECT 1 FROM user_spirit_beast_formation f
                    WHERE f.uid=b.uid AND f.beast_id=b.id
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM spirit_beast_dispatch d
                    WHERE d.uid=b.uid AND d.beast_id=b.id AND d.state='ACTIVE'
                  )
                ORDER BY b.id LIMIT 50
            """, (uid,))
            rows = await cursor.fetchall()
            if not rows:
                return _md(
                    "没有可批量归真的普通灵兽。地品、天品、已命名、已锁定、"
                    "羁绊5级以上及上阵/派遣灵兽均受保护。"
                )
            refund = {"spirit_essence": 0, "beast_material": 0}
            beast_ids = []
            for beast_id, level, stage in rows:
                beast_ids.append(int(beast_id))
                item = return_refund(level, stage)
                for key in refund:
                    refund[key] += int(item[key])
            token = _token(uid, "batch-return", *beast_ids)
            payload = {
                "beast_ids": beast_ids,
                "refund": refund,
            }
            await cursor.execute("""
                INSERT INTO spirit_beast_pending_choice
                    (uid,choice_type,beast_id,template_id,payload_json,
                     token,expires_at)
                VALUES(%s,'BATCH_RETURN',NULL,NULL,%s,%s,%s)
                ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json),
                    token=VALUES(token),expires_at=VALUES(expires_at)
            """, (
                uid, json.dumps(payload, ensure_ascii=False), token,
                datetime.now() + timedelta(minutes=10),
            ))
            await conn.commit()
    return _md(
        f"##### ⚠️ 批量归真预览\n\n普通灵兽：**{len(beast_ids)}只**｜"
        f"编号：{','.join(map(str, beast_ids))}\n"
        f"> 返还御兽灵息{refund['spirit_essence']}、基础兽材{refund['beast_material']}\n"
        "> 高价值与正在使用的灵兽已自动排除；确认时会再次校验。\n\n"
        f"<qqbot-cmd-input text='灵兽批量归真确认 {token}' show='确认批量归真' /> | "
        f"<qqbot-cmd-input text='灵兽批量归真取消 {token}' show='取消' />"
    )


@reg_xz_func
async def beast_batch_return_confirm(uid, qz, token):
    token = str(token or "").strip()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT payload_json,expires_at FROM spirit_beast_pending_choice
                WHERE uid=%s AND choice_type='BATCH_RETURN' AND token=%s
                FOR UPDATE
            """, (uid, token))
            row = await cursor.fetchone()
            if not row or row[1] < datetime.now():
                return _md("批量归真令牌无效或已过期。")
            payload = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0])
            requested = [int(item) for item in payload.get("beast_ids", [])][:50]
            valid = []
            refund = {"spirit_essence": 0, "beast_material": 0}
            for beast_id in requested:
                profile = await _load_beast(uid, beast_id, cursor, True)
                if not profile or profile["locked"] or profile["nickname"]:
                    continue
                if bond_level(profile["bond_exp"]) >= 5 or QUALITY_RANK[profile["quality"]] >= 3:
                    continue
                await cursor.execute("""
                    SELECT 1 FROM user_spirit_beast_formation
                    WHERE uid=%s AND beast_id=%s LIMIT 1
                """, (uid, beast_id))
                if await cursor.fetchone() or await _is_dispatched(beast_id, cursor):
                    continue
                valid.append(beast_id)
                item = return_refund(profile["level"], profile["stage"])
                for key in refund:
                    refund[key] += int(item[key])
            if not valid:
                return _md("预览中的灵兽状态已改变，没有可安全归真的对象。")
            await cursor.execute("""
                INSERT IGNORE INTO spirit_beast_return_log(uid,week_key)
                VALUES(%s,%s)
            """, (uid, week_key()))
            await cursor.execute("""
                SELECT return_count FROM spirit_beast_return_log
                WHERE uid=%s AND week_key=%s FOR UPDATE
            """, (uid, week_key()))
            used = int((await cursor.fetchone())[0])
            await cursor.execute("""
                SELECT MAX(free_return_until) FROM user_spirit_beast_setting
                WHERE uid=%s
            """, (uid,))
            free_until = (await cursor.fetchone())[0]
            paid_count = (
                0 if free_until and free_until >= date.today()
                else max(0, used + len(valid) - 3) - max(0, used - 3)
            )
            fee = paid_count * 2000
            if fee:
                await cursor.execute("""
                    UPDATE user_zt SET lingshi=lingshi-%s
                    WHERE id=%s AND lingshi>=%s
                """, (fee, uid, fee))
                if cursor.rowcount <= 0:
                    return _md(f"批量归真需要服务费{fee}灵石，当前灵石不足。")
            placeholders = ",".join(["%s"] * len(valid))
            await _wallet_change(cursor, uid, refund)
            await cursor.execute(
                f"DELETE FROM user_spirit_beast_skill_slot WHERE beast_id IN ({placeholders})",
                tuple(valid),
            )
            await cursor.execute(
                f"DELETE FROM user_spirit_beast_aptitude WHERE beast_id IN ({placeholders})",
                tuple(valid),
            )
            await cursor.execute(
                f"DELETE FROM user_spirit_beast_v2 WHERE uid=%s AND id IN ({placeholders})",
                (uid, *valid),
            )
            await cursor.execute("""
                UPDATE spirit_beast_return_log SET return_count=return_count+%s
                WHERE uid=%s AND week_key=%s
            """, (len(valid), uid, week_key()))
            await cursor.execute("""
                INSERT IGNORE INTO spirit_beast_reward_ledger
                    (uid,business_key,action_type,payload_json)
                VALUES(%s,%s,'BATCH_RETURN',%s)
            """, (uid, f"batch-return:{token}", json.dumps({"ids": valid, "refund": refund}, ensure_ascii=False)))
            await cursor.execute("""
                DELETE FROM spirit_beast_pending_choice
                WHERE uid=%s AND choice_type='BATCH_RETURN'
            """, (uid,))
            await conn.commit()
    return _md(
        f"##### ✅ 批量归真完成\n\n已归真{len(valid)}只普通灵兽，服务费{fee}灵石。\n"
        f"> 御兽灵息+{refund['spirit_essence']}｜基础兽材+{refund['beast_material']}\n"
        "<qqbot-cmd-input text='我的灵兽' show='返回收藏' />"
    )


@reg_xz_func
async def beast_batch_return_cancel(uid, qz, token):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                DELETE FROM spirit_beast_pending_choice
                WHERE uid=%s AND choice_type='BATCH_RETURN' AND token=%s
            """, (uid, str(token or "").strip()))
            await conn.commit()
    return _md("已取消批量归真。")


@reg_xz_func
async def beast_rename(uid, qz, value):
    parts = _parts(value)
    if len(parts) != 2 or not parts[0].isdigit() or not 2 <= len(parts[1]) <= 8:
        return _md("指令：灵兽改名 灵兽编号 新名称（2—8字）")
    beast_id, name = int(parts[0]), parts[1]
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _load_beast(uid, beast_id, cursor, True)
            if not profile or bond_level(profile["bond_exp"]) < 5:
                return _md("灵兽不存在，或羁绊尚未达到5级。")
            if not await _wallet_change(cursor, uid, {"nameplate": -1}):
                return _md(
                    "缺少灵兽改名牌。改名牌只从外观和赛季便利奖励获得。"
                )
            await cursor.execute("""
                UPDATE user_spirit_beast_v2 SET nickname=%s
                WHERE id=%s AND uid=%s
            """, (name, beast_id, uid))
            await conn.commit()
    return _md(
        f"从今日起，{profile['name']}将以 **{name}** 之名与你同行。"
    )


@reg_xz_func
async def beast_journal(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                INSERT IGNORE INTO spirit_beast_weekly_journal(uid,week_key)
                VALUES(%s,%s)
            """, (uid, week_key()))
            await cursor.execute("""
                SELECT pve_count,care_count,dispatch_count,claimed
                FROM spirit_beast_weekly_journal
                WHERE uid=%s AND week_key=%s
            """, (uid, week_key()))
            row = await cursor.fetchone()
            await conn.commit()
    done = min(int(row[0]), 6) + min(int(row[1]), 3) + min(int(row[2]), 2)
    output = (
        f"##### 📘 灵兽周记｜{week_key()}\n\n"
        f"参战：{min(row[0], 6)}/6｜照料：{min(row[1], 3)}/3｜"
        f"派遣：{min(row[2], 2)}/2\n总进度：{done}/11｜"
        f"{'已领取' if row[3] else '待完成'}\n\n"
        "> 奖励：洗髓露3、兽魂石2、御兽灵息120。\n"
    )
    if done >= 11 and not row[3]:
        output += (
            "\n<qqbot-cmd-input text='灵兽周记领取' show='领取周记奖励' />"
        )
    return _md(output)


@reg_xz_func
async def beast_journal_claim(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT pve_count,care_count,dispatch_count,claimed
                FROM spirit_beast_weekly_journal
                WHERE uid=%s AND week_key=%s FOR UPDATE
            """, (uid, week_key()))
            row = await cursor.fetchone()
            progress = (
                min(int(row[0]), 6) + min(int(row[1]), 3)
                + min(int(row[2]), 2)
            ) if row else 0
            if progress < 11:
                return _md("周记尚未完成。")
            if row[3]:
                return _md("本周周记奖励已领取。")
            await cursor.execute("""
                UPDATE spirit_beast_weekly_journal SET claimed=1
                WHERE uid=%s AND week_key=%s
            """, (uid, week_key()))
            await _wallet_change(
                cursor, uid,
                {"wash_dew": 3, "soul_stone": 2, "spirit_essence": 120},
            )
            await conn.commit()
    return _md(
        "##### 🎁 周记完成\n\n获得洗髓露×3、兽魂石×2、御兽灵息×120。"
    )


@reg_xz_func
async def beast_spar(uid, qz, value):
    try:
        target_uid = int(str(value).strip().replace("@", ""))
    except ValueError:
        return _md("指令：灵兽切磋 对方UID")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            left_role = await _current_role(uid, cursor)
            right_role = await _current_role(target_uid, cursor)
            left = (
                await load_formation_snapshot(uid, left_role[0], cursor)
                if left_role else None
            )
            right = (
                await load_formation_snapshot(target_uid, right_role[0], cursor)
                if right_role else None
            )
    if not left or not right:
        return _md("双方都需要配置主契灵阵。")

    def score(snapshot):
        base = sum(
            calculate_v2_power(item)["power"]
            for item in snapshot["formation"]
        )
        return (
            base + snapshot["resonance"]["value"] * 120
            + snapshot["role_synergy"]["value"] * 80
        )

    left_score, right_score = score(left), score(right)
    winner = "你方灵阵" if left_score >= right_score else f"UID {target_uid}的灵阵"
    return _md(
        f"##### ⚔️ 灵兽切磋\n\n你方：{left['name']}｜标准分{left_score}\n"
        f"对方：{right['name']}｜标准分{right_score}\n\n"
        f"**{winner}** 在本次机制推演中占优。\n"
        "> 切磋使用标准化属性，无奖励、不消耗资源、不进入日常。"
    )


@reg_xz_func
async def sect_guardian_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT sm.sect_id,s.name
                FROM sect_member sm JOIN sect s ON s.id=sm.sect_id
                WHERE sm.uid=%s AND sm.member_state='ACTIVE' LIMIT 1
            """, (uid,))
            sect = await cursor.fetchone()
            if not sect:
                return _md("请先加入宗门。")
            await cursor.execute("""
                INSERT IGNORE INTO sect_spirit_beast_guardian(sect_id,week_key)
                VALUES(%s,%s)
            """, (sect[0], week_key()))
            await cursor.execute("""
                SELECT level,supply FROM sect_spirit_beast_guardian
                WHERE sect_id=%s AND week_key=%s
            """, (sect[0], week_key()))
            guardian = await cursor.fetchone()
            await cursor.execute("""
                SELECT supplied FROM sect_spirit_beast_supply
                WHERE sect_id=%s AND uid=%s AND week_key=%s
            """, (sect[0], uid, week_key()))
            personal = await cursor.fetchone()
            await conn.commit()
    return _md(
        f"##### 🐲 {sect[1]}护山灵兽\n\n本周等级：{guardian[0]}｜"
        f"全宗供养：{guardian[1]}\n你的供养：{personal[0] if personal else 0}/3\n\n"
        "> 协作只提供秘境追赶材料，不增加个人永久攻击。\n"
        "<qqbot-cmd-input text='护山灵兽供养' show='供养一次' />"
    )


@reg_xz_func
async def sect_guardian_supply(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT sect_id,contribution FROM sect_member
                WHERE uid=%s AND member_state='ACTIVE' LIMIT 1 FOR UPDATE
            """, (uid,))
            member = await cursor.fetchone()
            if not member:
                return _md("请先加入宗门。")
            from Game_main.g19_sect import get_active_research
            research = await get_active_research(uid, cursor)
            chase_bonus = (
                1 if research and research.get("research_type") == "御兽学" else 0
            )
            await cursor.execute("""
                INSERT IGNORE INTO sect_spirit_beast_supply
                    (sect_id,uid,week_key)
                VALUES(%s,%s,%s)
            """, (member[0], uid, week_key()))
            await cursor.execute("""
                SELECT supplied FROM sect_spirit_beast_supply
                WHERE sect_id=%s AND uid=%s AND week_key=%s FOR UPDATE
            """, (member[0], uid, week_key()))
            supplied = int((await cursor.fetchone())[0])
            if supplied >= 3 or int(member[1]) < 10:
                return _md("本周已供养3次，或宗门贡献不足10。")
            await cursor.execute("""
                UPDATE sect_member SET contribution=contribution-10
                WHERE sect_id=%s AND uid=%s
            """, (member[0], uid))
            await cursor.execute("""
                UPDATE sect_spirit_beast_supply SET supplied=supplied+1
                WHERE sect_id=%s AND uid=%s AND week_key=%s
            """, (member[0], uid, week_key()))
            await cursor.execute("""
                INSERT INTO sect_spirit_beast_guardian(sect_id,week_key,supply)
                VALUES(%s,%s,1)
                ON DUPLICATE KEY UPDATE
                    supply=supply+1,level=1+FLOOR((supply+1)/20)
            """, (member[0], week_key()))
            await _wallet_change(
                cursor, uid,
                {
                    "bloodline_essence": 1 + chase_bonus,
                    "wash_dew": 1,
                },
            )
            await conn.commit()
    bonus_text = "（御兽学追赶+1）" if chase_bonus else ""
    return _md(
        f"供养完成：宗门贡献-10，获得血脉精华×{1 + chase_bonus}"
        f"{bonus_text}、洗髓露×1。"
    )


async def record_spirit_beast_pve(
    uid, role_id, completed=False, swept=False, source="DUNGEON"
):
    """手动前三场给羁绊；首次完整通关给兽踪；扫荡仅基础材料。"""
    today = date.today()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_user(uid, cursor)
            if swept:
                await _wallet_change(
                    cursor, uid, {"beast_material": 2, "spirit_essence": 8}
                )
                await conn.commit()
                return {"beast_material": 2, "spirit_essence": 8}
            await cursor.execute("""
                INSERT IGNORE INTO spirit_beast_daily_activity(uid,activity_date)
                VALUES(%s,%s)
            """, (uid, today))
            await cursor.execute("""
                SELECT pve_bond_count FROM spirit_beast_daily_activity
                WHERE uid=%s AND activity_date=%s FOR UPDATE
            """, (uid, today))
            count = int((await cursor.fetchone())[0])
            formation = await _formation_rows(uid, role_id, cursor)
            bond_granted = 0
            if count < 3 and formation:
                ids = [int(row["id"]) for row in formation]
                placeholders = ",".join(["%s"] * len(ids))
                await cursor.execute(
                    f"UPDATE user_spirit_beast_v2 SET bond_exp=bond_exp+10 "
                    f"WHERE uid=%s AND id IN ({placeholders})",
                    (uid, *ids),
                )
                await cursor.execute("""
                    UPDATE spirit_beast_daily_activity
                    SET pve_bond_count=pve_bond_count+1
                    WHERE uid=%s AND activity_date=%s
                """, (uid, today))
                bond_granted = 10
            await cursor.execute("""
                INSERT INTO spirit_beast_weekly_journal
                    (uid,week_key,pve_count)
                VALUES(%s,%s,1)
                ON DUPLICATE KEY UPDATE pve_count=pve_count+1
            """, (uid, week_key()))
            trace_granted = 0
            if completed:
                business_key = f"daily-trace:{uid}:{today}"
                await cursor.execute("""
                    INSERT IGNORE INTO spirit_beast_reward_ledger
                        (uid,business_key,action_type,payload_json)
                    VALUES(%s,%s,'DAILY_TRACE','{}')
                """, (uid, business_key))
                if cursor.rowcount > 0:
                    await _wallet_change(
                        cursor, uid,
                        {
                            "beast_trace": 1, "spirit_essence": 12,
                            "beast_material": 2,
                        },
                    )
                    trace_granted = 1
            if bond_granted:
                await _refresh_current_power(conn, uid)
            await conn.commit()
    return {
        "beast_trace": trace_granted,
        "bond": bond_granted,
        "beast_material": 2 if completed else 0,
    }


async def record_spirit_beast_world_boss(uid, action):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _wallet_change(
                cursor, uid,
                {
                    "soul_fragment": 2,
                    "skill_page": 1 if action in ("净化", "辅助") else 0,
                },
            )
            await conn.commit()


async def world_boss_beast_modifier(uid, cursor):
    """每周万灵弱点轮换；收益封顶5%，辅助与伤害都可贡献。"""
    role = await _current_role(uid, cursor)
    snapshot = (
        await load_formation_snapshot(uid, role[0], cursor) if role else None
    )
    weakness_roles = ("STRIKER", "GUARDIAN", "HEALER", "DISRUPTOR", "BREAKER")
    weakness = weakness_roles[date.today().isocalendar()[1] % len(weakness_roles)]
    active = bool(snapshot and snapshot["main"]["role"] == weakness)
    return {
        "role": weakness,
        "label": ROLE_LABELS[weakness],
        "bonus_bp": 500 if active else 0,
        "main_name": snapshot["name"] if snapshot else "",
    }
