# *-* coding:utf-8 *-*
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from cryptography.hazmat.primitives.asymmetric import ed25519
import logging
import uvicorn
import json
import hashlib
import aiohttp
import asyncio
import os
from output_main import *
from config import DOMAIN, IMG_BASE_URL
from Game_domain.event_inbox import MySQLEventInbox
from Tool.qq_keyboard import attach_keyboard
from Tool.qq_group_welcome import build_friend_welcome_message, build_group_welcome_message
from Tool.qq_official_group import append_official_group_notice

send_content = ''
user_last_call_time = {}

async def output_content(user_content, user_openid, qun_openid=None, request_id=None):
    import logging as lg
    lg.basicConfig(
        level=lg.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            lg.FileHandler("con_error.log"),
            lg.StreamHandler()
        ]
    )
    c_logger = lg.getLogger(__name__)

    # try:
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

    a = ('AC5EF3D2A47723672DB287CD216931A7', "7E9CFF8E86898B27D9009567D61D7A64")

    start_time = time.perf_counter()

    # if user_openid in f:
    #     return "您已被封禁！反复刷BUG导致游戏数据异常！\n警告！若发现玩家利用bug，刷取游戏数据，不及时上报反馈，将作封号处理！"

    # 小群：DF4D4281BEFA2776256C11AD7030596D
    # 内测群：1341185812BBA8426C8E1AD1BB254DAF

    con_arr0, con_arr1 = await jiance(user_content)
    send_content = await content(con_arr0, con_arr1, user_openid, qun_openid, request_id=request_id)
    send_content = apply_image_mode(send_content)
    send_content = attach_keyboard(send_content, is_group=qun_openid is not None)
    end_time = time.perf_counter()

    # send_content += f"\n\n执行耗时：{(end_time - start_time):.2f}s"
    return send_content

    # except Exception as e:
    #     c_logger.error(f"异常问题: {e}")
    #     return "异常错误，请截图当前消息添加反馈群反馈！"

# 斗罗觉醒APPID
APP_ID = os.getenv("QQ_APP_ID", "")
BOT_SECRET = os.getenv("QQ_BOT_SECRET", "")

# 苍穹觉醒APPID
# Configure QQ_APP_ID and QQ_BOT_SECRET through the environment.

# 沙箱模式配置（设为 True 使用沙箱环境，False 使用正式环境）
# 沙箱模式需要在QQ开放平台后台配置"沙箱配置"
SANDBOX_MODE = os.getenv("QQ_SANDBOX_MODE", "false").lower() == "true"

# 根据沙箱模式设置API域名
# 注意：Token URL 始终相同，只有 API 域名区分沙箱环境
if SANDBOX_MODE:
    API_BASE = "https://sandbox.api.sgroup.qq.com"
else:
    API_BASE = "https://api.sgroup.qq.com"

TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

app = FastAPI()
event_inbox = MySQLEventInbox()

# 配置日志
logging.basicConfig(level=logging.INFO)


# 定义数据模型
class ValidationRequest(BaseModel):
    plain_token: str
    event_ts: str


class ValidationResponse(BaseModel):
    plain_token: str
    signature: str


class Payload(BaseModel):
    id: str = None
    op: int
    d: dict
    s: int = None
    t: str = None


# 获取headers（异步版本）
async def get_headers(appid, secret):
    try:
        url = TOKEN_URL
        payload = {"appId": appid, "clientSecret": secret}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                
                if response.status != 200:
                    response_text = await response.text()
                    logging.error(f"获取access_token失败，状态码: {response.status}")
                    raise Exception(f"获取access_token失败: {response_text}")
                
                json_data = await response.json()
                
                if "access_token" not in json_data:
                    logging.error(f"响应中没有access_token字段: {json_data}")
                    raise Exception(f"响应中没有access_token字段: {json_data}")
                
                access_token = json_data["access_token"]
                
                headers = {
                    "Authorization": f"QQBot {access_token}"
                }
                
                return headers
    
    except Exception as e:
        logging.error(f"获取headers时发生错误: {e}")
        raise


