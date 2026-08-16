# -*- coding: utf-8 -*-
"""世界消息库、GM 管理操作与回复尾注轮换状态。"""

import hashlib
import logging
import re
from typing import Dict, List, Optional

from Game_domain.gm_service import GMError, require_admin
from sql.mysql import connect_mysql


logger = logging.getLogger(__name__)

MAX_WORLD_MESSAGE_LENGTH = 180
DEFAULT_LIST_LIMIT = 30
OFFICIAL_SLOT = 0
WORLD_MESSAGE_SLOT = 1
ROTATION_STATE_KEY = "reply_footer"
_rotation_failure_logged = False


class WorldMessageError(GMError):
    """管理员维护世界消息库时可直接展示的业务错误。"""


def normalize_world_message_content(value: str) -> str:
    """把攻略小贴士规范为适合回复尾注的一行纯文本。"""
    content = " ".join(str(value or "").split())
    if not content:
        raise WorldMessageError("世界消息内容不能为空。")
    if len(content) > MAX_WORLD_MESSAGE_LENGTH:
        raise WorldMessageError(
            f"世界消息不能超过 {MAX_WORLD_MESSAGE_LENGTH} 个字符。"
        )
    return content


def parse_world_message_id(value: str) -> int:
    raw = str(value or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        raise WorldMessageError("世界消息 ID 必须是正整数。")
    return int(raw)


def parse_world_message_update(value: str):
    matched = re.fullmatch(r"(\d+)\s*-\s*(.+)", str(value or "").strip(), re.DOTALL)
    if not matched:
        raise WorldMessageError("格式：GM世界消息修改 ID-新内容")
    return parse_world_message_id(matched.group(1)), normalize_world_message_content(
        matched.group(2)
    )


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _database_error(exc: Exception) -> WorldMessageError:
    return WorldMessageError(
        "世界消息库访问失败，请确认已执行 p2_world_message.sql 数据库迁移。"
    )


async def list_world_messages(operator_uid: int, limit: int = DEFAULT_LIST_LIMIT) -> List[Dict]:
    require_admin(operator_uid)
    limit = max(1, min(100, int(limit)))
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """SELECT id,content,enabled,created_by,updated_by
                       FROM world_message
                       WHERE is_deleted=0
                       ORDER BY id ASC LIMIT %s""",
                    (limit,),
                )
                rows = await cursor.fetchall()
    except Exception as exc:
        raise _database_error(exc) from exc
    return [
        {
            "id": int(row[0]),
            "content": row[1],
            "enabled": bool(row[2]),
            "created_by": int(row[3]),
            "updated_by": int(row[4]),
        }
        for row in rows
    ]


async def add_world_message(operator_uid: int, content: str) -> Dict:
    require_admin(operator_uid)
    content = normalize_world_message_content(content)
    digest = _content_hash(content)
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """SELECT id,content,enabled,is_deleted
                       FROM world_message WHERE content_hash=%s LIMIT 1 FOR UPDATE""",
                    (digest,),
                )
                row = await cursor.fetchone()
                if row:
                    message_id = int(row[0])
                    restored = not bool(row[2]) or bool(row[3])
                    if restored:
                        await cursor.execute(
                            """UPDATE world_message
                               SET content=%s,enabled=1,is_deleted=0,updated_by=%s
                               WHERE id=%s""",
                            (content, operator_uid, message_id),
                        )
                    await conn.commit()
                    return {
                        "id": message_id,
                        "content": content,
                        "enabled": True,
                        "created": False,
                        "restored": restored,
                    }

                await cursor.execute(
                    """INSERT INTO world_message
                       (content,content_hash,enabled,is_deleted,created_by,updated_by)
                       VALUES (%s,%s,1,0,%s,%s)""",
                    (content, digest, operator_uid, operator_uid),
                )
                message_id = int(cursor.lastrowid)
            await conn.commit()
    except Exception as exc:
        if isinstance(exc, WorldMessageError):
            raise
        raise _database_error(exc) from exc
    return {
        "id": message_id,
        "content": content,
        "enabled": True,
        "created": True,
        "restored": False,
    }


async def update_world_message(operator_uid: int, message_id: int, content: str) -> Dict:
    require_admin(operator_uid)
    message_id = parse_world_message_id(message_id)
    content = normalize_world_message_content(content)
    digest = _content_hash(content)
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """SELECT content FROM world_message
                       WHERE id=%s AND is_deleted=0 LIMIT 1 FOR UPDATE""",
                    (message_id,),
                )
                row = await cursor.fetchone()
                if not row:
                    raise WorldMessageError(f"未找到世界消息 ID：{message_id}")
                await cursor.execute(
                    """SELECT id FROM world_message
                       WHERE content_hash=%s AND id<>%s LIMIT 1""",
                    (digest, message_id),
                )
                duplicate = await cursor.fetchone()
                if duplicate:
                    raise WorldMessageError(
                        f"相同内容已存在于世界消息 ID：{int(duplicate[0])}"
                    )
                await cursor.execute(
                    """UPDATE world_message
                       SET content=%s,content_hash=%s,updated_by=%s
                       WHERE id=%s""",
                    (content, digest, operator_uid, message_id),
                )
            await conn.commit()
    except Exception as exc:
        if isinstance(exc, WorldMessageError):
            raise
        raise _database_error(exc) from exc
    return {"id": message_id, "content": content}


