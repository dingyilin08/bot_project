# -*- coding: utf-8 -*-
"""角色专属战斗养成服务：事务、保底、材料账本和战斗装配。"""

import json
import random
import re
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import NAMESPACE_URL, uuid4, uuid5

from sql.mysql import connect_mysql
from Game_domain.role_special_catalog import get_role_spec


PRAY_COST = 160
DAILY_PRAY_LIMIT = 10
DAILY_DROP_LIMIT = 3
POOL_VERSION = "v1"


class RoleSpecialError(Exception):
    pass


def _json(value, default=None):
    if value is None:
        return {} if default is None else default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {} if default is None else default


def _growth_code(spec: Dict) -> str:
    return f"ROLE_{spec['template_id']}_GROWTH"


def _material_codes(spec: Dict) -> Dict[str, str]:
    prefix = f"ROLE_{spec['template_id']}"
    return {"growth": f"{prefix}_GROWTH", "essence": f"{prefix}_ESSENCE", "core": f"{prefix}_CORE"}


async def _active_role(cursor, uid: int, lock: bool = False) -> Tuple[int, int, str]:
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        """SELECT ur.id, dr.id, ur.name
           FROM user_role ur JOIN data_role dr ON dr.name = ur.name
           WHERE ur.uid = %s AND ur.is_chuzhan = 1 LIMIT 1""" + suffix,
        (uid,),
    )
    row = await cursor.fetchone()
    if not row:
        raise RoleSpecialError("当前没有出战角色，请先选择出战角色。")
    if not get_role_spec(row[2]):
        raise RoleSpecialError(f"{row[2]}尚未开放角色专属养成。")
    return int(row[0]), int(row[1]), row[2]


async def _ensure_progress(cursor, uid: int, role_id: int, template_id: int, role_name: str) -> None:
    spec = get_role_spec(role_name)
    await cursor.execute(
        """INSERT IGNORE INTO user_role_special_progress
           (uid, role_id, role_template_id, role_name, growth_code, growth_stage, growth_value)
           VALUES (%s, %s, %s, %s, %s, 1, 0)""",
        (uid, role_id, template_id, role_name, _growth_code(spec)),
    )
    await cursor.execute(
        """INSERT IGNORE INTO role_special_pity
           (uid, role_id, pool_version) VALUES (%s, %s, %s)""",
        (uid, role_id, POOL_VERSION),
    )


async def _material_balance(cursor, uid: int, role_id: int, code: str, lock: bool = False) -> int:
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        "SELECT amount FROM user_role_special_material WHERE uid=%s AND role_id=%s AND material_code=%s" + suffix,
        (uid, role_id, code),
    )
    row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def _change_material(cursor, *, request_id: str, battle_id: Optional[str], uid: int, role_id: int,
                           code: str, amount: int, source: str) -> int:
    before = await _material_balance(cursor, uid, role_id, code, lock=True)
    after = before + int(amount)
    if after < 0:
        raise RoleSpecialError("专属材料不足。")
    await cursor.execute(
        """INSERT INTO user_role_special_material (uid, role_id, material_code, amount)
           VALUES (%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE amount=VALUES(amount)""",
        (uid, role_id, code, after),
    )
    try:
        await cursor.execute(
            """INSERT INTO role_special_material_ledger
               (request_id,battle_id,uid,role_id,material_code,change_amount,balance_before,balance_after,source_type)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (request_id, battle_id, uid, role_id, code, amount, before, after, source),
        )
    except Exception as exc:
        if getattr(exc, "args", [None])[0] == 1062:
            raise RoleSpecialError("该专属养成请求已经处理。") from exc
        raise
    return after


async def _add_fragments(cursor, *, request_id: str, battle_id: Optional[str], uid: int, role_id: int,
                         collection_id: int, fragment_code: str, amount: int, source: str) -> int:
    await cursor.execute(
        """INSERT IGNORE INTO user_role_special_collection
           (uid,role_id,collection_id,fragment_amount) VALUES (%s,%s,%s,0)""",
        (uid, role_id, collection_id),
    )
    await cursor.execute(
        """SELECT fragment_amount FROM user_role_special_collection
           WHERE uid=%s AND role_id=%s AND collection_id=%s FOR UPDATE""",
        (uid, role_id, collection_id),
    )
    before = int((await cursor.fetchone())[0])
    after = before + int(amount)
    await cursor.execute(
        """UPDATE user_role_special_collection SET fragment_amount=%s
           WHERE uid=%s AND role_id=%s AND collection_id=%s""",
        (after, uid, role_id, collection_id),
    )
    try:
        await cursor.execute(
            """INSERT INTO role_special_material_ledger
               (request_id,battle_id,uid,role_id,material_code,change_amount,balance_before,balance_after,source_type)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (request_id, battle_id, uid, role_id, fragment_code, amount, before, after, source),
        )
    except Exception as exc:
        if getattr(exc, "args", [None])[0] == 1062:
            raise RoleSpecialError("该专属材料已经结算。") from exc
        raise
    return after


