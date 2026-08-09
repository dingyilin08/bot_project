# -*- coding: utf-8 -*-
"""六大角色的账号级专属特性；拥有角色即可生效，无需出战。"""

import math


BASIS_POINTS = 10000
ROLE_TRAITS = {
    "萧炎": {
        "name": "帝炎丹心",
        "description": "炼制丹药效率提升20%（炼制耗时缩短20%）",
    },
    "韩立": {
        "name": "掌天培灵",
        "description": "种植药材效率提升20%（成熟耗时缩短20%）",
    },
    "王林": {
        "name": "古神道体",
        "description": "账号内任一角色进入战斗时，最大气血提升20%",
    },
    "叶凡": {
        "name": "源术通灵",
        "description": "所有非转账类玩法灵石产出提升20%",
    },
    "石昊": {
        "name": "锻体炼器",
        "description": "装备强化成功率提高10个百分点",
    },
    "孟川": {
        "name": "元神鉴灵",
        "description": "连续鉴灵未获天品时，第50次必出天品",
    },
}

PRODUCTION_DURATION_BONUS_BP = 2000
BATTLE_HP_BONUS_BP = 2000
LINGSHI_OUTPUT_BONUS_BP = 2000
ENHANCE_SUCCESS_BONUS_BP = 1000
DEFAULT_HEAVEN_PITY = 60
MENG_CHUAN_HEAVEN_PITY = 50


async def has_owned_role(cursor, uid, role_name):
    """实时检查账号角色仓库；角色刚合成后下一次操作立即生效。"""
    await cursor.execute(
        "SELECT 1 FROM user_role WHERE uid=%s AND `name`=%s LIMIT 1",
        (uid, role_name),
    )
    return bool(await cursor.fetchone())


def trait_description(role_name):
    trait = ROLE_TRAITS.get(str(role_name or "").strip())
    if not trait:
        return None
    return f"{trait['name']}：{trait['description']}（拥有即生效）"


def apply_production_duration(base_seconds, active):
    base_seconds = max(1, int(base_seconds))
    if not active:
        return base_seconds
    return max(
        1,
        math.ceil(base_seconds * (BASIS_POINTS - PRODUCTION_DURATION_BONUS_BP) / BASIS_POINTS),
    )


def adjusted_start_timestamp(now_timestamp, base_seconds, active):
    """兼容旧计时结构：通过回拨起点冻结本次缩时效果。"""
    duration = apply_production_duration(base_seconds, active)
    return int(now_timestamp) - (max(1, int(base_seconds)) - duration)


def apply_battle_hp(base_hp, active):
    base_hp = max(1, int(base_hp))
    if not active:
        return base_hp
    return max(1, base_hp * (BASIS_POINTS + BATTLE_HP_BONUS_BP) // BASIS_POINTS)


def apply_lingshi_output(base_amount, active):
    base_amount = max(0, int(base_amount))
    if not active or base_amount <= 0:
        return base_amount
    return base_amount * (BASIS_POINTS + LINGSHI_OUTPUT_BONUS_BP) // BASIS_POINTS


async def calculate_lingshi_output(cursor, uid, base_amount):
    return apply_lingshi_output(
        base_amount,
        await has_owned_role(cursor, uid, "叶凡"),
    )


def apply_enhance_success_rate(base_rate_bp, active):
    base_rate_bp = max(0, int(base_rate_bp))
    if active:
        base_rate_bp += ENHANCE_SUCCESS_BONUS_BP
    return min(BASIS_POINTS, base_rate_bp)


def heaven_pity_limit(active):
    return MENG_CHUAN_HEAVEN_PITY if active else DEFAULT_HEAVEN_PITY
