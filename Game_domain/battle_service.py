"""Battle Session 应用服务。"""

from datetime import timedelta
from typing import Any, Dict, Optional

from Tool.combat_system import CombatManager

from .battle_models import (
    ACTION_AUTO,
    BattleActionRecord,
    BattleError,
    BattleEvent,
    BattleResult,
    BattleSession,
    STATE_FINISHED,
    STATE_RECOVERY_REQUIRED,
    STATE_WAITING_ACTIONS,
    utcnow,
)


class BattleSessionService:
    def __init__(self, repository, action_timeout_seconds: int = 30):
        self.repository = repository
        self.action_timeout_seconds = action_timeout_seconds

    async def create_battle(
        self,
        *,
        uid: int,
        manager: CombatManager,
        battle_type: str = "SOLO_DUNGEON",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BattleSession:
        manager.initialize()
        metadata = dict(metadata or {})
        metadata.setdefault("participants", [uid])
        session = BattleSession.new(
            owner_uid=uid,
            battle_type=battle_type,
            snapshot=manager.to_snapshot(),
            metadata=metadata,
            action_timeout_seconds=self.action_timeout_seconds,
        )
        events = self._events_from_logs(session.battle_id, manager.combat_log, session.round_no)
        await self.repository.create_session(session, events)
        return session

    async def get_battle(self, battle_id: str, uid: int) -> BattleSession:
        session = await self.repository.get_session(battle_id)
        if session is None:
            raise BattleError("BATTLE_NOT_FOUND", "战斗不存在或已过期")
        if uid not in session.participants:
            raise BattleError("NOT_BATTLE_MEMBER", "你不在这场战斗中")
        return session

    async def get_active_battle(self, uid: int) -> Optional[BattleSession]:
        session = await self.repository.get_active_by_owner(uid)
        if session is not None and uid not in session.participants:
            return None
        return session

    async def submit_action(
        self,
        *,
        battle_id: str,
        uid: int,
        action_type: str,
        skill_id: Optional[int] = None,
        target_id: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> BattleResult:
        if action_id:
            previous = await self.repository.get_action(action_id)
            if previous:
                session = await self.get_battle(previous.battle_id, uid)
                return await self._result_for_existing_action(session, previous)
        session = await self.get_battle(battle_id, uid)
        if session.state == STATE_FINISHED:
            raise BattleError("ROUND_CLOSED", "战斗已经结束，请查看战斗结果")
        if session.state != STATE_WAITING_ACTIONS:
            raise BattleError("BATTLE_BUSY", "战斗正在结算，请稍后再试")

        manager = CombatManager.from_snapshot(session.snapshot)
        action = {
            "action_type": action_type.upper(),
            "skill_id": skill_id,
            "target_id": target_id,
        }
        valid, reason = manager.validate_player_action(action)
        if not valid:
            code = "SKILL_INVALID" if action["action_type"] == "SKILL" else "ACTION_INVALID"
            raise BattleError(code, reason)

        record = BattleActionRecord.new(
            battle_id=battle_id,
            round_no=session.round_no,
            uid=uid,
            action_type=action["action_type"],
            skill_id=skill_id,
            target_id=target_id,
            action_id=action_id,
        )
        accepted, existing, reason = await self.repository.claim_action(record)
        if not accepted:
            if existing and existing.action_id == record.action_id:
                return await self._result_for_existing_action(session, existing)
            if reason == "ACTION_ALREADY_SUBMITTED":
                raise BattleError("ACTION_ALREADY_SUBMITTED", "本回合行动已经提交")
            if reason == "ROUND_CLOSED":
                raise BattleError("ROUND_CLOSED", "本回合已经结算，请查看战斗状态")
            raise BattleError(reason, "战斗行动未能提交")

        return await self.resolve_round(battle_id=battle_id, force=False)

    async def resolve_round(
        self,
        *,
        battle_id: str,
        force: bool = False,
        now=None,
    ) -> BattleResult:
        session = await self.repository.get_session(battle_id)
        if session is None:
            raise BattleError("BATTLE_NOT_FOUND", "战斗不存在或已过期")
        if session.state == STATE_FINISHED:
            return BattleResult(
                battle_id=battle_id,
                state=session.state,
                round_no=session.round_no,
                waiting_for=[],
                summary=session.result or {},
                idempotent=True,
            )
        if session.state != STATE_WAITING_ACTIONS:
            raise BattleError("BATTLE_BUSY", "战斗正在结算")

        now = now or utcnow()
        actions = await self.repository.get_round_actions(battle_id, session.round_no)
        submitted_uids = {action.uid for action in actions}
        waiting_for = [uid for uid in session.participants if uid not in submitted_uids]
        expired = session.action_deadline is not None and now >= session.action_deadline
        if waiting_for and not force and not expired:
            return BattleResult(
                battle_id=battle_id,
                state=session.state,
                round_no=session.round_no,
                waiting_for=waiting_for,
                summary={"action_deadline": session.action_deadline.isoformat()},
            )

        manager = CombatManager.from_snapshot(session.snapshot)
        player_action = None
        owner_action = next((item for item in actions if item.uid == session.owner_uid), None)
        if owner_action:
            player_action = owner_action.to_action_dict()
        else:
            player_action = {"action_type": ACTION_AUTO}

        old_log_count = len(session.snapshot.get("combat_log", []))
        winner, round_logs = manager.resolve_round(player_action)
        is_finished = bool(winner) or manager.round >= manager.max_rounds
        session.state = STATE_FINISHED if is_finished else STATE_WAITING_ACTIONS
        session.round_no = manager.round
        session.snapshot = manager.to_snapshot()
        session.result = manager.get_combat_summary() if is_finished else None
        session.version += 1
        session.updated_at = now
        session.action_deadline = None if is_finished else now + timedelta(seconds=self.action_timeout_seconds)

        events = self._events_from_logs(
            battle_id,
            manager.combat_log[old_log_count:],
            manager.round,
            start_event_no=old_log_count + 1,
        )
        action_ids = [action.action_id for action in actions]
        await self.repository.persist_resolution(session, events, action_ids)
        return BattleResult(
            battle_id=battle_id,
            state=session.state,
            round_no=session.round_no,
            waiting_for=[] if is_finished else session.participants,
            events=events,
            summary=session.result or {"round_logs": round_logs},
        )

    async def run_to_completion(self, battle_id: str, uid: int) -> BattleResult:
        """兼容旧的自动战斗调用，仍然逐回合写入 Session。"""
        result = None
        while True:
            session = await self.get_battle(battle_id, uid)
            if session.state == STATE_FINISHED:
                return result or BattleResult(
                    battle_id=battle_id,
                    state=session.state,
                    round_no=session.round_no,
                    waiting_for=[],
                    summary=session.result or {},
                )
            result = await self.submit_action(
                battle_id=battle_id,
                uid=uid,
                action_type=ACTION_AUTO,
            )

    async def recover_stale_battles(self, now=None) -> int:
        recovered = 0
        for session in await self.repository.list_stale_waiting(now or utcnow()):
            try:
                await self.resolve_round(battle_id=session.battle_id, force=True, now=now)
                recovered += 1
            except Exception:
                await self.repository.mark_recovery_required(session.battle_id)
        return recovered

    async def _result_for_existing_action(self, session, action):
        if action.status == "RESOLVED":
            return BattleResult(
                battle_id=session.battle_id,
                state=session.state,
                round_no=session.round_no,
                waiting_for=[] if session.state == STATE_FINISHED else session.participants,
                summary=action.result or session.result or {},
                idempotent=True,
            )
        if session.state == STATE_FINISHED:
            return BattleResult(
                battle_id=session.battle_id,
                state=session.state,
                round_no=session.round_no,
                waiting_for=[],
                summary=session.result or {},
                idempotent=True,
            )
        return await self.resolve_round(battle_id=session.battle_id, force=True)

    @staticmethod
    def _events_from_logs(battle_id: str, logs, round_no: int, start_event_no: int = 1):
        return [
            BattleEvent(
                battle_id=battle_id,
                event_no=index,
                round_no=log.get("round", round_no),
                event_type=log.get("type", "LOG"),
                payload={"message": log.get("message", "")},
            )
            for index, log in enumerate(logs, start=start_event_no)
        ]
