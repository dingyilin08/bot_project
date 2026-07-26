# -*- coding: utf-8 -*-
"""P0 回合战斗面板：负责会话读取、玩家行动和结果交接。"""

from uuid import NAMESPACE_URL, uuid5

from func.pd_func import reg_xz_func
from Game_domain.battle_models import BattleError, STATE_FINISHED, utcnow
from Game_domain.battle_repository import MySQLBattleRepository
from Game_domain.battle_service import BattleSessionService
from Tool.combat_system import CombatManager


ACTION_ALIASES = {
    "普攻": ("NORMAL_ATTACK", None),
    "普通攻击": ("NORMAL_ATTACK", None),
    "防御": ("DEFEND", None),
    "调息": ("MEDITATE", None),
    "御器": ("ARTIFACT", None),
    "道心爆发": ("DAO_HEART_BURST", None),
    "道心延势": ("DAO_HEART_EXTEND", None),
    "留存道心": ("DAO_HEART_STORE", None),
}


def get_battle_service():
    """每次指令使用短生命周期仓储，状态完全由数据库会话保存。"""
    return BattleSessionService(MySQLBattleRepository(), action_timeout_seconds=90)


def _remaining_seconds(session):
    if not session.action_deadline:
        return 0
    return max(0, int((session.action_deadline - utcnow()).total_seconds()))


def _recent_messages(events):
    messages = [event.payload.get("message", "") for event in events]
    return [message for message in messages if message][-8:]


def render_battle_panel(session, notice="", events=None):
    """将已持久化快照渲染为可直接点击的 QQ 指令面板。"""
    manager = CombatManager.from_snapshot(session.snapshot)
    player = manager.player
    enemy = manager.enemy
    output = "##### ⚔️ 回合战斗\n\n"
    output += f"**第 {session.round_no + 1} 回合** | 剩余决策时间：{_remaining_seconds(session)} 秒\n\n"
    output += f"**我方** {player.name}\n> HP：{max(0, player.hp)}/{player.max_hp} | 法力：{player.mana}/{player.max_mana}\n"
    output += f"> 状态：{player.get_status_summary() or '无'}\n\n"
    dao_heart = manager.dao_heart
    output += f"> 道心：{dao_heart['value']}/{dao_heart['cap']}（{dao_heart['last_element'] or '未定'}）\n\n"
    output += f"**敌方** {enemy.name}\n> HP：{max(0, enemy.hp)}/{enemy.max_hp}\n"
    output += f"> 状态：{enemy.get_status_summary() or '无'}\n\n"

    intent = manager.boss_tianji.get("intent")
    if intent:
        output += f"> ☯️ **Boss 天机：{intent['name']}**，本回合使用**{intent['counter_name']}**技能可破局。\n\n"
    if notice:
        output += f"> {notice}\n\n"
    messages = _recent_messages(events or [])
    if messages:
        output += "**本回合战报**\n> " + "\n> ".join(messages) + "\n\n"

    output += "***\n\n**选择行动**\n"
    output += "<qqbot-cmd-enter text='战斗行动 普攻' /> | <qqbot-cmd-enter text='战斗行动 防御' />\n"
    output += "<qqbot-cmd-enter text='战斗行动 调息' /> | <qqbot-cmd-enter text='战斗行动 御器' />\n"
    if dao_heart["value"] >= 3:
        output += "<qqbot-cmd-enter text='战斗行动 道心爆发' /> | <qqbot-cmd-enter text='战斗行动 道心延势' />\n"
    if dao_heart["value"] >= dao_heart["cap"]:
        output += "<qqbot-cmd-enter text='战斗行动 留存道心' />\n"
    for skill in player.skills:
        cooldown = player.cooldowns.get(skill.id, 0)
        suffix = f"（冷却{cooldown}）" if cooldown else ""
        output += f"<qqbot-cmd-enter text='战斗行动 技能-{skill.id}' /> {skill.name}{suffix}\n"
    output += "\n<qqbot-cmd-enter text='战斗状态' />"
    return {"type": "markdown", "content": output}


async def _settle_finished_battle(uid, session):
    """复用副本已有结算，奖励仍由幂等账本保证只发放一次。"""
    monster_index = session.metadata.get("monster_index")
    if monster_index is None:
        return {"type": "markdown", "content": "战斗已结束，但缺少副本结算信息。"}
    from Game_main.g6_dungeon import fight_monster

    manager = CombatManager.from_snapshot(session.snapshot)
    return await fight_monster(uid, monster_index, combat_manager=manager)


async def _resolve_expired_or_render(uid, session, service):
    if session.is_expired():
        result = await service.resolve_round(battle_id=session.battle_id)
        session = await service.get_battle(session.battle_id, uid)
        if result.state == STATE_FINISHED:
            return await _settle_finished_battle(uid, session)
        return render_battle_panel(session, "已超时，系统自动采取防御。", result.events)
    return render_battle_panel(session)


@reg_xz_func
async def battle_status(uid, qz):
    service = get_battle_service()
    session = await service.get_active_battle(uid)
    if not session:
        return {"type": "markdown", "content": "当前没有进行中的回合战斗。\n<qqbot-cmd-enter text='查看怪物' />"}
    try:
        return await _resolve_expired_or_render(uid, session, service)
    except BattleError as error:
        return {"type": "markdown", "content": f"战斗状态读取失败：{error.message}"}


def _parse_action(value):
    text = (value or "").strip()
    if text in ACTION_ALIASES:
        return ACTION_ALIASES[text]
    if text.startswith("技能-"):
        try:
            return "SKILL", int(text[3:])
        except ValueError:
            pass
    raise BattleError("ACTION_INVALID", "行动格式错误，请使用：普攻、防御、调息、御器或 技能-编号")


@reg_xz_func
async def battle_action(uid, qz, action_text):
    service = get_battle_service()
    session = await service.get_active_battle(uid)
    if not session:
        return {"type": "markdown", "content": "当前没有进行中的回合战斗。\n<qqbot-cmd-enter text='查看怪物' />"}
    try:
        if session.is_expired():
            return await _resolve_expired_or_render(uid, session, service)
        action_type, skill_id = _parse_action(action_text)
        action_id = str(uuid5(NAMESPACE_URL, f"{session.battle_id}:{session.round_no}:{uid}"))
        result = await service.submit_action(
            battle_id=session.battle_id,
            uid=uid,
            action_type=action_type,
            skill_id=skill_id,
            action_id=action_id,
        )
        session = await service.get_battle(session.battle_id, uid)
        if result.state == STATE_FINISHED:
            return await _settle_finished_battle(uid, session)
        notice = "该行动已处理。" if result.idempotent else "行动已结算，请选择下一回合行动。"
        return render_battle_panel(session, notice, result.events)
    except BattleError as error:
        return {"type": "markdown", "content": f"行动未生效：{error.message}\n<qqbot-cmd-enter text='战斗状态' />"}
