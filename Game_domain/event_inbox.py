"""QQ 事件去重仓储。事件 ID 是平台重试时避免重复执行的第一道保护。"""

import hashlib
import json
from datetime import datetime
from typing import Optional

from sql.mysql import connect_mysql


def payload_hash(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class InMemoryEventInbox:
    def __init__(self):
        self.events = {}

    async def claim(self, event_id: str, source: str, event_type: str, body) -> bool:
        existing = self.events.get(event_id)
        if existing:
            if existing["status"] in ("RECEIVED", "PROCESSED"):
                return False
            existing.update({
                "source": source,
                "event_type": event_type,
                "payload_hash": payload_hash(body),
                "status": "RECEIVED",
            })
            return True
        self.events[event_id] = {
            "source": source,
            "event_type": event_type,
            "payload_hash": payload_hash(body),
            "status": "RECEIVED",
        }
        return True

    async def mark_processed(self, event_id: str, error_message: Optional[str] = None):
        item = self.events.get(event_id)
        if item:
            item["status"] = "FAILED" if error_message else "PROCESSED"
            item["error_message"] = error_message


class MySQLEventInbox:
    async def claim(self, event_id: str, source: str, event_type: str, body) -> bool:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT status FROM event_inbox WHERE event_id = %s FOR UPDATE",
                    (event_id,),
                )
                existing = await cursor.fetchone()
                if existing:
                    if existing[0] in ("RECEIVED", "PROCESSED"):
                        await conn.rollback()
                        return False
                    await cursor.execute(
                        """
                        UPDATE event_inbox SET source = %s, event_type = %s,
                            payload_hash = %s, status = 'RECEIVED',
                            received_at = %s, processed_at = NULL, error_message = NULL
                        WHERE event_id = %s
                        """,
                        (source, event_type, payload_hash(body), datetime.utcnow(), event_id),
                    )
                    await conn.commit()
                    return True
                try:
                    await cursor.execute(
                        """
                        INSERT INTO event_inbox
                        (event_id, source, event_type, payload_hash, status)
                        VALUES (%s, %s, %s, %s, 'RECEIVED')
                        """,
                        (event_id, source, event_type, payload_hash(body)),
                    )
                except Exception as exc:
                    await conn.rollback()
                    # 只有唯一键冲突表示重复事件；连接、权限或未迁移表必须继续抛出。
                    error_code = exc.args[0] if getattr(exc, "args", None) else None
                    if error_code == 1062:
                        return False
                    raise
                await conn.commit()
                return True

    async def mark_processed(self, event_id: str, error_message: Optional[str] = None):
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE event_inbox
                    SET status = %s, processed_at = %s, error_message = %s
                    WHERE event_id = %s
                    """,
                    (
                        "FAILED" if error_message else "PROCESSED",
                        datetime.utcnow(),
                        error_message,
                        event_id,
                    ),
                )
                await conn.commit()
