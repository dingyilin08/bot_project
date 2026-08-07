# -*- coding: utf-8 -*-
"""P1 角色专属战斗养成：统一入口、图鉴、祈愿、装配、组合与排行。"""

from func.pd_func import reg_xz_func
from Tool.tool_command import pagination_controls
from Game_domain.role_special_service import (
    DAILY_DROP_LIMIT,
    DAILY_PRAY_LIMIT,
    RoleSpecialError,
    advance,
    collection,
    combine,
    create_scroll,
    equip,
    equip_combo,
    home,
    list_combos,
    pray,
    rank,
    list_scrolls,
    set_target,
    select_feature,
    unlock,
)


COLLECTION_PAGE_SIZE = 4


def _stage_name(spec, stage_no):
    return next((item["name"] for item in spec["stages"] if item["stage"] == stage_no), f"阶段{stage_no}")


def _button(command, label=None):
    return f"<qqbot-cmd-input text='{command}' show='{label or command}' />"


def _actions(*items):
    """以统一的三栏操作区呈现专属养成的下一步入口。"""
    return "\n".join(
        " | ".join(_button(command, label) for command, label in items[index:index + 3])
        for index in range(0, len(items), 3)
    )


def _error_panel(title, error, *actions):
    output = f"##### ⚠️ {title}\n\n> {error}\n\n***\n"
    return {"type": "markdown", "content": output + _actions(*actions)}


def render_special_overview():
    """面向所有角色的专属养成总览，不依赖玩家当前进度。"""
    output = "##### ⚔️ 专属战斗养成｜玩法介绍\n\n"
    output += "**它有什么用？**\n"
    output += "> 为当前出战角色解锁专属主动、被动和成长路线，补足 PVE 中的爆发、减伤、控制或续航能力。\n"
    output += "> 不同角色拥有独立的材料、图鉴、进阶与组合规则；切换出战角色后，页面会自动切换为对应体系。\n\n"
    output += "**推荐流程**\n"
    output += "> ① 参与单人副本或世界 Boss 获得资源 → ② 专属祈愿积累能力碎片 → ③ 图鉴点亮并装备能力 → ④ 消耗成长材料进阶 → ⑤ 满足条件后创建专属组合。\n\n"
    output += "**功能说明**\n"
    output += "> **角色养成**：查看当前阶段、已装备能力、材料库存和祈愿状态。\n"
    output += "> **专属图鉴**：查看所有能力、碎片进度；点亮后用编号装备主动或被动。\n"
    output += "> **专属祈愿 / 五星定向**：获取能力碎片，并为五星能力设置优先目标。\n"
    output += "> **专属进阶**：消耗角色专属材料提升成长阶段，解锁更高阶的组合能力。\n"
    output += "> **专属组合 / 排行榜**：由三项已点亮能力创建组合；组合只作用于之后新建的 PVE 战斗。\n\n"
    output += "**战斗规则**\n"
    output += "> 专属能力仅在 PVE 生效；主动能力每场最多施放一次，不触发暴击或五行连锁。世界 Boss 的单次专属伤害最多为其生命上限的 3%。\n\n"
    output += "***\n"
    output += _actions(
        ("角色养成", "查看当前养成"),
        ("专属图鉴", "查看专属图鉴"),
        ("专属养成菜单", "功能菜单"),
    )
    return {"type": "markdown", "content": output}


def _parse_combo_action(value):
    text = str(value or "").strip()
    if text in ("", "背包", "列表", "查看"):
        return "LIST", None
    if text.startswith("装备"):
        combo_id = text[2:].lstrip(" -—:：")
        if not combo_id:
            raise RoleSpecialError("格式：专属组合 装备-组合编号")
        return "EQUIP", int(combo_id)
    return "CREATE", text


def _combo_effect_label(effect):
    effect = effect if isinstance(effect, dict) else {}
    mode = "专属主动替换·每场一次" if effect.get("mode") == "ACTIVE_OVERRIDE" else "专属被动替换·每场一次"
    codes = " / ".join(effect.get("effect_codes") or [effect.get("effect_code", "COMBO_ACTIVE_STRIKE")])
    return mode, codes