# 发送私聊消息（异步版本）
async def send_c2c_message(openid, content, msg_id):
    try:
        headers = await get_headers(APP_ID, BOT_SECRET)
        url = f"{API_BASE}/v2/users/{openid}/messages"
        json_data = {
            "content": append_official_group_notice(content),
            "msg_type": 0,
            "msg_id": msg_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json_data, headers=headers) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        return await response.json()
                    except:
                        return json_data
                else:
                    logging.error(f"私聊消息发送失败，状态码: {response.status}，响应: {response_text}")
                    return None
    
    except Exception as e:
        logging.error(f"发送私聊消息时发生错误: {e}")
        return None


# 发送群聊消息（异步版本）
async def send_group_message(group_openid, content, msg_id):
    try:
        headers = await get_headers(APP_ID, BOT_SECRET)
        url = f"{API_BASE}/v2/groups/{group_openid}/messages"
        json_data = {
            "content": append_official_group_notice(content),
            "msg_type": 0,
            "msg_id": msg_id
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json_data, headers=headers) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        return await response.json()
                    except:
                        return json_data
                else:
                    logging.error(f"群聊消息发送失败，状态码: {response.status}，响应: {response_text}")
                    return None

    except Exception as e:
        logging.error(f"发送群聊消息时发生错误: {e}")
        return None


# 发送群聊Markdown消息（异步版本）
async def send_group_markdown(group_openid, markdown_content, msg_id):
    """
    发送群聊Markdown消息
    :param group_openid: 群openid
    :param markdown_content: Markdown内容字符串
    :param msg_id: 回复的消息ID
    """
    try:
        headers = await get_headers(APP_ID, BOT_SECRET)
        url = f"{API_BASE}/v2/groups/{group_openid}/messages"

        # 构造markdown对象
        json_data = {
            "content": "",
            "msg_type": 2,   # 2 表示 markdown 消息
            "msg_id": msg_id,
            "markdown": {
                "content": append_official_group_notice(markdown_content)
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json_data, headers=headers) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        return await response.json()
                    except:
                        return json_data
                else:
                    logging.error(f"Markdown消息发送失败，状态码: {response.status}，响应: {response_text}")
                    return None

    except Exception as e:
        logging.error(f"发送Markdown消息时发生错误: {e}")
        return None


# 发送私聊Markdown消息（异步版本）
async def send_c2c_markdown(openid, markdown_content, msg_id):
    """
    发送私聊Markdown消息
    :param openid: 用户openid
    :param markdown_content: Markdown内容字符串
    :param msg_id: 回复的消息ID
    """
    try:
        headers = await get_headers(APP_ID, BOT_SECRET)
        url = f"{API_BASE}/v2/users/{openid}/messages"

        # 构造markdown对象
        json_data = {
            "content": "",
            "msg_type": 2,   # 2 表示 markdown 消息
            "msg_id": msg_id,
            "markdown": {
                "content": append_official_group_notice(markdown_content)
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json_data, headers=headers) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        return await response.json()
                    except:
                        return json_data
                else:
                    logging.error(f"私聊Markdown消息发送失败，状态码: {response.status}，响应: {response_text}")
                    return None

    except Exception as e:
        logging.error(f"发送私聊Markdown消息时发生错误: {e}")
        return None


# 发送群聊Markdown+Keyboard消息（异步版本）
async def send_group_markdown_keyboard(
    group_openid,
    markdown_content,
    keyboard,
    msg_id=None,
    *,
    event_id=None,
):
    """
    发送群聊Markdown+Keyboard消息
    :param group_openid: 群openid
    :param markdown_content: Markdown内容字符串
    :param keyboard: Keyboard按钮对象
    :param msg_id: 被动回复的消息 ID
    :param event_id: 被动响应的事件 ID，与 msg_id 二选一
    """
    if bool(msg_id) == bool(event_id):
        raise ValueError("msg_id 和 event_id 必须且只能传入一个")

    try:
        headers = await get_headers(APP_ID, BOT_SECRET)
        url = f"{API_BASE}/v2/groups/{group_openid}/messages"

        # 构造markdown+keyboard对象
        json_data = {
            "content": "",
            "msg_type": 2,
            "markdown": {
                "content": append_official_group_notice(markdown_content)
            },
            "keyboard": keyboard
        }
        json_data["msg_id" if msg_id else "event_id"] = msg_id or event_id

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json_data, headers=headers) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        return await response.json()
                    except:
                        return json_data
                else:
                    logging.error(f"Markdown+Keyboard消息发送失败，状态码: {response.status}，响应: {response_text}")
                    return None

    except Exception as e:
        logging.error(f"发送Markdown+Keyboard消息时发生错误: {e}")
        return None


# 发送私聊Markdown+Keyboard消息（异步版本）
async def send_c2c_markdown_keyboard(
    openid,
    markdown_content,
    keyboard,
    msg_id=None,
    *,
    event_id=None,
):
    """
    发送私聊Markdown+Keyboard消息
    :param openid: 用户openid
    :param markdown_content: Markdown内容字符串
    :param keyboard: Keyboard按钮对象
    :param msg_id: 被动回复的消息 ID
    :param event_id: 被动响应的事件 ID，与 msg_id 二选一
    """
    if bool(msg_id) == bool(event_id):
        raise ValueError("msg_id 和 event_id 必须且只能传入一个")

    try:
        headers = await get_headers(APP_ID, BOT_SECRET)
        url = f"{API_BASE}/v2/users/{openid}/messages"

        # 构造markdown+keyboard对象
        json_data = {
            "content": "",
            "msg_type": 2,
            "markdown": {
                "content": append_official_group_notice(markdown_content)
            },
            "keyboard": keyboard
        }
        json_data["msg_id" if msg_id else "event_id"] = msg_id or event_id

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=json_data, headers=headers) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        return await response.json()
                    except:
                        return json_data
                else:
                    logging.error(f"私聊Markdown+Keyboard消息发送失败，状态码: {response.status}，响应: {response_text}")
                    return None

    except Exception as e:
        logging.error(f"发送私聊Markdown+Keyboard消息时发生错误: {e}")
        return None


