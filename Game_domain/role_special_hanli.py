# -*- coding: utf-8 -*-
"""韩立：以青竹蜂云剑数量推进大庚剑阵，并编排法宝斗法先后手。"""


ROLE_SPEC = {
    "template_id":4,"role_name":"韩立","growth_name":"青竹蜂云剑",
    "drop_name":"法宝残片","essence_name":"大衍精华","core_name":"剑阵核心","growth_material":"青竹剑胚",
    "growth_on_drop":True,"combo_min_stage":4,
    "passive_lore":"藏锋后手：专属主动施放前隐藏具体类型；每日首次精英破局额外锻成一口剑胚。",
    "abilities":[
        {"code":"HL_TREASURE_01","name":"青元剑芒","rarity":4,"kind":"ACTIVE","multiplier":.50,"fragment_cost":10,"effect":{"type":"DAMAGE","sword_intent":1},"lore":"青元剑诀所化剑芒，是本命飞剑的根基。"},
        {"code":"HL_TREASURE_02","name":"大衍神念","rarity":4,"kind":"PASSIVE","multiplier":.60,"fragment_cost":15,"effect":{"type":"CONTROL_RESIST","value":15,"trigger":"BATTLE_START"},"lore":"大衍诀壮大神识，为傀儡与群剑御使之本。"},
        {"code":"HL_TREASURE_03","name":"噬金虫群","rarity":4,"kind":"ACTIVE","multiplier":.70,"fragment_cost":20,"effect":{"type":"DAMAGE","shield_bonus":10},"lore":"成熟噬金虫无物不噬，尤其克制器物护盾。"},
        {"code":"HL_TREASURE_04","name":"风雷翅","rarity":4,"kind":"PASSIVE","multiplier":.80,"fragment_cost":25,"effect":{"type":"PLAYER_SPEED_UP","value":10,"duration":2,"trigger":"BATTLE_START"},"lore":"风雷齐动，争得斗法先机。"},
        {"code":"HL_TREASURE_05","name":"辟邪神雷","rarity":4,"kind":"ACTIVE","multiplier":.90,"fragment_cost":30,"effect":{"type":"DAMAGE","resilience_down":8},"lore":"金雷竹蕴生神雷，克制魔气与阴魂。"},
        {"code":"HL_TREASURE_06","name":"大庚剑阵","rarity":5,"kind":"ACTIVE","multiplier":1.20,"fragment_cost":40,"effect":{"type":"DAMAGE","defense_ignore":10},"lore":"三十六口以上青竹蜂云剑布成杀阵。"},
        {"code":"HL_TREASURE_07","name":"元磁神光","rarity":5,"kind":"ACTIVE","multiplier":1.50,"fragment_cost":50,"effect":{"type":"DAMAGE_DISPEL","dispel":1},"lore":"五行元磁之力压制并牵引器物。"},
        {"code":"HL_TREASURE_08","name":"梵圣真魔功","rarity":5,"kind":"ACTIVE","multiplier":1.80,"fragment_cost":60,"effect":{"type":"DAMAGE","shield_percent":8},"lore":"梵圣法相护体，攻守一体。"},
        {"code":"HL_TREASURE_09","name":"玄天斩灵剑投影","rarity":5,"kind":"ACTIVE","multiplier":2.00,"fragment_cost":70,"effect":{"type":"DAMAGE","defense_ignore":15},"lore":"玄天之宝的受限投影，只表现锋芒而不追加控制。"},
    ],
    "stages":[
        {"stage":1,"name":"剑胚初炼","growth_cost":0,"unlock_count":1,"effect":"记录青竹剑胚"},
        {"stage":2,"name":"十二口飞剑","growth_cost":12,"unlock_count":1,"effect":"开放青竹剑芒"},
        {"stage":3,"name":"二十四口飞剑","growth_cost":12,"unlock_count":2,"effect":"剑光分化"},
        {"stage":4,"name":"三十六口飞剑","growth_cost":12,"unlock_count":3,"effect":"开放大庚剑阵与法宝协同"},
        {"stage":5,"name":"四十八口飞剑","growth_cost":12,"unlock_count":4,"effect":"破甲可换削韧"},
        {"stage":6,"name":"六十口飞剑","growth_cost":12,"unlock_count":5,"effect":"辟邪神雷入阵"},
        {"stage":7,"name":"七十二口飞剑","growth_cost":12,"unlock_count":7,"effect":"完整剑阵与协同双候选"},
    ],
    "combo":{"type":"法宝协同","command":"法宝协同","core_cost":3,"essence_cost":100,"max_saved":10},
    "rank":{"name":"剑阵排行榜","primary":"飞剑完成度","secondary":"法宝协同机制覆盖"},
}
