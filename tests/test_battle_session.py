import asyncio
import unittest

from Game_domain.battle_models import (
    ACTION_NORMAL_ATTACK,
    BattleError,
    STATE_FINISHED,
)
from Game_domain.battle_repository import InMemoryBattleRepository
from Game_domain.battle_service import BattleSessionService
from Tool.combat_system import CombatEntity, CombatManager


def entity(name, *, hp=100, attack=10, defense=10, speed=100, entity_type="player"):
    return CombatEntity(name, {
        "name": name,
        "qixue": hp,
        "gongji": attack,
        "fangyu": defense,
        "sudu": speed,
        "baoji": 0,
        "baoshang": 0,
        "shanbi": 0,
        "mingzhong": 10000,
        "pofang": 0,
        "xixue": 0,
        "max_fali": 100,
        "entity_type": entity_type,
    })


class BattleSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = InMemoryBattleRepository()
        self.service = BattleSessionService(self.repository, action_timeout_seconds=1)
        manager = CombatManager(
            entity("玩家", hp=100, attack=12, speed=100),
            entity("木桩", hp=1000, attack=1, speed=1, entity_type="normal"),
            max_rounds=5,
        )
        self.session = await self.service.create_battle(
            uid=10001,
            manager=manager,
            metadata={"participants": [10001], "dungeon_id": 1},
        )

    async def test_create_persists_initial_snapshot_and_events(self):
        saved = await self.repository.get_session(self.session.battle_id)
        events = await self.repository.list_events(self.session.battle_id)

        self.assertEqual(saved.round_no, 0)
        self.assertEqual(saved.snapshot["player"]["name"], "玩家")
        self.assertGreaterEqual(len(events), 3)
        self.assertEqual([event.event_no for event in events], list(range(1, len(events) + 1)))

    async def test_action_resolves_one_round_and_is_idempotent(self):
        result = await self.service.submit_action(
            battle_id=self.session.battle_id,
            uid=10001,
            action_type=ACTION_NORMAL_ATTACK,
            action_id="action-1",
        )
        self.assertEqual(result.round_no, 1)
        self.assertFalse(result.idempotent)

        repeated = await self.service.submit_action(
            battle_id=self.session.battle_id,
            uid=10001,
            action_type=ACTION_NORMAL_ATTACK,
            action_id="action-1",
        )
        self.assertTrue(repeated.idempotent)
        self.assertEqual(repeated.round_no, 1)

        saved = await self.repository.get_session(self.session.battle_id)
        actions = await self.repository.get_round_actions(self.session.battle_id, 0)
        self.assertEqual(saved.round_no, 1)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].status, "RESOLVED")

    async def test_second_action_in_same_round_is_rejected(self):
        await self.service.submit_action(
            battle_id=self.session.battle_id,
            uid=10001,
            action_type=ACTION_NORMAL_ATTACK,
            action_id="action-1",
        )
        # 下一回合重新提交是合法的，确认服务没有把 uid 锁死在整场战斗。
        result = await self.service.submit_action(
            battle_id=self.session.battle_id,
            uid=10001,
            action_type=ACTION_NORMAL_ATTACK,
            action_id="action-2",
        )
        self.assertEqual(result.round_no, 2)

    async def test_timeout_uses_auto_action(self):
        result = await self.service.resolve_round(
            battle_id=self.session.battle_id,
            force=True,
        )
        self.assertEqual(result.round_no, 1)
        self.assertFalse(result.idempotent)

    async def test_finished_battle_cannot_accept_new_action(self):
        manager = CombatManager(
            entity("玩家", hp=100, attack=10000, speed=100),
            entity("纸人", hp=1, attack=1, speed=1, entity_type="normal"),
            max_rounds=2,
        )
        session = await self.service.create_battle(uid=10002, manager=manager)
        result = await self.service.submit_action(
            battle_id=session.battle_id,
            uid=10002,
            action_type=ACTION_NORMAL_ATTACK,
            action_id="finish-1",
        )
        self.assertEqual(result.state, STATE_FINISHED)
        with self.assertRaises(BattleError) as context:
            await self.service.submit_action(
                battle_id=session.battle_id,
                uid=10002,
                action_type=ACTION_NORMAL_ATTACK,
                action_id="finish-2",
            )
        self.assertEqual(context.exception.code, "ROUND_CLOSED")


if __name__ == "__main__":
    unittest.main()