async def home(uid: int) -> Dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                """SELECT p.growth_stage,p.growth_value,p.daily_drop_date,p.daily_drop_count,
                          a.name,b.name,pt.rare_pity_count,pt.target_miss_count,pt.daily_pray_date,pt.daily_pray_count
                   FROM user_role_special_progress p
                   LEFT JOIN role_special_collection_config a ON a.id=p.active_skill_id
                   LEFT JOIN role_special_collection_config b ON b.id=p.active_passive_id
                   JOIN role_special_pity pt ON pt.uid=p.uid AND pt.role_id=p.role_id AND pt.pool_version=%s
                   WHERE p.uid=%s AND p.role_id=%s""",
                (POOL_VERSION, uid, role_id),
            )
            row = await cursor.fetchone()
            await cursor.execute(
                """SELECT COUNT(*) FROM user_role_special_collection
                   WHERE uid=%s AND role_id=%s AND unlocked=1""", (uid, role_id),
            )
            unlocked = int((await cursor.fetchone())[0])
            await cursor.execute(
                "SELECT COUNT(*) FROM role_special_collection_config WHERE role_template_id=%s AND enabled=1",
                (template_id,),
            )
            total = int((await cursor.fetchone())[0])
            await cursor.execute(
                "SELECT material_code,amount FROM user_role_special_material WHERE uid=%s AND role_id=%s",
                (uid, role_id),
            )
            materials = {code: int(amount) for code, amount in await cursor.fetchall()}
            await conn.commit()
    spec = get_role_spec(role_name)
    today = date.today()
    return {
        "role_id": role_id, "template_id": template_id, "role_name": role_name, "spec": spec,
        "growth_stage": int(row[0]), "growth_value": int(row[1]),
        "daily_drop_count": int(row[3]) if row[2] == today else 0,
        "active_skill": row[4] or "未装备", "active_passive": row[5] or "未装备",
        "rare_pity": int(row[6]), "target_miss": int(row[7]),
        "daily_pray_count": int(row[9]) if row[8] == today else 0,
        "unlocked": unlocked, "total": total, "materials": materials,
    }


async def collection(uid: int) -> Dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                """SELECT c.id,c.collection_code,c.name,c.rarity,c.fragment_cost,c.skill_type,
                          c.skill_multiplier,c.effect_json,c.lore_desc,
                          COALESCE(u.fragment_amount,0),COALESCE(u.unlocked,0),u.equipped_slot
                   FROM role_special_collection_config c
                   LEFT JOIN user_role_special_collection u
                     ON u.collection_id=c.id AND u.uid=%s AND u.role_id=%s
                   WHERE c.role_template_id=%s AND c.enabled=1
                   ORDER BY c.rarity,c.id""",
                (uid, role_id, template_id),
            )
            rows = await cursor.fetchall()
            await conn.commit()
    return {"role_id": role_id, "role_name": role_name, "spec": get_role_spec(role_name), "items": [
        {"id": int(r[0]), "code": r[1], "name": r[2], "rarity": int(r[3]), "cost": int(r[4]),
         "kind": r[5], "multiplier": float(r[6]), "effect": _json(r[7]), "lore": r[8],
         "fragments": int(r[9]), "unlocked": bool(r[10]), "slot": r[11]} for r in rows
    ]}


