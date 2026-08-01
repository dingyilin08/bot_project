import random

import aiomysql


CANWU_MIN_SECONDS = 30
CANWU_MAX_SECONDS = 120
LEGACY_CANWU_SECONDS = 1200

_CANWU_SCHEMA_READY = False


def roll_canwu_duration(rng=None):
    rng = rng or random
    return rng.randint(CANWU_MIN_SECONDS, CANWU_MAX_SECONDS)


def canwu_remaining_seconds(start_timestamp, duration, current_timestamp):
    duration = int(duration or LEGACY_CANWU_SECONDS)
    return max(0, duration - (int(current_timestamp) - int(start_timestamp)))


async def ensure_canwu_duration_column(cursor):
    """兼容未执行迁移的旧库；旧的进行中参悟仍按 20 分钟结算。"""
    global _CANWU_SCHEMA_READY
    if _CANWU_SCHEMA_READY:
        return

    await cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'user_zt'
          AND COLUMN_NAME = 'cw_duration'
        """
    )
    row = await cursor.fetchone()
    if not row or int(row[0]) == 0:
        try:
            await cursor.execute(
                "ALTER TABLE user_zt ADD COLUMN cw_duration INT NOT NULL DEFAULT 1200 "
                "COMMENT '本次参悟所需秒数' AFTER cw_timestamp"
            )
        except aiomysql.OperationalError as error:
            if not error.args or error.args[0] != 1060:
                raise
    _CANWU_SCHEMA_READY = True
