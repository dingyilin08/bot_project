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
    equip,
    home,
    pray,
    rank,
    set_target,
    select_feature,
    unlock,
)


def _stage_name(spec, stage_no):
    return next((item["name"] for item in spec["stages"] if item["stage"] == stage_no), f"阶段{stage_no}")


def _button(command, label=None):
    return f"<qqbot-cmd-input text='{command}' show='{label or command}' />"


def render_home(data):
    spec = data["spec"]
    codes = {
        "growth": f"ROLE_{spec['template_id']}_GROWTH",
        "essence": f"ROLE_{spec['template_id']}_ESSENCE",
        "core": f"ROLE_{spec['template_id']}_CORE",
    }
    materials = data["materials"]
    output = f"##### ⚔️ {data['role_name']}专属战斗养成｜{spec['growth_name']}\n\n"
    output += f"本体阶段：**{_stage_name(spec, data['growth_stage'])}**（第 {data['growth_stage']} 阶）\n"
    output += f"已点亮能力：{data['unlocked']}/{data['total']}｜今日战斗掉落：{data['daily_drop_count']}/{DAILY_DROP_LIMIT}\n"
    output += f"当前主动：**{data['active_skill']}**｜当前被动：**{data['active_passive']}**\n"
    output += f"五星保底：{data['rare_pity']}/10｜定向偏离：{data['target_miss']}/3｜今日祈愿：{data['daily_pray_count']}/{DAILY_PRAY_LIMIT}\n\n"
    output += f"> {spec['growth_material']}：{materials.get(codes['growth'], 0)}｜{spec['essence_name']}：{materials.get(codes['essence'], 0)}｜{spec['core_name']}：{materials.get(codes['core'], 0)}\n"
    for code, name in spec.get("extra_materials", {}).items():
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
        message = await set_target(uid, int(value))
        return {"type": "markdown", "content": f"{message}\n{_button('角色养成', '返回养成')}"}
    except (ValueError, RoleSpecialError) as error:
        return {"type": "markdown", "content": f"定向设置失败：{error or '请输入五星能力编号。'}"}


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
        parts = [item for item in str(value).split("-") if item]
        if len(parts) < 4:
            raise RoleSpecialError("格式：专属组合 能力1-能力2-能力3-组合名称")
        result = await combine(uid, [int(item) for item in parts[:3]], "-".join(parts[3:]))
        output = f"##### 🔥 专属组合完成｜{result['name']}\n\n"
        output += f"素材：{'、'.join(result['materials'])}\n最终倍率：**{result['multiplier']:.1%}**\n"
        output += f"继承特性来源：{result['effect'].get('inherited_from', '未知')}\n组合编号：#{result['id']}\n\n"
        output += f"{_button('角色养成', '返回养成')} | {_button('专属排行榜', '查看排行')}"
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
