# -*- coding: utf-8 -*-
"""道心问境 QQ 指令入口。"""

from Game_domain.dao_heart_service import (
    DaoHeartError,
    TENDENCY_LABELS,
    choose_daily_path,
    get_daily_state,
)
from func.pd_func import reg_xz_func


CHOICE_COMMANDS = {
    "清明": "clarity",
    "勇毅": "courage",
    "仁心": "compassion",
    "clarity": "clarity",
    "courage": "courage",
    "compassion": "compassion",
}


def _button(command, label):
    return f"<qqbot-cmd-input text='{command}' show='{label}' />"


def render_dao_heart_state(state):
    event = state["event"]
    tendencies = state["tendencies"]
    lines = [
        f"##### 🪷 道心问境 · {event['title']}",
        "",
        f"> {event['description']}",
        f"> 天机种：`{event['seed']}`（同日可复现）",
        "",
        f"**道心倾向：** 清明 {tendencies['clarity']}｜勇毅 {tendencies['courage']}｜仁心 {tendencies['compassion']}",
    ]
    if state["chosen"]:
        result = state.get("result") or {}
        lines.extend((
            "",
            f"**今日已择：** {result.get('choice_label', state.get('choice_key', '未知'))}",
            f"> {result.get('result_text', '今日问境已经完成。')}",
            f"**所得：** 灵石 ×{int((result.get('reward') or {}).get('lingshi', 0))}",
            f"**道心余韵：** {(result.get('buff') or {}).get('text', '今日有效')}",
            "",
            _button("今日修行", "返回今日修行"),
        ))
        return {"type": "markdown", "content": "\n".join(lines)}

    lines.extend(("", "**今日三问，只可择一：**"))
    for choice in event["choices"]:
        lines.extend((
            f"> **{choice['label']} · {choice['tendency']}**：{choice['description']}",
            f"> 奖励灵石 ×{choice['reward']['lingshi']}；{choice['buff']}",
            _button(f"道心抉择 {choice['tendency']}", f"选择{choice['tendency']}之道"),
            "",
        ))
    lines.append(_button("活动菜单", "返回活动菜单"))
    return {"type": "markdown", "content": "\n".join(lines)}


@reg_xz_func
async def dao_heart_home(uid, qz):
    try:
        return render_dao_heart_state(await get_daily_state(uid))
    except DaoHeartError as exc:
        return {"type": "markdown", "content": f"##### 道心问境未开启\n\n{exc}"}


@reg_xz_func
async def dao_heart_choose(uid, qz, value, request_id=None):
    choice_key = CHOICE_COMMANDS.get(str(value or "").strip().lower())
    if not choice_key:
        return {"type": "markdown", "content": "格式：道心抉择 清明（或勇毅、仁心）"}
    try:
        result = await choose_daily_path(uid, choice_key, request_id=request_id)
    except DaoHeartError as exc:
        return {"type": "markdown", "content": f"##### 道心抉择未完成\n\n{exc}"}

    tendencies = result["tendencies"]
    replayed = "\n> 今日抉择此前已完成，本次未重复发奖。" if result.get("replayed") else ""
    content = "\n".join((
        f"##### 🪷 {result['event_title']} · {result['choice_label']}",
        "",
        f"> {result['result_text']}{replayed}",
        f"**获得：** 灵石 ×{result['reward']['lingshi']}",
        f"**道心余韵：** {result['buff']['text']}",
        f"**当前倾向：** 清明 {tendencies['clarity']}｜勇毅 {tendencies['courage']}｜仁心 {tendencies['compassion']}",
        "",
        f"{_button('参悟', '开始参悟')} | {_button('道心问境', '查看今日问境')} | {_button('今日修行', '今日修行')}",
    ))
    return {"type": "markdown", "content": content}
