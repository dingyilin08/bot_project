# -*- coding: utf-8 -*-
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

import main
from Game_domain.event_inbox import InMemoryEventInbox


class _FakeRequest:
    headers = {
        "User-Agent": "QQBot-Callback",
        "X-Bot-Appid": "test-appid",
    }

    def __init__(self, payload):
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    async def body(self):
        return self._body


class _FakeResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def text(self):
        return '{"id":"sent-message-id"}'

    async def json(self):
        return {"id": "sent-message-id"}


class _FakeSession:
    def __init__(self, captured):
        self.captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def post(self, url, json, headers):
        self.captured.update({"url": url, "json": json, "headers": headers})
        return _FakeResponse()


class GroupWelcomeWebhookTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _request(event_id="event-group-add-1"):
        return _FakeRequest({
            "id": event_id,
            "op": 0,
            "t": "GROUP_ADD_ROBOT",
            "s": 1,
            "d": {
                "group_openid": "group-openid-1",
                "op_member_openid": "member-openid-1",
                "timestamp": 1784570534,
            },
        })

    async def test_group_add_event_replies_with_top_level_event_id(self):
        inbox = InMemoryEventInbox()
        sender = AsyncMock(return_value={"id": "sent-message-id"})

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "send_group_markdown_keyboard", sender
        ):
            response = await main.handle_webhook(self._request())

        self.assertEqual({"op": 12}, response)
        sender.assert_awaited_once()
        args, kwargs = sender.await_args
        self.assertEqual("group-openid-1", args[0])
        self.assertIn("问道诸天", args[1])
        self.assertEqual("event-group-add-1", kwargs["event_id"])
        self.assertNotIn("msg_id", kwargs)
        self.assertEqual(
            "注册游戏",
            args[2]["content"]["rows"][0]["buttons"][0]["action"]["data"],
        )
        self.assertEqual("PROCESSED", inbox.events["event-group-add-1"]["status"])

    async def test_duplicate_group_add_event_does_not_send_twice(self):
        inbox = InMemoryEventInbox()
        sender = AsyncMock(return_value={"id": "sent-message-id"})

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "send_group_markdown_keyboard", sender
        ):
            first = await main.handle_webhook(self._request("event-duplicate"))
            second = await main.handle_webhook(self._request("event-duplicate"))

        self.assertEqual({"op": 12}, first)
        self.assertEqual({"op": 12}, second)
        sender.assert_awaited_once()

    async def test_failed_welcome_send_marks_event_retryable(self):
        inbox = InMemoryEventInbox()
        sender = AsyncMock(return_value=None)

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "send_group_markdown_keyboard", sender
        ):
            with self.assertRaises(HTTPException) as caught:
                await main.handle_webhook(self._request("event-group-add-failed"))

        self.assertEqual(500, caught.exception.status_code)
        event = inbox.events["event-group-add-failed"]
        self.assertEqual("FAILED", event["status"])
        self.assertIn("入群欢迎消息发送失败", event["error_message"])

        retry_sender = AsyncMock(return_value={"id": "sent-on-retry"})
        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "send_group_markdown_keyboard", retry_sender
        ):
            response = await main.handle_webhook(self._request("event-group-add-failed"))

        self.assertEqual({"op": 12}, response)
        retry_sender.assert_awaited_once()
        self.assertEqual("PROCESSED", inbox.events["event-group-add-failed"]["status"])

    async def test_group_sender_serializes_event_reply_without_msg_id(self):
        captured = {}
        keyboard = {"content": {"rows": []}}

        with patch.object(
            main, "get_headers", AsyncMock(return_value={"Authorization": "QQBot token"})
        ), patch.object(
            main.aiohttp, "ClientSession", lambda: _FakeSession(captured)
        ):
            result = await main.send_group_markdown_keyboard(
                "group-openid-1",
                "welcome",
                keyboard,
                event_id="event-group-add-1",
            )

        self.assertEqual({"id": "sent-message-id"}, result)
        self.assertEqual("event-group-add-1", captured["json"]["event_id"])
        self.assertNotIn("msg_id", captured["json"])
        self.assertEqual(2, captured["json"]["msg_type"])
        self.assertEqual(keyboard, captured["json"]["keyboard"])

    async def test_group_sender_requires_exactly_one_reply_id(self):
        with self.assertRaises(ValueError):
            await main.send_group_markdown_keyboard(
                "group-openid-1", "welcome", {}, msg_id=None, event_id=None
            )
        with self.assertRaises(ValueError):
            await main.send_group_markdown_keyboard(
                "group-openid-1",
                "welcome",
                {},
                msg_id="message-id",
                event_id="event-id",
            )

    async def test_button_prefix_becomes_registration_command_with_player_name(self):
        welcome = main.build_group_welcome_message()
        action = welcome["keyboard"]["content"]["rows"][0]["buttons"][0]["action"]
        command, player_name = await main.jiance(f'{action["data"]} 云澈')

        self.assertEqual("注册游戏", command)
        self.assertEqual("云澈", player_name)


if __name__ == "__main__":
    unittest.main()
