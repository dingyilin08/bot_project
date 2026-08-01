import asyncio
import os
import time
import json
from datetime import datetime

import botpy
from botpy import logging
from botpy.ext.cog_yaml import read
from botpy.manage import GroupManageEvent
from botpy.message import GroupMessage, Message, C2CMessage, DirectMessage
from botpy.types.message import KeyboardPayload, MarkdownPayload, MessageMarkdownParams
from botpy.types.inline import Keyboard, Button, RenderData, Action, Permission, KeyboardRow
from botpy.types.inline import Keyboard

from output_main import *
from Tool.tool_command import *
from Game_domain.event_inbox import MySQLEventInbox

test_config = read(os.path.join(os.path.dirname(__file__), "config.yaml"))
_log = logging.get_logger()

user_last_call_time = {}
event_inbox = MySQLEventInbox()


async def output_content(user_content, user_openid, qun_openid=None):
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

    con_arr0, con_arr1 = await jiance(user_content)
    send_content = await content(con_arr0, con_arr1, user_openid, qun_openid)
    send_content = apply_image_mode(send_content)
    return attach_keyboard(send_content, is_group=qun_openid is not None)


class MyClient(botpy.Client):
    async def on_ready(self):
        _log.info(f"机器人 「{self.robot.name}」 上线了!")

    # 群聊消息
    async def on_group_at_message_create(self, message: GroupMessage):
        user_openid = message.author.member_openid        # 用户的openid
        qun_openid = message.group_openid                 # qq群的openid

        if not await event_inbox.claim(
            message.id,
            source="websocket",
            event_type="GROUP_AT_MESSAGE_CREATE",
            body={"content": message.content, "group_openid": qun_openid},
        ):
            return

        send_content = await output_content(message.content, user_openid, qun_openid)

        _log.info(f"群聊玩家消息[{user_openid}]：{message.content.strip()}")
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

        send_content = await output_content(message.content, user_openid)

        _log.info(f"私聊玩家消息[{user_openid}]：{message.content}")
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