def render_combo_bag(data, notice=""):
    output = f"##### 🔥 {data['role_name']}｜专属组合背包\n\n"
    if notice:
        output += f"> {notice}\n\n"
    output += "**组合说明**\n"
    output += "> 选择三项已点亮能力创建组合；装备后仅对之后新创建的 PVE 战斗生效。\n\n"
    if not data["items"]:
        output += "> 暂无组合。请先使用「创建组合」并输入三项能力编号。\n\n"
    for item in data["items"]:
        mode, codes = _combo_effect_label(item["effect"])
        status = "✅ 当前装备" if item["equipped"] else "未装备"
        output += f"**#{item['id']}｜{item['name']}**｜{item['combo_type']}\n"
        output += f"> {status}｜最终倍率 **{item['multiplier']:.1%}**\n"
        output += f"> {mode}｜规则：`{codes}`\n"
        if not item["equipped"]:
            equip_command = f"专属组合 装备-{item['id']}"
            output += f"> {_button(equip_command, '装备此组合')}\n"
        output += "\n"
    output += "***\n"
    output += _actions(
        ("专属组合 ", "创建组合*"),
        ("专属图鉴", "查看能力编号"),
        ("角色养成", "返回养成"),
    )
    return {"type": "markdown", "content": output}


def render_home(data):
    spec = data["spec"]
    codes = {
        "growth": spec.get("growth_material_code", f"ROLE_{spec['template_id']}_GROWTH"),
        "essence": spec.get("essence_material_code", f"ROLE_{spec['template_id']}_ESSENCE"),
        "core": spec.get("core_material_code", f"ROLE_{spec['template_id']}_CORE"),
    }
    materials = data["materials"]
    output = f"##### ⚔️ {data['role_name']}｜专属战斗养成\n\n"
    output += "**当前进度**\n"
    output += f"> 成长阶段：**{_stage_name(spec, data['growth_stage'])}**（第 {data['growth_stage']} 阶）\n"
    output += f"> 能力点亮：**{data['unlocked']}/{data['total']}**｜今日战斗掉落：{data['daily_drop_count']}/{DAILY_DROP_LIMIT}\n"
    output += f"> 当前主动：**{data['active_skill']}**｜当前被动：**{data['active_passive']}**\n"
    combo = data.get("equipped_combo")
    if combo:
        combo_mode = "主动替换·每场一次" if combo["mode"] == "ACTIVE_OVERRIDE" else "被动替换·每场一次"
        output += f"> 当前组合：**{combo['name']}**（{combo_mode}）\n"
    else:
        output += "> 当前组合：**未装备**\n"
    output += f"> 五星保底：{data['rare_pity']}/10｜定向偏离：{data['target_miss']}/3｜今日祈愿：{data['daily_pray_count']}/{DAILY_PRAY_LIMIT}\n\n"
    output += "**养成材料**\n"
    output += f"> {spec['growth_material']}：**{materials.get(codes['growth'], 0)}**｜{spec['essence_name']}：**{materials.get(codes['essence'], 0)}**｜{spec['core_name']}：**{materials.get(codes['core'], 0)}**\n"
    for code, name in spec.get("extra_materials", {}).items():
        if code in codes.values():
            continue
        output += f"> {name}：{materials.get(code, 0)}\n"
    output += f"> 角色特性：{spec['passive_lore']}\n\n"
    if spec.get("featured_system"):
        output += "**角色机制**\n"
        output += f"> {spec['featured_system']}\n"
        output += f"> 当前选择：**{data.get('feature', {}).get('feature_name', '未选择')}**\n\n"
    output += "**下一步**\n"
    output += "> 先查看图鉴确认碎片与装备，再通过祈愿补齐能力；材料充足时可尝试进阶。\n\n"
    output += "***\n"
    output += _actions(
        ("专属图鉴", spec["drop_name"] + "图鉴"),
        ("专属祈愿 1次", "祈愿1次"),
        ("专属祈愿 10次", "祈愿10次"),
        ("专属进阶", spec["growth_name"] + "进阶"),
        ("专属组合 背包", "组合背包"),
        ("专属排行榜", spec["rank"]["name"]),
        ("专属养成介绍", "玩法介绍"),
        ("专属养成菜单", "功能菜单"),
    )
    return {"type": "markdown", "content": output}


def _collection_page(value):
    """将图鉴页码限制在可用范围内；空参数默认展示第一页。"""
    try:
        return max(1, int(str(value or "").strip() or 1))
    except ValueError:
        return 1


def _collection_status(item):
    if not item["enabled"]:
        return "⏳ 暂未开放"
    if item["unlocked"]:
        return "✅ 已点亮"
    return f"碎片 {item['fragments']}/{item['cost']}"


