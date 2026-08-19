# -*- coding: utf-8 -*-
"""玩家战力立绘提交、GM 审核与生效状态服务。"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from uuid import uuid4

from Game_domain.gm_service import require_admin
from sql.mysql import connect_mysql
from Tool.power_portrait import (
    PowerPortraitError,
    download_and_store_portrait,
    image_attachments,
    portrait_file_path,
    remove_portrait_file,
)


UPLOAD_INTENT_TTL_SECONDS = 300
_UPLOAD_INTENTS = {}
_UPLOAD_INTENTS_LOCK = threading.Lock()
_POWER_PORTRAIT_SCHEMA_READY = False


async def ensure_power_portrait_schema(cursor) -> None:
    """幂等创建审核表，保证自动发布后无需等待人工迁移才能回退默认图。"""
    global _POWER_PORTRAIT_SCHEMA_READY
    if _POWER_PORTRAIT_SCHEMA_READY:
        return
    await cursor.execute(
        """CREATE TABLE IF NOT EXISTS power_portrait_submission (
            id BIGINT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin
                NOT NULL DEFAULT 'PENDING',
            storage_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            original_filename VARCHAR(255) NOT NULL DEFAULT '',
            content_type VARCHAR(80) CHARACTER SET ascii COLLATE ascii_general_ci
                NOT NULL DEFAULT 'image',
            width INT UNSIGNED NOT NULL,
            height INT UNSIGNED NOT NULL,
            file_size INT UNSIGNED NOT NULL,
            sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            platform_request_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
            reviewed_by INT NULL,
            reject_reason VARCHAR(120) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at DATETIME NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_power_portrait_storage (storage_key),
            UNIQUE KEY uk_power_portrait_request (platform_request_id),
            KEY idx_power_portrait_queue (status, id),
            KEY idx_power_portrait_user (uid, status, id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
          COMMENT='玩家战力立绘提交与GM审核'"""
    )
    _POWER_PORTRAIT_SCHEMA_READY = True


def begin_upload_intent(uid: int) -> None:
    with _UPLOAD_INTENTS_LOCK:
        _UPLOAD_INTENTS[int(uid)] = time.monotonic() + UPLOAD_INTENT_TTL_SECONDS


def has_upload_intent(uid: int) -> bool:
    if not uid:
        return False
    now = time.monotonic()
    with _UPLOAD_INTENTS_LOCK:
        deadline = _UPLOAD_INTENTS.get(int(uid), 0)
        if deadline <= now:
            _UPLOAD_INTENTS.pop(int(uid), None)
            return False
        return True


def consume_upload_intent(uid: int) -> bool:
    if not has_upload_intent(uid):
        return False
    with _UPLOAD_INTENTS_LOCK:
        _UPLOAD_INTENTS.pop(int(uid), None)
    return True


def _submission_row(row) -> dict | None:
    if not row:
        return None
    return {
        "id": int(row[0]),
        "uid": int(row[1]),
        "player_name": row[2] or "无名道友",
        "status": row[3],
        "storage_key": row[4],
        "original_filename": row[5] or "",
        "width": int(row[6] or 0),
        "height": int(row[7] or 0),
        "file_size": int(row[8] or 0),
        "reject_reason": row[9] or "",
        "created_at": row[10],
        "reviewed_at": row[11],
        "reviewed_by": int(row[12] or 0),
    }


_SUBMISSION_SELECT = """
    SELECT ps.id,ps.uid,uz.`name`,ps.status,ps.storage_key,
           ps.original_filename,ps.width,ps.height,ps.file_size,
           ps.reject_reason,ps.created_at,ps.reviewed_at,ps.reviewed_by
    FROM power_portrait_submission ps
    JOIN user_zt uz ON uz.id=ps.uid
"""


async def _find_by_request_id(request_id: str | None):
    if not request_id:
        return None
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_power_portrait_schema(cursor)
            await cursor.execute(
                _SUBMISSION_SELECT
                + " WHERE ps.platform_request_id=%s LIMIT 1",
                (str(request_id)[:128],),
            )
            return _submission_row(await cursor.fetchone())


async def submit_portrait(uid: int, attachments, request_id: str | None = None) -> dict:
    """保存一张待审立绘；提交本身绝不会替换当前已通过立绘。"""
    images = image_attachments(attachments)
    if not images:
        raise PowerPortraitError("没有检测到图片，请发送一张图片。")
    if len(images) != 1:
        raise PowerPortraitError("每次只能提交一张图片，请重新发送。")
    existing = await _find_by_request_id(request_id)
    if existing:
        return existing

    storage_key = f"portrait_{uuid4().hex}.jpg"
    metadata = await download_and_store_portrait(images[0], storage_key)
    superseded_keys = []
    try:
        async with connect_mysql() as conn:
            try:
                async with conn.cursor() as cursor:
                    await ensure_power_portrait_schema(cursor)
                    await cursor.execute(
                        "SELECT `name` FROM user_zt WHERE id=%s FOR UPDATE", (uid,)
                    )
                    player = await cursor.fetchone()
                    if not player:
                        raise PowerPortraitError("玩家资料不存在，请先注册游戏。")

                    await cursor.execute(
                        """SELECT storage_key FROM power_portrait_submission
                           WHERE uid=%s AND status='PENDING' FOR UPDATE""",
                        (uid,),
                    )
                    superseded_keys = [row[0] for row in await cursor.fetchall()]
                    if superseded_keys:
                        await cursor.execute(
                            """UPDATE power_portrait_submission
                               SET status='SUPERSEDED',reviewed_at=NOW(),
                                   reject_reason='玩家提交了新的待审立绘'
                               WHERE uid=%s AND status='PENDING'""",
                            (uid,),
                        )

                    await cursor.execute(
                        """INSERT INTO power_portrait_submission
                           (uid,status,storage_key,original_filename,content_type,
                            width,height,file_size,sha256,platform_request_id)
                           VALUES (%s,'PENDING',%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            uid,
                            metadata["storage_key"],
                            Path(images[0].get("filename") or "QQ图片").name[:255],
                            "image/jpeg",
                            metadata["width"],
                            metadata["height"],
                            metadata["file_size"],
                            metadata["sha256"],
                            str(request_id)[:128] if request_id else None,
                        ),
                    )
                    submission_id = int(cursor.lastrowid)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
    except Exception:
        remove_portrait_file(storage_key)
        raise

    for old_key in superseded_keys:
        remove_portrait_file(old_key)
    return {
        "id": submission_id,
        "uid": int(uid),
        "player_name": player[0],
        "status": "PENDING",
        **metadata,
    }


async def portrait_status(uid: int) -> dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_power_portrait_schema(cursor)
            await cursor.execute(
                _SUBMISSION_SELECT
                + " WHERE ps.uid=%s ORDER BY ps.id DESC LIMIT 1",
                (uid,),
            )
            latest = _submission_row(await cursor.fetchone())
            await cursor.execute(
                """SELECT storage_key FROM power_portrait_submission
                   WHERE uid=%s AND status='APPROVED'
                   ORDER BY id DESC LIMIT 1""",
                (uid,),
            )
            approved = await cursor.fetchone()
    approved_key = approved[0] if approved else None
    return {
        "latest": latest,
        "using_custom": bool(approved_key and portrait_file_path(approved_key)),
    }


async def active_portrait_path(uid: int) -> Path | None:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_power_portrait_schema(cursor)
            await cursor.execute(
                """SELECT storage_key FROM power_portrait_submission
                   WHERE uid=%s AND status='APPROVED'
                   ORDER BY id DESC LIMIT 1""",
                (uid,),
            )
            row = await cursor.fetchone()
    return portrait_file_path(row[0]) if row else None


async def pending_submissions(limit: int = 8) -> list[dict]:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_power_portrait_schema(cursor)
            await cursor.execute(
                _SUBMISSION_SELECT
                + " WHERE ps.status='PENDING' ORDER BY ps.id ASC LIMIT %s",
                (max(1, min(int(limit), 20)),),
            )
            return [_submission_row(row) for row in await cursor.fetchall()]


async def get_submission(submission_id: int) -> dict | None:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_power_portrait_schema(cursor)
            await cursor.execute(
                _SUBMISSION_SELECT + " WHERE ps.id=%s LIMIT 1", (submission_id,)
            )
            return _submission_row(await cursor.fetchone())


async def approve_submission(operator_uid: int, submission_id: int) -> dict:
    require_admin(operator_uid)
    old_approved_keys = []
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_power_portrait_schema(cursor)
                await cursor.execute(
                    """SELECT uid,status,storage_key FROM power_portrait_submission
                       WHERE id=%s FOR UPDATE""",
                    (submission_id,),
                )
                row = await cursor.fetchone()
                if not row:
                    raise PowerPortraitError("未找到该立绘审核单。")
                target_uid, status, storage_key = int(row[0]), row[1], row[2]
                if status == "APPROVED":
                    result = await get_submission(submission_id)
                    return result
                if status != "PENDING":
                    raise PowerPortraitError("该审核单已处理，不能再次通过。")
                if not portrait_file_path(storage_key):
                    raise PowerPortraitError("待审图片文件缺失，请让玩家重新提交。")

                await cursor.execute(
                    """SELECT storage_key FROM power_portrait_submission
                       WHERE uid=%s AND status='APPROVED' FOR UPDATE""",
                    (target_uid,),
                )
                old_approved_keys = [item[0] for item in await cursor.fetchall()]
                await cursor.execute(
                    """UPDATE power_portrait_submission
                       SET status='SUPERSEDED',reviewed_at=NOW(),
                           reject_reason='已由新审核立绘替换'
                       WHERE uid=%s AND status='APPROVED'""",
                    (target_uid,),
                )
                await cursor.execute(
                    """UPDATE power_portrait_submission
                       SET status='APPROVED',reviewed_by=%s,reviewed_at=NOW(),
                           reject_reason=NULL
                       WHERE id=%s""",
                    (operator_uid, submission_id),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    for old_key in old_approved_keys:
        remove_portrait_file(old_key)
    return await get_submission(submission_id)


async def reject_submission(
    operator_uid: int, submission_id: int, reason: str
) -> dict:
    require_admin(operator_uid)
    reason = str(reason or "").strip()
    if not reason:
        raise PowerPortraitError("请填写驳回原因，方便玩家修改后重新提交。")
    if len(reason) > 120:
        raise PowerPortraitError("驳回原因不能超过 120 个字。")
    storage_key = None
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_power_portrait_schema(cursor)
                await cursor.execute(
                    """SELECT status,storage_key FROM power_portrait_submission
                       WHERE id=%s FOR UPDATE""",
                    (submission_id,),
                )
                row = await cursor.fetchone()
                if not row:
                    raise PowerPortraitError("未找到该立绘审核单。")
                if row[0] != "PENDING":
                    raise PowerPortraitError("该审核单已处理，不能再次驳回。")
                storage_key = row[1]
                await cursor.execute(
                    """UPDATE power_portrait_submission
                       SET status='REJECTED',reviewed_by=%s,reviewed_at=NOW(),
                           reject_reason=%s WHERE id=%s""",
                    (operator_uid, reason, submission_id),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    result = await get_submission(submission_id)
    if storage_key:
        remove_portrait_file(storage_key)
    return result
