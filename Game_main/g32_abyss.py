# -*- coding: utf-8 -*-
"""轮海深渊玩家交互层。"""

from html import escape

from func.pd_func import reg_xz_func
from Game_domain.abyss_rules import (
    ABYSS_MAX_KILLS,
    abyss_monster_multiplier,
    abyss_rating,
    calculate_abyss_layer_reward,
    placement_target,
)
from Game_domain.abyss_service import (
    AbyssError,
    abandon_run,
    create_preview,
    get_active_run,
    get_dashboard,
    get_leaderboard,
    get_run_monsters,
    get_source_dungeon,
    get_world_role_names,
    recover_finished_battle,
    settle_finished_battle,
    settle_run,
    start_monster_battle,
    start_run,
)
from Game_domain.reward_service import required_exp


def _button(command, label):
    return (
        f"<qqbot-cmd-input text='{escape(str(command), quote=True)}' "
        f"show='{escape(str(label), quote=True)}' />"
    )


def _result(content, commands=()):
    return {
        "type": "markdown",
        "content": content,
        "keyboard_commands": [
            {
                "command": command,
                "label": label,
                "complete": complete,
                "style": style,
            }
            for command, label, complete, style in commands
        ],
    }


def _error(message, commands=None):
    commands = commands or (
        ("深渊", "返回深渊", True, 1),
        ("战斗状态", "战斗状态", True, 1),
        ("角色背包", "角色背包", True, 1),
    )
    links = " | ".join(_button(item[0], item[1]) for item in commands)
    return _result(f"##### ⚠️ 深渊未响应\n\n> {escape(str(message))}\n\n{links}", commands)


def _stars(value):
    value = max(0, min(3, int(value or 0)))
    return "★" * value + "☆" * (3 - value)


def _status_label(state):
    return {
        "READY": "等待开战",
        "FIGHTING": "挑战中",
        "QUALIFIED": "可结算",
        "SETTLING": "结算中",
    }.get(state, state)


async def _render_home(uid, notice=""):
    data = await get_dashboard(uid)
    profile, role, run = data["profile"], data["role"], data["run"]
    lines = [
        "##### 🌊 轮海深渊",
        "",
        "> 六波连战，每层30敌。击杀10/20/30只可得1/2/3星；跨界挑战时怪物全属性+20%。",
        "",
        f"**最高通关：** 第{profile['highest_cleared_layer']}层｜**累计击杀：** {profile['total_kills']}",
    ]
    if role:
        lines.append(f"**当前角色：** {escape(role['name'])} Lv.{role['level']}〔{escape(role['world'])}〕")
    else:
        lines.append("**当前角色：** 尚未出战")
    if notice:
        lines.extend(("", f"> {notice}"))

    commands = []
    if run:
        lines.extend((
            "",
            "***",
            f"**进行中：** 第{run['layer_no']}层｜{_status_label(run['state'])}",
            f"> 第{run['wave_no']}/6波｜击杀 {run['kill_count']}/{ABYSS_MAX_KILLS}｜{_stars(abyss_rating(run['kill_count']))}",
        ))
        if run["state"] == "READY":
            command = "深渊定级 开始" if run["run_type"] == "PLACEMENT" else f"挑战深渊 {run['layer_no']}"
            commands.append((command, "正式开战", True, 2))
            lines.append("\n" + _button(command, "正式开战") + " | " + _button("深渊预览", "重新预览"))
        elif run["state"] in ("FIGHTING", "QUALIFIED"):
            commands.append(("深渊怪物", "当前波次", True, 1))
            lines.append("\n" + _button("深渊怪物", "查看当前波") + " | " + _button("战斗状态", "战斗状态"))
            if abyss_rating(run["kill_count"]) > 0:
                commands.append(("深渊结算", f"{abyss_rating(run['kill_count'])}星结算", True, 2))
                lines.append("\n" + _button("深渊结算", f"按{abyss_rating(run['kill_count'])}星结算"))
    else:
        next_layer = profile["highest_cleared_layer"] + 1
        lines.extend(("", "***", f"**下一目标：** 第{next_layer}层"))
        commands.extend((
            (f"深渊预览 {next_layer}", "预览下一层", True, 1),
            (f"挑战深渊 {next_layer}", "直接挑战", True, 2),
        ))
        lines.append("\n" + _button(f"深渊预览 {next_layer}", "预览下一层") + " | " + _button(f"挑战深渊 {next_layer}", "直接挑战"))

    commands.extend((
        ("深渊定级", "深渊定级", True, 1),
        ("深渊排行", "深渊排行", True, 1),
        ("活动菜单", "活动菜单", True, 1),
    ))
    lines.extend((
        "",
        _button("深渊定级", "定级赛") + " | " + _button("深渊排行", "深渊排行") + " | " + _button("活动菜单", "活动菜单"),
    ))
    return _result("\n".join(lines), commands)


