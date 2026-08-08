# -*- coding: utf-8 -*-
"""灵兽资质、羁绊与战力的纯规则，供展示、战斗和排行榜共用。"""


MIN_APTITUDE = 60
MAX_APTITUDE = 100
BOND_EXP_PER_LEVEL = 100
MAX_BOND_LEVEL = 10
VALID_BEAST_ROLES = {"STRIKER", "GUARDIAN", "HEALER", "DISRUPTOR"}


def _as_int(value, default=0):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return int(default)


def normalized_aptitude(value):
    """旧服可能存在越界资质；所有消费者均使用同一安全区间。"""
    return min(MAX_APTITUDE, max(MIN_APTITUDE, _as_int(value, MIN_APTITUDE)))


def spirit_beast_bonus_value(aptitude):
    """与当前四类灵契实际进入战斗的百分比强度保持一致。"""
    aptitude = normalized_aptitude(aptitude)
    return 4 + (aptitude - MIN_APTITUDE) // 5


def spirit_beast_bond_level(bond_exp):
    return min(MAX_BOND_LEVEL, max(0, _as_int(bond_exp) // BOND_EXP_PER_LEVEL))


def calculate_spirit_beast_power(profile):
    """返回灵兽战力与可展示明细。

    战力只评估已经真实生效的资质、羁绊和灵契强度：
    500 + 资质×20 + 羁绊等级×120 + 灵契强度×100。
    四类定位使用同一权重，避免输出灵兽天然获得更高排行榜估值。
    """
    if not profile:
        return {
            "power": 0,
            "power_aptitude": 0,
            "power_bond": 0,
            "power_contract": 0,
            "aptitude": 0,
            "bond_level": 0,
            "contract_value": 0,
        }

    aptitude = normalized_aptitude(profile.get("aptitude"))
    bond_level = spirit_beast_bond_level(profile.get("bond_exp"))
    contract_value = (
        spirit_beast_bonus_value(aptitude)
        if str(profile.get("role") or "") in VALID_BEAST_ROLES
        else 0
    )
    power_aptitude = aptitude * 20
    power_bond = bond_level * 120
    power_contract = contract_value * 100
    total = 500 + power_aptitude + power_bond + power_contract
    return {
        "power": int(total),
        "power_aptitude": int(power_aptitude),
        "power_bond": int(power_bond),
        "power_contract": int(power_contract),
        "aptitude": aptitude,
        "bond_level": bond_level,
        "contract_value": contract_value,
    }
