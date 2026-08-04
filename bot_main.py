import asyncio
import os
import time
import json
from datetime import datetime

import botpy
from botpy import logging as botpy_logging
from botpy.ext.cog_yaml import read
from botpy.manage import C2CManageEvent, GroupManageEvent
from botpy.message import GroupMessage, Message, C2CMessage, DirectMessage
from botpy.types.message import KeyboardPayload, MarkdownPayload, MessageMarkdownParams
from botpy.types.inline import Keyboard, Button, RenderData, Action, Permission, KeyboardRow
from botpy.types.inline import Keyboard

from output_main import *
from Tool.tool_command import *
from Tool.qq_group_welcome import build_friend_welcome_message, build_group_welcome_message
from Tool.qq_event_delivery import send_event_with_retry
from Tool.qq_reply_footer import attach_rotating_reply_notice
from Game_domain.event_inbox import MySQLEventInbox

test_config = read(os.path.join(os.path.dirname(__file__), "config.yaml"))
_log = botpy_logging.get_logger()

user_last_call_time = {}
event_inbox = MySQLEventInbox()


async def output_content(user_content, user_openid, qun_openid=None, request_id=None):
    raw_user_content = user_content
    user_content = user_content.upper()

    # 图片模式密令两步验证（优先于限频与指令解析）
    pending_reply = check_img_mode_pending(user_content, user_openid)
    if pending_reply is not None:
        return pending_reply

    if await is_txt_exist(user_content):
        return await is_txt_exist(user_content)

    c_time = datetime.now().timestamp()

    if user_openid in user_last_call_time:
        time_diff = c_time - user_last_call_time[user_openid]
        if time_diff < 2:
            return "严重警告！你输入的指令过快！"
    user_last_call_time[user_openid] = c_time

    if user_content in ["1", "2", "3", "4", "5"] or re.match(r'^[1-5]-', user_content):
        user_content = await pd_command(user_openid, user_content)
        print(user_content)
        if user_content is False:
            return "该快捷指令不存在！"

    parser_content = (
        raw_user_content
        if any(
            raw_user_content.strip().upper().startswith(command)
            for command in world_message_value_commands
        )
        else user_content
    )
    con_arr0, con_arr1 = await jiance(parser_content)
    send_content = await content(con_arr0, con_arr1, user_openid, qun_openid, request_id=request_id)
    send_content = apply_image_mode(send_content)
    return attach_keyboard(send_content, is_group=qun_openid is not None)


