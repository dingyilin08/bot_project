# -*- coding: utf-8 -*-
"""月卡兑换码、有效期与每日奖励的事务服务。"""

import re
import secrets
import logging
import time
from datetime import datetime, timedelta
from uuid import uuid4

from pymysql.err import IntegrityError

from Game_domain.gm_service import require_admin
from sql.mysql import connect_mysql


MONTHLY_CARD_DAYS = 30
MONTHLY_CARD_MAX_REMAINING_DAYS = 180
MONTHLY_CARD_ACTIVATION_XIANYU = 600
MONTHLY_CARD_DAILY_XIANYU = 100
MONTHLY_CARD_DAILY_LINGSHI = 200
MONTHLY_CARD_TITLE = "月华玩家"
MONTHLY_CARD_LOGIN_OFFLINE_HOURS = 6
MONTHLY_CARD_LOGIN_EVENT_TTL_MINUTES = 30
MONTHLY_CARD_PRESENCE_CACHE_SECONDS = 300
MONTHLY_CARD_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MONTHLY_CARD_CODE_RANDOM_LENGTH = 12
MAX_CODES_PER_BATCH = 20
_MONTHLY_CARD_SCHEMA_READY = False
_presence_check_cache = {}
logger = logging.getLogger(__name__)


class MonthlyCardError(ValueError):
    pass


def normalize_monthly_card_code(value):
    compact = re.sub(r"[\s+-]", "", str(value or "").upper())
    if not re.fullmatch(r"MC[A-HJ-NP-Z2-9]{12}", compact):
        raise MonthlyCardError("月卡码格式错误，请复制完整月卡码后重试。")
    return compact


def display_monthly_card_code(value):
    code = normalize_monthly_card_code(value)
    return f"{code[:2]}-{code[2:6]}-{code[6:10]}-{code[10:14]}"


def generate_monthly_card_code():
    random_part = "".join(
        secrets.choice(MONTHLY_CARD_CODE_ALPHABET)
        for _ in range(MONTHLY_CARD_CODE_RANDOM_LENGTH)
    )
    return f"MC{random_part}"


def parse_generate_count(value):
    raw = str(value or "").strip()
    if not re.fullmatch(r"\d+", raw):
        raise MonthlyCardError("格式：GM生成月卡码 数量，例如：GM生成月卡码 5")
    count = int(raw)
    if count <= 0 or count > MAX_CODES_PER_BATCH:
        raise MonthlyCardError(f"单批生成数量必须为1—{MAX_CODES_PER_BATCH}个。")
    return count


def remaining_days(today, expires_on):
    if not expires_on:
        return 0
    return max(0, (expires_on - today).days + 1)


def calculate_stacked_expiry(today, current_expires_on, added_days=MONTHLY_CARD_DAYS):
    """激活日计为首日；有效期内续卡从原到期日的次日顺延。"""
    added_days = int(added_days)
    if added_days <= 0:
        raise MonthlyCardError("月卡有效天数必须大于0。")
    if current_expires_on and current_expires_on >= today:
        new_expires_on = current_expires_on + timedelta(days=added_days)
    else:
        new_expires_on = today + timedelta(days=added_days - 1)
    if remaining_days(today, new_expires_on) > MONTHLY_CARD_MAX_REMAINING_DAYS:
        raise MonthlyCardError(
            f"月卡最多累计{MONTHLY_CARD_MAX_REMAINING_DAYS}天，请在剩余天数减少后再续卡。"
        )
    return new_expires_on


def monthly_card_display_name(player_name, active=True):
    name = re.sub(r"[^\u4e00-\u9fffa-zA-Z0-9·]", "", str(player_name or ""))[:8]
    name = name or "无名道友"
    return f"「{MONTHLY_CARD_TITLE}」{name}" if active else name


def monthly_card_login_message(player_name):
    safe_name = monthly_card_display_name(player_name, active=False)
    return f"尊贵的{MONTHLY_CARD_TITLE}{safe_name}已上线！"


