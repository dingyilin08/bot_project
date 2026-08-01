# -*- coding: utf-8 -*-
"""仙玉祈愿领域服务：奖池、定向、保底、固定奖励和角色合成。"""

import json
import math
import random
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from Game_domain.reward_service import required_exp
from Game_domain.role_grant_service import RoleGrantError, grant_role
from Game_domain.role_progression_service import apply_role_experience
from Game_domain.role_special_asset_service import RoleSpecialAssetError, add_fragments
from sql.mysql import connect_mysql


FULL_SPECIAL = "SPECIAL_5_PACK"
FULL_RESOURCE = "HIGH_RESOURCE_PACK"
FULL_SPECIAL_FRAGMENT_AMOUNT = 10
FULL_RESOURCE_PILL_AMOUNT = 2
FULL_RESOURCE_ORIGIN_AMOUNT = 20


class CharacterWishError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def _loads(value, default=None):
    if value is None:
        return {} if default is None else default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {} if default is None else default


def choose_main_reward(rng, rates: dict, *, full_roster: bool = False) -> str:
    """按万分比选择主奖励；全图鉴时移除角色碎片并等比归一。"""
    entries = [
        ("HERB", int(rates["herb"])),
        ("PILL", int(rates["pill"])),
        ("SPECIAL_4", int(rates["special4"])),
        ("SPECIAL_5", int(rates["special5"])),
    ]
    if not full_roster:
        entries.append(("ROLE_FRAGMENT", int(rates["role_fragment"])))
    total = sum(weight for _, weight in entries)
    roll = rng.randint(1, total)
    current = 0
    for reward_type, weight in entries:
        current += weight
        if roll <= current:
            return reward_type
    return entries[-1][0]


def choose_by_rarity(rng, rows: list, rarity_weights: dict):
    """先按稀有度权重，再在同稀有度内等概率，避免目录数量扭曲稀有度。"""
    groups = {}
    for row in rows:
        groups.setdefault(int(row[2]), []).append(row)
    available = [(rarity, int(rarity_weights.get(rarity, 0))) for rarity in groups]
    available = [(rarity, weight) for rarity, weight in available if weight > 0]
    if not available:
        raise CharacterWishError("EMPTY_REWARD_POOL", "奖池缺少可用的药材或丹药配置。")
    roll = rng.randint(1, sum(weight for _, weight in available))
    current = 0
    chosen_rarity = available[-1][0]
    for rarity, weight in available:
        current += weight
        if roll <= current:
            chosen_rarity = rarity
            break
    return rng.choice(groups[chosen_rarity])


async def _active_pool(cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        """SELECT id,pool_code,version,name,single_cost,ten_cost,compose_fragment_cost,
                  herb_rate_bp,pill_rate_bp,special4_rate_bp,special5_rate_bp,
                  role_fragment_rate_bp,pity_count
           FROM character_wish_pool
           WHERE enabled=1 AND (starts_at IS NULL OR starts_at<=NOW())
             AND (ends_at IS NULL OR ends_at>NOW())
           ORDER BY id DESC LIMIT 1""" + suffix
    )
    row = await cursor.fetchone()
    if not row:
        raise CharacterWishError("POOL_CLOSED", "当前没有开放的仙玉祈愿池。")
    keys = ("id", "pool_code", "version", "name", "single_cost", "ten_cost",
            "compose_cost", "herb", "pill", "special4", "special5",
            "role_fragment", "pity_limit")
    return dict(zip(keys, row))


async def _ensure_pity(cursor, uid: int, pool_id: int, lock=False):
    await cursor.execute(
        "INSERT IGNORE INTO character_wish_pity (uid,pool_id) VALUES (%s,%s)",
        (uid, pool_id),
    )
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        """SELECT pity_count,total_count,target_role_template_id,full_reward_type,
                  full_reward_role_template_id
           FROM character_wish_pity WHERE uid=%s AND pool_id=%s""" + suffix,
        (uid, pool_id),
    )
    row = await cursor.fetchone()
    return {
        "pity": int(row[0]), "total": int(row[1]), "target_id": row[2],
        "full_type": row[3], "full_role_id": row[4],
    }


