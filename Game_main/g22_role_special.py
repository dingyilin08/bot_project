# -*- coding: utf-8 -*-
"""P1 角色专属战斗养成：统一入口、图鉴、祈愿、装配、组合与排行。"""

from func.pd_func import reg_xz_func
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


def _stage_name(spec, stage_no):
    return next((item["name"] for item in spec["stages"] if item["stage"] == stage_no), f"阶段{stage_no}")


def _button(command, label=None):
    return f"<qqbot-cmd-input text='{command}' show='{label or command}' />"


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
    if not data["items"]:
        output += "> 尚未生成组合。请先选择三种已点亮能力进行组合。\n"
    for item in data["items"]:
        mode, codes = _combo_effect_label(item["effect"])
        status = "✅ 当前装备" if item["equipped"] else "未装备"
        output += f"**#{item['id']} {item['name']}**｜{item['combo_type']}｜倍率 {item['multiplier']:.1%}\n"
        output += f"> {status}｜{mode}\n> 规则：`{codes}`\n"
        if not item["equipped"]:
            equip_command = f"专属组合 装备-{item['id']}"
            output += f"> {_button(equip_command, '装备此组合')}\n"
        output += "\n"
    output += (
        "组合只作用于新创建的PVE战斗快照；主动组合沿用专属主动每场一次限制，"
        "被动组合每场触发一次。\n\n"
    )
    output += f"{_button('专属组合 ', '创建组合*')} | {_button('角色养成', '返回养成')}"
    return {"type": "markdown", "content": output}


def render_home(data):
    spec = data["spec"]
    codes = {
        "growth": spec.get("growth_material_code", f"ROLE_{spec['template_id']}_GROWTH"),
        "essence": spec.get("essence_material_code", f"ROLE_{spec['template_id']}_ESSENCE"),
        "core": spec.get("core_material_code", f"ROLE_{spec['template_id']}_CORE"),
    }
    materials = data["materials"]
    output = f"##### ⚔️ {data['role_name']}专属战斗养成｜{spec['growth_name']}\n\n"
    output += f"本体阶段：**{_stage_name(spec, data['growth_stage'])}**（第 {data['growth_stage']} 阶）\n"
    output += f"已点亮能力：{data['unlocked']}/{data['total']}｜今日战斗掉落：{data['daily_drop_count']}/{DAILY_DROP_LIMIT}\n"
    output += f"当前主动：**{data['active_skill']}**｜当前被动：**{data['active_passive']}**\n"
    combo = data.get("equipped_combo")
    if combo:
        combo_mode = "主动替换·每场一次" if combo["mode"] == "ACTIVE_OVERRIDE" else "被动替换·每场一次"
        output += f"当前组合：**{combo['name']}**（{combo_mode}）\n"
    else:
        output += "当前组合：**未装备**\n"
    output += f"五星保底：{data['rare_pity']}/10｜定向偏离：{data['target_miss']}/3｜今日祈愿：{data['daily_pray_count']}/{DAILY_PRAY_LIMIT}\n\n"
    output += f"> {spec['growth_material']}：{materials.get(codes['growth'], 0)}｜{spec['essence_name']}：{materials.get(codes['essence'], 0)}｜{spec['core_name']}：{materials.get(codes['core'], 0)}\n"
    for code, name in spec.get("extra_materials", {}).items():
        if code in codes.values():
            continue
        output += f"> {name}：{materials.get(code, 0)}\n"
    output += f"> {spec['passive_lore']}\n\n"
    if spec.get("featured_system"):
        output += f"> {spec['featured_system']}\n"
        output += f"> 当前机制：{data.get('feature', {}).get('feature_name', '未选择')}\n\n"
    output += "专属能力只在 PVE 生效；主动每场最多施放一次，不暴击、不触发五行连锁，世界 Boss 单次伤害不超过最大生命的 3%。\n\n"
    output += " | ".join([
        _button("专属图鉴", spec["drop_name"] + "图鉴"),
        _button("专属祈愿 1次", "祈愿1次"),
        _button("专属祈愿 10次", "祈愿10次"),
        _button("专属进阶", spec["growth_name"] + "进阶"),
        _button("专属组合 背包", "组合背包"),
        _button("专属排行榜", spec["rank"]["name"]),
    ])
    return {"type": "markdown", "content": output}


