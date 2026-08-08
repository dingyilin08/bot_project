# -*- coding: utf-8 -*-
"""队伍 PVE v2：冻结阵容与技能，并在统一速度序列中结算回合。"""

from hashlib import sha256
import json
from random import Random
from uuid import uuid4

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql
from Tool.combat_system import normalize_buff_target, normalize_skill_buff_type


SCHEMA_VERSION = 2
RULE_VERSION = "party-pve.v2"
BASIS_POINTS = 10000
DEFENSE_CONSTANT = 800
MEDITATE_RECOVERY_BP = 3000
VICTORY_LINGSHI = 60
PVE_STAT_BONUS_CAP_BP = 1000

ACTION_LABELS = {"普攻": "ATTACK", "防御": "DEFEND", "调息": "MEDITATE"}
FORMATION_RULES = {
    "锋矢": {
        "front_damage_bp": 800,
        "front_taken_bp": 500,
        "defense_bp": 0,
        "speed_bp": 0,
        "healing_bp": 0,
    },
    "玄武": {
        "front_damage_bp": 0,
        "front_taken_bp": 0,
        "defense_bp": 800,
        "speed_bp": -300,
        "healing_bp": 0,
    },
    "流云": {
        "front_damage_bp": 0,
        "front_taken_bp": 0,
        "defense_bp": 0,
        "speed_bp": 800,
        "healing_bp": -500,
    },
}


def apply_basis_points(value, modifier_bp):
    """按基点向下取整，确保所有阵法倍率使用同一舍入口径。"""
    return int(value) * int(modifier_bp) // BASIS_POINTS


def parse_action(value):
    """将玩家文本转换为可落库的 action type/payload。"""
    text = str(value or "").strip()
    action_type = ACTION_LABELS.get(text)
    if action_type:
        return {"type": action_type, "payload": {}}
    if text.startswith("技能"):
        slot_text = text[len("技能"):].strip()
        if slot_text in {"1", "2", "3"}:
            return {"type": "SKILL", "payload": {"skill_slot": int(slot_text)}}
    return None


def normalize_action(value):
    parsed = parse_action(value)
    return parsed["type"] if parsed else None


def _action_dict(value):
    if isinstance(value, dict):
        action_type = str(value.get("type") or value.get("action_type") or "DEFEND").upper()
        payload = value.get("payload") or {}
        return {"type": action_type, "payload": dict(payload) if isinstance(payload, dict) else {}}
    action_type = str(value or "DEFEND").upper()
    return {"type": action_type, "payload": {}}


def round_should_resolve(actions, alive_members, deadline_expired=False):
    """只有存活 UID 的动作计入齐备；死亡成员和脏 action 不会提前推进。"""
    if deadline_expired:
        return True
    alive_uids = {str(member["uid"]) for member in alive_members if int(member.get("hp", 0)) > 0 or "hp" not in member}
    submitted_uids = {str(uid) for uid in actions}
    return bool(alive_uids) and alive_uids.issubset(submitted_uids)


def _formation_rule(formation):
    return FORMATION_RULES.get(str(formation or "锋矢"), FORMATION_RULES["锋矢"])


def _buff_total(entity, positive_types, negative_types=()):
    total = 0
    for buff in entity.get("buffs", []):
        buff_type = str(buff.get("type") or "")
        value = max(0, int(buff.get("value", 0) or 0))
        if buff_type in positive_types:
            total += value
        elif buff_type in negative_types:
            total -= value
    return max(-90, min(300, total))


def effective_attack(entity):
    modifier = _buff_total(entity, {"gongji_up", "attack_up", "all_stat_up"}, {"gongji_down", "attack_down"})
    pve_bp = max(0, min(PVE_STAT_BONUS_CAP_BP, int(entity.get("pve_attack_bp", 0) or 0)))
    return max(1, apply_basis_points(entity.get("attack", 1), BASIS_POINTS + modifier * 100 + pve_bp))


def effective_defense(entity, formation=None):
    modifier = _buff_total(entity, {"fangyu_up", "defense_up", "all_stat_up"}, {"fangyu_down", "defense_down"})
    formation_bp = _formation_rule(formation)["defense_bp"] if entity.get("side") == "PLAYER" else 0
    pve_bp = max(0, min(PVE_STAT_BONUS_CAP_BP, int(entity.get("pve_defense_bp", 0) or 0)))
    return max(0, apply_basis_points(entity.get("defense", 0), BASIS_POINTS + modifier * 100 + formation_bp + pve_bp))


def effective_speed(entity, formation=None):
    modifier = _buff_total(entity, {"sudu_up", "speed_up", "all_stat_up"}, {"sudu_down", "speed_down"})
    formation_bp = _formation_rule(formation)["speed_bp"] if entity.get("side") == "PLAYER" else 0
    pve_bp = max(0, min(PVE_STAT_BONUS_CAP_BP, int(entity.get("pve_speed_bp", 0) or 0)))
    return max(0, apply_basis_points(entity.get("speed", 0), BASIS_POINTS + modifier * 100 + formation_bp + pve_bp))