def render_collection(data, notice="", page=1):
    spec = data["spec"]
    enabled_items = [item for item in data["items"] if item["enabled"]]
    unlocked_count = sum(1 for item in enabled_items if item["unlocked"])
    total_items = len(enabled_items)
    total_pages = max(1, (len(data["items"]) + COLLECTION_PAGE_SIZE - 1) // COLLECTION_PAGE_SIZE)
    page = min(max(1, int(page)), total_pages)
    start = (page - 1) * COLLECTION_PAGE_SIZE
    page_items = data["items"][start:start + COLLECTION_PAGE_SIZE]

    output = f"##### 📚 {data['role_name']}｜{spec['drop_name']}图鉴\n\n"
    if notice:
        output += f"> {notice}\n\n"

    output += "**收集进度**\n"
    output += f"> 已点亮：**{unlocked_count}/{total_items}**｜当前：第 **{page}/{total_pages}** 页\n"
    output += "> 点亮能力后，可发送「装备专属 能力编号」分别装备主动或被动能力。\n\n"
    output += "**能力列表**\n"

    if not page_items:
        output += "> 当前没有可展示的专属能力。\n\n"
    for item in page_items:
        stars = "★" * item["rarity"]
        status = _collection_status(item)
        slot = ""
        if item["slot"]:
            slot_name = "主动槽" if item["slot"] == "ACTIVE" else "被动槽"
            slot = f"｜装备：{slot_name}"
        kind = "未开放" if not item["enabled"] else "主动" if item["kind"] == "ACTIVE" else "被动"
        output += f"**#{item['id']}｜{item['name']}**｜{stars}\n"
        output += f"> {kind}｜倍率 **{item['multiplier']:.0%}**｜{status}{slot}\n"
        output += f"> {item['lore']}\n\n"

    output += "***\n"
    output += pagination_controls("专属图鉴", page, total_pages) + "\n\n"
    output += _actions(
        ("点亮能力 ", "点亮能力*"),
        ("装备专属 ", "装备专属*"),
        ("专属定向", "五星定向"),
        ("角色养成", "返回养成"),
    )
    return {"type": "markdown", "content": output}


def render_target_selection(data):
    candidates = [
        item for item in data["items"]
        if item["enabled"] and item["rarity"] == 5
    ]
    output = f"##### 🎯 {data['role_name']}｜五星能力定向\n\n"
    output += "**定向说明**\n"
    output += "> 选择后，专属祈愿会优先朝该五星能力靠拢；每次切换会将定向偏离计数重置为 0。\n\n"
    if not candidates:
        output += "> 当前角色没有可定向的五星能力。请先查看图鉴或进行专属祈愿。\n\n"
    else:
        output += "**可定向能力**\n"
    for item in candidates:
        output += f"**#{item['id']}｜{item['name']}**｜{'★' * item['rarity']}\n"
        output += f"> {item['lore']}\n"
        target_command = f"专属定向 {item['id']}"
        target_label = f"定向·{item['name']}"
        output += f"> {_button(target_command, target_label)}\n\n"
    output += "***\n"
    output += _actions(("专属图鉴", "返回图鉴"), ("角色养成", "返回养成"))
    return {"type": "markdown", "content": output}


@reg_xz_func
async def role_special_home(uid, qz):
    try:
        return render_home(await home(uid))
    except RoleSpecialError as error:
        return _error_panel("专属养成暂不可用", error, ("专属养成菜单", "功能菜单"))


@reg_xz_func
async def role_special_overview(uid, qz):
    return render_special_overview()


@reg_xz_func
async def role_special_collection(uid, qz, value=""):
    try:
        return render_collection(await collection(uid), page=_collection_page(value))
    except RoleSpecialError as error:
        return _error_panel("专属图鉴暂不可用", error, ("角色养成", "返回养成"), ("专属养成菜单", "功能菜单"))


@reg_xz_func
async def role_special_pray(uid, qz, value):
    try:
        count = 10 if str(value).strip().startswith("10") else 1 if str(value).strip().startswith("1") else 0
        result = await pray(uid, count)
        lines = [f"##### ✨ {result['role_name']}｜专属祈愿结果", "", "**本次收获**"]
        for item in result["results"]:
            lines.append(f"> {'★' * item['rarity']} **{item['name']}** 碎片 +{item['amount']}（现有 {item['balance']}）")
        lines.extend(["", "**祈愿状态**",
                      f"> 消耗灵石：**{result['cost']}**｜五星保底：{result['rare_pity']}/10｜定向偏离：{result['target_miss']}/3",
                      f"> 今日祈愿：{result['daily_count']}/{DAILY_PRAY_LIMIT}", "", "***",
                      _actions(("专属图鉴", "查看图鉴"), ("专属定向", "五星定向"), ("角色养成", "返回养成"))])
        return {"type": "markdown", "content": "\n".join(lines)}
    except RoleSpecialError as error:
        return _error_panel("专属祈愿未生效", error, ("角色养成", "返回养成"), ("专属图鉴", "查看图鉴"))


@reg_xz_func
async def role_special_target(uid, qz, value):
    try:
        target_text = str(value or "").strip()
        if not target_text:
            return render_target_selection(await collection(uid))
        if not target_text.isdecimal():
            raise RoleSpecialError("格式：专属定向 五星能力编号。")
        message = await set_target(uid, int(target_text))
        output = f"##### 🎯 五星定向已更新\n\n> {message}\n\n***\n"
        return {"type": "markdown", "content": output + _actions(("专属祈愿 1次", "祈愿1次"), ("专属图鉴", "查看图鉴"), ("角色养成", "返回养成"))}
    except ValueError:
        return _error_panel("定向设置失败", "请输入有效的五星能力编号。", ("专属定向", "返回定向列表"))
    except RoleSpecialError as error:
        return _error_panel("定向设置失败", error, ("专属定向", "返回定向列表"), ("专属图鉴", "查看图鉴"))


@reg_xz_func
async def role_special_unlock(uid, qz, value):
    try:
        message = await unlock(uid, int(value))
        return render_collection(await collection(uid), message)
    except (ValueError, RoleSpecialError) as error:
        return _error_panel("能力点亮失败", error or "请输入能力编号。", ("专属图鉴", "返回图鉴"))


@reg_xz_func
async def role_special_equip(uid, qz, value):
    try:
        message = await equip(uid, int(value))
        data = await home(uid)
        result = render_home(data)
        result["content"] = f"> {message}\n\n" + result["content"]
        return result
    except (ValueError, RoleSpecialError) as error:
        return _error_panel("专属能力装备失败", error or "请输入能力编号。", ("专属图鉴", "返回图鉴"))


@reg_xz_func
async def role_special_advance(uid, qz):
    try:
        message = await advance(uid)
        result = render_home(await home(uid))
        result["content"] = f"> {message}\n\n" + result["content"]
        return result
    except RoleSpecialError as error:
        return _error_panel("专属进阶失败", error, ("角色养成", "查看材料"), ("专属图鉴", "查看能力"))


@reg_xz_func
async def role_special_combine(uid, qz, value):
    try:
        action, payload = _parse_combo_action(value)
        if action == "LIST":
            return render_combo_bag(await list_combos(uid))
        if action == "EQUIP":
            equipped = await equip_combo(uid, payload)
            notice = (
                f"「{equipped['name']}」已经是当前装备，未重复写入。"
                if equipped["idempotent"]
                else f"已装备「{equipped['name']}」，新创建的PVE战斗将使用该组合。"
            )
            return render_combo_bag(await list_combos(uid), notice)
        parts = [item for item in payload.split("-") if item]
        if len(parts) < 4:
            raise RoleSpecialError("格式：专属组合 能力1-能力2-能力3-组合名称")
        result = await combine(uid, [int(item) for item in parts[:3]], "-".join(parts[3:]))
        output = f"##### 🔥 专属组合完成｜{result['name']}\n\n"
        output += "**组合结果**\n"
        output += f"> 组合编号：**#{result['id']}**｜最终倍率：**{result['multiplier']:.1%}**\n"
        output += f"> 使用素材：{'、'.join(result['materials'])}\n"
        output += f"> 继承特性：{result['effect'].get('inherited_from', '未知')}\n\n"
        output += "**下一步**\n> 装备后，新的 PVE 战斗将使用该组合；已创建的战斗不会改变。\n\n***\n"
        equip_button = _button(f"专属组合 装备-{result['id']}", "立即装备")
        output += f"{equip_button} | {_button('专属组合 背包', '组合背包')} | {_button('专属排行榜', '查看排行')}"
        return {"type": "markdown", "content": output}
    except (ValueError, RoleSpecialError) as error:
        return _error_panel("专属组合失败", error, ("专属图鉴", "查看能力编号"), ("专属组合 背包", "组合背包"))


@reg_xz_func
async def role_special_rank(uid, qz):
    try:
        data = await rank(uid)
        spec = data["spec"]
        output = f"##### 🏆 {data['role_name']}｜{spec['rank']['name']}\n\n"
        if data["rows"]:
            output += "**组合排行**\n"
            for index, row in enumerate(data["rows"], 1):
                effect = row[3] if isinstance(row[3], dict) else {}
                output += f"> **{index}. {row[1]}**｜倍率 {float(row[2]):.1%}｜{row[0]}｜继承 {effect.get('inherited_from', '专属特性')}\n"
        else:
            output += "> 暂无已生成的组合能力。\n"
        output += "\n**排行说明**\n> 排行榜仅授予称号与外观展示，不提供永久属性优势。\n\n***\n"
        output += _actions(("专属组合 背包", "查看组合"), ("角色养成", "返回养成"))
        return {"type": "markdown", "content": output}
    except RoleSpecialError as error:
        return _error_panel("专属排行榜暂不可用", error, ("角色养成", "返回养成"))


@reg_xz_func
async def role_special_feature(uid, qz, value):
    try:
        message = await select_feature(uid, int(value))
        result = render_home(await home(uid))
        result["content"] = f"> {message}\n\n" + result["content"]
        return result
    except (ValueError, RoleSpecialError) as error:
        return _error_panel("角色机制选择失败", error or "请输入机制编号。", ("角色养成", "返回养成"))


@reg_xz_func
async def role_special_draw_scroll(uid, qz, value):
    try:
        result = await create_scroll(uid, value)
        output = f"##### 🎨 战斗绘卷｜{result['quality']}\n\n"
        output += "**绘卷信息**\n"
        output += f"> 绘卷编号：**#{result['id']}**｜战斗编号：{result['battle_id']}\n"
        output += f"> 记录回合：{result['detail']['rounds']}｜Boss 破局：{result['detail']['broken_stages']}\n\n"
        output += "**下一步**\n> 孟川可使用此绘卷作为刀势推演的依据。\n\n***\n"
        output += _actions(("刀势推演 ", "刀势推演*"), ("战斗绘卷", "绘卷收藏"), ("角色养成", "返回养成"))
        return {"type": "markdown", "content": output}
    except RoleSpecialError as error:
        return _error_panel("绘卷生成失败", error, ("战斗绘卷", "绘卷收藏"), ("角色养成", "返回养成"))


@reg_xz_func
async def role_special_scrolls(uid, qz):
    try:
        rows = await list_scrolls(uid)
        output = "##### 🖼️ 孟川战斗绘卷\n\n"
        if rows:
            output += "**可用绘卷**\n"
            for item in rows:
                output += f"> **#{item['id']}**｜{item['quality']}｜{item['status']}｜破局 {item['detail'].get('broken_stages', 0)}\n"
        else:
            output += "> 暂无绘卷。请先使用孟川完成 PVE 战斗，再输入「绘制绘卷 战斗编号」。\n"
        output += "\n***\n"
        output += _actions(("绘制绘卷 ", "绘制绘卷*"), ("角色养成", "返回养成"))
        return {"type": "markdown", "content": output}
    except RoleSpecialError as error:
        return _error_panel("战斗绘卷暂不可用", error, ("角色养成", "返回养成"))


@reg_xz_func
async def role_special_scroll_combine(uid, qz, value):
    try:
        parts = [item for item in str(value).split("-") if item]
        if len(parts) < 4:
            raise RoleSpecialError("格式：刀势推演 绘卷编号-能力1-能力2-能力3-名称")
        scroll_id = int(parts[0])
        name = "-".join(parts[4:]) if len(parts) > 4 else f"刀势{scroll_id}"
        result = await combine(uid, [int(item) for item in parts[1:4]], name, scroll_id=scroll_id)
        output = f"##### 🗡️ 刀势推演完成｜{result['name']}\n\n"
        output += "**推演结果**\n"
        output += f"> 使用绘卷：**#{scroll_id}**｜组合编号：**#{result['id']}**\n"
        output += f"> 最终倍率：**{result['multiplier']:.1%}**｜素材：{'、'.join(result['materials'])}\n"
        output += f"> 观察 / 起刀 / 收刀继承：{result['effect'].get('inherited_from', '刀势')}\n\n***\n"
        equip_button = _button(f"专属组合 装备-{result['id']}", "立即装备")
        output += (
            f"{equip_button} | "
            f"{_button('专属组合 背包', '组合背包')} | {_button('专属排行榜', '刀道排行')}"
        )
        return {"type": "markdown", "content": output}
    except (ValueError, RoleSpecialError) as error:
        return _error_panel("刀势推演失败", error, ("战斗绘卷", "绘卷收藏"), ("专属图鉴", "查看能力编号"))