def render_collection(data, notice=""):
    spec = data["spec"]
    output = f"##### 📚 {data['role_name']}｜{spec['drop_name']}图鉴\n\n"
    if notice:
        output += f"> {notice}\n\n"
    for item in data["items"]:
        stars = "★" * item["rarity"]
        status = "未开放·待考据" if not item["enabled"] else "已点亮" if item["unlocked"] else f"残片 {item['fragments']}/{item['cost']}"
        slot = f"｜已装备{item['slot']}" if item["slot"] else ""
        kind = "未开放" if not item["enabled"] else "主动" if item["kind"] == "ACTIVE" else "被动"
        output += f"**#{item['id']} {item['name']}**｜{stars}｜{kind}｜倍率 {item['multiplier']:.0%}\n"
        output += f"> {status}{slot}｜{item['lore']}\n"
    output += "\n" + " | ".join([
        _button("点亮能力 ", "点亮能力*"),
        _button("装备专属 ", "装备专属*"),
        _button("专属定向 ", "五星定向*"),
        _button("角色养成", "返回养成"),
    ])
    return {"type": "markdown", "content": output}


def render_target_selection(data):
    candidates = [
        item for item in data["items"]
        if item["enabled"] and item["rarity"] == 5
    ]
    output = f"##### 🎯 {data['role_name']}｜五星能力定向\n\n"
    output += "> 请选择当前角色奖池中的五星能力；切换定向会将定向偏离计数重置为 0。\n\n"
    if not candidates:
        output += "> 当前角色暂无可定向的五星能力。\n\n"
    for item in candidates:
        output += f"**#{item['id']} {item['name']}**｜{'★' * item['rarity']}\n"
        output += f"> {item['lore']}\n"
        target_command = f"专属定向 {item['id']}"
        target_label = f"定向·{item['name']}"
        output += f"> {_button(target_command, target_label)}\n\n"
    output += _button("专属图鉴", "返回图鉴")
    return {"type": "markdown", "content": output}


@reg_xz_func
async def role_special_home(uid, qz):
    try:
        return render_home(await home(uid))
    except RoleSpecialError as error:
        return {"type": "markdown", "content": str(error)}


@reg_xz_func
async def role_special_collection(uid, qz):
    try:
        return render_collection(await collection(uid))
    except RoleSpecialError as error:
        return {"type": "markdown", "content": str(error)}


@reg_xz_func
async def role_special_pray(uid, qz, value):
    try:
        count = 10 if str(value).strip().startswith("10") else 1 if str(value).strip().startswith("1") else 0
        result = await pray(uid, count)
        lines = [f"##### ✨ {result['role_name']}专属祈愿", ""]
        for item in result["results"]:
            lines.append(f"> {'★' * item['rarity']} {item['name']}残片 +{item['amount']}（现有 {item['balance']}）")
        lines.extend(["", f"消耗灵石：{result['cost']}｜五星保底：{result['rare_pity']}/10｜定向偏离：{result['target_miss']}/3",
                      f"今日祈愿：{result['daily_count']}/{DAILY_PRAY_LIMIT}", "",
                      f"{_button('专属图鉴', '查看图鉴')} | {_button('角色养成', '返回养成')}"])
        return {"type": "markdown", "content": "\n".join(lines)}
    except RoleSpecialError as error:
        return {"type": "markdown", "content": f"专属祈愿未生效：{error}\n{_button('角色养成', '返回养成')}"}


@reg_xz_func
async def role_special_target(uid, qz, value):
    try:
        target_text = str(value or "").strip()
        if not target_text:
            return render_target_selection(await collection(uid))
        if not target_text.isdecimal():
            raise RoleSpecialError("格式：专属定向 五星能力编号。")
        message = await set_target(uid, int(target_text))
        return {"type": "markdown", "content": f"{message}\n{_button('角色养成', '返回养成')}"}
    except ValueError:
        return {"type": "markdown", "content": "定向设置失败：请输入有效的五星能力编号。"}
    except RoleSpecialError as error:
        return {"type": "markdown", "content": f"定向设置失败：{error}"}


@reg_xz_func
async def role_special_unlock(uid, qz, value):
    try:
        message = await unlock(uid, int(value))
        return render_collection(await collection(uid), message)
    except (ValueError, RoleSpecialError) as error:
        return {"type": "markdown", "content": f"点亮失败：{error or '请输入能力编号。'}\n{_button('专属图鉴', '返回图鉴')}"}


@reg_xz_func
async def role_special_equip(uid, qz, value):
    try:
        message = await equip(uid, int(value))
        data = await home(uid)
        result = render_home(data)
        result["content"] = f"> {message}\n\n" + result["content"]
        return result
    except (ValueError, RoleSpecialError) as error:
        return {"type": "markdown", "content": f"装备失败：{error or '请输入能力编号。'}\n{_button('专属图鉴', '返回图鉴')}"}