async def set_target(uid: int, collection_id: int) -> str:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                "SELECT name,rarity FROM role_special_collection_config WHERE id=%s AND role_template_id=%s AND enabled=1",
                (collection_id, template_id),
            )
            row = await cursor.fetchone()
            if not row or int(row[1]) != 5:
                raise RoleSpecialError("只能定向当前角色奖池中的五星能力。")
            await cursor.execute(
                """UPDATE role_special_pity SET target_collection_id=%s,target_miss_count=0
                   WHERE uid=%s AND role_id=%s AND pool_version=%s""",
                (collection_id, uid, role_id, POOL_VERSION),
            )
            await conn.commit()
    return f"已将五星定向设为「{row[0]}」；十次保底进度保留，定向计数重新开始。"


async def pray(uid: int, count: int) -> Dict:
    if count not in (1, 10):
        raise RoleSpecialError("专属祈愿仅支持 1 次或 10 次。")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute("SELECT lingshi FROM user_zt WHERE id=%s FOR UPDATE", (uid,))
            currency_row = await cursor.fetchone()
            if not currency_row or int(currency_row[0]) < PRAY_COST * count:
                raise RoleSpecialError(f"灵石不足，本次需要 {PRAY_COST * count} 灵石。")
            await cursor.execute(
                """SELECT total_count,rare_pity_count,target_collection_id,target_miss_count,daily_pray_date,daily_pray_count
                   FROM role_special_pity WHERE uid=%s AND role_id=%s AND pool_version=%s FOR UPDATE""",
                (uid, role_id, POOL_VERSION),
            )
            pity = list(await cursor.fetchone())
            today = date.today()
            daily_count = int(pity[5]) if pity[4] == today else 0
            if daily_count + count > DAILY_PRAY_LIMIT:
                raise RoleSpecialError(f"今日专属祈愿剩余 {DAILY_PRAY_LIMIT - daily_count} 次。")
            await cursor.execute(
                """SELECT id,name,rarity,fragment_code FROM role_special_collection_config
                   WHERE role_template_id=%s AND enabled=1 ORDER BY id""", (template_id,),
            )
            pool = await cursor.fetchall()
            four = [r for r in pool if int(r[2]) == 4]
            five = [r for r in pool if int(r[2]) == 5]
            if not four or not five:
                raise RoleSpecialError("当前角色专属奖池尚未配置完整。")
            rng = random.SystemRandom()
            request_root = f"pray:{uuid4()}"
            results = []
            rare_pity = int(pity[1])
            target_id = int(pity[2]) if pity[2] else None
            target_miss = int(pity[3])
            for index in range(count):
                is_five = rare_pity >= 9 or rng.random() < .10
                if is_five:
                    rare_pity = 0
                    if target_id and target_miss >= 2:
                        chosen = next((r for r in five if int(r[0]) == target_id), rng.choice(five))
                    else:
                        chosen = rng.choice(five)
                    if target_id:
                        target_miss = 0 if int(chosen[0]) == target_id else target_miss + 1
                    amount = 10
                else:
                    rare_pity += 1
                    chosen = rng.choice(four)
                    amount = 5
                balance = await _add_fragments(
                    cursor, request_id=f"{request_root}:{index}", battle_id=None, uid=uid, role_id=role_id,
                    collection_id=int(chosen[0]), fragment_code=chosen[3], amount=amount, source="PRAY",
                )
                results.append({"id": int(chosen[0]), "name": chosen[1], "rarity": int(chosen[2]), "amount": amount, "balance": balance})
            await cursor.execute("UPDATE user_zt SET lingshi=lingshi-%s WHERE id=%s", (PRAY_COST * count, uid))
            await cursor.execute(
                """UPDATE role_special_pity SET total_count=total_count+%s,rare_pity_count=%s,
                   target_miss_count=%s,daily_pray_date=%s,daily_pray_count=%s
                   WHERE uid=%s AND role_id=%s AND pool_version=%s""",
                (count, rare_pity, target_miss, today, daily_count + count, uid, role_id, POOL_VERSION),
            )
            await conn.commit()
    return {"role_name": role_name, "results": results, "rare_pity": rare_pity, "target_miss": target_miss,
            "daily_count": daily_count + count, "cost": PRAY_COST * count}


