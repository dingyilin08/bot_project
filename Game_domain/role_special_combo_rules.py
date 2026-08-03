# -*- coding: utf-8 -*-
"""专属组合的白名单规则、战斗快照与现有专属槽位适配。"""

from copy import deepcopy


COMBO_SNAPSHOT_SCHEMA_VERSION = 1
COMBO_RULE_VERSION = "role_combo.v1"
COMBO_MULTIPLIER_CAP_BP = 20000

PASSIVE_EFFECT_TYPES = {
    "ENEMY_ATTACK_DOWN": ("COMBO_ENEMY_ATTACK_DOWN", 15),
    "PLAYER_DEFENSE_UP": ("COMBO_PLAYER_DEFENSE_UP", 15),
    "PLAYER_SPEED_UP": ("COMBO_PLAYER_SPEED_UP", 15),
    "PLAYER_HEAL": ("COMBO_LOW_HP_HEAL", 10),
    "PLAYER_SHIELD": ("COMBO_LOW_HP_SHIELD", 10),
}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, lower, upper, default=0):
    return min(upper, max(lower, _int(value, default)))


def normalize_combo_multiplier_bp(value):
    """倍率统一转为基点并限制在0—200%。"""
    try:
        multiplier = float(value)
    except (TypeError, ValueError):
        multiplier = 0.0
    return min(COMBO_MULTIPLIER_CAP_BP, max(0, int(round(multiplier * 10000))))


def sanitize_combo_effect(raw_effect):
    """将旧/随机 effect_json 转成战斗允许的机器字段并统一封顶。"""
    raw = raw_effect if isinstance(raw_effect, dict) else {}
    raw_type = str(raw.get("type") or "DAMAGE").upper()
    source_kind = str(raw.get("source_kind") or "").upper()
    inherited_from = str(raw.get("inherited_from") or "专属组合")[:32]

    if source_kind != "ACTIVE" and raw_type in PASSIVE_EFFECT_TYPES:
        effect_code, value_cap = PASSIVE_EFFECT_TYPES[raw_type]
        effect = {
            "effect_code": effect_code,
            "effect_codes": [effect_code],
            "mode": "PASSIVE_OVERRIDE",
            "type": raw_type,
            "value": _clamp(raw.get("value"), 1, value_cap, min(8, value_cap)),
            "duration": _clamp(raw.get("duration"), 1, 3, 1),
            "trigger": "LOW_HP" if raw_type in ("PLAYER_HEAL", "PLAYER_SHIELD") else "BATTLE_START",
            "inherited_from": inherited_from,
        }
        if effect["trigger"] == "LOW_HP":
            effect["threshold"] = _clamp(raw.get("threshold"), 10, 50, 30)
        return effect

    effect = {
        "effect_code": "COMBO_ACTIVE_STRIKE",
        "effect_codes": ["COMBO_ACTIVE_STRIKE"],
        "mode": "ACTIVE_OVERRIDE",
        "type": "DAMAGE",
        "inherited_from": inherited_from,
    }

    def add_percent(source_key, target_key, cap, code):
        value = _clamp(raw.get(source_key), 0, cap)
        if value:
            effect[target_key] = value
            effect["effect_codes"].append(code)

    add_percent("defense_ignore", "defense_ignore", 15, "COMBO_DEFENSE_PIERCE")
    add_percent("boss_bonus", "boss_bonus", 15, "COMBO_BOSS_DAMAGE")
    add_percent("resilience_down", "resilience_down", 15, "COMBO_RESILIENCE_BREAK")
    add_percent("healing_down", "healing_down", 20, "COMBO_HEAL_SUPPRESS")
    add_percent("speed_down", "speed_down", 15, "COMBO_SPEED_BREAK")
    add_percent("shield_percent", "shield_percent", 10, "COMBO_SELF_SHIELD")

    # 旧“破盾加成”在现有战斗公式中等价收敛为有限破防，不透传未知字段。
    shield_break = _clamp(raw.get("shield_bonus"), 0, 10)
    if shield_break:
        effect["defense_ignore"] = max(effect.get("defense_ignore", 0), shield_break)
        effect["effect_codes"].append("COMBO_SHIELD_BREAK")

    burn_turns = _clamp(raw.get("burn"), 0, 2)
    if burn_turns:
        effect["burn"] = burn_turns
        effect["effect_codes"].append("COMBO_BURN")

    damage_bonus = _clamp(raw.get("damage_bonus"), 0, 15)
    if raw.get("target_hp_below") and damage_bonus:
        effect["target_hp_below"] = _clamp(raw.get("target_hp_below"), 10, 90, 30)
        effect["damage_bonus"] = damage_bonus
        effect["effect_codes"].append("COMBO_EXECUTE")
    elif raw.get("self_hp_above"):
        effect["self_hp_above"] = _clamp(raw.get("self_hp_above"), 10, 90, 70)
        effect["damage_bonus"] = damage_bonus or 10
        effect["effect_codes"].append("COMBO_HIGH_HP_STRIKE")
    elif raw.get("round_at_least") and damage_bonus:
        effect["round_at_least"] = _clamp(raw.get("round_at_least"), 1, 20, 3)
        effect["damage_bonus"] = damage_bonus
        effect["effect_codes"].append("COMBO_LATE_STRIKE")

    # 固定连携中的战意/迅捷转换为首回合有限增伤，确保效果能被当前PVE执行器消费。
    fixed_opening_bonus = max(
        _clamp(raw.get("first_round_bonus"), 0, 15),
        _clamp(raw.get("battle_intent"), 0, 3) * 5,
        _clamp(raw.get("speed_up"), 0, 15),
    )
    if fixed_opening_bonus:
        effect["first_round_bonus"] = min(15, fixed_opening_bonus)
        effect["effect_codes"].append("COMBO_OPENING_STRIKE")

    if raw.get("preview") or raw.get("threat_insight"):
        effect["threat_insight"] = 1
        effect["effect_codes"].append("COMBO_THREAT_INSIGHT")

    if raw.get("dispel"):
        effect["type"] = "DAMAGE_DISPEL"
        effect["dispel"] = 1
        effect["effect_codes"].append("COMBO_DISPEL")

    heal_percent = _clamp(raw.get("heal_percent"), 0, 10)
    heal_damage_percent = _clamp(raw.get("heal_damage_percent"), 0, 5)
    clear_dot = 1 if raw.get("clear_dot") else 0
    if heal_percent or heal_damage_percent or clear_dot:
        effect["type"] = "DAMAGE_HEAL"
        if heal_percent:
            effect["heal_percent"] = heal_percent
        if heal_damage_percent:
            effect["heal_damage_percent"] = heal_damage_percent
            effect["heal_percent_cap"] = _clamp(raw.get("heal_percent_cap"), 1, 10, 5)
        if clear_dot:
            effect["clear_dot"] = 1
        effect["effect_codes"].append("COMBO_RECOVERY")

    # 去重且保持稳定顺序，方便快照和战报做精确比较。
    effect["effect_codes"] = list(dict.fromkeys(effect["effect_codes"]))
    return effect