# 消息过滤函数（过滤/符号）
def filter_message_content(content: str) -> str:
    """
    过滤玩家发送消息中的/符号，防止命令解析错误
    """
    if not content:
        return content
    return content.replace("/", "")


# Ed25519签名计算函数（按照QQ机器人文档实现）
def generate_signature(bot_secret: str, event_ts: str, plain_token: str) -> str:
    """
    根据QQ机器人文档实现Ed25519签名算法
    参考: https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/interface-framework/event-emit.html#webhook%E6%96%B9%E5%BC%8F
    
    经过调试验证，正确的实现方式是：
    1. 重复bot_secret直到长度达到32字节
    2. 直接使用种子字节作为Ed25519私钥种子
    3. 确保种子长度为32字节（填充或截取）
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    # 1. 生成种子：重复bot_secret直到长度达到32字节
    seed = bot_secret
    while len(seed) < 32:
        seed = seed + seed  # 重复字符串
    seed = seed[:32]  # 截取前32字节

    # 2. 直接使用种子字节作为私钥种子
    seed_bytes = seed.encode('utf-8')

    # 3. 确保种子长度为32字节
    if len(seed_bytes) < 32:
        # 如果不足32字节，用0填充
        seed_bytes = seed_bytes + b'\x00' * (32 - len(seed_bytes))
    elif len(seed_bytes) > 32:
        # 如果超过32字节，截取前32字节
        seed_bytes = seed_bytes[:32]

    # 4. 使用种子生成Ed25519私钥
    private_key = Ed25519PrivateKey.from_private_bytes(seed_bytes)

    # 5. 构造待签名消息：event_ts + plain_token
    message = (event_ts + plain_token).encode('utf-8')

    # 6. 生成签名并转换为十六进制字符串
    signature_bytes = private_key.sign(message)
    signature = signature_bytes.hex()

    return signature


@app.post("/webhook")
async def handle_webhook(request: Request):
    """
    处理QQ开放平台的webhook请求
    支持回调地址验证和事件推送
    """
    event_id = None
    try:
        # 获取请求头信息
        user_agent = request.headers.get("User-Agent", "")
        bot_appid = request.headers.get("X-Bot-Appid", "")

        # 验证请求来源（仅在生产环境中启用严格验证）
        if user_agent and user_agent != "QQBot-Callback":
            logging.warning(f"无效的User-Agent: {user_agent}")
            # 在开发环境中，我们可以放宽验证
            # raise HTTPException(status_code=400, detail="Invalid User-Agent")

        # 获取请求体
        body_bytes = await request.body()
        body_str = body_bytes.decode('utf-8')

        # 解析payload
        payload_data = json.loads(body_str)
        payload = Payload(**payload_data)
        event_id = payload.id

        logging.info(f"收到webhook请求 - AppID: {bot_appid}, OpCode: {payload.op}")

        # QQ 可能重投同一事件；先按平台事件 ID 去重，避免重复执行游戏指令。
        if payload.op == 0 and event_id:
            claimed = await event_inbox.claim(
                event_id,
                source="webhook",
                event_type=payload.t or "UNKNOWN",
                body=payload.d,
            )
            if not claimed:
                logging.info(f"忽略重复Webhook事件: {event_id}")
                return {"op": 12}

        # 处理回调地址验证 (op=13)
        if payload.op == 13:

            validation_request = ValidationRequest(**payload.d)

            # 计算签名
            signature = generate_signature(
                BOT_SECRET,
                validation_request.event_ts,
                validation_request.plain_token
            )

            response = ValidationResponse(
                plain_token=validation_request.plain_token,
                signature=signature
            )
            return response.dict()

        # 处理事件推送 (op=0)
        elif payload.op == 0:
            # 消息类型
            message_type = payload.t
            # webhook收到事件内容
            json_data_text = json.dumps(payload.d, ensure_ascii=False, indent=2)
            json_data = json.loads(json_data_text)

            logging.info(f"消息类型: {message_type}")
            # 管理事件体不含普通消息的 content/author/id，必须先分流。
            if payload.t == "GROUP_ADD_ROBOT":
                group_openid = json_data["group_openid"]
                welcome = build_group_welcome_message()
                result = await send_group_markdown_keyboard(
                    group_openid,
                    welcome["content"],
                    welcome["keyboard"],
                    event_id=event_id,
                )
                if result is None:
                    raise RuntimeError("入群欢迎消息发送失败")
                logging.info(f"已向新加入的群聊[{group_openid}]发送游戏介绍")

            # 玩家新添加机器人后，使用顶层事件 ID 发送被动欢迎消息。
            elif payload.t == "FRIEND_ADD":
                user_openid = json_data["openid"]
                welcome = build_friend_welcome_message()
                result = await send_c2c_markdown_keyboard(
                    user_openid,
                    welcome["content"],
                    welcome["keyboard"],
                    event_id=event_id,
                )
                if result is None:
                    raise RuntimeError("好友欢迎消息发送失败")
                logging.info(f"已向新添加机器人的玩家[{user_openid}]发送游戏介绍")

            # 群聊消息处理
            elif payload.t == "GROUP_AT_MESSAGE_CREATE":
                content = filter_message_content(json_data["content"])
                user_openid = json_data["author"]["union_openid"]
                msg_id = json_data["id"]
                group_openid = json_data["group_openid"]
                logging.info(f"群聊【{group_openid}】{user_openid}：{redact_sensitive_content(content)}")
                # 发送群聊消息
                result = await output_content(content, user_openid, group_openid, request_id=msg_id)

                # 检查返回消息类型
                if isinstance(result, dict):
                    result_type = result.get("type")
                    if result_type == "markdown_keyboard":
                        # Markdown + Keyboard 消息
                        asyncio.create_task(send_group_markdown_keyboard(
                            group_openid, result["content"], result["keyboard"], msg_id
                        ))
                    elif result_type == "markdown":
                        # 纯 Markdown 消息
                        await asyncio.create_task(send_group_markdown(group_openid, result["content"], msg_id))
                    else:
                        # 普通文本消息
                        await asyncio.create_task(send_group_message(group_openid, result, msg_id))
                else:
                    asyncio.create_task(send_group_message(group_openid, result, msg_id))

            # 私聊消息处理
            elif payload.t == "C2C_MESSAGE_CREATE":
                content = filter_message_content(json_data["content"])
                user_openid = json_data["author"]["union_openid"]
                msg_id = json_data["id"]
                logging.info(f"私聊【{user_openid}】：{redact_sensitive_content(content)}")
                result = await output_content(content, user_openid, request_id=msg_id)

                # 检查返回消息类型
                if isinstance(result, dict):
                    result_type = result.get("type")
                    if result_type == "markdown_keyboard":
                        # Markdown + Keyboard 消息
                        await asyncio.create_task(send_c2c_markdown_keyboard(
                            user_openid, result["content"], result["keyboard"], msg_id
                        ))
                    elif result_type == "markdown":
                        # 纯 Markdown 消息
                        await asyncio.create_task(send_c2c_markdown(user_openid, result["content"], msg_id))
                    else:
                        # 普通文本消息
                        await asyncio.create_task(send_c2c_message(user_openid, result, msg_id))
                else:
                    asyncio.create_task(send_c2c_message(user_openid, result, msg_id))

            else:
                logging.info(f"暂未配置业务处理的事件: {message_type}")

            # logging.info(f"{json_data_text}")

            # 返回HTTP Callback ACK (op=12)
            if event_id:
                await event_inbox.mark_processed(event_id)
            return {"op": 12}

        else:
            logging.warning(f"未知的OpCode: {payload.op}")
            return {"error": "Unknown OpCode"}

    except json.JSONDecodeError as e:
        logging.error(f"JSON解析失败: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        if event_id:
            try:
                await event_inbox.mark_processed(event_id, str(e)[:500])
            except Exception:
                logging.exception("记录Webhook失败事件时发生错误")
        logging.error(f"处理webhook请求失败: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")


@app.get("/")
async def root():
    """
    根路径，返回102135148.json文件内容
    """
    json_path = os.path.join(IMAGES_DIR, "102056573.json")
    if os.path.exists(json_path):
        return FileResponse(json_path, media_type="application/json")
    return {"message": "QQ机器人webhook签名服务运行中"}


@app.get("/health")
async def health_check():
    """
    健康检查端点
    """
    return {"status": "healthy"}


@app.get("/102135148.json/")
async def get_images_index():
    """
    访问 /images/ 返回102135148.json文件内容
    """
    json_path = os.path.join(IMAGES_DIR, "102135148.json")
    if os.path.exists(json_path):
        return FileResponse(json_path, media_type="application/json")
    raise HTTPException(status_code=404, detail="文件不存在")


@app.get("/images/{image_name}")
async def get_image(image_name: str):
    """
    获取图片
    访问 /images/图片名称 可以获取图片
    """
    image_path = os.path.join(IMAGES_DIR, image_name)
    
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    
    if not os.path.isfile(image_path):
        raise HTTPException(status_code=400, detail="不是有效的图片文件")
    
    return FileResponse(image_path)


if __name__ == "__main__":
    if not APP_ID or not BOT_SECRET:
        raise RuntimeError("QQ_APP_ID and QQ_BOT_SECRET must be configured in the environment")

    print("启动QQ机器人Webhook服务器...")
    print(f"服务器域名地址：{DOMAIN}/")
    print(f"Webhook端点: {DOMAIN}/webhook")
    print(f"健康检查: {DOMAIN}/health")
    print(f"图片访问: {IMG_BASE_URL}/图片名称")
    print(f"图片目录: {IMAGES_DIR}")

    uvicorn.run(app,
                host=os.getenv("APP_HOST", "127.0.0.1"),
                port=int(os.getenv("APP_PORT", "8000")),
                log_level="info")
