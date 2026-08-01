# -*- coding: utf-8 -*-
"""角色专属养成的纯配置目录；数据库种子与测试均以此为规则来源。"""

import importlib
from typing import Dict, Iterable, List, Optional


ROLE_MODULES = {
    "萧炎": "Game_domain.role_special_xiao",
    "王林": "Game_domain.role_special_wanglin",
}


def get_role_spec(role_name: str) -> Optional[Dict]:
    module_name = ROLE_MODULES.get(str(role_name or "").strip())
    if not module_name:
        return None
    return importlib.import_module(module_name).ROLE_SPEC


def iter_role_specs() -> Iterable[Dict]:
    for role_name in ROLE_MODULES:
        spec = get_role_spec(role_name)
        if spec:
            yield spec


def ability_map(role_name: str) -> Dict[str, Dict]:
    spec = get_role_spec(role_name) or {}
    return {item["code"]: item for item in spec.get("abilities", [])}


def four_star_abilities(role_name: str) -> List[Dict]:
    return [item for item in (get_role_spec(role_name) or {}).get("abilities", []) if item["rarity"] == 4]


def five_star_abilities(role_name: str) -> List[Dict]:
    return [item for item in (get_role_spec(role_name) or {}).get("abilities", []) if item["rarity"] == 5]


def validate_role_spec(spec: Dict) -> None:
    required = {"template_id", "role_name", "growth_name", "abilities", "stages"}
    missing = required - set(spec)
    if missing:
        raise ValueError(f"角色专属配置缺少字段：{sorted(missing)}")
    codes = [item["code"] for item in spec["abilities"]]
    if len(codes) != len(set(codes)):
        raise ValueError(f"{spec['role_name']}存在重复能力编号")
    if not any(item["rarity"] == 4 for item in spec["abilities"]):
        raise ValueError(f"{spec['role_name']}缺少四星战斗掉落")
    if not any(item["rarity"] == 5 for item in spec["abilities"]):
        raise ValueError(f"{spec['role_name']}缺少五星长期养成内容")
    for item in spec["abilities"]:
        if item["kind"] not in {"ACTIVE", "PASSIVE"}:
            raise ValueError(f"能力类型无效：{item['code']}")
        if not 0 <= float(item.get("multiplier", 0)) <= 2.0:
            raise ValueError(f"能力倍率越界：{item['code']}")
        if int(item.get("fragment_cost", 0)) <= 0:
            raise ValueError(f"点亮碎片数量无效：{item['code']}")


for _spec in iter_role_specs():
    validate_role_spec(_spec)
