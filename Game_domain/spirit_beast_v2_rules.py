# -*- coding: utf-8 -*-
"""《诸天灵契》V2 纯规则：目录、保底、养成、灵阵与奖励上限。"""

from datetime import date
from hashlib import sha256
from random import Random


RULE_VERSION = "spirit-beast.v2"
WORLDS = ("斗气大陆", "仙罡星域", "大荒", "北斗星域", "人界灵界", "沧元界")
QUALITIES = ("灵品", "玄品", "地品", "天品")
QUALITY_RANK = {name: index + 1 for index, name in enumerate(QUALITIES)}
QUALITY_POWER_BP = {"灵品": 10000, "玄品": 10400, "地品": 10800, "天品": 11800}
STAGES = ("幼灵", "启智", "凝丹", "化形", "返祖", "真灵", "太古")
SLOTS = ("主契", "护契", "辅契")
TEMPERAMENTS = ("勇猛", "沉稳", "灵慧", "机敏")
ROLE_LABELS = {
    "STRIKER": "攻伐", "GUARDIAN": "守御", "HEALER": "生息",
    "DISRUPTOR": "控场", "BREAKER": "破阵",
}
ROLE_BUFF = {
    "STRIKER": ("attack_up", 12),
    "GUARDIAN": ("defense_up", 12),
    "HEALER": ("heal_over_time", 8),
    "DISRUPTOR": ("speed_up", 12),
    "BREAKER": ("penetration_up", 10),
}
WORLD_ROLE = {
    "斗气大陆": "萧炎", "仙罡星域": "王林", "大荒": "石昊",
    "北斗星域": "叶凡", "人界灵界": "韩立", "沧元界": "孟川",
}
WORLD_ELEMENTS = {
    "斗气大陆": "火", "仙罡星域": "水", "大荒": "雷",
    "北斗星域": "金", "人界灵界": "木", "沧元界": "风",
}
STAGE_COSTS = (1000, 2000, 4000, 7000, 11000, 16000)
STAGE_MATERIALS = (8, 16, 28, 44, 66, 96)

# id, 名称, 世界, 品质, 定位, 元素, 天赋机器码, 天赋名, 简述
TEMPLATES = (
    (1, "赤焰灵狐", "诸天通用", "灵品", "STRIKER", "火", "BURN_CHASE", "焰尾追击", "灼烧后弱化追击，每场最多2次。"),
    (2, "玄甲龟", "诸天通用", "灵品", "GUARDIAN", "土", "LOW_HP_SHIELD", "玄甲护主", "首次低于半血时生成护盾。"),
    (3, "青木鹿", "诸天通用", "灵品", "HEALER", "PERIODIC_HEAL", "回春灵息", "每三回合回复并减轻持续伤害。"),
    (4, "寒翎雀", "诸天通用", "灵品", "DISRUPTOR", "OPENING_SLOW", "霜羽迟滞", "开场加速，首次命中降低敌速。"),
    (101, "紫晶翼狮", "斗气大陆", "地品", "STRIKER", "火", "PURPLE_FIRE", "紫火震击", "强化灼烧目标受到的首次追击。"),
    (102, "太虚幼龙", "斗气大陆", "天品", "BREAKER", "空", "VOID_BREAK", "虚空挪移", "移除一层护盾并提高破甲。"),
    (103, "天妖凰影", "斗气大陆", "地品", "DISRUPTOR", "风", "PHOENIX_SPEED", "凰翼掠空", "抢先手并规避一次速度压制。"),
    (201, "蚊兽", "仙罡星域", "玄品", "DISRUPTOR", "血", "DEBUFF_TOUGHNESS", "血翅噬灵", "目标带减益时追加削韧。"),
    (202, "雷蛙", "仙罡星域", "地品", "BREAKER", "雷", "CAST_BREAK", "天雷震魂", "首领蓄力时提高破局效率。"),
    (203, "望月幼灵", "仙罡星域", "天品", "GUARDIAN", "月", "MOON_GUARD", "古神月守", "高血护主，低血转为回复。"),
    (301, "狻猊", "大荒", "地品", "BREAKER", "雷", "THUNDER_BREAK", "狻猊雷印", "雷行伤害追加削韧。"),
    (302, "朱厌", "大荒", "地品", "GUARDIAN", "土", "MOUNTAIN_BODY", "搬山战躯", "受击后短暂提高攻防。"),
    (303, "九头狮子", "大荒", "天品", "STRIKER", "金", "WAVE_WILL", "九首齐啸", "多波战斗保留一次战意。"),
    (401, "黑皇道影", "北斗星域", "天品", "DISRUPTOR", "阵", "FORMATION_HINT", "无始阵纹", "提示首领机制并降低阵法伤害。"),
    (402, "龙马", "北斗星域", "地品", "STRIKER", "风", "FIRST_STRIKE", "星路奔袭", "取得先手时追加冲击。"),
    (403, "九变神蚕", "北斗星域", "天品", "HEALER", "光", "COCOON_REBIRTH", "神蚕九变", "首次濒危时蜕变回复。"),
    (501, "噬金虫群", "人界灵界", "地品", "BREAKER", "金", "ARTIFACT_BREAK", "万虫噬器", "对护盾、法宝机制额外削韧。"),
    (502, "啼魂兽", "人界灵界", "天品", "DISRUPTOR", "魂", "SOUL_CLEANSE", "啼魂镇煞", "清除魂系减益并反制阴魂。"),
    (503, "豹麟兽", "人界灵界", "地品", "STRIKER", "风", "EXECUTE_CHASE", "豹麟追影", "敌方低于三成气血时追击。"),
    (601, "镜湖雷隼", "沧元界", "地品", "DISRUPTOR", "雷", "RESET_CHASE", "雷隼掠影", "首回合加速，破局后重置追击。"),
    (602, "城关玄犀", "沧元界", "地品", "GUARDIAN", "土", "TEAM_GUARD", "城关不退", "组队或世界首领中分担高额伤害。"),
    (603, "元神梦貘", "沧元界", "天品", "HEALER", "魂", "THREAT_SIGHT", "梦境观敌", "显示最高威胁并降低首次元神伤害。"),
)
TEMPLATE_BY_ID = {row[0]: row for row in TEMPLATES}
TEMPLATE_BY_NAME = {row[1]: row for row in TEMPLATES}