class MyClient(botpy.Client):
    async def on_ready(self):
        _log.info(f"机器人 「{self.robot.name}」 上线了!")

    # 机器人被添加到群聊
    async def on_group_add_robot(self, event: GroupManageEvent):
        if not await event_inbox.claim(
            event.event_id,
            source="websocket",
            event_type="GROUP_ADD_ROBOT",
            body={
                "group_openid": event.group_openid,
                "op_member_openid": event.op_member_openid,
                "timestamp": event.timestamp,
            },
        ):
            return

        try:
            welcome = build_group_welcome_message()
            await send_event_with_retry(
                lambda: self.api.post_group_message(
                    group_openid=event.group_openid,
                    msg_type=2,
                    event_id=event.event_id,
                    msg_seq=1,
                    content="",
                    markdown=MarkdownPayload(content=welcome["content"]),
                    keyboard=welcome["keyboard"],
                )
            )
        except Exception as exc:
            await event_inbox.mark_processed(event.event_id, str(exc)[:500])
            raise

        await event_inbox.mark_processed(event.event_id)
        _log.info(f"已向新加入的群聊[{event.group_openid}]发送游戏介绍")

    # 玩家新添加机器人好友
    async def on_friend_add(self, event: C2CManageEvent):
        if not await event_inbox.claim(
            event.event_id,
            source="websocket",
            event_type="FRIEND_ADD",
            body={"openid": event.openid, "timestamp": event.timestamp},
        ):
            return

        try:
            welcome = build_friend_welcome_message()
            await send_event_with_retry(
                lambda: self.api.post_c2c_message(
                    openid=event.openid,
                    msg_type=2,
                    event_id=event.event_id,
                    msg_seq=1,
                    content="",
                    markdown=MarkdownPayload(content=welcome["content"]),
                    keyboard=welcome["keyboard"],
                )
            )
        except Exception as exc:
            await event_inbox.mark_processed(event.event_id, str(exc)[:500])
            raise

        await event_inbox.mark_processed(event.event_id)
        _log.info(f"已向新添加机器人的玩家[{event.openid}]发送游戏介绍")

    async def _handle_group_message(self, message: GroupMessage, event_type: str):
        """统一处理 @ 消息与已开启全量接收后的群消息事件。"""
        user_openid = message.author.member_openid        # 用户的openid
        qun_openid = message.group_openid                 # qq群的openid

        if not await event_inbox.claim(
            message.id,
            source="websocket",
            event_type=event_type,
            body={"content": message.content, "group_openid": qun_openid},
        ):
            return

        if (
            event_type == "GROUP_MESSAGE_CREATE"
            and not await should_reply_to_full_group_message(message.content, user_openid)
        ):
            await event_inbox.mark_processed(message.id)
            _log.info("忽略非游戏指令的全量群消息: %s", message.id)
            return

        send_content = await output_content(message.content, user_openid, qun_openid, request_id=message.id)
        send_content = await attach_rotating_reply_notice(send_content)

        _log.info(f"群聊玩家消息[{user_openid}]：{redact_sensitive_content(message.content.strip())}")
        if isinstance(send_content, dict):
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=2,
                msg_id=message.id,
                msg_seq=1,
                content="",
                markdown=MarkdownPayload(content=send_content.get("content", "")),
                keyboard=send_content.get("keyboard"),
            )
        else:
            await message._api.post_group_message(
                group_openid=message.group_openid,
                msg_type=0,
                msg_id=message.id,
                msg_seq=1,
                content=f"\n{send_content}",
            )
        await event_inbox.mark_processed(message.id)

        _log.info(f"机器人回复：{send_content}")

    # 群 @ 机器人消息
    async def on_group_at_message_create(self, message: GroupMessage):
        await self._handle_group_message(message, "GROUP_AT_MESSAGE_CREATE")

    # 开启“接收所有消息”后，群内非 @ 消息也会进入此事件。
    # 该事件和 GROUP_AT_MESSAGE_CREATE 共享 GROUP_AND_C2C_EVENT 意图。
    async def on_group_message_create(self, message: GroupMessage):
        if getattr(message.author, "bot", False):
            _log.info("忽略机器人自身的全量群消息: %s", message.id)
            return
        await self._handle_group_message(message, "GROUP_MESSAGE_CREATE")

    # 私聊消息
    async def on_c2c_message_create(self, message: C2CMessage):
        user_openid = message.author.user_openid  # 用户的openid

        if not await event_inbox.claim(
            message.id,
            source="websocket",
            event_type="C2C_MESSAGE_CREATE",
            body={"content": message.content, "user_openid": user_openid},
        ):
            return

        send_content = await output_content(message.content, user_openid, request_id=message.id)
        send_content = await attach_rotating_reply_notice(send_content)

        _log.info(f"私聊玩家消息[{user_openid}]：{redact_sensitive_content(message.content)}")
        if isinstance(send_content, dict):
            await self.api.post_c2c_message(
                openid=message.author.user_openid,
                msg_type=2,
                msg_id=message.id,
                msg_seq=1,
                content="",
                markdown=MarkdownPayload(content=send_content.get("content", "")),
                keyboard=send_content.get("keyboard"),
            )
        else:
            await self.api.post_c2c_message(
                openid=message.author.user_openid,
                msg_type=0,
                msg_id=message.id,
                msg_seq=1,
                content=send_content,
            )
        await event_inbox.mark_processed(message.id)

        _log.info(f"机器人回复：{send_content}")


if __name__ == "__main__":
    intents = botpy.Intents(public_messages=True, public_guild_messages=True, direct_message=True, guilds=True)
    client = MyClient(intents=intents)
    client.run(appid=test_config["appid"], secret=test_config["secret"])