async def _render_preview(uid, run):
    dashboard = await get_dashboard(uid)
    role = dashboard["role"]
    dungeon = await get_source_dungeon(run["source_dungeon_id"])
    same_world_roles = await get_world_role_names(run["source_world"])
    cross = bool(role and role["world"] != run["source_world"])
    req = required_exp(role["level"]) if role else 0
    rewards = {
        star: calculate_abyss_layer_reward(req, run["layer_no"], star)
        for star in (1, 2, 3)
    }
    lines = [
        f"##### 🔭 深渊预览｜第{run['layer_no']}层",
        "",
        f"**世界：**《{escape(run['source_world'])}》｜**源境：** {escape(dungeon['name'] if dungeon else '未知副本')}",
        f"**同界角色：** {'、'.join(escape(name) for name in same_world_roles) or '暂无'}",
        f"**当前压制：** {'⚠️ 跨界，怪物全属性+20%' if cross else '✅ 同界，无跨界增幅'}",
        f"**本层倍率：** ×{abyss_monster_multiplier(run['layer_no'], cross):.2f}",
        "",
        "**通关奖励**",
    ]
    for star in (1, 2, 3):
        reward = rewards[star]
        lines.append(f"> {_stars(star)}｜经验 {reward['exp']}｜灵石 {reward['lingshi']}｜仙玉 {reward['xianyu']}")
    lines.extend((
        "",
        "> 开战后角色、装备、技能、灵兽与长期增益将冻结至本层结束。",
        "",
        _button(f"挑战深渊 {run['layer_no']}", "正式开战") + " | " + _button("深渊", "返回深渊"),
    ))
    commands = (
        (f"挑战深渊 {run['layer_no']}", "正式开战", True, 2),
        ("深渊", "返回深渊", True, 1),
        ("角色背包", "切换角色", True, 1),
    )
    return _result("\n".join(lines), commands)


async def _render_monsters(uid, notice=""):
    run = await get_active_run(uid)
    if not run or run["state"] not in ("FIGHTING", "QUALIFIED"):
        return _error("当前没有正在挑战的深渊层。", (("深渊", "返回深渊", True, 1),))
    monsters = await get_run_monsters(run["run_uuid"], run["wave_no"])
    rating = abyss_rating(run["kill_count"])
    next_target = 10 if run["kill_count"] < 10 else 20 if run["kill_count"] < 20 else 30
    lines = [
        f"##### ⚔️ 第{run['layer_no']}层｜第{run['wave_no']}/6波",
        "",
        f"**击杀：** {run['kill_count']}/{ABYSS_MAX_KILLS}｜**评级：** {_stars(rating)}",
        f"> 距离下一评级还需 {max(0, next_target - run['kill_count'])} 杀｜战后恢复30%最大气血",
    ]
    if run["role_snapshot"].get("world") != run["source_world"]:
        lines.append("> ⚠️ 跨界压制生效：本层怪物全属性+20%。")
    if notice:
        lines.extend(("", f"> {notice}"))
    lines.extend(("", "**本波敌影**"))
    commands = []
    state_icons = {"READY": "◇", "FIGHTING": "⚔", "DEFEATED": "✓", "SURVIVED": "✦"}
    for monster in monsters:
        icon = state_icons.get(monster["state"], "◇")
        kind = "首领" if monster["type"] == "boss" else "普通"
        line = f"> {icon} **{monster['slot_no']}. {escape(monster['name'])}**｜{kind}"
        if monster["state"] == "READY":
            fight_command = f"挑战深渊怪物 {monster['slot_no']}"
            line += f"｜{_button(fight_command, '挑战')}"
            commands.append((f"挑战深渊怪物 {monster['slot_no']}", f"挑战{monster['slot_no']}号", True, 2 if monster["type"] == "boss" else 1))
        elif monster["state"] == "FIGHTING":
            line += f"｜{_button('战斗状态', '继续战斗')}"
            commands.append(("战斗状态", "继续战斗", True, 2))
        lines.append(line)
    lines.extend(("", "***"))
    if rating > 0:
        lines.append(_button("深渊结算", f"按{rating}星结算") + " | " + _button("深渊怪物", "继续冲星"))
        commands.append(("深渊结算", f"{rating}星结算", True, 2))
    else:
        lines.append(_button("离开深渊", "离开深渊") + " | " + _button("深渊", "深渊主页"))
        commands.append(("离开深渊", "离开深渊", True, 3))
    commands.append(("深渊", "深渊主页", True, 1))
    return _result("\n".join(lines), commands[:10])


