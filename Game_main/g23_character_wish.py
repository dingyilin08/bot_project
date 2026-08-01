# -*- coding: utf-8 -*-
"""仙玉祈愿 QQ 交互层。"""

from collections import Counter

from func.pd_func import reg_xz_func
from Game_domain.character_wish_service import (
    CharacterWishError,
    FULL_RESOURCE,
    FULL_SPECIAL,
    compose,
    draw,
    fragments,
    history,
    home,
    set_full_choice,
    set_target,
)


def _button(command, label=None):
    return f"<qqbot-cmd-input text='{command}' show='{label or command}' />"


def _result(content, commands=()):
    return {"type": "markdown", "content": content, "keyboard_commands": list(commands)}


def _error(error):
    message = error.message if isinstance(error, CharacterWishError) else str(error)
    return _result(
        f"##### ⚠️ 仙玉祈愿未生效\n\n{message}\n\n{_button('仙玉祈愿', '返回祈愿')} | {_button('主菜单', '主菜单')}",
        (("仙玉祈愿", "返回祈愿"), ("主菜单", "主菜单")),
    )


def render_home(data):
    pool, pity = data["pool"], data["pity"]
    output = f"##### ✨ {pool['name']}\n\n"
    output += f"仙玉：**{data['xianyu']}**｜单抽 {pool['single_cost']}｜十连 {pool['ten_cost']}\n"
    output += f"出战角色：**{data['role']['name']} Lv.{data['role']['level']}**｜角色图鉴 {data['owned']}/{data['roster_total']}\n"
    output += f"角色保底：**{pity['pity']}/{pool['pity_limit']}**（还需 {pool['pity_limit']-pity['pity']} 抽）\n\n"
    output += "> 每抽主奖励：药材30%｜丹药30%｜当前角色四星专属碎片25%｜五星专属碎片10%｜定向角色碎片5%。\n"
    output += "> 每抽另得当前角色升级所需经验的1/3与本源材料；80抽主奖励保底，固定奖励照常发放。\n\n"
    if data["full_roster"]:
        if pity["full_type"] == FULL_SPECIAL:
            choice = f"五星专属礼包-{data['full_role_name']}"
        elif pity["full_type"] == FULL_RESOURCE:
            choice = "高阶资源礼包"
        else:
            choice = "未设置"
        output += f"全图鉴保底选择：**{choice}**\n"
        output += f"> {_button('祈愿保底选择 高阶资源礼包', '高阶资源礼包')}"
        for role_name in data["owned_roles"]:
            output += f" | {_button('祈愿保底选择 五星专属礼包-' + role_name, '五星礼包-' + role_name)}"
        output += "\n\n"
    else:
        output += f"当前定向：**{data['target_name'] or '未设置'}**（切换定向不清空保底次数）\n"
        if data["unowned_roles"]:
            output += "> " + " | ".join(
                _button(f"祈愿定向 {name}", f"定向{name}") for name in data["unowned_roles"]
            ) + "\n\n"
    output += " | ".join((
        _button("仙玉祈愿 1次", "祈愿1次"), _button("仙玉祈愿 10次", "祈愿10次"),
        _button("角色碎片", "角色碎片"), _button("祈愿记录", "祈愿记录"),
    ))
    return _result(output, (
        {"command": "仙玉祈愿 1次", "label": "祈愿1次", "style": 1},
        {"command": "仙玉祈愿 10次", "label": "祈愿10次", "style": 1},
        ("角色碎片", "角色碎片"), ("祈愿记录", "祈愿记录"),
    ))


@reg_xz_func
async def character_wish_home(uid, qz):
    try:
        return render_home(await home(uid))
    except CharacterWishError as error:
        return _error(error)


