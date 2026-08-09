# -*- coding: utf-8 -*-
"""轮海深渊应用服务：进度、波次、战斗交接与原子结算。"""

import copy
import json
import random
from decimal import Decimal
from html import escape
from uuid import uuid4

from sql.mysql import connect_mysql
from Tool.combat_system import CombatEntity, CombatManager, Skill, normalize_buff_target
from Game_domain.role_trait_service import (
    apply_battle_hp,
    calculate_lingshi_output,
    has_owned_role,
)

from .abyss_rules import (
    ABYSS_MAX_KILLS,
    abyss_monster_multiplier,
    abyss_rating,
    abyss_tier_min_level,
    build_abyss_monster_stats,
    calculate_reward_delta,
    placement_target,
    select_wave_templates,
)
from .battle_models import STATE_FINISHED
from .battle_repository import MySQLBattleRepository
from .reward_service import MySQLRewardService, required_exp


ACTIVE_RUN_STATES = ("READY", "FIGHTING", "QUALIFIED", "SETTLING")
LOCKED_ROLE_STATES = ("FIGHTING", "QUALIFIED", "SETTLING")
RUN_COLUMNS = (
    "run_uuid", "uid", "run_type", "layer_no", "role_id", "source_world",
    "source_dungeon_id", "rng_seed", "state", "wave_no", "kill_count",
    "player_hp_ratio", "version", "role_snapshot_json", "effect_snapshot_json",
    "reward_snapshot_json", "settlement_json", "created_at", "settled_at",
)


class AbyssError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _loads(value, default=None):
    if value in (None, ""):
        return copy.deepcopy(default)
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    return json.loads(value)


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return str(value)


def _dumps(value):
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _run_from_row(row):
    if not row:
        return None
    data = dict(zip(RUN_COLUMNS, row))
    data["layer_no"] = int(data["layer_no"])
    data["wave_no"] = int(data["wave_no"])
    data["kill_count"] = int(data["kill_count"])
    data["player_hp_ratio"] = float(data["player_hp_ratio"])
    for key in ("role_snapshot_json", "effect_snapshot_json", "reward_snapshot_json", "settlement_json"):
        data[key[:-5] if key.endswith("_json") else key] = _loads(data.pop(key), {})
    return data


def _run_select(lock=False):
    suffix = " FOR UPDATE" if lock else ""
    return f"""
        SELECT run_uuid,uid,run_type,layer_no,role_id,source_world,
               source_dungeon_id,rng_seed,state,wave_no,kill_count,
               player_hp_ratio,version,role_snapshot_json,effect_snapshot_json,
               reward_snapshot_json,settlement_json,created_at,settled_at
        FROM abyss_run WHERE uid = %s AND state IN ('READY','FIGHTING','QUALIFIED','SETTLING')
        ORDER BY created_at DESC LIMIT 1{suffix}
    """


async def get_active_run(uid, cursor=None, lock=False):
    async def _query(cur):
        await cur.execute(_run_select(lock=lock), (uid,))
        return _run_from_row(await cur.fetchone())

    if cursor is not None:
        return await _query(cursor)
    async with connect_mysql() as conn:
        async with conn.cursor() as cur:
            return await _query(cur)


async def is_role_locked_by_abyss(uid, cursor=None):
    async def _query(cur):
        await cur.execute(
            "SELECT 1 FROM abyss_run WHERE uid = %s AND state IN ('FIGHTING','QUALIFIED','SETTLING') LIMIT 1",
            (uid,),
        )
        return bool(await cur.fetchone())

    if cursor is not None:
        return await _query(cursor)
    async with connect_mysql() as conn:
        async with conn.cursor() as cur:
            return await _query(cur)


async def _ensure_profile(cursor, uid):
    await cursor.execute("INSERT IGNORE INTO user_abyss_profile (uid) VALUES (%s)", (uid,))
    await cursor.execute(
        "SELECT highest_cleared_layer,total_kills FROM user_abyss_profile WHERE uid = %s",
        (uid,),
    )
    row = await cursor.fetchone()
    return {"highest_cleared_layer": int(row[0]), "total_kills": int(row[1])}


