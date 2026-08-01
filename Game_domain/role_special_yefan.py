# -*- coding: utf-8 -*-
"""叶凡：荒古圣体五秘境、圣体异象、九秘连携与万物母气鼎。"""


ROLE_SPEC = {
    "template_id":6,"role_name":"叶凡","growth_name":"圣体五秘境",
    "drop_name":"九秘残印","essence_name":"天尊道屑","core_name":"帝路碑拓","growth_material":"圣体精血",
    "growth_on_drop":True,"combo_min_stage":4,"boss_material_code":"ROLE_6_TRIBULATION",
    "world_material_code":"ROLE_6_MOTHER_QI","extra_materials":{"ROLE_6_TRIBULATION":"天劫道痕","ROLE_6_MOTHER_QI":"玄黄母气"},
    "passive_lore":"圣体破禁：面对高战力PVE敌人时，首次硬控改为一回合20%行动减伤。",
    "featured_system":"圣体异象：金色苦海、苦海种金莲、仙王临九天、锦绣山河、阴阳生死图、黄金神藏均由战斗成就解锁，不进入祈愿。",
    "features":[
        {"id":1,"name":"金色苦海","unlock_stage":2,"effect":{"type":"PLAYER_DEFENSE_UP","value":8,"duration":1}},
        {"id":2,"name":"苦海种金莲","unlock_stage":3,"effect":{"type":"BOSS_BREAK_HEAL","value":5}},
        {"id":3,"name":"仙王临九天","unlock_stage":3,"effect":{"type":"BOSS_DAMAGE","value":8}},
        {"id":4,"name":"锦绣山河","unlock_stage":4,"effect":{"type":"PLAYER_SHIELD","value":6}},
        {"id":5,"name":"阴阳生死图","unlock_stage":5,"effect":{"type":"PLAYER_DEFENSE_UP","value":10,"duration":1}},
        {"id":6,"name":"黄金神藏","unlock_stage":6,"effect":{"type":"THREAT_INSIGHT"}},
    ],
    "abilities":[
        {"code":"YF_SECRET_01","name":"斗字秘","rarity":4,"kind":"ACTIVE","multiplier":.50,"fragment_cost":10,"effect":{"type":"DAMAGE","resilience_down":8},"lore":"演化攻伐圣法，并改变一次破局标签。"},
        {"code":"YF_SECRET_02","name":"行字秘","rarity":4,"kind":"PASSIVE","multiplier":.50,"fragment_cost":15,"effect":{"type":"PLAYER_SPEED_UP","value":10,"duration":2,"trigger":"BATTLE_START"},"lore":"世间极速，改变首次行动顺序判定。"},
        {"code":"YF_SECRET_03","name":"兵字秘","rarity":4,"kind":"ACTIVE","multiplier":.60,"fragment_cost":20,"effect":{"type":"DAMAGE_DISPEL","dispel":1},"lore":"驾驭兵器，压制一次器物或武器机制。"},
        {"code":"YF_SECRET_04","name":"组字秘","rarity":4,"kind":"PASSIVE","multiplier":.50,"fragment_cost":25,"effect":{"type":"PLAYER_DEFENSE_UP","value":10,"duration":2,"trigger":"BATTLE_START"},"lore":"预置阵纹，降低下一次机制伤害。"},
        {"code":"YF_SECRET_05","name":"前字秘","rarity":4,"kind":"PASSIVE","multiplier":.70,"fragment_cost":30,"effect":{"type":"THREAT_INSIGHT","trigger":"BATTLE_START"},"lore":"预见战局，显示Boss下一次真实机制。"},
        {"code":"YF_SECRET_06","name":"者字秘","rarity":5,"kind":"ACTIVE","multiplier":1.20,"fragment_cost":40,"effect":{"type":"DAMAGE_HEAL","heal_percent":5,"clear_dot":1},"lore":"疗伤秘术受限投影，清除持续伤害并小额恢复。"},
        {"code":"YF_SECRET_07","name":"皆字秘","rarity":5,"kind":"ACTIVE","multiplier":1.50,"fragment_cost":50,"effect":{"type":"DAMAGE","battle_intent":3,"damage_bonus":15},"lore":"以三层战意换取固定增幅，不采用随机十倍伤害。"},
        {"code":"YF_SECRET_08","name":"临字秘","rarity":0,"kind":"PASSIVE","multiplier":0,"fragment_cost":0,"enabled":False,"effect":{"type":"UNAVAILABLE"},"lore":"原著功能指向尚无统一考据，仅保留图鉴空位。"},
        {"code":"YF_SECRET_09","name":"数秘","rarity":0,"kind":"PASSIVE","multiplier":0,"fragment_cost":0,"enabled":False,"effect":{"type":"UNAVAILABLE"},"lore":"原著功能指向尚无统一考据，仅保留图鉴空位。"},
    ],
    "stages":[
        {"stage":1,"name":"圣体未启","growth_cost":0,"unlock_count":1,"effect":"记录圣体精血"},
        {"stage":2,"name":"轮海秘境","growth_cost":20,"unlock_count":1,"effect":"开放主动与金色苦海"},
        {"stage":3,"name":"道宫秘境","growth_cost":40,"unlock_count":2,"effect":"开放异象被动槽"},
        {"stage":4,"name":"四极秘境","growth_cost":60,"unlock_count":3,"effect":"开放九秘连携"},
        {"stage":5,"name":"化龙秘境","growth_cost":80,"unlock_count":5,"effect":"开放第二套预设"},
        {"stage":6,"name":"仙台秘境","growth_cost":100,"unlock_count":7,"effect":"连携双候选与母气鼎外观"},
    ],
    "combo":{"type":"九秘连携","command":"九秘连携","core_cost":3,"essence_cost":100,"max_saved":10},
    "fixed_combos":{
        "YF_SECRET_01+YF_SECRET_07+YF_SECRET_05":{"type":"FIXED_COMBO","name":"先见而战","preview":1,"battle_intent":1},
        "YF_SECRET_02+YF_SECRET_03+YF_SECRET_01":{"type":"FIXED_COMBO","name":"一击破器","dispel":1,"speed_up":10},
        "YF_SECRET_06+YF_SECRET_04+YF_SECRET_05":{"type":"FIXED_COMBO","name":"渡劫生阵","clear_dot":1,"heal_percent":3},
        "YF_SECRET_02+YF_SECRET_06+YF_SECRET_04":{"type":"FIXED_COMBO","name":"行阵自愈","shield_percent":6},
        "YF_SECRET_03+YF_SECRET_04+YF_SECRET_01":{"type":"FIXED_COMBO","name":"万物为兵","defense_ignore":8},
    },
    "rank":{"name":"圣体排行榜","primary":"五秘境与完美渡劫","secondary":"圣体异象与九秘连携"},
}
