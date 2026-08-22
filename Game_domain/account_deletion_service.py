# -*- coding: utf-8 -*-
"""低等级玩家账号删除规则与事务服务。"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from sql.mysql import connect_mysql


ACCOUNT_DELETION_LEVEL_LIMIT = 10
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_USER_REFERENCE_COLUMNS = (
    "uid",
    "owner_uid",
    "leader_uid",
    "master_uid",
    "apprentice_uid",
    "operator_uid",
    "target_uid",
    "helper_uid",
    "inviter_uid",
    "invitee_uid",
    "buyer_uid",
    "seller_uid",
    "active_uid",
)

# 奖励、兑换、交易和管理审计不属于可重置资产；保留可防止删号后重放。
_PRESERVED_TABLES = frozenset(
    {
        "account_deletion_log",
        "gm_operation_log",
        "reward_ledger",
        "user_invitation_profile",
        "user_invitation_reward",
        "user_market_trade",
        "user_monthly_card_activation_log",
        "user_monthly_card_claim_log",
        "user_xianyu_redeem_log",
        "web_admin_audit",
    }
)
_SPECIAL_RELATION_TABLES = frozenset({"party", "sect", "expedition_session"})
_SCHEMA_READY = False


class AccountDeletionError(Exception):
    """可直接展示给玩家的删号失败原因。"""


async def ensure_account_deletion_schema(cursor) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    await cursor.execute(
        """SELECT COUNT(*) FROM information_schema.TABLES
           WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='account_deletion_log'"""
    )
    if int((await cursor.fetchone())[0] or 0) > 0:
        _SCHEMA_READY = True
        return
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS account_deletion_log (
            openid_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            last_uid INT NOT NULL,
            role_count INT UNSIGNED NOT NULL,
            highest_role_level INT UNSIGNED NOT NULL,
            deletion_count INT UNSIGNED NOT NULL DEFAULT 1,
            first_deleted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_deleted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (openid_hash),
            KEY idx_account_deletion_uid (last_uid),
            KEY idx_account_deletion_time (last_deleted_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
          COMMENT='玩家主动删号的最小化防滥用审计'
        """
    )
    _SCHEMA_READY = True


def validate_account_deletion_roles(roles) -> dict:
    normalized = [
        {
            "id": int(row[0]),
            "name": str(row[1]),
            "level": int(row[2] or 0),
            "active": bool(row[3]),
        }
        for row in roles
    ]
    if not normalized:
        raise AccountDeletionError("尚未选择角色，当前账号不能执行删号。")
    highest = max(role["level"] for role in normalized)
    if highest >= ACCOUNT_DELETION_LEVEL_LIMIT:
        raise AccountDeletionError(
            f"账号最高角色已达到{highest}级；只有所有角色均未达到"
            f"{ACCOUNT_DELETION_LEVEL_LIMIT}级的账号可以删号。"
        )
    active = next((role for role in normalized if role["active"]), None)
    return {
        "role_count": len(normalized),
        "highest_role_level": highest,
        "roles": normalized,
        "active_role": active,
    }


async def _load_account(cursor, uid: int, *, for_update: bool) -> tuple:
    lock = " FOR UPDATE" if for_update else ""
    await cursor.execute(
        f"SELECT id,openid,`name` FROM user_zt WHERE id=%s LIMIT 1{lock}",
        (uid,),
    )
    account = await cursor.fetchone()
    if not account:
        raise AccountDeletionError("玩家资料不存在，可能已经完成删号。")
    await cursor.execute(
        f"SELECT id,`name`,dengji,is_chuzhan FROM user_role "
        f"WHERE uid=%s ORDER BY id{lock}",
        (uid,),
    )
    roles = await cursor.fetchall()
    summary = validate_account_deletion_roles(roles)
    return account, summary


async def get_account_deletion_preview(uid: int) -> dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_account_deletion_schema(cursor)
            account, summary = await _load_account(cursor, uid, for_update=False)
            return {
                "uid": int(account[0]),
                "player_name": account[2],
                **summary,
            }


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(str(value or "")):
        raise RuntimeError("数据库返回了不安全的表或字段名。")
    return f"`{value}`"


def build_user_delete_statement(table: str, columns) -> tuple[str, int]:
    safe_table = _safe_identifier(table)
    safe_columns = [_safe_identifier(column) for column in columns]
    if not safe_columns:
        raise ValueError("删除语句至少需要一个玩家关联字段。")
    where = " OR ".join(f"{column}=%s" for column in safe_columns)
    return f"DELETE FROM {safe_table} WHERE {where}", len(safe_columns)