# id, 名称, 类别, 机器码, 数值, 冷却, 每场上限, 残页成本
SKILLS = (
    (1, "烈焰追袭", "攻伐", "SKILL_ATTACK", 6, 2, 3, 12),
    (2, "玄灵护障", "守御", "SKILL_SHIELD", 8, 3, 2, 12),
    (3, "万木回春", "生息", "SKILL_HEAL", 6, 3, 2, 12),
    (4, "霜风定势", "控场", "SKILL_SPEED", 6, 3, 2, 12),
    (5, "碎阵灵鸣", "破阵", "SKILL_BREAK", 8, 3, 2, 12),
    (6, "焚脉紫炎", "攻伐", "SKILL_BURN", 8, 3, 2, 24),
    (7, "生死轮转", "生息", "SKILL_EMERGENCY_HEAL", 8, 99, 1, 24),
    (8, "雷印破妄", "破阵", "SKILL_TOUGHNESS", 10, 4, 2, 24),
    (9, "阵纹先觉", "控场", "SKILL_HINT", 5, 99, 1, 24),
    (10, "城关同守", "守御", "SKILL_TEAM_GUARD", 10, 99, 1, 24),
)
SKILL_BY_ID = {row[0]: row for row in SKILLS}


def bounded_int(value, lower=0, upper=2_147_483_647):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = lower
    return min(upper, max(lower, value))


def week_key(day=None):
    year, week, _ = (day or date.today()).isocalendar()
    return f"{year}-W{week:02d}"


def deterministic_rng(*parts):
    seed = ":".join(str(part) for part in parts)
    return Random(sha256(seed.encode("utf-8")).hexdigest())


def stage_name(stage):
    return STAGES[bounded_int(stage, 0, len(STAGES) - 1)]


