# -*- coding: utf-8 -*-
"""副本经验与灵石产出规则。

经验以 data_dungeon.reward_exp 作为普通遭遇基础值；灵石按同档装备强化
基础消耗定标。十五场完整通关使用固定权重，保证手动挑战、扫荡和菜单
预览得到完全相同的总额。
"""


DUNGEON_REWARD_RULE_VERSION = "2026-08-enhance-anchor-v1"

# 与装备强化成本档位对应。完整通关产出为同档“强化+1基础消耗”的两倍。
ENHANCE_BASE_COST_BY_DUNGEON_LEVEL = {
    1: 500,
    10: 1500,
    20: 4000,
    30: 10000,
    40: 25000,
    50: 60000,
    60: 130000,
    70: 280000,
    80: 600000,
    90: 1200000,
}
FULL_CLEAR_ENHANCE_COST_MULTIPLIER = 2

STREAK_BONUS_BP = {
    3: 11000,
    5: 12000,
    10: 13500,
    15: 15000,
}
FULL_CLEAR_BATTLE_COUNT = 15
BOSS_INTERVAL = 5


def dungeon_tier(min_level):
    """将任意副本等级归入现有强化成本档位。"""
    level = max(1, int(min_level or 1))
    return max(
        tier for tier in ENHANCE_BASE_COST_BY_DUNGEON_LEVEL if tier <= level
    )


def streak_bonus_bp(kill_streak):
    streak = max(1, int(kill_streak or 1))
    bonus = 10000
    for threshold, candidate in STREAK_BONUS_BP.items():
        if streak >= threshold:
            bonus = max(bonus, candidate)
    return bonus


def encounter_weight_units(kill_streak):
    """返回一次遭遇在完整通关中的整数权重；每5场固定为首领。"""
    streak = max(1, int(kill_streak or 1))
    boss_multiplier = 2 if streak % BOSS_INTERVAL == 0 else 1
    return streak_bonus_bp(streak) * boss_multiplier


FULL_CLEAR_WEIGHT_UNITS = tuple(
    encounter_weight_units(index)
    for index in range(1, FULL_CLEAR_BATTLE_COUNT + 1)
)
FULL_CLEAR_TOTAL_WEIGHT_UNITS = sum(FULL_CLEAR_WEIGHT_UNITS)


def allocate_full_clear_total(total):
    """按遭遇权重分配整数奖励，并保证十五场之和严格等于 total。"""
    total = max(0, int(total or 0))
    rewards = []
    previous = 0
    cumulative_weight = 0
    for weight in FULL_CLEAR_WEIGHT_UNITS:
        cumulative_weight += weight
        current = total * cumulative_weight // FULL_CLEAR_TOTAL_WEIGHT_UNITS
        rewards.append(current - previous)
        previous = current
    return tuple(rewards)


def calculate_full_clear_currency(reward_exp, reward_lingshi, min_level=1):
    """计算完整通关的经验与灵石目标值。"""
    configured_exp = max(0, int(reward_exp or 0))
    configured_lingshi = max(0, int(reward_lingshi or 0))
    total_exp = configured_exp * FULL_CLEAR_TOTAL_WEIGHT_UNITS // 10000
    tier = dungeon_tier(min_level)
    enhance_anchor = ENHANCE_BASE_COST_BY_DUNGEON_LEVEL[tier]
    total_lingshi = max(
        configured_lingshi,
        enhance_anchor * FULL_CLEAR_ENHANCE_COST_MULTIPLIER,
    )
    return total_exp, total_lingshi


def calculate_encounter_currency(
    reward_exp,
    reward_lingshi,
    min_level,
    kill_streak,
):
    """计算指定场次奖励；十五场逐场相加与扫荡完整结算严格一致。"""
    index = min(
        FULL_CLEAR_BATTLE_COUNT,
        max(1, int(kill_streak or 1)),
    ) - 1
    total_exp, total_lingshi = calculate_full_clear_currency(
        reward_exp,
        reward_lingshi,
        min_level,
    )
    return (
        allocate_full_clear_total(total_exp)[index],
        allocate_full_clear_total(total_lingshi)[index],
    )