def should_announce_monthly_card_login(now, last_seen_at, last_announced_at):
    """离线满6小时且当天尚未播报时，视为一次可公告的重新上线。"""
    if last_announced_at and last_announced_at.date() == now.date():
        return False
    if last_seen_at is None:
        return True
    return last_seen_at <= now - timedelta(hours=MONTHLY_CARD_LOGIN_OFFLINE_HOURS)


async def ensure_monthly_card_schema(cursor):
    global _MONTHLY_CARD_SCHEMA_READY
    if _MONTHLY_CARD_SCHEMA_READY:
        return
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_card_redeem_code (
            id BIGINT NOT NULL AUTO_INCREMENT,
            redeem_code VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            days SMALLINT NOT NULL DEFAULT 30,
            activation_xianyu INT NOT NULL DEFAULT 600,
            status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
            batch_id CHAR(32) NOT NULL,
            created_by INT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            redeemed_by INT NULL,
            redeemed_at DATETIME NULL,
            expires_at DATETIME NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_monthly_card_code (redeem_code),
            KEY idx_monthly_card_code_status (status, created_at),
            KEY idx_monthly_card_code_user (redeemed_by, redeemed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='月卡一次性兑换码'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_monthly_card (
            uid INT NOT NULL,
            expires_on DATE NOT NULL,
            total_days_activated INT NOT NULL DEFAULT 0,
            total_days_claimed INT NOT NULL DEFAULT 0,
            last_claim_date DATE NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (uid),
            KEY idx_user_monthly_card_expiry (expires_on)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_月卡权益'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_monthly_card_activation_log (
            id BIGINT NOT NULL AUTO_INCREMENT,
            code_id BIGINT NOT NULL,
            uid INT NOT NULL,
            days SMALLINT NOT NULL,
            previous_expires_on DATE NULL,
            new_expires_on DATE NOT NULL,
            activation_xianyu INT NOT NULL,
            balance_before BIGINT NOT NULL,
            balance_after BIGINT NOT NULL,
            activated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_monthly_card_activation_code (code_id),
            KEY idx_monthly_card_activation_user (uid, activated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_月卡激活流水'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_monthly_card_claim_log (
            id BIGINT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            claim_date DATE NOT NULL,
            reward_xianyu INT NOT NULL,
            reward_lingshi BIGINT NOT NULL,
            xianyu_before BIGINT NOT NULL,
            xianyu_after BIGINT NOT NULL,
            lingshi_before BIGINT NOT NULL,
            lingshi_after BIGINT NOT NULL,
            claimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_monthly_card_daily_claim (uid, claim_date),
            KEY idx_monthly_card_claim_user (uid, claimed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_月卡每日领取流水'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_monthly_card_presence (
            uid INT NOT NULL,
            last_seen_at DATETIME NOT NULL,
            last_announced_at DATETIME NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (uid),
            KEY idx_monthly_card_presence_seen (last_seen_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_月卡在线状态'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS world_message_event_queue (
            id BIGINT NOT NULL AUTO_INCREMENT,
            event_key VARCHAR(96) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            content VARCHAR(180) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
            available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            published_at DATETIME NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_world_message_event_key (event_key),
            KEY idx_world_message_event_pending (status, available_at, expires_at, id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='临时世界消息事件队列'
        """
    )
    _MONTHLY_CARD_SCHEMA_READY = True


async def record_monthly_card_player_activity(openid):
    """记录月卡玩家活跃，并在符合上线规则时写入临时世界消息队列。

    该能力属于回复增强，任何数据库异常都必须降级，不能阻断正常游戏指令。
    """
    if not openid:
        return None
    cache_key = str(openid)
    monotonic_now = time.monotonic()
    cached_at = _presence_check_cache.get(cache_key)
    if cached_at is not None and monotonic_now - cached_at < MONTHLY_CARD_PRESENCE_CACHE_SECONDS:
        return None
    _presence_check_cache[cache_key] = monotonic_now

    try:
        async with connect_mysql() as conn:
            try:
                async with conn.cursor() as cursor:
                    await ensure_monthly_card_schema(cursor)
                    await cursor.execute(
                        """
                        SELECT uz.id,uz.`name`,mc.expires_on,p.last_seen_at,
                               p.last_announced_at,CURDATE(),NOW()
                        FROM user_zt uz
                        LEFT JOIN user_monthly_card mc ON mc.uid=uz.id
                        LEFT JOIN user_monthly_card_presence p ON p.uid=uz.id
                        WHERE uz.openid=%s LIMIT 1 FOR UPDATE
                        """,
                        (openid,),
                    )
                    row = await cursor.fetchone()
                    if not row:
                        await conn.rollback()
                        return None
                    uid, player_name, expires_on, last_seen_at, last_announced_at, today, now = row
                    if not expires_on or expires_on < today:
                        await conn.rollback()
                        return None

                    announce = should_announce_monthly_card_login(
                        now, last_seen_at, last_announced_at
                    )
                    announced_at = now if announce else last_announced_at
                    await cursor.execute(
                        """
                        INSERT INTO user_monthly_card_presence(uid,last_seen_at,last_announced_at)
                        VALUES(%s,%s,%s)
                        ON DUPLICATE KEY UPDATE
                            last_seen_at=VALUES(last_seen_at),
                            last_announced_at=VALUES(last_announced_at)
                        """,
                        (uid, now, announced_at),
                    )
                    message = None
                    if announce:
                        event_key = f"monthly-login:{int(uid)}:{today:%Y%m%d}"
                        message = monthly_card_login_message(player_name)
                        expires_at = now + timedelta(
                            minutes=MONTHLY_CARD_LOGIN_EVENT_TTL_MINUTES
                        )
                        await cursor.execute(
                            """
                            INSERT IGNORE INTO world_message_event_queue(
                                event_key,content,status,available_at,expires_at
                            ) VALUES(%s,%s,'PENDING',%s,%s)
                            """,
                            (event_key, message, now, expires_at),
                        )
                        if cursor.rowcount <= 0:
                            message = None
                await conn.commit()
            except BaseException:
                await conn.rollback()
                raise
        return message
    except Exception:
        logger.exception("记录月卡玩家上线状态失败，已降级为普通回复")
        return None


async def create_monthly_card_codes(operator_uid, count):
    require_admin(int(operator_uid))
    count = parse_generate_count(count)
    batch_id = uuid4().hex
    created = []
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_monthly_card_schema(cursor)
                for _ in range(count):
                    for _attempt in range(10):
                        code = generate_monthly_card_code()
                        try:
                            await cursor.execute(
                                """
                                INSERT INTO monthly_card_redeem_code(
                                    redeem_code,days,activation_xianyu,status,batch_id,created_by
                                ) VALUES(%s,%s,%s,'ACTIVE',%s,%s)
                                """,
                                (
                                    code,
                                    MONTHLY_CARD_DAYS,
                                    MONTHLY_CARD_ACTIVATION_XIANYU,
                                    batch_id,
                                    operator_uid,
                                ),
                            )
                            created.append(code)
                            break
                        except IntegrityError:
                            continue
                    else:
                        raise MonthlyCardError("月卡码生成冲突次数过多，请重新操作。")
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
    return {
        "batch_id": batch_id,
        "count": count,
        "days": MONTHLY_CARD_DAYS,
        "activation_xianyu": MONTHLY_CARD_ACTIVATION_XIANYU,
        "codes": tuple(display_monthly_card_code(code) for code in created),
    }


async def redeem_monthly_card_code(uid, value):
    code = normalize_monthly_card_code(value)
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_monthly_card_schema(cursor)
                await cursor.execute("SELECT CURDATE()")
                today = (await cursor.fetchone())[0]
                await cursor.execute(
                    """
                    SELECT id,days,activation_xianyu,status,redeemed_by,expires_at
                    FROM monthly_card_redeem_code
                    WHERE redeem_code=%s LIMIT 1 FOR UPDATE
                    """,
                    (code,),
                )
                row = await cursor.fetchone()
                if not row:
                    raise MonthlyCardError("月卡码不存在，请检查后重试。")
                code_id, days, activation_xianyu, status, redeemed_by, code_expires_at = row
                if status == "REDEEMED":
                    if int(redeemed_by or 0) == int(uid):
                        raise MonthlyCardError("该月卡码已由您激活，不能重复使用。")
                    raise MonthlyCardError("该月卡码已经被使用。")
                if status != "ACTIVE":
                    raise MonthlyCardError("该月卡码当前不可使用。")
                if code_expires_at and code_expires_at <= datetime.now():
                    await cursor.execute(
                        "UPDATE monthly_card_redeem_code SET status='EXPIRED' WHERE id=%s",
                        (code_id,),
                    )
                    await conn.commit()
                    raise MonthlyCardError("该月卡码已经过期。")
                if int(days) != MONTHLY_CARD_DAYS or int(activation_xianyu) < 0:
                    raise MonthlyCardError("该月卡码档位异常，请联系管理员处理。")

                await cursor.execute(
                    "SELECT `name`,xianyu FROM user_zt WHERE id=%s FOR UPDATE",
                    (uid,),
                )
                player = await cursor.fetchone()
                if not player:
                    raise MonthlyCardError("未找到玩家数据，请重新注册后再试。")
                await cursor.execute(
                    "SELECT expires_on FROM user_monthly_card WHERE uid=%s FOR UPDATE",
                    (uid,),
                )
                card = await cursor.fetchone()
                previous_expires_on = card[0] if card else None
                new_expires_on = calculate_stacked_expiry(today, previous_expires_on, days)
                balance_before = int(player[1] or 0)
                balance_after = balance_before + int(activation_xianyu)

                await cursor.execute(
                    "UPDATE user_zt SET xianyu=%s WHERE id=%s",
                    (balance_after, uid),
                )
                await cursor.execute(
                    """
                    INSERT INTO user_monthly_card(
                        uid,expires_on,total_days_activated,total_days_claimed,last_claim_date
                    ) VALUES(%s,%s,%s,0,NULL)
                    ON DUPLICATE KEY UPDATE
                        expires_on=VALUES(expires_on),
                        total_days_activated=total_days_activated+VALUES(total_days_activated)
                    """,
                    (uid, new_expires_on, int(days)),
                )
                await cursor.execute(
                    """
                    UPDATE monthly_card_redeem_code
                    SET status='REDEEMED',redeemed_by=%s,redeemed_at=NOW()
                    WHERE id=%s AND status='ACTIVE'
                    """,
                    (uid, code_id),
                )
                if cursor.rowcount <= 0:
                    raise MonthlyCardError("月卡码状态已变化，请勿重复兑换。")
                await cursor.execute(
                    """
                    INSERT INTO user_monthly_card_activation_log(
                        code_id,uid,days,previous_expires_on,new_expires_on,
                        activation_xianyu,balance_before,balance_after
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        code_id,
                        uid,
                        days,
                        previous_expires_on,
                        new_expires_on,
                        activation_xianyu,
                        balance_before,
                        balance_after,
                    ),
                )
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
    return {
        "code": display_monthly_card_code(code),
        "days": int(days),
        "activation_xianyu": int(activation_xianyu),
        "previous_expires_on": previous_expires_on,
        "expires_on": new_expires_on,
        "remaining_days": remaining_days(today, new_expires_on),
        "balance_before": balance_before,
        "balance_after": balance_after,
    }


async def claim_monthly_card(uid):
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_monthly_card_schema(cursor)
                await cursor.execute("SELECT CURDATE()")
                today = (await cursor.fetchone())[0]
                await cursor.execute(
                    "SELECT `name`,xianyu,lingshi FROM user_zt WHERE id=%s FOR UPDATE",
                    (uid,),
                )
                player = await cursor.fetchone()
                if not player:
                    raise MonthlyCardError("未找到玩家数据，请重新注册后再试。")
                await cursor.execute(
                    """
                    SELECT expires_on,total_days_claimed,last_claim_date
                    FROM user_monthly_card WHERE uid=%s FOR UPDATE
                    """,
                    (uid,),
                )
                card = await cursor.fetchone()
                if not card or card[0] < today:
                    raise MonthlyCardError("当前月卡尚未激活或已经到期。")
                expires_on, total_days_claimed, last_claim_date = card
                if last_claim_date == today:
                    raise MonthlyCardError("今日月卡奖励已经领取，请明日再来。")

                xianyu_before = int(player[1] or 0)
                lingshi_before = int(player[2] or 0)
                xianyu_after = xianyu_before + MONTHLY_CARD_DAILY_XIANYU
                lingshi_after = lingshi_before + MONTHLY_CARD_DAILY_LINGSHI
                await cursor.execute(
                    "UPDATE user_zt SET xianyu=%s,lingshi=%s WHERE id=%s",
                    (xianyu_after, lingshi_after, uid),
                )
                if cursor.rowcount != 1:
                    raise MonthlyCardError("玩家资产状态已变化，本次奖励未发放。")
                await cursor.execute(
                    """
                    INSERT INTO user_monthly_card_claim_log(
                        uid,claim_date,reward_xianyu,reward_lingshi,
                        xianyu_before,xianyu_after,lingshi_before,lingshi_after
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        uid,
                        today,
                        MONTHLY_CARD_DAILY_XIANYU,
                        MONTHLY_CARD_DAILY_LINGSHI,
                        xianyu_before,
                        xianyu_after,
                        lingshi_before,
                        lingshi_after,
                    ),
                )
                await cursor.execute(
                    """
                    UPDATE user_monthly_card
                    SET total_days_claimed=total_days_claimed+1,last_claim_date=%s
                    WHERE uid=%s
                    """,
                    (today, uid),
                )
                if cursor.rowcount != 1:
                    raise MonthlyCardError("月卡状态更新失败，本次奖励未发放。")
            await conn.commit()
        except BaseException:
            await conn.rollback()
            raise
    return {
        "claim_date": today,
        "expires_on": expires_on,
        "remaining_days": remaining_days(today, expires_on),
        "total_days_claimed": int(total_days_claimed) + 1,
        "reward_xianyu": MONTHLY_CARD_DAILY_XIANYU,
        "reward_lingshi": MONTHLY_CARD_DAILY_LINGSHI,
        "xianyu_after": xianyu_after,
        "lingshi_after": lingshi_after,
    }


async def get_monthly_card_status(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_monthly_card_schema(cursor)
            await cursor.execute("SELECT CURDATE()")
            today = (await cursor.fetchone())[0]
            await cursor.execute(
                """
                SELECT expires_on,total_days_activated,total_days_claimed,last_claim_date
                FROM user_monthly_card WHERE uid=%s
                """,
                (uid,),
            )
            card = await cursor.fetchone()
            await cursor.execute(
                """
                SELECT claim_date,reward_xianyu,reward_lingshi
                FROM user_monthly_card_claim_log
                WHERE uid=%s ORDER BY id DESC LIMIT 5
                """,
                (uid,),
            )
            recent = await cursor.fetchall()
            await conn.commit()
    if not card:
        return {
            "active": False,
            "today": today,
            "expires_on": None,
            "remaining_days": 0,
            "claimed_today": False,
            "total_days_activated": 0,
            "total_days_claimed": 0,
            "recent_claims": tuple(recent),
        }
    expires_on, total_days_activated, total_days_claimed, last_claim_date = card
    return {
        "active": expires_on >= today,
        "today": today,
        "expires_on": expires_on,
        "remaining_days": remaining_days(today, expires_on),
        "claimed_today": last_claim_date == today,
        "total_days_activated": int(total_days_activated),
        "total_days_claimed": int(total_days_claimed),
        "recent_claims": tuple(recent),
    }
