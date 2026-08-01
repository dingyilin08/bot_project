-- 叶凡：圣体五秘境与九秘（依赖 p1_role_special_growth.sql）
INSERT INTO role_special_collection_config
(role_template_id,role_name,collection_code,name,rarity,fragment_code,fragment_cost,skill_type,skill_multiplier,effect_json,lore_desc,enabled) VALUES
(6,'叶凡','YF_SECRET_01','斗字秘',4,'YF_SECRET_01_FRAG',10,'ACTIVE',0.500,'{"type":"DAMAGE","resilience_down":8}','演化攻伐圣法。',1),
(6,'叶凡','YF_SECRET_02','行字秘',4,'YF_SECRET_02_FRAG',15,'PASSIVE',0.500,'{"type":"PLAYER_SPEED_UP","value":10,"duration":2,"trigger":"BATTLE_START"}','世间极速。',1),
(6,'叶凡','YF_SECRET_03','兵字秘',4,'YF_SECRET_03_FRAG',20,'ACTIVE',0.600,'{"type":"DAMAGE_DISPEL","dispel":1}','驾驭兵器。',1),
(6,'叶凡','YF_SECRET_04','组字秘',4,'YF_SECRET_04_FRAG',25,'PASSIVE',0.500,'{"type":"PLAYER_DEFENSE_UP","value":10,"duration":2,"trigger":"BATTLE_START"}','预置阵纹。',1),
(6,'叶凡','YF_SECRET_05','前字秘',4,'YF_SECRET_05_FRAG',30,'PASSIVE',0.700,'{"type":"THREAT_INSIGHT","trigger":"BATTLE_START"}','预见下一次真实机制。',1),
(6,'叶凡','YF_SECRET_06','者字秘',5,'YF_SECRET_06_FRAG',40,'ACTIVE',1.200,'{"type":"DAMAGE_HEAL","heal_percent":5,"clear_dot":1}','清除持续伤害并小额恢复。',1),
(6,'叶凡','YF_SECRET_07','皆字秘',5,'YF_SECRET_07_FRAG',50,'ACTIVE',1.500,'{"type":"DAMAGE","battle_intent":3,"damage_bonus":15}','三层战意换取固定增幅。',1),
(6,'叶凡','YF_SECRET_08','临字秘',0,'YF_SECRET_08_LOCKED',0,'PASSIVE',0.000,'{"type":"UNAVAILABLE"}','待考据，只保留图鉴空位。',0),
(6,'叶凡','YF_SECRET_09','数秘',0,'YF_SECRET_09_LOCKED',0,'PASSIVE',0.000,'{"type":"UNAVAILABLE"}','待考据，只保留图鉴空位。',0)
ON DUPLICATE KEY UPDATE name=VALUES(name),rarity=VALUES(rarity),fragment_cost=VALUES(fragment_cost),skill_type=VALUES(skill_type),skill_multiplier=VALUES(skill_multiplier),effect_json=VALUES(effect_json),lore_desc=VALUES(lore_desc),enabled=VALUES(enabled);

INSERT INTO role_growth_stage_config
(role_template_id,role_name,growth_code,stage_no,stage_name,cost_json,unlock_condition_json,unlock_effect_json) VALUES
(6,'叶凡','YE_FAN_REALMS',1,'圣体未启','{"ROLE_6_GROWTH":0}','{"unlocked":1}','{"sacred_body":0}'),
(6,'叶凡','YE_FAN_REALMS',2,'轮海秘境','{"ROLE_6_GROWTH":20,"ROLE_6_TRIBULATION":1}','{"unlocked":1}','{"active_slot":1,"phenomenon":"金色苦海"}'),
(6,'叶凡','YE_FAN_REALMS',3,'道宫秘境','{"ROLE_6_GROWTH":40,"ROLE_6_TRIBULATION":2}','{"unlocked":2}','{"passive_slot":1}'),
(6,'叶凡','YE_FAN_REALMS',4,'四极秘境','{"ROLE_6_GROWTH":60,"ROLE_6_TRIBULATION":3}','{"unlocked":3}','{"combo":1,"stances":2}'),
(6,'叶凡','YE_FAN_REALMS',5,'化龙秘境','{"ROLE_6_GROWTH":80,"ROLE_6_TRIBULATION":4}','{"unlocked":5}','{"presets":2}'),
(6,'叶凡','YE_FAN_REALMS',6,'仙台秘境','{"ROLE_6_GROWTH":100,"ROLE_6_TRIBULATION":5}','{"unlocked":7}','{"combo_candidates":2,"mother_qi_appearance":1,"passive_slots":2}')
ON DUPLICATE KEY UPDATE stage_name=VALUES(stage_name),cost_json=VALUES(cost_json),unlock_condition_json=VALUES(unlock_condition_json),unlock_effect_json=VALUES(unlock_effect_json),enabled=1;
