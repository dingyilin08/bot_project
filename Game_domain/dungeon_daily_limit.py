# -*- coding: utf-8 -*-
"""副本每日累计次数：手动挑战与扫荡共用基础额度，体力药可扩充额度。"""

from datetime import date


DAILY_DUNGEON_ATTEMPT_LIMIT = 20
MAX_DUNGEON_ATTEMPT_LIMIT = 40
_DAILY_SCHEMA_READY = False


def remaining_daily_attempts(used_count, attempt_limit=DAILY_DUNGEON_ATTEMPT_LIMIT):
    limit = min(
        MAX_DUNGEON_ATTEMPT_LIMIT,
        max(DAILY_DUNGEON_ATTEMPT_LIMIT, int(attempt_limit or 0)),
    )
    return max(0, limit - max(0, int(used_count or 0)))


async def ensure_daily_attempt_schema(cursor):
    global _DAILY_SCHEMA_READY
    if _DAILY_SCHEMA_READY:
        return
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_dungeon_daily_usage (
            uid INT NOT NULL,
            stat_date DATE NOT NULL,
            used_count INT NOT NULL DEFAULT 0,
            attempt_limit INT NOT NULL DEFAULT 20,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (uid, stat_date),
            KEY idx_dungeon_usage_date (stat_date, used_count)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        COMMENT='玩家_副本每日累计挑战与扫荡次数'
        """
    )
    await cursor.execute(
        "SHOW COLUMNS FROM user_dungeon_daily_usage LIKE 'attempt_limit'"
    )
    if not await cursor.fetchone():
        await cursor.execute(
            "ALTER TABLE user_dungeon_daily_usage "
            "ADD COLUMN attempt_limit INT NOT NULL DEFAULT 20 AFTER used_count"
        )
    _DAILY_SCHEMA_READY = True


async def get_daily_attempt_status(cursor, uid, *, lock=False, stat_date=None):
    stat_date = stat_date or date.today()
    await cursor.execute("SELECT id FROM user_zt WHERE id=%s LIMIT 1", (uid,))
    if not await cursor.fetchone():
        return None
    await cursor.execute(
        """
        INSERT IGNORE INTO user_dungeon_daily_usage(
            uid,stat_date,used_count,attempt_limit
        ) VALUES(%s,%s,0,%s)
        """,
        (uid, stat_date, DAILY_DUNGEON_ATTEMPT_LIMIT),
    )
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        "SELECT used_count,attempt_limit FROM user_dungeon_daily_usage "
        f"WHERE uid=%s AND stat_date=%s{suffix}",
        (uid, stat_date),
    )
    row = await cursor.fetchone()
    used = int(row[0] or 0)
    attempt_limit = min(
        MAX_DUNGEON_ATTEMPT_LIMIT,
        max(DAILY_DUNGEON_ATTEMPT_LIMIT, int(row[1] or 0)),
    )
    remaining = remaining_daily_attempts(used, attempt_limit)
    # dungeon_num 继续作为旧菜单/旧版本的只读兼容快照，真实限制只看累计表。
    await cursor.execute(
        """
        UPDATE user_zt
        SET dungeon_num=%s,daily_dungeon_reset_time=%s
        WHERE id=%s
        """,
        (remaining, stat_date, uid),
    )
    return {"used": used, "remaining": remaining, "limit": attempt_limit}


async def consume_daily_attempt(cursor, uid, *, stat_date=None):
    stat_date = stat_date or date.today()
    status = await get_daily_attempt_status(
        cursor, uid, lock=True, stat_date=stat_date
    )
    if not status or status["used"] >= status["limit"]:
        return None
    await cursor.execute(
        """
        UPDATE user_dungeon_daily_usage
        SET used_count=used_count+1
        WHERE uid=%s AND stat_date=%s AND used_count<attempt_limit
        """,
        (uid, stat_date),
    )
    if cursor.rowcount <= 0:
        return None
    used = status["used"] + 1
    remaining = remaining_daily_attempts(used, status["limit"])
    await cursor.execute(
        """
        UPDATE user_zt
        SET dungeon_num=%s,daily_dungeon_reset_time=%s
        WHERE id=%s
        """,
        (remaining, stat_date, uid),
    )
    return {"used": used, "remaining": remaining, "limit": status["limit"]}


async def increase_daily_attempt_limit(cursor, uid, amount, *, stat_date=None):
    """使用体力药扩充当日额度；返回扩充后的状态，达到上限时返回 None。"""
    stat_date = stat_date or date.today()
    status = await get_daily_attempt_status(
        cursor, uid, lock=True, stat_date=stat_date
    )
    if not status:
        return None
    amount = max(0, int(amount or 0))
    new_limit = min(MAX_DUNGEON_ATTEMPT_LIMIT, status["limit"] + amount)
    if new_limit <= status["limit"]:
        return None
    await cursor.execute(
        """
        UPDATE user_dungeon_daily_usage
        SET attempt_limit=%s
        WHERE uid=%s AND stat_date=%s
        """,
        (new_limit, uid, stat_date),
    )
    remaining = remaining_daily_attempts(status["used"], new_limit)
    await cursor.execute(
        """
        UPDATE user_zt
        SET dungeon_num=%s,daily_dungeon_reset_time=%s
        WHERE id=%s
        """,
        (remaining, stat_date, uid),
    )
    return {
        "used": status["used"],
        "remaining": remaining,
        "limit": new_limit,
        "added": new_limit - status["limit"],
    }
