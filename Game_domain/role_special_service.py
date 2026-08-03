# -*- coding: utf-8 -*-
"""角色专属战斗养成服务：事务、保底、材料账本和战斗装配。"""

import json
import random
import re
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import NAMESPACE_URL, uuid4, uuid5

import aiomysql

from sql.mysql import connect_mysql
from Game_domain.role_special_catalog import get_role_spec
from Game_domain.role_special_asset_service import (
    RoleSpecialAssetError,
    add_fragments as add_role_special_fragments,
)
from Game_domain.role_special_combo_rules import (
    COMBO_RULE_VERSION,
    apply_combo_to_battle_special,
    build_combo_battle_snapshot,
    normalize_combo_multiplier_bp,
    sanitize_combo_effect,
)


PRAY_COST = 160
DAILY_PRAY_LIMIT = 10
DAILY_DROP_LIMIT = 3
POOL_VERSION = "v1"

_COMBO_EQUIPMENT_SCHEMA_READY = False


class RoleSpecialError(Exception):
    pass


async def ensure_combo_equipment_schema(cursor) -> None:
    """兼容旧组合表；装备列和唯一约束仅在进程首次访问时检查。"""
    global _COMBO_EQUIPMENT_SCHEMA_READY
    if _COMBO_EQUIPMENT_SCHEMA_READY:
        return
    await cursor.execute(
        """
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=DATABASE()
          AND TABLE_NAME=%s AND COLUMN_NAME=%s
        """,
        ("user_role_special_combo", "equipped_slot"),
    )
    row = await cursor.fetchone()
    if not row or int(row[0]) == 0:
        try:
            await cursor.execute(
                "ALTER TABLE user_role_special_combo "
                "ADD COLUMN equipped_slot TINYINT NULL DEFAULT NULL "
                "COMMENT '装备槽：1=当前装备，NULL=未装备' AFTER status"
            )
        except aiomysql.OperationalError as error:
            if not error.args or error.args[0] != 1060:
                raise
    await cursor.execute(
        """
        SELECT COUNT(*) FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA=DATABASE()
          AND TABLE_NAME=%s AND INDEX_NAME=%s
        """,
        ("user_role_special_combo", "uk_role_combo_equipped"),
    )
    row = await cursor.fetchone()
    if not row or int(row[0]) == 0:
        try:
            # MySQL唯一索引允许多行NULL，因而每个角色只能存在一个slot=1。
            await cursor.execute(
                "ALTER TABLE user_role_special_combo "
                "ADD UNIQUE KEY uk_role_combo_equipped (uid,role_id,equipped_slot)"
            )
        except aiomysql.OperationalError as error:
            if not error.args or error.args[0] != 1061:
                raise
    _COMBO_EQUIPMENT_SCHEMA_READY = True


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
    return {
        "growth": spec.get("growth_material_code", f"{prefix}_GROWTH"),
        "essence": spec.get("essence_material_code", f"{prefix}_ESSENCE"),
        "core": spec.get("core_material_code", f"{prefix}_CORE"),
    }


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
    try:
        return await add_role_special_fragments(
            cursor, request_id=request_id, battle_id=battle_id, uid=uid,
            role_id=role_id, collection_id=collection_id,
            fragment_code=fragment_code, amount=amount, source=source,
        )
    except RoleSpecialAssetError as exc:
        raise RoleSpecialError(str(exc)) from exc


def _combo_row_to_snapshot(row) -> Optional[Dict]:
    if not row:
        return None
    return build_combo_battle_snapshot({
        "id": row[0],
        "name": row[1],
        "combo_type": row[2],
        "multiplier": row[3],
        "effect": _json(row[4]),
    })


async def load_equipped_combo(cursor, uid: int, role_id: int) -> Optional[Dict]:
    """只读取当前角色唯一已装备且仍有效的组合，并立即生成规则快照。"""
    try:
        # 战斗创建事务中禁止执行兼容 DDL（ALTER 会隐式提交）。迁移尚未部署时
        # 安全回退为“未装备组合”；组合页面会在任何资产写入前补齐旧表结构。
        await cursor.execute(
            """
            SELECT id,custom_name,combo_type,multiplier,effect_json
            FROM user_role_special_combo
            WHERE uid=%s AND role_id=%s AND status='ACTIVE' AND equipped_slot=1
            LIMIT 1
            """,
            (uid, role_id),
        )
    except aiomysql.OperationalError as error:
        if error.args and error.args[0] == 1054:
            return None
        raise
    return _combo_row_to_snapshot(await cursor.fetchone())


