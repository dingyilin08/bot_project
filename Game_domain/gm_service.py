# -*- coding: utf-8 -*-
"""GM 鉴权、资产发放与审计服务。"""

import hmac
import json
import re
from uuid import uuid4

from Game_domain.gm_state import grant_admin, is_admin
from sql.mysql import connect_mysql


MAX_GRANT_AMOUNT = 1_000_000_000


class GMError(Exception):
    pass


def authenticate_admin(uid: int, password: str, expected_password: str) -> bool:
    expected = str(expected_password or "")
    supplied = str(password or "")
    if not expected:
        raise GMError("服务器尚未配置 ADMIN_PASSWORD，无法验证管理员密令。")
    # 命令解析器历史上会统一转大写，沿用原图片模式密令的不区分大小写口径。
    if not hmac.compare_digest(supplied.upper().encode("utf-8"), expected.upper().encode("utf-8")):
        raise GMError("管理员密令错误。")
    grant_admin(int(uid))
    return True


def require_admin(uid: int) -> None:
    if not is_admin(uid):
        raise GMError("你不是管理员，请先发送“GM验证”完成密令验证。")


def parse_item_grant(value: str):
    matched = re.fullmatch(r"(\d+)-(.+)-(\d+)", str(value or "").strip())
    if not matched:
        raise GMError("格式：GM发放物品 目标UID-物品名称或编号-数量")
    target_uid, item_key, amount = int(matched.group(1)), matched.group(2).strip(), int(matched.group(3))
    _validate_amount(target_uid, amount)
    return target_uid, item_key, amount


def parse_xianyu_grant(value: str):
    matched = re.fullmatch(r"(\d+)-(\d+)", str(value or "").strip())
    if not matched:
        raise GMError("格式：GM发放仙玉 目标UID-数量")
    target_uid, amount = int(matched.group(1)), int(matched.group(2))
    _validate_amount(target_uid, amount)
    return target_uid, amount


def parse_global_grant(value: str, command: str) -> int:
    matched = re.fullmatch(r"\d+", str(value or "").strip())
    if not matched:
        raise GMError(f"格式：{command} 数量")
    amount = int(matched.group(0))
    if amount <= 0 or amount > MAX_GRANT_AMOUNT:
        raise GMError(f"发放数量必须在 1—{MAX_GRANT_AMOUNT} 之间。")
    return amount


def _validate_amount(target_uid: int, amount: int) -> None:
    if target_uid <= 0:
        raise GMError("目标 UID 无效。")
    if amount <= 0 or amount > MAX_GRANT_AMOUNT:
        raise GMError(f"发放数量必须在 1—{MAX_GRANT_AMOUNT} 之间。")


def _loads(value):
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


async def _existing_operation(cursor, request_id: str):
    await cursor.execute(
        "SELECT status,result_json FROM gm_operation_log WHERE request_id=%s LIMIT 1",
        (request_id,),
    )
    row = await cursor.fetchone()
    if row and row[0] == "SUCCESS":
        return _loads(row[1])
    return None


