"""装备属性与战力计算共用的规则常量。"""

EQUIPMENT_QUALITY_MULTIPLIER = {
    "凡品": 1.0,
    "良品": 1.3,
    "精品": 1.8,
    "仙品": 2.5,
    "神品": 3.5,
}

# 每强化一级提升装备基础属性 10%。角色属性展示、战斗和战力必须一致。
EQUIPMENT_ENHANCE_BONUS_PER_LEVEL = 0.10

# 套装仅取玩家已激活套装中的最高档位，不叠加。
EQUIPMENT_SET_BONUS = {2: 0.20, 4: 0.40, 6: 0.60}