def damage_after_defense(
    attack,
    defense,
    random_factor_bp=BASIS_POINTS,
    damage_modifier_bp=BASIS_POINTS,
    incoming_modifier_bp=BASIS_POINTS,
    pierce_bp=0,
):
    """统一防御衰减：damage = atk * 800 / (def + 800)，再合并伤害倍率。"""
    attack = max(1, int(attack))
    defense = max(0, int(defense))
    pierce_bp = max(0, min(9000, int(pierce_bp)))
    reduced_defense = apply_basis_points(defense, BASIS_POINTS - pierce_bp)
    numerator = (
        attack
        * DEFENSE_CONSTANT
        * max(0, int(random_factor_bp))
        * max(0, int(damage_modifier_bp))
        * max(0, int(incoming_modifier_bp))
    )
    denominator = (reduced_defense + DEFENSE_CONSTANT) * BASIS_POINTS ** 3
    return max(1, numerator // max(1, denominator))


def select_front_target(candidates, requested_id=None):
    """有存活前列时锁定前列；前列全灭后才允许回退到后列。"""
    living = [item for item in candidates if int(item.get("hp", 0)) > 0]
    if not living:
        return None
    front = [item for item in living if item.get("position", "前列") == "前列"]
    allowed = front or living
    if requested_id is not None:
        requested = str(requested_id)
        for item in allowed:
            if requested in {str(item.get("id")), str(item.get("uid")), str(item.get("entity_id"))}:
                return item
    return min(
        allowed,
        key=lambda item: (
            int(item.get("hp", 0)) / max(1, int(item.get("max_hp", 1))),
            str(item.get("entity_id") or item.get("uid") or item.get("id")),
        ),
    )


def _prepare_member(raw, formation):
    member = dict(raw)
    member.setdefault("position", "前列")
    member.setdefault("defense", 0)
    member.setdefault("speed", 0)
    member.setdefault("mana", int(member.get("max_mana", 0) or 0))
    member.setdefault("max_mana", int(member.get("mana", 0) or 0))
    member.setdefault("skills", [])
    member.setdefault("cooldowns", {})
    member.setdefault("buffs", [])
    member.setdefault("party_damage_bp", 0)
    member.setdefault("pve_attack_bp", 0)
    member.setdefault("pve_defense_bp", 0)
    member.setdefault("pve_speed_bp", 0)
    member.setdefault("effect_sources", [])
    member.setdefault("spirit_beast", None)
    member["side"] = "PLAYER"
    member["entity_id"] = str(member.get("entity_id") or f"player:{member['uid']}")
    member["formation"] = formation
    member["defending"] = False
    return member


def _prepare_enemy(raw, index=0):
    enemy = dict(raw)
    enemy.setdefault("id", f"enemy-{index + 1}")
    enemy.setdefault("position", "前列" if index == 0 else "后列")
    enemy.setdefault("defense", max(0, int(enemy.get("attack", 1)) // 2))
    enemy.setdefault("speed", 0)
    enemy.setdefault("buffs", [])
    enemy["side"] = "ENEMY"
    enemy["entity_id"] = str(enemy.get("entity_id") or enemy["id"])
    enemy["defending"] = False
    return enemy


def upgrade_snapshot(raw_snapshot):
    """把 v1 活跃快照投影为 v2 reader 视图，不原地破坏旧数据。"""
    source = json.loads(raw_snapshot) if isinstance(raw_snapshot, str) else raw_snapshot
    snapshot = json.loads(json.dumps(source or {}, ensure_ascii=False))
    stored_version = int(snapshot.get("schema_version", 1) or 1)
    source_version = int(snapshot.get("source_schema_version", stored_version) or stored_version)
    formation = snapshot.get("formation") or (snapshot.get("enemy") or {}).get("formation") or "锋矢"
    members = [_prepare_member(member, formation) for member in snapshot.get("members", [])]
    raw_enemies = snapshot.get("enemies")
    if not isinstance(raw_enemies, list):
        raw_enemy = snapshot.get("enemy") or {}
        raw_enemies = [raw_enemy] if raw_enemy else []
    enemies = [_prepare_enemy(enemy, index) for index, enemy in enumerate(raw_enemies)]
    snapshot.update(
        {
            "schema_version": SCHEMA_VERSION,
            "source_schema_version": source_version,
            "rule_version": snapshot.get("rule_version") or ("party-pve.v1" if source_version < 2 else RULE_VERSION),
            "formation": formation,
            "members": members,
            "enemies": enemies,
        }
    )
    snapshot.pop("enemy", None)
    return snapshot


def _resolve_legacy_round(members, actions, enemy, seed):
    """只供已经 ACTIVE 的 v1 快照续战；保持旧回合语义直至该场结束。"""
    rng = Random(sha256(str(seed).encode()).hexdigest())
    members = [dict(member) for member in members]
    enemy = dict(enemy)
    logs = []
    for member in members:
        member["defending"] = False
    for member in sorted(
        (item for item in members if int(item.get("hp", 0)) > 0),
        key=lambda item: (-int(item.get("speed", 0)), item["uid"]),
    ):
        action = _action_dict(actions.get(str(member["uid"]), "DEFEND"))["type"]
        if action == "DEFEND":
            member["defending"] = True
            logs.append(f"{member['name']}采取防御姿态。")
        elif action == "MEDITATE":
            member["mana"] = min(int(member.get("max_mana", 0)), int(member.get("mana", 0)) + 25)
            logs.append(f"{member['name']}调息回灵。")
        else:
            damage = max(1, int(int(member.get("attack", 1)) * (0.9 + rng.random() * 0.2)))
            enemy["hp"] = int(enemy.get("hp", 0)) - damage
            logs.append(f"{member['name']}造成{damage}点伤害。")
        if int(enemy.get("hp", 0)) <= 0:
            break
    if int(enemy.get("hp", 0)) > 0:
        living = [item for item in members if int(item.get("hp", 0)) > 0]
        if living:
            target = min(
                living,
                key=lambda item: (
                    int(item["hp"]) / max(1, int(item.get("max_hp", 1))),
                    item["uid"],
                ),
            )
            damage = max(1, int(int(enemy.get("attack", 1)) * (0.9 + rng.random() * 0.2)))
            if target.get("defending"):
                damage = max(1, int(damage * 0.55))
            target["hp"] = int(target["hp"]) - damage
            logs.append(f"{enemy['name']}攻击{target['name']}，造成{damage}点伤害。")
    return members, enemy, logs


def _skill_for_action(member, action):
    slot = action.get("payload", {}).get("skill_slot")
    try:
        slot = int(slot)
    except (TypeError, ValueError):
        return None
    return next((skill for skill in member.get("skills", []) if int(skill.get("slot", 0)) == slot), None)


def validate_action_for_member(member, action):
    """验证存活、技能槽、法力与冷却；handler 与 resolver 共用。"""
    if int(member.get("hp", 0)) <= 0:
        return "你已力竭，本回合无需提交行动。"
    action = _action_dict(action)
    if action["type"] != "SKILL":
        return None
    skill = _skill_for_action(member, action)
    if not skill:
        return "该技能槽未装备技能。"
    cooldown = int(member.get("cooldowns", {}).get(str(skill["id"]), 0) or 0)
    if cooldown > 0:
        return f"技能「{skill['name']}」冷却中（剩余 {cooldown} 回合）。"
    mana_cost = max(0, int(skill.get("mana_cost", 0) or 0))
    if int(member.get("mana", 0)) < mana_cost:
        return f"法力不足：「{skill['name']}」需要 {mana_cost} MP，当前仅 {member.get('mana', 0)} MP。"
    return None


def _random_factor_bp(rng):
    return 9000 + rng.randrange(0, 2001)


def _damage_modifiers(member, formation):
    rule = _formation_rule(formation)
    formation_bonus = rule["front_damage_bp"] if member.get("position") == "前列" else 0
    return BASIS_POINTS + formation_bonus + int(member.get("party_damage_bp", 0) or 0)


def _incoming_modifier(target, formation):
    rule = _formation_rule(formation)
    return BASIS_POINTS + (rule["front_taken_bp"] if target.get("position") == "前列" else 0)


def _pierce_bp(entity):
    value = _buff_total(entity, {"pofang_up", "pierce_up"}, {"pofang_down", "pierce_down"})
    return max(0, min(9000, int(entity.get("pierce", 0) or 0) + value * 100))


def _spirit_synergy(entity):
    beast = entity.get("spirit_beast") or {}
    synergy = beast.get("synergy") or {}
    return beast, synergy


def _trigger_spirit_synergy(entity, round_no, event_type, **event_data):
    beast, synergy = _spirit_synergy(entity)
    max_triggers = max(0, int(synergy.get("max_triggers", 0) or 0))
    triggered = max(0, int(beast.get("triggered", 0) or 0))
    if not synergy or triggered >= max_triggers:
        return False
    beast["triggered"] = triggered + 1
    event = {"round": max(0, int(round_no or 0)), "type": event_type}
    event.update(event_data)
    beast.setdefault("events", []).append(event)
    entity["spirit_beast"] = beast
    return True


def _trigger_reincarnation_heal(entity, round_no, logs):
    beast, synergy = _spirit_synergy(entity)
    if synergy.get("code") != "REINCARNATION_HEALER" or int(entity.get("hp", 0)) <= 0:
        return False
    if int(beast.get("triggered", 0) or 0) >= int(synergy.get("max_triggers", 0) or 0):
        return False
    max_hp = max(1, int(entity.get("max_hp", 1)))
    threshold = max(1, min(100, int(synergy.get("threshold", 30) or 30)))
    if int(entity["hp"]) * 100 > max_hp * threshold:
        return False
    heal_percent = max(1, min(100, int(synergy.get("heal_percent", 5) or 5)))
    healing = max(1, apply_basis_points(max_hp, heal_percent * 100))
    before = int(entity["hp"])
    entity["hp"] = min(max_hp, before + healing)
    actual = int(entity["hp"]) - before
    if _trigger_spirit_synergy(
        entity,
        round_no,
        "LOW_HP_HEAL",
        value=actual,
        hp_after=int(entity["hp"]),
    ):
        logs.append(f"{entity['name']}触发「{synergy.get('label', '轮回协同')}」，回复{actual}点气血。")
        return True
    return False


def _shield_reduction_bp(entity):
    shield_percent = _buff_total(entity, {"shield", "gedang"})
    return max(0, min(8000, shield_percent * 100))


def _apply_periodic_effects(entity, logs, round_no=0):
    if int(entity.get("hp", 0)) <= 0:
        return
    for buff in list(entity.get("buffs", [])):
        buff_type = str(buff.get("type") or "")
        value = max(0, int(buff.get("value", 0) or 0))
        if buff_type in {"HP_down", "hp_down", "burn"} and value:
            damage = max(1, apply_basis_points(entity.get("max_hp", 1), value * 100))
            entity["hp"] = max(0, int(entity["hp"]) - damage)
            logs.append(f"{entity['name']}受到「{buff.get('name') or '持续伤害'}」{damage}点伤害。")
        elif buff_type in {"HP_up", "hp_up", "heal_over_time"} and value:
            healing = max(1, apply_basis_points(entity.get("max_hp", 1), value * 100))
            before = int(entity["hp"])
            entity["hp"] = min(int(entity.get("max_hp", before)), before + healing)
            actual = int(entity["hp"]) - before
            if actual:
                logs.append(f"{entity['name']}由「{buff.get('name') or '持续恢复'}」回复{actual}点气血。")
    if entity.get("side") == "PLAYER":
        _trigger_reincarnation_heal(entity, round_no, logs)


def _is_stunned(entity):
    return any(str(buff.get("type")) in {"un_action", "stun"} for buff in entity.get("buffs", []))


def _append_buff(target, skill):
    buff_type = skill.get("buff_type")
    duration = max(0, int(skill.get("buff_duration", 0) or 0))
    if not buff_type or duration <= 0:
        return False
    target.setdefault("buffs", []).append(
        {
            "type": str(buff_type),
            "value": int(skill.get("buff_value", 0) or 0),
            "duration": duration,
            "name": skill.get("buff_name") or skill.get("name") or "技能效果",
            "fresh": True,
        }
    )
    return True


def _tick_buffs(entities):
    for entity in entities:
        kept = []
        for buff in entity.get("buffs", []):
            if buff.pop("fresh", False):
                kept.append(buff)
                continue
            buff["duration"] = int(buff.get("duration", 0) or 0) - 1
            if buff["duration"] > 0:
                kept.append(buff)
        entity["buffs"] = kept


def _tick_cooldowns(member):
    member["cooldowns"] = {
        str(skill_id): max(0, int(turns) - 1)
        for skill_id, turns in member.get("cooldowns", {}).items()
        if int(turns) - 1 > 0
    }


def _member_attack(member, target, rng, formation, logs, skill=None):
    attack = effective_attack(member)
    if skill:
        value = max(0, int(skill.get("value", 0) or 0))
        if int(skill.get("is_percent", 0) or 0):
            attack = max(1, attack * value // 100)
        else:
            attack += value
    damage = damage_after_defense(
        attack,
        effective_defense(target),
        _random_factor_bp(rng),
        _damage_modifiers(member, formation),
        BASIS_POINTS,
        _pierce_bp(member),
    )
    target["hp"] = max(0, int(target["hp"]) - damage)
    if skill:
        logs.append(f"{member['name']}施展「{skill['name']}」攻击{target['name']}，造成{damage}点伤害。")
    else:
        logs.append(f"{member['name']}攻击{target['name']}，造成{damage}点伤害。")
    return damage


def _execute_skill(member, action, members, enemies, rng, formation, logs, round_no=0):
    skill = _skill_for_action(member, action)
    error = validate_action_for_member(member, action)
    if error or not skill:
        member["defending"] = True
        logs.append(f"{member['name']}的技能未能发动，系统托管为防御。")
        return
    mana_cost = max(0, int(skill.get("mana_cost", 0) or 0))
    member["mana"] = max(0, int(member.get("mana", 0)) - mana_cost)
    cooldown = max(0, int(skill.get("cooldown", 0) or 0))
    if cooldown:
        member.setdefault("cooldowns", {})[str(skill["id"])] = cooldown
    skill_type = int(skill.get("skill_type", 1) or 1)
    target = None
    if skill_type in (1, 4):
        target = select_front_target(enemies, action.get("payload", {}).get("target_id"))
        if not target:
            return
        _member_attack(member, target, rng, formation, logs, skill=skill)
    elif skill_type == 3:
        living = [item for item in members if int(item.get("hp", 0)) > 0]
        requested_uid = action.get("payload", {}).get("target_uid")
        target = next((item for item in living if requested_uid is not None and str(item["uid"]) == str(requested_uid)), None)
        if target is None and living:
            target = min(living, key=lambda item: (int(item["hp"]) / max(1, int(item["max_hp"])), str(item["uid"])))
        if target:
            value = max(0, int(skill.get("value", 0) or 0))
            raw_heal = apply_basis_points(target["max_hp"], value * 100) if int(skill.get("is_percent", 0) or 0) else value
            healing_status_bp = _buff_total(
                target, {"healing_up", "heal_up"}, {"healing_down", "heal_down"}
            ) * 100
            healing_bp = max(
                1000,
                BASIS_POINTS + _formation_rule(formation)["healing_bp"] + healing_status_bp,
            )
            healing = max(1, apply_basis_points(raw_heal, healing_bp))
            before = int(target["hp"])
            target["hp"] = min(int(target["max_hp"]), before + healing)
            logs.append(f"{member['name']}施展「{skill['name']}」，为{target['name']}回复{int(target['hp']) - before}点气血。")
    else:
        target = member
        logs.append(f"{member['name']}施展「{skill['name']}」，凝聚护身之势。")

    buff_skill = skill
    if skill_type == 2 and not skill.get("buff_type"):
        # 老技能若没有独立 buff 配置，仍按其明示 value 形成一回合防御增益。
        buff_skill = dict(skill)
        buff_skill.update(
            {
                "buff_type": "fangyu_up",
                "buff_value": max(1, min(100, int(skill.get("value", 0) or 0))),
                "buff_duration": 1,
                "buff_target": 1,
                "buff_name": skill.get("name"),
            }
        )
    normalized_buff_type = normalize_skill_buff_type(
        buff_skill.get("buff_type"),
        skill.get("name"),
    )
    if normalized_buff_type != buff_skill.get("buff_type"):
        buff_skill = dict(buff_skill)
        buff_skill["buff_type"] = normalized_buff_type
    beast, synergy = _spirit_synergy(member)
    buff_type = str(buff_skill.get("buff_type") or "")
    if (
        target
        and synergy.get("code") == "FIRE_STRIKER"
        and buff_type in {"HP_down", "hp_down", "burn"}
        and int(buff_skill.get("buff_duration", 0) or 0) > 0
    ):
        duration_bonus = max(0, min(2, int(synergy.get("burn_duration_bonus", 1) or 1)))
        if duration_bonus and _trigger_spirit_synergy(
            member,
            round_no,
            "BURN_DURATION",
            value=duration_bonus,
            skill_id=int(skill["id"]),
        ):
            buff_skill = dict(buff_skill)
            buff_skill["buff_duration"] = int(buff_skill.get("buff_duration", 0) or 0) + duration_bonus
            logs.append(f"{member['name']}触发「{synergy.get('label', '异火协同')}」。")
    if (
        target
        and synergy.get("code") == "TREASURE_GUARDIAN"
        and buff_type in {"shield", "gedang"}
        and int(buff_skill.get("buff_duration", 0) or 0) > 0
    ):
        shield_bonus = max(0, min(10, int(synergy.get("shield_bonus", 0) or 0)))
        if shield_bonus and _trigger_spirit_synergy(
            member,
            round_no,
            "SHIELD_BONUS",
            value=shield_bonus,
            skill_id=int(skill["id"]),
        ):
            buff_skill = dict(buff_skill)
            buff_skill["buff_value"] = int(buff_skill.get("buff_value", 0) or 0) + shield_bonus
            logs.append(f"{member['name']}触发「{synergy.get('label', '掌天协同')}」。")
    target_code = normalize_buff_target(
        buff_skill.get("buff_target"),
        buff_type=buff_type,
    )
    buff_target = member if target_code == 1 else target
    if buff_target and _append_buff(buff_target, buff_skill):
        logs.append(f"{buff_target['name']}获得「{skill.get('buff_name') or skill['name']}」效果。")


def resolve_party_round(members, actions, enemy, seed, formation=None, round_no=0):
    """确定性统一速度结算；兼容旧调用的单个 enemy 字典。"""
    rng = Random(sha256(str(seed).encode()).hexdigest())
    legacy_enemy = isinstance(enemy, dict)
    inferred_formation = formation or (enemy.get("formation") if legacy_enemy else None) or "锋矢"
    resolved_members = [_prepare_member(item, inferred_formation) for item in json.loads(json.dumps(members, ensure_ascii=False))]
    raw_enemies = [enemy] if legacy_enemy else list(enemy or [])
    enemies = [_prepare_enemy(item, index) for index, item in enumerate(json.loads(json.dumps(raw_enemies, ensure_ascii=False)))]
    logs = []

    for member in resolved_members:
        member["defending"] = False
        _tick_cooldowns(member)
    for foe in enemies:
        foe["defending"] = False

    turns = []
    for member in resolved_members:
        if int(member.get("hp", 0)) > 0:
            turns.append((-effective_speed(member, inferred_formation), member["entity_id"], "PLAYER", member))
    for foe in enemies:
        if int(foe.get("hp", 0)) > 0:
            turns.append((-effective_speed(foe), foe["entity_id"], "ENEMY", foe))

    for _, _, side, actor in sorted(turns, key=lambda item: (item[0], item[1])):
        if int(actor.get("hp", 0)) <= 0:
            continue
        _apply_periodic_effects(actor, logs, round_no)
        if int(actor.get("hp", 0)) <= 0:
            continue
        if _is_stunned(actor):
            logs.append(f"{actor['name']}受到控制，本回合无法行动。")
            continue
        if side == "PLAYER":
            if not any(int(item.get("hp", 0)) > 0 for item in enemies):
                break
            action = _action_dict(actions.get(str(actor["uid"]), "DEFEND"))
            if action["type"] == "DEFEND":
                actor["defending"] = True
                logs.append(f"{actor['name']}采取防御姿态。")
            elif action["type"] == "MEDITATE":
                recovery = max(1, apply_basis_points(actor.get("max_mana", 0), MEDITATE_RECOVERY_BP))
                before = int(actor.get("mana", 0))
                actor["mana"] = min(int(actor.get("max_mana", before)), before + recovery)
                logs.append(f"{actor['name']}调息回灵，恢复{int(actor['mana']) - before} MP。")
            elif action["type"] == "SKILL":
                _execute_skill(
                    actor,
                    action,
                    resolved_members,
                    enemies,
                    rng,
                    inferred_formation,
                    logs,
                    round_no,
                )
            else:
                target = select_front_target(enemies, action.get("payload", {}).get("target_id"))
                if target:
                    _member_attack(actor, target, rng, inferred_formation, logs)
        else:
            target = select_front_target(resolved_members)
            if not target:
                break
            damage = damage_after_defense(
                effective_attack(actor),
                effective_defense(target, inferred_formation),
                _random_factor_bp(rng),
                BASIS_POINTS,
                _incoming_modifier(target, inferred_formation),
                _pierce_bp(actor),
            )
            if target.get("defending"):
                damage = max(1, apply_basis_points(damage, 5500))
            shield_bp = _shield_reduction_bp(target)
            if shield_bp:
                damage = max(1, apply_basis_points(damage, BASIS_POINTS - shield_bp))
            target["hp"] = max(0, int(target["hp"]) - damage)
            logs.append(f"{actor['name']}攻击{target['name']}，造成{damage}点伤害。")
            _trigger_reincarnation_heal(target, round_no, logs)

    _tick_buffs(resolved_members + enemies)
    for member in resolved_members:
        member.pop("formation", None)
    result_enemy = enemies[0] if legacy_enemy else enemies
    return resolved_members, result_enemy, logs


def _session_fields(session):
    """集中解包 7 列 session，避免旧 handler 的 5/7 列错位。"""
    if not session or len(session) != 7:
        raise ValueError("队伍战斗会话字段不完整")
    return {
        "id": session[0],
        "party_id": session[1],
        "round_no": int(session[2]),
        "state": session[3],
        "snapshot_json": session[4],
        "deadline_at": session[5],
        "deadline_expired": bool(session[6]),
    }


def normalize_request_id(request_id):
    """QQ 消息 ID 作为业务幂等键；限制长度与迁移列一致。"""
    value = str(request_id or "").strip()
    return value[:128] if value else None


async def _party_for_battle(uid, group_openid, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(f"""
        SELECT p.id, p.group_openid, p.leader_uid, p.formation, p.state
        FROM party p JOIN party_member pm ON pm.party_id = p.id
        WHERE pm.uid = %s AND pm.member_state = 'ACTIVE' AND p.group_openid = %s
          AND p.state IN ('LOBBY', 'BATTLE')
        ORDER BY p.created_at DESC LIMIT 1{suffix}
    """, (uid, group_openid))
    return await cursor.fetchone()


async def _load_session(uid, cursor, lock=False, group_openid=None):
    suffix = " FOR UPDATE" if lock else ""
    group_clause = " AND p.group_openid = %s" if group_openid is not None else ""
    params = (uid, group_openid) if group_openid is not None else (uid,)
    await cursor.execute(f"""
        SELECT b.id, b.party_id, b.round_no, b.state, b.snapshot_json,
               b.deadline_at, b.deadline_at <= NOW() AS deadline_expired
        FROM party_battle_session b JOIN party_battle_member bm ON bm.session_id = b.id
        JOIN party p ON p.id = b.party_id
        WHERE bm.uid = %s AND b.state = 'ACTIVE'
          {group_clause}
        ORDER BY b.created_at DESC LIMIT 1{suffix}
    """, params)
    return await cursor.fetchone()


async def _load_party_session(party_id, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(f"""
        SELECT id, party_id, round_no, state, snapshot_json,
               deadline_at, deadline_at <= NOW() AS deadline_expired
        FROM party_battle_session
        WHERE party_id = %s AND state = 'ACTIVE'
        ORDER BY created_at DESC LIMIT 1{suffix}
    """, (party_id,))
    return await cursor.fetchone()


async def _find_action_request(uid, group_openid, request_id, cursor, session_id=None, lock=False):
    """查找已处理消息；独立账本可保留同回合内每一次改动作请求。"""
    suffix = " FOR UPDATE" if lock else ""
    session_clause = " AND req.session_id = %s" if session_id else ""
    params = [uid, request_id, group_openid]
    if session_id:
        params.append(session_id)
    await cursor.execute(f"""
        SELECT req.session_id, req.round_no, b.round_no, b.state, b.snapshot_json
        FROM party_battle_action_request req
        JOIN party_battle_session b ON b.id = req.session_id
        JOIN party p ON p.id = b.party_id
        WHERE req.uid = %s AND req.request_id = %s AND p.group_openid = %s
          {session_clause}
        ORDER BY req.created_at DESC LIMIT 1{suffix}
    """, tuple(params))
    return await cursor.fetchone()


async def _replay_action_request(cursor, request_row, uid):
    session_id, action_round, current_round, state, raw_snapshot = request_row
    if state == "ACTIVE":
        actions = await _load_round_actions(cursor, session_id, current_round)
        notice = (
            f"该消息已在第 {action_round} 回合处理，未重复提交到第 {current_round} 回合。"
        )
        return _render(session_id, current_round, raw_snapshot, set(actions), notice, uid)
    state_text = {"COMPLETED": "胜利", "FAILED": "失败", "CANCELLED": "已取消"}.get(state, "已结束")
    return {
        "type": "markdown",
        "content": (
            f"该行动消息已在第 {action_round} 回合处理；本场战斗{state_text}，"
            "未重复提交行动或结算奖励。\n\n"
            "<qqbot-cmd-input text='队伍' show='返回队伍' />"
        ),
    }


def _to_int(value, default=0):
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


async def _load_skill(cursor, uid, skill_instance_id, slot, effect_bonus_bp=0):
    await cursor.execute("""
        SELECT id, is_data_skill, skill_id, skill_name, skill_type, `value`,
               is_percent, cooldown, mana_cost, skill_1
        FROM user_skill WHERE id = %s AND uid = %s LIMIT 1
    """, (skill_instance_id, uid))
    row = await cursor.fetchone()
    if not row:
        return None
    (
        user_skill_id, is_data_skill, data_skill_id, skill_name, skill_type,
        value, is_percent, cooldown, mana_cost, source_skill_id,
    ) = row
    buff_type = None
    buff_value = 0
    buff_duration = 0
    buff_target = 2
    buff_name = ""
    if int(is_data_skill or 0) == 1 and data_skill_id:
        await cursor.execute("""
            SELECT skill_name, skill_type, `value`, is_percent, cooldown, mana_cost,
                   buff_type, buff_value, buff_duration, buff_target, buff_name
            FROM data_skill WHERE id = %s LIMIT 1
        """, (data_skill_id,))
        detail = await cursor.fetchone()
        if detail:
            (
                skill_name, skill_type, value, is_percent, cooldown, mana_cost,
                buff_type, buff_value, buff_duration, buff_target, buff_name,
            ) = detail
    elif source_skill_id:
        await cursor.execute("""
            SELECT buff_type, buff_value, buff_duration, buff_target, buff_name
            FROM data_skill WHERE id = %s LIMIT 1
        """, (source_skill_id,))
        detail = await cursor.fetchone()
        if detail:
            buff_type, buff_value, buff_duration, buff_target, buff_name = detail

    buff_type = normalize_skill_buff_type(buff_type, skill_name)
    skill_effect_bp = BASIS_POINTS + max(0, min(450, int(effect_bonus_bp or 0)))
    return {
        "id": int(user_skill_id),
        "slot": int(slot),
        "name": str(skill_name),
        "skill_type": _to_int(skill_type, 1),
        "value": apply_basis_points(_to_int(value), skill_effect_bp),
        "is_percent": _to_int(is_percent),
        "cooldown": max(0, _to_int(cooldown)),
        "mana_cost": max(0, _to_int(mana_cost)),
        "buff_type": buff_type,
        "buff_value": apply_basis_points(_to_int(buff_value), skill_effect_bp),
        "buff_duration": max(0, _to_int(buff_duration)),
        "buff_target": normalize_buff_target(buff_target, buff_type=buff_type),
        "buff_name": str(buff_name or ""),
    }


async def _build_member_snapshot(cursor, role_row, formation, season_effect=None):
    (
        uid, role_id, name, qixue, gongji, fangyu, sudu, fali,
        baoji, baoshang, shanbi, mingzhong, pofang, xixue,
        gongji_jc, fangyu_jc, qixue_jc,
        skill1_id, skill2_id, skill3_id, position,
    ) = role_row
    from Game_main.g7_equip import calc_role_equip_bonus
    from Game_main.g12_spirit_beast import get_active_beast_snapshot
    from Game_main.g14_estate import build_estate_effect_snapshot, read_estate_levels
    from Game_main.g15_expedition import get_causal_mark_snapshot
    from Game_main.g19_sect import get_active_research

    equip_bonus = await calc_role_equip_bonus(role_id, cursor)
    estate_levels = await read_estate_levels(uid, cursor, ensure_rows=False)
    estate_snapshot = build_estate_effect_snapshot(estate_levels)
    skill_effect_bp = int(estate_snapshot["effects"].get("pve_skill_effect_bonus_bp", 0) or 0)
    causal_effect = await get_causal_mark_snapshot(uid, cursor)
    research = await get_active_research(uid, cursor)
    spirit_beast = await get_active_beast_snapshot(uid, cursor, role_id)
    party_damage_bp = 300 if research and research.get("research_type") == "阵法" else 0
    season_effect = dict(season_effect or {})
    pve_attack_bp = min(
        PVE_STAT_BONUS_CAP_BP,
        max(0, int(causal_effect.get("attack_bp", 0) or 0))
        + max(0, int(season_effect.get("attack_bp", 0) or 0)),
    )
    pve_defense_bp = min(
        PVE_STAT_BONUS_CAP_BP,
        max(0, int(causal_effect.get("defense_bp", 0) or 0))
        + max(0, int(season_effect.get("defense_bp", 0) or 0)),
    )
    pve_speed_bp = min(
        PVE_STAT_BONUS_CAP_BP,
        max(0, int(season_effect.get("speed_bp", 0) or 0)),
    )
    effect_sources = []
    if causal_effect.get("marks"):
        effect_sources.append("因果印记：" + "、".join(causal_effect["marks"]))
    if season_effect.get("active"):
        effect_sources.append("赛季天象：" + str(season_effect.get("name") or season_effect.get("rule_code")))
    if party_damage_bp:
        effect_sources.append("宗门研究：阵法")
    if skill_effect_bp:
        effect_sources.append(f"藏经阁：技能效果 +{skill_effect_bp / 100:g}%")
    initial_buffs = []
    if spirit_beast:
        beast_bonus = spirit_beast.get("combat_bonus") or {}
        if beast_bonus.get("buff_type"):
            initial_buffs.append(
                {
                    "type": str(beast_bonus["buff_type"]),
                    "value": max(0, int(beast_bonus.get("value", 0) or 0)),
                    "duration": 99,
                    "name": str(beast_bonus.get("label") or spirit_beast.get("name") or "灵兽灵契"),
                }
            )
        source = f"灵兽：{spirit_beast.get('name', '灵契')}"
        if (spirit_beast.get("synergy") or {}).get("label"):
            source += "·" + str(spirit_beast["synergy"]["label"])
        effect_sources.append(source)

    attack = int(int(gongji) * (100 + float(gongji_jc or 0)) / 100) + int(equip_bonus.get("gongji", 0) or 0)
    defense = int(int(fangyu) * (100 + float(fangyu_jc or 0)) / 100) + int(equip_bonus.get("fangyu", 0) or 0)
    max_hp = int(int(qixue) * (100 + float(qixue_jc or 0)) / 100) + int(equip_bonus.get("qixue", 0) or 0)
    max_mana = max(0, int(fali) + int(equip_bonus.get("fali", 0) or 0))
    speed = max(0, int(sudu) + int(equip_bonus.get("sudu", 0) or 0))
    critical = max(0, int(baoji) + int(equip_bonus.get("baoji", 0) or 0))
    critical_damage = max(0, int(baoshang) + int(equip_bonus.get("baoshang", 0) or 0))
    dodge = max(0, int(shanbi) + int(equip_bonus.get("shanbi", 0) or 0))
    hit = max(0, int(mingzhong) + int(equip_bonus.get("mingzhong", 0) or 0))
    pierce = max(0, int(pofang) + int(equip_bonus.get("pofang", 0) or 0))
    lifesteal = max(0, int(xixue) + int(equip_bonus.get("xixue", 0) or 0))
    skills = []
    for slot, skill_id in enumerate((skill1_id, skill2_id, skill3_id), 1):
        if skill_id:
            skill = await _load_skill(cursor, uid, skill_id, slot, skill_effect_bp)
            if skill:
                skills.append(skill)
    return {
        "uid": int(uid),
        "role_id": int(role_id),
        "name": str(name),
        "position": position if position in ("前列", "后列") else "后列",
        "hp": max(1, max_hp),
        "max_hp": max(1, max_hp),
        "attack": max(1, attack),
        "defense": max(0, defense),
        "speed": speed,
        "critical": critical,
        "critical_damage": critical_damage,
        "dodge": dodge,
        "hit": hit,
        "pierce": pierce,
        "lifesteal": lifesteal,
        "mana": max_mana,
        "max_mana": max_mana,
        "skills": skills,
        "cooldowns": {},
        "buffs": initial_buffs,
        "spirit_beast": spirit_beast,
        "party_damage_bp": party_damage_bp,
        "pve_attack_bp": pve_attack_bp,
        "pve_defense_bp": pve_defense_bp,
        "pve_speed_bp": pve_speed_bp,
        "effect_sources": effect_sources,
        "causal_mark_snapshot": causal_effect,
        "season_effect_snapshot": season_effect,
        "research_snapshot": research,
        "estate_effect_snapshot": estate_snapshot,
    }


def _build_enemies(members):
    total_hp = sum(int(item["max_hp"]) for item in members)
    average_attack = max(1, sum(int(item["attack"]) for item in members) // max(1, len(members)))
    average_defense = max(0, sum(int(item["defense"]) for item in members) // max(1, len(members)))
    average_speed = max(0, sum(int(item["speed"]) for item in members) // max(1, len(members)))
    front_hp = max(1, apply_basis_points(total_hp, 2500))
    back_hp = max(1, apply_basis_points(total_hp, 5000))
    return [
        {
            "id": "guard-front",
            "name": "道途护阵者",
            "position": "前列",
            "hp": front_hp,
            "max_hp": front_hp,
            "attack": max(1, apply_basis_points(average_attack, 3000)),
            "defense": max(0, apply_basis_points(average_defense, 3500)),
            "speed": max(0, apply_basis_points(average_speed, 9000)),
            "buffs": [],
        },
        {
            "id": "keeper-back",
            "name": "道途守关者",
            "position": "后列",
            "hp": back_hp,
            "max_hp": back_hp,
            "attack": max(1, apply_basis_points(average_attack, 4500)),
            "defense": max(0, apply_basis_points(average_defense, 4500)),
            "speed": max(0, apply_basis_points(average_speed, 8000)),
            "buffs": [],
        },
    ]


def _actions_from_rows(rows):
    actions = {}
    for row in rows:
        payload = {}
        if len(row) > 2 and row[2]:
            try:
                payload = json.loads(row[2]) if isinstance(row[2], str) else dict(row[2])
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
        actions[str(row[0])] = {"type": row[1], "payload": payload}
    return actions


async def _load_round_actions(cursor, session_id, round_no):
    await cursor.execute("""
        SELECT uid, action_type, action_payload
        FROM party_battle_action WHERE session_id = %s AND round_no = %s
    """, (session_id, round_no))
    return _actions_from_rows(await cursor.fetchall())


async def _record_round_result(cursor, session_id, round_no, result):
    await cursor.execute("""
        INSERT IGNORE INTO party_battle_round_log
            (session_id, round_no, result_json)
        VALUES (%s, %s, %s)
    """, (session_id, round_no, json.dumps(result, ensure_ascii=False)))


async def _finish_battle(cursor, session_id, party_id, state, snapshot, logs):
    await cursor.execute("""
        UPDATE party_battle_session
        SET state = %s, snapshot_json = %s, resolved_at = NOW()
        WHERE id = %s AND state = 'ACTIVE'
    """, (state, json.dumps(snapshot, ensure_ascii=False), session_id))
    await cursor.execute("UPDATE party SET state = 'LOBBY' WHERE id = %s AND state = 'BATTLE'", (party_id,))
    await cursor.execute("UPDATE party_member SET ready = 0 WHERE party_id = %s AND member_state = 'ACTIVE'", (party_id,))
    if state == "COMPLETED":
        for member in snapshot["members"]:
            await cursor.execute("""
                INSERT IGNORE INTO party_battle_reward
                    (session_id, uid, reward_type, amount)
                VALUES (%s, %s, 'LINGSHI', %s)
            """, (session_id, member["uid"], VICTORY_LINGSHI))
            if cursor.rowcount:
                await cursor.execute(
                    "UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s",
                    (VICTORY_LINGSHI, member["uid"]),
                )
        return {
            "type": "markdown",
            "content": "##### 🏆 队伍战斗胜利\n\n"
            + "\n".join(f"> {line}" for line in logs)
            + f"\n\n每位参战道友获得 **{VICTORY_LINGSHI} 灵石**。\n\n"
            + "<qqbot-cmd-input text='队伍' show='返回队伍' />",
        }
    return {
        "type": "markdown",
        "content": "##### 队伍战斗结束\n\n全员力竭，本次未获得胜利奖励。\n\n"
        + "<qqbot-cmd-input text='队伍' show='返回队伍' />",
    }


async def _resolve_round_if_ready(conn, cursor, session, actions):
    """在会话行锁内仅结算一次；回合日志和奖励均以稳定业务键幂等。"""
    fields = _session_fields(session)
    snapshot = upgrade_snapshot(fields["snapshot_json"])
    alive = [member for member in snapshot["members"] if int(member["hp"]) > 0]
    if not round_should_resolve(actions, alive, fields["deadline_expired"]):
        return None
    alive_uids = {str(member["uid"]) for member in alive}
    filtered_actions = {uid: action for uid, action in actions.items() if str(uid) in alive_uids}
    missing = [member["name"] for member in alive if str(member["uid"]) not in filtered_actions]
    if int(snapshot.get("source_schema_version", SCHEMA_VERSION)) < SCHEMA_VERSION:
        members, legacy_enemy, logs = _resolve_legacy_round(
            snapshot["members"],
            filtered_actions,
            snapshot["enemies"][0],
            f"{fields['id']}:{fields['round_no']}",
        )
        enemies = [legacy_enemy]
    else:
        members, enemies, logs = resolve_party_round(
            snapshot["members"],
            filtered_actions,
            snapshot["enemies"],
            f"{fields['id']}:{fields['round_no']}",
            snapshot["formation"],
        )
    snapshot.update({"members": members, "enemies": enemies})
    if missing:
        logs.insert(0, f"回合超时，{'、'.join(missing)}由系统托管为防御。")
    await _record_round_result(
        cursor,
        fields["id"],
        fields["round_no"],
        {"snapshot": snapshot, "logs": logs},
    )
    if not any(int(enemy["hp"]) > 0 for enemy in enemies):
        return await _finish_battle(cursor, fields["id"], fields["party_id"], "COMPLETED", snapshot, logs)
    if not any(int(member["hp"]) > 0 for member in members):
        return await _finish_battle(cursor, fields["id"], fields["party_id"], "FAILED", snapshot, logs)
    next_round = fields["round_no"] + 1
    await cursor.execute("""
        UPDATE party_battle_session
        SET round_no = %s, snapshot_json = %s,
            deadline_at = DATE_ADD(NOW(), INTERVAL 90 SECOND)
        WHERE id = %s AND state = 'ACTIVE' AND round_no = %s
    """, (next_round, json.dumps(snapshot, ensure_ascii=False), fields["id"], fields["round_no"]))
    return _render(fields["id"], next_round, snapshot, set(), "\n".join(logs))


def _render(session_id, round_no, snapshot, submitted, notice="", viewer_uid=None):
    snapshot = upgrade_snapshot(snapshot)
    output = f"##### ⚔️ 队伍战斗｜第 {round_no} 回合\n\n"
    output += f"**阵法：{snapshot['formation']}**｜规则 {snapshot['rule_version']}\n\n"
    for enemy in snapshot["enemies"]:
        output += f"> [敌方·{enemy['position']}] {enemy['name']}：HP {max(0, int(enemy['hp']))}/{enemy['max_hp']}\n"
    output += "\n"
    for member in snapshot["members"]:
        if int(member["hp"]) <= 0:
            state = "已力竭"
        else:
            state = "已提交" if str(member["uid"]) in submitted else "等待行动"
        output += (
            f"> [我方·{member['position']}] {member['name']}："
            f"HP {max(0, int(member['hp']))}/{member['max_hp']}｜"
            f"MP {max(0, int(member['mana']))}/{member['max_mana']}｜{state}\n"
        )
    if notice:
        output += f"\n> {notice}\n"
    output += "\n<qqbot-cmd-input text='队伍战斗行动 普攻' show='普攻' /> | <qqbot-cmd-input text='队伍战斗行动 防御' show='防御' /> | <qqbot-cmd-input text='队伍战斗行动 调息' show='调息' />\n"
    viewer = next((member for member in snapshot["members"] if viewer_uid is not None and str(member["uid"]) == str(viewer_uid)), None)
    if viewer and viewer.get("effect_sources"):
        output += "\n**本场冻结效果**\n"
        output += "> " + "｜".join(viewer["effect_sources"]) + "\n"
        output += (
            f"> 属性快照：攻击 +{viewer.get('pve_attack_bp', 0) / 100:g}%｜"
            f"防御 +{viewer.get('pve_defense_bp', 0) / 100:g}%｜"
            f"速度 +{viewer.get('pve_speed_bp', 0) / 100:g}%\n"
        )
    if viewer and viewer.get("skills"):
        output += "\n**你的技能**\n"
        for skill in viewer["skills"]:
            cooldown = int(viewer.get("cooldowns", {}).get(str(skill["id"]), 0) or 0)
            status = f"冷却{cooldown}回合" if cooldown else f"消耗{skill['mana_cost']}MP"
            output += f"<qqbot-cmd-input text='队伍战斗行动 技能 {skill['slot']}' show='{skill['name']}·{status}' />\n"
    output += "\n<qqbot-cmd-input text='队伍战斗状态' show='刷新战斗' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def party_battle_start(uid, qz, group_openid):
    if not group_openid:
        return {"type": "markdown", "content": "队伍战斗仅可在群聊中开启。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            party = await _party_for_battle(uid, group_openid, cursor, lock=True)
            if not party or party[2] != uid:
                return {"type": "markdown", "content": "请由已创建队伍的队长在群内开启队伍战斗。"}
            party_id, _, _, formation, party_state = party
            existing = await _load_party_session(party_id, cursor, lock=True)
            if existing:
                await cursor.execute("UPDATE party SET state = 'BATTLE' WHERE id = %s", (party_id,))
                await conn.commit()
                fields = _session_fields(existing)
                return _render(fields["id"], fields["round_no"], fields["snapshot_json"], set(), "队伍战斗已在进行，未重复创建场次。", uid)
            repaired_state = party_state == "BATTLE"
            if repaired_state:
                # 异常中断后没有 ACTIVE session，先恢复大厅状态再由队长重开。
                await cursor.execute("UPDATE party SET state = 'LOBBY' WHERE id = %s", (party_id,))
            await cursor.execute("""
                SELECT uid, ready, position FROM party_member
                WHERE party_id = %s AND member_state = 'ACTIVE'
                ORDER BY joined_at FOR UPDATE
            """, (party_id,))
            party_rows = await cursor.fetchall()
            if len(party_rows) < 2 or not all(row[1] for row in party_rows):
                if repaired_state:
                    await conn.commit()
                return {"type": "markdown", "content": "队伍战斗需要至少两名成员且全员准备。"}
            await cursor.execute("""
                SELECT r.uid, r.id, r.name, r.qixue, r.gongji, r.fangyu, r.sudu, r.fali,
                       r.baoji, r.baoshang, r.shanbi, r.mingzhong, r.pofang, r.xixue,
                       r.gongji_jc, r.fangyu_jc, r.qixue_jc,
                       r.skill1_id, r.skill2_id, r.skill3_id, pm.position
                FROM party_member pm JOIN user_role r ON r.uid = pm.uid AND r.is_chuzhan = 1
                WHERE pm.party_id = %s AND pm.member_state = 'ACTIVE'
                ORDER BY pm.joined_at
            """, (party_id,))
            role_rows = await cursor.fetchall()
            if len(role_rows) != len(party_rows):
                if repaired_state:
                    await conn.commit()
                return {"type": "markdown", "content": "请确保所有队员均有出战角色后再开启。"}
            from Game_main.g21_season import get_active_season_effect
            season_effect = await get_active_season_effect(cursor)
            members = [
                await _build_member_snapshot(cursor, row, formation, season_effect)
                for row in role_rows
            ]
            snapshot = {
                "schema_version": SCHEMA_VERSION,
                "rule_version": RULE_VERSION,
                "formation": formation,
                "season_effect_snapshot": season_effect,
                "members": members,
                "enemies": _build_enemies(members),
            }
            session_id = uuid4().hex
            await cursor.execute("""
                INSERT INTO party_battle_session
                    (id, party_id, round_no, state, snapshot_json, deadline_at, schema_version)
                VALUES (%s, %s, 1, 'ACTIVE', %s, DATE_ADD(NOW(), INTERVAL 90 SECOND), %s)
            """, (session_id, party_id, json.dumps(snapshot, ensure_ascii=False), SCHEMA_VERSION))
            for member in members:
                await cursor.execute(
                    "INSERT INTO party_battle_member (session_id, uid) VALUES (%s, %s)",
                    (session_id, member["uid"]),
                )
            await cursor.execute("UPDATE party SET state = 'BATTLE' WHERE id = %s AND state = 'LOBBY'", (party_id,))
            await conn.commit()
    return _render(session_id, 1, snapshot, set(), "队伍战斗已开启，等待全员行动。", uid)


@reg_xz_func
async def party_battle_status(uid, qz, group_openid):
    if not group_openid:
        return {"type": "markdown", "content": "队伍战斗仅可在所属群聊中查看与行动。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            session = await _load_session(uid, cursor, lock=True, group_openid=group_openid)
            if not session:
                return {"type": "markdown", "content": "当前没有进行中的队伍战斗。"}
            fields = _session_fields(session)
            actions = await _load_round_actions(cursor, fields["id"], fields["round_no"])
            result = await _resolve_round_if_ready(conn, cursor, session, actions)
            if result:
                await conn.commit()
                return result
            return _render(fields["id"], fields["round_no"], fields["snapshot_json"], set(actions), viewer_uid=uid)


@reg_xz_func
async def party_battle_action(uid, qz, group_openid, action_text, request_id=None):
    if not group_openid:
        return {"type": "markdown", "content": "队伍战斗仅可在所属群聊中查看与行动。"}
    parsed_action = parse_action(action_text)
    if not parsed_action:
        return {"type": "markdown", "content": "行动错误，请使用：队伍战斗行动 普攻/防御/调息/技能 1-3。"}
    request_key = normalize_request_id(request_id)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            session = await _load_session(uid, cursor, lock=True, group_openid=group_openid)
            if not session:
                if request_key:
                    replay = await _find_action_request(uid, group_openid, request_key, cursor)
                    if replay:
                        return await _replay_action_request(cursor, replay, uid)
                return {"type": "markdown", "content": "当前没有进行中的队伍战斗。"}
            fields = _session_fields(session)
            if request_key:
                replay = await _find_action_request(
                    uid,
                    group_openid,
                    request_key,
                    cursor,
                    session_id=fields["id"],
                    lock=True,
                )
                if replay:
                    return await _replay_action_request(cursor, replay, uid)
            snapshot = upgrade_snapshot(fields["snapshot_json"])
            member = next((item for item in snapshot["members"] if str(item["uid"]) == str(uid)), None)
            if not member:
                return {"type": "markdown", "content": "你不在本场战斗的参战快照中。"}
            error = validate_action_for_member(member, parsed_action)
            if error:
                return {"type": "markdown", "content": error + "\n\n<qqbot-cmd-input text='队伍战斗状态' show='返回战斗' />"}
            if request_key:
                await cursor.execute("""
                    INSERT INTO party_battle_action_request
                        (session_id, uid, request_id, round_no, action_type, action_payload)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    fields["id"], uid, request_key, fields["round_no"],
                    parsed_action["type"],
                    json.dumps(parsed_action["payload"], ensure_ascii=False),
                ))
            await cursor.execute("""
                INSERT INTO party_battle_action
                    (session_id, round_no, uid, action_type, action_payload, request_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    action_type = VALUES(action_type),
                    action_payload = VALUES(action_payload),
                    request_id = COALESCE(VALUES(request_id), request_id)
            """, (
                fields["id"], fields["round_no"], uid, parsed_action["type"],
                json.dumps(parsed_action["payload"], ensure_ascii=False),
                request_key,
            ))
            actions = await _load_round_actions(cursor, fields["id"], fields["round_no"])
            result = await _resolve_round_if_ready(conn, cursor, session, actions)
            if not result:
                await conn.commit()
                return _render(fields["id"], fields["round_no"], snapshot, set(actions), "已记录你的行动，等待其他道友。", uid)
            await conn.commit()
            return result
