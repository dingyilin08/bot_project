# -*- coding: utf-8 -*-
"""孟川：元神八层与真实战斗绘卷驱动的刀势推演。"""


ROLE_SPEC = {
    "template_id":7,"role_name":"孟川","growth_name":"元神八层",
    "drop_name":"刀意残痕","essence_name":"雷霆砂","core_name":"魔锥核心","growth_material":"元神星芒",
    "growth_on_drop":True,"combo_min_stage":4,"requires_scroll":True,
    "essence_material_code":"ROLE_7_THUNDER","world_material_code":"ROLE_7_INK",
    "extra_materials":{"ROLE_7_INK":"绘卷墨","ROLE_7_THUNDER":"雷霆砂"},
    "drop_extra_materials":{"ROLE_7_INK":1},"boss_extra_materials":{"ROLE_7_THUNDER":3},
    "passive_lore":"元神观敌：每场PVE首次行动前显示最高威胁与判断原因，不自动选择目标。",
    "featured_system":"战斗绘卷只读取孟川亲自完成的PVE battle_id、关键回合、技能和破局事件，不能手填伤害。",
    "abilities":[
        {"code":"MC_BLADE_01","name":"拔刀式","rarity":4,"kind":"ACTIVE","multiplier":.50,"fragment_cost":10,"effect":{"type":"DAMAGE","first_round_bonus":10},"lore":"快刀在出鞘一瞬决胜，首回合威力更盛。"},
        {"code":"MC_BLADE_02","name":"心刀式","rarity":4,"kind":"ACTIVE","multiplier":.60,"fragment_cost":15,"effect":{"type":"DAMAGE","resilience_down":10},"lore":"心刀锁定威胁最高的目标并削其韧性。"},
        {"code":"MC_BLADE_03","name":"天地游龙刀","rarity":4,"kind":"PASSIVE","multiplier":.70,"fragment_cost":20,"effect":{"type":"PLAYER_SPEED_UP","value":10,"duration":2,"trigger":"BATTLE_START"},"lore":"身法如游龙，抗住控制后抢回先手。"},
        {"code":"MC_BLADE_04","name":"雷霆灭世魔体","rarity":4,"kind":"ACTIVE","multiplier":.80,"fragment_cost":25,"effect":{"type":"DAMAGE","resilience_down":8},"lore":"雷霆淬炼肉身，为刀法附加雷霆标签。"},
        {"code":"MC_BLADE_05","name":"意之刀","rarity":4,"kind":"ACTIVE","multiplier":.90,"fragment_cost":30,"effect":{"type":"DAMAGE","boss_bonus":10},"lore":"洞察破局后以刀意乘势而进。"},
        {"code":"MC_BLADE_06","name":"魔锥秘术","rarity":5,"kind":"ACTIVE","multiplier":1.20,"fragment_cost":40,"effect":{"type":"DAMAGE","resilience_down":12},"lore":"元神魔锥攻伐；Boss免疫控制时转为削韧。"},
        {"code":"MC_BLADE_07","name":"元神星辰","rarity":5,"kind":"PASSIVE","multiplier":1.50,"fragment_cost":50,"effect":{"type":"PLAYER_DEFENSE_UP","value":10,"duration":2,"trigger":"BATTLE_START"},"lore":"元神星辰镇守识海，降低首次元神威胁。"},
        {"code":"MC_BLADE_08","name":"无尽刀","rarity":5,"kind":"ACTIVE","multiplier":1.80,"fragment_cost":60,"effect":{"type":"DAMAGE","round_at_least":5,"damage_bonus":10},"lore":"久战不衰，第五回合后刀势更为绵长。"},
        {"code":"MC_BLADE_09","name":"时空刀印","rarity":5,"kind":"ACTIVE","multiplier":2.00,"fragment_cost":70,"effect":{"type":"DAMAGE","copy_weak":1},"lore":"记录一次行动，在下一回合复制其弱化效果。"},
    ],
    "stages":[
        {"stage":1,"name":"元神一层","growth_cost":0,"unlock_count":1,"effect":"开放刀法主动"},
        {"stage":2,"name":"元神二层","growth_cost":5,"unlock_count":2,"effect":"威胁提示显示速度倾向"},
        {"stage":3,"name":"元神三层","growth_cost":8,"unlock_count":3,"effect":"开放刀法被动槽"},
        {"stage":4,"name":"元神四层","growth_cost":12,"unlock_count":3,"effect":"开放魔锥削韧与绘卷推演"},
        {"stage":5,"name":"元神五层","growth_cost":16,"unlock_count":4,"effect":"绘卷记录关键破局回合"},
        {"stage":6,"name":"元神六层","growth_cost":20,"unlock_count":5,"effect":"开放第二套预设"},
        {"stage":7,"name":"元神七层","growth_cost":25,"unlock_count":7,"effect":"推演生成双候选"},
        {"stage":8,"name":"元神八层","growth_cost":30,"unlock_count":9,"effect":"元神星辰外观与均值保护"},
    ],
    "combo":{"type":"刀势推演","command":"刀势推演","core_cost":3,"essence_cost":20,"max_saved":10},
    "rank":{"name":"刀道排行榜","primary":"元神层次与传神绘卷","secondary":"Boss破局和刀势数量"},
}
