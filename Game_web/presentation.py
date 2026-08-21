# -*- coding: utf-8 -*-
"""把现有 QQ Markdown 响应安全适配为网页 JSON。"""

from html.parser import HTMLParser
import re
from uuid import uuid4

from Game_domain.monthly_card_service import record_monthly_card_player_activity
from Tool.tool_user import uid_to_openid


MAX_WEB_COMMAND_LENGTH = 120
BLOCKED_PLAYER_COMMANDS = {
    "GM验证",
    "GM菜单",
    "GM发放物品",
    "GM发放仙玉",
    "GM全服发放灵石",
    "GM全服发放仙玉",
    "GM生成兑换码",
    "GM生成月卡码",
    "GM世界消息",
    "GM世界消息添加",
    "GM世界消息修改",
    "GM世界消息启用",
    "GM世界消息停用",
    "GM世界消息删除",
    "GM立绘审核",
    "GM查看立绘",
    "GM通过立绘",
    "GM驳回立绘",
    "GM网页绑定",
    "关闭图片模式",
    "开启图片模式",
}


class _QQCommandParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.actions = []

    def handle_starttag(self, tag, attrs):
        if tag != "qqbot-cmd-input":
            return
        attributes = dict(attrs)
        command = str(attributes.get("text", "")).strip()
        label = str(attributes.get("show", command)).strip().rstrip("*").strip()
        if command and len(command) <= MAX_WEB_COMMAND_LENGTH:
            self.actions.append({"label": label or command, "command": command})


def _deduplicate_actions(actions):
    seen = set()
    result = []
    for action in actions:
        key = (action["label"], action["command"])
        if key not in seen:
            seen.add(key)
            result.append(action)
    return result[:24]


def adapt_game_response(response) -> dict:
    """返回前端可渲染的有限 Markdown 和动作列表。"""

    if isinstance(response, dict):
        content = str(response.get("content", ""))
        response_type = str(response.get("type", "markdown"))
    else:
        content = str(response or "")
        response_type = "text"

    parser = _QQCommandParser()
    parser.feed(content)
    # 标签替换为其可读 label，防止网页显示平台私有标记。
    def replace_tag(match):
        inner = match.group(0)
        local = _QQCommandParser()
        local.feed(inner)
        return local.actions[0]["label"] if local.actions else ""

    content = re.sub(r"<qqbot-cmd-input\b[^>]*>", replace_tag, content, flags=re.I)
    content = re.sub(r"<qqbot-[^>]+>", "", content, flags=re.I)
    content = re.sub(r"^To\[\d+\][^：\n]*：\s*", "", content)
    return {
        "type": response_type,
        "content": content.strip(),
        "actions": _deduplicate_actions(parser.actions),
    }


async def dispatch_web_command(uid: int, command: str, *, request_id: str = None) -> dict:
    """使用现有命令路由执行玩家命令，同时阻断所有 GM/全局管理入口。"""

    raw_command = str(command or "").strip()
    if not raw_command:
        raise ValueError("请输入或选择一个指令。")
    if len(raw_command) > MAX_WEB_COMMAND_LENGTH:
        raise ValueError(f"指令不能超过 {MAX_WEB_COMMAND_LENGTH} 个字符。")

    # 延迟导入避免 Web 路由和 output_main 初始化时形成循环引用。
    from output_main import content, jiance

    command_name, command_value = await jiance(raw_command)
    if not command_name:
        raise ValueError("无法识别该指令，请从页面按钮中选择。")
    if command_name in BLOCKED_PLAYER_COMMANDS or command_name.startswith("GM"):
        raise ValueError("玩家网页不能执行管理指令。")
    openid = await uid_to_openid(int(uid))
    if not openid:
        raise ValueError("玩家账号不存在或未绑定 QQ。")
    result = await content(
        command_name,
        command_value,
        openid,
        group_openid=None,
        request_id=request_id or f"web:{uid}:{uuid4().hex}",
    )
    await record_monthly_card_player_activity(openid)
    return adapt_game_response(result)
