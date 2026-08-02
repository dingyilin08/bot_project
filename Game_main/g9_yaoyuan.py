# -*- coding: utf-8 -*-
"""
药园 + 炼丹系统
"""

import json
import math
import random
import time

from sql.mysql import *
from Tool.tool_user import *
from func.pd_func import *
from Tool.tool_power import update_role_power
from Tool.tool_command import pagination_controls


FARM_SLOT_COUNT = 12
FURNACE_SLOT_COUNT = 5

FARM_MATURE_SECONDS = 7200
ALCHEMY_SECONDS = 3600

FARM_UNLOCK_BASE_OPEN = 5
FERTILIZER_ITEM_ID = 210
LEGACY_FERTILIZER_ITEM_ID = 207
ALCHEMY_ACCEL_ITEM_ID = 208
TIANHUO_REDUCE_SECONDS = 1800
TIANHUO_HELP_DAILY_LIMIT = 10
TIANHUO_BE_HELPED_DAILY_LIMIT = 20
TIANHUO_PER_FURNACE_LIMIT = 10

DANLU_LEVEL_UNLOCK = {2: 30, 3: 50}
DANLU_XIANYU_UNLOCK = {4: 500, 5: 1000}

SEED_PAGE_SIZE = 6
RECIPE_PAGE_SIZE = 6

TIER_NAME = {1: "凡品", 2: "良品", 3: "精品", 4: "仙品"}
TIER_OUTPUT_RANGE = {1: (8, 12), 2: (6, 10), 3: (4, 8), 4: (2, 5)}

ROLE_BASE_ATTRS = {"gongji", "fangyu", "qixue", "fali", "sudu"}
ROLE_RATE_ATTRS = {"baoji", "baoshang", "shanbi", "mingzhong", "pofang", "xixue"}
ROLE_ALL_ATTRS = ROLE_BASE_ATTRS | ROLE_RATE_ATTRS

_YAOYUAN_SCHEMA_READY = False


def _json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(raw):
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = raw.strip()
        if raw == "" or raw.lower() == "null":
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None
    return None


def _empty_farm_slot():
    return {"is_zz": 0, "zz_id": 0, "time": 0}


def _empty_furnace_slot():
    return {"is_lz": 0, "df_id": 0, "time": 0, "fire_count": 0, "batch_ts": 0}


def _format_seconds(seconds):
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    sec = seconds % 60
    if hours > 0:
        return f"{hours}小时{minutes}分{sec}秒"
    if minutes > 0:
        return f"{minutes}分{sec}秒"
    return f"{sec}秒"


def _farm_unlock_cost(plot_no):
    if plot_no <= FARM_UNLOCK_BASE_OPEN:
        return 0
    return max(0, (plot_no - 4) * 100)


def _parse_name_num(param):
    text = str(param or "").strip()
    if "-" not in text:
        return (text, 1) if text else (None, None)
    name, num_txt = text.rsplit("-", 1)
    name = name.strip()
    if not name:
        return None, None
    if not num_txt.strip():
        return name, 1
    try:
        num = int(num_txt.strip())
    except Exception:
        return None, None
    return name, num


def _parse_name_slot(param):
    if "-" not in str(param):
        return None, None
    name, slot_txt = str(param).rsplit("-", 1)
    name = name.strip()
    if not name:
        return None, None
    try:
        slot = int(slot_txt.strip())
    except Exception:
        return None, None
    return name, slot


def _parse_alchemy_param(param):
    """兼容旧指令，并支持“火候-丹方名-炉号”。"""
    name, slot = _parse_name_slot(param)
    if not name:
        return None, None, None
    style = "均衡"
    if "-" in name:
        candidate, recipe_name = name.split("-", 1)
        if candidate in {"保守", "均衡", "冒险"} and recipe_name.strip():
            style, name = candidate, recipe_name.strip()
    return name, slot, style


def _parse_index(param):
    try:
        return int(str(param).strip())
    except Exception:
        return None


def _is_breakthrough_pill_name(pill_name):
    return str(pill_name or "").strip().endswith("破境丹")


def _parse_uid_slot(param):
    txt = str(param).strip()
    if not txt:
        return None, None
    if "-" not in txt:
        if txt.isdigit():
            return int(txt), None
        return None, None
    uid_txt, slot_txt = txt.rsplit("-", 1)
    uid_txt = uid_txt.strip()
    slot_txt = slot_txt.strip()
    if not uid_txt.isdigit():
        return None, None
    try:
        slot = int(slot_txt)
    except Exception:
        return None, None
    return int(uid_txt), slot


def _today_date():
    return time.strftime("%Y-%m-%d", time.localtime())


def _parse_world_or_page(param, default_world):
    world = default_world
    page = 1
    txt = str(param).strip()
    if not txt:
        return world, page
    if txt.isdigit():
        return world, max(1, int(txt))
    if "-" in txt:
        maybe_world, maybe_page = txt.rsplit("-", 1)
        if maybe_page.isdigit():
            world = maybe_world.strip() or default_world
            page = max(1, int(maybe_page))
            return world, page
    world = txt
    return world, page


def _resolve_item_id(data_id, row):
    if not row:
        return int(data_id)
    item_id = row.get("item_id")
    if item_id is None:
        return int(data_id)
    try:
        return int(item_id)
    except Exception:
        return int(data_id)


async def _add_user_item(cursor, uid, item_id, num):
    await cursor.execute(
        """
        INSERT INTO user_item (uid, item_id, item_num)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE item_num = item_num + VALUES(item_num)
        """,
        (uid, item_id, num),
    )


async def _deduct_user_item(cursor, uid, item_id, num):
    await cursor.execute(
        """
        UPDATE user_item
        SET item_num = item_num - %s
        WHERE uid = %s AND item_id = %s AND item_num >= %s
        """,
        (num, uid, item_id, num),
    )
    if cursor.rowcount <= 0:
        return False
    await cursor.execute(
        "DELETE FROM user_item WHERE uid = %s AND item_id = %s AND item_num <= 0",
        (uid, item_id),
    )
    return True


