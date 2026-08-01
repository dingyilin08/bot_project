# -*- coding: utf-8 -*-
"""石昊：十洞天逐口开辟并合一，以六道轮回天功统御宝术。"""


ROLE_SPEC = {
    "template_id":5,"role_name":"石昊","growth_name":"洞天极境",
    "drop_name":"宝术残文","essence_name":"原始符文","core_name":"轮回道盘","growth_material":"洞天灵魄",
    "growth_on_drop":True,"combo_min_stage":12,"non_combinable_codes":["SH_ART_09"],
    "passive_lore":"极境破限：首次完成副本隐藏破局时额外获得洞天灵魄，不复制稀有掉落。",
    "abilities":[
        {"code":"SH_ART_01","name":"狻猊宝术","rarity":4,"kind":"ACTIVE","multiplier":.50,"fragment_cost":10,"effect":{"type":"DAMAGE","resilience_down":8},"lore":"狻猊雷霆符文淬炼肉身并轰击强敌。"},
        {"code":"SH_ART_02","name":"朱厌宝术","rarity":4,"kind":"PASSIVE","multiplier":.60,"fragment_cost":15,"effect":{"type":"PLAYER_DEFENSE_UP","value":8,"duration":2,"trigger":"BATTLE_START"},"lore":"朱厌宝术刚猛善战，以符文护住要害。"},
        {"code":"SH_ART_03","name":"金翅大鹏宝术","rarity":4,"kind":"PASSIVE","multiplier":.70,"fragment_cost":20,"effect":{"type":"PLAYER_SPEED_UP","value":10,"duration":2,"trigger":"BATTLE_START"},"lore":"大鹏极速横渡战场，夺取先手。"},
        {"code":"SH_ART_04","name":"麒麟步投影","rarity":4,"kind":"ACTIVE","multiplier":.80,"fragment_cost":25,"effect":{"type":"DAMAGE","speed_down":10},"lore":"麒麟步震荡虚空，压低敌方下一回合速度。"},
        {"code":"SH_ART_05","name":"鲲鹏宝术","rarity":4,"kind":"ACTIVE","multiplier":.90,"fragment_cost":30,"effect":{"type":"DAMAGE","shield_percent":6},"lore":"阴阳变化，可在攻伐与守御之间换形。"},
        {"code":"SH_ART_06","name":"真凰宝术","rarity":5,"kind":"PASSIVE","multiplier":1.20,"fragment_cost":40,"effect":{"type":"PLAYER_HEAL","value":8,"trigger":"LOW_HP","threshold":20},"lore":"真凰涅槃之意，在濒危时恢复生机。"},
        {"code":"SH_ART_07","name":"雷帝宝术","rarity":5,"kind":"ACTIVE","multiplier":1.50,"fragment_cost":50,"effect":{"type":"DAMAGE","boss_bonus":10},"lore":"雷帝执掌天罚，雷霆贯穿强敌。"},
        {"code":"SH_ART_08","name":"草字剑诀","rarity":5,"kind":"ACTIVE","multiplier":1.80,"fragment_cost":60,"effect":{"type":"DAMAGE","defense_ignore":10},"lore":"一株草亦可斩尽日月星辰。"},
        {"code":"SH_ART_09","name":"他化自在大法投影","rarity":5,"kind":"ACTIVE","multiplier":2.00,"fragment_cost":80,"effect":{"type":"COPY_WEAK","copy_weak":1},"lore":"受限最终投影，不作为普通宝术参与六道轮回。"},
    ],
    "stages":[{"stage":1,"name":"洞天未开","growth_cost":0,"unlock_count":1,"effect":"记录洞天灵魄"}]
        + [{"stage":i+1,"name":f"{('一二三四五六七八九十'[i-1])}洞天","growth_cost":10,"unlock_count":min(9,max(1,(i+1)//2)),"effect":"开辟洞天并解锁极境机制"} for i in range(1,11)]
        + [{"stage":12,"name":"唯一洞天","growth_cost":10,"unlock_count":9,"effect":"十洞天合一，开放六道轮回"}],
    "combo":{"type":"六道轮回","command":"六道轮回","core_cost":3,"essence_cost":100,"max_saved":10},
    "rank":{"name":"极境排行榜","primary":"洞天与唯一洞天进度","secondary":"宝术和轮回组合数"},
}
