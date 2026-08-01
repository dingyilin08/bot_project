# -*- coding: utf-8 -*-
"""角色专属战斗养成的玩家向介绍；能力、阶段和命令均复用正式配置。"""

from typing import Dict, Optional

from Game_domain.role_special_catalog import get_role_spec


_ROLE_COPY: Dict[str, Dict[str, str]] = {
    "萧炎": {
        "position": "以焚诀吞噬异火。先用稳定的异火主动削韧、破盾或续航，再以高阶异火完成爆发。",
        "growth": "收集异火残焰点亮九种异火，以焚诀感悟从黄阶进至天阶；地阶开始可进行三火融合。",
    },
    "王林": {
        "position": "以意境拆解战局。极境神识负责削韧，生死、因果与真假意境提供护盾、防御和抗控。",
        "growth": "收集意境残念与古神之血，沿古神一星至八星推进；四星后可将三种已点亮意境合道为本源神通。",
    },
    "韩立": {
        "position": "以飞剑数量建立先后手优势。风雷翅和大衍神念保障出手，剑阵与神雷负责破甲、驱散和压制。",
        "growth": "战斗锻成青竹剑胚，依次扩充至七十二口青竹蜂云剑；三十六口时开放大庚剑阵和法宝协同。",
    },
    "石昊": {
        "position": "以洞天极境统御宝术。先以雷霆、极速和护体建立节奏，后以鲲鹏、雷帝与草字剑诀应对强敌。",
        "growth": "战斗获得洞天灵魄，逐口开辟十大洞天；十洞天合一成为唯一洞天后，才能进行六道轮回组合。",
    },
    "叶凡": {
        "position": "以荒古圣体正面破禁。九秘负责攻伐、速度、预警与自愈，异象则按战斗成就解锁并按需选择。",
        "growth": "收集圣体精血，从轮海到仙台贯通五大秘境；四极秘境开放九秘连携，世界 Boss 还能取得天劫道痕与玄黄母气。",
    },
    "孟川": {
        "position": "以元神观敌和刀势决胜。先通过威胁提示判断破局点，再以心刀、魔锥、意之刀和无尽刀持续压制。",
        "growth": "收集元神星芒修至元神八层；四层起可把本人获胜的 PVE 战绩绘成真实战斗绘卷，用佳作以上绘卷进行刀势推演。",
    },
}

_ENTRY_COMMANDS = {
    "萧炎": ("萧炎养成", "异火图鉴", "异火祈愿 1次", "专属进阶"),
    "王林": ("王林养成", "意境图鉴", "意境祈愿 1次", "专属进阶"),
    "韩立": ("韩立养成", "法宝图鉴", "法宝祈愿 1次", "炼制飞剑"),
    "石昊": ("石昊养成", "宝术图鉴", "宝术祈愿 1次", "开辟洞天"),
    "叶凡": ("叶凡养成", "九秘图鉴", "九秘祈愿 1次", "圣体秘境"),
    "孟川": ("孟川养成", "刀法图鉴", "刀法祈愿 1次", "元神修炼"),
}


def render_role_special_intro(role_name: str, include_actions: bool = True) -> Optional[str]:
    """返回角色专属养成介绍；非专属角色返回 None，方便旧角色介绍平滑兼容。"""
    normalized_name = str(role_name or "").strip()
    spec = get_role_spec(normalized_name)
    copy = _ROLE_COPY.get(normalized_name)
    if not spec or not copy:
        return None

    enabled_abilities = [item["name"] for item in spec["abilities"] if item.get("enabled", True)]
    stages = " → ".join(item["name"] for item in spec["stages"])
    active_count = sum(item["kind"] == "ACTIVE" and item.get("enabled", True) for item in spec["abilities"])
    passive_count = sum(item["kind"] == "PASSIVE" and item.get("enabled", True) for item in spec["abilities"])

    output = f"##### ⚔️ {normalized_name}｜专属战斗养成玩法\n\n"
    output += "**核心定位：**\n"
    output += f"> {copy['position']}\n\n"
    output += "**养成主线：**\n"
    output += f"> {copy['growth']}\n"
    output += f"> 本角色专属主线为「{spec['growth_name']}」，材料包括 {spec['drop_name']}、{spec['essence_name']} 与 {spec['core_name']}。\n\n"
    output += "**阶段路线：**\n"
    output += f"> {stages}\n\n"
    output += "**战斗构筑：**\n"
    output += f"> 可点亮 {len(enabled_abilities)} 项能力（{active_count} 主动 / {passive_count} 被动）；代表能力：{'、'.join(enabled_abilities[:3])}。\n"
    output += f"> {spec['passive_lore']}\n"
    output += f"> 进阶后可进行「{spec['combo']['type']}」：{spec['combo']['command']} 能力1-能力2-能力3-自定义名称。\n\n"
    if spec.get("featured_system"):
        output += "**角色独有机制：**\n"
        output += f"> {spec['featured_system']}\n\n"
    output += "**PVE规则：**\n"
    output += "> 单人副本与世界 Boss 胜利可获得专属养成资源；专属主动每场最多施放一次，仅在 PVE 生效。\n"
    output += "> 专属主动不触发暴击或五行连锁；世界 Boss 单次专属伤害上限为其最大生命的 3%。\n"

    if include_actions:
        home, collection, pray, advance = _ENTRY_COMMANDS[normalized_name]
        output += "\n***\n"
        output += " | ".join([
            f"<qqbot-cmd-input text='{home}' show='专属养成' />",
            f"<qqbot-cmd-input text='{collection}' show='专属图鉴' />",
            f"<qqbot-cmd-input text='{pray}' show='祈愿1次' />",
            f"<qqbot-cmd-input text='{advance}' show='专属进阶' />",
        ])
    return output
