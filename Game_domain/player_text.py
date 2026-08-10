# -*- coding: utf-8 -*-
"""玩家可见文案的资源名称与奖励格式化。

业务层可以使用稳定的数据库字段名，但这些字段名不能直接出现在机器人回复中。
所有动态奖励字典应经由本模块格式化；另外在统一输出层再做一次兜底，
避免新增玩法遗漏格式化时把内部键泄露给玩家。
"""

import logging
import re
from collections.abc import Mapping


_LOGGER = logging.getLogger(__name__)


# 这里只保存玩家可理解的名称，严禁把数据库列名作为玩家文案使用。
PLAYER_RESOURCE_LABELS = {
    "lingshi": "灵石",
    "xianyu": "仙玉",
    "exp": "经验",
    "beast_trace": "兽踪",
    "soul_stone": "兽魂石",
    "spirit_essence": "御兽灵息",
    "beast_material": "基础兽材",
    "wash_dew": "洗髓露",
    "bloodline_essence": "血脉精华",
    "skill_page": "灵契残页",
    "story_token": "故事信物",
    "nameplate": "灵兽改名牌",
    "soul_fragment": "兽魂碎片",
    "herb_token": "灵草凭证",
    "role_fragment": "角色碎片",
    "character_fragment": "角色碎片",
    "stamina_pill": "体力药",
    "sweep_ticket": "扫荡副本券",
    "dungeon_sweep_ticket": "扫荡副本券",
}

PLAYER_EFFECT_LABELS = {
    "active_slot": "解锁主动槽",
    "passive_slot": "解锁被动槽",
    "passive_slots": "扩展被动槽",
    "ability_trait": "解锁专属特性",
    "combo": "解锁专属组合",
    "combo_candidates": "扩展组合候选",
    "presets": "扩展预设位",
    "average_protection": "获得均衡防护",
    "phenomenon": "解锁异象",
    "mother_qi_appearance": "显化万物母气",
    "spirit_appearance": "显化元神法相",
    "sword_count": "凝成飞剑",
    "cave_count": "开辟洞天",
    "second_target": "解锁第二定向",
    "resilience_stance": "获得韧性剑势",
    "divine_thunder": "引动辟邪神雷",
    "stances": "解锁洞天姿态",
    "unity_trial": "开启洞天合一试炼",
    "unique_cave": "成就唯一洞天",
    "COMBO_ACTIVE_STRIKE": "专属一击",
    "COMBO_ENEMY_ATTACK_DOWN": "敌方攻击削弱",
    "COMBO_PLAYER_DEFENSE_UP": "自身防御提升",
    "COMBO_PLAYER_SPEED_UP": "自身速度提升",
    "COMBO_LOW_HP_HEAL": "低血量回复",
    "COMBO_LOW_HP_SHIELD": "低血量护盾",
    "COMBO_DEFENSE_PIERCE": "破防",
    "COMBO_BOSS_DAMAGE": "首领增伤",
    "COMBO_RESILIENCE_BREAK": "韧性削弱",
    "COMBO_HEAL_SUPPRESS": "治疗压制",
    "COMBO_SPEED_BREAK": "减速",
    "COMBO_SELF_SHIELD": "自身护盾",
    "COMBO_SHIELD_BREAK": "破盾",
    "COMBO_BURN": "灼烧",
    "COMBO_EXECUTE": "斩杀增伤",
    "COMBO_HIGH_HP_STRIKE": "高血压制",
    "COMBO_LATE_STRIKE": "后程增伤",
    "COMBO_OPENING_STRIKE": "首回合增伤",
    "COMBO_THREAT_INSIGHT": "洞察威胁",
    "COMBO_DISPEL": "驱散",
    "COMBO_RECOVERY": "恢复",
}
PLAYER_IDENTIFIER_LABELS = {**PLAYER_RESOURCE_LABELS, **PLAYER_EFFECT_LABELS}