def bond_level(exp):
    return min(10, bounded_int(exp) // 100)


def level_exp_required(level):
    level = bounded_int(level, 1, 70)
    return 40 + level * 12


def feed_plan(level, exp, amount, role_level, stage=None):
    """每份灵息提供10经验，返回实际消耗及新等级；不跨越境界或角色上限。"""
    level = bounded_int(level, 1, 70)
    exp = bounded_int(exp)
    role_level = bounded_int(role_level, 1, 70)
    stage_cap = min(
        70,
        (bounded_int(stage, 0, 6) + 1) * 10
        if stage is not None
        else ((level - 1) // 10 + 1) * 10,
    )
    cap = min(stage_cap, role_level)
    available = bounded_int(amount)
    used = 0
    while used < available and level < cap:
        exp += 10
        used += 1
        need = level_exp_required(level)
        if exp >= need:
            exp -= need
            level += 1
    return {"used": used, "level": level, "exp": exp, "cap": cap}


def aptitude_total(values):
    return sum(bounded_int(value, 60, 100) for value in values)


def aptitude_average(values):
    return aptitude_total(values) // 4


def generate_aptitudes(uid, nonce, quality, minimum_total=0):
    rng = deterministic_rng("aptitude", uid, nonce, quality)
    floor = {"灵品": 60, "玄品": 66, "地品": 72, "天品": 78}.get(quality, 60)
    values = [rng.randint(floor, min(100, floor + 20)) for _ in range(4)]
    while sum(values) < minimum_total:
        index = min(range(4), key=values.__getitem__)
        if values[index] >= 100:
            break
        values[index] += 1
    return tuple(values)


def roll_quality(clue, ten_pity, sixty_pity, roll):
    """10次地品、60次天品硬保底；roll 为[0,9999]。"""
    ten_pity = bounded_int(ten_pity)
    sixty_pity = bounded_int(sixty_pity)
    roll = bounded_int(roll, 0, 9999)
    if sixty_pity >= 59:
        return "天品"
    if ten_pity >= 9:
        return "地品" if roll >= 500 else "天品"
    rates = {
        "稳定": (6200, 8700, 9900),
        "稀有": (2500, 6500, 9500),
        "未知": (3500, 7000, 9400),
    }.get(clue, (6200, 8700, 9900))
    if roll < rates[0]:
        return "灵品"
    if roll < rates[1]:
        return "玄品"
    if roll < rates[2]:
        return "地品"
    return "天品"


def choose_template(world, quality, uid, nonce, owned_template_ids=()):
    candidates = [row for row in TEMPLATES if row[3] == quality and (world == "未知" or row[2] == world)]
    if not candidates:
        candidates = [row for row in TEMPLATES if row[3] == quality]
    owned = {int(value) for value in owned_template_ids}
    protected = [row for row in candidates if row[0] not in owned]
    pool = protected or candidates
    return deterministic_rng("template", uid, nonce, world, quality).choice(pool)


def calculate_v2_power(profile):
    if not profile:
        return {"power": 0, "aptitude": 0, "bond_level": 0}
    values = (
        profile.get("apt_spirit", profile.get("aptitude", 60)),
        profile.get("apt_body", profile.get("aptitude", 60)),
        profile.get("apt_soul", profile.get("aptitude", 60)),
        profile.get("apt_speed", profile.get("aptitude", 60)),
    )
    average = aptitude_average(values)
    level = bounded_int(profile.get("level", 1), 1, 70)
    stage = bounded_int(profile.get("stage", 0), 0, 6)
    bloodline = bounded_int(profile.get("bloodline_nodes", 0), 0, 6)
    bond = bond_level(profile.get("bond_exp", 0))
    skill_count = bounded_int(profile.get("skill_count", 0), 0, 2)
    quality = str(profile.get("quality") or "灵品")
    raw = (
        500 + average * 20 + level * 55 + stage * 400
        + bloodline * 260 + bond * 120 + skill_count * 220
    )
    power = raw * QUALITY_POWER_BP.get(quality, 10000) // 10000
    return {
        "power": int(power), "aptitude": average,
        "bond_level": bond, "skill_count": skill_count,
    }


def formation_resonance(worlds, elements):
    valid_worlds = [value for value in worlds if value]
    valid_elements = [value for value in elements if value]
    if valid_worlds:
        counts = {world: valid_worlds.count(world) for world in set(valid_worlds)}
        world, count = max(counts.items(), key=lambda item: (item[1], item[0]))
        if world != "诸天通用" and count >= 2:
            return {"type": "WORLD", "world": world, "count": count, "value": 5 if count == 2 else 8}
    if len(valid_elements) == 3 and len(set(valid_elements)) == 3:
        return {"type": "ELEMENT", "world": "五行灵阵", "count": 3, "value": 5}
    return {"type": "NONE", "world": "未激活", "count": 0, "value": 0}


def unlocked_slots(garden_level):
    level = bounded_int(garden_level, 1, 10)
    return ("主契",) if level < 4 else (("主契", "护契") if level < 7 else SLOTS)


def dispatch_reward(kind, hours, garden_level, profile):
    hours = bounded_int(hours, 4, 12)
    efficiency = 100 + (bounded_int(garden_level, 1, 10) - 1) * 5 + bounded_int(profile.get("stage", 0)) * 5
    base = hours * efficiency // 100
    rewards = {"spirit_essence": base * 8, "beast_material": base}
    if kind == "采药":
        rewards["herb_token"] = max(1, base // 4)
    elif kind == "探矿":
        rewards["lingshi"] = base * 25
    elif kind == "寻迹":
        rewards["soul_fragment"] = max(1, base // 6)
    return rewards


def realm_reward(route, world, uid, key):
    rng = deterministic_rng("realm", uid, key, route, world)
    reward = {"spirit_essence": 80 + rng.randint(0, 40), "beast_material": 8 + rng.randint(0, 4)}
    if route == "血脉":
        reward["bloodline_essence"] = 3 + rng.randint(0, 2)
    elif route == "技能":
        reward["skill_page"] = 5 + rng.randint(0, 3)
    else:
        reward["story_token"] = 2 + rng.randint(0, 2)
    return reward


def return_refund(level, stage):
    essence = sum((level_exp_required(value) + 9) // 10 for value in range(1, bounded_int(level, 1, 70)))
    materials = sum(STAGE_MATERIALS[:bounded_int(stage, 0, 6)])
    return {"spirit_essence": essence, "beast_material": materials}
