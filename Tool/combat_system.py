# -*- coding: utf-8 -*-
"""
回合制PVE战斗系统（1v1版）
完全适配120个技能及其BUFF效果
"""

import random
import re
import copy
from enum import Enum
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


BUFF_TYPE_CN = {
    "attack_up": "攻击提升",
    "attack_down": "攻击削弱",
    "defense_up": "防御提升",
    "defense_down": "防御削弱",
    "speed_up": "速度提升",
    "speed_down": "速度降低",
    "slow": "减速",
    "crit_up": "暴击提升",
    "crit_dmg_up": "暴伤提升",
    "dodge_up": "闪避提升",
    "dodge_down": "闪避削弱",
    "hit_up": "命中提升",
    "hit_down": "命中削弱",
    "pierce_up": "破防提升",
    "pierce_down": "破防削弱",
    "all_stat_up": "全属性提升",
    "heal": "治疗",
    "heal_over_time": "持续回复",
    "healing_down": "治疗压制",
    "damage_over_time": "持续伤害",
    "lifesteal": "吸血",
    "stun": "眩晕",
    "silence": "沉默",
    "disarm": "缴械",
    "confusion": "混乱",
    "paralyze": "麻痹",
    "blind": "致盲",
    "shackle": "束缚",
    "invincible": "无敌",
    "untargetable": "隐身",
    "shield": "护盾",
    "reflect": "反伤",
    "defense_ignore": "无视防御",
    "see_through": "看破",
    "suppress": "镇压",
    "clone": "分身",
    "resurrect": "复苏",
    "immortal": "不死",
    "god_mode": "神模式",
    "death_sentence": "死亡宣告",
    "burning": "燃烧",
    "wet": "潮湿",
    "rooted": "缠绕",
    "poison": "中毒",
    "HP_down": "持续伤害",
    "HP_up": "持续回复",
    "gongji_up": "攻击提升",
    "gongji_down": "攻击削弱",
    "fangyu_up": "防御提升",
    "fangyu_down": "防御削弱",
    "sudu_up": "速度提升",
    "sudu_down": "速度降低",
    "baoji_up": "暴击提升",
    "shanbi_up": "闪避提升",
    "mingzhong_up": "命中提升",
    "pofang_up": "破防提升",
    "un_action": "眩晕",
    "unaction_fy_down": "眩晕破防",
}

WORLD_BUFF_PREFIX_RULES = [
    ("斗气", ("异火", "炎", "火莲", "焰", "雷动", "帝印", "黄泉", "龙鳞")),
    ("轮回", ("轮回", "因果", "古神", "封灭", "逆命", "戮默", "幽冥", "天命", "岁月")),
    ("灵界", ("掌天", "青元", "玄天", "辟邪", "噬金", "重元", "大衍", "傀儡", "惊蛰", "春黎", "梵圣")),
    ("荒域", ("至尊", "鲲鹏", "柳神", "仙王", "天荒", "重瞳", "草字", "荒天", "平乱", "他化")),
    ("帝路", ("圣体", "母气", "道经", "斗战", "皆字", "行字", "兵字", "前字", "六道", "天帝", "仙鼎", "虚空", "龙纹")),
    ("心海", ("沧元", "心刀", "八劫", "归墟", "时空", "金乌", "阴阳", "雷霆", "元神", "光阴", "刀域", "绝斩")),
]


DEFAULT_BOSS_MECHANICS = (
    {"stage": "first", "threshold": 0.75, "name": "天机·护体", "counter_element": "METAL", "counter_name": "金行", "effect": "defense_up", "value": 35, "duration": 2, "drop_weight": 15},
    {"stage": "second", "threshold": 0.40, "name": "天机·蓄力", "counter_element": "WATER", "counter_name": "水行", "effect": "attack_up", "value": 30, "duration": 2, "drop_weight": 20},
)

HARD_CONTROL_TYPES = frozenset(("stun", "paralyze", "shackle"))
BASIS_POINTS = 10000


def _is_code_like_name(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_]+", str(name or "")))


def _infer_world_prefix(skill_name: str) -> str:
    if not skill_name:
        return ""
    for prefix, keywords in WORLD_BUFF_PREFIX_RULES:
        for kw in keywords:
            if kw and kw in skill_name:
                return prefix
    return ""


def _format_lore_buff_name(buff_type: str, skill_name: str = "", custom_name: str = "") -> str:
    if custom_name and not _is_code_like_name(custom_name):
        return custom_name

    buff_cn = BUFF_TYPE_CN.get(buff_type, buff_type)
    world_prefix = _infer_world_prefix(skill_name)
    if world_prefix:
        return f"{world_prefix}·{buff_cn}"
    return buff_cn


SELF_BUFF_TYPES = frozenset({
    "attack_up", "gongji_up", "defense_up", "fangyu_up",
    "speed_up", "sudu_up", "crit_up", "baoji_up",
    "crit_dmg_up", "baoshang_up", "dodge_up", "shanbi_up",
    "hit_up", "mingzhong_up", "pierce_up", "pofang_up",
    "all_stat_up", "heal", "heal_over_time", "hp_up", "regeneration",
    "lifesteal", "invincible", "untargetable", "shield", "gedang",
    "reflect", "defense_ignore", "see_through", "clone", "resurrect",
    "immortal", "god_mode", "wudi", "immune", "transform",
})

ENEMY_BUFF_TYPES = frozenset({
    "attack_down", "gongji_down", "defense_down", "fangyu_down",
    "speed_down", "sudu_down", "slow", "slow_down",
    "crit_down", "baoji_down", "dodge_down", "shanbi_down",
    "hit_down", "mingzhong_down", "pierce_down", "pofang_down",
    "damage_over_time", "hp_down", "burning", "poison", "healing_down",
    "stun", "un_action", "unaction_fy_down", "stun_defense_down",
    "silence", "disarm", "confusion", "paralyze", "blind", "shackle",
    "rooted", "wet", "suppress", "death_sentence", "shock", "mana_burn",
})


def normalize_skill_buff_type(buff_type, skill_name: str = ""):
    """兼容迁移前已经写入战斗快照的错误技能配置。"""
    normalized_type = str(buff_type or "").strip().lower()
    if str(skill_name or "").strip() == "至尊骨" and normalized_type == "suppress":
        return "all_stat_up"
    return buff_type


def normalize_buff_target(value, default: int = 2, buff_type: str = None) -> int:
    """按 Buff 语义确定目标，并兼容历史数据中的 0/1 自身标记。"""
    normalized_type = str(buff_type or "").strip().lower()
    if normalized_type in SELF_BUFF_TYPES:
        return 1
    if normalized_type in ENEMY_BUFF_TYPES:
        return 2
    if value is None:
        return default
    try:
        return 2 if int(value) == 2 else 1
    except (TypeError, ValueError):
        return default


# ================================
# 枚举定义
# ================================

class SkillType(Enum):
    """技能类型"""
    ATTACK = 1              # 普通攻击型
    DEFENSE = 2             # 防御型
    HEAL = 3                # 治疗型
    ULTIMATE = 4            # 终极技能型（穿透攻击）


class TargetType(Enum):
    """目标选择类型（1v1）"""
    SELF = "self"           # 自身
    ENEMY = "enemy"         # 敌方


class BuffType(Enum):
    """BUFF效果类型"""
    # 属性增益/减益
    ATTACK_UP = "attack_up"
    ATTACK_DOWN = "attack_down"
    DEFENSE_UP = "defense_up"
    DEFENSE_DOWN = "defense_down"
    SPEED_UP = "speed_up"
    SPEED_DOWN = "speed_down"
    CRIT_UP = "crit_up"
    CRIT_DMG_UP = "crit_dmg_up"
    DODGE_UP = "dodge_up"
    DODGE_DOWN = "dodge_down"
    WET = "wet"
    ROOTED = "rooted"
    HIT_UP = "hit_up"
    HIT_DOWN = "hit_down"
    PIERCE_UP = "pierce_up"
    PIERCE_DOWN = "pierce_down"
    ALL_STAT_UP = "all_stat_up"

    # 生命效果
    HEAL = "heal"
    HEAL_OVER_TIME = "heal_over_time"
    DAMAGE_OVER_TIME = "damage_over_time"
    LIFESTEAL = "lifesteal"

    # 控制效果
    STUN = "stun"
    SILENCE = "silence"
    DISARM = "disarm"
    CONFUSION = "confusion"
    PARALYZE = "paralyze"
    BLIND = "blind"
    SLOW = "slow"
    SHACKLE = "shackle"

    # 特殊状态
    INVINCIBLE = "invincible"
    UNTARGETABLE = "untargetable"
    SHIELD = "shield"
    REFLECT = "reflect"
    DEFENSE_IGNORE = "defense_ignore"
    SEE_THROUGH = "see_through"
    SUPPRESS = "suppress"
    CLONE = "clone"
    RESURRECT = "resurrect"
    IMMORTAL = "immortal"
    GOD_MODE = "god_mode"
    DEATH_SENTENCE = "death_sentence"

    # 元素效果
    BURNING = "burning"
    POISON = "poison"


# ================================
# BUFF效果类
# ================================

@dataclass
class Buff:
    """BUFF效果"""
    buff_type: str
    value: float
    duration: int
    source_name: str = ""
    buff_name: str = ""  # BUFF显示名称（来自data_skill.buff_name）

    def __post_init__(self):
        """初始化后处理"""
        # 标准化BUFF类型
        buff_type_map = {
            'gongji_up': 'attack_up',
            'gongji_down': 'attack_down',
            'fangyu_up': 'defense_up',
            'fangyu_down': 'defense_down',
            'sudu_up': 'speed_up',
            'sudu_down': 'speed_down',
            'baoji_up': 'crit_up',
            'shanbi_up': 'dodge_up',
            'mingzhong_up': 'hit_up',
            'pofang_up': 'pierce_up',
            'HP_down': 'damage_over_time',
            'HP_up': 'heal_over_time',
            'un_action': 'stun',
            'unaction_fy_down': 'stun_defense_down',
        }
        if self.buff_type in buff_type_map:
            self.buff_type = buff_type_map[self.buff_type]

    def clone(self) -> 'Buff':
        """克隆BUFF"""
        return Buff(self.buff_type, self.value, self.duration, self.source_name, self.buff_name)

    def to_snapshot(self) -> Dict:
        """将BUFF转换为可持久化的基础类型。"""
        return {
            'buff_type': self.buff_type,
            'value': self.value,
            'duration': self.duration,
            'source_name': self.source_name,
            'buff_name': self.buff_name,
        }

    @classmethod
    def from_snapshot(cls, data: Dict) -> 'Buff':
        return cls(
            buff_type=data.get('buff_type', ''),
            value=data.get('value', 0),
            duration=data.get('duration', 0),
            source_name=data.get('source_name', ''),
            buff_name=data.get('buff_name', ''),
        )


# ================================
# 技能类
# ================================

