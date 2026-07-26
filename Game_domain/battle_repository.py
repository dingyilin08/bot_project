"""Battle Session 仓储。

生产环境使用 MySQL 仓储；测试和本地规则测试使用内存仓储。业务服务只依赖
这里定义的行为，不直接拼接 SQL。
"""

import json
import copy
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sql.mysql import connect_mysql

from .battle_models import (
    BattleActionRecord,
    BattleEvent,
    BattleSession,
    STATE_WAITING_ACTIONS,
    utcnow,
)


class BattleRepositoryError(Exception):
    pass


class InMemoryBattleRepository:
    def __init__(self):
        self.sessions: Dict[str, BattleSession] = {}
        self.actions: Dict[str, BattleActionRecord] = {}
        self.events: Dict[str, List[BattleEvent]] = {}

    async def create_session(self, session: BattleSession, events: List[BattleEvent]):
        if session.battle_id in self.sessions:
            raise BattleRepositoryError("battle already exists")
        self.sessions[session.battle_id] = session
        self.events[session.battle_id] = list(events)

    async def get_session(self, battle_id: str) -> Optional[BattleSession]:
        session = self.sessions.get(battle_id)
        return copy.deepcopy(session) if session else None

    async def get_active_by_owner(self, uid: int) -> Optional[BattleSession]:
        active = [
            session for session in self.sessions.values()
            if session.owner_uid == uid and session.state in ("CREATED", "WAITING_ACTIONS", "RESOLVING")
        ]
        session = sorted(active, key=lambda item: item.created_at)[-1] if active else None
        return copy.deepcopy(session) if session else None

    async def get_action(self, action_id: str) -> Optional[BattleActionRecord]:
        return self.actions.get(action_id)

    async def get_round_actions(self, battle_id: str, round_no: int) -> List[BattleActionRecord]:
        return [
            action for action in self.actions.values()
            if action.battle_id == battle_id and action.round_no == round_no
        ]

    async def claim_action(self, action: BattleActionRecord) -> Tuple[bool, Optional[BattleActionRecord], str]:
        existing = self.actions.get(action.action_id)
        if existing:
            return False, existing, "ACTION_ALREADY_PROCESSED"

        session = self.sessions.get(action.battle_id)
        if session is None:
            return False, None, "BATTLE_NOT_FOUND"
        if session.state != STATE_WAITING_ACTIONS:
            return False, None, "ROUND_CLOSED"
        if session.round_no != action.round_no:
            return False, None, "ROUND_CLOSED"

        for existing_action in await self.get_round_actions(action.battle_id, action.round_no):
            if existing_action.uid == action.uid:
                return False, existing_action, "ACTION_ALREADY_SUBMITTED"

        self.actions[action.action_id] = action
        return True, action, "ACCEPTED"

    async def persist_resolution(
        self,
        session: BattleSession,
        events: List[BattleEvent],
        action_ids: List[str],
    ):
        current = self.sessions.get(session.battle_id)
        if current is None:
            raise BattleRepositoryError("battle not found")
        if current.version != session.version - 1:
            raise BattleRepositoryError("battle version conflict")
        self.sessions[session.battle_id] = session
        self.events.setdefault(session.battle_id, []).extend(events)
        for action_id in action_ids:
            action = self.actions.get(action_id)
            if action:
                action.status = "RESOLVED"
                action.result = session.result or {}
                action.resolved_at = utcnow()

    async def list_stale_waiting(self, now: Optional[datetime] = None) -> List[BattleSession]:
        now = now or utcnow()
        return [
            session for session in self.sessions.values()
            if session.state == STATE_WAITING_ACTIONS
            and session.action_deadline is not None
            and session.action_deadline <= now
        ]

    async def mark_recovery_required(self, battle_id: str):
        session = self.sessions.get(battle_id)
        if session:
            session.state = "RECOVERY_REQUIRED"

    async def list_events(self, battle_id: str) -> List[BattleEvent]:
        return list(self.events.get(battle_id, []))