@reg_xz_func
async def character_wish_draw(uid, qz, value, request_id=None):
    try:
        text = str(value or "").strip()
        count = 10 if text.startswith("10") else 1 if text.startswith("1") else 0
        result = await draw(uid, count, request_id=request_id)
        lines = [f"##### 🌠 {result['role_name']}｜{'十连' if count == 10 else '单抽'}祈愿", ""]
        for item in result["results"]:
            reward = item["reward"]
            prefix = "🎯 保底" if item["is_pity"] else f"第{item['index']}抽"
            if item["reward_type"] == "FULL_ROSTER_PACK" and reward.get("pill"):
                detail = f"{reward['name']}（{reward['pill']['name']}×{reward['pill']['amount']}、{reward['origin']['name']}×{reward['origin']['amount']}）"
            elif reward.get("detail"):
                detail = f"{reward['name']}：{reward['detail']}碎片×{reward['amount']}"
            else:
                detail = f"{reward.get('name', '奖励')} ×{reward.get('amount', 1)}"
            fixed_items = [f"经验+{item['role_exp']}"] if item["role_exp"] else []
            fixed_items.extend(f"{part['name']}+{part['amount']}" for part in item["fixed"] if part["type"] == "ORIGIN")
            lines.append(f"> {prefix}｜**{detail}**")
            lines.append(f"> 固定：{'、'.join(fixed_items)}｜保底 {item['pity_after']}/80")
        lines.extend(["", f"消耗仙玉：**{result['cost']}**｜余额：**{result['balance_after']}**｜当前保底：**{result['pity_after']}/80**", "",
                      f"{_button('仙玉祈愿 1次', '再祈愿1次')} | {_button('仙玉祈愿 10次', '再祈愿10次')} | {_button('角色碎片', '查看碎片')}"])
        return _result("\n".join(lines), (("仙玉祈愿 1次", "再抽1次"), ("仙玉祈愿 10次", "再抽10次"), ("角色碎片", "角色碎片"), ("仙玉祈愿", "祈愿首页")))
    except (ValueError, CharacterWishError) as error:
        return _error(error)


@reg_xz_func
async def character_wish_target(uid, qz, value):
    try:
        data = await set_target(uid, value)
        return _result(f"##### 🎯 定向设置成功\n\n已定向：**{data['role_name']}**\n当前保底：{data['pity']}/{data['pity_limit']}，切换定向未清空次数。\n\n{_button('仙玉祈愿', '返回祈愿')}", (("仙玉祈愿", "返回祈愿"),))
    except CharacterWishError as error:
        return _error(error)


@reg_xz_func
async def character_wish_full_choice(uid, qz, value):
    try:
        data = await set_full_choice(uid, value)
        return _result(f"##### 🎁 全图鉴保底已设置\n\n第80抽奖励：**{data['choice']}**\n\n{_button('仙玉祈愿', '返回祈愿')}", (("仙玉祈愿", "返回祈愿"),))
    except CharacterWishError as error:
        return _error(error)


@reg_xz_func
async def character_fragment_list(uid, qz):
    try:
        rows = await fragments(uid)
        lines = ["##### 🧩 角色碎片", "", "> 集齐同一角色10个碎片后，可手动合成该角色。", ""]
        for row in rows:
            state = "已拥有" if row["owned"] else f"{row['amount']}/10"
            line = f"**{row['role_name']}**｜{state}"
            if not row["owned"] and row["amount"] >= 10:
                line += f"｜{_button('合成角色 ' + row['role_name'], '合成' + row['role_name'])}"
            lines.append(line)
        lines.extend(["", f"{_button('仙玉祈愿', '返回祈愿')} | {_button('祈愿记录', '祈愿记录')}"])
        return _result("\n".join(lines), (("仙玉祈愿", "返回祈愿"), ("祈愿记录", "祈愿记录")))
    except CharacterWishError as error:
        return _error(error)


@reg_xz_func
async def character_compose(uid, qz, value, request_id=None):
    try:
        data = await compose(uid, value, request_id=request_id)
        return _result(
            f"##### 🎊 角色合成成功\n\n获得角色：**{data['role_name']}**（编号 {data['role_id']}）\n境界：{data['stage']}｜消耗碎片：{data['fragment_cost']}｜剩余：{data['fragment_balance']}\n\n{_button('出战 ' + str(data['role_id']), '让该角色出战')} | {_button('角色碎片', '角色碎片')}",
            ((f"出战 {data['role_id']}", "让TA出战"), ("角色碎片", "角色碎片"), ("仙玉祈愿", "祈愿首页")),
        )
    except CharacterWishError as error:
        return _error(error)


@reg_xz_func
async def character_wish_history(uid, qz):
    rows = await history(uid)
    lines = ["##### 📜 最近祈愿记录", ""]
    if not rows:
        lines.append("> 暂无祈愿记录。")
    for row in rows:
        rewards = []
        for item in row["result"].get("results", []):
            name = item.get("reward", {}).get("name", "奖励")
            rewards.append(name)
        summary = "、".join(f"{name}×{amount}" for name, amount in Counter(rewards).items())
        lines.append(f"> {row['created_at']}｜{row['count']}抽｜{summary}｜保底 {row['pity_before']}→{row['pity_after']}")
    lines.extend(["", f"{_button('仙玉祈愿', '返回祈愿')} | {_button('角色碎片', '角色碎片')}"])
    return _result("\n".join(lines), (("仙玉祈愿", "返回祈愿"), ("角色碎片", "角色碎片")))