@dataclass
class Skill:
    """技能"""
    id: int
    name: str
    skill_type: int
    target_type: str
    value: int
    is_percent: int
    item_id: Optional[int] = None
    cooldown: int = 0
    mana_cost: int = 0
    buff_type: Optional[str] = None
    buff_value: int = 0
    buff_duration: int = 0
    buff_target: int = 2  # 1:我方, 2:敌方
    buff_name: str = ""  # BUFF显示名称（从data_skill.buff_name获取）
    description: str = ""
    element: str = ""
    # 洞府藏经阁只强化技能的主伤害/治疗数值，不改动 Buff 与普攻。
    effect_bonus_bp: int = 0

    def __post_init__(self):
        # 旧 data_skill 曾以 0 表示“自身”。统一标准化，避免增益 Buff 落到敌方。
        self.buff_type = normalize_skill_buff_type(self.buff_type, self.name)
        self.buff_target = normalize_buff_target(self.buff_target, buff_type=self.buff_type)
        if self.buff_type:
            self.target_type = "enemy" if self.buff_target == 2 else "self"
        self.effect_bonus_bp = max(0, min(500, int(self.effect_bonus_bp or 0)))

    def effective_value(self) -> int:
        """返回写入快照后不再依赖洞府数据的技能主数值。"""
        return int(int(self.value) * (BASIS_POINTS + self.effect_bonus_bp) // BASIS_POINTS)

    def can_use(self, entity: 'CombatEntity') -> Tuple[bool, str]:
        """检查是否可以使用技能"""
        # 检查冷却
        if entity.cooldowns.get(self.id, 0) > 0:
            return False, f"技能冷却中（剩余{entity.cooldowns[self.id]}回合）"
        # 检查法力
        if entity.mana < self.mana_cost:
            return False, f"法力不足（需要{self.mana_cost}，当前{entity.mana}）"
        return True, ""

    def execute(self, attacker: 'CombatEntity', defender: 'CombatEntity') -> Dict:
        """执行技能"""
        # 扣除法力
        attacker.mana -= self.mana_cost
        # 设置冷却
        if self.cooldown > 0:
            attacker.cooldowns[self.id] = self.cooldown

        result = {
            'skill_name': self.name,
            'damage': 0,
            'heal': 0,
            'is_critical': False,
            'is_dodge': False,
            'buffs_applied': [],
            'reflect_damage': 0
        }

        # 根据技能类型执行不同效果
        if self.skill_type in [1, 4]:  # 攻击型技能
            result = self._execute_attack(attacker, defender)
        elif self.skill_type == 2:  # 防御型技能
            result = self._execute_defense(attacker)
        elif self.skill_type == 3:  # 回复型技能
            result = self._execute_heal(attacker)

        # 应用BUFF效果（只有技能命中时才应用，闪避不获得buff）
        if self.buff_type and not result.get('is_dodge', False):
            target = attacker if self.buff_target == 1 else defender
            buff = Buff(self.buff_type, self.buff_value, self.buff_duration, self.name, self.buff_name)
            if target.add_buff(buff) is not False:
                result['buffs_applied'].append({
                    'target': target.name,
                    'buff_type': self.buff_type,
                    'buff_name': self._get_buff_name(),
                    'duration': buff.duration
                })

        return result

    def _execute_attack(self, attacker: 'CombatEntity', defender: 'CombatEntity') -> Dict:
        """执行攻击技能"""
        result = {
            'skill_name': self.name,
            'damage': 0,
            'heal': 0,
            'is_critical': False,
            'is_dodge': False,
            'buffs_applied': [],
            'reflect_damage': 0
        }

        # 检查是否无法攻击
        if attacker.has_buff('disarm'):
            return result

        # 检查目标是否无法被选中
        if defender.has_buff('untargetable'):
            return result

        # 检查闪避
        hit_rate = self._calculate_hit_rate(attacker, defender)
        if random.random() > hit_rate:
            result['is_dodge'] = True
            # 闪避后仍然检查是否需要应用技能buff（如增伤、减防等效果）
            # 但不造成伤害
            return result

        # 检查无敌
        if defender.has_buff('invincible') or defender.has_buff('immortal'):
            return result

        # 计算伤害
        damage = self._calculate_damage(attacker, defender)

        # 检查暴击（暴击率已通过crit_mod计算，这里不再额外加成）
        crit_rate = attacker.get_effective_crit()
        if random.random() < crit_rate:
            crit_dmg = attacker.crit_dmg
            if attacker.has_buff('crit_dmg_up'):
                for buff in attacker.buffs:
                    if buff.buff_type == 'crit_dmg_up':
                        crit_dmg *= (1 + buff.value / 100)
            damage *= crit_dmg
            result['is_critical'] = True

        damage, shield_absorbed = defender.mitigate_with_shield(int(max(1, damage)))
        result['damage'] = damage
        result['shield_absorbed'] = shield_absorbed

        # 处理反射
        if defender.has_buff('reflect'):
            for buff in defender.buffs:
                if buff.buff_type == 'reflect':
                    result['reflect_damage'] = int(result['damage'] * buff.value / 100)
                    attacker.hp -= result['reflect_damage']

        defender.hp -= result['damage']

        # 吸血效果
        if self.buff_type == 'lifesteal':
            heal_amount = int(result['damage'] * self.buff_value / 100)
            actual_heal, healing_reduced = attacker.receive_heal(heal_amount)
            result['heal'] = actual_heal
            result['healing_reduced'] = healing_reduced

        return result

    def _calculate_hit_rate(self, attacker: 'CombatEntity', defender: 'CombatEntity') -> float:
        """计算命中率"""
        base_hit = 0.95
        effective_hit = attacker.get_effective_hit()
        effective_dodge = defender.get_effective_dodge()

        # 致盲减半命中率
        if attacker.has_buff('blind'):
            base_hit *= 0.5

        # 计算命中率
        hit_rate = base_hit * (effective_hit / (effective_hit + effective_dodge + 0.001))
        return max(0.1, min(0.95, hit_rate))

    def _calculate_damage(self, attacker: 'CombatEntity', defender: 'CombatEntity') -> float:
        atk = attacker.get_effective_attack()
        dfn = defender.get_effective_defense()
        pierce = attacker.pierce + attacker.pierce_mod

        if attacker.has_buff('defense_ignore'):
            base_damage = atk
        else:
            K = 800
            effective_defense = max(0, dfn * (1 - min(pierce, 0.9)))
            damage_reduction = effective_defense / (effective_defense + K)
            base_damage = atk * (1 - damage_reduction)

        base_damage = max(1, base_damage)

        effective_value = self.effective_value()
        if self.is_percent:
            skill_multiplier = effective_value / 100
        else:
            skill_multiplier = 1.0 + effective_value / max(1, atk)

        random_factor = random.uniform(0.92, 1.08)

        return base_damage * skill_multiplier * random_factor

    def _execute_defense(self, attacker: 'CombatEntity') -> Dict:
        """执行防御技能"""
        return {
            'skill_name': self.name,
            'damage': 0,
            'heal': 0,
            'is_critical': False,
            'is_dodge': False,
            'buffs_applied': [],
            'reflect_damage': 0
        }

    def _execute_heal(self, attacker: 'CombatEntity') -> Dict:
        """执行治疗技能"""
        effective_value = self.effective_value()
        if self.is_percent:
            heal_amount = int(attacker.max_hp * effective_value / 100)
        else:
            heal_amount = effective_value

        actual_heal, healing_reduced = attacker.receive_heal(heal_amount)

        return {
            'skill_name': self.name,
            'damage': 0,
            'heal': actual_heal,
            'healing_reduced': healing_reduced,
            'is_critical': False,
            'is_dodge': False,
            'buffs_applied': [],
            'reflect_damage': 0
        }

    def _get_buff_name(self) -> str:
        """获取BUFF显示名称"""
        return _format_lore_buff_name(self.buff_type, self.name, self.buff_name)

    def to_snapshot(self) -> Dict:
        """将技能定义转换为战斗快照，避免恢复时重新读取会变化的数据。"""
        return {
            'id': self.id,
            'name': self.name,
            'skill_type': self.skill_type,
            'target_type': self.target_type,
            'value': self.value,
            'is_percent': self.is_percent,
            'item_id': self.item_id,
            'cooldown': self.cooldown,
            'mana_cost': self.mana_cost,
            'buff_type': self.buff_type,
            'buff_value': self.buff_value,
            'buff_duration': self.buff_duration,
            'buff_target': self.buff_target,
            'buff_name': self.buff_name,
            'description': self.description,
            'element': self.element,
            'effect_bonus_bp': self.effect_bonus_bp,
        }

    @classmethod
    def from_snapshot(cls, data: Dict) -> 'Skill':
        return cls(
            id=data['id'],
            name=data['name'],
            skill_type=data['skill_type'],
            target_type=data.get('target_type', 'enemy'),
            value=data.get('value', 0),
            is_percent=data.get('is_percent', 0),
            item_id=data.get('item_id'),
            cooldown=data.get('cooldown', 0),
            mana_cost=data.get('mana_cost', 0),
            buff_type=data.get('buff_type'),
            buff_value=data.get('buff_value', 0),
            buff_duration=data.get('buff_duration', 0),
            buff_target=data.get('buff_target', 2),
            buff_name=data.get('buff_name', ''),
            description=data.get('description', ''),
            element=data.get('element', ''),
            effect_bonus_bp=data.get('effect_bonus_bp', 0),
        )


# ================================
# 战斗实体类
# ================================

class CombatEntity:
    """战斗实体（玩家/敌人）"""

    def __init__(self, name: str, role_data: Dict, skill_list: List[Skill] = None):
        # 基础属性
        self.name = name
        self.role_data = copy.deepcopy(role_data)
        self.max_hp = role_data.get('qixue')
        self.hp = self.max_hp
        self.attack = role_data.get('gongji')
        self.defense = role_data.get('fangyu')
        self.speed = role_data.get('sudu')
        self.crit = role_data.get('baoji') / 10000  # 转换为小数（默认500 = 5%暴击率）
        self.crit_dmg = 1.5 + role_data.get('baoshang') / 10000
        self.dodge = role_data.get('shanbi') / 10000
        self.hit = role_data.get('mingzhong') / 10000 # 默认命中率0.5
        self.pierce = role_data.get('pofang') / 10000
        self.max_mana = role_data.get('max_fali')
        self.mana = self.max_mana
        self.lifesteal = role_data.get('xixue') / 10000

        # 实体类型标记（用于AI策略区分）
        self.entity_type = role_data.get('entity_type', 'player')  # player / normal / boss

        # 战斗状态
        self.is_alive = True
        self.can_action = True
        self.buffs: List[Buff] = []
        self.cooldowns: Dict[int, int] = {}
        self.skills: List[Skill] = skill_list or []

        # 临时属性修正
        self.attack_mod = 1.0
        self.defense_mod = 1.0
        self.speed_mod = 1.0
        self.crit_mod = 1.0
        self.dodge_mod = 1.0
        self.hit_mod = 1.0
        self.pierce_mod = 0.0
        # 专属职业特性使用有限次数而非隐式随机，所有状态都会进入快照。
        self.control_resist_value = 0
        self.control_resist_rounds = 0
        self.control_resist_available = False
        self.control_resist_event = None
        self.sacred_body_control_guard = False
        self.next_damage_penalty = 0

    def get_effective_attack(self) -> int:
        """获取有效攻击力"""
        return int(self.attack * self.attack_mod)

    def get_effective_defense(self) -> int:
        """获取有效防御力"""
        return int(self.defense * self.defense_mod)

    def get_effective_speed(self) -> int:
        """获取有效速度"""
        return int(self.speed * self.speed_mod)

    def get_effective_crit(self) -> float:
        """获取有效暴击率"""
        return min(1.0, self.crit * self.crit_mod)

    def get_effective_dodge(self) -> float:
        """获取有效闪避率"""
        return min(1.0, self.dodge * self.dodge_mod)

    def get_effective_hit(self) -> float:
        """获取有效命中率"""
        return min(1.0, self.hit * self.hit_mod)

    def add_buff(self, buff: Buff):
        """添加BUFF"""
        if buff.buff_type in HARD_CONTROL_TYPES:
            original_duration = max(0, int(buff.duration))
            if self.sacred_body_control_guard:
                self.sacred_body_control_guard = False
                self.next_damage_penalty = max(self.next_damage_penalty, 20)
                self.control_resist_event = {
                    'mode': 'SACRED_BODY',
                    'buff_type': buff.buff_type,
                    'original_duration': original_duration,
                    'final_duration': 0,
                    'damage_penalty': 20,
                }
                return False
            if self.control_resist_available:
                reduction = min(original_duration, max(1, int(self.control_resist_rounds or 1)))
                buff.duration = original_duration - reduction
                self.control_resist_available = False
                self.control_resist_event = {
                    'mode': 'CONTROL_RESIST',
                    'buff_type': buff.buff_type,
                    'original_duration': original_duration,
                    'final_duration': int(buff.duration),
                    'resist_value': int(self.control_resist_value),
                    'reduced_rounds': reduction,
                }
                if buff.duration <= 0:
                    return False
        # 检查是否已有相同BUFF，有的话刷新持续时间
        for existing in self.buffs:
            if existing.buff_type == buff.buff_type:
                existing.duration = max(existing.duration, buff.duration)
                existing.value = max(existing.value, buff.value)
                return True
        self.buffs.append(buff)
        self._apply_buff_modifiers()
        return True

    def consume_control_resist_event(self):
        event = self.control_resist_event
        self.control_resist_event = None
        return event

    def receive_heal(self, amount: int, consume_healing_down: bool = True) -> Tuple[int, int]:
        """统一结算直接、持续与吸血回复，并消耗一次治疗压制。"""
        amount = max(0, int(amount or 0))
        reduction = 0
        healing_down = next((item for item in self.buffs if item.buff_type == 'healing_down'), None)
        if healing_down and amount:
            reduction = max(0, min(50, int(healing_down.value or 0)))
            amount = amount * (100 - reduction) // 100
            if consume_healing_down:
                self.remove_buff('healing_down')
        actual = max(0, min(amount, self.max_hp - self.hp))
        self.hp += actual
        return actual, reduction

    def mitigate_with_shield(self, damage: int) -> Tuple[int, int]:
        """护盾强度是确定性减伤百分比，取最强一层且上限 40%。"""
        damage = max(1, int(damage))
        shields = [item for item in self.buffs if item.buff_type == 'shield']
        if not shields:
            return damage, 0
        strength = max(0, min(40, int(max(item.value for item in shields))))
        final_damage = max(1, damage * (100 - strength) // 100)
        return final_damage, damage - final_damage

    def has_buff(self, buff_type: str) -> bool:
        """检查是否有指定BUFF"""
        return any(b.buff_type == buff_type for b in self.buffs)

    def remove_buff(self, buff_type: str):
        """移除指定BUFF"""
        self.buffs = [b for b in self.buffs if b.buff_type != buff_type]
        self._reset_modifiers()
        self._apply_buff_modifiers()

    def _apply_buff_modifiers(self):
        """应用BUFF属性修正"""
        self._reset_modifiers()

        for buff in self.buffs:
            if buff.buff_type == 'attack_up':
                self.attack_mod *= (1 + buff.value / 100)
            elif buff.buff_type == 'attack_down':
                self.attack_mod *= (1 - buff.value / 100)
            elif buff.buff_type == 'defense_up':
                self.defense_mod *= (1 + buff.value / 100)
            elif buff.buff_type == 'defense_down':
                self.defense_mod *= (1 - buff.value / 100)
            elif buff.buff_type == 'speed_up':
                self.speed_mod *= (1 + buff.value / 100)
            elif buff.buff_type == 'speed_down' or buff.buff_type == 'slow':
                self.speed_mod *= (1 - buff.value / 100)
            elif buff.buff_type == 'crit_up':
                self.crit_mod *= (1 + buff.value / 100)
            elif buff.buff_type == 'dodge_up':
                self.dodge_mod *= (1 + buff.value / 100)
            elif buff.buff_type == 'hit_up':
                self.hit_mod *= (1 + buff.value / 100)
            elif buff.buff_type == 'pierce_up':
                self.pierce_mod = min(1.0, self.pierce_mod + buff.value / 100)
            elif buff.buff_type == 'all_stat_up':
                self.attack_mod *= (1 + buff.value / 100)
                self.defense_mod *= (1 + buff.value / 100)
                self.speed_mod *= (1 + buff.value / 100)
                self.crit_mod *= (1 + buff.value / 100)
                self.dodge_mod *= (1 + buff.value / 100)

    def _reset_modifiers(self):
        """重置属性修正"""
        self.attack_mod = 1.0
        self.defense_mod = 1.0
        self.speed_mod = 1.0
        self.crit_mod = 1.0
        self.dodge_mod = 1.0
        self.hit_mod = 1.0
        self.pierce_mod = 0.0

    def update_buffs(self):
        """更新BUFF状态（回合结束时调用）"""
        expired_buffs = []
        for buff in self.buffs:
            buff.duration -= 1
            if buff.duration <= 0:
                expired_buffs.append(buff)

        for buff in expired_buffs:
            self.buffs.remove(buff)

        if expired_buffs:
            self._reset_modifiers()
            self._apply_buff_modifiers()

    def process_dot_hot(self) -> Tuple[int, int]:
        """处理持续效果（回合开始时调用）"""
        total_damage = 0
        total_heal = 0

        for buff in self.buffs[:]:
            if buff.buff_type in ['burning', 'poison', 'damage_over_time']:
                damage = int(self.max_hp * buff.value / 100)
                self.hp -= damage
                total_damage += damage
            elif buff.buff_type == 'heal_over_time':
                heal = int(self.max_hp * buff.value / 100)
                actual_heal, _ = self.receive_heal(heal)
                total_heal += actual_heal
            elif buff.buff_type == 'death_sentence':
                # 死亡宣告效果
                if buff.duration == 1:
                    self.hp = 0

        return total_damage, total_heal

    def update_cooldowns(self):
        """更新技能冷却"""
        for skill_id in list(self.cooldowns.keys()):
            self.cooldowns[skill_id] -= 1
            if self.cooldowns[skill_id] <= 0:
                del self.cooldowns[skill_id]

    def is_dead(self) -> bool:
        """检查是否死亡"""
        return self.hp <= 0

    def get_status_summary(self) -> str:
        """获取状态摘要"""
        status = []
        if self.has_buff('stun'):
            status.append('[眩晕]')
        if self.has_buff('silence'):
            status.append('[沉默]')
        if self.has_buff('burning'):
            status.append('[燃烧]')
        if self.has_buff('wet'):
            status.append('[潮湿]')
        if self.has_buff('rooted'):
            status.append('[缠绕]')
        if self.has_buff('poison'):
            status.append('[中毒]')
        if self.has_buff('invincible'):
            status.append('[无敌]')
        if self.has_buff('attack_up'):
            status.append('[攻击提升]')
        if self.has_buff('defense_up'):
            status.append('[防御提升]')
        if self.has_buff('shield'):
            status.append('[护盾]')
        if self.has_buff('healing_down'):
            status.append('[治疗压制]')
        return ''.join(status) if status else ''

    def to_snapshot(self) -> Dict:
        """导出实体的完整战斗状态。"""
        return {
            'name': self.name,
            'role_data': copy.deepcopy(self.role_data),
            'max_hp': self.max_hp,
            'hp': self.hp,
            'attack': self.attack,
            'defense': self.defense,
            'speed': self.speed,
            'crit': self.crit,
            'crit_dmg': self.crit_dmg,
            'dodge': self.dodge,
            'hit': self.hit,
            'pierce': self.pierce,
            'max_mana': self.max_mana,
            'mana': self.mana,
            'lifesteal': self.lifesteal,
            'entity_type': self.entity_type,
            'is_alive': self.is_alive,
            'can_action': self.can_action,
            'buffs': [buff.to_snapshot() for buff in self.buffs],
            'cooldowns': dict(self.cooldowns),
            'skills': [skill.to_snapshot() for skill in self.skills],
            'attack_mod': self.attack_mod,
            'defense_mod': self.defense_mod,
            'speed_mod': self.speed_mod,
            'crit_mod': self.crit_mod,
            'dodge_mod': self.dodge_mod,
            'hit_mod': self.hit_mod,
            'pierce_mod': self.pierce_mod,
            'control_resist_value': self.control_resist_value,
            'control_resist_rounds': self.control_resist_rounds,
            'control_resist_available': self.control_resist_available,
            'control_resist_event': copy.deepcopy(self.control_resist_event),
            'sacred_body_control_guard': self.sacred_body_control_guard,
            'next_damage_penalty': self.next_damage_penalty,
        }

    @classmethod
    def from_snapshot(cls, data: Dict) -> 'CombatEntity':
        entity = cls(
            name=data['name'],
            role_data=data.get('role_data', {}),
            skill_list=[Skill.from_snapshot(item) for item in data.get('skills', [])],
        )
        for attr in (
            'max_hp', 'hp', 'attack', 'defense', 'speed', 'crit', 'crit_dmg',
            'dodge', 'hit', 'pierce', 'max_mana', 'mana', 'lifesteal',
            'entity_type', 'is_alive', 'can_action', 'attack_mod', 'defense_mod',
            'speed_mod', 'crit_mod', 'dodge_mod', 'hit_mod', 'pierce_mod',
            'control_resist_value', 'control_resist_rounds', 'control_resist_available',
            'control_resist_event', 'sacred_body_control_guard', 'next_damage_penalty',
        ):
            if attr in data:
                setattr(entity, attr, data[attr])
        entity.cooldowns = {int(k): v for k, v in data.get('cooldowns', {}).items()}
        entity.buffs = [Buff.from_snapshot(item) for item in data.get('buffs', [])]
        entity._reset_modifiers()
        entity._apply_buff_modifiers()
        return entity


# ================================
# 战斗管理器
# ================================

class CombatManager:
    """战斗管理器"""

    def __init__(self, player: CombatEntity, enemy: CombatEntity, max_rounds: int = 50):
        self.player = player
        self.enemy = enemy
        self.round = 0
        self.combat_log: List[Dict] = []
        self.winner: Optional[CombatEntity] = None
        self.max_rounds = max_rounds
        self.skill_history: List[Dict] = []  # 技能使用历史
        self.first: Optional[CombatEntity] = None
        self.second: Optional[CombatEntity] = None
        self.initialized = False
        self.combat_ended = False
        # 天机为 Boss 的可读机制预告。每个阶段只触发一次，完整写入快照。
        self.boss_tianji = {
            "triggered": [], "intent": None, "broken_stages": [], "reward_weight_bonus": 0,
            "insight": None, "insight_source": "",
        }
        self.reaction_targets_this_round = set()
        # 道心由玩家连续施展同系技能积累，作为手动战斗的短回合资源。
        self.dao_heart = {"value": 0, "cap": 5, "last_element": "", "stored": False}
        # 专属能力来自创建战斗时的数据库快照，整场最多使用一次且仅用于 PVE。
        self.role_special = copy.deepcopy(player.role_data.get("role_special") or {})
        self.role_special.setdefault("used", False)
        self.role_special.setdefault("passive_triggered", False)
        self.role_special.setdefault("events", [])
        self.role_special.setdefault("pending_copy", None)
        self.role_special.setdefault("sword_intent", 0)
        self.role_special.setdefault("battle_intent", 0)
        self.role_special.setdefault("sacred_body_guard_used", False)
        # 灵兽与本源协同已在开战前冻结到 role_data，恢复时不再查库。
        self.spirit_beast = copy.deepcopy(player.role_data.get("spirit_beast") or {})
        self.spirit_beast.setdefault("triggered", 0)
        self.spirit_beast.setdefault("events", [])

    def initialize(self) -> None:
        """初始化战斗顺序；可单独调用以创建可持久化的待行动战斗。"""
        if self.initialized:
            return
        self._log("combat_start", f"⚔️ 战斗开始！{self.player.name} VS {self.enemy.name}")
        self._log(
            "status",
            f"{self.player.name}: HP={self.player.hp}/{self.player.max_hp} | "
            f"MP={self.player.mana}/{self.player.max_mana}"
        )
        self._log("status", f"{self.enemy.name}: HP={self.enemy.hp}/{self.enemy.max_hp}")
        self._apply_role_identity_traits()
        self._apply_role_special_passive()
        self._apply_role_feature()
        # 速度被动必须先于先手判定生效。
        self.first, self.second = self._determine_order()
        self._log("order", f"速度判定：{self.first.name} 先手！")
        self.initialized = True

    def _role_name(self) -> str:
        return str(self.role_special.get('role_name') or self.player.name or '')

    def _apply_role_identity_traits(self) -> None:
        """接入不占主动/被动槽的职业核心特性。"""
        role_name = self._role_name()
        if role_name == '叶凡' and not self.role_special.get('sacred_body_guard_used'):
            self.player.sacred_body_control_guard = True
            self._log('role_identity', '🛡️ 圣体破禁：本场首次硬控将被化解，下一次伤害降低20%。')
        if role_name == '孟川':
            self._set_threat_insight('元神观敌')

    def _set_threat_insight(self, source_name: str, force: bool = False) -> None:
        if self.boss_tianji.get('insight') and not force:
            return
        if self.enemy.entity_type == 'boss':
            triggered = set(self.boss_tianji.get('triggered', []))
            available = [item for item in self._boss_mechanics() if item.get('stage') not in triggered]
            if available:
                next_mechanic = max(available, key=lambda item: float(item.get('threshold', 0)))
                threshold = int(float(next_mechanic.get('threshold', 0)) * 100)
                summary = (
                    f"下一高威胁为「{next_mechanic['name']}」（气血≤{threshold}%），"
                    f"以{next_mechanic['counter_name']}技能可破局"
                )
            else:
                summary = '已无未触发的 Boss 机制'
        else:
            attack_pressure = self.enemy.get_effective_attack() / max(1, self.player.get_effective_defense())
            if self.enemy.get_effective_speed() > self.player.get_effective_speed():
                summary = f"最高威胁为先手压力：{self.enemy.name}速度高于我方"
            else:
                summary = f"最高威胁为正面攻势：攻防压力比{attack_pressure:.2f}"
        self.boss_tianji['insight'] = {'source': source_name, 'summary': summary, 'round': self.round}
        self.boss_tianji['insight_source'] = source_name
        self._log('threat_insight', f"🔮 {source_name}：{summary}。")

    def _log_control_resist_event(self, target: CombatEntity) -> None:
        event = target.consume_control_resist_event()
        if not event:
            return
        if event.get('mode') == 'SACRED_BODY':
            self.role_special['sacred_body_guard_used'] = True
            message = '🛡️ 圣体破禁化解了本场首次硬控；下一次造成的伤害降低20%。'
        else:
            message = (
                f"🧠 控制抗性{event.get('resist_value', 0)}点生效，"
                f"本场首次硬控缩短{event.get('reduced_rounds', 0)}回合。"
            )
        self.role_special['events'].append({'round': self.round, 'type': 'CONTROL_RESIST', **event})
        self._log('control_resist', message)

    def _apply_spirit_beast_conditional(self) -> None:
        synergy = self.spirit_beast.get('synergy') or {}
        if synergy.get('code') != 'REINCARNATION_HEALER' or self.spirit_beast.get('triggered', 0):
            return
        threshold = max(1, min(50, int(synergy.get('threshold', 30))))
        if self.player.hp > self.player.max_hp * threshold / 100:
            return
        percent = max(1, min(5, int(synergy.get('heal_percent', 5))))
        heal, healing_reduced = self.player.receive_heal(int(self.player.max_hp * percent / 100))
        self.spirit_beast['triggered'] = 1
        event = {'round': self.round, 'type': 'LOW_HP_HEAL', 'value': heal, 'healing_reduced': healing_reduced}
        self.spirit_beast['events'].append(event)
        self._log('spirit_beast_synergy', f"💚 轮回灵契激发，为{self.player.name}回复{heal}点气血。")

    def _boost_first_player_shield(self) -> None:
        synergy = self.spirit_beast.get('synergy') or {}
        if synergy.get('code') != 'TREASURE_GUARDIAN' or self.spirit_beast.get('triggered', 0):
            return
        shields = [item for item in self.player.buffs if item.buff_type == 'shield']
        if not shields:
            return
        bonus = max(1, min(5, int(synergy.get('shield_bonus', 5))))
        shield = max(shields, key=lambda item: item.value)
        before = int(shield.value)
        shield.value = min(40, before + bonus)
        self.spirit_beast['triggered'] = 1
        self.spirit_beast['events'].append({
            'round': self.round, 'type': 'SHIELD_BONUS', 'before': before, 'after': int(shield.value),
        })
        self._log('spirit_beast_synergy', f"🛡️ 掌天灵契加持首层护盾，减伤强度提升至{int(shield.value)}%。")

    def _trigger_pending_copy(self) -> None:
        pending = self.role_special.get('pending_copy')
        if not pending or self.round < int(pending.get('trigger_round', self.round)):
            return
        damage = max(1, int(pending.get('damage', 1)))
        if self.enemy.entity_type == 'boss':
            damage = min(damage, max(1, int(self.enemy.max_hp * .01)))
        damage, absorbed = self.enemy.mitigate_with_shield(damage)
        self.enemy.hp -= damage
        self.role_special['pending_copy'] = None
        event = {
            'round': self.round, 'type': 'COPY_ECHO', 'name': pending.get('name'),
            'final_value': damage, 'shield_absorbed': absorbed,
        }
        self.role_special['events'].append(event)
        self._log('role_special_effect', f"🌌 「{pending.get('name', '弱化投影')}」延迟复制，造成{damage}点伤害。")

    def _gain_battle_intent(self) -> None:
        active_effect = ((self.role_special.get('active') or {}).get('effect') or {})
        if self._role_name() != '叶凡' and not active_effect.get('battle_intent'):
            return
        cap = max(1, min(5, int(active_effect.get('battle_intent', 3))))
        before = int(self.role_special.get('battle_intent', 0))
        after = min(cap, before + 1)
        self.role_special['battle_intent'] = after
        if after != before:
            self._log('battle_intent', f"🔥 圣体战意积累至{after}/{cap}层。")

    def _apply_player_damage_traits(
        self,
        actor: CombatEntity,
        target: CombatEntity,
        result: Dict,
        *,
        gain_intent: bool = True,
    ) -> None:
        """在基础伤害已扣除后统一应用有上限的职业增减伤。"""
        if actor is not self.player or int(result.get('damage', 0)) <= 0:
            return
        original = int(result['damage'])
        bonus_bp = 0
        feature_effect = ((self.role_special.get('feature') or {}).get('effect') or {})
        if feature_effect.get('type') == 'BOSS_DAMAGE' and target.entity_type == 'boss':
            bonus_bp += min(1000, max(0, int(feature_effect.get('value', 0))) * 100)

        sword_intent = max(0, int(self.role_special.get('sword_intent', 0)))
        if sword_intent:
            bonus_bp += 800
            self.role_special['sword_intent'] = sword_intent - 1
            self._log('sword_intent', '⚔️ 青元剑意融入本次攻击，伤害提升8%。')

        penalty_bp = min(5000, max(0, int(self.player.next_damage_penalty)) * 100)
        if penalty_bp:
            self.player.next_damage_penalty = 0
            self._log('role_identity', '⚠️ 圣体破禁的余震使本次伤害降低20%。')

        bonus_bp = min(2500, bonus_bp)
        final_damage = max(1, original * max(1000, BASIS_POINTS + bonus_bp - penalty_bp) // BASIS_POINTS)
        target.hp -= final_damage - original
        result['damage'] = final_damage
        result['trait_bonus_bp'] = bonus_bp
        result['trait_penalty_bp'] = penalty_bp
        if gain_intent:
            self._gain_battle_intent()

    def validate_player_action(self, action: Dict) -> Tuple[bool, str]:
        """验证手动行动，不改变战斗状态。"""
        action_type = str(action.get('action_type', '')).upper()
        if action_type == 'ARTIFACT':
            cost = max(1, int(self.player.max_mana * 0.2))
            if self.player.mana < cost:
                return False, f'法力不足，御器至少需要{cost}点法力'
            return True, ''
        if action_type in ('DAO_HEART_BURST', 'DAO_HEART_EXTEND'):
            if self.dao_heart['value'] < 3:
                return False, '道心不足，需要连续同系技能积累至3层'
            return True, ''
        if action_type == 'DAO_HEART_STORE':
            if self.dao_heart['value'] < self.dao_heart['cap']:
                return False, '道心不足，需要积累至5层才能留存'
            return True, ''
        if action_type in ('NORMAL_ATTACK', 'DEFEND', 'MEDITATE', 'AUTO'):
            return True, ''
        if action_type == 'SPECIAL':
            active = self.role_special.get('active')
            if not active:
                return False, '当前角色尚未装备专属主动能力'
            if self.role_special.get('used'):
                return False, '本场战斗已经施放过专属主动能力'
            required_intent = max(0, min(5, int((active.get('effect') or {}).get('battle_intent', 0))))
            if required_intent and int(self.role_special.get('battle_intent', 0)) < required_intent:
                return False, f'战意不足，需要积累至{required_intent}层才能施放'
            return True, ''
        if action_type != 'SKILL':
            return False, '不支持的行动类型'

        skill_id = action.get('skill_id')
        try:
            skill_id = int(skill_id)
        except (TypeError, ValueError):
            return False, '技能编号格式错误'

        skill = next((item for item in self.player.skills if item.id == skill_id), None)
        if skill is None:
            return False, '技能不存在或未装备'
        can_use, reason = skill.can_use(self.player)
        if not can_use:
            return False, reason
        if self.player.has_buff('silence') and skill.skill_type != 1:
            return False, '沉默状态只能使用普通攻击型技能'
        if self.player.has_buff('disarm') and skill.skill_type in [1, 4]:
            return False, '缴械状态不能使用攻击技能'
        return True, ''

    def resolve_round(self, player_action: Optional[Dict] = None) -> Tuple[Optional[CombatEntity], List[Dict]]:
        """执行一回合；player_action 为空时沿用旧的玩家自动战斗AI。"""
        self.initialize()
        if self._check_combat_end():
            return self.winner, []

        before = len(self.combat_log)
        self.round += 1
        self.reaction_targets_this_round = set()
        self._log("round", f"═══ 第 {self.round} 回合 ═══")
        self._prepare_boss_tianji()

        if self.first == self.player:
            self._execute_player_action(player_action)
            if not self._check_combat_end():
                self._execute_turn(self.enemy, self.player)
        else:
            self._execute_turn(self.enemy, self.player)
            if not self._check_combat_end():
                self._execute_player_action(player_action)

        self._end_of_round()
        self._resolve_boss_tianji()
        self._check_combat_end()
        if not self.winner and self.round >= self.max_rounds:
            self._log('draw', '⚖️ 达到最大回合数，战斗平局！')

        if self.winner or self.round >= self.max_rounds:
            self._end_combat()
        return self.winner, self.combat_log[before:]

    def _execute_player_action(self, action: Optional[Dict]) -> None:
        self._apply_role_special_conditional_passive()
        self._apply_spirit_beast_conditional()
        self._trigger_pending_copy()
        if self.enemy.is_dead():
            return
        if action is None or str(action.get('action_type', '')).upper() == 'AUTO':
            self._execute_turn(self.player, self.enemy)
            return

        if any(self.player.has_buff(control) for control in HARD_CONTROL_TYPES):
            self._log('stun', f"❌ {self.player.name} 被眩晕，无法行动！")
            return

        action_type = str(action.get('action_type', '')).upper()
        if action_type == 'DEFEND':
            self.player.add_buff(Buff('defense_up', 45, 2, '防御', '防御姿态'))
            self._log('action', f"🛡️ {self.player.name} 采取防御姿态，防御提升45%！")
            return
        if action_type == 'MEDITATE':
            recover = max(1, int(self.player.max_mana * 0.3))
            before_mana = self.player.mana
            self.player.mana = min(self.player.max_mana, self.player.mana + recover)
            self._log('action', f"🧘 {self.player.name} 调息回灵，法力 {before_mana} → {self.player.mana}！")
            return
        if action_type == 'ARTIFACT':
            cost = max(1, int(self.player.max_mana * 0.2))
            if self.player.mana < cost:
                self._log('action', f"❌ {self.player.name} 法力不足，无法御器护体！")
                return
            self.player.mana -= cost
            self.player.add_buff(Buff('defense_up', 30, 2, '御器', '御器护体'))
            self._log('action', f"✨ {self.player.name} 御器护体，消耗{cost}法力并提升30%防御！")
            return
        if action_type == 'DAO_HEART_BURST':
            damage = max(1, int(self.enemy.max_hp * 0.08))
            self.enemy.hp -= damage
            self.dao_heart['value'] -= 3
            self.dao_heart['last_element'] = ''
            self._log('dao_heart', f"💥 {self.player.name} 引爆3层道心，对{self.enemy.name}造成{damage}点道心伤害！")
            return
        if action_type == 'DAO_HEART_EXTEND':
            for buff in self.player.buffs:
                buff.duration += 1
            self.dao_heart['value'] -= 3
            self.dao_heart['last_element'] = ''
            self._log('dao_heart', f"🌀 {self.player.name} 以3层道心延势，身上增益延长1回合！")
            return
        if action_type == 'DAO_HEART_STORE':
            self.dao_heart['stored'] = True
            self._log('dao_heart', f"🔮 {self.player.name} 留存5层道心，下一次五行技能将获得额外威能！")
            return
        if action_type == 'NORMAL_ATTACK':
            self._execute_normal_attack(self.player, self.enemy)
            return
        if action_type == 'SPECIAL':
            self._execute_role_special()
            return

        skill_id = int(action.get('skill_id'))
        skill = next(item for item in self.player.skills if item.id == skill_id)
        self._log('action', f"🎯 {self.player.name} 使用技能：{skill.name}")
        result = skill.execute(self.player, self.enemy)
        self._log_control_resist_event(self.enemy)
        self._apply_player_damage_traits(self.player, self.enemy, result)
        self._boost_first_player_shield()
        self._log_skill_result(self.player, self.enemy, skill, result)
        self._apply_elemental_effect(self.player, self.enemy, skill, result)
        self._gain_dao_heart(skill, result)
        self.skill_history.append({
            'round': self.round,
            'actor': self.player.name,
            'skill': skill.name,
            'result': result,
        })

    def start_combat(self) -> Tuple[Optional[CombatEntity], List[Dict]]:
        """开始战斗"""
        self.initialize()

        # 战斗循环
        while self.round < self.max_rounds and not self._check_combat_end():
            self.resolve_round()

        # 战斗结束结算
        self._end_combat()

        return self.winner, self.combat_log

    def _determine_order(self) -> Tuple[CombatEntity, CombatEntity]:
        """决定行动顺序"""
        player_speed = self.player.get_effective_speed()
        enemy_speed = self.enemy.get_effective_speed()

        # 随机因素（10%波动）
        player_speed *= random.uniform(0.95, 1.05)
        enemy_speed *= random.uniform(0.95, 1.05)

        if player_speed >= enemy_speed:
            return self.player, self.enemy
        return self.enemy, self.player

    def _execute_turn(self, actor: CombatEntity, target: CombatEntity):
        """执行一个单位的行动回合"""
        # 检查是否被眩晕
        if any(actor.has_buff(control) for control in HARD_CONTROL_TYPES):
            self._log("stun", f"❌ {actor.name} 被眩晕，无法行动！")
            return

        # 检查是否被混乱
        if actor.has_buff('confusion'):
            if random.random() < 0.5:
                self._log("confusion", f"🌀 {actor.name} 陷入混乱，攻击了自己！")
                target = actor
            else:
                self._log("confusion", f"🌀 {actor.name} 陷入混乱！")

        # 检查是否被沉默（只能普攻）
        can_use_skill = not actor.has_buff('silence')

        # 选择技能
        skill = self._select_skill(actor, target, can_use_skill)

        if skill is None:
            # 普通攻击
            self._execute_normal_attack(actor, target)
        else:
            # 释放技能
            self._log("action", f"🎯 {actor.name} 使用技能：{skill.name}")
            result = skill.execute(actor, target)
            self._log_control_resist_event(target)
            self._apply_player_damage_traits(actor, target, result)
            if actor is self.player:
                self._boost_first_player_shield()
            self._log_skill_result(actor, target, skill, result)
            self._apply_elemental_effect(actor, target, skill, result)

            # 记录技能使用历史
            self.skill_history.append({
                'round': self.round,
                'actor': actor.name,
                'skill': skill.name,
                'result': result
            })

    def _get_available_skills(self, entity: CombatEntity, can_use_skill: bool = True) -> List[Skill]:
        """获取当前可用的技能列表"""
        if not entity.skills:
            return []

        available = []
        for skill in entity.skills:
            # 沉默状态只能用普通攻击类型技能
            if not can_use_skill and skill.skill_type != 1:
                continue
            # 缴械状态不能用攻击技能
            if entity.has_buff('disarm') and skill.skill_type in [1, 4]:
                continue
            can_use, _ = skill.can_use(entity)
            if can_use:
                available.append(skill)

        return available

    def _select_skill(self, entity: CombatEntity, target: CombatEntity, can_use_skill: bool = True) -> Optional[Skill]:
        """技能选择路由（根据实体类型分发到不同AI策略）"""
        available = self._get_available_skills(entity, can_use_skill)
        if not available:
            return None

        entity_type = getattr(entity, 'entity_type', 'player')

        if entity_type == 'boss':
            return self._ai_boss(entity, target, available)
        elif entity_type == 'normal':
            return self._ai_normal(entity, target, available)
        else:
            return self._ai_player(entity, target, available)

    def _ai_player(self, entity: CombatEntity, target: CombatEntity, available: List[Skill]) -> Optional[Skill]:
        """
        玩家自动战斗AI
        优先级：濒死治疗 → 收割 → 上增益 → 上减益 → 最强攻击
        """
        # 分类技能
        heals = [s for s in available if s.skill_type == 3]
        attacks = [s for s in available if s.skill_type in [1, 4]]
        buffs_self = [s for s in available
                      if s.buff_type and s.buff_target == 1
                      and s.buff_type in ('attack_up', 'all_stat_up', 'crit_up',
                                          'defense_up', 'speed_up', 'pierce_up')]
        debuffs_enemy = [s for s in available
                         if s.buff_type and s.buff_target == 2
                         and s.buff_type in ('defense_down', 'attack_down',
                                             'stun', 'silence')]
        dot_skills = [s for s in available
                      if s.buff_type and s.buff_target == 2
                      and s.buff_type in ('damage_over_time', 'burning', 'poison')]

        # ---- 优先级1：濒死治疗（血量<25%）----
        if entity.hp < entity.max_hp * 0.25 and heals:
            return max(heals, key=lambda s: s.value)

        # ---- 优先级2：收割（敌方血量<15%，用最强攻击）----
        if target.hp < target.max_hp * 0.15 and attacks:
            return max(attacks, key=lambda s: s.value)

        # ---- 优先级3：第1回合优先上增益BUFF ----
        if self.round <= 1 and buffs_self:
            # 优先全属性提升，其次攻击提升
            for preferred in ('all_stat_up', 'attack_up', 'pierce_up'):
                for s in buffs_self:
                    if s.buff_type == preferred and not entity.has_buff(s.buff_type):
                        return s

        # ---- 优先级4：没有增益时上增益（每5回合检查一次）----
        if self.round % 5 == 1:
            for s in buffs_self:
                if not entity.has_buff(s.buff_type):
                    return s

        # ---- 优先级5：敌方没有控制/减益时，上减益 ----
        if debuffs_enemy and random.random() < 0.35:
            for s in debuffs_enemy:
                if not target.has_buff(s.buff_type):
                    return s

        # ---- 优先级6：敌方没有DOT时，上持续伤害 ----
        if dot_skills and random.random() < 0.3:
            has_dot = (target.has_buff('burning') or target.has_buff('poison')
                       or target.has_buff('damage_over_time'))
            if not has_dot:
                return max(dot_skills, key=lambda s: s.buff_value * s.buff_duration)

        # ---- 优先级7：血量<50%且有治疗，30%概率治疗 ----
        if entity.hp < entity.max_hp * 0.5 and heals and random.random() < 0.3:
            return max(heals, key=lambda s: s.value)

        # ---- 默认：使用最强攻击技能 ----
        if attacks:
            # 80%概率用最强技能，20%概率随机（增加战斗变化）
            if random.random() < 0.8:
                return max(attacks, key=lambda s: s.value)
            else:
                return random.choice(attacks)

        # 没有攻击技能，随机选一个
        return random.choice(available) if available else None

    def _ai_boss(self, entity: CombatEntity, target: CombatEntity, available: List[Skill]) -> Optional[Skill]:
        """
        Boss AI — 三阶段策略
        阶段1（HP>60%）：优先上BUFF/减益，建立优势
        阶段2（30%<HP≤60%）：全力输出，优先高伤害技能
        阶段3（HP≤30%）：狂暴模式，使用终极技能，不再治疗
        """
        hp_ratio = entity.hp / entity.max_hp

        # 分类技能
        heals = [s for s in available if s.skill_type == 3]
        attacks = [s for s in available if s.skill_type in [1, 4]]
        ultimates = [s for s in available if s.skill_type == 4]
        buffs_self = [s for s in available if s.buff_type and s.buff_target == 1]
        debuffs_enemy = [s for s in available
                         if s.buff_type and s.buff_target == 2
                         and s.buff_type in ('defense_down', 'attack_down',
                                             'stun', 'silence',
                                             'damage_over_time', 'burning', 'poison')]

        # ======== 阶段1：HP > 60% — 建立优势 ========
        if hp_ratio > 0.6:
            # 第1回合必定上BUFF（如果有的话）
            if self.round <= 1 and buffs_self:
                return max(buffs_self, key=lambda s: s.buff_value)

            # 40%概率使用减益/控制技能
            if debuffs_enemy and random.random() < 0.4:
                for s in debuffs_enemy:
                    if not target.has_buff(s.buff_type):
                        return s

            # 30%概率上自身BUFF
            if buffs_self and random.random() < 0.3:
                for s in buffs_self:
                    if not entity.has_buff(s.buff_type):
                        return s

            # 其余情况正常攻击
            if attacks:
                return max(attacks, key=lambda s: s.value)

        # ======== 阶段2：30% < HP ≤ 60% — 全力输出 ========
        elif hp_ratio > 0.3:
            # 优先使用终极技能
            if ultimates:
                best_ult = max(ultimates, key=lambda s: s.value)
                can_use, _ = best_ult.can_use(entity)
                if can_use:
                    return best_ult

            # 20%概率治疗（如果有）
            if heals and random.random() < 0.2:
                return max(heals, key=lambda s: s.value)

            # 使用最强攻击
            if attacks:
                return max(attacks, key=lambda s: s.value)

        # ======== 阶段3：HP ≤ 30% — 狂暴模式 ========
        else:
            # 狂暴模式：不治疗，全力输出
            # 优先终极技能
            if ultimates:
                best_ult = max(ultimates, key=lambda s: s.value)
                can_use, _ = best_ult.can_use(entity)
                if can_use:
                    return best_ult

            # 尝试上攻击增益（孤注一掷）
            if buffs_self and random.random() < 0.25:
                atk_buffs = [s for s in buffs_self
                             if s.buff_type in ('attack_up', 'all_stat_up', 'crit_up')]
                if atk_buffs and not entity.has_buff(atk_buffs[0].buff_type):
                    return atk_buffs[0]

            # 使用最强攻击
            if attacks:
                return max(attacks, key=lambda s: s.value)

        # 兜底
        return random.choice(available) if available else None

    def _ai_normal(self, entity: CombatEntity, target: CombatEntity, available: List[Skill]) -> Optional[Skill]:
        """
        小怪AI — 简单直接
        血少治疗，否则随机攻击（带一点变化）
        """
        heals = [s for s in available if s.skill_type == 3]
        attacks = [s for s in available if s.skill_type in [1, 4]]

        # 血量<20%时治疗
        if entity.hp < entity.max_hp * 0.2 and heals:
            return random.choice(heals)

        # 70%概率用最强攻击，30%概率随机
        if attacks:
            if random.random() < 0.7:
                return max(attacks, key=lambda s: s.value)
            else:
                return random.choice(attacks)

        return random.choice(available) if available else None

    @staticmethod
    def _infer_element(skill: Skill) -> str:
        """由既有技能名推断五行，首发不要求一次性迁移全部技能数据。"""
        if skill.element:
            return str(skill.element).upper()
        text = f"{skill.name}{skill.buff_type or ''}"
        if any(word in text for word in ('冰', '水', '雨', '寒', '玄冰')):
            return 'WATER'
        if any(word in text for word in ('火', '炎', '焰', '燃烧')):
            return 'FIRE'
        if any(word in text for word in ('木', '草', '藤', '青莲', '缠绕')):
            return 'WOOD'
        if any(word in text for word in ('金', '剑', '雷', '庚')):
            return 'METAL'
        if any(word in text for word in ('土', '石', '山', '地脉')):
            return 'EARTH'
        return ''

    def _apply_elemental_effect(self, actor: CombatEntity, target: CombatEntity, skill: Skill, result: Dict) -> None:
        """处理首发五行状态。每次技能最多触发一种反应，闪避不附加状态。"""
        if result.get('is_dodge') or skill.buff_target == 1 or target is actor:
            return
        element = self._infer_element(skill)
        if not element:
            return

        if actor is self.player and self.dao_heart.get('stored'):
            bonus = max(1, int(target.max_hp * 0.05))
            target.hp -= bonus
            self.dao_heart = {"value": 0, "cap": 5, "last_element": "", "stored": False}
            self._log('dao_heart', f"✨ 留存道心共鸣{element}行，{target.name}额外受到{bonus}点伤害！")

        intent = self.boss_tianji.get('intent')
        if target is self.enemy and intent and not intent.get('broken') and element == intent['counter_element']:
            intent['broken'] = True
            self._log('boss_break', f"⚡ {actor.name} 以{intent['counter_name']}之法看破天机「{intent['name']}」！")

        if element == 'WATER':
            target.add_buff(Buff('wet', 0, 2, skill.name, '潮湿'))
            self._log('element', f"💧 {target.name} 被水行之力浸染，陷入潮湿！")
        elif element == 'WOOD':
            target.add_buff(Buff('rooted', 0, 2, skill.name, '缠绕'))
            target.add_buff(Buff('slow', 15, 2, skill.name, '缠绕减速'))
            self._log('element', f"🌿 {target.name} 被木行缠绕，速度降低！")
        elif element == 'FIRE':
            target_key = target.name
            can_react = target_key not in self.reaction_targets_this_round
            if target.has_buff('wet') and can_react:
                target.remove_buff('wet')
                bonus = max(1, int(target.max_hp * 0.04))
                target.hp -= bonus
                self.reaction_targets_this_round.add(target_key)
                self._log('reaction', f"♨️ 水火相激触发「蒸腾」！{target.name} 额外受到{bonus}点伤害。")
            elif target.has_buff('rooted') and can_react:
                target.remove_buff('rooted')
                target.add_buff(Buff('burning', 3, 2, skill.name, '焚林'))
                self.reaction_targets_this_round.add(target_key)
                self._log('reaction', f"🔥 木火相燃触发「焚林」！{target.name} 获得强化燃烧。")
            else:
                target.add_buff(Buff('burning', 2, 2, skill.name, '燃烧'))
                if target.has_buff('wet') or target.has_buff('rooted'):
                    self._log('reaction_guard', f"🛡️ {target.name} 本回合已触发过元素反应，本次仅施加燃烧。")
                self._log('element', f"🔥 {target.name} 被火行点燃！")
            synergy = self.spirit_beast.get('synergy') or {}
            if (
                actor is self.player
                and synergy.get('code') == 'FIRE_STRIKER'
                and not self.spirit_beast.get('triggered', 0)
            ):
                burning = next((item for item in target.buffs if item.buff_type == 'burning'), None)
                if burning:
                    bonus = max(1, min(1, int(synergy.get('burn_duration_bonus', 1))))
                    before = int(burning.duration)
                    burning.duration = min(10, before + bonus)
                    self.spirit_beast['triggered'] = 1
                    self.spirit_beast['events'].append({
                        'round': self.round,
                        'type': 'BURN_DURATION',
                        'before': before,
                        'after': int(burning.duration),
                    })
                    self._log(
                        'spirit_beast_synergy',
                        f"🔥 异火灵契延续首个燃烧，持续时间增至{int(burning.duration)}回合。",
                    )
        elif element == 'METAL':
            target.add_buff(Buff('defense_down', 15, 2, skill.name, '破甲'))
            self._log('element', f"⚔️ 金行破甲！{target.name} 防御降低15%。")
        elif element == 'EARTH':
            actor.add_buff(Buff('defense_up', 12, 2, skill.name, '地脉护体'))
            self._log('element', f"⛰️ 土行护体！{actor.name} 防御提升12%。")

    def _gain_dao_heart(self, skill: Skill, result: Dict) -> None:
        """玩家连续使用同系且命中的技能，才会积累道心。"""
        if result.get('is_dodge'):
            return
        element = self._infer_element(skill)
        if not element:
            self.dao_heart['value'] = 0
            self.dao_heart['last_element'] = ''
            return
        if self.dao_heart.get('last_element') == element:
            self.dao_heart['value'] = min(self.dao_heart['cap'], self.dao_heart['value'] + 1)
        else:
            self.dao_heart['value'] = 1
            self.dao_heart['last_element'] = element
        value = self.dao_heart['value']
        self._log('dao_heart', f"☯️ {element}行道心积累至{value}/{self.dao_heart['cap']}层。")
        if value == 3:
            self._log('dao_heart', '✨ 道心可用：下回合可选择「道心爆发」或「道心延势」。')
        elif value == self.dao_heart['cap']:
            self._log('dao_heart', '🔮 道心圆满：可选择「留存道心」强化下一次五行技能。')

    def _boss_mechanics(self):
        configured = self.enemy.role_data.get("boss_mechanics") or []
        valid = [
            {**item, "threshold": float(item.get("threshold", 0)), "duration": int(item.get("duration", 2)), "drop_weight": int(item.get("drop_weight", 0))}
            for item in configured if isinstance(item, dict) and item.get("stage")
        ]
        return valid or [dict(item) for item in DEFAULT_BOSS_MECHANICS]

    def _prepare_boss_tianji(self) -> None:
        """Boss 在血量跨越 75%/40% 时预告一次，玩家可在该回合破局。"""
        if self.enemy.entity_type != 'boss' or self.boss_tianji.get('intent'):
            return
        hp_ratio = self.enemy.hp / max(1, self.enemy.max_hp)
        triggered = self.boss_tianji['triggered']
        available = [item for item in self._boss_mechanics() if item['stage'] not in triggered and hp_ratio <= item['threshold']]
        if not available:
            return
        intent = {**min(available, key=lambda item: item['threshold']), 'broken': False}
        triggered.append(intent['stage'])
        self.boss_tianji['intent'] = intent
        self._log('boss_telegraph', f"☯️ {self.enemy.name} 显化「{intent['name']}」：本回合使用{intent['counter_name']}技能可破局！")

    def _resolve_boss_tianji(self) -> None:
        intent = self.boss_tianji.get('intent')
        if not intent:
            return
        if intent.get('broken'):
            self.boss_tianji.setdefault('broken_stages', []).append(intent['stage'])
            self.boss_tianji['reward_weight_bonus'] = self.boss_tianji.get('reward_weight_bonus', 0) + intent.get('drop_weight', 0)
            self._log('boss_break', f"✅ 「{intent['name']}」已被破局，Boss 未能获得强化。")
            feature_effect = ((self.role_special.get('feature') or {}).get('effect') or {})
            if feature_effect.get('type') == 'BOSS_BREAK_HEAL':
                percent = max(1, min(10, int(feature_effect.get('value', 0))))
                heal, healing_reduced = self.player.receive_heal(int(self.player.max_hp * percent / 100))
                self._log(
                    'role_feature',
                    f"🌸 苦海种金莲回复{heal}点气血"
                    + (f"（治疗压制{healing_reduced}%）" if healing_reduced else "") + "。",
                )
        elif not self.enemy.is_dead():
            self.enemy.add_buff(Buff(intent['effect'], intent['value'], intent.get('duration', 2), intent['name'], intent['name']))
            effect_name = '防御' if intent['effect'] == 'defense_up' else '攻击'
            self._log('boss_resolve', f"⚠️ 天机未破！{self.enemy.name}{effect_name}提升{intent['value']}%，持续2回合。")
        self.boss_tianji['intent'] = None
        insight_source = self.boss_tianji.get('insight_source')
        if insight_source:
            self._set_threat_insight(insight_source, force=True)

    def _execute_normal_attack(self, attacker: CombatEntity, defender: CombatEntity):
        """执行普通攻击"""
        self._log("action", f"⚔️ {attacker.name} 发动普通攻击！")

        result = {
            'skill_name': '普通攻击',
            'damage': 0,
            'heal': 0,
            'is_critical': False,
            'is_dodge': False,
            'reflect_damage': 0
        }

        # 检查是否被缴械
        if attacker.has_buff('disarm'):
            self._log("disarm", f"❌ {attacker.name} 被缴械，无法攻击！")
            return

        # 检查目标是否无法被选中
        if defender.has_buff('untargetable'):
            self._log("untargetable", f"👻 {defender.name} 处于隐身状态，无法被攻击！")
            return

        # 检查闪避
        hit_rate = 0.95 * (attacker.get_effective_hit() /
                          (attacker.get_effective_hit() + defender.get_effective_dodge()))

        if attacker.has_buff('blind'):
            hit_rate *= 0.5

        if random.random() > hit_rate:
            result['is_dodge'] = True
            self._log("dodge", f"💨 {defender.name} 闪避了攻击！")
            return

        # 检查无敌
        if defender.has_buff('invincible') or defender.has_buff('immortal'):
            self._log("invincible", f"🛡️ {defender.name} 处于无敌状态，免疫伤害！")
            return

        atk = attacker.get_effective_attack()
        dfn = defender.get_effective_defense()
        pierce = attacker.pierce + attacker.pierce_mod

        K = 800
        effective_defense = max(0, dfn * (1 - min(pierce, 0.9)))
        damage_reduction = effective_defense / (effective_defense + K)
        base_damage = atk * (1 - damage_reduction)

        damage = base_damage * random.uniform(0.85, 1.15)
        damage = int(max(1, damage))

        if random.random() < attacker.get_effective_crit():
            crit_dmg = attacker.crit_dmg
            if attacker.has_buff('crit_dmg_up'):
                for buff in attacker.buffs:
                    if buff.buff_type == 'crit_dmg_up':
                        crit_dmg *= (1 + buff.value / 100)
            damage = int(damage * crit_dmg)
            result['is_critical'] = True

        damage, shield_absorbed = defender.mitigate_with_shield(damage)
        result['damage'] = damage
        result['shield_absorbed'] = shield_absorbed
        defender.hp -= damage
        self._apply_player_damage_traits(attacker, defender, result)
        damage = int(result['damage'])

        # 处理反射
        if defender.has_buff('reflect'):
            for buff in defender.buffs:
                if buff.buff_type == 'reflect':
                    result['reflect_damage'] = int(damage * buff.value / 100)
                    attacker.hp -= result['reflect_damage']
                    if result['reflect_damage'] > 0:
                        self._log("reflect", f"↩️ {defender.name} 反弹了 {result['reflect_damage']} 点伤害！")

        # 吸血
        if attacker.lifesteal > 0:
            heal = int(damage * attacker.lifesteal)
            actual_heal, healing_reduced = attacker.receive_heal(heal)
            if actual_heal > 0:
                suffix = f"（治疗压制{healing_reduced}%）" if healing_reduced else ""
                self._log("lifesteal", f"❤️ {attacker.name} 吸取了 {actual_heal} 点生命！{suffix}")

        self._log_damage_result(attacker, defender, result)

    def _apply_role_special_passive(self) -> None:
        passive = self.role_special.get('passive')
        if not passive or self.role_special.get('passive_triggered'):
            return
        effect = passive.get('effect') or {}
        if effect.get('trigger', 'BATTLE_START') != 'BATTLE_START':
            return
        effect_type = effect.get('type')
        raw_value = int(effect.get('value', 0) or 0)
        value = max(0, min(15, raw_value))
        duration = max(1, int(effect.get('duration', 1)))
        final_value = value
        if effect_type == 'ENEMY_ATTACK_DOWN':
            self.enemy.add_buff(Buff('attack_down', value, duration, passive['name'], passive['name']))
            message = f"🔥 专属被动「{passive['name']}」压制敌方攻击{value}%，持续{duration}回合。"
        elif effect_type == 'PLAYER_DEFENSE_UP':
            self.player.add_buff(Buff('defense_up', value, duration, passive['name'], passive['name']))
            message = f"🛡️ 专属被动「{passive['name']}」提升自身防御{value}%，持续{duration}回合。"
        elif effect_type == 'PLAYER_SPEED_UP':
            self.player.add_buff(Buff('speed_up', value, duration, passive['name'], passive['name']))
            message = f"⚡ 专属被动「{passive['name']}」提升自身速度{value}%，持续{duration}回合。"
        elif effect_type == 'CONTROL_RESIST':
            final_value = max(0, min(30, raw_value))
            reduced_rounds = max(1, min(2, (final_value + 9) // 15))
            self.player.control_resist_value = final_value
            self.player.control_resist_rounds = reduced_rounds
            self.player.control_resist_available = True
            message = (
                f"🧠 专属被动「{passive['name']}」获得{final_value}点控制抗性；"
                f"本场首次硬控缩短{reduced_rounds}回合。"
            )
        elif effect_type == 'THREAT_INSIGHT':
            final_value = 0
            self._set_threat_insight(passive['name'])
            message = f"🔮 专属被动「{passive['name']}」已冻结本场最高威胁与下一机制提示。"
        else:
            final_value = 0
            message = f"🔎 专属被动「{passive['name']}」已记录本场敌方威胁与破局信息。"
        self.role_special['passive_triggered'] = True
        self.role_special['events'].append({'round': self.round, 'type': 'PASSIVE', 'id': passive.get('id'), 'name': passive['name'], 'final_value': final_value})
        self._log('role_special_passive', message)

    def _apply_role_special_conditional_passive(self) -> None:
        passive = self.role_special.get('passive')
        if not passive or self.role_special.get('passive_triggered'):
            return
        effect = passive.get('effect') or {}
        if effect.get('trigger') != 'LOW_HP':
            return
        threshold = max(1, min(90, int(effect.get('threshold', 30))))
        if self.player.hp > self.player.max_hp * threshold / 100:
            return
        value = max(1, min(10, int(effect.get('value', 8))))
        if effect.get('type') == 'PLAYER_HEAL':
            final_value, healing_reduced = self.player.receive_heal(int(self.player.max_hp * value / 100))
            message = f"💚 专属被动「{passive['name']}」在低血量时恢复{final_value}点生命。"
        else:
            self.player.add_buff(Buff('shield', value, 2, passive['name'], passive['name']))
            self._boost_first_player_shield()
            final_value = value
            message = f"🛡️ 专属被动「{passive['name']}」在低血量时生成{value}%护身屏障。"
        self.role_special['passive_triggered'] = True
        self.role_special['events'].append({'round': self.round, 'type': 'PASSIVE', 'id': passive.get('id'), 'name': passive['name'], 'final_value': final_value})
        self._log('role_special_passive', message)

    def _apply_role_feature(self) -> None:
        feature = self.role_special.get('feature') or {}
        effect = feature.get('effect') or {}
        if not feature.get('feature_name'):
            return
        effect_type = effect.get('type')
        if effect_type == 'PLAYER_DEFENSE_UP':
            value = min(15, int(effect.get('value', 0)))
            self.player.add_buff(Buff('defense_up', value, max(1, int(effect.get('duration', 1))), feature['feature_name'], feature['feature_name']))
            detail = f"防御提升{value}%"
        elif effect_type == 'PLAYER_SHIELD':
            value = min(10, int(effect.get('value', 0)))
            self.player.add_buff(Buff('shield', value, 2, feature['feature_name'], feature['feature_name']))
            self._boost_first_player_shield()
            detail = f"获得{value}%护盾减伤"
        elif effect_type == 'THREAT_INSIGHT':
            self._set_threat_insight(feature['feature_name'])
            detail = '显示本场最高威胁与下一 Boss 机制'
        elif effect_type == 'BOSS_DAMAGE':
            value = min(10, int(effect.get('value', 0)))
            detail = f'对 Boss 造成的普攻与技能伤害提升{value}%'
        elif effect_type == 'BOSS_BREAK_HEAL':
            value = min(10, int(effect.get('value', 0)))
            detail = f'每次成功破解 Boss 机制恢复{value}%最大气血'
        else:
            detail = '本场已冻结，未使用未知数值标签'
        self._log('role_feature', f"🌌 角色机制「{feature['feature_name']}」生效：{detail}。")

    def _execute_role_special(self) -> None:
        active = self.role_special.get('active') or {}
        if not active or self.role_special.get('used'):
            self._log('role_special', '❌ 当前没有可施放的专属能力。')
            return
        effect = active.get('effect') or {}
        effect_type = str(effect.get('type', 'DAMAGE')).upper()
        required_intent = max(0, min(5, int(effect.get('battle_intent', 0))))
        current_intent = max(0, int(self.role_special.get('battle_intent', 0)))
        if required_intent and current_intent < required_intent:
            self._log('role_special', f'❌ 战意不足，需要{required_intent}层才能施放。')
            return
        if required_intent:
            self.role_special['battle_intent'] = current_intent - required_intent
            self._log('battle_intent', f'🔥 消耗{required_intent}层战意发动专属能力。')

        multiplier = max(0.0, min(2.0, float(active.get('multiplier', 0))))
        base_value = max(1, int(self.player.get_effective_attack() * max(1.0, self.player.crit_dmg)))
        conditional_bonus = 0
        if effect.get('target_hp_below') and self.enemy.hp <= self.enemy.max_hp * int(effect['target_hp_below']) / 100:
            conditional_bonus += max(0, min(15, int(effect.get('damage_bonus', 0))))
        if effect.get('self_hp_above') and self.player.hp >= self.player.max_hp * int(effect['self_hp_above']) / 100:
            conditional_bonus += max(0, min(15, int(effect.get('damage_bonus', 10))))
        if effect.get('first_round_bonus') and self.round == 1:
            conditional_bonus += max(0, min(15, int(effect['first_round_bonus'])))
        if effect.get('boss_bonus') and self.enemy.entity_type == 'boss':
            conditional_bonus += max(0, min(15, int(effect['boss_bonus'])))
        if effect.get('round_at_least') and self.round >= int(effect['round_at_least']):
            conditional_bonus += max(0, min(15, int(effect.get('damage_bonus', 0))))
        if required_intent:
            conditional_bonus += max(0, min(15, int(effect.get('damage_bonus', 0))))

        shield = next((item for item in self.enemy.buffs if item.buff_type == 'shield'), None)
        shield_break_bonus = 0
        if shield and effect.get('shield_bonus'):
            shield_break_bonus = max(0, min(10, int(effect.get('shield_bonus', 0))))
            conditional_bonus += shield_break_bonus
        conditional_bonus = min(25, conditional_bonus)

        raw_damage = int(base_value * (1 + multiplier) * (1 + conditional_bonus / 100))
        defense_ignore = max(0, min(15, int(effect.get('defense_ignore', 0)))) / 100
        defense = max(0, self.enemy.get_effective_defense() * (1 - defense_ignore))
        damage = max(1, int(raw_damage * (1 - defense / (defense + 800))))
        shield_absorbed = 0
        if not shield_break_bonus:
            damage, shield_absorbed = self.enemy.mitigate_with_shield(damage)
        self.enemy.hp -= damage

        trait_result = {'damage': damage}
        self._apply_player_damage_traits(
            self.player,
            self.enemy,
            trait_result,
            gain_intent=False,
        )
        damage = int(trait_result['damage'])
        if self.enemy.entity_type == 'boss':
            capped_damage = min(damage, max(1, int(self.enemy.max_hp * .03)))
            if capped_damage != damage:
                self.enemy.hp += damage - capped_damage
                damage = capped_damage

        if shield_break_bonus and shield in self.enemy.buffs:
            self.enemy.buffs.remove(shield)
            self.enemy._reset_modifiers()
            self.enemy._apply_buff_modifiers()
            self._log(
                'role_special_effect',
                f"🪲 「{active.get('name')}」破除敌方护盾并获得{shield_break_bonus}%有限增伤。",
            )

        self.role_special['used'] = True
        event = {
            'round': self.round, 'type': 'ACTIVE', 'id': active.get('id'), 'name': active.get('name'),
            'base_value': base_value,
            'multiplier': multiplier,
            'conditional_bonus': conditional_bonus,
            'final_value': damage,
            'shield_absorbed': shield_absorbed,
            'shield_break_bonus': shield_break_bonus,
            'intent_spent': required_intent,
            'effect': effect,
        }
        self.role_special['events'].append(event)
        self._log('role_special', f"🌟 {self.player.name}施展专属能力「{active.get('name', '未名之力')}」，造成{damage}点伤害！")
        if shield_absorbed:
            self._log('shield', f"🛡️ {self.enemy.name}的护盾吸收了{shield_absorbed}点伤害。")

        if effect.get('burn'):
            self.enemy.add_buff(Buff('burning', 2, min(2, int(effect['burn'])), active.get('name', ''), '专属灼烧'))
            self._log('role_special_effect', f"🔥 {self.enemy.name}受到专属灼烧；该效果不触发五行反应。")
        if effect.get('resilience_down'):
            value = min(15, int(effect['resilience_down']))
            self.enemy.add_buff(Buff('defense_down', value, 2, active.get('name', ''), '韧性削减'))
            self._log('role_special_effect', f"⚔️ {self.enemy.name}韧性降低{value}%。")
        if effect.get('healing_down'):
            value = min(20, int(effect['healing_down']))
            self.enemy.add_buff(Buff('healing_down', value, 2, active.get('name', ''), '治疗压制'))
            self._log('role_special_effect', f"☯️ {self.enemy.name}下一次治疗效果降低{value}%。")
        if effect.get('speed_down'):
            value = min(15, int(effect['speed_down']))
            self.enemy.add_buff(Buff('speed_down', value, 2, active.get('name', ''), '速度压制'))
            self._log('role_special_effect', f"💨 {self.enemy.name}下一回合速度降低{value}%。")
        if effect_type == 'DAMAGE_DISPEL' and effect.get('dispel'):
            removable = [buff for buff in self.enemy.buffs if buff.buff_type.endswith('_up')]
            if removable:
                self.enemy.buffs.remove(removable[0])
                self.enemy._reset_modifiers()
                self.enemy._apply_buff_modifiers()
                self._log('role_special_effect', f"✨ 「{active.get('name')}」净化了敌方一项增益。")
        if effect.get('shield_percent'):
            value = min(10, int(effect['shield_percent']))
            self.player.add_buff(Buff('shield', value, 2, active.get('name', ''), '专属护盾'))
            self._boost_first_player_shield()
            self._log('role_special_effect', f"🛡️ {self.player.name}获得{value}%专属护盾。")
        if effect_type == 'DAMAGE_HEAL':
            if effect.get('clear_dot'):
                removable = next((buff for buff in self.player.buffs if buff.buff_type in ('burning', 'poison', 'damage_over_time')), None)
                if removable:
                    self.player.buffs.remove(removable)
                    self._log('role_special_effect', f"✨ 「{active.get('name')}」清除了一项持续伤害。")
            if effect.get('heal_damage_percent'):
                heal = int(damage * min(5, int(effect['heal_damage_percent'])) / 100)
            else:
                heal = int(self.player.max_hp * min(10, int(effect.get('heal_percent', 0))) / 100)
            cap = int(self.player.max_hp * min(10, int(effect.get('heal_percent_cap', 10))) / 100)
            heal, healing_reduced = self.player.receive_heal(max(0, min(heal, cap)))
            if heal:
                self._log('role_special_effect', f"💚 专属能力为{self.player.name}恢复{heal}点生命。")
            if healing_reduced:
                self._log('healing_down', f"☯️ 治疗压制使本次恢复降低{healing_reduced}%。")

        if effect_type == 'COPY_WEAK' or effect.get('copy_weak'):
            copy_ratio = 35
            echo_damage = max(1, damage * copy_ratio // 100)
            self.role_special['pending_copy'] = {
                'name': active.get('name', '弱化投影'),
                'trigger_round': self.round + 1,
                'damage': echo_damage,
                'ratio': copy_ratio,
            }
            self.role_special['events'].append({
                'round': self.round,
                'type': 'COPY_SCHEDULE',
                'name': active.get('name'),
                'trigger_round': self.round + 1,
                'damage': echo_damage,
            })
            self._log('role_special_effect', f"🌌 已记录弱化投影，将在下一回合复制{copy_ratio}%伤害。")

        if effect.get('sword_intent'):
            gain = max(1, min(1, int(effect.get('sword_intent', 1))))
            before = max(0, int(self.role_special.get('sword_intent', 0)))
            self.role_special['sword_intent'] = min(3, before + gain)
            self.role_special['events'].append({
                'round': self.round,
                'type': 'SWORD_INTENT',
                'before': before,
                'after': self.role_special['sword_intent'],
            })
            self._log('sword_intent', f"⚔️ 青元剑意积累至{self.role_special['sword_intent']}/3层。")

        if effect.get('threat_insight'):
            self._set_threat_insight(active.get('name', '先见而战'), force=True)

    def _log_skill_result(self, actor: CombatEntity, target: CombatEntity, skill: Skill, result: Dict):
        """记录技能结果"""
        if result['is_dodge']:
            self._log("dodge", f"💨 {target.name} 闪避了 {skill.name}！")
            # 闪避技能不会获得buff
            return

        if result['damage'] > 0:
            crit_text = " [暴击!]" if result['is_critical'] else ""
            self._log("damage", f"💥 {skill.name} 对 {target.name} 造成 {result['damage']} 点伤害！{crit_text}")

            if result['reflect_damage'] > 0:
                self._log("reflect", f"↩️ {target.name} 反弹了 {result['reflect_damage']} 点伤害！")
        elif result['heal'] > 0:
            self._log("heal", f"💚 {skill.name} 回复了 {result['heal']} 点生命！")

        # 记录BUFF应用（只有技能命中后才显示）
        for buff in result.get('buffs_applied', []):
            self._log("buff", f"✨ {buff['target']} 获得 {buff['buff_name']}（持续{buff['duration']}回合）")

    def _log_damage_result(self, attacker: CombatEntity, defender: CombatEntity, result: Dict):
        """记录伤害结果"""
        if result['damage'] > 0:
            crit_text = " [暴击!]" if result['is_critical'] else ""
            self._log("damage", f"💥 造成 {result['damage']} 点伤害！{crit_text}")
        elif result['heal'] > 0:
            self._log("heal", f"💚 回复了 {result['heal']} 点生命！")

    def _end_of_round(self):
        """回合结束处理"""
        self._log("round_end", "〖回合结算〗")

        for entity in [self.player, self.enemy]:
            if not entity.is_dead():
                dot_damage, hot_heal = entity.process_dot_hot()

                if dot_damage > 0:
                    self._log("dot", f"🔥 {entity.name} 受到持续伤害：-{dot_damage} HP")
                if hot_heal > 0:
                    self._log("hot", f"💚 {entity.name} 持续回复：+{hot_heal} HP")

                entity.update_cooldowns()

                old_buffs = entity.buffs.copy()
                entity.update_buffs()
                expired = [b for b in old_buffs if b not in entity.buffs]
                if expired:
                    expired_names = [self._get_buff_name(b) for b in expired]
                    self._log("buff_expire", f"⏰ {entity.name} 的 {', '.join(expired_names)} 效果消失")

            status = entity.get_status_summary()
            if status:
                if entity.hp < 0:
                    entity.hp = 0
                self._log("status", f"📊 {entity.name}: HP={entity.hp}/{entity.max_hp} {status}")
            else:
                if entity.hp < 0:
                    entity.hp = 0
                self._log("status", f"📊 {entity.name}: HP={entity.hp}/{entity.max_hp}")

            if entity.is_dead():
                self._log("death", f"💀 {entity.name} 倒下了！")

    def _get_buff_name(self, buff_input) -> str:
        """
        获取BUFF名称
        支持传入Buff对象或buff_type字符串
        """
        if hasattr(buff_input, 'buff_type'):
            buff_type = buff_input.buff_type
            buff_name = getattr(buff_input, 'buff_name', '')
            source_name = getattr(buff_input, 'source_name', '')
            return _format_lore_buff_name(buff_type, source_name, buff_name)
        return _format_lore_buff_name(buff_input, "", "")

    def _check_combat_end(self) -> bool:
        """检查战斗是否结束"""
        if self.player.is_dead():
            self.winner = self.enemy
            return True
        if self.enemy.is_dead():
            self.winner = self.player
            return True
        return False

    def _end_combat(self):
        """战斗结束"""
        if self.combat_ended:
            return
        self.combat_ended = True
        if self.winner:
            self._log("combat_end", f"\n═══ 战斗结束 ═══")
            self._log("winner", f"🏆 {self.winner.name} 获得胜利！")
        else:
            self._log("combat_end", f"\n═══ 战斗结束 ═══")
            self._log("draw", "⚖️ 战斗平局！")

    def _log(self, log_type: str, message: str):
        """记录战斗日志"""
        self.combat_log.append({
            'round': self.round,
            'type': log_type,
            'message': message
        })
        # Windows 默认 GBK 控制台无法输出部分表情符号，不能让日志输出中断战斗。
        try:
            print(message)
        except UnicodeEncodeError:
            print(message.encode('ascii', 'backslashreplace').decode('ascii'))

    def get_combat_summary(self) -> Dict:
        """获取战斗摘要"""
        return {
            'total_rounds': self.round,
            'winner': self.winner.name if self.winner else None,
            'player_hp': self.player.hp,
            'enemy_hp': self.enemy.hp,
            'total_skills_used': len(self.skill_history),
            'skill_history': self.skill_history,
            'boss_tianji': copy.deepcopy(self.boss_tianji),
            'reaction_targets_this_round': list(self.reaction_targets_this_round),
            'dao_heart': copy.deepcopy(self.dao_heart),
            'role_special': copy.deepcopy(self.role_special),
            'spirit_beast': copy.deepcopy(self.spirit_beast),
        }

    def to_snapshot(self) -> Dict:
        """导出可写入 JSON 的战斗快照。"""
        first_side = None
        if self.first is self.player:
            first_side = 'player'
        elif self.first is self.enemy:
            first_side = 'enemy'
        winner_side = None
        if self.winner is self.player:
            winner_side = 'player'
        elif self.winner is self.enemy:
            winner_side = 'enemy'
        return {
            'player': self.player.to_snapshot(),
            'enemy': self.enemy.to_snapshot(),
            'round': self.round,
            'max_rounds': self.max_rounds,
            'combat_log': copy.deepcopy(self.combat_log),
            'skill_history': copy.deepcopy(self.skill_history),
            'first_side': first_side,
            'winner_side': winner_side,
            'initialized': self.initialized,
            'combat_ended': self.combat_ended,
            'boss_tianji': copy.deepcopy(self.boss_tianji),
            'reaction_targets_this_round': list(self.reaction_targets_this_round),
            'dao_heart': copy.deepcopy(self.dao_heart),
            'role_special': copy.deepcopy(self.role_special),
            'spirit_beast': copy.deepcopy(self.spirit_beast),
        }

    @classmethod
    def from_snapshot(cls, snapshot: Dict) -> 'CombatManager':
        manager = cls(
            CombatEntity.from_snapshot(snapshot['player']),
            CombatEntity.from_snapshot(snapshot['enemy']),
            max_rounds=snapshot.get('max_rounds', 50),
        )
        manager.round = snapshot.get('round', 0)
        manager.combat_log = copy.deepcopy(snapshot.get('combat_log', []))
        manager.skill_history = copy.deepcopy(snapshot.get('skill_history', []))
        manager.initialized = snapshot.get('initialized', False)
        manager.combat_ended = snapshot.get('combat_ended', False)
        manager.boss_tianji = copy.deepcopy(snapshot.get('boss_tianji', manager.boss_tianji))
        manager.reaction_targets_this_round = set(snapshot.get('reaction_targets_this_round', []))
        manager.dao_heart = copy.deepcopy(snapshot.get('dao_heart', manager.dao_heart))
        manager.role_special = copy.deepcopy(snapshot.get('role_special', manager.role_special))
        manager.spirit_beast = copy.deepcopy(snapshot.get('spirit_beast', manager.spirit_beast))
        first_side = snapshot.get('first_side')
        if first_side == 'player':
            manager.first, manager.second = manager.player, manager.enemy
        elif first_side == 'enemy':
            manager.first, manager.second = manager.enemy, manager.player
        winner_side = snapshot.get('winner_side')
        if winner_side == 'player':
            manager.winner = manager.player
        elif winner_side == 'enemy':
            manager.winner = manager.enemy
        return manager


# ================================
# 工厂函数
# ================================

def create_skill_from_db(skill_data: Dict) -> Skill:
    """从数据库数据创建技能对象"""
    return Skill(
        id=skill_data['id'],
        name=skill_data['skill_name'],
        skill_type=skill_data['skill_type'],
        target_type=skill_data.get('target_type', 'enemy'),
        value=skill_data['value'],
        is_percent=skill_data['is_percent'],
        item_id=skill_data.get('item_id'),
        cooldown=skill_data.get('cooldown', 0),
        mana_cost=skill_data.get('mana_cost', 0),
        buff_type=skill_data.get('buff_type'),
        buff_value=skill_data.get('buff_value', 0),
        buff_duration=skill_data.get('buff_duration', 0),
        buff_target=skill_data.get('buff_target', 2),
        buff_name=skill_data.get('buff_name', ''),
        description=skill_data.get('buff_desc', skill_data.get('skill_desc', '')),
        element=skill_data.get('element', '')
    )


def create_combat_entity(role_data: Dict, skill_data_list: List[Dict] = None) -> CombatEntity:
    """从数据库数据创建战斗实体"""
    skills = []
    if skill_data_list:
        for skill_data in skill_data_list:
            skills.append(create_skill_from_db(skill_data))

    return CombatEntity(
        name=role_data['name'],
        role_data=role_data,
        skill_list=skills
    )