class MySQLBattleRepository:
    """MySQL 实现，使用行锁和版本号保护状态推进。"""

    async def create_session(self, session: BattleSession, events: List[BattleEvent]):
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    INSERT INTO battle_session
                    (battle_uuid, owner_uid, battle_type, state, round_no,
                     action_deadline, rng_seed, engine_version, snapshot_json,
                     metadata_json, result_json, version)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session.battle_id,
                        session.owner_uid,
                        session.battle_type,
                        session.state,
                        session.round_no,
                        session.action_deadline,
                        session.rng_seed,
                        session.engine_version,
                        json.dumps(session.snapshot, ensure_ascii=False),
                        json.dumps(session.metadata, ensure_ascii=False),
                        json.dumps(session.result, ensure_ascii=False) if session.result else None,
                        session.version,
                    ),
                )
                await self._insert_events(cursor, events)
                await conn.commit()

    async def get_session(self, battle_id: str) -> Optional[BattleSession]:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT battle_uuid, owner_uid, battle_type, state, round_no,
                           action_deadline, rng_seed, engine_version, snapshot_json,
                           metadata_json, result_json, version, created_at, updated_at
                    FROM battle_session WHERE battle_uuid = %s LIMIT 1
                    """,
                    (battle_id,),
                )
                row = await cursor.fetchone()
                return self._session_from_row(row) if row else None

    async def get_active_by_owner(self, uid: int) -> Optional[BattleSession]:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT battle_uuid, owner_uid, battle_type, state, round_no,
                           action_deadline, rng_seed, engine_version, snapshot_json,
                           metadata_json, result_json, version, created_at, updated_at
                    FROM battle_session
                    WHERE owner_uid = %s AND state IN ('CREATED', 'WAITING_ACTIONS', 'RESOLVING')
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (uid,),
                )
                row = await cursor.fetchone()
                return self._session_from_row(row) if row else None

    async def get_action(self, action_id: str) -> Optional[BattleActionRecord]:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT action_id, battle_uuid, round_no, uid, action_type,
                           skill_id, target_id, status, result_json, created_at, resolved_at
                    FROM battle_action WHERE action_id = %s LIMIT 1
                    """,
                    (action_id,),
                )
                row = await cursor.fetchone()
                return self._action_from_row(row) if row else None

    async def get_round_actions(self, battle_id: str, round_no: int) -> List[BattleActionRecord]:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT action_id, battle_uuid, round_no, uid, action_type,
                           skill_id, target_id, status, result_json, created_at, resolved_at
                    FROM battle_action WHERE battle_uuid = %s AND round_no = %s
                    ORDER BY id ASC
                    """,
                    (battle_id, round_no),
                )
                return [self._action_from_row(row) for row in await cursor.fetchall()]

    async def claim_action(self, action: BattleActionRecord) -> Tuple[bool, Optional[BattleActionRecord], str]:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT battle_uuid, state, round_no
                    FROM battle_session WHERE battle_uuid = %s FOR UPDATE
                    """,
                    (action.battle_id,),
                )
                session_row = await cursor.fetchone()
                if not session_row:
                    return False, None, "BATTLE_NOT_FOUND"
                _, state, round_no = session_row
                if state != STATE_WAITING_ACTIONS or round_no != action.round_no:
                    return False, None, "ROUND_CLOSED"

                await cursor.execute(
                    """
                    SELECT action_id, battle_uuid, round_no, uid, action_type,
                           skill_id, target_id, status, result_json, created_at, resolved_at
                    FROM battle_action
                    WHERE battle_uuid = %s AND round_no = %s AND uid = %s
                    LIMIT 1
                    """,
                    (action.battle_id, action.round_no, action.uid),
                )
                round_row = await cursor.fetchone()
                if round_row:
                    await conn.rollback()
                    return False, self._action_from_row(round_row), "ACTION_ALREADY_SUBMITTED"

                try:
                    await cursor.execute(
                        """
                        INSERT INTO battle_action
                        (action_id, battle_uuid, round_no, uid, action_type,
                         skill_id, target_id, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            action.action_id,
                            action.battle_id,
                            action.round_no,
                            action.uid,
                            action.action_type,
                            action.skill_id,
                            action.target_id,
                            action.status,
                        ),
                    )
                except Exception as exc:
                    await conn.rollback()
                    error_code = exc.args[0] if getattr(exc, "args", None) else None
                    if error_code == 1062:
                        existing = await self.get_action(action.action_id)
                        return False, existing, "ACTION_ALREADY_PROCESSED"
                    raise
                await conn.commit()
                return True, action, "ACCEPTED"

    async def persist_resolution(
        self,
        session: BattleSession,
        events: List[BattleEvent],
        action_ids: List[str],
    ):
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    UPDATE battle_session SET state = %s, round_no = %s,
                        action_deadline = %s, snapshot_json = %s,
                        result_json = %s, version = %s
                    WHERE battle_uuid = %s AND version = %s
                    """,
                    (
                        session.state,
                        session.round_no,
                        session.action_deadline,
                        json.dumps(session.snapshot, ensure_ascii=False),
                        json.dumps(session.result, ensure_ascii=False) if session.result else None,
                        session.version,
                        session.battle_id,
                        session.version - 1,
                    ),
                )
                if cursor.rowcount != 1:
                    await conn.rollback()
                    raise BattleRepositoryError("battle version conflict")
                await self._insert_events(cursor, events)
                for action_id in action_ids:
                    await cursor.execute(
                        """
                        UPDATE battle_action SET status = 'RESOLVED',
                            result_json = %s, resolved_at = %s
                        WHERE action_id = %s
                        """,
                        (
                            json.dumps(session.result or {}, ensure_ascii=False),
                            utcnow(),
                            action_id,
                        ),
                    )
                await conn.commit()

    async def list_stale_waiting(self, now: Optional[datetime] = None) -> List[BattleSession]:
        now = now or utcnow()
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT battle_uuid, owner_uid, battle_type, state, round_no,
                           action_deadline, rng_seed, engine_version, snapshot_json,
                           metadata_json, result_json, version, created_at, updated_at
                    FROM battle_session
                    WHERE state = %s AND action_deadline IS NOT NULL
                      AND action_deadline <= %s
                    ORDER BY action_deadline ASC
                    """,
                    (STATE_WAITING_ACTIONS, now),
                )
                return [self._session_from_row(row) for row in await cursor.fetchall()]

    async def mark_recovery_required(self, battle_id: str):
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "UPDATE battle_session SET state = 'RECOVERY_REQUIRED', version = version + 1 WHERE battle_uuid = %s AND state = 'WAITING_ACTIONS'",
                    (battle_id,),
                )
                await conn.commit()

    async def list_events(self, battle_id: str) -> List[BattleEvent]:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT battle_uuid, event_no, round_no, event_type,
                           actor_id, target_id, payload_json, rng_index, created_at
                    FROM battle_event WHERE battle_uuid = %s ORDER BY event_no ASC
                    """,
                    (battle_id,),
                )
                events = []
                for row in await cursor.fetchall():
                    events.append(BattleEvent(
                        battle_id=row[0], event_no=row[1], round_no=row[2],
                        event_type=row[3], actor_id=row[4], target_id=row[5],
                        payload=json.loads(row[6]) if isinstance(row[6], str) else row[6],
                        rng_index=row[7], created_at=row[8],
                    ))
                return events

    async def _insert_events(self, cursor, events: List[BattleEvent]):
        for event in events:
            await cursor.execute(
                """
                INSERT INTO battle_event
                (battle_uuid, event_no, round_no, event_type, actor_id,
                 target_id, payload_json, rng_index)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event.battle_id,
                    event.event_no,
                    event.round_no,
                    event.event_type,
                    event.actor_id,
                    event.target_id,
                    json.dumps(event.payload, ensure_ascii=False),
                    event.rng_index,
                ),
            )

    @staticmethod
    def _session_from_row(row) -> BattleSession:
        def load(value, default):
            if value is None:
                return default
            if isinstance(value, (dict, list)):
                return value
            return json.loads(value)

        return BattleSession(
            battle_id=row[0], owner_uid=row[1], battle_type=row[2], state=row[3],
            round_no=row[4], action_deadline=row[5], rng_seed=row[6],
            engine_version=row[7], snapshot=load(row[8], {}),
            metadata=load(row[9], {}), result=load(row[10], None), version=row[11],
            created_at=row[12], updated_at=row[13],
        )

    @staticmethod
    def _action_from_row(row) -> BattleActionRecord:
        result = row[8]
        if isinstance(result, str):
            result = json.loads(result)
        return BattleActionRecord(
            action_id=row[0], battle_id=row[1], round_no=row[2], uid=row[3],
            action_type=row[4], skill_id=row[5], target_id=row[6], status=row[7],
            result=result, created_at=row[9], resolved_at=row[10],
        )