async def home(uid: int) -> Dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_combo_equipment_schema(cursor)
            role_id, template_id, role_name = await _active_role(cursor, uid)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                """SELECT p.growth_stage,p.growth_value,p.daily_drop_date,p.daily_drop_count,
                          a.name,b.name,pt.rare_pity_count,pt.target_miss_count,pt.daily_pray_date,pt.daily_pray_count
                          ,p.preset_json
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
            equipped_combo = await load_equipped_combo(cursor, uid, role_id)
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
        "unlocked": unlocked, "total": total, "materials": materials, "feature": _json(row[10]),
        "equipped_combo": equipped_combo,
    }


async def select_feature(uid: int, feature_id: int) -> str:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            spec = get_role_spec(role_name)
            feature = next((item for item in spec.get("features", []) if int(item["id"]) == int(feature_id)), None)
            if not feature:
                raise RoleSpecialError("当前角色没有该机制编号。")
            await cursor.execute("SELECT growth_stage FROM user_role_special_progress WHERE uid=%s AND role_id=%s FOR UPDATE", (uid, role_id))
            stage = int((await cursor.fetchone())[0])
            if stage < int(feature.get("unlock_stage", 1)):
                raise RoleSpecialError(f"该机制需要角色专属成长达到第{feature['unlock_stage']}阶段。")
            payload = {"feature_id": feature["id"], "feature_name": feature["name"], "effect": feature["effect"]}
            await cursor.execute("UPDATE user_role_special_progress SET preset_json=%s WHERE uid=%s AND role_id=%s",
                                 (json.dumps(payload, ensure_ascii=False), uid, role_id))
            await conn.commit()
    return f"已装备角色机制「{feature['name']}」；同一场只生效一个。"


async def collection(uid: int) -> Dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                """SELECT c.id,c.collection_code,c.name,c.rarity,c.fragment_cost,c.skill_type,
                          c.skill_multiplier,c.effect_json,c.lore_desc,
                          COALESCE(u.fragment_amount,0),COALESCE(u.unlocked,0),u.equipped_slot,c.enabled
                   FROM role_special_collection_config c
                   LEFT JOIN user_role_special_collection u
                     ON u.collection_id=c.id AND u.uid=%s AND u.role_id=%s
                   WHERE c.role_template_id=%s
                   ORDER BY c.rarity,c.id""",
                (uid, role_id, template_id),
            )
            rows = await cursor.fetchall()
            await conn.commit()
    return {"role_id": role_id, "role_name": role_name, "spec": get_role_spec(role_name), "items": [
        {"id": int(r[0]), "code": r[1], "name": r[2], "rarity": int(r[3]), "cost": int(r[4]),
         "kind": r[5], "multiplier": float(r[6]), "effect": _json(r[7]), "lore": r[8],
         "fragments": int(r[9]), "unlocked": bool(r[10]), "slot": r[11], "enabled": bool(r[12])} for r in rows
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


async def list_combos(uid: int) -> Dict:
    """返回当前出战角色的组合背包及唯一装备态。"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_combo_equipment_schema(cursor)
            role_id, _, role_name = await _active_role(cursor, uid)
            await cursor.execute(
                """
                SELECT id,custom_name,combo_type,multiplier,effect_json,
                       equipped_slot,status,created_at
                FROM user_role_special_combo
                WHERE uid=%s AND role_id=%s AND status='ACTIVE'
                ORDER BY (equipped_slot=1) DESC,id DESC
                """,
                (uid, role_id),
            )
            rows = await cursor.fetchall()
            await conn.commit()
    items = []
    for row in rows:
        snapshot = _combo_row_to_snapshot(row)
        items.append({
            "id": int(row[0]),
            "name": row[1],
            "combo_type": row[2],
            "multiplier": snapshot["multiplier"],
            "effect": snapshot["effect"],
            "mode": snapshot["mode"],
            "equipped": int(row[5] or 0) == 1,
            "status": row[6],
            "created_at": row[7],
        })
    return {
        "role_id": role_id,
        "role_name": role_name,
        "spec": get_role_spec(role_name),
        "items": items,
        "rule_version": COMBO_RULE_VERSION,
    }


