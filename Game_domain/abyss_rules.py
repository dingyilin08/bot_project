# -*- coding: utf-8 -*-
"""轮海深渊的纯规则函数。"""

import math
import random
from decimal import Decimal
from typing import Dict, Iterable, List


ABYSS_WAVES = 6
ABYSS_MONSTERS_PER_WAVE = 5
ABYSS_MAX_KILLS = ABYSS_WAVES * ABYSS_MONSTERS_PER_WAVE
ABYSS_POST_BATTLE_HEAL_BP = 3000
ABYSS_PLACEMENT_MIN_LEVEL = 50
ABYSS_TIER_LEVELS = (1, 10, 20, 30, 40, 50, 60, 70, 80, 90)

# 与普通副本第一关保持同一基础数值。
ABYSS_BASE_STATS = {
    "gongji": 550,
    "fangyu": 380,
    "qixue": 2800,
    "sudu": 65,
    "baoji": 700,
    "baoshang": 3000,
    "shanbi": 600,
    "mingzhong": 3000,
    "pofang": 100,
    "xixue": 0,
}


def _positive_layer(layer_no: int) -> int:
    layer_no = int(layer_no)
    if layer_no < 1:
        raise ValueError("深渊层数必须大于0")
    return layer_no


def abyss_tier_index(layer_no: int) -> int:
    """返回0至9档；91层以后固定使用第10档怪物池。"""
    return min(9, (_positive_layer(layer_no) - 1) // 10)


def abyss_tier_min_level(layer_no: int) -> int:
    return ABYSS_TIER_LEVELS[abyss_tier_index(layer_no)]


def abyss_rating(kill_count: int) -> int:
    kills = max(0, min(ABYSS_MAX_KILLS, int(kill_count or 0)))
    if kills >= 30:
        return 3
    if kills >= 20:
        return 2
    if kills >= 10:
        return 1
    return 0


def abyss_monster_multiplier(layer_no: int, cross_world: bool = False) -> float:
    multiplier = Decimal(100 + 5 * _positive_layer(layer_no)) / Decimal(100)
    if cross_world:
        multiplier *= Decimal(120) / Decimal(100)
    return float(multiplier)


def build_abyss_monster_stats(
    layer_no: int,
    monster: Dict,
    *,
    cross_world: bool = False,
) -> Dict[str, int]:
    """把副本怪物模板换算为本层冻结属性。"""
    multiplier = Decimal(str(abyss_monster_multiplier(layer_no, cross_world)))
    ratios = {
        "gongji": Decimal(str(monster.get("atk_ratio") or 1)),
        "fangyu": Decimal(str(monster.get("def_ratio") or 1)),
        "qixue": Decimal(str(monster.get("hp_ratio") or 1)),
        "sudu": Decimal(str(monster.get("spd_ratio") or 1)),
        "baoji": Decimal(str(monster.get("crit_ratio") or 1)),
        "baoshang": Decimal(str(monster.get("crit_dmg_ratio") or 1)),
        "shanbi": Decimal(str(monster.get("dodge_ratio") or 1)),
        "mingzhong": Decimal(str(monster.get("hit_ratio") or 1)),
        "pofang": Decimal(1),
        "xixue": Decimal(1),
    }
    stats = {
        key: max(0 if key == "xixue" else 1, math.floor(Decimal(value) * ratios[key] * multiplier))
        for key, value in ABYSS_BASE_STATS.items()
    }
    stats.update({"max_fali": 100, "entity_type": monster.get("type", "normal")})
    return stats


def calculate_abyss_layer_reward(required_exp: int, layer_no: int, stars: int) -> Dict[str, int]:
    layer_no = _positive_layer(layer_no)
    stars = int(stars or 0)
    if stars not in (0, 1, 2, 3):
        raise ValueError("深渊星级必须为0至3")
    if stars == 0:
        return {"exp": 0, "lingshi": 0, "xianyu": 0}
    return {
        "exp": max(0, int(required_exp or 0)) // 1016,
        "lingshi": 300 + 15 * layer_no * stars,
        "xianyu": stars * 30,
    }


def calculate_reward_delta(
    required_exp: int,
    layer_no: int,
    previous_stars: int,
    new_stars: int,
    *,
    exp_rewarded: bool = False,
) -> Dict[str, int]:
    previous_stars = max(0, min(3, int(previous_stars or 0)))
    new_stars = max(0, min(3, int(new_stars or 0)))
    if new_stars <= previous_stars:
        return {"exp": 0, "lingshi": 0, "xianyu": 0}
    before = calculate_abyss_layer_reward(required_exp, layer_no, previous_stars)
    after = calculate_abyss_layer_reward(required_exp, layer_no, new_stars)
    return {
        "exp": 0 if exp_rewarded else after["exp"],
        "lingshi": after["lingshi"] - before["lingshi"],
        "xianyu": after["xianyu"] - before["xianyu"],
    }


def placement_target(role_level: int) -> int:
    role_level = int(role_level or 0)
    if role_level < ABYSS_PLACEMENT_MIN_LEVEL:
        raise ValueError("角色达到50级后才能参加深渊定级")
    return role_level


def select_wave_templates(
    normal_monsters: Iterable[Dict],
    boss_monsters: Iterable[Dict],
    *,
    rng_seed: str,
    wave_no: int,
) -> List[Dict]:
    """稳定生成4普通+1Boss；同一随机种子与波次可安全重放。"""
    normals = list(normal_monsters)
    bosses = list(boss_monsters)
    if not normals or not bosses:
        raise ValueError("深渊来源副本缺少普通怪或Boss模板")
    rng = random.Random(f"{rng_seed}:wave:{int(wave_no)}")
    selected = [dict(rng.choice(normals)) for _ in range(4)]
    selected.append(dict(rng.choice(bosses)))
    return selected
