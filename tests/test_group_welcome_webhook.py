# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

import main
from Game_domain.event_inbox import InMemoryEventInbox
from Tool.qq_official_group import OFFICIAL_GROUP_NOTICE


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


async def _append_official_notice(content):
    return f"{content}\n\n{OFFICIAL_GROUP_NOTICE}"


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

    @staticmethod
    def _friend_request(event_id="event-friend-add-1"):
        return _FakeRequest({
            "id": event_id,
            "op": 0,
            "t": "FRIEND_ADD",
            "s": 2,
            "d": {
                "openid": "user-openid-1",
                "timestamp": 1784570523,
                "scene": 1001,
                "scene_param": "",
                "author": {"union_openid": "union-openid-1"},
            },
        })

    @staticmethod
    def _group_message_request(
        event_id="event-group-message-1",
        event_type="GROUP_AT_MESSAGE_CREATE",
        author=None,
        content="menu",
    ):
        return _FakeRequest({
            "id": event_id,
            "op": 0,
            "t": event_type,
            "s": 3,
            "d": {
                "id": "group-message-id-1",
                "content": content,
                "group_openid": "group-openid-1",
                "author": author or {"union_openid": "union-openid-1"},
            },
        })

    @staticmethod
    def _c2c_message_request(event_id="event-c2c-message-1"):
        return _FakeRequest({
            "id": event_id,
            "op": 0,
            "t": "C2C_MESSAGE_CREATE",
            "s": 4,
            "d": {
                "id": "c2c-message-id-1",
                "content": "menu",
                "author": {"union_openid": "union-openid-1"},
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

    async def test_friend_add_event_replies_to_openid_with_event_id(self):
        inbox = InMemoryEventInbox()
        sender = AsyncMock(return_value={"id": "sent-friend-welcome"})

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "send_c2c_markdown_keyboard", sender
        ):
            response = await main.handle_webhook(self._friend_request())

        self.assertEqual({"op": 12}, response)
        sender.assert_awaited_once()
        args, kwargs = sender.await_args
        self.assertEqual("user-openid-1", args[0])
        self.assertIn("欢迎添加《问道诸天》", args[1])
        self.assertTrue(args[1].endswith(OFFICIAL_GROUP_NOTICE))
        self.assertEqual("event-friend-add-1", kwargs["event_id"])
        self.assertNotIn("msg_id", kwargs)
        self.assertEqual(
            "注册游戏",
            args[2]["content"]["rows"][0]["buttons"][0]["action"]["data"],
        )
        self.assertEqual("PROCESSED", inbox.events["event-friend-add-1"]["status"])

    async def test_duplicate_friend_add_event_does_not_send_twice(self):
        inbox = InMemoryEventInbox()
        sender = AsyncMock(return_value={"id": "sent-friend-welcome"})

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "send_c2c_markdown_keyboard", sender
        ):
            first = await main.handle_webhook(
                self._friend_request("event-friend-duplicate")
            )
            second = await main.handle_webhook(
                self._friend_request("event-friend-duplicate")
            )

        self.assertEqual({"op": 12}, first)
        self.assertEqual({"op": 12}, second)
        sender.assert_awaited_once()

    async def test_failed_friend_welcome_can_retry(self):
        inbox = InMemoryEventInbox()
        failed_sender = AsyncMock(return_value=None)

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "send_c2c_markdown_keyboard", failed_sender
        ):
            with self.assertRaises(HTTPException):
                await main.handle_webhook(self._friend_request("event-friend-retry"))

        self.assertEqual("FAILED", inbox.events["event-friend-retry"]["status"])
        self.assertIn(
            "好友欢迎消息发送失败",
            inbox.events["event-friend-retry"]["error_message"],
        )

        retry_sender = AsyncMock(return_value={"id": "sent-on-retry"})
        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "send_c2c_markdown_keyboard", retry_sender
        ):
            response = await main.handle_webhook(
                self._friend_request("event-friend-retry")
            )

        self.assertEqual({"op": 12}, response)
        retry_sender.assert_awaited_once()
        self.assertEqual("PROCESSED", inbox.events["event-friend-retry"]["status"])

    async def test_failed_group_reply_is_not_marked_processed(self):
        inbox = InMemoryEventInbox()
        reply = {
            "type": "markdown_keyboard",
            "content": "reply",
            "keyboard": {"content": {"rows": []}},
        }
        sender = AsyncMock(return_value=None)

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "output_content", AsyncMock(return_value=reply)
        ), patch.object(main, "send_group_markdown_keyboard", sender):
            with self.assertRaises(HTTPException) as caught:
                await main.handle_webhook(
                    self._group_message_request("event-group-reply-failed")
                )

        self.assertEqual(500, caught.exception.status_code)
        self.assertEqual(2, sender.await_count)
        self.assertEqual("FAILED", inbox.events["event-group-reply-failed"]["status"])
        self.assertIn(
            "群聊回复消息发送失败",
            inbox.events["event-group-reply-failed"]["error_message"],
        )

    async def test_failed_c2c_reply_is_not_marked_processed(self):
        inbox = InMemoryEventInbox()
        sender = AsyncMock(return_value=None)

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "output_content", AsyncMock(return_value="reply")
        ), patch.object(main, "send_c2c_message", sender):
            with self.assertRaises(HTTPException) as caught:
                await main.handle_webhook(
                    self._c2c_message_request("event-c2c-reply-failed")
                )

        self.assertEqual(500, caught.exception.status_code)
        self.assertEqual(2, sender.await_count)
        self.assertEqual("FAILED", inbox.events["event-c2c-reply-failed"]["status"])
        self.assertIn(
            "私聊回复消息发送失败",
            inbox.events["event-c2c-reply-failed"]["error_message"],
        )

    async def test_handler_error_returns_safe_player_notice_when_delivery_is_available(self):
        inbox = InMemoryEventInbox()
        safe_sender = AsyncMock(return_value={"id": "safe-error-message"})

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "output_content", AsyncMock(side_effect=RuntimeError("unexpected label error"))
        ), patch.object(main, "send_c2c_message", safe_sender):
            response = await main.handle_webhook(
                self._c2c_message_request("event-c2c-processing-error")
            )

        self.assertEqual({"op": 12}, response)
        self.assertEqual("PROCESSED", inbox.events["event-c2c-processing-error"]["status"])
        content = safe_sender.await_args.args[1]
        self.assertIn("操作结果待确认", content)
        self.assertIn("event-c2c-processing-error", content)
        self.assertNotIn("unexpected label error", content)

    async def test_full_group_message_routes_with_member_openid(self):
        inbox = InMemoryEventInbox()
        sender = AsyncMock(return_value={"id": "sent-message-id"})

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "output_content", AsyncMock(return_value="全量回复")
        ) as output, patch.object(main, "send_group_message", sender):
            response = await main.handle_webhook(
                self._group_message_request(
                    "event-group-full-message",
                    event_type="GROUP_MESSAGE_CREATE",
                    author={"member_openid": "member-openid-1"},
                )
            )

        self.assertEqual({"op": 12}, response)
        output.assert_awaited_once_with(
            "menu", "member-openid-1", "group-openid-1", request_id="group-message-id-1"
        )
        sender.assert_awaited_once_with("group-openid-1", "全量回复", "group-message-id-1")
        self.assertEqual("GROUP_MESSAGE_CREATE", inbox.events["event-group-full-message"]["event_type"])
        self.assertEqual("PROCESSED", inbox.events["event-group-full-message"]["status"])

    async def test_full_group_at_message_strips_qq_mention_before_parsing(self):
        inbox = InMemoryEventInbox()
        sender = AsyncMock(return_value={"id": "sent-message-id"})

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "output_content", AsyncMock(return_value="艾特指令回复")
        ) as output, patch.object(main, "send_group_message", sender):
            response = await main.handle_webhook(
                self._group_message_request(
                    "event-group-full-at-message",
                    event_type="GROUP_MESSAGE_CREATE",
                    content="<@!bot-member-openid>菜单",
                    author={"member_openid": "member-openid-1"},
                )
            )

        self.assertEqual({"op": 12}, response)
        output.assert_awaited_once_with(
            "菜单", "member-openid-1", "group-openid-1", request_id="group-message-id-1"
        )
        sender.assert_awaited_once_with("group-openid-1", "艾特指令回复", "group-message-id-1")

    async def test_full_group_at_message_strips_visible_mention_before_parsing(self):
        inbox = InMemoryEventInbox()
        sender = AsyncMock(return_value={"id": "sent-message-id"})

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "output_content", AsyncMock(return_value="艾特指令回复")
        ) as output, patch.object(main, "send_group_message", sender):
            response = await main.handle_webhook(
                self._group_message_request(
                    "event-group-visible-at-message",
                    event_type="GROUP_MESSAGE_CREATE",
                    content="@机器人 菜单",
                    author={"member_openid": "member-openid-1"},
                )
            )

        self.assertEqual({"op": 12}, response)
        output.assert_awaited_once_with(
            "菜单", "member-openid-1", "group-openid-1", request_id="group-message-id-1"
        )

    async def test_full_group_message_silently_ignores_normal_chat(self):
        inbox = InMemoryEventInbox()
        output = AsyncMock()
        sender = AsyncMock()

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "output_content", output
        ), patch.object(main, "send_group_message", sender):
            response = await main.handle_webhook(
                self._group_message_request(
                    "event-group-normal-chat",
                    event_type="GROUP_MESSAGE_CREATE",
                    author={"member_openid": "member-openid-1"},
                    content="大家晚上好，今天一起玩吗？",
                )
            )

        self.assertEqual({"op": 12}, response)
        output.assert_not_awaited()
        sender.assert_not_awaited()
        self.assertEqual("PROCESSED", inbox.events["event-group-normal-chat"]["status"])

    async def test_group_at_message_keeps_unknown_command_feedback(self):
        inbox = InMemoryEventInbox()
        output = AsyncMock(return_value="指令错误，请检查指令后重试！")
        sender = AsyncMock(return_value={"id": "sent-message-id"})

        with patch.object(main, "event_inbox", inbox), patch.object(
            main, "output_content", output
        ), patch.object(main, "send_group_message", sender):
            response = await main.handle_webhook(
                self._group_message_request(
                    "event-group-at-unknown",
                    event_type="GROUP_AT_MESSAGE_CREATE",
                    content="完全未知的内容",
                )
            )

        self.assertEqual({"op": 12}, response)
        output.assert_awaited_once()
        sender.assert_awaited_once()

    async def test_full_group_message_ignores_bot_author(self):
        inbox = InMemoryEventInbox()
        output = AsyncMock()

        with patch.object(main, "event_inbox", inbox), patch.object(main, "output_content", output):
            response = await main.handle_webhook(
                self._group_message_request(
                    "event-group-bot-message",
                    event_type="GROUP_MESSAGE_CREATE",
                    author={"member_openid": "bot-member-openid", "bot": True},
                )
            )

        self.assertEqual({"op": 12}, response)
        output.assert_not_awaited()
        self.assertEqual("PROCESSED", inbox.events["event-group-bot-message"]["status"])

    def test_websocket_client_registers_full_group_message_callback(self):
        source = (Path(__file__).resolve().parents[1] / "bot_main.py").read_text(encoding="utf-8")
        self.assertIn("async def on_group_message_create", source)
        self.assertIn('"GROUP_MESSAGE_CREATE"', source)
        self.assertIn("should_reply_to_full_group_message", source)

    async def test_group_sender_serializes_event_reply_without_msg_id(self):
        captured = {}
        keyboard = {"content": {"rows": []}}

        with patch.object(
            main, "get_headers", AsyncMock(return_value={"Authorization": "QQBot token"})
        ), patch.object(
            main.aiohttp, "ClientSession", lambda: _FakeSession(captured)
        ), patch.object(
            main, "append_rotating_reply_notice", _append_official_notice
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
        self.assertTrue(
            captured["json"]["markdown"]["content"].endswith(OFFICIAL_GROUP_NOTICE)
        )

    async def test_c2c_sender_serializes_friend_event_reply_without_msg_id(self):
        captured = {}
        keyboard = {"content": {"rows": []}}

        with patch.object(
            main, "get_headers", AsyncMock(return_value={"Authorization": "QQBot token"})
        ), patch.object(
            main.aiohttp, "ClientSession", lambda: _FakeSession(captured)
        ), patch.object(
            main, "append_rotating_reply_notice", _append_official_notice
        ):
            result = await main.send_c2c_markdown_keyboard(
                "user-openid-1",
                "welcome",
                keyboard,
                event_id="event-friend-add-1",
            )

        self.assertEqual({"id": "sent-message-id"}, result)
        self.assertEqual("event-friend-add-1", captured["json"]["event_id"])
        self.assertNotIn("msg_id", captured["json"])
        self.assertEqual(2, captured["json"]["msg_type"])
        self.assertEqual(keyboard, captured["json"]["keyboard"])
        self.assertTrue(
            captured["json"]["markdown"]["content"].endswith(OFFICIAL_GROUP_NOTICE)
        )

    async def test_text_and_markdown_senders_append_official_group_notice(self):
        cases = (
            (
                "c2c_text",
                lambda: main.send_c2c_message("user-1", "reply", "message-1"),
                lambda payload: payload["content"],
            ),
            (
                "group_text",
                lambda: main.send_group_message("group-1", "reply", "message-1"),
                lambda payload: payload["content"],
            ),
            (
                "c2c_markdown",
                lambda: main.send_c2c_markdown("user-1", "reply", "message-1"),
                lambda payload: payload["markdown"]["content"],
            ),
            (
                "group_markdown",
                lambda: main.send_group_markdown("group-1", "reply", "message-1"),
                lambda payload: payload["markdown"]["content"],
            ),
        )

        for name, sender, get_content in cases:
            with self.subTest(name=name):
                captured = {}
                with patch.object(
                    main,
                    "get_headers",
                    AsyncMock(return_value={"Authorization": "QQBot token"}),
                ), patch.object(
                    main.aiohttp,
                    "ClientSession",
                    lambda: _FakeSession(captured),
                ), patch.object(
                    main,
                    "append_rotating_reply_notice",
                    _append_official_notice,
                ):
                    result = await sender()

                self.assertEqual({"id": "sent-message-id"}, result)
                self.assertTrue(get_content(captured["json"]).endswith(OFFICIAL_GROUP_NOTICE))

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

    async def test_c2c_sender_requires_exactly_one_reply_id(self):
        with self.assertRaises(ValueError):
            await main.send_c2c_markdown_keyboard(
                "user-openid-1", "welcome", {}, msg_id=None, event_id=None
            )
        with self.assertRaises(ValueError):
            await main.send_c2c_markdown_keyboard(
                "user-openid-1",
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

    async def test_world_message_gm_content_reaches_parser_without_uppercasing(self):
        raw_command = "GM世界消息添加 Boss 前先检查 Skill 配置！"
        parser = AsyncMock(return_value=("GM世界消息添加", "Boss 前先检查 Skill 配置！"))
        main.user_last_call_time.pop("gm-world-message-user", None)

        with patch.object(main, "jiance", parser), patch.object(
            main, "is_txt_exist", AsyncMock(return_value=False)
        ), patch.object(
            main, "content", AsyncMock(return_value="保存成功")
        ), patch.object(
            main, "record_monthly_card_player_activity", AsyncMock(return_value=None)
        ), patch.object(
            main.logging, "FileHandler", return_value=main.logging.NullHandler()
        ):
            result = await main.output_content(raw_command, "gm-world-message-user")

        parser.assert_awaited_once_with(raw_command)
        self.assertEqual("保存成功", result)


if __name__ == "__main__":
    unittest.main()
