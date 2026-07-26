"""Battle Session 的领域模型和稳定错误码。"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4


STATE_CREATED = "CREATED"
STATE_WAITING_ACTIONS = "WAITING_ACTIONS"
STATE_RESOLVING = "RESOLVING"
STATE_FINISHED = "FINISHED"
STATE_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"

ACTION_NORMAL_ATTACK = "NORMAL_ATTACK"
ACTION_SKILL = "SKILL"
ACTION_DEFEND = "DEFEND"
ACTION_MEDITATE = "MEDITATE"
ACTION_ARTIFACT = "ARTIFACT"
ACTION_DAO_HEART_BURST = "DAO_HEART_BURST"
ACTION_DAO_HEART_EXTEND = "DAO_HEART_EXTEND"
ACTION_DAO_HEART_STORE = "DAO_HEART_STORE"
ACTION_AUTO = "AUTO"


class BattleError(Exception):
    """可直接映射为玩家提示的业务错误。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def utcnow() -> datetime:
    """返回无时区 UTC 时间，兼容 MySQL DATETIME。"""
    return datetime.utcnow()


@dataclass
class BattleActionRecord:
    action_id: str
    battle_id: str
    round_no: int
    uid: int
    action_type: str
    skill_id: Optional[int] = None
    target_id: Optional[str] = None
    status: str = "SUBMITTED"
    result: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=utcnow)
    resolved_at: Optional[datetime] = None

    @classmethod
    def new(
        cls,
        *,
        battle_id: str,
        round_no: int,
        uid: int,
        action_type: str,
        skill_id: Optional[int] = None,
        target_id: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> "BattleActionRecord":
        return cls(
            action_id=action_id or str(uuid4()),
            battle_id=battle_id,
            round_no=round_no,
            uid=uid,
            action_type=action_type.upper(),
            skill_id=skill_id,
            target_id=target_id,
        )

    def to_action_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "skill_id": self.skill_id,
            "target_id": self.target_id,
        }


@dataclass
class BattleEvent:
    battle_id: str
    event_no: int
    round_no: int
    event_type: str
    payload: Dict[str, Any]
    actor_id: Optional[str] = None
    target_id: Optional[str] = None
    rng_index: Optional[int] = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class BattleSession:
    battle_id: str
    owner_uid: int
    battle_type: str
    state: str
    round_no: int
    action_deadline: Optional[datetime]
    rng_seed: str
    engine_version: str
    snapshot: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    version: int = 0
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @classmethod
    def new(
        cls,
        *,
        owner_uid: int,
        battle_type: str,
        snapshot: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        engine_version: str = "combat-v2",
        action_timeout_seconds: int = 30,
        rng_seed: Optional[str] = None,
    ) -> "BattleSession":
        now = utcnow()
        return cls(
            battle_id=str(uuid4()),
            owner_uid=owner_uid,
            battle_type=battle_type,
            state=STATE_WAITING_ACTIONS,
            round_no=snapshot.get("round", 0),
            action_deadline=now + timedelta(seconds=action_timeout_seconds),
            rng_seed=rng_seed or str(uuid4()),
            engine_version=engine_version,
            snapshot=snapshot,
            metadata=metadata or {"participants": [owner_uid]},
            created_at=now,
            updated_at=now,
        )

    @property
    def participants(self) -> List[int]:
        values = self.metadata.get("participants", [self.owner_uid])
        return [int(value) for value in values]

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if self.action_deadline is None:
            return False
        return (now or utcnow()) >= self.action_deadline


@dataclass
class BattleResult:
    battle_id: str
    state: str
    round_no: int
    waiting_for: List[int]
    events: List[BattleEvent] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    idempotent: bool = False
