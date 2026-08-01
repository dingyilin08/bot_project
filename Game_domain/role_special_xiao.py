# -*- coding: utf-8 -*-
"""萧炎：焚诀吞噬异火，以异火投影和融合火莲构成战斗养成。"""


ROLE_SPEC = {
    "template_id": 1,
    "role_name": "萧炎",
    "growth_name": "焚诀",
    "drop_name": "异火残焰",
    "essence_name": "火种精华",
    "core_name": "火莲核心",
    "growth_material": "焚诀感悟",
    "passive_lore": "丹火同源：萧炎炼丹时缩短20%基础耗时，不提高稀有丹药成功率。",
    "abilities": [
        {"code": "XY_FLAME_01", "name": "青莲地心火", "rarity": 4, "kind": "ACTIVE", "multiplier": .50, "fragment_cost": 10,
         "effect": {"type": "DAMAGE", "burn": 1}, "lore": "取自塔戈尔沙漠地底岩浆世界，火中生莲。"},
        {"code": "XY_FLAME_02", "name": "陨落心炎", "rarity": 4, "kind": "ACTIVE", "multiplier": .60, "fragment_cost": 20,
         "effect": {"type": "DAMAGE", "resilience_down": 10}, "lore": "无形心火淬炼斗气，亦能由内而外焚身。"},
        {"code": "XY_FLAME_03", "name": "海心焰", "rarity": 4, "kind": "ACTIVE", "multiplier": .70, "fragment_cost": 15,
         "effect": {"type": "DAMAGE", "shield_bonus": 10}, "lore": "深蓝火焰如海潮翻涌，克制护体之法。"},
        {"code": "XY_FLAME_04", "name": "骨灵冷火", "rarity": 4, "kind": "PASSIVE", "multiplier": .80, "fragment_cost": 20,
         "effect": {"type": "ENEMY_ATTACK_DOWN", "value": 10, "duration": 1, "trigger": "BATTLE_START"}, "lore": "极寒与极热相融，药老所传异火。"},
        {"code": "XY_FLAME_05", "name": "三千焱炎火", "rarity": 4, "kind": "ACTIVE", "multiplier": .90, "fragment_cost": 25,
         "effect": {"type": "DAMAGE_HEAL", "heal_percent": 5}, "lore": "星空中形成的不死之火，恢复力极强。"},
        {"code": "XY_FLAME_06", "name": "金帝焚天炎", "rarity": 5, "kind": "ACTIVE", "multiplier": 1.20, "fragment_cost": 50,
         "effect": {"type": "DAMAGE", "defense_ignore": 10}, "lore": "古族传承异火，号称焚尽万物。"},
        {"code": "XY_FLAME_07", "name": "净莲妖火", "rarity": 5, "kind": "ACTIVE", "multiplier": 1.50, "fragment_cost": 60,
         "effect": {"type": "DAMAGE_DISPEL", "dispel": 1}, "lore": "可净化万物的妖火，曾受净莲妖圣掌控。"},
        {"code": "XY_FLAME_08", "name": "虚无吞炎", "rarity": 5, "kind": "ACTIVE", "multiplier": 1.80, "fragment_cost": 70,
         "effect": {"type": "DAMAGE_HEAL", "heal_damage_percent": 5, "heal_percent_cap": 5}, "lore": "生于虚无，拥有吞噬万物之能。"},
        {"code": "XY_FLAME_09", "name": "帝炎", "rarity": 5, "kind": "ACTIVE", "multiplier": 2.00, "fragment_cost": 80,
         "effect": {"type": "DAMAGE", "defense_ignore": 15}, "lore": "万火归一的传承投影，以最高倍率表现炎帝之路。"},
    ],
    "stages": [
        {"stage": 1, "name": "黄阶", "growth_cost": 0, "unlock_count": 1, "effect": "开放异火主动技能"},
        {"stage": 2, "name": "玄阶", "growth_cost": 10, "unlock_count": 3, "effect": "开放异火战斗特性"},
        {"stage": 3, "name": "地阶", "growth_cost": 20, "unlock_count": 5, "effect": "开放三火融合"},
        {"stage": 4, "name": "准天阶", "growth_cost": 35, "unlock_count": 7, "effect": "开放第二套异火预设"},
        {"stage": 5, "name": "天阶", "growth_cost": 50, "unlock_count": 9, "effect": "融合结果获得均值保护"},
    ],
    "combo": {"type": "异火融合", "command": "异火融合", "core_cost": 3, "essence_cost": 20, "max_saved": 10},
    "rank": {"name": "异火排行榜", "primary": "融合异火倍率", "secondary": "继承特性稀有度"},
}
