import unittest

from Game_domain.reward_service import (
    InMemoryRewardService,
    RewardError,
    RewardItem,
    calculate_exp_progress,
)


class RewardServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_battle_rewards_are_idempotent(self):
        service = InMemoryRewardService()
        first = await service.grant_battle_rewards(
            battle_id="battle-1",
            uid=10001,
            lingshi=500,
            items=[RewardItem(7, 2)],
        )
        second = await service.grant_battle_rewards(
            battle_id="battle-1",
            uid=10001,
            lingshi=500,
            items=[RewardItem(7, 2)],
        )
        self.assertEqual(service.lingshi[10001], 500)
        self.assertEqual(service.items[(10001, 7)], 2)
        self.assertEqual(len(first.applied), 2)
        self.assertEqual(len(second.applied), 0)
        self.assertEqual(len(second.duplicates), 2)

    async def test_items_are_merged_before_granting(self):
        service = InMemoryRewardService()
        await service.grant_battle_rewards(
            battle_id="battle-2",
            uid=10001,
            items=[RewardItem(7, 2), RewardItem(7, 3)],
        )
        self.assertEqual(service.items[(10001, 7)], 5)

    async def test_negative_reward_is_rejected(self):
        service = InMemoryRewardService()
        with self.assertRaises(RewardError):
            await service.grant_battle_rewards(battle_id="battle-3", uid=10001, lingshi=-1)

    def test_exp_progress_stops_at_breakthrough_level(self):
        progress = calculate_exp_progress(9, 0, 100000)
        self.assertEqual(progress["level"], 10)
        self.assertTrue(progress["need_breakthrough"])