async def get_dashboard(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            profile = await _ensure_profile(cursor, uid)
            await cursor.execute(
                "SELECT id,`name`,dengji,world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1",
                (uid,),
            )
            role_row = await cursor.fetchone()
            role = None
            if role_row:
                role = {"id": int(role_row[0]), "name": role_row[1], "level": int(role_row[2]), "world": role_row[3]}
            run = await get_active_run(uid, cursor)
            await conn.commit()
            return {"profile": profile, "role": role, "run": run}


async def _available_dungeons(cursor, layer_no):
    min_level = abyss_tier_min_level(layer_no)
    await cursor.execute(
        "SELECT id,`name`,world,min_level FROM data_dungeon WHERE min_level = %s ORDER BY id",
        (min_level,),
    )
    return [
        {"id": int(row[0]), "name": row[1], "world": row[2], "min_level": int(row[3])}
        for row in await cursor.fetchall()
    ]


async def create_preview(uid, layer_no=None, run_type="NORMAL"):
    run_type = str(run_type or "NORMAL").upper()
    if run_type not in ("NORMAL", "PLACEMENT"):
        raise AbyssError("RUN_TYPE_INVALID", "未知的深渊挑战类型。")
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT id FROM user_zt WHERE id = %s FOR UPDATE", (uid,))
                if not await cursor.fetchone():
                    raise AbyssError("PLAYER_NOT_FOUND", "玩家数据不存在。")
                profile = await _ensure_profile(cursor, uid)
                await cursor.execute(
                    "SELECT id,`name`,dengji,world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1",
                    (uid,),
                )
                role_row = await cursor.fetchone()
                if not role_row:
                    raise AbyssError("ROLE_REQUIRED", "请先选择一名角色出战。")
                role = {"id": int(role_row[0]), "name": role_row[1], "level": int(role_row[2]), "world": role_row[3]}

                if run_type == "PLACEMENT":
                    try:
                        target = placement_target(role["level"])
                    except ValueError as exc:
                        raise AbyssError("PLACEMENT_LOCKED", str(exc)) from exc
                    if profile["highest_cleared_layer"] >= target:
                        raise AbyssError("PLACEMENT_REDUNDANT", f"你已通关第{profile['highest_cleared_layer']}层，无需挑战第{target}层定级赛。")
                    layer_no = target
                else:
                    try:
                        layer_no = int(layer_no or (profile["highest_cleared_layer"] + 1))
                    except (TypeError, ValueError) as exc:
                        raise AbyssError("LAYER_INVALID", "深渊层数应为正整数。") from exc
                    if layer_no < 1 or layer_no > profile["highest_cleared_layer"] + 1:
                        raise AbyssError("LAYER_LOCKED", f"当前最高可挑战第{profile['highest_cleared_layer'] + 1}层。")

                existing = await get_active_run(uid, cursor, lock=True)
                if existing:
                    if existing["state"] != "READY":
                        raise AbyssError("RUN_ACTIVE", "已有进行中的深渊挑战，请先继续或结算。")
                    if existing["layer_no"] == layer_no and existing["run_type"] == run_type:
                        await conn.commit()
                        return existing
                    await cursor.execute(
                        "UPDATE abyss_run SET state = 'ABANDONED',settled_at = NOW() WHERE run_uuid = %s AND state = 'READY'",
                        (existing["run_uuid"],),
                    )

                dungeons = await _available_dungeons(cursor, layer_no)
                if len(dungeons) < 6:
                    raise AbyssError("MONSTER_POOL_MISSING", "六世界副本数据不完整，暂时无法生成该层深渊。")
                run_uuid = str(uuid4())
                rng_seed = uuid4().hex
                dungeon = random.Random(rng_seed).choice(dungeons)
                await cursor.execute(
                    """
                    INSERT INTO abyss_run
                        (run_uuid,uid,run_type,layer_no,source_world,source_dungeon_id,rng_seed,state)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'READY')
                    """,
                    (run_uuid, uid, run_type, layer_no, dungeon["world"], dungeon["id"], rng_seed),
                )
                await conn.commit()
                return await get_active_run(uid)
        except Exception:
            await conn.rollback()
            raise


async def get_world_role_names(world, cursor=None):
    async def _query(cur):
        await cur.execute("SELECT `name` FROM data_role WHERE world = %s ORDER BY id", (world,))
        return [row[0] for row in await cur.fetchall()]
    if cursor is not None:
        return await _query(cursor)
    async with connect_mysql() as conn:
        async with conn.cursor() as cur:
            return await _query(cur)


async def get_source_dungeon(source_dungeon_id):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id,`name`,world,min_level FROM data_dungeon WHERE id=%s LIMIT 1",
                (source_dungeon_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {"id": int(row[0]), "name": row[1], "world": row[2], "min_level": int(row[3])}


async def _load_player_skills(cursor, uid, role_id, role_name, slots, effect_bonus_bp):
    skills = []
    for slot_id in slots:
        if not slot_id:
            continue
        await cursor.execute(
            """
            SELECT skill_id,is_data_skill,skill_name,skill_type,value,is_percent,
                   cooldown,mana_cost,skill_1
            FROM user_skill WHERE id = %s AND uid = %s LIMIT 1
            """,
            (slot_id, uid),
        )
        row = await cursor.fetchone()
        if not row:
            continue
        data_skill_id, is_data_skill, skill_name, skill_type, value, is_percent, cooldown, mana_cost, source_skill_id = row
        buff_type = None
        buff_value = buff_duration = 0
        buff_target = 2
        buff_desc = buff_name = ""
        item_id = 0
        if int(is_data_skill or 0) == 1:
            await cursor.execute(
                """
                SELECT skill_name,skill_type,value,is_percent,item_id,buff_type,buff_value,
                       buff_duration,buff_target,buff_desc,buff_name,cooldown,mana_cost
                FROM data_skill WHERE id = %s LIMIT 1
                """,
                (data_skill_id,),
            )
            base = await cursor.fetchone()
            if not base:
                continue
            skill_name, skill_type, value, is_percent, item_id, buff_type, buff_value, buff_duration, buff_target, buff_desc, buff_name, cooldown, mana_cost = base
        elif source_skill_id:
            await cursor.execute(
                "SELECT buff_type,buff_value,buff_duration,buff_target,buff_desc,buff_name FROM data_skill WHERE id = %s LIMIT 1",
                (source_skill_id,),
            )
            buff = await cursor.fetchone()
            if buff:
                buff_type, buff_value, buff_duration, buff_target, buff_desc, buff_name = buff
        normalized_target = normalize_buff_target(buff_target, buff_type=buff_type)
        skill = Skill(
            id=int(slot_id), name=skill_name, skill_type=int(skill_type),
            target_type="enemy" if normalized_target == 2 else "self",
            value=int(float(value or 0)), is_percent=int(is_percent or 0),
            item_id=int(item_id or 0), cooldown=int(cooldown or 0), mana_cost=int(mana_cost or 0),
            effect_bonus_bp=int(effect_bonus_bp or 0), buff_type=buff_type,
            buff_value=int(buff_value or 0), buff_duration=int(buff_duration or 0),
            buff_target=normalized_target, buff_name=buff_name or "", description=buff_desc or "",
        )
        skills.append(skill.to_snapshot())

    from Game_main.g4_benyuan import get_role_benyuan_skills_for_battle
    benyuan_skills = await get_role_benyuan_skills_for_battle(uid, role_id, role_name, cursor)
    for data in benyuan_skills:
        target = normalize_buff_target(data.get("buff_target"), buff_type=data.get("buff_type"))
        skills.append(Skill(
            id=int(data["id"]), name=data["skill_name"], skill_type=int(data["skill_type"]),
            target_type="enemy" if target == 2 else "self",
            value=int(float(data.get("value") or 0)), is_percent=int(data.get("is_percent") or 0),
            item_id=0, cooldown=int(data.get("cooldown") or 0), mana_cost=0,
            effect_bonus_bp=int(effect_bonus_bp or 0), buff_type=data.get("buff_type"),
            buff_value=int(data.get("buff_value") or 0), buff_duration=int(data.get("buff_duration") or 0),
            buff_target=target, buff_name=f"本源·{data['skill_name']}", description=data.get("skill_desc", ""),
        ).to_snapshot())
    return skills


async def _build_role_snapshot(uid, cursor):
    await cursor.execute(
        """
        SELECT id,`name`,dengji,gongji,fangyu,qixue,sudu,baoji,baoshang,
               shanbi,mingzhong,pofang,xixue,fali,gongji_jc,fangyu_jc,qixue_jc,
               skill1_id,skill2_id,skill3_id,world
        FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1 FOR UPDATE
        """,
        (uid,),
    )
    row = await cursor.fetchone()
    if not row:
        raise AbyssError("ROLE_REQUIRED", "请先选择一名角色出战。")
    (role_id, role_name, role_level, gongji, fangyu, qixue, sudu, baoji, baoshang,
     shanbi, mingzhong, pofang, xixue, fali, gongji_jc, fangyu_jc, qixue_jc,
     skill1_id, skill2_id, skill3_id, role_world) = row

    from Game_main.g7_equip import calc_role_equip_bonus
    from Game_main.g14_estate import read_estate_levels, scripture_skill_effect_bonus_bp
    from Game_main.g15_expedition import get_causal_mark_snapshot
    from Game_main.g19_sect import get_active_research
    from Game_main.g21_season import get_active_season_effect
    from Game_main.g6_dungeon import apply_solo_pve_stat_effects, solo_pve_effect_snapshot
    from Game_domain.role_special_service import load_battle_special
    from Game_main.g12_spirit_beast import get_active_beast_snapshot

    equip = await calc_role_equip_bonus(role_id, cursor)
    attack = int(gongji * (1 + float(gongji_jc or 0) / 100)) + int(equip.get("gongji", 0))
    defense = int(fangyu * (1 + float(fangyu_jc or 0) / 100)) + int(equip.get("fangyu", 0))
    hp = int(qixue * (1 + float(qixue_jc or 0) / 100)) + int(equip.get("qixue", 0))
    wang_lin_trait = await has_owned_role(cursor, uid, "王林")
    hp = apply_battle_hp(hp, wang_lin_trait)
    speed = int(sudu) + int(equip.get("sudu", 0))
    estate = await read_estate_levels(uid, cursor, ensure_rows=False)
    causal = await get_causal_mark_snapshot(uid, cursor)
    season = await get_active_season_effect(cursor)
    research = await get_active_research(uid, cursor)
    effects = solo_pve_effect_snapshot(causal, season)
    if wang_lin_trait:
        effects["sources"].append("王林特性：气血 +20%")
    attack, defense, speed = apply_solo_pve_stat_effects(attack, defense, speed, effects)
    skill_bonus = scripture_skill_effect_bonus_bp(estate.get("scripture_library", 1))
    if skill_bonus:
        effects["sources"].append(f"藏经阁 Lv.{estate.get('scripture_library', 1)}")
    if research:
        effects["sources"].append(f"宗门研究·{research['research_type']}")

    role_data = {
        "name": role_name, "qixue": max(1, hp), "gongji": max(1, attack),
        "fangyu": max(1, defense), "sudu": max(1, speed),
        "baoji": int(baoji) + int(equip.get("baoji", 0)),
        "baoshang": int(baoshang) + int(equip.get("baoshang", 0)),
        "shanbi": int(shanbi) + int(equip.get("shanbi", 0)),
        "mingzhong": int(mingzhong) + int(equip.get("mingzhong", 0)),
        "pofang": int(pofang) + int(equip.get("pofang", 0)),
        "xixue": int(xixue) + int(equip.get("xixue", 0)),
        "max_fali": int(fali) + int(equip.get("fali", 0)),
        "pve_effect_snapshot": effects,
    }
    special = await load_battle_special(cursor, uid, role_id, role_name)
    if special:
        role_data["role_special"] = special
    beast = await get_active_beast_snapshot(uid, cursor, role_id)
    skills = await _load_player_skills(
        cursor, uid, role_id, role_name, (skill1_id, skill2_id, skill3_id), skill_bonus
    )
    return {
        "schema_version": 1,
        "role_id": int(role_id), "name": role_name, "level": int(role_level), "world": role_world,
        "role_data": role_data, "skills": skills, "spirit_beast": beast,
        "required_exp": required_exp(int(role_level)),
    }, effects


async def _load_monster_templates(cursor, dungeon_id):
    await cursor.execute(
        """
        SELECT id,name,type,description,hp_ratio,atk_ratio,def_ratio,spd_ratio,
               crit_ratio,crit_dmg_ratio,dodge_ratio,hit_ratio,skill_id,world
        FROM data_monster WHERE dungeon_id = %s ORDER BY id
        """,
        (dungeon_id,),
    )
    keys = ("id", "name", "type", "description", "hp_ratio", "atk_ratio", "def_ratio", "spd_ratio",
            "crit_ratio", "crit_dmg_ratio", "dodge_ratio", "hit_ratio", "skill_id", "world")
    rows = [dict(zip(keys, row)) for row in await cursor.fetchall()]
    return [row for row in rows if row["type"] == "normal"], [row for row in rows if row["type"] == "boss"]


async def _generate_wave(cursor, run, role_world):
    await cursor.execute(
        "SELECT COUNT(*) FROM abyss_run_monster WHERE run_uuid = %s AND wave_no = %s",
        (run["run_uuid"], run["wave_no"]),
    )
    if int((await cursor.fetchone())[0]) >= 5:
        return
    normals, bosses = await _load_monster_templates(cursor, run["source_dungeon_id"])
    selected = select_wave_templates(normals, bosses, rng_seed=run["rng_seed"], wave_no=run["wave_no"])
    cross_world = role_world != run["source_world"]
    for slot, monster in enumerate(selected, 1):
        snapshot = {
            "schema_version": 1,
            "source": {key: float(value) if key.endswith("ratio") and value is not None else value for key, value in monster.items()},
            "stats": build_abyss_monster_stats(run["layer_no"], monster, cross_world=cross_world),
            "cross_world": cross_world,
        }
        await cursor.execute(
            """
            INSERT IGNORE INTO abyss_run_monster
                (run_uuid,wave_no,slot_no,source_monster_id,monster_name,monster_type,monster_snapshot_json,state)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'READY')
            """,
            (run["run_uuid"], run["wave_no"], slot, int(monster["id"]), monster["name"],
             monster["type"], _dumps(snapshot)),
        )


async def start_run(uid, run_type="NORMAL", layer_no=None):
    preview = await create_preview(uid, layer_no, run_type)
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT id FROM user_zt WHERE id = %s FOR UPDATE", (uid,))
                await cursor.fetchone()
                run = await get_active_run(uid, cursor, lock=True)
                if not run or run["run_uuid"] != preview["run_uuid"]:
                    raise AbyssError("RUN_NOT_FOUND", "深渊预览已失效，请重新预览。")
                if run["state"] != "READY":
                    return run
                from Game_main.g11_battle import get_battle_service
                if await get_battle_service().get_active_battle(uid):
                    raise AbyssError("BATTLE_ACTIVE", "你已有进行中的回合战斗，请先完成当前战斗。")
                role_snapshot, effects = await _build_role_snapshot(uid, cursor)
                if run["run_type"] == "PLACEMENT":
                    target = placement_target(role_snapshot["level"])
                    if target != run["layer_no"]:
                        raise AbyssError("PLACEMENT_CHANGED", "出战角色等级已变化，请重新确认定级赛。")
                reward_snapshot = {
                    "required_exp": int(role_snapshot["required_exp"]),
                    "role_level": int(role_snapshot["level"]),
                }
                await cursor.execute(
                    """
                    UPDATE abyss_run SET role_id=%s,state='FIGHTING',wave_no=1,kill_count=0,
                        player_hp_ratio=1,role_snapshot_json=%s,effect_snapshot_json=%s,
                        reward_snapshot_json=%s,version=version+1
                    WHERE run_uuid=%s AND state='READY'
                    """,
                    (role_snapshot["role_id"], _dumps(role_snapshot), _dumps(effects),
                     _dumps(reward_snapshot), run["run_uuid"]),
                )
                if cursor.rowcount != 1:
                    raise AbyssError("RUN_CHANGED", "深渊状态已变化，请重新查看。")
                run = await get_active_run(uid, cursor, lock=True)
                await _generate_wave(cursor, run, role_snapshot["world"])
                await conn.commit()
                return await get_active_run(uid)
        except Exception:
            await conn.rollback()
            raise


async def get_run_monsters(run_uuid, wave_no=None, cursor=None):
    async def _query(cur):
        sql = """
            SELECT id,wave_no,slot_no,source_monster_id,monster_name,monster_type,
                   monster_snapshot_json,state,battle_uuid
            FROM abyss_run_monster WHERE run_uuid = %s
        """
        params = [run_uuid]
        if wave_no is not None:
            sql += " AND wave_no = %s"
            params.append(int(wave_no))
        sql += " ORDER BY wave_no,slot_no"
        await cur.execute(sql, tuple(params))
        return [{
            "id": int(row[0]), "wave_no": int(row[1]), "slot_no": int(row[2]),
            "source_monster_id": int(row[3]), "name": row[4], "type": row[5],
            "snapshot": _loads(row[6], {}), "state": row[7], "battle_uuid": row[8],
        } for row in await cur.fetchall()]
    if cursor is not None:
        return await _query(cursor)
    async with connect_mysql() as conn:
        async with conn.cursor() as cur:
            return await _query(cur)


async def start_monster_battle(uid, slot_no):
    try:
        slot_no = int(slot_no)
    except (TypeError, ValueError) as exc:
        raise AbyssError("MONSTER_INVALID", "怪物编号应为1至5。") from exc
    if slot_no not in range(1, 6):
        raise AbyssError("MONSTER_INVALID", "怪物编号应为1至5。")
    from Game_main.g11_battle import get_battle_service
    service = get_battle_service()
    active = await service.get_active_battle(uid)
    if active:
        if active.battle_type == "ABYSS":
            return active
        raise AbyssError("BATTLE_ACTIVE", "你已有其他进行中的回合战斗，请先完成当前战斗。")

    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                run = await get_active_run(uid, cursor, lock=True)
                if not run or run["state"] not in ("FIGHTING", "QUALIFIED"):
                    raise AbyssError("RUN_NOT_FIGHTING", "当前没有可继续的深渊挑战。")
                await cursor.execute(
                    """
                    SELECT id,monster_name,monster_type,monster_snapshot_json,state,battle_uuid
                    FROM abyss_run_monster
                    WHERE run_uuid=%s AND wave_no=%s AND slot_no=%s FOR UPDATE
                    """,
                    (run["run_uuid"], run["wave_no"], slot_no),
                )
                row = await cursor.fetchone()
                if not row:
                    raise AbyssError("MONSTER_NOT_FOUND", "该怪物尚未生成。")
                monster_id, monster_name, monster_type, snapshot_raw, state, battle_uuid = row
                if state == "DEFEATED":
                    raise AbyssError("MONSTER_DEFEATED", "该怪物已经被击败，请选择其他目标。")
                if state == "FIGHTING" and battle_uuid:
                    session = await service.get_battle(battle_uuid, uid)
                    await conn.commit()
                    return session

                role_snapshot = run["role_snapshot"]
                role_data = copy.deepcopy(role_snapshot["role_data"])
                player = CombatEntity(
                    role_snapshot["name"], role_data,
                    [Skill.from_snapshot(data) for data in role_snapshot.get("skills", [])],
                )
                max_hp = max(1, int(role_data["qixue"]))
                inherited = max(0.0, min(1.0, float(run["player_hp_ratio"])))
                player.hp = min(max_hp, max(int(max_hp * inherited), int(max_hp * 0.3)))
                from Game_main.g12_spirit_beast import apply_beast_snapshot_to_entity
                apply_beast_snapshot_to_entity(role_snapshot.get("spirit_beast"), player)

                monster_snapshot = _loads(snapshot_raw, {})
                monster_data = copy.deepcopy(monster_snapshot["stats"])
                monster_data["entity_type"] = monster_type
                monster_skills = []
                source = monster_snapshot.get("source", {})
                if monster_type == "boss" and source.get("skill_id"):
                    from Game_main.g6_dungeon import create_monster_skill, get_boss_mechanics
                    skill = await create_monster_skill(source["skill_id"])
                    if skill:
                        monster_skills.append(skill)
                    mechanics = await get_boss_mechanics(cursor, run["source_dungeon_id"], monster_name)
                    if mechanics:
                        monster_data["boss_mechanics"] = mechanics
                monster = CombatEntity(monster_name, monster_data, monster_skills)
                manager = CombatManager(player, monster, max_rounds=50)
                session = await service.create_battle(
                    uid=uid, manager=manager, battle_type="ABYSS",
                    metadata={
                        "participants": [uid], "run_uuid": run["run_uuid"],
                        "abyss_monster_id": int(monster_id), "wave_no": run["wave_no"],
                        "slot_no": slot_no, "monster_name": monster_name, "monster_type": monster_type,
                    },
                )
                await cursor.execute(
                    "UPDATE abyss_run_monster SET state='FIGHTING',battle_uuid=%s WHERE id=%s AND state='READY'",
                    (session.battle_id, monster_id),
                )
                if cursor.rowcount != 1:
                    raise AbyssError("MONSTER_CHANGED", "怪物状态已变化，请重新查看。")
                await conn.commit()
                return session
        except Exception:
            await conn.rollback()
            raise


async def _claim_reward(cursor, business_key, uid, reward_type, amount, run_uuid, layer_no):
    if int(amount or 0) <= 0:
        return False
    await cursor.execute(
        """
        INSERT IGNORE INTO reward_ledger
            (business_key,uid,reward_type,amount,source_type,source_id,status,payload_json)
        VALUES (%s,%s,%s,%s,'ABYSS',%s,'GRANTED',%s)
        """,
        (business_key, uid, reward_type, int(amount), run_uuid, _dumps({"layer_no": layer_no})),
    )
    return cursor.rowcount == 1


async def _settle_run_in_transaction(cursor, run, conn=None):
    stars = abyss_rating(run["kill_count"])
    if stars <= 0:
        raise AbyssError("NOT_QUALIFIED", "至少击败10只怪物才能结算本层。")
    await cursor.execute(
        "UPDATE abyss_run SET state='SETTLING' WHERE run_uuid=%s AND state IN ('FIGHTING','QUALIFIED','SETTLING')",
        (run["run_uuid"],),
    )
    required = int(run.get("reward_snapshot", {}).get("required_exp", 0))
    layers = range(1, run["layer_no"] + 1) if run["run_type"] == "PLACEMENT" else (run["layer_no"],)
    total_exp = total_lingshi = total_xianyu = 0
    rewarded_layers = 0
    for layer_no in layers:
        await cursor.execute(
            """
            INSERT IGNORE INTO user_abyss_layer_record (uid,layer_no)
            VALUES (%s,%s)
            """,
            (run["uid"], layer_no),
        )
        await cursor.execute(
            """
            SELECT best_stars,best_kills,exp_rewarded,rewarded_stars
            FROM user_abyss_layer_record WHERE uid=%s AND layer_no=%s FOR UPDATE
            """,
            (run["uid"], layer_no),
        )
        _, _, exp_rewarded, rewarded_stars = await cursor.fetchone()
        delta = calculate_reward_delta(
            required, layer_no, int(rewarded_stars), stars, exp_rewarded=bool(exp_rewarded)
        )
        applied_any = False
        if delta["exp"] and await _claim_reward(
            cursor, f"abyss:{run['uid']}:{layer_no}:exp", run["uid"], "EXP",
            delta["exp"], run["run_uuid"], layer_no,
        ):
            total_exp += delta["exp"]
            applied_any = True
        credited_lingshi = await calculate_lingshi_output(
            cursor, run["uid"], delta["lingshi"]
        )
        if credited_lingshi and await _claim_reward(
            cursor, f"abyss:{run['uid']}:{layer_no}:lingshi:star:{stars}", run["uid"], "LINGSHI",
            credited_lingshi, run["run_uuid"], layer_no,
        ):
            total_lingshi += credited_lingshi
            applied_any = True
        if delta["xianyu"] and await _claim_reward(
            cursor, f"abyss:{run['uid']}:{layer_no}:xianyu:star:{stars}", run["uid"], "XIANYU",
            delta["xianyu"], run["run_uuid"], layer_no,
        ):
            total_xianyu += delta["xianyu"]
            applied_any = True
        if applied_any:
            rewarded_layers += 1
        await cursor.execute(
            """
            UPDATE user_abyss_layer_record SET
                best_stars=GREATEST(best_stars,%s),best_kills=GREATEST(best_kills,%s),
                clear_count=clear_count+1,
                exp_rewarded=1,
                rewarded_stars=GREATEST(rewarded_stars,%s),
                first_cleared_at=COALESCE(first_cleared_at,NOW())
            WHERE uid=%s AND layer_no=%s
            """,
            (stars, run["kill_count"], stars, run["uid"], layer_no),
        )

    level_before = level_after = None
    if total_exp:
        await cursor.execute(
            """
            SELECT id,`name`,dengji,exp,gongji,fangyu,qixue,
                   baoji,baoshang,mingzhong,shanbi,pofang,xixue
            FROM user_role WHERE id=%s AND uid=%s LIMIT 1 FOR UPDATE
            """,
            (run["role_id"], run["uid"]),
        )
        role = await cursor.fetchone()
        if not role:
            raise AbyssError("ROLE_MISSING", "参赛角色不存在，深渊奖励尚未发放。")
        progress = await MySQLRewardService().apply_experience(cursor, role, total_exp)
        level_before, level_after = int(role[2]), int(progress["level"])
        if conn is not None and level_after != level_before:
            from Tool.tool_power import update_role_power
            await update_role_power(conn, run["uid"])
    await cursor.execute(
        "UPDATE user_zt SET lingshi=lingshi+%s,xianyu=xianyu+%s WHERE id=%s",
        (total_lingshi, total_xianyu, run["uid"]),
    )
    await cursor.execute(
        """
        INSERT INTO user_abyss_profile (uid,highest_cleared_layer,total_kills)
        VALUES (%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            highest_cleared_layer=GREATEST(highest_cleared_layer,VALUES(highest_cleared_layer)),
            total_kills=total_kills+VALUES(total_kills)
        """,
        (run["uid"], run["layer_no"], run["kill_count"]),
    )
    settlement = {
        "run_uuid": run["run_uuid"], "run_type": run["run_type"], "layer_no": run["layer_no"],
        "stars": stars, "kills": run["kill_count"], "rewarded_layers": rewarded_layers,
        "exp": total_exp, "lingshi": total_lingshi, "xianyu": total_xianyu,
        "level_before": level_before, "level_after": level_after,
    }
    await cursor.execute(
        """
        UPDATE abyss_run SET state='SETTLED',settlement_json=%s,settled_at=NOW(),version=version+1
        WHERE run_uuid=%s AND state='SETTLING'
        """,
        (_dumps(settlement), run["run_uuid"]),
    )
    if cursor.rowcount != 1:
        raise AbyssError("SETTLEMENT_CHANGED", "结算状态已变化，请重新查看深渊。")
    return settlement


async def settle_run(uid):
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                run = await get_active_run(uid, cursor, lock=True)
                if not run:
                    raise AbyssError("RUN_NOT_FOUND", "当前没有可结算的深渊挑战。")
                settlement = await _settle_run_in_transaction(cursor, run, conn)
                await conn.commit()
                return settlement
        except Exception:
            await conn.rollback()
            raise


async def settle_finished_battle(uid, session):
    if session.battle_type != "ABYSS":
        raise AbyssError("BATTLE_TYPE_INVALID", "该战斗不属于轮海深渊。")
    run_uuid = session.metadata.get("run_uuid")
    monster_id = session.metadata.get("abyss_monster_id")
    if not run_uuid or not monster_id:
        raise AbyssError("BATTLE_METADATA_MISSING", "战斗缺少深渊结算信息。")
    manager = CombatManager.from_snapshot(session.snapshot)
    won = manager.winner == manager.player or (session.result or {}).get("winner") == manager.player.name
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                run = await get_active_run(uid, cursor, lock=True)
                if not run or run["run_uuid"] != run_uuid:
                    await cursor.execute("SELECT settlement_json,state FROM abyss_run WHERE run_uuid=%s AND uid=%s", (run_uuid, uid))
                    terminal = await cursor.fetchone()
                    if terminal and terminal[0]:
                        await conn.commit()
                        return {"kind": "settled", "settlement": _loads(terminal[0], {})}
                    raise AbyssError("RUN_NOT_FOUND", "本次深渊挑战已结束。")
                await cursor.execute(
                    "SELECT state FROM abyss_run_monster WHERE id=%s AND run_uuid=%s FOR UPDATE",
                    (monster_id, run_uuid),
                )
                monster_row = await cursor.fetchone()
                if not monster_row:
                    raise AbyssError("MONSTER_NOT_FOUND", "深渊怪物记录不存在。")
                if monster_row[0] in ("DEFEATED", "SURVIVED"):
                    await conn.commit()
                    return {"kind": "progress", "run": run, "notice": "该场战斗已经结算。"}

                if won:
                    hp_ratio = max(0.0, manager.player.hp / max(1, manager.player.max_hp))
                    next_ratio = min(1.0, hp_ratio + 0.30)
                    # 灵阵在开层时已冻结；每只怪物之间只恢复主契30%灵体，
                    # 不重新读取玩家实时养成或换阵结果。
                    beast_snapshot = run["role_snapshot"].get("spirit_beast") or {}
                    battle_beast = manager.spirit_beast or {}
                    body = battle_beast.get("spirit_body") or beast_snapshot.get("spirit_body") or {}
                    if body:
                        maximum = max(1, int(body.get("maximum", 1)))
                        current = min(
                            maximum,
                            int(body.get("current", maximum)) + int(maximum * 0.30),
                        )
                        beast_snapshot["spirit_body"] = {
                            "maximum": maximum, "current": current,
                        }
                        beast_snapshot["retreated"] = current <= 0
                        run["role_snapshot"]["spirit_beast"] = beast_snapshot
                    kills = min(ABYSS_MAX_KILLS, run["kill_count"] + 1)
                    await cursor.execute(
                        "UPDATE abyss_run_monster SET state='DEFEATED',defeated_at=NOW() WHERE id=%s AND state='FIGHTING'",
                        (monster_id,),
                    )
                    await cursor.execute(
                        """
                        UPDATE abyss_run SET kill_count=%s,player_hp_ratio=%s,
                            role_snapshot_json=%s,state=%s,version=version+1
                        WHERE run_uuid=%s
                        """,
                        (
                            kills, next_ratio, _dumps(run["role_snapshot"]),
                            "QUALIFIED" if kills >= 10 else "FIGHTING", run_uuid,
                        ),
                    )
                    run["kill_count"] = kills
                    run["player_hp_ratio"] = next_ratio
                    run["state"] = "QUALIFIED" if kills >= 10 else "FIGHTING"
                    if kills >= ABYSS_MAX_KILLS:
                        settlement = await _settle_run_in_transaction(cursor, run, conn)
                        await conn.commit()
                        from Game_main.g33_spirit_beast_v2 import record_spirit_beast_pve
                        await record_spirit_beast_pve(
                            uid, run["role_id"], source="ABYSS"
                        )
                        return {"kind": "settled", "settlement": settlement}
                    await cursor.execute(
                        "SELECT COUNT(*) FROM abyss_run_monster WHERE run_uuid=%s AND wave_no=%s AND state='DEFEATED'",
                        (run_uuid, run["wave_no"]),
                    )
                    if int((await cursor.fetchone())[0]) == 5:
                        run["wave_no"] += 1
                        await cursor.execute(
                            "UPDATE abyss_run SET wave_no=%s WHERE run_uuid=%s",
                            (run["wave_no"], run_uuid),
                        )
                        await _generate_wave(cursor, run, run["role_snapshot"]["world"])
                    await conn.commit()
                    from Game_main.g33_spirit_beast_v2 import record_spirit_beast_pve
                    await record_spirit_beast_pve(
                        uid, run["role_id"], source="ABYSS"
                    )
                    return {"kind": "progress", "run": run, "notice": f"已击败{escape(manager.enemy.name)}，本层累计{kills}杀。"}

                await cursor.execute(
                    "UPDATE abyss_run_monster SET state='SURVIVED' WHERE id=%s AND state='FIGHTING'",
                    (monster_id,),
                )
                if abyss_rating(run["kill_count"]) > 0:
                    settlement = await _settle_run_in_transaction(cursor, run, conn)
                    await conn.commit()
                    return {"kind": "settled", "settlement": settlement, "defeated": True}
                await cursor.execute(
                    """
                    INSERT INTO user_abyss_profile (uid,total_kills) VALUES (%s,%s)
                    ON DUPLICATE KEY UPDATE total_kills=total_kills+VALUES(total_kills)
                    """,
                    (uid, run["kill_count"]),
                )
                failure = {"layer_no": run["layer_no"], "kills": run["kill_count"], "stars": 0}
                await cursor.execute(
                    "UPDATE abyss_run SET state='FAILED',settlement_json=%s,settled_at=NOW() WHERE run_uuid=%s",
                    (_dumps(failure), run_uuid),
                )
                await conn.commit()
                return {"kind": "failed", "failure": failure}
        except Exception:
            await conn.rollback()
            raise


async def recover_finished_battle(uid):
    run = await get_active_run(uid)
    if not run or run["state"] not in ("FIGHTING", "QUALIFIED"):
        return None
    monsters = await get_run_monsters(run["run_uuid"], run["wave_no"])
    fighting = next((item for item in monsters if item["state"] == "FIGHTING" and item["battle_uuid"]), None)
    if not fighting:
        return None
    session = await MySQLBattleRepository().get_session(fighting["battle_uuid"])
    if session and session.state == STATE_FINISHED:
        return await settle_finished_battle(uid, session)
    return None


async def abandon_run(uid):
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                run = await get_active_run(uid, cursor, lock=True)
                if not run:
                    raise AbyssError("RUN_NOT_FOUND", "当前没有进行中的深渊挑战。")
                if run["state"] == "QUALIFIED":
                    raise AbyssError("RUN_QUALIFIED", "本层已经达到通关线，请先结算奖励。")
                await cursor.execute(
                    "SELECT 1 FROM abyss_run_monster WHERE run_uuid=%s AND state='FIGHTING' LIMIT 1",
                    (run["run_uuid"],),
                )
                if await cursor.fetchone():
                    raise AbyssError("BATTLE_ACTIVE", "回合战斗尚未结束，当前不能离开深渊。")
                await cursor.execute(
                    "UPDATE abyss_run SET state='ABANDONED',settled_at=NOW() WHERE run_uuid=%s",
                    (run["run_uuid"],),
                )
                if run["kill_count"]:
                    await cursor.execute(
                        """
                        INSERT INTO user_abyss_profile (uid,total_kills) VALUES (%s,%s)
                        ON DUPLICATE KEY UPDATE total_kills=total_kills+VALUES(total_kills)
                        """,
                        (uid, run["kill_count"]),
                    )
                await conn.commit()
                return run
        except Exception:
            await conn.rollback()
            raise


async def get_leaderboard(uid, page=1, page_size=10):
    try:
        page = max(1, int(page or 1))
    except (TypeError, ValueError):
        page = 1
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT p.uid,z.`name`,p.highest_cleared_layer,p.total_kills,
                       COALESCE(l.best_stars,0),l.first_cleared_at
                FROM user_abyss_profile p
                JOIN user_zt z ON z.id=p.uid
                LEFT JOIN user_abyss_layer_record l
                  ON l.uid=p.uid AND l.layer_no=p.highest_cleared_layer
                WHERE p.highest_cleared_layer > 0
                ORDER BY p.highest_cleared_layer DESC,COALESCE(l.best_stars,0) DESC,
                         p.total_kills DESC,l.first_cleared_at ASC,p.uid ASC
                """
            )
            rows = await cursor.fetchall()
    ranking = [{
        "rank": index, "uid": int(row[0]), "name": row[1], "layer": int(row[2]),
        "kills": int(row[3]), "stars": int(row[4]),
    } for index, row in enumerate(rows, 1)]
    total = len(ranking)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    mine = next((item for item in ranking if item["uid"] == int(uid)), None)
    start = (page - 1) * page_size
    return {"rows": ranking[start:start + page_size], "page": page, "total_pages": total_pages, "total": total, "mine": mine}
