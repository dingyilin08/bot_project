# -*- coding: utf-8 -*-
"""王林：古神本尊承载意境感悟，最终合道为本源神通。"""


ROLE_SPEC = {
    "template_id": 3, "role_name": "王林", "growth_name": "古神星点",
    "drop_name": "意境残念", "essence_name": "天逆灵气", "core_name": "本源道晶",
    "growth_material": "古神之血",
    "passive_lore": "逆修极念：首次将Boss韧性压至半数以下时，标记一项可破局机制，只提供信息。",
    "abilities": [
        {"code":"WL_CONCEPT_01","name":"极境神识","rarity":4,"kind":"ACTIVE","multiplier":.50,"fragment_cost":10,"effect":{"type":"DAMAGE","resilience_down":10},"lore":"极境神识凌厉决绝，以神识之威破开桎梏。"},
        {"code":"WL_CONCEPT_02","name":"黄泉指","rarity":4,"kind":"ACTIVE","multiplier":.60,"fragment_cost":15,"effect":{"type":"DAMAGE","target_hp_below":30,"damage_bonus":10},"lore":"一指黄泉，取生死轮转之意。"},
        {"code":"WL_CONCEPT_03","name":"寂灭指","rarity":4,"kind":"ACTIVE","multiplier":.70,"fragment_cost":20,"effect":{"type":"DAMAGE","healing_down":20},"lore":"寂灭之力断绝生机，压制目标后续恢复。"},
        {"code":"WL_CONCEPT_04","name":"古神一击","rarity":4,"kind":"ACTIVE","multiplier":.80,"fragment_cost":25,"effect":{"type":"DAMAGE","self_hp_above":70,"defense_ignore":8},"lore":"古神本尊凝聚肉身之力的正面一击。"},
        {"code":"WL_CONCEPT_05","name":"生死意境","rarity":4,"kind":"PASSIVE","multiplier":.90,"fragment_cost":30,"effect":{"type":"PLAYER_SHIELD","value":8,"trigger":"LOW_HP","threshold":30},"lore":"看遍生死轮回，于死境中留下一线生机。"},
        {"code":"WL_CONCEPT_06","name":"因果意境","rarity":5,"kind":"PASSIVE","multiplier":1.20,"fragment_cost":40,"effect":{"type":"PLAYER_DEFENSE_UP","value":8,"duration":2,"trigger":"BATTLE_START"},"lore":"因果之线牵引战局，延展首次减益。"},
        {"code":"WL_CONCEPT_07","name":"真假意境","rarity":5,"kind":"PASSIVE","multiplier":1.50,"fragment_cost":50,"effect":{"type":"CONTROL_RESIST","value":25,"trigger":"BATTLE_START"},"lore":"真假互易，动摇外来控制的根基。"},
        {"code":"WL_CONCEPT_08","name":"残夜","rarity":5,"kind":"ACTIVE","multiplier":1.80,"fragment_cost":60,"effect":{"type":"DAMAGE","boss_bonus":10},"lore":"天地至暗之后迎来破晓，杀伐之意贯穿长夜。"},
        {"code":"WL_CONCEPT_09","name":"轮回本源","rarity":5,"kind":"ACTIVE","multiplier":2.00,"fragment_cost":70,"effect":{"type":"DAMAGE_HEAL","heal_percent":5},"lore":"轮回本源记录状态，于下一息收回部分生命差值。"},
    ],
    "stages": [
        {"stage":1,"name":"古神一星","growth_cost":0,"unlock_count":1,"effect":"开放意境主动"},
        {"stage":2,"name":"古神二星","growth_cost":5,"unlock_count":2,"effect":"极境额外削韧"},
        {"stage":3,"name":"古神三星","growth_cost":10,"unlock_count":3,"effect":"开放意境被动槽"},
        {"stage":4,"name":"古神四星","growth_cost":15,"unlock_count":4,"effect":"合道消耗降低10%"},
        {"stage":5,"name":"古神五星","growth_cost":20,"unlock_count":5,"effect":"古神一击攻守换形"},
        {"stage":6,"name":"古神六星","growth_cost":25,"unlock_count":6,"effect":"开放第二套预设"},
        {"stage":7,"name":"古神七星","growth_cost":30,"unlock_count":7,"effect":"本源合道双候选"},
        {"stage":8,"name":"古神八星","growth_cost":40,"unlock_count":9,"effect":"本源组合均值保护"},
    ],
    "combo":{"type":"本源合道","command":"本源合道","core_cost":3,"essence_cost":100,"max_saved":8},
    "rank":{"name":"问道排行榜","primary":"点亮意境与古神星点","secondary":"本源神通完整度"},
}
