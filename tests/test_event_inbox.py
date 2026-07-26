import unittest

from Game_domain.event_inbox import InMemoryEventInbox, payload_hash


class EventInboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_event_is_ignored(self):
        inbox = InMemoryEventInbox()
        body = {"id": "message-1", "content": "战斗状态"}
        self.assertTrue(await inbox.claim("event-1", "webhook", "C2C_MESSAGE_CREATE", body))
        self.assertFalse(await inbox.claim("event-1", "webhook", "C2C_MESSAGE_CREATE", body))
        self.assertEqual(len(inbox.events), 1)

    def test_payload_hash_is_order_independent(self):
        self.assertEqual(
            payload_hash({"a": 1, "b": 2}),
            payload_hash({"b": 2, "a": 1}),
        )