async def set_world_message_enabled(
    operator_uid: int, message_id: int, enabled: bool
) -> Dict:
    require_admin(operator_uid)
    message_id = parse_world_message_id(message_id)
    enabled = bool(enabled)
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """SELECT content,enabled FROM world_message
                       WHERE id=%s AND is_deleted=0 LIMIT 1 FOR UPDATE""",
                    (message_id,),
                )
                row = await cursor.fetchone()
                if not row:
                    raise WorldMessageError(f"未找到世界消息 ID：{message_id}")
                changed = bool(row[1]) != enabled
                if changed:
                    await cursor.execute(
                        """UPDATE world_message SET enabled=%s,updated_by=%s
                           WHERE id=%s""",
                        (int(enabled), operator_uid, message_id),
                    )
            await conn.commit()
    except Exception as exc:
        if isinstance(exc, WorldMessageError):
            raise
        raise _database_error(exc) from exc
    return {
        "id": message_id,
        "content": row[0],
        "enabled": enabled,
        "changed": changed,
    }


async def delete_world_message(operator_uid: int, message_id: int) -> Dict:
    """软删除消息，使平台重投同一 GM 指令时仍保持幂等。"""
    require_admin(operator_uid)
    message_id = parse_world_message_id(message_id)
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """SELECT content,is_deleted FROM world_message
                       WHERE id=%s LIMIT 1 FOR UPDATE""",
                    (message_id,),
                )
                row = await cursor.fetchone()
                if not row:
                    raise WorldMessageError(f"未找到世界消息 ID：{message_id}")
                changed = not bool(row[1])
                if changed:
                    await cursor.execute(
                        """UPDATE world_message
                           SET enabled=0,is_deleted=1,updated_by=%s WHERE id=%s""",
                        (operator_uid, message_id),
                    )
            await conn.commit()
    except Exception as exc:
        if isinstance(exc, WorldMessageError):
            raise
        raise _database_error(exc) from exc
    return {"id": message_id, "content": row[0], "changed": changed}


async def next_world_message_slot() -> Optional[str]:
    """原子取得下一个尾注槽位；None 表示本轮展示官方群提示。"""
    global _rotation_failure_logged
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                # 临时玩法事件优先于常驻攻略轮播；发布后立即标记，避免重复展示。
                await cursor.execute(
                    """SELECT id,content FROM world_message_event_queue
                       WHERE status='PENDING' AND available_at<=NOW() AND expires_at>NOW()
                       ORDER BY id ASC LIMIT 1 FOR UPDATE"""
                )
                event_message = await cursor.fetchone()
                if event_message:
                    await cursor.execute(
                        """UPDATE world_message_event_queue
                           SET status='PUBLISHED',published_at=NOW()
                           WHERE id=%s AND status='PENDING'""",
                        (int(event_message[0]),),
                    )
                    await conn.commit()
                    _rotation_failure_logged = False
                    return str(event_message[1])

                await cursor.execute(
                    """INSERT IGNORE INTO world_message_state
                       (state_key,next_source,last_message_id)
                       VALUES (%s,%s,NULL)""",
                    (ROTATION_STATE_KEY, OFFICIAL_SLOT),
                )
                await cursor.execute(
                    """SELECT next_source,last_message_id
                       FROM world_message_state
                       WHERE state_key=%s LIMIT 1 FOR UPDATE""",
                    (ROTATION_STATE_KEY,),
                )
                state = await cursor.fetchone()
                next_source = int(state[0]) if state else OFFICIAL_SLOT
                last_message_id = int(state[1]) if state and state[1] else 0

                if next_source == OFFICIAL_SLOT:
                    await cursor.execute(
                        """UPDATE world_message_state SET next_source=%s
                           WHERE state_key=%s""",
                        (WORLD_MESSAGE_SLOT, ROTATION_STATE_KEY),
                    )
                    await conn.commit()
                    _rotation_failure_logged = False
                    return None

                await cursor.execute(
                    """SELECT id,content FROM world_message
                       WHERE enabled=1 AND is_deleted=0 AND id>%s
                       ORDER BY id ASC LIMIT 1""",
                    (last_message_id,),
                )
                message = await cursor.fetchone()
                if not message:
                    await cursor.execute(
                        """SELECT id,content FROM world_message
                           WHERE enabled=1 AND is_deleted=0
                           ORDER BY id ASC LIMIT 1"""
                    )
                    message = await cursor.fetchone()
                if not message:
                    await conn.commit()
                    _rotation_failure_logged = False
                    return None

                await cursor.execute(
                    """UPDATE world_message_state
                       SET next_source=%s,last_message_id=%s WHERE state_key=%s""",
                    (OFFICIAL_SLOT, int(message[0]), ROTATION_STATE_KEY),
                )
            await conn.commit()
        _rotation_failure_logged = False
        return str(message[1])
    except Exception:
        if not _rotation_failure_logged:
            logger.exception("世界消息轮换失败，已降级为官方群提示")
            _rotation_failure_logged = True
        return None