async def grant_item(*, operator_uid: int, target_uid: int, item_key: str,
                     amount: int, request_id: str = None) -> dict:
    require_admin(operator_uid)
    _validate_amount(int(target_uid), int(amount))
    request_id = str(request_id or f"gm:{uuid4().hex}")[:80]
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT id,`name` FROM user_zt WHERE id=%s FOR UPDATE", (target_uid,))
                player = await cursor.fetchone()
                if not player:
                    raise GMError("目标玩家不存在。")
                existing = await _existing_operation(cursor, request_id)
                if existing:
                    return existing
                if str(item_key).isdigit():
                    await cursor.execute("SELECT id,`name` FROM data_item WHERE id=%s LIMIT 1", (int(item_key),))
                else:
                    await cursor.execute("SELECT id,`name` FROM data_item WHERE `name`=%s LIMIT 1", (item_key,))
                item = await cursor.fetchone()
                if not item:
                    raise GMError(f"未找到物品：{item_key}")
                item_id, item_name = int(item[0]), item[1]
                await cursor.execute(
                    "SELECT item_num FROM user_item WHERE uid=%s AND item_id=%s FOR UPDATE",
                    (target_uid, item_id),
                )
                row = await cursor.fetchone()
                balance_before = int(row[0]) if row else 0
                balance_after = balance_before + int(amount)
                await cursor.execute(
                    """INSERT INTO user_item (uid,item_id,item_num) VALUES (%s,%s,%s)
                       ON DUPLICATE KEY UPDATE item_num=item_num+VALUES(item_num)""",
                    (target_uid, item_id, amount),
                )
                result = {"operation": "GRANT_ITEM", "operator_uid": int(operator_uid),
                          "target_uid": int(target_uid), "target_name": player[1],
                          "item_id": item_id, "item_name": item_name, "amount": int(amount),
                          "balance_before": balance_before, "balance_after": balance_after}
                payload = json.dumps(result, ensure_ascii=False)
                await cursor.execute(
                    """INSERT INTO reward_ledger
                       (business_key,uid,reward_type,amount,source_type,source_id,status,payload_json)
                       VALUES (%s,%s,'ITEM',%s,'GM',%s,'GRANTED',%s)""",
                    (f"gm:{request_id}:item", target_uid, amount, str(operator_uid), payload),
                )
                await cursor.execute(
                    """INSERT INTO gm_operation_log
                       (request_id,operator_uid,target_uid,operation_type,item_id,amount,
                        balance_before,balance_after,status,result_json)
                       VALUES (%s,%s,%s,'GRANT_ITEM',%s,%s,%s,%s,'SUCCESS',%s)""",
                    (request_id, operator_uid, target_uid, item_id, amount,
                     balance_before, balance_after, payload),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return result


async def grant_xianyu(*, operator_uid: int, target_uid: int, amount: int,
                       request_id: str = None) -> dict:
    require_admin(operator_uid)
    _validate_amount(int(target_uid), int(amount))
    request_id = str(request_id or f"gm:{uuid4().hex}")[:80]
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT `name`,xianyu FROM user_zt WHERE id=%s FOR UPDATE", (target_uid,))
                player = await cursor.fetchone()
                if not player:
                    raise GMError("目标玩家不存在。")
                existing = await _existing_operation(cursor, request_id)
                if existing:
                    return existing
                balance_before = int(player[1])
                balance_after = balance_before + int(amount)
                await cursor.execute("UPDATE user_zt SET xianyu=xianyu+%s WHERE id=%s", (amount, target_uid))
                result = {"operation": "GRANT_XIANYU", "operator_uid": int(operator_uid),
                          "target_uid": int(target_uid), "target_name": player[0],
                          "amount": int(amount), "balance_before": balance_before,
                          "balance_after": balance_after}
                payload = json.dumps(result, ensure_ascii=False)
                await cursor.execute(
                    """INSERT INTO reward_ledger
                       (business_key,uid,reward_type,amount,source_type,source_id,status,payload_json)
                       VALUES (%s,%s,'XIANYU',%s,'GM',%s,'GRANTED',%s)""",
                    (f"gm:{request_id}:xianyu", target_uid, amount, str(operator_uid), payload),
                )
                await cursor.execute(
                    """INSERT INTO gm_operation_log
                       (request_id,operator_uid,target_uid,operation_type,amount,
                        balance_before,balance_after,status,result_json)
                       VALUES (%s,%s,%s,'GRANT_XIANYU',%s,%s,%s,'SUCCESS',%s)""",
                    (request_id, operator_uid, target_uid, amount,
                     balance_before, balance_after, payload),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return result


async def grant_all_currency(*, operator_uid: int, currency: str, amount: int,
                             request_id: str = None) -> dict:
    """Atomically grant one currency amount to every existing player."""
    require_admin(operator_uid)
    currency_config = {
        "lingshi": ("灵石", "LINGSHI", "GRANT_ALL_LINGSHI"),
        "xianyu": ("仙玉", "XIANYU", "GRANT_ALL_XIANYU"),
    }
    if currency not in currency_config:
        raise GMError("不支持的全服发放货币。")
    currency_name, reward_type, operation_type = currency_config[currency]
    amount = parse_global_grant(amount, f"GM全服发放{currency_name}")
    request_id = str(request_id or f"gm:{uuid4().hex}")[:80]

    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                existing = await _existing_operation(cursor, request_id)
                if existing:
                    return existing
                await cursor.execute("SELECT COUNT(*) FROM user_zt")
                player_count = int((await cursor.fetchone())[0])
                if player_count <= 0:
                    raise GMError("当前没有可发放奖励的玩家。")

                await cursor.execute(
                    f"UPDATE user_zt SET {currency}={currency}+%s",
                    (amount,),
                )
                recipient_count = int(cursor.rowcount)
                total_amount = recipient_count * amount
                result = {
                    "operation": operation_type,
                    "operator_uid": int(operator_uid),
                    "currency": currency,
                    "currency_name": currency_name,
                    "amount_per_player": amount,
                    "recipient_count": recipient_count,
                    "total_amount": total_amount,
                }
                payload = json.dumps(result, ensure_ascii=False)
                await cursor.execute(
                    """INSERT INTO reward_ledger
                       (business_key,uid,reward_type,amount,source_type,source_id,status,payload_json)
                       VALUES (%s,0,%s,%s,'GM',%s,'GRANTED',%s)""",
                    (f"gm:{request_id}:all:{currency}", reward_type, total_amount,
                     str(operator_uid), payload),
                )
                await cursor.execute(
                    """INSERT INTO gm_operation_log
                       (request_id,operator_uid,target_uid,operation_type,amount,
                        balance_before,balance_after,status,result_json)
                       VALUES (%s,%s,0,%s,%s,0,%s,'SUCCESS',%s)""",
                    (request_id, operator_uid, operation_type, amount,
                     recipient_count, payload),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return result