def _render_settlement(data, defeated=False):
    stars = int(data.get("stars", 0))
    title = "虽败犹荣，成绩已结算" if defeated else "深渊通关"
    lines = [
        f"##### 🎊 {title}",
        "",
        f"**第{data.get('layer_no', 0)}层｜{_stars(stars)}**",
        f"> 本层击杀 {data.get('kills', 0)}/30｜结算层数 {data.get('rewarded_layers', 0)}",
        "",
        f"**经验：** +{data.get('exp', 0)}",
        f"**灵石：** +{data.get('lingshi', 0)}",
        f"**仙玉：** +{data.get('xianyu', 0)}",
    ]
    if data.get("level_before") is not None and data.get("level_after") != data.get("level_before"):
        lines.append(f"**等级：** Lv.{data['level_before']} → Lv.{data['level_after']}")
    if not any(int(data.get(key, 0) or 0) for key in ("exp", "lingshi", "xianyu")):
        lines.extend(("", "> 本层对应星级奖励此前已领取，本次仅刷新最佳成绩。"))
    lines.extend((
        "",
        _button("深渊", "挑战下一层") + " | " + _button("深渊排行", "查看排行") + " | " + _button("主菜单", "主菜单"),
    ))
    commands = (
        ("深渊", "挑战下一层", True, 2),
        ("深渊排行", "查看排行", True, 1),
        ("主菜单", "主菜单", True, 1),
    )
    return _result("\n".join(lines), commands)


def _render_failure(data):
    lines = [
        "##### 🌑 深渊挑战结束",
        "",
        f"止步第{data.get('layer_no', 0)}层｜击杀 **{data.get('kills', 0)}/30**",
        "> 未达到10杀通关线，本次不发放奖励，永久层数不变。",
        "",
        _button("深渊", "重新挑战") + " | " + _button("角色菜单", "调整角色") + " | " + _button("装备菜单", "调整装备"),
    ]
    commands = (
        ("深渊", "重新挑战", True, 2),
        ("角色菜单", "调整角色", True, 1),
        ("装备菜单", "调整装备", True, 1),
    )
    return _result("\n".join(lines), commands)


async def _render_battle_outcome(uid, outcome):
    if not outcome:
        return None
    if outcome["kind"] == "settled":
        return _render_settlement(outcome["settlement"], bool(outcome.get("defeated")))
    if outcome["kind"] == "failed":
        return _render_failure(outcome["failure"])
    return await _render_monsters(uid, outcome.get("notice", ""))


async def render_abyss_outcome(uid, outcome):
    """供统一战斗面板在恢复或完成深渊战斗后渲染结果。"""
    return await _render_battle_outcome(uid, outcome)


async def settle_abyss_battle(uid, session):
    try:
        return await _render_battle_outcome(uid, await settle_finished_battle(uid, session))
    except AbyssError as error:
        return _error(error.message)


@reg_xz_func
async def abyss_home(uid, qz):
    try:
        recovered = await recover_finished_battle(uid)
        if recovered:
            return await _render_battle_outcome(uid, recovered)
        return await _render_home(uid)
    except AbyssError as error:
        return _error(error.message)


@reg_xz_func
async def abyss_preview(uid, qz, layer_no=None):
    try:
        return await _render_preview(uid, await create_preview(uid, layer_no, "NORMAL"))
    except AbyssError as error:
        return _error(error.message)


@reg_xz_func
async def abyss_start(uid, qz, layer_no=None):
    try:
        await start_run(uid, "NORMAL", layer_no)
        return await _render_monsters(uid, "角色与本层增益已冻结，深渊挑战正式开始。")
    except AbyssError as error:
        return _error(error.message)


@reg_xz_func
async def abyss_monsters(uid, qz):
    try:
        recovered = await recover_finished_battle(uid)
        if recovered:
            return await _render_battle_outcome(uid, recovered)
        return await _render_monsters(uid)
    except AbyssError as error:
        return _error(error.message)


@reg_xz_func
async def abyss_fight(uid, qz, slot_no):
    try:
        session = await start_monster_battle(uid, slot_no)
        from Game_main.g11_battle import render_battle_panel
        return render_battle_panel(session, f"深渊第{session.metadata.get('wave_no', 1)}波，请选择行动。")
    except AbyssError as error:
        return _error(error.message, (("深渊怪物", "返回当前波", True, 1), ("战斗状态", "战斗状态", True, 1)))