async def unlock(uid: int, collection_id: int) -> str:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                """SELECT c.name,c.fragment_cost,c.effect_json,COALESCE(u.fragment_amount,0),COALESCE(u.unlocked,0)
                   FROM role_special_collection_config c
                   LEFT JOIN user_role_special_collection u ON u.collection_id=c.id AND u.uid=%s AND u.role_id=%s
                   WHERE c.id=%s AND c.role_template_id=%s AND c.enabled=1 FOR UPDATE""",
                (uid, role_id, collection_id, template_id),
            )
            row = await cursor.fetchone()
            if not row:
                raise RoleSpecialError("能力编号不存在。")
            if row[4]:
                return f"「{row[0]}」已经点亮。"
            if int(row[3]) < int(row[1]):
                raise RoleSpecialError(f"「{row[0]}」残片不足：{row[3]}/{row[1]}。")
            await cursor.execute(
                """INSERT INTO user_role_special_collection
                   (uid,role_id,collection_id,fragment_amount,unlocked,unlocked_at,effect_snapshot_json)
                   VALUES (%s,%s,%s,%s,1,NOW(),%s)
                   ON DUPLICATE KEY UPDATE fragment_amount=fragment_amount-%s,unlocked=1,unlocked_at=NOW(),effect_snapshot_json=VALUES(effect_snapshot_json)""",
                (uid, role_id, collection_id, int(row[3]) - int(row[1]), json.dumps(_json(row[2]), ensure_ascii=False), int(row[1])),
            )
            await conn.commit()
    return f"成功点亮「{row[0]}」，现已永久进入{get_role_spec(role_name)['drop_name']}图鉴。"


async def equip(uid: int, collection_id: int) -> str:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                """SELECT c.name,c.skill_type,u.unlocked FROM role_special_collection_config c
                   JOIN user_role_special_collection u ON u.collection_id=c.id AND u.uid=%s AND u.role_id=%s
                   WHERE c.id=%s AND c.role_template_id=%s FOR UPDATE""",
                (uid, role_id, collection_id, template_id),
            )
            row = await cursor.fetchone()
            if not row or not row[2]:
                raise RoleSpecialError("该能力尚未点亮。")
            slot = "ACTIVE" if row[1] == "ACTIVE" else "PASSIVE"
            await cursor.execute(
                "UPDATE user_role_special_collection SET equipped_slot=NULL WHERE uid=%s AND role_id=%s AND equipped_slot=%s",
                (uid, role_id, slot),
            )
            await cursor.execute(
                "UPDATE user_role_special_collection SET equipped_slot=%s WHERE uid=%s AND role_id=%s AND collection_id=%s",
                (slot, uid, role_id, collection_id),
            )
            field = "active_skill_id" if slot == "ACTIVE" else "active_passive_id"
            await cursor.execute(
                f"UPDATE user_role_special_progress SET {field}=%s WHERE uid=%s AND role_id=%s",
                (collection_id, uid, role_id),
            )
            await conn.commit()
    return f"已将「{row[0]}」装备到专属{'主动' if slot == 'ACTIVE' else '被动'}槽。"