@reg_xz_func
async def role_special_advance(uid, qz):
    try:
        message = await advance(uid)
        result = render_home(await home(uid))
        result["content"] = f"> {message}\n\n" + result["content"]
        return result
    except RoleSpecialError as error:
        return {"type": "markdown", "content": f"专属进阶失败：{error}\n{_button('角色养成', '返回养成')}"}


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
        output += f"素材：{'、'.join(result['materials'])}\n最终倍率：**{result['multiplier']:.1%}**\n"
        output += f"继承特性来源：{result['effect'].get('inherited_from', '未知')}\n组合编号：#{result['id']}\n\n"
        equip_button = _button(f"专属组合 装备-{result['id']}", "立即装备")
        output += (
            f"{equip_button} | "
            f"{_button('专属组合 背包', '组合背包')} | {_button('专属排行榜', '查看排行')}"
        )
        return {"type": "markdown", "content": output}
    except (ValueError, RoleSpecialError) as error:
        return {"type": "markdown", "content": f"专属组合失败：{error}"}


@reg_xz_func
async def role_special_rank(uid, qz):
    try:
        data = await rank(uid)
        spec = data["spec"]
        output = f"##### 🏆 {data['role_name']}｜{spec['rank']['name']}\n\n"
        if data["rows"]:
            for index, row in enumerate(data["rows"], 1):
                effect = row[3] if isinstance(row[3], dict) else {}
                output += f"> {index}. {row[1]}｜{float(row[2]):.1%}｜{row[0]}｜继承 {effect.get('inherited_from', '专属特性')}\n"
        else:
            output += "> 尚无已生成的组合能力。\n"
        output += "\n排行榜只授予称号与外观展示，不产生永久属性优势。\n"
        output += _button("角色养成", "返回养成")
        return {"type": "markdown", "content": output}
    except RoleSpecialError as error:
        return {"type": "markdown", "content": str(error)}


@reg_xz_func
async def role_special_feature(uid, qz, value):
    try:
        message = await select_feature(uid, int(value))
        result = render_home(await home(uid))
        result["content"] = f"> {message}\n\n" + result["content"]
        return result
    except (ValueError, RoleSpecialError) as error:
        return {"type": "markdown", "content": f"机制选择失败：{error or '请输入机制编号。'}"}


@reg_xz_func
async def role_special_draw_scroll(uid, qz, value):
    try:
        result = await create_scroll(uid, value)
        output = f"##### 🎨 战斗绘卷｜{result['quality']}\n\n"
        output += f"绘卷编号：#{result['id']}｜battle_id：{result['battle_id']}\n"
        output += f"记录回合：{result['detail']['rounds']}｜Boss破局：{result['detail']['broken_stages']}\n\n"
        output += f"{_button('刀势推演 ', '刀势推演*')} | {_button('战斗绘卷', '绘卷收藏')}"
        return {"type": "markdown", "content": output}
    except RoleSpecialError as error:
        return {"type": "markdown", "content": f"绘卷生成失败：{error}"}


@reg_xz_func
async def role_special_scrolls(uid, qz):
    try:
        rows = await list_scrolls(uid)
        output = "##### 🖼️ 孟川战斗绘卷\n\n"
        if rows:
            for item in rows:
                output += f"> #{item['id']}｜{item['quality']}｜{item['status']}｜破局 {item['detail'].get('broken_stages', 0)}\n"
        else:
            output += "> 尚无绘卷，请先使用孟川完成PVE战斗。\n"
        output += "\n" + _button("绘制绘卷 ", "绘制绘卷*")
        return {"type": "markdown", "content": output}
    except RoleSpecialError as error:
        return {"type": "markdown", "content": str(error)}


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
        output += f"绘卷：#{scroll_id}｜素材：{'、'.join(result['materials'])}\n最终倍率：{result['multiplier']:.1%}\n"
        output += f"观察/起刀/收刀的继承来源：{result['effect'].get('inherited_from', '刀势')}\n\n"
        equip_button = _button(f"专属组合 装备-{result['id']}", "立即装备")
        output += (
            f"{equip_button} | "
            f"{_button('专属组合 背包', '组合背包')} | {_button('专属排行榜', '刀道排行')}"
        )
        return {"type": "markdown", "content": output}
    except (ValueError, RoleSpecialError) as error:
        return {"type": "markdown", "content": f"刀势推演失败：{error}"}