async def _roster(cursor, uid: int):
    await cursor.execute("SELECT COUNT(*) FROM data_role")
    total = int((await cursor.fetchone())[0])
    await cursor.execute("SELECT COUNT(DISTINCT `name`) FROM user_role WHERE uid=%s", (uid,))
    owned = int((await cursor.fetchone())[0])
    return owned >= total and total > 0, owned, total


async def _active_role(cursor, uid: int, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        """SELECT ur.id,dr.id,ur.name,ur.dengji,ur.exp
           FROM user_role ur JOIN data_role dr ON dr.name=ur.name
           WHERE ur.uid=%s AND ur.is_chuzhan=1 LIMIT 1""" + suffix,
        (uid,),
    )
    row = await cursor.fetchone()
    if not row:
        raise CharacterWishError("NO_ACTIVE_ROLE", "请先让一名角色出战，再进行仙玉祈愿。")
    return {"role_id": int(row[0]), "template_id": int(row[1]), "name": row[2],
            "level": int(row[3]), "exp": int(row[4])}


async def _origin_items(cursor, role_name: str):
    await cursor.execute(
        "SELECT need_item_1,need_item_2,need_item_3 FROM data_benyuan WHERE role_name=%s LIMIT 1",
        (role_name,),
    )
    row = await cursor.fetchone()
    ids = []
    for value in row or ():
        try:
            item_id = int(value)
            if item_id > 0:
                ids.append(item_id)
        except (TypeError, ValueError):
            continue
    if not ids:
        raise CharacterWishError("ORIGIN_CONFIG_MISSING", f"角色{role_name}缺少本源材料配置。")
    return ids


async def _item_names(cursor, item_ids):
    if not item_ids:
        return {}
    marks = ",".join(["%s"] * len(item_ids))
    await cursor.execute(f"SELECT id,`name` FROM data_item WHERE id IN ({marks})", tuple(item_ids))
    return {int(row[0]): row[1] for row in await cursor.fetchall()}


async def _grant_item(cursor, *, key: str, uid: int, item_id: int, amount: int, source_id: str):
    await cursor.execute(
        """INSERT INTO reward_ledger
           (business_key,uid,reward_type,amount,source_type,source_id,status,payload_json)
           VALUES (%s,%s,'ITEM',%s,'CHARACTER_WISH',%s,'GRANTED',%s)""",
        (key, uid, amount, source_id, _dumps({"item_id": item_id})),
    )
    await cursor.execute(
        """INSERT INTO user_item (uid,item_id,item_num) VALUES (%s,%s,%s)
           ON DUPLICATE KEY UPDATE item_num=item_num+VALUES(item_num)""",
        (uid, item_id, amount),
    )