async def advance(uid: int) -> str:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                "SELECT growth_stage FROM user_role_special_progress WHERE uid=%s AND role_id=%s FOR UPDATE",
                (uid, role_id),
            )
            current = int((await cursor.fetchone())[0])
            await cursor.execute(
                """SELECT stage_no,stage_name,cost_json,unlock_condition_json,unlock_effect_json
                   FROM role_growth_stage_config WHERE role_template_id=%s AND stage_no=%s AND enabled=1""",
                (template_id, current + 1),
            )
            stage = await cursor.fetchone()
            if not stage:
                return "该角色的本体专属成长已达到当前最高阶段。"
            condition = _json(stage[3])
            await cursor.execute(
                "SELECT COUNT(*) FROM user_role_special_collection WHERE uid=%s AND role_id=%s AND unlocked=1",
                (uid, role_id),
            )
            unlocked_count = int((await cursor.fetchone())[0])
            if unlocked_count < int(condition.get("unlocked", 0)):
                raise RoleSpecialError(f"需要先点亮 {condition['unlocked']} 种能力，当前为 {unlocked_count} 种。")
            costs = _json(stage[2])
            request_id = f"advance:{uuid4()}"
            for code, amount in costs.items():
                await _change_material(cursor, request_id=request_id, battle_id=None, uid=uid, role_id=role_id,
                                       code=code, amount=-int(amount), source="ADVANCE")
            await cursor.execute(
                "UPDATE user_role_special_progress SET growth_stage=%s,growth_value=growth_value+1 WHERE uid=%s AND role_id=%s",
                (int(stage[0]), uid, role_id),
            )
            await conn.commit()
    return f"{get_role_spec(role_name)['growth_name']}突破至「{stage[1]}」：{', '.join(_json(stage[4]).keys())}。"


def _normalize_name(value: str) -> str:
    value = re.sub(r"\s+", "", str(value or ""))
    if not 2 <= len(value) <= 12:
        raise RoleSpecialError("组合名称需为 2—12 个字符。")
    if re.search(r"[<>\[\]{}'\"]", value):
        raise RoleSpecialError("组合名称包含不允许的字符。")
    return value.casefold()