async def _transfer_parties(cursor, uid: int) -> None:
    await cursor.execute("SELECT id FROM party WHERE leader_uid=%s FOR UPDATE", (uid,))
    for (party_id,) in await cursor.fetchall():
        await cursor.execute(
            """SELECT uid FROM party_member
               WHERE party_id=%s AND uid<>%s AND member_state='ACTIVE'
               ORDER BY joined_at,id LIMIT 1 FOR UPDATE""",
            (party_id, uid),
        )
        successor = await cursor.fetchone()
        if successor:
            await cursor.execute(
                "UPDATE party SET leader_uid=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                (successor[0], party_id),
            )
            continue
        await cursor.execute(
            "SELECT id FROM party_battle_session WHERE party_id=%s FOR UPDATE",
            (party_id,),
        )
        session_ids = [row[0] for row in await cursor.fetchall()]
        for session_id in session_ids:
            await cursor.execute("DELETE FROM party_battle_action WHERE session_id=%s", (session_id,))
            await cursor.execute("DELETE FROM party_battle_member WHERE session_id=%s", (session_id,))
        await cursor.execute("DELETE FROM party_battle_session WHERE party_id=%s", (party_id,))
        await cursor.execute("DELETE FROM party_member WHERE party_id=%s", (party_id,))
        await cursor.execute("DELETE FROM party WHERE id=%s", (party_id,))


async def _transfer_expeditions(cursor, uid: int) -> None:
    await cursor.execute(
        "SELECT id FROM expedition_session WHERE leader_uid=%s FOR UPDATE", (uid,)
    )
    for (session_id,) in await cursor.fetchall():
        await cursor.execute(
            """SELECT uid FROM expedition_member
               WHERE session_id=%s AND uid<>%s AND member_state='ACTIVE'
               ORDER BY joined_at,id LIMIT 1 FOR UPDATE""",
            (session_id, uid),
        )
        successor = await cursor.fetchone()
        if successor:
            await cursor.execute(
                "UPDATE expedition_session SET leader_uid=%s WHERE id=%s",
                (successor[0], session_id),
            )
            continue
        await cursor.execute("DELETE FROM expedition_node_log WHERE session_id=%s", (session_id,))
        await cursor.execute("DELETE FROM expedition_vote WHERE session_id=%s", (session_id,))
        await cursor.execute("DELETE FROM expedition_member WHERE session_id=%s", (session_id,))
        await cursor.execute("DELETE FROM expedition_session WHERE id=%s", (session_id,))


async def _transfer_sects(cursor, uid: int) -> None:
    await cursor.execute("SELECT id FROM sect WHERE leader_uid=%s FOR UPDATE", (uid,))
    for (sect_id,) in await cursor.fetchall():
        await cursor.execute(
            """SELECT uid FROM sect_member
               WHERE sect_id=%s AND uid<>%s AND member_state='ACTIVE'
               ORDER BY contribution DESC,joined_at,id LIMIT 1 FOR UPDATE""",
            (sect_id, uid),
        )
        successor = await cursor.fetchone()
        if successor:
            await cursor.execute("UPDATE sect SET leader_uid=%s WHERE id=%s", (successor[0], sect_id))
            await cursor.execute(
                "UPDATE sect_member SET role='掌门' WHERE sect_id=%s AND uid=%s",
                (sect_id, successor[0]),
            )
            continue
        await cursor.execute(
            """SELECT TABLE_NAME FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='sect_id'
                 AND TABLE_NAME<>'sect'
               ORDER BY TABLE_NAME"""
        )
        for (table,) in await cursor.fetchall():
            sql, _ = build_user_delete_statement(table, ("sect_id",))
            await cursor.execute(sql, (sect_id,))
        await cursor.execute("DELETE FROM sect WHERE id=%s", (sect_id,))


async def _delete_spirit_beast_children(cursor, uid: int) -> None:
    await cursor.execute("SELECT id FROM user_spirit_beast_v2 WHERE uid=%s FOR UPDATE", (uid,))
    beast_ids = [int(row[0]) for row in await cursor.fetchall()]
    for beast_id in beast_ids:
        await cursor.execute(
            "DELETE FROM user_spirit_beast_skill_slot WHERE beast_id=%s", (beast_id,)
        )
        await cursor.execute(
            "DELETE FROM user_spirit_beast_aptitude WHERE beast_id=%s", (beast_id,)
        )