async def _grant_character_fragment(cursor, *, key: str, uid: int, template_id: int,
                                    amount: int, source: str):
    await cursor.execute(
        """INSERT IGNORE INTO user_character_fragment (uid,role_template_id,amount)
           VALUES (%s,%s,0)""",
        (uid, template_id),
    )
    await cursor.execute(
        """SELECT amount FROM user_character_fragment
           WHERE uid=%s AND role_template_id=%s FOR UPDATE""",
        (uid, template_id),
    )
    before = int((await cursor.fetchone())[0])
    after = before + amount
    await cursor.execute(
        "UPDATE user_character_fragment SET amount=%s WHERE uid=%s AND role_template_id=%s",
        (after, uid, template_id),
    )
    await cursor.execute(
        """INSERT INTO character_fragment_ledger
           (request_id,uid,role_template_id,change_amount,balance_before,balance_after,source_type)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (key, uid, template_id, amount, before, after, source),
    )
    return after


async def home(uid: int) -> dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            pool = await _active_pool(cursor)
            await cursor.execute("SELECT xianyu FROM user_zt WHERE id=%s", (uid,))
            player = await cursor.fetchone()
            if not player:
                raise CharacterWishError("PLAYER_NOT_FOUND", "请先注册游戏。")
            role = await _active_role(cursor, uid)
            pity = await _ensure_pity(cursor, uid, pool["id"])
            full, owned, total = await _roster(cursor, uid)
            target_name = None
            if pity["target_id"]:
                await cursor.execute("SELECT `name` FROM data_role WHERE id=%s", (pity["target_id"],))
                target = await cursor.fetchone()
                target_name = target[0] if target else None
            full_role_name = None
            if pity["full_role_id"]:
                await cursor.execute("SELECT `name` FROM data_role WHERE id=%s", (pity["full_role_id"],))
                selected = await cursor.fetchone()
                full_role_name = selected[0] if selected else None
            await cursor.execute(
                """SELECT dr.name FROM data_role dr LEFT JOIN user_role ur
                   ON ur.uid=%s AND ur.name=dr.name WHERE ur.id IS NULL ORDER BY dr.id""",
                (uid,),
            )
            unowned_roles = [row[0] for row in await cursor.fetchall()]
            await cursor.execute("SELECT `name` FROM user_role WHERE uid=%s ORDER BY id", (uid,))
            owned_roles = [row[0] for row in await cursor.fetchall()]
            await conn.commit()
    return {"pool": pool, "xianyu": int(player[0]), "role": role, "pity": pity,
            "target_name": target_name, "full_roster": full, "owned": owned,
            "roster_total": total, "full_role_name": full_role_name,
            "unowned_roles": unowned_roles, "owned_roles": owned_roles}


async def set_target(uid: int, role_name: str) -> dict:
    role_name = str(role_name or "").strip()
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                pool = await _active_pool(cursor)
                full, _, _ = await _roster(cursor, uid)
                if full:
                    raise CharacterWishError("FULL_ROSTER", "你已集齐全部角色，请改为设置全图鉴保底奖励。")
                await cursor.execute("SELECT id,`name` FROM data_role WHERE `name`=%s LIMIT 1", (role_name,))
                target = await cursor.fetchone()
                if not target:
                    raise CharacterWishError("ROLE_NOT_FOUND", "未找到该角色。")
                await cursor.execute("SELECT id FROM user_role WHERE uid=%s AND `name`=%s LIMIT 1", (uid, role_name))
                if await cursor.fetchone():
                    raise CharacterWishError("ROLE_OWNED", f"你已经拥有{role_name}，请定向尚未拥有的角色。")
                pity = await _ensure_pity(cursor, uid, pool["id"], lock=True)
                await cursor.execute(
                    "UPDATE character_wish_pity SET target_role_template_id=%s WHERE uid=%s AND pool_id=%s",
                    (target[0], uid, pool["id"]),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return {"role_name": target[1], "pity": pity["pity"], "pity_limit": pool["pity_limit"]}


async def set_full_choice(uid: int, choice: str) -> dict:
    text = str(choice or "").strip()
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                pool = await _active_pool(cursor)
                full, _, _ = await _roster(cursor, uid)
                if not full:
                    raise CharacterWishError("ROSTER_INCOMPLETE", "集齐全部角色后才能设置全图鉴保底。")
                reward_type, role_id, label = None, None, None
                if text == "高阶资源礼包":
                    reward_type, label = FULL_RESOURCE, text
                elif text.startswith("五星专属礼包-"):
                    role_name = text.split("-", 1)[1].strip()
                    await cursor.execute(
                        """SELECT dr.id FROM data_role dr JOIN user_role ur ON ur.name=dr.name
                           WHERE ur.uid=%s AND dr.name=%s LIMIT 1""",
                        (uid, role_name),
                    )
                    row = await cursor.fetchone()
                    if not row:
                        raise CharacterWishError("ROLE_NOT_FOUND", "礼包角色不存在或尚未拥有。")
                    await cursor.execute(
                        "SELECT id FROM role_special_collection_config WHERE role_template_id=%s AND rarity=5 AND enabled=1 LIMIT 1",
                        (row[0],),
                    )
                    if not await cursor.fetchone():
                        raise CharacterWishError("SPECIAL_NOT_FOUND", "该角色暂无五星专属能力配置。")
                    reward_type, role_id, label = FULL_SPECIAL, int(row[0]), text
                else:
                    raise CharacterWishError("INVALID_CHOICE", "请选择“五星专属礼包-角色名”或“高阶资源礼包”。")
                await _ensure_pity(cursor, uid, pool["id"], lock=True)
                await cursor.execute(
                    """UPDATE character_wish_pity SET full_reward_type=%s,
                       full_reward_role_template_id=%s WHERE uid=%s AND pool_id=%s""",
                    (reward_type, role_id, uid, pool["id"]),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return {"choice": label}


async def _catalog(cursor, pool_id: int, active_template_id: int):
    await cursor.execute("SELECT item_id,`name`,tier FROM data_herb WHERE item_id IS NOT NULL")
    herbs = [(int(r[0]), r[1], int(r[2])) for r in await cursor.fetchall()]
    await cursor.execute("SELECT item_id,`name`,category FROM data_pill WHERE item_id IS NOT NULL")
    pills = [(int(r[0]), r[1], int(r[2])) for r in await cursor.fetchall()]
    await cursor.execute(
        """SELECT id,`name`,rarity,fragment_code FROM role_special_collection_config
           WHERE role_template_id=%s AND rarity IN (4,5) AND enabled=1""",
        (active_template_id,),
    )
    specials = await cursor.fetchall()
    by_rarity = {4: [], 5: []}
    for row in specials:
        by_rarity[int(row[2])].append(row)
    if not by_rarity[4] or not by_rarity[5]:
        raise CharacterWishError("SPECIAL_POOL_EMPTY", "当前出战角色的四星或五星专属能力配置不完整。")
    await cursor.execute(
        "SELECT reward_group,rarity,weight FROM character_wish_rarity_weight WHERE pool_id=%s AND enabled=1",
        (pool_id,),
    )
    weights = {"HERB": {}, "PILL": {}}
    for group, rarity, weight in await cursor.fetchall():
        weights.setdefault(group, {})[int(rarity)] = int(weight)
    if not herbs or not pills:
        raise CharacterWishError("ITEM_POOL_EMPTY", "药材或丹药奖池为空，请联系管理员补全目录。")
    return herbs, pills, by_rarity, weights


async def draw(uid: int, count: int, request_id: str = None) -> dict:
    if int(count) not in (1, 10):
        raise CharacterWishError("INVALID_COUNT", "仅支持单抽或十连祈愿。")
    count = int(count)
    request_id = str(request_id or f"manual:{uuid4().hex}")[:80]
    rng = random.SystemRandom()
    level_changed = False
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT xianyu FROM user_zt WHERE id=%s FOR UPDATE", (uid,))
                player = await cursor.fetchone()
                if not player:
                    raise CharacterWishError("PLAYER_NOT_FOUND", "请先注册游戏。")
                # 先锁玩家再查业务键，确保同一玩家的并发重复请求能看到首个事务的提交结果。
                await cursor.execute("SELECT status,result_json FROM character_wish_order WHERE request_id=%s", (request_id,))
                duplicate = await cursor.fetchone()
                if duplicate and duplicate[0] == "SUCCESS":
                    return _loads(duplicate[1])
                pool = await _active_pool(cursor, lock=True)
                role = await _active_role(cursor, uid, lock=True)
                pity = await _ensure_pity(cursor, uid, pool["id"], lock=True)
                full, _, _ = await _roster(cursor, uid)
                if full:
                    if not pity["full_type"]:
                        raise CharacterWishError("FULL_CHOICE_REQUIRED", "请先设置全图鉴第80抽奖励。")
                else:
                    if not pity["target_id"]:
                        raise CharacterWishError("TARGET_REQUIRED", "请先发送“祈愿定向 角色名”设置定向角色。")
                    await cursor.execute(
                        "SELECT ur.id FROM user_role ur JOIN data_role dr ON dr.name=ur.name WHERE ur.uid=%s AND dr.id=%s LIMIT 1",
                        (uid, pity["target_id"]),
                    )
                    if await cursor.fetchone():
                        raise CharacterWishError("TARGET_OWNED", "当前定向角色已经拥有，请重新设置定向。")
                cost = int(pool["single_cost"] if count == 1 else pool["ten_cost"])
                balance_before = int(player[0])
                if balance_before < cost:
                    raise CharacterWishError("INSUFFICIENT_XIANYU", f"仙玉不足，本次需要{cost}仙玉。")
                herbs, pills, specials, rarity_weights = await _catalog(cursor, pool["id"], role["template_id"])
                origin_ids = await _origin_items(cursor, role["name"])
                origin_names = await _item_names(cursor, origin_ids)
                await cursor.execute(
                    """INSERT INTO character_wish_order
                       (request_id,uid,pool_id,pool_version,draw_count,cost_xianyu,
                        balance_before,balance_after,role_id,target_role_template_id,pity_before,status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PROCESSING')""",
                    (request_id, uid, pool["id"], pool["version"], count, cost,
                     balance_before, balance_before-cost, role["role_id"],
                     pity["target_id"], pity["pity"]),
                )
                order_id = int(cursor.lastrowid)
                await cursor.execute(
                    "UPDATE user_zt SET xianyu=xianyu-%s WHERE id=%s AND xianyu>=%s",
                    (cost, uid, cost),
                )
                if cursor.rowcount != 1:
                    raise CharacterWishError("INSUFFICIENT_XIANYU", "仙玉余额发生变化，请重试。")

                results = []
                current_pity = pity["pity"]
                current_level = role["level"]
                for index in range(1, count + 1):
                    draw_key = f"wish:{order_id}:{index}"
                    pity_before = current_pity
                    is_pity = current_pity >= int(pool["pity_limit"]) - 1
                    if is_pity:
                        reward_type = "FULL_ROSTER_PACK" if full else "ROLE_FRAGMENT"
                        current_pity = 0
                    else:
                        reward_type = choose_main_reward(rng, pool, full_roster=full)
                        current_pity = 0 if reward_type == "ROLE_FRAGMENT" else current_pity + 1

                    reward = {}
                    if reward_type in ("HERB", "PILL"):
                        rows = herbs if reward_type == "HERB" else pills
                        row = choose_by_rarity(rng, rows, rarity_weights[reward_type])
                        amount = rng.randint(1, 2)
                        await _grant_item(cursor, key=f"{draw_key}:main", uid=uid,
                                          item_id=row[0], amount=amount, source_id=request_id)
                        reward = {"name": row[1], "item_id": row[0], "rarity": row[2], "amount": amount}
                    elif reward_type in ("SPECIAL_4", "SPECIAL_5"):
                        rarity = 4 if reward_type == "SPECIAL_4" else 5
                        row = rng.choice(specials[rarity])
                        try:
                            balance = await add_fragments(
                                cursor, request_id=f"{draw_key}:special", battle_id=None,
                                uid=uid, role_id=role["role_id"], collection_id=int(row[0]),
                                fragment_code=row[3], amount=1, source="CHARACTER_WISH",
                            )
                        except RoleSpecialAssetError as exc:
                            raise CharacterWishError("SPECIAL_GRANT_FAILED", str(exc)) from exc
                        reward = {"name": row[1], "collection_id": int(row[0]),
                                  "rarity": rarity, "amount": 1, "balance": balance}
                    elif reward_type == "ROLE_FRAGMENT":
                        await cursor.execute("SELECT `name` FROM data_role WHERE id=%s", (pity["target_id"],))
                        target = await cursor.fetchone()
                        balance = await _grant_character_fragment(
                            cursor, key=f"{draw_key}:role", uid=uid,
                            template_id=int(pity["target_id"]), amount=1,
                            source="PITY" if is_pity else "WISH",
                        )
                        reward = {"name": f"{target[0]}碎片", "role_template_id": int(pity["target_id"]),
                                  "amount": 1, "balance": balance}
                    else:
                        if pity["full_type"] == FULL_SPECIAL:
                            await cursor.execute(
                                "SELECT id,`name` FROM user_role WHERE uid=%s AND `name`=(SELECT `name` FROM data_role WHERE id=%s) LIMIT 1",
                                (uid, pity["full_role_id"]),
                            )
                            pack_role = await cursor.fetchone()
                            await cursor.execute(
                                """SELECT id,`name`,fragment_code FROM role_special_collection_config
                                   WHERE role_template_id=%s AND rarity=5 AND enabled=1""",
                                (pity["full_role_id"],),
                            )
                            special = rng.choice(await cursor.fetchall())
                            balance = await add_fragments(
                                cursor, request_id=f"{draw_key}:full-special", battle_id=None,
                                uid=uid, role_id=int(pack_role[0]), collection_id=int(special[0]),
                                fragment_code=special[2], amount=FULL_SPECIAL_FRAGMENT_AMOUNT,
                                source="CHARACTER_WISH_FULL_PITY",
                            )
                            reward = {"name": f"五星专属礼包-{pack_role[1]}", "detail": special[1],
                                      "amount": FULL_SPECIAL_FRAGMENT_AMOUNT, "balance": balance}
                        else:
                            highest = max(int(row[2]) for row in pills)
                            row = rng.choice([row for row in pills if int(row[2]) == highest])
                            await _grant_item(cursor, key=f"{draw_key}:full-pill", uid=uid,
                                              item_id=row[0], amount=FULL_RESOURCE_PILL_AMOUNT,
                                              source_id=request_id)
                            origin_id = rng.choice(origin_ids)
                            await _grant_item(cursor, key=f"{draw_key}:full-origin", uid=uid,
                                              item_id=origin_id, amount=FULL_RESOURCE_ORIGIN_AMOUNT,
                                              source_id=request_id)
                            reward = {"name": "高阶丹药与本源材料礼包",
                                      "pill": {"name": row[1], "amount": FULL_RESOURCE_PILL_AMOUNT},
                                      "origin": {"name": origin_names.get(origin_id, str(origin_id)),
                                                 "amount": FULL_RESOURCE_ORIGIN_AMOUNT}}

                    fixed = []
                    role_exp = 0
                    if current_level < 100:
                        role_exp = int(math.ceil(required_exp(current_level) / 3))
                        await cursor.execute(
                            """INSERT INTO reward_ledger
                               (business_key,uid,reward_type,amount,source_type,source_id,status,payload_json)
                               VALUES (%s,%s,'EXP',%s,'CHARACTER_WISH',%s,'GRANTED',%s)""",
                            (f"{draw_key}:exp", uid, role_exp, request_id,
                             _dumps({"role_id": role["role_id"]})),
                        )
                        progress = await apply_role_experience(
                            cursor, uid=uid, role_id=role["role_id"], add_exp=role_exp,
                        )
                        level_changed = level_changed or progress["level"] != current_level
                        current_level = int(progress["level"])
                        fixed.append({"type": "EXP", "amount": role_exp,
                                      "level": current_level, "exp": int(progress["exp"])})
                    origin_rolls = 2 if current_level >= 100 and role_exp == 0 else 1
                    for origin_index in range(origin_rolls):
                        item_id = rng.choice(origin_ids)
                        amount = rng.randint(1, 5)
                        await _grant_item(cursor, key=f"{draw_key}:origin:{origin_index}",
                                          uid=uid, item_id=item_id, amount=amount,
                                          source_id=request_id)
                        fixed.append({"type": "ORIGIN", "item_id": item_id,
                                      "name": origin_names.get(item_id, str(item_id)), "amount": amount})
                    entry = {"index": index, "reward_type": reward_type, "reward": reward,
                             "role_exp": role_exp, "fixed": fixed, "pity_before": pity_before,
                             "pity_after": current_pity, "is_pity": is_pity}
                    results.append(entry)
                    await cursor.execute(
                        """INSERT INTO character_wish_result
                           (order_id,draw_index,main_reward_type,reward_json,role_exp,
                            fixed_reward_json,pity_before,pity_after,is_pity)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (order_id, index, reward_type, _dumps(reward), role_exp,
                         _dumps(fixed), pity_before, current_pity, 1 if is_pity else 0),
                    )
                await cursor.execute(
                    """UPDATE character_wish_pity SET pity_count=%s,total_count=total_count+%s
                       WHERE uid=%s AND pool_id=%s""",
                    (current_pity, count, uid, pool["id"]),
                )
                result = {"request_id": request_id, "count": count, "cost": cost,
                          "balance_before": balance_before, "balance_after": balance_before-cost,
                          "pity_before": pity["pity"], "pity_after": current_pity,
                          "role_name": role["name"], "results": results}
                await cursor.execute(
                    """UPDATE character_wish_order SET pity_after=%s,status='SUCCESS',
                       result_json=%s,completed_at=NOW() WHERE id=%s""",
                    (current_pity, _dumps(result), order_id),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    if level_changed:
        try:
            from Tool.tool_power import update_role_power
            async with connect_mysql() as power_conn:
                await update_role_power(power_conn, uid)
                await power_conn.commit()
        except Exception:
            pass
    return result


async def fragments(uid: int) -> list:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """SELECT dr.id,dr.name,COALESCE(f.amount,0),
                          CASE WHEN ur.id IS NULL THEN 0 ELSE 1 END
                   FROM data_role dr
                   LEFT JOIN user_character_fragment f ON f.uid=%s AND f.role_template_id=dr.id
                   LEFT JOIN user_role ur ON ur.uid=%s AND ur.name=dr.name
                   ORDER BY dr.id""",
                (uid, uid),
            )
            return [{"role_template_id": int(r[0]), "role_name": r[1],
                     "amount": int(r[2]), "owned": bool(r[3])} for r in await cursor.fetchall()]


async def compose(uid: int, role_name: str, request_id: str = None) -> dict:
    request_id = str(request_id or f"manual:{uuid4().hex}")[:80]
    role_name = str(role_name or "").strip()
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT id FROM user_zt WHERE id=%s FOR UPDATE", (uid,))
                if not await cursor.fetchone():
                    raise CharacterWishError("PLAYER_NOT_FOUND", "请先注册游戏。")
                await cursor.execute("SELECT status,result_json FROM character_compose_order WHERE request_id=%s", (request_id,))
                duplicate = await cursor.fetchone()
                if duplicate and duplicate[0] == "SUCCESS":
                    return _loads(duplicate[1])
                pool = await _active_pool(cursor)
                await cursor.execute("SELECT id,`name` FROM data_role WHERE `name`=%s LIMIT 1", (role_name,))
                template = await cursor.fetchone()
                if not template:
                    raise CharacterWishError("ROLE_NOT_FOUND", "未找到该角色。")
                await cursor.execute("SELECT id FROM user_role WHERE uid=%s AND `name`=%s LIMIT 1", (uid, role_name))
                if await cursor.fetchone():
                    raise CharacterWishError("ROLE_OWNED", f"你已经拥有角色{role_name}。")
                await cursor.execute(
                    """INSERT IGNORE INTO user_character_fragment (uid,role_template_id,amount)
                       VALUES (%s,%s,0)""", (uid, template[0]))
                await cursor.execute(
                    "SELECT amount FROM user_character_fragment WHERE uid=%s AND role_template_id=%s FOR UPDATE",
                    (uid, template[0]),
                )
                amount = int((await cursor.fetchone())[0])
                cost = int(pool["compose_cost"])
                if amount < cost:
                    raise CharacterWishError("FRAGMENT_NOT_ENOUGH", f"{role_name}碎片不足，需要{cost}个，当前{amount}个。")
                await cursor.execute(
                    """INSERT INTO character_compose_order
                       (request_id,uid,role_template_id,fragment_cost,status)
                       VALUES (%s,%s,%s,%s,'PROCESSING')""",
                    (request_id, uid, template[0], cost),
                )
                order_id = int(cursor.lastrowid)
                await cursor.execute(
                    """UPDATE user_character_fragment SET amount=amount-%s
                       WHERE uid=%s AND role_template_id=%s AND amount>=%s""",
                    (cost, uid, template[0], cost),
                )
                if cursor.rowcount != 1:
                    raise CharacterWishError("FRAGMENT_NOT_ENOUGH", "角色碎片余额发生变化，请重试。")
                await cursor.execute(
                    """INSERT INTO character_fragment_ledger
                       (request_id,uid,role_template_id,change_amount,balance_before,balance_after,source_type)
                       VALUES (%s,%s,%s,%s,%s,%s,'COMPOSE')""",
                    (f"compose:{request_id}", uid, template[0], -cost, amount, amount-cost),
                )
                try:
                    granted = await grant_role(cursor, uid=uid, role_template_id=int(template[0]))
                except RoleGrantError as exc:
                    raise CharacterWishError("ROLE_GRANT_FAILED", str(exc)) from exc
                await cursor.execute(
                    """UPDATE character_wish_pity SET target_role_template_id=NULL
                       WHERE uid=%s AND target_role_template_id=%s""",
                    (uid, template[0]),
                )
                result = {**granted, "fragment_cost": cost, "fragment_balance": amount-cost}
                await cursor.execute(
                    """UPDATE character_compose_order SET role_id=%s,status='SUCCESS',
                       result_json=%s,completed_at=NOW() WHERE id=%s""",
                    (granted["role_id"], _dumps(result), order_id),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return result


async def history(uid: int, limit: int = 5) -> list:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """SELECT request_id,draw_count,cost_xianyu,pity_before,pity_after,
                          result_json,created_at FROM character_wish_order
                   WHERE uid=%s AND status='SUCCESS' ORDER BY id DESC LIMIT %s""",
                (uid, max(1, min(int(limit), 10))),
            )
            rows = await cursor.fetchall()
    return [{"request_id": r[0], "count": int(r[1]), "cost": int(r[2]),
             "pity_before": int(r[3]), "pity_after": int(r[4]),
             "result": _loads(r[5]), "created_at": r[6]} for r in rows]