async def equip_combo(uid: int, combo_id: int) -> Dict:
    """原子切换当前角色组合；重复装备同一组合不产生额外写入。"""
    try:
        combo_id = int(combo_id)
    except (TypeError, ValueError) as exc:
        raise RoleSpecialError("组合编号格式错误。") from exc
    if combo_id <= 0:
        raise RoleSpecialError("组合编号格式错误。")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_combo_equipment_schema(cursor)
            role_id, _, role_name = await _active_role(cursor, uid, True)
            await cursor.execute(
                """
                SELECT id,custom_name,combo_type,multiplier,effect_json,
                       equipped_slot,status
                FROM user_role_special_combo
                WHERE id=%s AND uid=%s AND role_id=%s
                LIMIT 1 FOR UPDATE
                """,
                (combo_id, uid, role_id),
            )
            row = await cursor.fetchone()
            if not row:
                await conn.rollback()
                raise RoleSpecialError("组合不存在，或不属于当前出战角色。")
            if row[6] != "ACTIVE":
                await conn.rollback()
                raise RoleSpecialError("该组合已封存，无法装备。")
            snapshot = _combo_row_to_snapshot(row)
            if int(row[5] or 0) == 1:
                await conn.commit()
                return {
                    "id": combo_id,
                    "name": row[1],
                    "role_name": role_name,
                    "snapshot": snapshot,
                    "idempotent": True,
                }
            await cursor.execute(
                """
                UPDATE user_role_special_combo SET equipped_slot=NULL
                WHERE uid=%s AND role_id=%s AND equipped_slot=1
                """,
                (uid, role_id),
            )
            await cursor.execute(
                """
                UPDATE user_role_special_combo SET equipped_slot=1
                WHERE id=%s AND uid=%s AND role_id=%s
                  AND status='ACTIVE' AND equipped_slot IS NULL
                """,
                (combo_id, uid, role_id),
            )
            if cursor.rowcount != 1:
                await conn.rollback()
                raise RoleSpecialError("组合装备状态已变化，请重新打开组合背包。")
            await conn.commit()
    return {
        "id": combo_id,
        "name": row[1],
        "role_name": role_name,
        "snapshot": snapshot,
        "idempotent": False,
    }