async def _discover_user_tables(cursor) -> dict[str, list[str]]:
    placeholders = ",".join(["%s"] * len(_USER_REFERENCE_COLUMNS))
    await cursor.execute(
        f"""SELECT c.TABLE_NAME,c.COLUMN_NAME
            FROM information_schema.COLUMNS c
            JOIN information_schema.TABLES t
              ON t.TABLE_SCHEMA=c.TABLE_SCHEMA AND t.TABLE_NAME=c.TABLE_NAME
            WHERE c.TABLE_SCHEMA=DATABASE() AND t.TABLE_TYPE='BASE TABLE'
              AND c.COLUMN_NAME IN ({placeholders})
            ORDER BY c.TABLE_NAME,c.ORDINAL_POSITION""",
        _USER_REFERENCE_COLUMNS,
    )
    tables = defaultdict(list)
    for table, column in await cursor.fetchall():
        if table in _PRESERVED_TABLES or table in _SPECIAL_RELATION_TABLES:
            continue
        tables[str(table)].append(str(column))
    return dict(tables)


async def allocate_player_uid(cursor) -> int:
    """避免删号后 COUNT(*) 回退导致 UID 与历史流水冲突。"""

    await ensure_account_deletion_schema(cursor)
    await cursor.execute(
        """SELECT GREATEST(
               COALESCE((SELECT MAX(id) FROM user_zt),100000),
               COALESCE((SELECT MAX(uid) FROM user_invitation_profile),100000),
               COALESCE((SELECT MAX(last_uid) FROM account_deletion_log),100000)
           ) + 1"""
    )
    return int((await cursor.fetchone())[0])


async def was_openid_deleted(cursor, openid: str) -> bool:
    await ensure_account_deletion_schema(cursor)
    digest = hashlib.sha256(str(openid).encode("utf-8")).hexdigest()
    await cursor.execute(
        "SELECT 1 FROM account_deletion_log WHERE openid_hash=%s LIMIT 1", (digest,)
    )
    return bool(await cursor.fetchone())


async def delete_player_account(uid: int) -> dict:
    portrait_keys = []
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_account_deletion_schema(cursor)
                account, summary = await _load_account(cursor, uid, for_update=True)
                openid_hash = hashlib.sha256(str(account[1]).encode("utf-8")).hexdigest()

                await cursor.execute(
                    "SELECT storage_key FROM power_portrait_submission WHERE uid=%s FOR UPDATE",
                    (uid,),
                )
                portrait_keys = [row[0] for row in await cursor.fetchall()]

                await _delete_spirit_beast_children(cursor, uid)
                await _transfer_parties(cursor, uid)
                await _transfer_expeditions(cursor, uid)
                await _transfer_sects(cursor, uid)

                deleted_rows = 0
                for table, columns in (await _discover_user_tables(cursor)).items():
                    sql, parameter_count = build_user_delete_statement(table, columns)
                    await cursor.execute(sql, tuple([uid] * parameter_count))
                    deleted_rows += max(0, int(cursor.rowcount or 0))

                await cursor.execute(
                    """INSERT INTO account_deletion_log
                       (openid_hash,last_uid,role_count,highest_role_level)
                       VALUES (%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                         last_uid=VALUES(last_uid),
                         role_count=VALUES(role_count),
                         highest_role_level=VALUES(highest_role_level),
                         deletion_count=deletion_count+1,
                         last_deleted_at=CURRENT_TIMESTAMP""",
                    (
                        openid_hash,
                        uid,
                        summary["role_count"],
                        summary["highest_role_level"],
                    ),
                )
                await cursor.execute("DELETE FROM user_zt WHERE id=%s", (uid,))
                if cursor.rowcount != 1:
                    raise RuntimeError("玩家主记录删除失败。")
            await conn.commit()
        except AccountDeletionError:
            await conn.rollback()
            raise
        except Exception:
            await conn.rollback()
            raise

    from Tool.power_portrait import remove_portrait_file

    for storage_key in portrait_keys:
        remove_portrait_file(storage_key)
    return {
        "uid": int(uid),
        "role_count": summary["role_count"],
        "highest_role_level": summary["highest_role_level"],
        "deleted_rows": deleted_rows,
    }
