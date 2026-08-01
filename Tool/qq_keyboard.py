# -*- coding: utf-8 -*-
"""QQ Markdown 文本交互与自定义 Keyboard 的混合排版支持。"""

import html
import re
from typing import Dict, Iterable, List, Optional, Tuple


COMMAND_TAG_RE = re.compile(
    r"<qqbot-cmd-input\s+text=(?P<quote>['\"])(?P<text>.*?)(?P=quote)"
    r"\s+show=(?P<show_quote>['\"])(?P<show>.*?)(?P=show_quote)\s*/>",
    re.IGNORECASE,
)

MAX_ROWS = 5
MAX_BUTTONS_PER_ROW = 2
MAX_LABEL_LENGTH = 10
MAX_COMMAND_LENGTH = 100


def _clip(value: str, limit: int) -> str:
    value = html.unescape(str(value or "")).strip()
    return value if len(value) <= limit else value[:limit]


def command_button(
    label: str,
    command: str,
    *,
    complete: bool,
    is_group: bool,
    button_id: str,
    style: int = 1,
) -> Dict:
    """构造一个 QQ 开放平台 type=2 指令按钮。"""
    label = _clip(label, MAX_LABEL_LENGTH) or "执行"
    command = _clip(command, MAX_COMMAND_LENGTH)
    return {
        "id": _clip(button_id, 64),
        "render_data": {
            "label": label,
            "visited_label": label,
            "style": max(0, min(3, int(style))),
        },
        "action": {
            "type": 2,
            "permission": {"type": 2},
            "data": command,
            # 官方协议仅允许单聊直接发送；群聊一律只填入输入框。
            "enter": bool(complete and not is_group),
            "reply": False,
        },
    }


def build_keyboard(buttons: Iterable[Dict]) -> Dict:
    items = list(buttons)[: MAX_ROWS * MAX_BUTTONS_PER_ROW]
    rows = [
        {"buttons": items[index:index + MAX_BUTTONS_PER_ROW]}
        for index in range(0, len(items), MAX_BUTTONS_PER_ROW)
    ]
    return {"content": {"rows": rows}}


def build_command_keyboard(commands: Iterable, *, is_group: bool) -> Optional[Dict]:
    """从业务显式声明的主操作构建 Keyboard，不改动 Markdown 正文。"""
    buttons: List[Dict] = []
    for index, item in enumerate(list(commands)[: MAX_ROWS * MAX_BUTTONS_PER_ROW], 1):
        if isinstance(item, dict):
            command = str(item.get("command", item.get("data", "")))
            label = str(item.get("label", command))
            complete = item.get("complete")
            style = item.get("style", 1)
        elif isinstance(item, (tuple, list)) and item:
            command = str(item[0])
            label = str(item[1]) if len(item) > 1 else command
            complete = None
            style = 1
        else:
            command = label = str(item or "")
            complete = None
            style = 1
        if not command.strip():
            continue
        buttons.append(command_button(
            label,
            command,
            complete=_is_complete_command(command, label) if complete is None else bool(complete),
            is_group=is_group,
            button_id=f"cmd_{index}",
            style=style,
        ))
    return build_keyboard(buttons) if buttons else None


def _is_complete_command(command: str, label: str) -> bool:
    """含占位符或刻意保留尾部空格的指令需要玩家继续输入参数。"""
    raw = html.unescape(command or "")
    if raw != raw.rstrip():
        return False
    hint = f"{raw}{html.unescape(label or '')}"
    return not any(token in hint for token in ("*", "［", "[", "编号", "名称", "数量", "ID", "id"))


def extract_keyboard(markdown: str, *, is_group: bool) -> Tuple[str, Optional[Dict]]:
    """显式迁移工具：把正文标签抽取为 Keyboard；全局回复不再自动调用。"""
    if not isinstance(markdown, str) or "<qqbot-cmd-input" not in markdown.lower():
        return markdown, None

    matches = list(COMMAND_TAG_RE.finditer(markdown))
    if not matches:
        return markdown, None

    selected = matches[: MAX_ROWS * MAX_BUTTONS_PER_ROW]
    buttons: List[Dict] = []
    selected_spans = set()
    for index, match in enumerate(selected, 1):
        command = html.unescape(match.group("text"))
        label = html.unescape(match.group("show"))
        buttons.append(command_button(
            label,
            command,
            complete=_is_complete_command(command, label),
            is_group=is_group,
            button_id=f"cmd_{index}",
        ))
        selected_spans.add(match.span())

    pieces = []
    cursor = 0
    for match in matches:
        pieces.append(markdown[cursor:match.start()])
        if match.span() not in selected_spans:
            # 超出 keyboard 容量时保留旧标签，避免丢失入口。
            pieces.append(match.group(0))
        cursor = match.end()
    pieces.append(markdown[cursor:])
    cleaned = "".join(pieces)
    cleaned = re.sub(r"[ \t]*\|[ \t]*(?=\r?$)", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?m)^[ \t]*\|[ \t]*$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, build_keyboard(buttons)


def attach_keyboard(result, *, is_group: bool):
    """仅处理业务显式声明的 Keyboard；正文蓝字标签始终留在原排版位置。"""
    if isinstance(result, str):
        if "<qqbot-cmd-input" in result.lower():
            return {"type": "markdown", "content": result}
        return result
    if not isinstance(result, dict):
        return result
    if result.get("type") == "markdown_keyboard" or not isinstance(result.get("content"), str):
        return result

    commands = result.get("keyboard_commands")
    if not commands:
        return result
    keyboard = build_command_keyboard(commands, is_group=is_group)
    if not keyboard:
        return result

    upgraded = dict(result)
    upgraded.pop("keyboard_commands", None)
    upgraded.update({"type": "markdown_keyboard", "keyboard": keyboard})
    return upgraded