async def combine(uid: int, ids: Sequence[int], custom_name: str) -> Dict:
    if len(ids) != 3 or len(set(ids)) != 3:
        raise RoleSpecialError("必须选择三种不同且已点亮的能力。")
    normalized = _normalize_name(custom_name)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            spec = get_role_spec(role_name)
            await cursor.execute(
                "SELECT growth_stage FROM user_role_special_progress WHERE uid=%s AND role_id=%s FOR UPDATE",
                (uid, role_id),
            )
            if int((await cursor.fetchone())[0]) < 3:
                raise RoleSpecialError(f"{spec['growth_name']}达到第三阶段后才可进行{spec['combo']['type']}。")
            placeholders = ",".join(["%s"] * 3)
            await cursor.execute(
                f"""SELECT c.id,c.name,c.skill_multiplier,c.effect_json
                    FROM role_special_collection_config c JOIN user_role_special_collection u
                      ON u.collection_id=c.id AND u.uid=%s AND u.role_id=%s AND u.unlocked=1
                    WHERE c.role_template_id=%s AND c.id IN ({placeholders}) ORDER BY FIELD(c.id,{placeholders})""",
                (uid, role_id, template_id, *ids, *ids),
            )
            materials = await cursor.fetchall()
            if len(materials) != 3:
                raise RoleSpecialError("组合材料中存在未点亮或不属于当前角色的能力。")
            await cursor.execute("SELECT COUNT(*) FROM user_role_special_combo WHERE uid=%s AND role_id=%s AND status<>'SEALED'", (uid, role_id))
            if int((await cursor.fetchone())[0]) >= int(spec["combo"]["max_saved"]):
                raise RoleSpecialError("该角色保存的组合能力已达到上限。")
            codes = _material_codes(spec)
            request_id = f"combo:{uuid4()}"
            await _change_material(cursor, request_id=request_id, battle_id=None, uid=uid, role_id=role_id,
                                   code=codes["core"], amount=-int(spec["combo"]["core_cost"]), source="COMBO")
            await _change_material(cursor, request_id=request_id, battle_id=None, uid=uid, role_id=role_id,
                                   code=codes["essence"], amount=-int(spec["combo"]["essence_cost"]), source="COMBO")
            seed = random.SystemRandom().randint(1, 2**63 - 1)
            rng = random.Random(seed)
            values = [float(row[2]) for row in materials]
            multiplier = max(sum(values) / 3, rng.uniform(min(values), min(2.0, max(values) * 1.5)))
            effect_source = rng.choice(materials)
            effect = _json(effect_source[3])
            effect["inherited_from"] = effect_source[1]
            await cursor.execute(
                """INSERT INTO user_role_special_combo
                   (uid,role_id,combo_type,custom_name,normalized_name,material_collection_ids_json,slot_order_json,multiplier,effect_json,seed)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (uid, role_id, spec["combo"]["type"], custom_name, normalized,
                 json.dumps(list(ids)), json.dumps(list(ids)), round(multiplier, 3),
                 json.dumps(effect, ensure_ascii=False), seed),
            )
            combo_id = cursor.lastrowid
            await conn.commit()
    return {"id": int(combo_id), "name": custom_name, "multiplier": round(multiplier, 3),
            "effect": effect, "materials": [row[1] for row in materials]}


async def rank(uid: int) -> Dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            _, template_id, role_name = await _active_role(cursor, uid)
            await cursor.execute(
                """SELECT u.name,c.custom_name,c.multiplier,c.effect_json,c.created_at
                   FROM user_role_special_combo c JOIN user_role ur ON ur.id=c.role_id
                   JOIN user_zt u ON u.id=c.uid
                   WHERE ur.name=%s AND c.status='ACTIVE'
                   ORDER BY c.multiplier DESC,c.created_at ASC LIMIT 10""", (role_name,),
            )
            rows = await cursor.fetchall()
    return {"role_name": role_name, "spec": get_role_spec(role_name), "rows": rows}


async def load_battle_special(cursor, uid: int, role_id: int, role_name: str) -> Optional[Dict]:
    """将已装备主动/被动读入战斗快照，之后战斗断线恢复不再查询配置。"""
    if not get_role_spec(role_name):
        return None
    await cursor.execute(
        """SELECT p.growth_stage,a.id,a.name,a.skill_multiplier,a.effect_json,b.id,b.name,b.effect_json
           FROM user_role_special_progress p
           LEFT JOIN role_special_collection_config a ON a.id=p.active_skill_id
           LEFT JOIN role_special_collection_config b ON b.id=p.active_passive_id
           WHERE p.uid=%s AND p.role_id=%s LIMIT 1""", (uid, role_id),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "role_id": role_id, "role_name": role_name, "growth_stage": int(row[0]),
        "active": None if not row[1] else {"id": int(row[1]), "name": row[2], "multiplier": float(row[3]), "effect": _json(row[4])},
        "passive": None if not row[5] else {"id": int(row[5]), "name": row[6], "effect": _json(row[7])},
    }


async def grant_battle_drop(*, battle_id: str, uid: int, role_id: int, role_name: str, is_boss: bool,
                            special_events: Optional[List[Dict]] = None) -> Optional[Dict]:
    spec = get_role_spec(role_name)
    if not spec:
        return None
    request_id = f"battle:{battle_id}:special"
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT material_code,balance_after FROM role_special_material_ledger WHERE request_id=%s LIMIT 1",
                (request_id,),
            )
            previous = await cursor.fetchone()
            if previous:
                return {"idempotent": True, "material_code": previous[0], "balance": int(previous[1])}
            role_id_db, template_id, active_name = await _active_role(cursor, uid, True)
            if role_id_db != int(role_id) or active_name != role_name:
                return None
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            for event in special_events or []:
                if not event.get("id"):
                    continue
                await cursor.execute(
                    """INSERT IGNORE INTO role_special_battle_log
                       (battle_id,uid,role_id,skill_id,trigger_round,target_id,base_value,multiplier,final_value,effect_result_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (battle_id, uid, role_id, int(event["id"]), int(event.get("round", 0)), "enemy",
                     int(event.get("base_value", 0)), float(event.get("multiplier", 0)),
                     int(event.get("final_value", 0)), json.dumps(event.get("effect", {}), ensure_ascii=False)),
                )
            await cursor.execute(
                "SELECT daily_drop_date,daily_drop_count FROM user_role_special_progress WHERE uid=%s AND role_id=%s FOR UPDATE",
                (uid, role_id),
            )
            row = await cursor.fetchone()
            today = date.today()
            daily_count = int(row[1]) if row[0] == today else 0
            if daily_count >= DAILY_DROP_LIMIT:
                await conn.commit()
                return {"capped": True, "daily_count": daily_count}
            rng = random.Random(str(battle_id))
            chance = .35 if is_boss else .25
            if rng.random() >= chance:
                await conn.commit()
                return {"dropped": False, "daily_count": daily_count}
            await cursor.execute(
                """SELECT id,name,fragment_code FROM role_special_collection_config
                   WHERE role_template_id=%s AND rarity=4 AND enabled=1 ORDER BY id""", (template_id,),
            )
            pool = await cursor.fetchall()
            if not pool:
                return None
            chosen = rng.choice(pool)
            balance = await _add_fragments(
                cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                collection_id=int(chosen[0]), fragment_code=chosen[2], amount=1, source="BOSS_DROP" if is_boss else "BATTLE_DROP",
            )
            if is_boss:
                codes = _material_codes(spec)
                await _change_material(cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                                       code=codes["growth"], amount=1, source="BOSS_GROWTH")
                if rng.random() < .20:
                    await _change_material(cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                                           code=codes["core"], amount=1, source="BOSS_CORE")
            await cursor.execute(
                "UPDATE user_role_special_progress SET daily_drop_date=%s,daily_drop_count=%s WHERE uid=%s AND role_id=%s",
                (today, daily_count + 1, uid, role_id),
            )
            await conn.commit()
    return {"dropped": True, "name": chosen[1], "amount": 1, "balance": balance,
            "daily_count": daily_count + 1, "daily_limit": DAILY_DROP_LIMIT}


async def world_boss_loadout(cursor, uid: int) -> Optional[Dict]:
    try:
        role_id, _, role_name = await _active_role(cursor, uid)
    except RoleSpecialError:
        return None
    special = await load_battle_special(cursor, uid, role_id, role_name)
    if special:
        special["spec"] = get_role_spec(role_name)
    return special


def world_boss_contribution(special: Optional[Dict], combat_power: int, max_hp: int) -> Tuple[int, str]:
    active = (special or {}).get("active")
    if not active:
        raise RoleSpecialError("当前出战角色尚未装备专属主动能力。")
    raw = int(max(1, combat_power) * (1 + float(active["multiplier"])))
    damage = min(int(max_hp * .03), raw)
    return damage, f"{special['role_name']}施展「{active['name']}」"


async def grant_world_insight(*, run_key: str, uid: int) -> Optional[Dict]:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                "SELECT world_insight_key FROM user_role_special_progress WHERE uid=%s AND role_id=%s FOR UPDATE",
                (uid, role_id),
            )
            if (await cursor.fetchone())[0] == run_key:
                return None
            spec = get_role_spec(role_name)
            codes = _material_codes(spec)
            request_id = f"world:{run_key}:{uid}:{role_id}"
            growth = await _change_material(cursor, request_id=request_id, battle_id=run_key, uid=uid, role_id=role_id,
                                            code=codes["growth"], amount=2, source="WORLD_INSIGHT")
            essence = await _change_material(cursor, request_id=request_id, battle_id=run_key, uid=uid, role_id=role_id,
                                             code=codes["essence"], amount=10, source="WORLD_INSIGHT")
            await _change_material(cursor, request_id=request_id, battle_id=run_key, uid=uid, role_id=role_id,
                                   code=codes["core"], amount=1, source="WORLD_INSIGHT")
            await cursor.execute(
                "UPDATE user_role_special_progress SET world_insight_key=%s WHERE uid=%s AND role_id=%s",
                (run_key, uid, role_id),
            )
            await conn.commit()
    return {"role_name": role_name, "growth": growth, "essence": essence}