async def combine(uid: int, ids: Sequence[int], custom_name: str, scroll_id: Optional[int] = None) -> Dict:
    if len(ids) != 3 or len(set(ids)) != 3:
        raise RoleSpecialError("必须选择三种不同且已点亮的能力。")
    normalized = _normalize_name(custom_name)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            spec = get_role_spec(role_name)
            scroll = None
            if spec.get("requires_scroll"):
                if scroll_id is None:
                    raise RoleSpecialError("该角色必须选择一幅佳作以上且未用于推演的真实战斗绘卷。")
                await cursor.execute(
                    """SELECT id,quality FROM user_role_special_scroll
                       WHERE id=%s AND uid=%s AND role_id=%s AND status='READY' FOR UPDATE""",
                    (scroll_id, uid, role_id),
                )
                scroll = await cursor.fetchone()
                quality_order = {"凡品":1,"佳作":2,"传神":3,"绝响":4}
                if not scroll or quality_order.get(scroll[1], 0) < 2:
                    raise RoleSpecialError("刀势推演要求一幅佳作以上且未使用的绘卷。")
            await cursor.execute(
                "SELECT growth_stage FROM user_role_special_progress WHERE uid=%s AND role_id=%s FOR UPDATE",
                (uid, role_id),
            )
            combo_min_stage = int(spec.get("combo_min_stage", 3))
            if int((await cursor.fetchone())[0]) < combo_min_stage:
                raise RoleSpecialError(f"{spec['growth_name']}达到第{combo_min_stage}阶段后才可进行{spec['combo']['type']}。")
            placeholders = ",".join(["%s"] * 3)
            await cursor.execute(
                f"""SELECT c.id,c.collection_code,c.name,c.skill_multiplier,c.effect_json,c.skill_type
                    FROM role_special_collection_config c JOIN user_role_special_collection u
                      ON u.collection_id=c.id AND u.uid=%s AND u.role_id=%s AND u.unlocked=1
                    WHERE c.role_template_id=%s AND c.id IN ({placeholders}) ORDER BY FIELD(c.id,{placeholders})""",
                (uid, role_id, template_id, *ids, *ids),
            )
            materials = await cursor.fetchall()
            if len(materials) != 3:
                raise RoleSpecialError("组合材料中存在未点亮或不属于当前角色的能力。")
            forbidden = set(spec.get("non_combinable_codes", []))
            if any(row[1] in forbidden for row in materials):
                raise RoleSpecialError("所选能力属于独立终极投影，不能作为三能力组合材料。")
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
            values = [float(row[3]) for row in materials]
            fixed_key = "+".join(row[1] for row in materials)
            fixed_effect = spec.get("fixed_combos", {}).get(fixed_key)
            if fixed_effect:
                multiplier = sum(values) / 3
                raw_effect = dict(fixed_effect)
                raw_effect["inherited_from"] = "固定连携"
                raw_effect["source_kind"] = "ACTIVE"
            else:
                multiplier = max(sum(values) / 3, rng.uniform(min(values), min(2.0, max(values) * 1.5)))
                effect_source = rng.choice(materials)
                raw_effect = dict(_json(effect_source[4]))
                raw_effect["inherited_from"] = effect_source[2]
                raw_effect["source_kind"] = effect_source[5]
            multiplier_bp = normalize_combo_multiplier_bp(multiplier)
            multiplier = multiplier_bp / 10000
            effect = sanitize_combo_effect(raw_effect)
            await cursor.execute(
                """INSERT INTO user_role_special_combo
                   (uid,role_id,combo_type,custom_name,normalized_name,material_collection_ids_json,slot_order_json,multiplier,effect_json,seed)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (uid, role_id, spec["combo"]["type"], custom_name, normalized,
                 json.dumps(list(ids)), json.dumps(list(ids)), round(multiplier, 3),
                 json.dumps(effect, ensure_ascii=False), seed),
            )
            combo_id = cursor.lastrowid
            if scroll:
                await cursor.execute("UPDATE user_role_special_scroll SET status='USED',used_combo_id=%s WHERE id=%s", (combo_id, scroll[0]))
            await conn.commit()
    return {"id": int(combo_id), "name": custom_name, "multiplier": round(multiplier, 3),
            "effect": effect, "materials": [row[2] for row in materials]}


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
    normalized_rows = []
    for row in rows:
        normalized_rows.append((row[0], row[1], row[2], _json(row[3]), row[4]))
    return {"role_name": role_name, "spec": get_role_spec(role_name), "rows": normalized_rows}


async def create_scroll(uid: int, battle_id: str) -> Dict:
    battle_id = str(battle_id or "").strip()
    if not battle_id:
        raise RoleSpecialError("请提供已完成战斗的 battle_id。")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, template_id, role_name = await _active_role(cursor, uid, True)
            spec = get_role_spec(role_name)
            if not spec.get("requires_scroll"):
                raise RoleSpecialError("当前角色没有真实战斗绘卷系统。")
            await _ensure_progress(cursor, uid, role_id, template_id, role_name)
            await cursor.execute(
                """SELECT battle_uuid,battle_type,state,snapshot_json,result_json,metadata_json
                   FROM battle_session WHERE battle_uuid=%s AND owner_uid=%s LIMIT 1 FOR UPDATE""",
                (battle_id, uid),
            )
            row = await cursor.fetchone()
            if not row or row[2] != "FINISHED" or row[1] not in ("SOLO_DUNGEON", "WORLD_BOSS"):
                raise RoleSpecialError("只能使用本人已完成结算的PVE战斗记录。")
            snapshot, result, metadata = _json(row[3]), _json(row[4]), _json(row[5])
            if snapshot.get("player", {}).get("name") != role_name or result.get("winner") != role_name:
                raise RoleSpecialError("该战斗不是由当前孟川出战并获胜的有效记录。")
            broken = len(result.get("boss_tianji", {}).get("broken_stages", []))
            rounds = int(result.get("total_rounds", 0))
            if broken >= 2 and rounds >= 5:
                quality = "绝响"
            elif broken >= 1 and int(result.get("player_hp", 0)) > 0:
                quality = "传神"
            elif broken >= 1:
                quality = "佳作"
            else:
                quality = "凡品"
            request_id = f"scroll:{battle_id}:{uid}:{role_id}"
            ink_code = spec.get("world_material_code", f"ROLE_{template_id}_INK")
            await _change_material(cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                                   code=ink_code, amount=-1, source="CREATE_SCROLL")
            detail = {
                "rounds": rounds, "broken_stages": broken, "monster": metadata.get("monster_name"),
                "special_events": result.get("role_special", {}).get("events", []),
            }
            try:
                await cursor.execute(
                    """INSERT INTO user_role_special_scroll
                       (uid,role_id,battle_id,quality,detail_json,status) VALUES (%s,%s,%s,%s,%s,'READY')""",
                    (uid, role_id, battle_id, quality, json.dumps(detail, ensure_ascii=False)),
                )
            except Exception as exc:
                if getattr(exc, "args", [None])[0] == 1062:
                    raise RoleSpecialError("该 battle_id 已经生成过绘卷。") from exc
                raise
            scroll_id = int(cursor.lastrowid)
            await conn.commit()
    return {"id": scroll_id, "quality": quality, "battle_id": battle_id, "detail": detail}


async def list_scrolls(uid: int) -> List[Dict]:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            role_id, _, role_name = await _active_role(cursor, uid)
            if role_name != "孟川":
                return []
            await cursor.execute(
                """SELECT id,battle_id,quality,detail_json,status,created_at
                   FROM user_role_special_scroll WHERE uid=%s AND role_id=%s ORDER BY id DESC LIMIT 10""",
                (uid, role_id),
            )
            rows = await cursor.fetchall()
    return [{"id":int(r[0]),"battle_id":r[1],"quality":r[2],"detail":_json(r[3]),"status":r[4],"created_at":r[5]} for r in rows]


async def load_battle_special(cursor, uid: int, role_id: int, role_name: str) -> Optional[Dict]:
    """将主动、被动和唯一组合读入战斗快照，断线恢复不再查询配置。"""
    if not get_role_spec(role_name):
        return None
    await cursor.execute(
        """SELECT p.growth_stage,a.id,a.name,a.skill_multiplier,a.effect_json,b.id,b.name,b.effect_json,p.preset_json
           FROM user_role_special_progress p
           LEFT JOIN role_special_collection_config a ON a.id=p.active_skill_id
           LEFT JOIN role_special_collection_config b ON b.id=p.active_passive_id
           WHERE p.uid=%s AND p.role_id=%s LIMIT 1""", (uid, role_id),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    special = {
        "role_id": role_id, "role_name": role_name, "growth_stage": int(row[0]),
        "active": None if not row[1] else {"id": int(row[1]), "name": row[2], "multiplier": float(row[3]), "effect": _json(row[4])},
        "passive": None if not row[5] else {"id": int(row[5]), "name": row[6], "effect": _json(row[7])},
        "feature": _json(row[8]),
    }
    combo = await load_equipped_combo(cursor, uid, role_id)
    return apply_combo_to_battle_special(special, combo)


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
                event_id = int(event["id"])
                # 组合使用负skill_id保持旧唯一键幂等，同时在combo_id记录真实正编号。
                skill_id = event_id
                combo_id = -event_id if event_id < 0 else None
                await cursor.execute(
                    """INSERT IGNORE INTO role_special_battle_log
                       (battle_id,uid,role_id,skill_id,combo_id,trigger_round,target_id,base_value,multiplier,final_value,effect_result_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (battle_id, uid, role_id, skill_id, combo_id, int(event.get("round", 0)), "enemy",
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
            codes = _material_codes(spec)
            if spec.get("growth_on_drop"):
                await _change_material(cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                                       code=codes["growth"], amount=1, source="BATTLE_GROWTH")
            elif is_boss:
                await _change_material(cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                                       code=codes["growth"], amount=1, source="BOSS_GROWTH")
            if is_boss:
                if spec.get("boss_material_code"):
                    await _change_material(cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                                           code=spec["boss_material_code"], amount=1, source="BOSS_TRIAL_MATERIAL")
                if rng.random() < .20:
                    await _change_material(cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                                           code=codes["core"], amount=1, source="BOSS_CORE")
            for code, amount in spec.get("drop_extra_materials", {}).items():
                await _change_material(cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                                       code=code, amount=int(amount), source="BATTLE_EXTRA")
            if is_boss:
                for code, amount in spec.get("boss_extra_materials", {}).items():
                    await _change_material(cursor, request_id=request_id, battle_id=battle_id, uid=uid, role_id=role_id,
                                           code=code, amount=int(amount), source="BOSS_EXTRA")
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
            extra_name = None
            if spec.get("world_material_code"):
                await _change_material(cursor, request_id=request_id, battle_id=run_key, uid=uid, role_id=role_id,
                                       code=spec["world_material_code"], amount=1, source="WORLD_ROLE_MATERIAL")
                extra_name = spec.get("extra_materials", {}).get(spec["world_material_code"], spec["world_material_code"])
            await cursor.execute(
                "UPDATE user_role_special_progress SET world_insight_key=%s WHERE uid=%s AND role_id=%s",
                (run_key, uid, role_id),
            )
            await conn.commit()
    return {"role_name": role_name, "growth": growth, "essence": essence, "extra_name": extra_name}