def build_combo_battle_snapshot(combo):
    """把数据库组合记录转换为可恢复、可验证的PVE快照。"""
    combo = combo if isinstance(combo, dict) else {}
    combo_id = _int(combo.get("id"))
    if combo_id <= 0:
        return None
    multiplier_bp = normalize_combo_multiplier_bp(combo.get("multiplier"))
    effect = sanitize_combo_effect(combo.get("effect"))
    return {
        "schema_version": COMBO_SNAPSHOT_SCHEMA_VERSION,
        "rule_version": COMBO_RULE_VERSION,
        "id": combo_id,
        "name": str(combo.get("name") or f"组合#{combo_id}")[:30],
        "combo_type": str(combo.get("combo_type") or "专属组合")[:30],
        "mode": effect["mode"],
        "multiplier_bp": multiplier_bp,
        "multiplier": multiplier_bp / 10000,
        "effect": effect,
        "max_uses": 1,
    }


def apply_combo_to_battle_special(base_special, combo_snapshot):
    """将一个已装备组合适配到现有主动/被动执行器；不修改输入对象。"""
    result = deepcopy(base_special or {})
    combo = deepcopy(combo_snapshot)
    if not combo:
        return result
    result["combo"] = combo
    entry = {
        # 负ID与图鉴能力ID隔离，战斗快照中仍保留正 combo_id。
        "id": -int(combo["id"]),
        "combo_id": int(combo["id"]),
        "name": combo["name"],
        "multiplier": combo["multiplier"],
        "effect": deepcopy(combo["effect"]),
        "source": "EQUIPPED_COMBO",
    }
    if combo["mode"] == "PASSIVE_OVERRIDE":
        result["base_passive"] = deepcopy(result.get("passive"))
        result["passive"] = entry
    else:
        result["base_active"] = deepcopy(result.get("active"))
        result["active"] = entry
    return result