@reg_xz_func
async def abyss_settle(uid, qz):
    try:
        return _render_settlement(await settle_run(uid))
    except AbyssError as error:
        return _error(error.message, (("深渊怪物", "返回当前波", True, 1), ("深渊", "深渊主页", True, 1)))


@reg_xz_func
async def abyss_leave(uid, qz):
    try:
        run = await abandon_run(uid)
        return await _render_home(uid, f"已离开第{run['layer_no']}层，本次击杀未产生通关奖励。")
    except AbyssError as error:
        return _error(error.message, (("深渊怪物", "返回当前波", True, 1), ("深渊结算", "结算奖励", True, 2)))


@reg_xz_func
async def abyss_placement(uid, qz, action=None):
    try:
        dashboard = await get_dashboard(uid)
        role = dashboard["role"]
        if not role:
            raise AbyssError("ROLE_REQUIRED", "请先选择一名角色出战。")
        target = placement_target(role["level"])
        highest = dashboard["profile"]["highest_cleared_layer"]
        if highest >= target:
            raise AbyssError("PLACEMENT_REDUNDANT", f"你已通关第{highest}层，当前角色无需定级。")
        if str(action or "").strip() == "开始":
            await start_run(uid, "PLACEMENT", target)
            return await _render_monsters(uid, f"定级目标第{target}层；失败无奖励，成功后补齐未领取层数。")
        req = required_exp(role["level"])
        totals = {}
        for star in (1, 2, 3):
            rewards = [calculate_abyss_layer_reward(req, layer, star) for layer in range(1, target + 1)]
            totals[star] = {key: sum(item[key] for item in rewards) for key in ("exp", "lingshi", "xianyu")}
        lines = [
            f"##### 🧭 深渊定级｜目标第{target}层",
            "",
            f"**参赛角色：** {escape(role['name'])} Lv.{role['level']}",
            f"**当前进度：** 第{highest}层",
            "> 定级按角色等级1:1挑战。失败不发奖、不改进度，可无限重试。",
            "",
            "**理论满额奖励**（已领取部分会自动扣除）",
        ]
        for star in (1, 2, 3):
            reward = totals[star]
            lines.append(f"> {_stars(star)}｜经验 {reward['exp']}｜灵石 {reward['lingshi']}｜仙玉 {reward['xianyu']}")
        lines.extend((
            "",
            _button("深渊定级 开始", "确认开始定级") + " | " + _button("深渊", "暂不挑战"),
        ))
        commands = (
            ("深渊定级 开始", "确认定级", True, 2),
            ("深渊", "暂不挑战", True, 1),
        )
        return _result("\n".join(lines), commands)
    except (AbyssError, ValueError) as error:
        return _error(getattr(error, "message", str(error)), (("深渊", "返回深渊", True, 1), ("当前角色", "当前角色", True, 1)))


@reg_xz_func
async def abyss_rank(uid, qz, page=1):
    data = await get_leaderboard(uid, page)
    lines = [
        "##### 🏆 轮海深渊榜",
        "",
        f"> 第{data['page']}/{data['total_pages']}页｜共{data['total']}位道友上榜",
        "",
    ]
    if not data["rows"]:
        lines.append("尚无人踏破第一层，首位留名者或许就是你。")
    for item in data["rows"]:
        icon = {1: "🥇", 2: "🥈", 3: "🥉"}.get(item["rank"], f"{item['rank']}.")
        mine = " ⭐" if item["uid"] == int(uid) else ""
        lines.append(f"{icon} **{escape(item['name'])}**｜第{item['layer']}层 {_stars(item['stars'])}｜{item['kills']}杀{mine}")
    if data["mine"] and all(item["uid"] != int(uid) for item in data["rows"]):
        mine = data["mine"]
        lines.extend(("", f"> 你的排名：第{mine['rank']}名｜第{mine['layer']}层｜{mine['kills']}杀"))
    nav = []
    commands = []
    if data["page"] > 1:
        nav.append(_button(f"深渊排行 {data['page'] - 1}", "上一页"))
        commands.append((f"深渊排行 {data['page'] - 1}", "上一页", True, 1))
    if data["page"] < data["total_pages"]:
        nav.append(_button(f"深渊排行 {data['page'] + 1}", "下一页"))
        commands.append((f"深渊排行 {data['page'] + 1}", "下一页", True, 1))
    nav.append(_button("深渊", "返回深渊"))
    commands.append(("深渊", "返回深渊", True, 1))
    lines.extend(("", " | ".join(nav)))
    return _result("\n".join(lines), commands)