async def _get_current_role(cursor, uid):
    await cursor.execute(
        """
        SELECT id, `name`, dengji, stage, world
        FROM user_role
        WHERE uid = %s AND is_chuzhan = 1
        LIMIT 1
        """,
        (uid,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "level": row[2],
        "stage": row[3] or "",
        "world": row[4] or "",
    }


async def _get_max_role_level(cursor, uid):
    await cursor.execute("SELECT MAX(dengji) FROM user_role WHERE uid = %s", (uid,))
    row = await cursor.fetchone()
    return int(row[0]) if row and row[0] else 0


async def _ensure_yaoyuan_schema(cursor):
    global _YAOYUAN_SCHEMA_READY
    if _YAOYUAN_SCHEMA_READY:
        return

    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS data_seed (
            id INT NOT NULL AUTO_INCREMENT,
            name VARCHAR(50) NOT NULL,
            cl_name VARCHAR(50) NOT NULL,
            cl_id INT NOT NULL,
            price INT NOT NULL,
            tier TINYINT NOT NULL DEFAULT 1,
            world VARCHAR(20) NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_name (name),
            KEY idx_world_tier (world, tier)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_种子表'
        """
    )

    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS data_herb (
            id INT NOT NULL AUTO_INCREMENT,
            name VARCHAR(50) NOT NULL,
            description VARCHAR(255) NULL,
            sell_price INT NOT NULL DEFAULT 0,
            tier TINYINT NOT NULL DEFAULT 1,
            world VARCHAR(20) NULL,
            item_id INT NULL DEFAULT NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_name (name),
            KEY idx_world_tier (world, tier)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_药材表'
        """
    )

    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS data_recipe (
            id INT NOT NULL AUTO_INCREMENT,
            name VARCHAR(50) NOT NULL,
            pill_id INT NOT NULL,
            ingredients VARCHAR(255) NOT NULL,
            need_num INT NOT NULL DEFAULT 10,
            cost INT NOT NULL DEFAULT 200,
            category TINYINT NOT NULL DEFAULT 1,
            world VARCHAR(20) NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_name_world (name, world),
            KEY idx_world_category (world, category)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_丹方表'
        """
    )

    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS data_pill (
            id INT NOT NULL AUTO_INCREMENT,
            name VARCHAR(50) NOT NULL,
            description VARCHAR(255) NULL,
            effect_type VARCHAR(50) NOT NULL,
            effect_value VARCHAR(50) NOT NULL,
            is_percent TINYINT NOT NULL DEFAULT 0,
            max_use INT NOT NULL DEFAULT 1000,
            category TINYINT NOT NULL DEFAULT 1,
            world VARCHAR(20) NULL,
            item_id INT NULL DEFAULT NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_name (name),
            KEY idx_world_category (world, category)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_丹药表'
        """
    )

    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_yaotian (
            id INT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            yt_1 JSON NULL,
            yt_2 JSON NULL,
            yt_3 JSON NULL,
            yt_4 JSON NULL,
            yt_5 JSON NULL,
            yt_6 JSON NULL,
            yt_7 JSON NULL,
            yt_8 JSON NULL,
            yt_9 JSON NULL,
            yt_10 JSON NULL,
            yt_11 JSON NULL,
            yt_12 JSON NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_uid (uid)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_药田表'
        """
    )

    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_danlu (
            id INT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            dl_1 JSON NULL,
            dl_2 JSON NULL,
            dl_3 JSON NULL,
            dl_4 JSON NULL,
            dl_5 JSON NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_uid (uid)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_丹炉表'
        """
    )

    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_seed_bag (
            id INT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            zz_id INT NOT NULL,
            zz_num INT NOT NULL DEFAULT 0,
            PRIMARY KEY (id),
            UNIQUE KEY uk_uid_seed (uid, zz_id),
            KEY idx_uid (uid)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_种子背包'
        """
    )

    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_liandan_fire_daily (
            id INT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            stat_date DATE NOT NULL,
            help_used_times INT NOT NULL DEFAULT 0,
            be_helped_times INT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_uid_date (uid, stat_date),
            KEY idx_date (stat_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_炼丹添火日统计'
        """
    )

    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_liandan_fire_log (
            id BIGINT NOT NULL AUTO_INCREMENT,
            helper_uid INT NOT NULL,
            target_uid INT NOT NULL,
            furnace_no TINYINT NOT NULL,
            batch_ts INT NOT NULL,
            reduce_seconds INT NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_once (helper_uid, target_uid, furnace_no, batch_ts),
            KEY idx_target_created (target_uid, created_at),
            KEY idx_helper_created (helper_uid, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_炼丹添火记录'
        """
    )

    await cursor.execute(
        """
        SELECT COUNT(1)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'user_role'
          AND COLUMN_NAME = 'pill_usage'
        """
    )
    if (await cursor.fetchone())[0] == 0:
        await cursor.execute(
            """
            ALTER TABLE user_role
            ADD COLUMN pill_usage JSON NULL DEFAULT NULL COMMENT '丹药使用计数'
            """
        )

    await cursor.execute(
        """
        SELECT COUNT(1)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'data_herb'
          AND COLUMN_NAME = 'item_id'
        """
    )
    if (await cursor.fetchone())[0] == 0:
        await cursor.execute("ALTER TABLE data_herb ADD COLUMN item_id INT NULL DEFAULT NULL")

    await cursor.execute(
        """
        SELECT COUNT(1)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'data_pill'
          AND COLUMN_NAME = 'item_id'
        """
    )
    if (await cursor.fetchone())[0] == 0:
        await cursor.execute("ALTER TABLE data_pill ADD COLUMN item_id INT NULL DEFAULT NULL")

    await cursor.execute(
        """
        SELECT COUNT(1)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'user_liandan_fire_daily'
          AND COLUMN_NAME = 'help_used_times'
        """
    )
    if (await cursor.fetchone())[0] == 0:
        await cursor.execute("ALTER TABLE user_liandan_fire_daily ADD COLUMN help_used_times INT NOT NULL DEFAULT 0")

    await cursor.execute(
        """
        SELECT COUNT(1)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'user_liandan_fire_daily'
          AND COLUMN_NAME = 'be_helped_times'
        """
    )
    if (await cursor.fetchone())[0] == 0:
        await cursor.execute("ALTER TABLE user_liandan_fire_daily ADD COLUMN be_helped_times INT NOT NULL DEFAULT 0")

    _YAOYUAN_SCHEMA_READY = True


async def _init_yaotian(uid, cursor):
    await cursor.execute("SELECT uid FROM user_yaotian WHERE uid = %s LIMIT 1", (uid,))
    if await cursor.fetchone():
        return

    fields = []
    values = [uid]
    for idx in range(1, FARM_SLOT_COUNT + 1):
        fields.append(f"yt_{idx}")
        if idx <= FARM_UNLOCK_BASE_OPEN:
            values.append(_json_dumps(_empty_farm_slot()))
        else:
            values.append(None)

    placeholders = ", ".join(["%s"] * len(values))
    sql = f"INSERT INTO user_yaotian (uid, {', '.join(fields)}) VALUES ({placeholders})"
    await cursor.execute(sql, tuple(values))


async def _init_danlu(uid, cursor):
    await cursor.execute("SELECT uid FROM user_danlu WHERE uid = %s LIMIT 1", (uid,))
    if await cursor.fetchone():
        return

    fields = []
    values = [uid]
    for idx in range(1, FURNACE_SLOT_COUNT + 1):
        fields.append(f"dl_{idx}")
        if idx == 1:
            values.append(_json_dumps(_empty_furnace_slot()))
        else:
            values.append(None)
    placeholders = ", ".join(["%s"] * len(values))
    sql = f"INSERT INTO user_danlu (uid, {', '.join(fields)}) VALUES ({placeholders})"
    await cursor.execute(sql, tuple(values))


def _row_to_slots(row, prefix, count):
    if not row:
        return [None] * count
    slots = []
    for idx in range(1, count + 1):
        slots.append(_json_loads(row.get(f"{prefix}_{idx}")))
    return slots


async def _fetch_yaotian_slots(uid, cursor, for_update=False):
    if for_update:
        sql = """
        SELECT yt_1, yt_2, yt_3, yt_4, yt_5, yt_6, yt_7, yt_8, yt_9, yt_10, yt_11, yt_12
        FROM user_yaotian
        WHERE uid = %s
        FOR UPDATE
        """
    else:
        sql = """
        SELECT yt_1, yt_2, yt_3, yt_4, yt_5, yt_6, yt_7, yt_8, yt_9, yt_10, yt_11, yt_12
        FROM user_yaotian
        WHERE uid = %s
        LIMIT 1
        """
    await cursor.execute(sql, (uid,))
    raw = await cursor.fetchone()
    if not raw:
        return None
    row = {f"yt_{idx + 1}": raw[idx] for idx in range(FARM_SLOT_COUNT)}
    return _row_to_slots(row, "yt", FARM_SLOT_COUNT)


async def _fetch_danlu_slots(uid, cursor, for_update=False):
    if for_update:
        sql = """
        SELECT dl_1, dl_2, dl_3, dl_4, dl_5
        FROM user_danlu
        WHERE uid = %s
        FOR UPDATE
        """
    else:
        sql = """
        SELECT dl_1, dl_2, dl_3, dl_4, dl_5
        FROM user_danlu
        WHERE uid = %s
        LIMIT 1
        """
    await cursor.execute(sql, (uid,))
    raw = await cursor.fetchone()
    if not raw:
        return None
    row = {f"dl_{idx + 1}": raw[idx] for idx in range(FURNACE_SLOT_COUNT)}
    slots = _row_to_slots(row, "dl", FURNACE_SLOT_COUNT)
    for idx, slot in enumerate(slots):
        if slot is None:
            continue
        slot.setdefault("is_lz", 0)
        slot.setdefault("df_id", 0)
        slot.setdefault("time", 0)
        slot.setdefault("fire_count", 0)
        slot.setdefault("batch_ts", int(slot.get("time", 0)))
        slots[idx] = slot
    return slots


async def _save_slots(uid, slots, cursor, table, prefix, changed_indices=None):
    updates = []
    values = []
    if changed_indices is None:
        changed_indices = list(range(1, len(slots) + 1))
    for idx in changed_indices:
        col = f"{prefix}_{idx}"
        val = slots[idx - 1]
        updates.append(f"{col} = %s")
        values.append(None if val is None else _json_dumps(val))
    values.append(uid)
    sql = f"UPDATE {table} SET {', '.join(updates)} WHERE uid = %s"
    await cursor.execute(sql, tuple(values))


async def _sync_danlu_level_unlock(uid, cursor, slots=None):
    max_level = await _get_max_role_level(cursor, uid)
    if slots is None:
        slots = await _fetch_danlu_slots(uid, cursor, for_update=True)

    unlocked = []
    changed = []
    for danlu_no, need_level in DANLU_LEVEL_UNLOCK.items():
        idx = danlu_no - 1
        if max_level >= need_level and slots[idx] is None:
            slots[idx] = _empty_furnace_slot()
            unlocked.append(danlu_no)
            changed.append(danlu_no)

    if changed:
        await _save_slots(uid, slots, cursor, "user_danlu", "dl", changed)

    return slots, unlocked, max_level


async def _lock_fire_daily_rows(cursor, uid_list, stat_date):
    uid_set = sorted({int(x) for x in uid_list if int(x) > 0})
    if not uid_set:
        return {}

    for one_uid in uid_set:
        await cursor.execute(
            """
            INSERT INTO user_liandan_fire_daily (uid, stat_date, help_used_times, be_helped_times)
            VALUES (%s, %s, 0, 0)
            ON DUPLICATE KEY UPDATE uid = VALUES(uid)
            """,
            (one_uid, stat_date),
        )

    placeholders = ", ".join(["%s"] * len(uid_set))
    await cursor.execute(
        f"""
        SELECT uid, help_used_times, be_helped_times
        FROM user_liandan_fire_daily
        WHERE stat_date = %s AND uid IN ({placeholders})
        FOR UPDATE
        """,
        tuple([stat_date] + uid_set),
    )
    rows = await cursor.fetchall()
    result = {}
    for row in rows:
        result[int(row[0])] = {
            "help_used_times": int(row[1] or 0),
            "be_helped_times": int(row[2] or 0),
        }
    for one_uid in uid_set:
        result.setdefault(one_uid, {"help_used_times": 0, "be_helped_times": 0})
    return result


async def _get_fire_daily_stats(cursor, uid, stat_date):
    await cursor.execute(
        """
        SELECT help_used_times, be_helped_times
        FROM user_liandan_fire_daily
        WHERE uid = %s AND stat_date = %s
        LIMIT 1
        """,
        (uid, stat_date),
    )
    row = await cursor.fetchone()
    if not row:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)


def _split_ids(raw_ids):
    if raw_ids is None:
        return []
    result = []
    for part in str(raw_ids).split("|"):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


def _calc_effect_increment(attr_key, current_value, effect_value, is_percent):
    if attr_key in ROLE_RATE_ATTRS:
        if is_percent:
            # RATE_ATTRS 数据库存储为「百分比*100」：
            # 1) 常规写法：0.1 表示 +0.1%
            # 2) 兼容写法：0.001 表示 +0.1%（比例写法）
            if abs(effect_value) <= 0.01:
                effect_value = effect_value * 100
            return int(round(effect_value * 100))
        return int(round(effect_value))
    if attr_key in ROLE_BASE_ATTRS:
        if is_percent:
            return int(round(current_value * effect_value / 100))
        return int(round(effect_value))
    return 0


async def _get_seed_by_name(cursor, seed_name):
    await cursor.execute(
        "SELECT id, name, cl_id, cl_name, price, tier, world FROM data_seed WHERE name = %s LIMIT 1",
        (seed_name,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "cl_id": row[2],
        "cl_name": row[3],
        "price": row[4],
        "tier": row[5],
        "world": row[6] or "",
    }


async def _get_seed_map(cursor, seed_ids):
    if not seed_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(seed_ids))
    await cursor.execute(
        f"SELECT id, name, cl_id, cl_name, price, tier, world FROM data_seed WHERE id IN ({placeholders})",
        tuple(seed_ids),
    )
    rows = await cursor.fetchall()
    result = {}
    for row in rows:
        result[int(row[0])] = {
            "id": row[0],
            "name": row[1],
            "cl_id": row[2],
            "cl_name": row[3],
            "price": row[4],
            "tier": row[5],
            "world": row[6] or "",
        }
    return result


async def _get_herb_map(cursor, herb_ids):
    if not herb_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(herb_ids))
    await cursor.execute(
        f"""
        SELECT id, name, description, sell_price, tier, world, item_id
        FROM data_herb
        WHERE id IN ({placeholders})
        """,
        tuple(herb_ids),
    )
    rows = await cursor.fetchall()
    result = {}
    for row in rows:
        result[int(row[0])] = {
            "id": row[0],
            "name": row[1],
            "description": row[2] or "",
            "sell_price": row[3] or 0,
            "tier": row[4] or 1,
            "world": row[5] or "",
            "item_id": row[6],
        }
    return result


async def _get_herb_by_name(cursor, herb_name):
    await cursor.execute(
        """
        SELECT id, name, description, sell_price, tier, world, item_id
        FROM data_herb
        WHERE name = %s
        LIMIT 1
        """,
        (herb_name,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2] or "",
        "sell_price": row[3] or 0,
        "tier": row[4] or 1,
        "world": row[5] or "",
        "item_id": row[6],
    }


async def _get_recipe_by_name(cursor, recipe_name, role_world):
    await cursor.execute(
        """
        SELECT id, name, pill_id, ingredients, need_num, cost, category, world
        FROM data_recipe
        WHERE name = %s
          AND (world IS NULL OR world = '' OR world = %s)
        ORDER BY CASE WHEN world = %s THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (recipe_name, role_world, role_world),
    )
    row = await cursor.fetchone()
    if not row:
        # 兼容“炼丹 丹药名-炉号”输入：通过丹药名反查丹方
        await cursor.execute(
            """
            SELECT dr.id, dr.name, dr.pill_id, dr.ingredients, dr.need_num, dr.cost, dr.category, dr.world
            FROM data_recipe dr
            JOIN data_pill dp ON dp.id = dr.pill_id
            WHERE dp.name = %s
              AND (dr.world IS NULL OR dr.world = '' OR dr.world = %s)
            ORDER BY CASE WHEN dr.world = %s THEN 0 ELSE 1 END, dr.id ASC
            LIMIT 1
            """,
            (recipe_name, role_world, role_world),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "pill_id": row[2],
        "ingredients": row[3],
        "need_num": row[4] or 0,
        "cost": row[5] or 0,
        "category": row[6] or 1,
        "world": row[7] or "",
    }


async def _get_recipe_map(cursor, recipe_ids):
    if not recipe_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(recipe_ids))
    await cursor.execute(
        f"""
        SELECT id, name, pill_id, ingredients, need_num, cost, category, world
        FROM data_recipe
        WHERE id IN ({placeholders})
        """,
        tuple(recipe_ids),
    )
    rows = await cursor.fetchall()
    result = {}
    for row in rows:
        result[int(row[0])] = {
            "id": row[0],
            "name": row[1],
            "pill_id": row[2],
            "ingredients": row[3],
            "need_num": row[4] or 0,
            "cost": row[5] or 0,
            "category": row[6] or 1,
            "world": row[7] or "",
        }
    return result


async def _get_pill_by_id(cursor, pill_id):
    await cursor.execute(
        """
        SELECT id, name, description, effect_type, effect_value, is_percent, max_use, category, world, item_id
        FROM data_pill
        WHERE id = %s
        LIMIT 1
        """,
        (pill_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2] or "",
        "effect_type": row[3] or "",
        "effect_value": row[4] or "",
        "is_percent": row[5] or 0,
        "max_use": row[6] or 0,
        "category": row[7] or 1,
        "world": row[8] or "",
        "item_id": row[9],
    }


async def _get_pill_by_name(cursor, pill_name):
    await cursor.execute(
        """
        SELECT id, name, description, effect_type, effect_value, is_percent, max_use, category, world, item_id
        FROM data_pill
        WHERE name = %s
        LIMIT 1
        """,
        (pill_name,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2] or "",
        "effect_type": row[3] or "",
        "effect_value": row[4] or "",
        "is_percent": row[5] or 0,
        "max_use": row[6] or 0,
        "category": row[7] or 1,
        "world": row[8] or "",
        "item_id": row[9],
    }


# 查看药园
@reg_xz_func
async def ck_yaotian(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_yaotian(uid, cursor)
            role_info = await _get_current_role(cursor, uid)
            slots = await _fetch_yaotian_slots(uid, cursor, for_update=False)
            await conn.commit()

            if role_info is None:
                return {"type": "markdown", "content": "当前没有出战角色，请先出战角色后再查看药田。"}

            seed_ids = [slot.get("zz_id", 0) for slot in slots if slot and slot.get("is_zz") == 1]
            seed_map = await _get_seed_map(cursor, list(set(seed_ids)))

            lines = []
            lines.append("##### 🌿 药 园")
            lines.append(f"**当前角色：** [{role_info['id']}] {role_info['name']} Lv.{role_info['level']} [{role_info['world']}]")
            lines.append("***")

            now = int(time.time())
            mature_count = 0
            for idx, slot in enumerate(slots, 1):
                if slot is None:
                    cost = _farm_unlock_cost(idx)
                    lines.append(f"**药田{idx}** | 🔒 未解锁（{cost}仙玉）")
                    continue
                if int(slot.get("is_zz", 0)) == 0:
                    lines.append(f"**药田{idx}** | 空闲")
                    continue

                seed = seed_map.get(int(slot.get("zz_id", 0)))
                seed_name = seed["name"] if seed else f"未知种子#{slot.get('zz_id', 0)}"
                remain = FARM_MATURE_SECONDS - (now - int(slot.get("time", 0)))
                if remain <= 0:
                    mature_count += 1
                    lines.append(f"**药田{idx}** | {seed_name} | <qqbot-cmd-input text='采摘 {idx}' show='采摘：{seed_name}' />")
                else:
                    lines.append(f"**药田{idx}** | {seed_name} | ⏳ 剩余 {_format_seconds(remain)} <qqbot-cmd-input text='施肥 {idx}' show='培育：{seed_name}' />")

            lines.append("***")
            lines.append(f"> 已成熟药田：{mature_count} 块")
            lines.append("<qqbot-cmd-input text='一键采摘' show='一键采摘' /> | <qqbot-cmd-input text='种子背包' show='种子背包' />")
            lines.append("<qqbot-cmd-input text='种子商店' show='种子商店' /> | <qqbot-cmd-input text='播种 ' show='播种*' />")
            lines.append("<qqbot-cmd-input text='解锁药田 ' show='解锁药田*' /> | <qqbot-cmd-input text='施肥 ' show='施肥*' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 种子商店
@reg_xz_func
async def zz_shangdian(uid, qz, param):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            role_info = await _get_current_role(cursor, uid)
            if role_info is None:
                return {"type": "markdown", "content": "当前没有出战角色，请先出战角色后再查看种子商店。"}

            world, page = _parse_world_or_page(param, role_info["world"])
            page = max(1, page)

            await cursor.execute("SELECT COUNT(1) FROM data_seed WHERE world = %s", (world,))
            total_count = int((await cursor.fetchone())[0] or 0)
            if total_count == 0:
                await cursor.execute("SELECT DISTINCT world FROM data_seed WHERE world IS NOT NULL AND world <> '' ORDER BY id")
                worlds = [row[0] for row in await cursor.fetchall()]
                if not worlds:
                    return {"type": "markdown", "content": "种子商店暂无配置数据，请先导入 data_seed。"}
                if world != role_info["world"]:
                    return {"type": "markdown", "content": f"未找到【{world}】的种子数据。可用世界：{'、'.join(worlds)}"}
                world = worlds[0]
                await cursor.execute("SELECT COUNT(1) FROM data_seed WHERE world = %s", (world,))
                total_count = int((await cursor.fetchone())[0] or 0)

            total_pages = max(1, math.ceil(total_count / SEED_PAGE_SIZE))
            page = min(page, total_pages)
            offset = (page - 1) * SEED_PAGE_SIZE

            await cursor.execute(
                """
                SELECT id, name, cl_name, cl_id, price, tier, world
                FROM data_seed
                WHERE world = %s
                ORDER BY tier ASC, id ASC
                LIMIT %s OFFSET %s
                """,
                (world, SEED_PAGE_SIZE, offset),
            )
            seeds = await cursor.fetchall()

            await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s LIMIT 1", (uid,))
            lingshi = int((await cursor.fetchone() or [0])[0] or 0)

            await conn.commit()

            lines = []
            lines.append(f"##### 种子商店（第{page}/{total_pages}页）")
            lines.append(f"> 当前世界：{world}")
            lines.append(f"> 当前灵石：{lingshi}")
            lines.append("***")
            for row in seeds:
                seed_id, seed_name, _, _, price, tier, _ = row
                lines.append(f"[{seed_id}] {seed_name} | {TIER_NAME.get(tier, f'品阶{tier}')} | {price}灵石")
                lines.append(f"> <qqbot-cmd-input text='购买种子 {seed_name}-1' show='购买×1' /> | <qqbot-cmd-input text='购买种子 {seed_name}-5' show='购买×5' />")

            lines.append("***")
            prev_page = max(1, page - 1)
            next_page = min(total_pages, page + 1)
            lines.append(pagination_controls("种子商店", page, total_pages))
            lines.append("<qqbot-cmd-input text='丹方列表 ' show='丹方列表' /> | <qqbot-cmd-input text='种子背包' show='种子背包' />")
            lines.append("<qqbot-cmd-input text='种子商店 斗破苍穹' show='种子商店 斗破苍穹' /> | <qqbot-cmd-input text='种子商店 仙逆' show='种子商店 仙逆' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 种子背包
@reg_xz_func
async def zz_beibao(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await cursor.execute(
                """
                SELECT usb.zz_id, usb.zz_num, ds.name, ds.tier, ds.world
                FROM user_seed_bag usb
                JOIN data_seed ds ON ds.id = usb.zz_id
                WHERE usb.uid = %s AND usb.zz_num > 0
                ORDER BY ds.world ASC, ds.tier ASC, ds.id ASC
                """,
                (uid,),
            )
            rows = await cursor.fetchall()
            await conn.commit()

            if not rows:
                lines = []
                lines.append("##### 种子背包")
                lines.append("> 你的种子背包为空。")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='种子商店' show='种子商店' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            lines = []
            lines.append("##### 种子背包")
            lines.append("***")
            for row in rows:
                _, zz_num, seed_name, tier, world = row
                lines.append(f"{seed_name} | {world}·{TIER_NAME.get(tier, f'品阶{tier}')} | 数量 {zz_num}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='种子商店' show='种子商店' /> | <qqbot-cmd-input text='一键播种 ' show='一键播种*' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 出售药材
@reg_xz_func
async def sell_herb(uid, qz, param):
    param = str(param).strip()
    if not param:
        return {"type": "markdown", "content": "指令错误，正确指令：出售药材 药材名-数量\n示例：出售药材 冰灵焰草-10"}

    if "-" in param:
        herb_name, sell_num = _parse_name_num(param)
        if not herb_name or not sell_num or sell_num <= 0:
            return {"type": "markdown", "content": "指令错误，正确指令：出售药材 药材名-数量\n示例：出售药材 冰灵焰草-10"}
    else:
        herb_name = param
        sell_num = 1

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            herb = await _get_herb_by_name(cursor, herb_name)
            if herb is None:
                return {"type": "markdown", "content": f"未找到药材：{herb_name}"}
            if int(herb["sell_price"] or 0) <= 0:
                return {"type": "markdown", "content": f"{herb['name']} 当前不可出售。"}

            herb_item_id = _resolve_item_id(herb["id"], herb)
            ok = await _deduct_user_item(cursor, uid, herb_item_id, sell_num)
            if not ok:
                await conn.rollback()
                return {"type": "markdown", "content": f"药材不足：{herb['name']} x {sell_num}"}

            gain_lingshi = int(herb["sell_price"]) * sell_num
            await cursor.execute(
                "UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s",
                (gain_lingshi, uid),
            )
            await conn.commit()

            await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s LIMIT 1", (uid,))
            now_lingshi = int((await cursor.fetchone() or [0])[0] or 0)

            lines = []
            lines.append("##### 药材出售成功")
            lines.append(f"出售药材：{herb['name']} x {sell_num}")
            lines.append(f"获得灵石：{gain_lingshi}")
            lines.append(f"当前灵石：{now_lingshi}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='物品背包' show='物品背包' /> | <qqbot-cmd-input text='出售药材 ' show='继续出售*' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 购买种子
@reg_xz_func
async def gm_zhongzi(uid, qz, param):
    seed_name, buy_num = _parse_name_num(param)
    if not seed_name or not buy_num or buy_num <= 0:
        return {"type": "markdown", "content": "指令错误，正确指令：购买种子 种子名-数量\n示例：购买种子 冰灵焰草种子-5"}

    if buy_num > 9999:
        return {"type": "markdown", "content": "单次购买数量过大，请分批购买（<=9999）。"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            seed = await _get_seed_by_name(cursor, seed_name)
            if seed is None:
                return {"type": "markdown", "content": f"未找到种子：{seed_name}"}

            total_cost = int(seed["price"]) * buy_num
            await cursor.execute(
                """
                UPDATE user_zt
                SET lingshi = lingshi - %s
                WHERE id = %s AND lingshi >= %s
                """,
                (total_cost, uid, total_cost),
            )
            if cursor.rowcount <= 0:
                await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s LIMIT 1", (uid,))
                cur_lingshi = int((await cursor.fetchone() or [0])[0] or 0)
                await conn.rollback()
                return {
                    "type": "markdown",
                    "content": f"灵石不足，无法购买。\n需要灵石：{total_cost}\n当前灵石：{cur_lingshi}",
                }

            await cursor.execute(
                """
                INSERT INTO user_seed_bag (uid, zz_id, zz_num)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE zz_num = zz_num + VALUES(zz_num)
                """,
                (uid, seed["id"], buy_num),
            )
            await conn.commit()

            await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s LIMIT 1", (uid,))
            left_lingshi = int((await cursor.fetchone() or [0])[0] or 0)

            lines = []
            lines.append("##### 购买成功")
            lines.append(f"获得种子：{seed['name']} x {buy_num}")
            lines.append(f"消耗灵石：{total_cost}")
            lines.append(f"剩余灵石：{left_lingshi}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='种子背包' show='种子背包' /> | <qqbot-cmd-input text='播种 ' show='播种*' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 播种
@reg_xz_func
async def bo_zhong(uid, qz, param):
    seed_name, plot_no = _parse_name_slot(param)
    if not seed_name or not plot_no:
        return {"type": "markdown", "content": "指令错误，正确指令：播种 种子名-田号\n示例：播种 冰灵焰草种子-1"}
    if plot_no < 1 or plot_no > FARM_SLOT_COUNT:
        return {"type": "markdown", "content": f"田号错误，仅支持 1-{FARM_SLOT_COUNT}。"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_yaotian(uid, cursor)

            seed = await _get_seed_by_name(cursor, seed_name)
            if seed is None:
                return {"type": "markdown", "content": f"未找到种子：{seed_name}"}

            slots = await _fetch_yaotian_slots(uid, cursor, for_update=True)
            slot = slots[plot_no - 1]
            if slot is None:
                cost = _farm_unlock_cost(plot_no)
                return {"type": "markdown", "content": f"药田{plot_no}未解锁，请先解锁（需{cost}仙玉）。"}

            if int(slot.get("is_zz", 0)) == 1:
                return {"type": "markdown", "content": f"药田{plot_no}正在种植中，请先采摘后再播种。"}

            await cursor.execute(
                """
                UPDATE user_seed_bag
                SET zz_num = zz_num - 1
                WHERE uid = %s AND zz_id = %s AND zz_num >= 1
                """,
                (uid, seed["id"]),
            )
            if cursor.rowcount <= 0:
                await conn.rollback()
                return {"type": "markdown", "content": f"种子不足：{seed['name']}"}

            await cursor.execute(
                "DELETE FROM user_seed_bag WHERE uid = %s AND zz_id = %s AND zz_num <= 0",
                (uid, seed["id"]),
            )

            slot["is_zz"] = 1
            slot["zz_id"] = int(seed["id"])
            slot["time"] = int(time.time())
            slots[plot_no - 1] = slot
            await _save_slots(uid, slots, cursor, "user_yaotian", "yt", [plot_no])
            await conn.commit()
            from Game_main.g16_onboarding import record_onboarding_event
            await record_onboarding_event(uid, "FARM")
            from Game_main.g25_daily_tasks import record_daily_event
            await record_daily_event(uid, "FARM")

            lines = []
            lines.append("##### 播种成功")
            lines.append(f"药田{plot_no} 已播种：{seed['name']}")
            lines.append(f"预计成熟：{_format_seconds(FARM_MATURE_SECONDS)}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='药园' show='药园' /> | <qqbot-cmd-input text='一键播种 ' show='一键播种*' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 一键播种
@reg_xz_func
async def yj_bozhong(uid, qz, seed_name):
    seed_name = str(seed_name).strip()
    if not seed_name:
        return {"type": "markdown", "content": "指令错误，正确指令：一键播种 种子名\n示例：一键播种 冰灵焰草种子"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_yaotian(uid, cursor)

            seed = await _get_seed_by_name(cursor, seed_name)
            if seed is None:
                return {"type": "markdown", "content": f"未找到种子：{seed_name}"}

            slots = await _fetch_yaotian_slots(uid, cursor, for_update=True)
            empty_indices = []
            for idx, slot in enumerate(slots, 1):
                if slot is None:
                    continue
                if int(slot.get("is_zz", 0)) == 0:
                    empty_indices.append(idx)

            if not empty_indices:
                return {"type": "markdown", "content": "当前没有空闲药田可播种。"}

            await cursor.execute(
                "SELECT zz_num FROM user_seed_bag WHERE uid = %s AND zz_id = %s FOR UPDATE",
                (uid, seed["id"]),
            )
            seed_row = await cursor.fetchone()
            own_num = int(seed_row[0]) if seed_row else 0
            if own_num <= 0:
                return {"type": "markdown", "content": f"种子不足：{seed['name']}"}

            plant_num = min(len(empty_indices), own_num)
            now_ts = int(time.time())
            changed = []
            for idx in empty_indices[:plant_num]:
                slots[idx - 1] = {"is_zz": 1, "zz_id": int(seed["id"]), "time": now_ts}
                changed.append(idx)

            await _save_slots(uid, slots, cursor, "user_yaotian", "yt", changed)
            await cursor.execute(
                "UPDATE user_seed_bag SET zz_num = zz_num - %s WHERE uid = %s AND zz_id = %s",
                (plant_num, uid, seed["id"]),
            )
            await cursor.execute(
                "DELETE FROM user_seed_bag WHERE uid = %s AND zz_id = %s AND zz_num <= 0",
                (uid, seed["id"]),
            )
            await conn.commit()

            lines = []
            lines.append("##### 一键播种完成")
            lines.append(f"种子：{seed['name']}")
            lines.append(f"播种药田数量：{plant_num}")
            lines.append(f"预计成熟：{_format_seconds(FARM_MATURE_SECONDS)}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='药园' show='药园' /> | <qqbot-cmd-input text='种子背包' show='种子背包' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 采摘
@reg_xz_func
async def cai_zhai(uid, qz, param):
    plot_no = _parse_index(param)
    if not plot_no:
        return {"type": "markdown", "content": "指令错误，正确指令：采摘 田号\n示例：采摘 1"}
    if plot_no < 1 or plot_no > FARM_SLOT_COUNT:
        return {"type": "markdown", "content": f"田号错误，仅支持 1-{FARM_SLOT_COUNT}。"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_yaotian(uid, cursor)
            slots = await _fetch_yaotian_slots(uid, cursor, for_update=True)
            slot = slots[plot_no - 1]
            if slot is None:
                return {"type": "markdown", "content": f"药田{plot_no}尚未解锁。"}
            if int(slot.get("is_zz", 0)) == 0:
                return {"type": "markdown", "content": f"药田{plot_no}为空，暂无可采摘作物。"}

            now_ts = int(time.time())
            remain = FARM_MATURE_SECONDS - (now_ts - int(slot.get("time", 0)))
            if remain > 0:
                return {"type": "markdown", "content": f"药田{plot_no}尚未成熟，还需 {_format_seconds(remain)}。"}

            seed_map = await _get_seed_map(cursor, [int(slot.get("zz_id", 0))])
            seed = seed_map.get(int(slot.get("zz_id", 0)))
            if not seed:
                return {"type": "markdown", "content": "播种数据异常：找不到对应种子配置。"}

            herb_map = await _get_herb_map(cursor, [int(seed["cl_id"])])
            herb = herb_map.get(int(seed["cl_id"]))
            herb_item_id = _resolve_item_id(seed["cl_id"], herb)
            herb_name = herb["name"] if herb else seed["cl_name"]
            tier = int(seed["tier"] or 1)
            low, high = TIER_OUTPUT_RANGE.get(tier, (1, 3))
            drop_num = random.randint(low, high)

            await _add_user_item(cursor, uid, herb_item_id, drop_num)

            slots[plot_no - 1] = _empty_farm_slot()
            await _save_slots(uid, slots, cursor, "user_yaotian", "yt", [plot_no])
            await conn.commit()

            lines = []
            lines.append("##### 采摘成功")
            lines.append(f"药田{plot_no}：{seed['name']}")
            lines.append(f"获得药材：{herb_name} x {drop_num}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='药园' show='药园' /> | <qqbot-cmd-input text='播种 ' show='继续播种*' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 一键采摘
@reg_xz_func
async def yj_caizhai(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_yaotian(uid, cursor)
            slots = await _fetch_yaotian_slots(uid, cursor, for_update=True)

            now_ts = int(time.time())
            planted_seed_ids = []
            for slot in slots:
                if slot and int(slot.get("is_zz", 0)) == 1:
                    planted_seed_ids.append(int(slot.get("zz_id", 0)))
            seed_map = await _get_seed_map(cursor, list(set(planted_seed_ids)))
            herb_ids = [seed_map[sid]["cl_id"] for sid in seed_map if seed_map[sid]]
            herb_map = await _get_herb_map(cursor, list(set(herb_ids)))

            changed = []
            drops = []
            nearest_remain = None

            for idx, slot in enumerate(slots, 1):
                if slot is None or int(slot.get("is_zz", 0)) == 0:
                    continue
                remain = FARM_MATURE_SECONDS - (now_ts - int(slot.get("time", 0)))
                if remain > 0:
                    if nearest_remain is None or remain < nearest_remain:
                        nearest_remain = remain
                    continue

                seed = seed_map.get(int(slot.get("zz_id", 0)))
                if not seed:
                    continue
                herb = herb_map.get(int(seed["cl_id"]))
                herb_item_id = _resolve_item_id(seed["cl_id"], herb)
                herb_name = herb["name"] if herb else seed["cl_name"]
                tier = int(seed["tier"] or 1)
                low, high = TIER_OUTPUT_RANGE.get(tier, (1, 3))
                drop_num = random.randint(low, high)

                await _add_user_item(cursor, uid, herb_item_id, drop_num)
                drops.append((idx, herb_name, drop_num))
                slots[idx - 1] = _empty_farm_slot()
                changed.append(idx)

            if not drops:
                await conn.rollback()
                if nearest_remain is not None:
                    return {"type": "markdown", "content": f"当前没有成熟药田，最近一块还需 {_format_seconds(nearest_remain)}。"}
                return {"type": "markdown", "content": "当前没有可采摘的药田。"}

            await _save_slots(uid, slots, cursor, "user_yaotian", "yt", changed)
            await conn.commit()

            lines = []
            lines.append("##### 一键采摘完成")
            lines.append(f"采摘药田数量：{len(drops)}")
            lines.append("***")
            for idx, herb_name, drop_num in drops:
                lines.append(f"药田{idx}：{herb_name} x {drop_num}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='药园' show='药园' /> | <qqbot-cmd-input text='一键播种 ' show='一键播种*' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 解锁药田
@reg_xz_func
async def js_yaotian(uid, qz, param):
    plot_no = _parse_index(param)
    if not plot_no:
        return {"type": "markdown", "content": "指令错误，正确指令：解锁药田 田号\n示例：解锁药田 6"}
    if plot_no < 1 or plot_no > FARM_SLOT_COUNT:
        return {"type": "markdown", "content": f"田号错误，仅支持 1-{FARM_SLOT_COUNT}。"}

    if plot_no <= FARM_UNLOCK_BASE_OPEN:
        return {"type": "markdown", "content": f"药田{plot_no}为初始药田，无需解锁。"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_yaotian(uid, cursor)
            slots = await _fetch_yaotian_slots(uid, cursor, for_update=True)
            if slots[plot_no - 1] is not None:
                return {"type": "markdown", "content": f"药田{plot_no}已解锁。"}

            for idx in range(FARM_UNLOCK_BASE_OPEN + 1, plot_no):
                if slots[idx - 1] is None:
                    return {"type": "markdown", "content": f"请先解锁药田{idx}，再解锁药田{plot_no}。"}

            cost = _farm_unlock_cost(plot_no)
            await cursor.execute(
                "UPDATE user_zt SET xianyu = xianyu - %s WHERE id = %s AND xianyu >= %s",
                (cost, uid, cost),
            )
            if cursor.rowcount <= 0:
                await cursor.execute("SELECT xianyu FROM user_zt WHERE id = %s LIMIT 1", (uid,))
                cur_xy = int((await cursor.fetchone() or [0])[0] or 0)
                await conn.rollback()
                return {"type": "markdown", "content": f"仙玉不足，解锁药田{plot_no}需要{cost}仙玉，当前仅有{cur_xy}。"}

            slots[plot_no - 1] = _empty_farm_slot()
            await _save_slots(uid, slots, cursor, "user_yaotian", "yt", [plot_no])
            await conn.commit()

            lines = []
            lines.append("##### 解锁成功")
            lines.append(f"已解锁药田{plot_no}")
            lines.append(f"消耗仙玉：{cost}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='药园' show='药园' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 施肥
@reg_xz_func
async def shi_fei(uid, qz, param):
    plot_no = _parse_index(param)
    if not plot_no:
        return {"type": "markdown", "content": "指令错误，正确指令：施肥 田号\n示例：施肥 1"}
    if plot_no < 1 or plot_no > FARM_SLOT_COUNT:
        return {"type": "markdown", "content": f"田号错误，仅支持 1-{FARM_SLOT_COUNT}。"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_yaotian(uid, cursor)
            slots = await _fetch_yaotian_slots(uid, cursor, for_update=True)
            slot = slots[plot_no - 1]
            if slot is None:
                return {"type": "markdown", "content": f"药田{plot_no}未解锁，无法施肥。"}
            if int(slot.get("is_zz", 0)) == 0:
                return {"type": "markdown", "content": f"药田{plot_no}当前为空，无法施肥。"}

            now_ts = int(time.time())
            if now_ts - int(slot.get("time", 0)) >= FARM_MATURE_SECONDS:
                return {"type": "markdown", "content": f"药田{plot_no}已经成熟，无需施肥。"}

            # 旧版“植物肥料”仍可继续使用；商城新售卖“灵草培育液”。
            ok = await _deduct_user_item(cursor, uid, FERTILIZER_ITEM_ID, 1)
            used_item_name = "灵草培育液"
            if not ok:
                ok = await _deduct_user_item(cursor, uid, LEGACY_FERTILIZER_ITEM_ID, 1)
                used_item_name = "植物肥料"
            if not ok:
                await conn.rollback()
                return {"type": "markdown", "content": "缺少道具：灵草培育液或植物肥料 x1。可发送“商城”购买灵草培育液。"}

            slot["time"] = now_ts - FARM_MATURE_SECONDS
            slots[plot_no - 1] = slot
            await _save_slots(uid, slots, cursor, "user_yaotian", "yt", [plot_no])
            await conn.commit()

            lines = []
            lines.append("##### 施肥成功")
            lines.append(f"药田{plot_no}已立即成熟，可直接采摘。")
            lines.append(f"消耗：{used_item_name} x1")
            lines.append("***")
            lines.append(f"<qqbot-cmd-input text='采摘 {plot_no}' show='采摘 {plot_no}' /> | <qqbot-cmd-input text='药园' show='药园' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 查看丹炉
@reg_xz_func
async def ck_danlu(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_danlu(uid, cursor)
            slots = await _fetch_danlu_slots(uid, cursor, for_update=True)
            slots, auto_unlocked, max_level = await _sync_danlu_level_unlock(uid, cursor, slots)
            await conn.commit()
            role_info = await _get_current_role(cursor, uid)

            recipe_ids = [int(slot.get("df_id", 0)) for slot in slots if slot and int(slot.get("is_lz", 0)) == 1]
            recipe_map = await _get_recipe_map(cursor, list(set(recipe_ids)))

            now_ts = int(time.time())
            lines = []
            lines.append("##### 🔥 丹 炉")
            if role_info:
                lines.append(f"**当前角色：** [{role_info['id']}] {role_info['name']} Lv.{role_info['level']} [{role_info['world']}]")
            lines.append(f"**账号最高角色等级：** Lv.{max_level}")
            if auto_unlocked:
                lines.append(f"🎉 自动解锁丹炉：{','.join(str(x) for x in auto_unlocked)}")
            lines.append("***")

            for idx, slot in enumerate(slots, 1):
                if slot is None:
                    if idx in DANLU_LEVEL_UNLOCK:
                        lines.append(f"**丹炉{idx}** | 🔒 未解锁（任一角色达到Lv.{DANLU_LEVEL_UNLOCK[idx]}自动解锁）")
                    else:
                        lines.append(f"**丹炉{idx}** | 🔒 未解锁（{DANLU_XIANYU_UNLOCK.get(idx, 0)}仙玉）")
                    continue

                if int(slot.get("is_lz", 0)) == 0:
                    lines.append(f"**丹炉{idx}** | 空闲")
                    continue

                recipe = recipe_map.get(int(slot.get("df_id", 0)))
                recipe_name = recipe["name"] if recipe else f"未知丹方#{slot.get('df_id', 0)}"
                remain = ALCHEMY_SECONDS - (now_ts - int(slot.get("time", 0)))
                fire_count = int(slot.get("fire_count", 0))
                if remain <= 0:
                    lines.append(f"**丹炉{idx}** | {recipe_name}")
                    lines.append(f"> ✅ 炼制完成 <qqbot-cmd-input text='收丹 {idx}' show='收取：{recipe_name}' />")
                else:
                    lines.append(f"**丹炉{idx}** | {recipe_name}")
                    lines.append(f"> ⏳ 剩余 {_format_seconds(remain)} | <qqbot-cmd-input text='加速炼丹 {idx}' show='加速：{recipe_name}' /> | 帮其丹炉 <qqbot-cmd-input text='添火 {uid}-{idx}' show='添火助炼' />")

            lines.append("***")
            lines.append("<qqbot-cmd-input text='一键收丹' show='一键收丹' /> | <qqbot-cmd-input text='丹方列表' show='丹方列表' />")
            lines.append("<qqbot-cmd-input text='炼丹 ' show='炼丹*' /> | <qqbot-cmd-input text='收丹 ' show='收丹*' />")
            lines.append("<qqbot-cmd-input text='解锁丹炉 ' show='解锁丹炉*' /> | <qqbot-cmd-input text='加速炼丹 ' show='加速炼丹*' />")
            lines.append("<qqbot-cmd-input text='添火次数' show='添火次数' /> | <qqbot-cmd-input text='添火 ' show='添火 目标UID-炉号' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 丹方列表
@reg_xz_func
async def df_liebiao(uid, qz, param):
    page = _parse_index(param)
    if not page:
        page = 1
    page = max(1, page)

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            role_info = await _get_current_role(cursor, uid)
            if role_info is None:
                return {"type": "markdown", "content": "当前没有出战角色，请先出战角色后再查看丹方。"}

            await cursor.execute(
                """
                SELECT id, name, pill_id, ingredients, need_num, cost, category, world
                FROM data_recipe
                WHERE world IS NULL OR world = '' OR world = %s
                ORDER BY CASE WHEN world IS NULL OR world = '' THEN 0 ELSE 1 END, id ASC
                """,
                (role_info["world"],),
            )
            recipes = await cursor.fetchall()
            if not recipes:
                return {"type": "markdown", "content": "当前没有可用丹方，请联系管理员。"}

            total_pages = max(1, math.ceil(len(recipes) / RECIPE_PAGE_SIZE))
            page = min(page, total_pages)
            start = (page - 1) * RECIPE_PAGE_SIZE
            page_rows = recipes[start:start + RECIPE_PAGE_SIZE]

            herb_ids = []
            for row in page_rows:
                herb_ids.extend(_split_ids(row[3]))
            herb_map = await _get_herb_map(cursor, list(set(herb_ids)))

            await conn.commit()

            lines = []
            lines.append(f"##### 丹方列表（第{page}/{total_pages}页）")
            lines.append(f"> 当前世界：{role_info['world']}")
            lines.append("***")
            for row in page_rows:
                recipe_id, recipe_name, _, ingredients, need_num, cost, _, world = row
                item_world = "通用" if not world else f"{world}专属"
                ing_names = []
                for hid in _split_ids(ingredients):
                    herb = herb_map.get(hid)
                    ing_names.append(herb["name"] if herb else f"药材#{hid}")
                if not ing_names:
                    ing_text = "无原料配置"
                else:
                    ing_text = " + ".join(ing_names)
                lines.append(f"『{recipe_id}』 {recipe_name} | {item_world} <qqbot-cmd-input text='炼丹 {recipe_name}-' show='炼丹' />")
                lines.append(f"> 原料：{ing_text}（每种x{need_num}）| 炼制消耗：{cost}灵石\n")

            lines.append("> Tips：点击炼丹后记得输入丹炉号噢~")
            lines.append("***")
            prev_page = max(1, page - 1)
            next_page = min(total_pages, page + 1)
            lines.append(pagination_controls("丹方列表", page, total_pages))
            lines.append("<qqbot-cmd-input text='炼丹 ' show='炼丹*' /> | <qqbot-cmd-input text='查看丹炉' show='查看丹炉' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 炼丹
@reg_xz_func
async def lian_dan(uid, qz, param):
    recipe_or_pill_name, furnace_no, fire_style = _parse_alchemy_param(param)
    if not recipe_or_pill_name or not furnace_no:
        return {"type": "markdown", "content": "指令错误，正确指令：炼丹 丹方名-炉号（也支持丹药名）\n可选火候：炼丹 冒险-九转丹-1"}
    if furnace_no < 1 or furnace_no > FURNACE_SLOT_COUNT:
        return {"type": "markdown", "content": f"炉号错误，仅支持 1-{FURNACE_SLOT_COUNT}。"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_danlu(uid, cursor)
            role_info = await _get_current_role(cursor, uid)
            if role_info is None:
                return {"type": "markdown", "content": "当前没有出战角色，请先出战角色后再炼丹。"}

            slots = await _fetch_danlu_slots(uid, cursor, for_update=True)
            slots, _, _ = await _sync_danlu_level_unlock(uid, cursor, slots)
            slot = slots[furnace_no - 1]
            if slot is None:
                if furnace_no in DANLU_LEVEL_UNLOCK:
                    return {"type": "markdown", "content": f"丹炉{furnace_no}尚未解锁，需任一角色达到Lv.{DANLU_LEVEL_UNLOCK[furnace_no]}。"}
                return {"type": "markdown", "content": f"丹炉{furnace_no}尚未解锁，需{DANLU_XIANYU_UNLOCK.get(furnace_no, 0)}仙玉。"}

            if int(slot.get("is_lz", 0)) == 1:
                return {"type": "markdown", "content": f"丹炉{furnace_no}正在炼制中，请先收丹。"}

            role_world = role_info["world"]
            recipe = await _get_recipe_by_name(cursor, recipe_or_pill_name, role_world)
            if recipe is None:
                return {"type": "markdown", "content": f"未找到可炼制丹方/丹药：{recipe_or_pill_name}"}

            if recipe["world"] and recipe["world"] != role_world:
                return {
                    "type": "markdown",
                    "content": f"该丹方属于【{recipe['world']}】世界，当前出战角色世界为【{role_world}】，无法炼制。",
                }

            herb_ids = _split_ids(recipe["ingredients"])
            if not herb_ids:
                return {"type": "markdown", "content": f"丹方 {recipe['name']} 原料配置为空，请联系管理员。"}
            herb_map = await _get_herb_map(cursor, herb_ids)

            need_lingshi = int(recipe["cost"])
            await cursor.execute(
                """
                UPDATE user_zt
                SET lingshi = lingshi - %s
                WHERE id = %s AND lingshi >= %s
                """,
                (need_lingshi, uid, need_lingshi),
            )
            if cursor.rowcount <= 0:
                await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s LIMIT 1", (uid,))
                cur_lingshi = int((await cursor.fetchone() or [0])[0] or 0)
                await conn.rollback()
                return {"type": "markdown", "content": f"灵石不足，炼制需要{need_lingshi}，当前仅有{cur_lingshi}。"}

            need_num = int(recipe["need_num"])
            lack_msg = None
            for herb_id in herb_ids:
                herb = herb_map.get(herb_id)
                herb_item_id = _resolve_item_id(herb_id, herb)
                ok = await _deduct_user_item(cursor, uid, herb_item_id, need_num)
                if not ok:
                    herb_name = herb["name"] if herb else f"药材#{herb_id}"
                    lack_msg = f"药材不足：{herb_name} x {need_num}"
                    break

            if lack_msg:
                await conn.rollback()
                return {"type": "markdown", "content": f"炼丹失败，{lack_msg}"}

            now_ts = int(time.time())
            from Game_main.g18_alchemy_study import get_alchemy_mastery
            mastery = await get_alchemy_mastery(cursor, uid, recipe["name"])
            slots[furnace_no - 1] = {
                "is_lz": 1,
                "df_id": int(recipe["id"]),
                "time": now_ts,
                "fire_count": 0,
                "batch_ts": now_ts,
                "fire_style": fire_style,
                "mastery": mastery,
            }
            await _save_slots(uid, slots, cursor, "user_danlu", "dl", [furnace_no])
            await conn.commit()
            from Game_main.g18_alchemy_study import record_alchemy_start
            await record_alchemy_start(uid, recipe['name'])
            from Game_main.g16_onboarding import record_onboarding_event
            await record_onboarding_event(uid, "ALCHEMY")
            from Game_main.g25_daily_tasks import record_daily_event
            await record_daily_event(uid, "ALCHEMY")

            lines = []
            lines.append("##### 炼丹开始")
            lines.append(f"丹炉{furnace_no}：{recipe['name']}")
            lines.append(f"消耗灵石：{need_lingshi}")
            lines.append(f"炼制时长：{_format_seconds(ALCHEMY_SECONDS)}")
            lines.append(f"火候：{fire_style}｜当前熟练度：{mastery}")
            lines.append("成功率：保守95% / 均衡90% / 冒险83%")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='查看丹炉' show='查看丹炉' /> | <qqbot-cmd-input text='加速炼丹 ' show='加速炼丹*' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 收丹
@reg_xz_func
async def shou_dan(uid, qz, param):
    furnace_no = _parse_index(param)
    if not furnace_no:
        return {"type": "markdown", "content": "指令错误，正确指令：收丹 炉号\n示例：收丹 1"}
    if furnace_no < 1 or furnace_no > FURNACE_SLOT_COUNT:
        return {"type": "markdown", "content": f"炉号错误，仅支持 1-{FURNACE_SLOT_COUNT}。"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_danlu(uid, cursor)
            slots = await _fetch_danlu_slots(uid, cursor, for_update=True)
            slots, _, _ = await _sync_danlu_level_unlock(uid, cursor, slots)
            slot = slots[furnace_no - 1]
            if slot is None:
                return {"type": "markdown", "content": f"丹炉{furnace_no}未解锁。"}
            if int(slot.get("is_lz", 0)) == 0:
                return {"type": "markdown", "content": f"丹炉{furnace_no}当前空闲，没有可收取丹药。"}

            now_ts = int(time.time())
            remain = ALCHEMY_SECONDS - (now_ts - int(slot.get("time", 0)))
            if remain > 0:
                return {"type": "markdown", "content": f"丹炉{furnace_no}尚未完成，还需 {_format_seconds(remain)}。"}

            recipe_map = await _get_recipe_map(cursor, [int(slot.get("df_id", 0))])
            recipe = recipe_map.get(int(slot.get("df_id", 0)))
            if not recipe:
                return {"type": "markdown", "content": "丹炉数据异常：找不到对应丹方。"}

            pill = await _get_pill_by_id(cursor, int(recipe["pill_id"]))
            if not pill:
                return {"type": "markdown", "content": "丹炉数据异常：找不到对应丹药配置。"}

            from Game_main.g18_alchemy_study import roll_alchemy_outcome
            success, quality, output_num = roll_alchemy_outcome(
                slot.get("fire_style", "均衡"), slot.get("mastery", 0), random.randint(1, 100)
            )
            lines = []
            lines.append("##### 收丹结果")
            lines.append(f"丹炉{furnace_no} | {recipe['name']}")
            if success:
                pill_item_id = _resolve_item_id(pill["id"], pill)
                await _add_user_item(cursor, uid, pill_item_id, output_num)
                lines.append("炼制结果：✅ 成功")
                lines.append(f"火候品质：{quality}｜获得：{pill['name']} x {output_num}")
            else:
                lines.append("炼制结果：💥 炸炉")
                lines.append("材料尽失，无丹药产出")

            slots[furnace_no - 1] = _empty_furnace_slot()
            await _save_slots(uid, slots, cursor, "user_danlu", "dl", [furnace_no])
            await conn.commit()

            lines.append("***")
            lines.append("<qqbot-cmd-input text='查看丹炉' show='查看丹炉' /> | <qqbot-cmd-input text='一键收丹' show='一键收丹' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 一键收丹
@reg_xz_func
async def yj_shoudan(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_danlu(uid, cursor)
            slots = await _fetch_danlu_slots(uid, cursor, for_update=True)
            slots, _, _ = await _sync_danlu_level_unlock(uid, cursor, slots)

            now_ts = int(time.time())
            running_recipe_ids = []
            for slot in slots:
                if slot and int(slot.get("is_lz", 0)) == 1:
                    running_recipe_ids.append(int(slot.get("df_id", 0)))
            recipe_map = await _get_recipe_map(cursor, list(set(running_recipe_ids)))

            pill_ids = [recipe["pill_id"] for recipe in recipe_map.values()]
            pill_map = {}
            for pill_id in set(pill_ids):
                pill = await _get_pill_by_id(cursor, pill_id)
                if pill:
                    pill_map[int(pill_id)] = pill

            collected = []
            changed = []
            for idx, slot in enumerate(slots, 1):
                if slot is None or int(slot.get("is_lz", 0)) == 0:
                    continue
                remain = ALCHEMY_SECONDS - (now_ts - int(slot.get("time", 0)))
                if remain > 0:
                    continue

                recipe = recipe_map.get(int(slot.get("df_id", 0)))
                if not recipe:
                    slots[idx - 1] = _empty_furnace_slot()
                    changed.append(idx)
                    collected.append((idx, "未知丹方", False, "配置异常"))
                    continue

                pill = pill_map.get(int(recipe["pill_id"]))
                from Game_main.g18_alchemy_study import roll_alchemy_outcome
                success, quality, output_num = roll_alchemy_outcome(
                    slot.get("fire_style", "均衡"), slot.get("mastery", 0), random.randint(1, 100)
                )
                if success and pill:
                    pill_item_id = _resolve_item_id(pill["id"], pill)
                    await _add_user_item(cursor, uid, pill_item_id, output_num)
                    collected.append((idx, recipe["name"], True, f"{quality}，{pill['name']} x{output_num}"))
                elif success:
                    collected.append((idx, recipe["name"], False, "丹药配置缺失"))
                else:
                    collected.append((idx, recipe["name"], False, "炸炉"))

                slots[idx - 1] = _empty_furnace_slot()
                changed.append(idx)

            if not collected:
                await conn.rollback()
                return {"type": "markdown", "content": "当前没有已完成炼制的丹炉。"}

            await _save_slots(uid, slots, cursor, "user_danlu", "dl", changed)
            await conn.commit()

            lines = []
            lines.append("##### 一键收丹结果")
            lines.append("***")
            for idx, recipe_name, success, extra in collected:
                if success:
                    lines.append(f"丹炉{idx} | {recipe_name} | ✅ 成功，获得 {extra} x1")
                else:
                    lines.append(f"丹炉{idx} | {recipe_name} | ❌ {extra}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='查看丹炉' show='查看丹炉' /> | <qqbot-cmd-input text='炼丹 ' show='炼丹*' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 服丹
@reg_xz_func
async def fu_dan(uid, qz, param):
    pill_name, use_num = _parse_name_num(param)
    if not pill_name or not use_num or use_num <= 0:
        return {"type": "markdown", "content": "指令错误，正确指令：服丹 丹药名[-数量]\n示例：服丹 九转丹 或 服丹 九转丹-10"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            pill = await _get_pill_by_name(cursor, pill_name)
            if pill is None:
                return {"type": "markdown", "content": f"未找到丹药：{pill_name}"}
            if _is_breakthrough_pill_name(pill["name"]):
                return {
                    "type": "markdown",
                    "content": f"【{pill['name']}】是破境凭证，无需直接服用；角色达到境界巅峰后发送“悟道进阶”，系统会自动消耗。",
                }

            await cursor.execute(
                """
                SELECT id, dengji, exp, gongji, fangyu, qixue, fali, sudu,
                       baoji, baoshang, shanbi, mingzhong, pofang, xixue, pill_usage
                FROM user_role
                WHERE uid = %s AND is_chuzhan = 1
                LIMIT 1
                FOR UPDATE
                """,
                (uid,),
            )
            role_row = await cursor.fetchone()
            if not role_row:
                return {"type": "markdown", "content": "当前无出战角色，无法服丹。"}

            role_id = role_row[0]
            role_level = int(role_row[1] or 1)
            role_exp = int(role_row[2] or 0)
            current_attrs = {
                "gongji": int(role_row[3] or 0),
                "fangyu": int(role_row[4] or 0),
                "qixue": int(role_row[5] or 0),
                "fali": int(role_row[6] or 0),
                "sudu": int(role_row[7] or 0),
                "baoji": int(role_row[8] or 0),
                "baoshang": int(role_row[9] or 0),
                "shanbi": int(role_row[10] or 0),
                "mingzhong": int(role_row[11] or 0),
                "pofang": int(role_row[12] or 0),
                "xixue": int(role_row[13] or 0),
            }
            usage_raw = _json_loads(role_row[14]) or {}
            usage_key = str(pill["id"])
            used_times = int(usage_raw.get(usage_key, 0))
            max_use = int(pill["max_use"] or 0)

            if max_use > 0 and used_times + use_num > max_use:
                can_use = max_use - used_times
                return {"type": "markdown", "content": f"该丹药已达服用上限，当前可再服用 {max(0, can_use)} 次。"}

            pill_item_id = _resolve_item_id(pill["id"], pill)
            ok = await _deduct_user_item(cursor, uid, pill_item_id, use_num)
            if not ok:
                await conn.rollback()
                return {"type": "markdown", "content": f"丹药不足：{pill['name']} x {use_num}"}

            effect_types = [x.strip() for x in str(pill["effect_type"]).split(",") if x.strip()]
            effect_values = [x.strip() for x in str(pill["effect_value"]).split(",") if x.strip()]
            if not effect_types or len(effect_types) != len(effect_values):
                await conn.rollback()
                return {"type": "markdown", "content": f"丹药效果配置异常：{pill['name']}"}

            is_percent = int(pill["is_percent"] or 0) == 1
            attr_add = {}
            exp_add = 0
            lingshi_add = 0
            from Game_main.g18_alchemy_study import tolerance_factor
            permanent_factor = tolerance_factor(used_times, use_num)

            for idx, effect_type in enumerate(effect_types):
                try:
                    effect_val = float(effect_values[idx])
                except Exception:
                    effect_val = 0.0

                if effect_type in ROLE_ALL_ATTRS:
                    per_use = _calc_effect_increment(
                        effect_type,
                        current_attrs.get(effect_type, 0),
                        effect_val,
                        is_percent
                    )
                    attr_add[effect_type] = attr_add.get(effect_type, 0) + int(per_use * use_num * permanent_factor)
                    continue

                if effect_type == "exp":
                    if is_percent:
                        need_exp = await up_need_exp(role_level)
                        exp_add += int(need_exp * effect_val / 100) * use_num
                    else:
                        exp_add += int(effect_val) * use_num
                    continue

                if effect_type == "sell":
                    lingshi_add += int(effect_val) * use_num
                    continue

            for attr_key, add_val in attr_add.items():
                if add_val == 0:
                    continue
                await cursor.execute(
                    f"UPDATE user_role SET {attr_key} = {attr_key} + %s WHERE id = %s",
                    (add_val, role_id),
                )

            if exp_add > 0:
                await cursor.execute("UPDATE user_role SET exp = exp + %s WHERE id = %s", (exp_add, role_id))
            if lingshi_add > 0:
                await cursor.execute("UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s", (lingshi_add, uid))

            usage_raw[usage_key] = used_times + use_num
            await cursor.execute(
                "UPDATE user_role SET pill_usage = %s WHERE id = %s",
                (_json_dumps(usage_raw), role_id),
            )

            if attr_add:
                await update_role_power(conn, uid)
            await conn.commit()
            from Game_main.g18_alchemy_study import record_pill_tolerance
            await record_pill_tolerance(uid, pill['name'], use_num)

            lines = []
            lines.append("##### 服丹结果")
            lines.append(f"服用丹药：{pill['name']} x {use_num}")
            lines.append(f"累计服用：{usage_raw[usage_key]}/{max_use if max_use > 0 else '∞'}")
            if attr_add:
                lines.append(f"本次永久属性效力：{round(permanent_factor * 100, 1)}%（同类丹药耐药）")
            if attr_add:
                lines.append("**属性变化：**")
                for k, v in attr_add.items():
                    if k in ROLE_RATE_ATTRS:
                        lines.append(f"> {k} + {round(v / 100, 2)}%")
                    else:
                        lines.append(f"> {k} + {v}")
            if exp_add > 0:
                lines.append(f"> 经验 + {exp_add}（当前经验 {role_exp + exp_add}）")
            if lingshi_add > 0:
                lines.append(f"> 灵石 + {lingshi_add}")

            lines.append("***")
            lines.append("<qqbot-cmd-input text='当前角色' show='当前角色' /> | <qqbot-cmd-input text='物品背包' show='物品背包' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 解锁丹炉
@reg_xz_func
async def js_danlu(uid, qz, param):
    furnace_no = _parse_index(param)
    if not furnace_no:
        return {"type": "markdown", "content": "指令错误，正确指令：解锁丹炉 炉号\n示例：解锁丹炉 4"}
    if furnace_no < 1 or furnace_no > FURNACE_SLOT_COUNT:
        return {"type": "markdown", "content": f"炉号错误，仅支持 1-{FURNACE_SLOT_COUNT}。"}
    if furnace_no == 1:
        return {"type": "markdown", "content": "丹炉1为初始丹炉，无需解锁。"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_danlu(uid, cursor)
            slots = await _fetch_danlu_slots(uid, cursor, for_update=True)
            slots, auto_unlocked, max_level = await _sync_danlu_level_unlock(uid, cursor, slots)
            if auto_unlocked:
                await conn.commit()
                if furnace_no in auto_unlocked:
                    return {"type": "markdown", "content": f"丹炉{furnace_no}已自动解锁（角色等级达标）。"}

            if slots[furnace_no - 1] is not None:
                return {"type": "markdown", "content": f"丹炉{furnace_no}已解锁。"}

            for idx in range(1, furnace_no):
                if slots[idx - 1] is None:
                    return {"type": "markdown", "content": f"请先解锁丹炉{idx}，再解锁丹炉{furnace_no}。"}

            if furnace_no in DANLU_LEVEL_UNLOCK:
                need_level = DANLU_LEVEL_UNLOCK[furnace_no]
                if max_level < need_level:
                    return {"type": "markdown", "content": f"丹炉{furnace_no}需任一角色达到Lv.{need_level}后自动解锁。当前最高Lv.{max_level}。"}
                slots[furnace_no - 1] = _empty_furnace_slot()
                await _save_slots(uid, slots, cursor, "user_danlu", "dl", [furnace_no])
                await conn.commit()
                return {"type": "markdown", "content": f"丹炉{furnace_no}解锁成功（等级达标）。"}

            cost = DANLU_XIANYU_UNLOCK.get(furnace_no, 0)
            if cost <= 0:
                return {"type": "markdown", "content": "丹炉解锁配置异常，请联系管理员。"}

            await cursor.execute(
                "UPDATE user_zt SET xianyu = xianyu - %s WHERE id = %s AND xianyu >= %s",
                (cost, uid, cost),
            )
            if cursor.rowcount <= 0:
                await cursor.execute("SELECT xianyu FROM user_zt WHERE id = %s LIMIT 1", (uid,))
                cur_xy = int((await cursor.fetchone() or [0])[0] or 0)
                await conn.rollback()
                return {"type": "markdown", "content": f"仙玉不足，解锁丹炉{furnace_no}需要{cost}仙玉，当前仅有{cur_xy}。"}

            slots[furnace_no - 1] = _empty_furnace_slot()
            await _save_slots(uid, slots, cursor, "user_danlu", "dl", [furnace_no])
            await conn.commit()

            lines = []
            lines.append("##### 丹炉解锁成功")
            lines.append(f"已解锁丹炉{furnace_no}")
            lines.append(f"消耗仙玉：{cost}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='查看丹炉' show='查看丹炉' />")
            return {"type": "markdown", "content": "\n".join(lines)}

# 添火次数
@reg_xz_func
async def ck_tianhuo_times(uid, qz):
    stat_date = _today_date()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            help_used, be_helped = await _get_fire_daily_stats(cursor, uid, stat_date)

            lines = []
            lines.append("##### 🔥 添火次数")
            lines.append(f"统计日期：{stat_date}")
            lines.append(f"主动添火：{help_used}/{TIANHUO_HELP_DAILY_LIMIT}")
            lines.append(f"被添火：{be_helped}/{TIANHUO_BE_HELPED_DAILY_LIMIT}")
            lines.append("***")
            lines.append("指令：添火 目标UID（自动选炉） 或 添火 目标UID-炉号（指定炉）")
            return {"type": "markdown", "content": "\n".join(lines)}


# 添火
@reg_xz_func
async def th_liandan(uid, qz, param):
    target_uid, furnace_no = _parse_uid_slot(param)
    if not target_uid:
        return {"type": "markdown", "content": "指令错误，正确指令：添火 目标UID 或 添火 目标UID-炉号\n示例：添火 10086 或 添火 10086-1"}
    if target_uid == uid:
        return {"type": "markdown", "content": "不能给自己添火，请指定其他玩家的UID。"}
    if furnace_no is not None and (furnace_no < 1 or furnace_no > FURNACE_SLOT_COUNT):
        return {"type": "markdown", "content": f"炉号错误，仅支持 1-{FURNACE_SLOT_COUNT}。"}

    stat_date = _today_date()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await cursor.execute("SELECT `name` FROM user_zt WHERE id = %s LIMIT 1", (target_uid,))
            target_row = await cursor.fetchone()
            if not target_row:
                return {"type": "markdown", "content": f"目标玩家不存在：{target_uid}"}
            target_name = target_row[0]

            daily_map = await _lock_fire_daily_rows(cursor, [uid, target_uid], stat_date)
            helper_today = int(daily_map.get(uid, {}).get("help_used_times", 0))
            target_today = int(daily_map.get(target_uid, {}).get("be_helped_times", 0))
            if helper_today >= TIANHUO_HELP_DAILY_LIMIT:
                await conn.rollback()
                return {"type": "markdown", "content": f"你今日主动添火次数已达上限（{TIANHUO_HELP_DAILY_LIMIT}次）。"}
            if target_today >= TIANHUO_BE_HELPED_DAILY_LIMIT:
                await conn.rollback()
                return {"type": "markdown", "content": f"玩家[{target_uid}]今日被添火次数已达上限（{TIANHUO_BE_HELPED_DAILY_LIMIT}次）。"}

            await _init_danlu(target_uid, cursor)
            target_slots = await _fetch_danlu_slots(target_uid, cursor, for_update=True)
            target_slots, _, _ = await _sync_danlu_level_unlock(target_uid, cursor, target_slots)
            now_ts = int(time.time())
            selected_slot = None
            selected_furnace_no = None
            selected_batch_ts = 0
            selected_remain = 0

            if furnace_no is not None:
                slot = target_slots[furnace_no - 1]
                if slot is None:
                    await conn.rollback()
                    return {"type": "markdown", "content": f"目标玩家丹炉{furnace_no}未解锁。"}
                if int(slot.get("is_lz", 0)) == 0:
                    await conn.rollback()
                    return {"type": "markdown", "content": f"目标玩家丹炉{furnace_no}当前空闲，无法添火。"}

                remain = ALCHEMY_SECONDS - (now_ts - int(slot.get("time", 0)))
                if remain <= 0:
                    await conn.rollback()
                    return {"type": "markdown", "content": f"目标玩家丹炉{furnace_no}已炼制完成，无需添火。"}

                fire_count = int(slot.get("fire_count", 0))
                if fire_count >= TIANHUO_PER_FURNACE_LIMIT:
                    await conn.rollback()
                    return {"type": "markdown", "content": f"目标玩家丹炉{furnace_no}当前批次添火已达上限（{TIANHUO_PER_FURNACE_LIMIT}次）。"}

                batch_ts = int(slot.get("batch_ts", 0) or slot.get("time", 0))
                await cursor.execute(
                    """
                    INSERT IGNORE INTO user_liandan_fire_log
                    (helper_uid, target_uid, furnace_no, batch_ts, reduce_seconds)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (uid, target_uid, furnace_no, batch_ts, TIANHUO_REDUCE_SECONDS),
                )
                if cursor.rowcount <= 0:
                    await conn.rollback()
                    return {"type": "markdown", "content": "本批次你已为该玩家该丹炉添火过，不能重复添火。"}

                selected_slot = slot
                selected_furnace_no = furnace_no
                selected_batch_ts = batch_ts
                selected_remain = remain
            else:
                candidate_nos = []
                running_exist = False
                for idx, slot in enumerate(target_slots, 1):
                    if slot is None or int(slot.get("is_lz", 0)) != 1:
                        continue
                    remain = ALCHEMY_SECONDS - (now_ts - int(slot.get("time", 0)))
                    if remain <= 0:
                        continue
                    running_exist = True
                    fire_count = int(slot.get("fire_count", 0))
                    if fire_count >= TIANHUO_PER_FURNACE_LIMIT:
                        continue
                    candidate_nos.append((remain, idx))

                if not running_exist:
                    await conn.rollback()
                    return {"type": "markdown", "content": f"玩家[{target_uid}]当前没有炼制中的丹炉。"}
                if not candidate_nos:
                    await conn.rollback()
                    return {"type": "markdown", "content": f"玩家[{target_uid}]炼制中的丹炉当前均不可添火（可能已达批次上限）。"}

                candidate_nos.sort(key=lambda x: (x[0], x[1]))
                for remain, no in candidate_nos:
                    slot = target_slots[no - 1]
                    batch_ts = int(slot.get("batch_ts", 0) or slot.get("time", 0))
                    await cursor.execute(
                        """
                        INSERT IGNORE INTO user_liandan_fire_log
                        (helper_uid, target_uid, furnace_no, batch_ts, reduce_seconds)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (uid, target_uid, no, batch_ts, TIANHUO_REDUCE_SECONDS),
                    )
                    if cursor.rowcount > 0:
                        selected_slot = slot
                        selected_furnace_no = no
                        selected_batch_ts = batch_ts
                        selected_remain = remain
                        break

                if selected_slot is None:
                    await conn.rollback()
                    return {"type": "markdown", "content": f"你已对玩家[{target_uid}]当前可添火丹炉完成过添火，暂无可继续添火目标。"}

            fire_count = int(selected_slot.get("fire_count", 0))
            selected_slot["batch_ts"] = selected_batch_ts
            selected_slot["fire_count"] = fire_count + 1
            selected_slot["time"] = max(int(selected_slot.get("time", 0)) - TIANHUO_REDUCE_SECONDS, now_ts - ALCHEMY_SECONDS)
            target_slots[selected_furnace_no - 1] = selected_slot
            await _save_slots(target_uid, target_slots, cursor, "user_danlu", "dl", [selected_furnace_no])

            await cursor.execute(
                """
                UPDATE user_liandan_fire_daily
                SET help_used_times = help_used_times + 1
                WHERE uid = %s AND stat_date = %s
                """,
                (uid, stat_date),
            )
            await cursor.execute(
                """
                UPDATE user_liandan_fire_daily
                SET be_helped_times = be_helped_times + 1
                WHERE uid = %s AND stat_date = %s
                """,
                (target_uid, stat_date),
            )

            await conn.commit()

            helper_after = helper_today + 1
            target_after = target_today + 1
            remain_after = ALCHEMY_SECONDS - (now_ts - int(selected_slot.get("time", 0)))
            lines = []
            lines.append("##### 🔥 添火成功")
            lines.append(f"目标玩家：[{target_uid}] {target_name}")
            lines.append(f"目标丹炉：{selected_furnace_no}")
            if furnace_no is None:
                lines.append(f"自动选择：按成熟顺序选择当前最先成熟的可添火丹炉（原剩余{_format_seconds(selected_remain)}）")
            lines.append(f"本次减时：{_format_seconds(TIANHUO_REDUCE_SECONDS)}")
            lines.append(f"你的主动添火：{helper_after}/{TIANHUO_HELP_DAILY_LIMIT}")
            lines.append(f"对方被添火：{target_after}/{TIANHUO_BE_HELPED_DAILY_LIMIT}")
            if remain_after <= 0:
                lines.append("结果：该丹炉已可收丹。")
            else:
                lines.append(f"当前剩余：{_format_seconds(remain_after)}")
            lines.append("***")
            lines.append("<qqbot-cmd-input text='添火次数' show='添火次数' />")
            return {"type": "markdown", "content": "\n".join(lines)}


# 加速炼丹
@reg_xz_func
async def js_liandan(uid, qz, param):
    furnace_no = _parse_index(param)
    if not furnace_no:
        return {"type": "markdown", "content": "指令错误，正确指令：加速炼丹 炉号\n示例：加速炼丹 1"}
    if furnace_no < 1 or furnace_no > FURNACE_SLOT_COUNT:
        return {"type": "markdown", "content": f"炉号错误，仅支持 1-{FURNACE_SLOT_COUNT}。"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_yaoyuan_schema(cursor)
            await _init_danlu(uid, cursor)
            slots = await _fetch_danlu_slots(uid, cursor, for_update=True)
            slots, _, _ = await _sync_danlu_level_unlock(uid, cursor, slots)
            slot = slots[furnace_no - 1]
            if slot is None:
                return {"type": "markdown", "content": f"丹炉{furnace_no}未解锁。"}
            if int(slot.get("is_lz", 0)) == 0:
                return {"type": "markdown", "content": f"丹炉{furnace_no}当前空闲，无需加速。"}

            ok = await _deduct_user_item(cursor, uid, ALCHEMY_ACCEL_ITEM_ID, 1)
            if not ok:
                await conn.rollback()
                return {"type": "markdown", "content": "缺少道具：炼丹加速卡 x1。"}

            slot["time"] = int(time.time()) - ALCHEMY_SECONDS
            slots[furnace_no - 1] = slot
            await _save_slots(uid, slots, cursor, "user_danlu", "dl", [furnace_no])
            await conn.commit()

            lines = []
            lines.append("##### 加速成功")
            lines.append(f"丹炉{furnace_no}已立即完成炼制，可直接收丹。")
            lines.append("消耗：炼丹加速卡 x1")
            lines.append("***")
            lines.append(f"<qqbot-cmd-input text='收丹 {furnace_no}' show='收丹 {furnace_no}' /> | <qqbot-cmd-input text='查看丹炉' show='查看丹炉' />")
            return {"type": "markdown", "content": "\n".join(lines)}