_KNOWN_IDENTIFIER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(" + "|".join(
        re.escape(key) for key in sorted(PLAYER_IDENTIFIER_LABELS, key=len, reverse=True)
    ) + r")(?![A-Za-z0-9_])"
)
# 仅在“标识符+数量”这一奖励语境下屏蔽尚未登记的新内部键，避免误伤普通文本。
_UNKNOWN_REWARD_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])([a-z][a-z0-9_]{2,})(?=\s*[+×]\s*\d)"
)
_UNKNOWN_TECHNICAL_CODE_PATTERN = re.compile(
    r"(?<![A-Z0-9_])([A-Z][A-Z0-9]*_[A-Z0-9_]+)(?![A-Z0-9_])"
)


def player_resource_name(resource_key, default="未命名奖励"):
    """返回资源的玩家名称；未知键绝不回显原始内部标识。"""
    return PLAYER_RESOURCE_LABELS.get(str(resource_key or "").strip(), default)


def format_reward_map(rewards, separator="、"):
    """将 ``{内部资源键: 数量}`` 安全格式化为玩家可读的奖励文案。"""
    if not isinstance(rewards, Mapping):
        return "无"
    parts = []
    for resource_key, raw_amount in rewards.items():
        try:
            amount = int(raw_amount or 0)
        except (TypeError, ValueError):
            continue
        if not amount:
            continue
        label = player_resource_name(resource_key)
        parts.append(f"{label}{'+' if amount > 0 else '-'}{abs(amount)}")
    return separator.join(parts) or "无"


def format_effect_codes(codes, separator="、"):
    """将战斗规则码转换为玩家可理解的效果名称。"""
    if isinstance(codes, str):
        codes = (codes,)
    if not isinstance(codes, (list, tuple, set)):
        return "未命名效果"
    return separator.join(
        PLAYER_EFFECT_LABELS.get(str(code or ""), "未命名效果")
        for code in codes
        if str(code or "")
    ) or "未命名效果"


def format_unlock_effects(effects, separator="、"):
    """格式化专属成长的解锁项，保留有意义的数量或名称。"""
    if not isinstance(effects, Mapping):
        return "获得新的专属能力"
    parts = []
    for effect_key, value in effects.items():
        key = str(effect_key or "")
        if key == "sword_count":
            parts.append(f"凝成{int(value or 0)}口飞剑")
        elif key == "cave_count":
            parts.append(f"开辟{int(value or 0)}口洞天")
        elif key == "phenomenon" and value:
            parts.append(f"解锁异象「{value}」")
        elif key == "presets":
            parts.append(f"新增{int(value or 0)}个预设位")
        elif key == "stances":
            parts.append(f"解锁{int(value or 0)}种洞天姿态")
        else:
            parts.append(PLAYER_EFFECT_LABELS.get(key, "获得新的专属能力"))
    return separator.join(dict.fromkeys(parts)) or "获得新的专属能力"


def sanitize_player_content(content):
    """为统一发送层提供最后一道内部字段名拦截。

    已登记字段会替换为中文名；未登记的英文下划线奖励键会被隐藏并记录日志，
    这样线上不会再把实现细节发送给玩家，同时开发者能补充映射。
    """
    if not isinstance(content, str):
        return content

    sanitized = _KNOWN_IDENTIFIER_PATTERN.sub(
        lambda match: PLAYER_IDENTIFIER_LABELS[match.group(1)], content
    )

    def _hide_unknown_reward(match):
        key = match.group(1)
        _LOGGER.warning("拦截未登记的玩家奖励字段：%s", key)
        return "未命名奖励"

    sanitized = _UNKNOWN_REWARD_PATTERN.sub(_hide_unknown_reward, sanitized)

    def _hide_unknown_technical_code(match):
        code = match.group(1)
        _LOGGER.warning("拦截未登记的玩家规则码：%s", code)
        return "未命名效果"

    return _UNKNOWN_TECHNICAL_CODE_PATTERN.sub(
        _hide_unknown_technical_code, sanitized
    )
