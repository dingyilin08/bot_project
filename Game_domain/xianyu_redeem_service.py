# -*- coding: utf-8 -*-
"""一次性仙玉兑换码的生成、校验与原子兑换。"""

import re
import secrets
from datetime import datetime
from uuid import uuid4

from pymysql.err import IntegrityError

from Game_domain.gm_service import require_admin
from sql.mysql import connect_mysql


XIANYU_REDEEM_TIERS = (600, 1800, 3000, 6800, 15000)
REDEEM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REDEEM_CODE_RANDOM_LENGTH = 12
MAX_REDEEM_CODES_PER_BATCH = 20
_REDEEM_SCHEMA_READY = False


class XianyuRedeemError(ValueError):
    pass


def normalize_redeem_code(value):
    compact = re.sub(r"[\s+-]", "", str(value or "").upper())
    if not re.fullmatch(r"XY[A-HJ-NP-Z2-9]{12}", compact):
        raise XianyuRedeemError("兑换码格式错误，请复制完整兑换码后重试。")
    return compact


def display_redeem_code(value):
    code = normalize_redeem_code(value)
    return f"{code[:2]}-{code[2:6]}-{code[6:10]}-{code[10:14]}"


def generate_redeem_code():
    random_part = "".join(
        secrets.choice(REDEEM_CODE_ALPHABET)
        for _ in range(REDEEM_CODE_RANDOM_LENGTH)
    )
    return f"XY{random_part}"


def parse_generate_request(value):
    matched = re.fullmatch(r"(\d+)(?:\s+|-)(\d+)", str(value or "").strip())
    if not matched:
        raise XianyuRedeemError("格式：GM生成兑换码 仙玉档位 数量，例如：GM生成兑换码 600 5")
    amount, count = int(matched.group(1)), int(matched.group(2))
    if amount not in XIANYU_REDEEM_TIERS:
        tiers = "、".join(str(item) for item in XIANYU_REDEEM_TIERS)
        raise XianyuRedeemError(f"仙玉档位仅支持：{tiers}。")
    if count <= 0 or count > MAX_REDEEM_CODES_PER_BATCH:
        raise XianyuRedeemError(
            f"单批生成数量必须为1—{MAX_REDEEM_CODES_PER_BATCH}个。"
        )
    return amount, count


async def ensure_redeem_schema(cursor):
    global _REDEEM_SCHEMA_READY
    if _REDEEM_SCHEMA_READY:
        return
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS xianyu_redeem_code (
            id BIGINT NOT NULL AUTO_INCREMENT,
            redeem_code VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            amount INT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
            batch_id CHAR(32) NOT NULL,
            created_by INT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            redeemed_by INT NULL,
            redeemed_at DATETIME NULL,
            expires_at DATETIME NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_xianyu_redeem_code (redeem_code),
            KEY idx_xianyu_redeem_status (status, amount, created_at),
            KEY idx_xianyu_redeem_user (redeemed_by, redeemed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        COMMENT='仙玉一次性兑换码'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_xianyu_redeem_log (
            id BIGINT NOT NULL AUTO_INCREMENT,
            code_id BIGINT NOT NULL,
            uid INT NOT NULL,
            amount INT NOT NULL,
            balance_before BIGINT NOT NULL,
            balance_after BIGINT NOT NULL,
            redeemed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_xianyu_redeem_log_code (code_id),
            KEY idx_xianyu_redeem_log_user (uid, redeemed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        COMMENT='玩家_仙玉兑换流水'
        """
    )
    _REDEEM_SCHEMA_READY = True


async def create_redeem_codes(operator_uid, amount, count):
    require_admin(int(operator_uid))
    amount, count = parse_generate_request(f"{amount} {count}")
    batch_id = uuid4().hex
    created = []
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_redeem_schema(cursor)
                for _ in range(count):
                    for _attempt in range(10):
                        code = generate_redeem_code()
                        try:
                            await cursor.execute(
                                """
                                INSERT INTO xianyu_redeem_code(
                                    redeem_code,amount,status,batch_id,created_by
                                ) VALUES(%s,%s,'ACTIVE',%s,%s)
                                """,
                                (code, amount, batch_id, operator_uid),
                            )
                            created.append(code)
                            break
                        except IntegrityError:
                            continue
                    else:
                        raise XianyuRedeemError("兑换码生成冲突次数过多，请重新操作。")
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
    return {
        "batch_id": batch_id,
        "amount": amount,
        "count": count,
        "codes": tuple(display_redeem_code(code) for code in created),
    }


async def redeem_xianyu_code(uid, value):
    code = normalize_redeem_code(value)
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_redeem_schema(cursor)
                await cursor.execute(
                    """
                    SELECT id,amount,status,redeemed_by,expires_at
                    FROM xianyu_redeem_code
                    WHERE redeem_code=%s
                    LIMIT 1 FOR UPDATE
                    """,
                    (code,),
                )
                row = await cursor.fetchone()
                if not row:
                    raise XianyuRedeemError("兑换码不存在，请检查后重试。")
                code_id, amount, status, redeemed_by, expires_at = row
                if status == "REDEEMED":
                    if int(redeemed_by or 0) == int(uid):
                        raise XianyuRedeemError("该兑换码已由您领取，不能重复兑换。")
                    raise XianyuRedeemError("该兑换码已经被使用。")
                if status != "ACTIVE":
                    raise XianyuRedeemError("该兑换码当前不可使用。")
                if int(amount or 0) not in XIANYU_REDEEM_TIERS:
                    raise XianyuRedeemError("该兑换码档位异常，请联系管理员处理。")
                if expires_at and expires_at <= datetime.now():
                    await cursor.execute(
                        "UPDATE xianyu_redeem_code SET status='EXPIRED' WHERE id=%s",
                        (code_id,),
                    )
                    await conn.commit()
                    raise XianyuRedeemError("该兑换码已经过期。")

                await cursor.execute(
                    "SELECT `name`,xianyu FROM user_zt WHERE id=%s FOR UPDATE",
                    (uid,),
                )
                player = await cursor.fetchone()
                if not player:
                    raise XianyuRedeemError("未找到玩家数据，请重新注册后再试。")
                balance_before = int(player[1] or 0)
                balance_after = balance_before + int(amount)
                await cursor.execute(
                    "UPDATE user_zt SET xianyu=%s WHERE id=%s",
                    (balance_after, uid),
                )
                await cursor.execute(
                    """
                    UPDATE xianyu_redeem_code
                    SET status='REDEEMED',redeemed_by=%s,redeemed_at=NOW()
                    WHERE id=%s AND status='ACTIVE'
                    """,
                    (uid, code_id),
                )
                if cursor.rowcount <= 0:
                    raise XianyuRedeemError("兑换码状态已变化，请勿重复兑换。")
                await cursor.execute(
                    """
                    INSERT INTO user_xianyu_redeem_log(
                        code_id,uid,amount,balance_before,balance_after
                    ) VALUES(%s,%s,%s,%s,%s)
                    """,
                    (code_id, uid, amount, balance_before, balance_after),
                )
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
    return {
        "code": display_redeem_code(code),
        "amount": int(amount),
        "balance_before": balance_before,
        "balance_after": balance_after,
    }
