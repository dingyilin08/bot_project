-- 韩立：青竹蜂云剑阵（依赖 p1_role_special_growth.sql）
INSERT INTO role_special_collection_config
(role_template_id,role_name,collection_code,name,rarity,fragment_code,fragment_cost,skill_type,skill_multiplier,effect_json,lore_desc) VALUES
(4,'韩立','HL_TREASURE_01','青元剑芒',4,'HL_TREASURE_01_FRAG',10,'ACTIVE',0.500,'{"type":"DAMAGE","sword_intent":1}','青元剑诀所化剑芒。'),
(4,'韩立','HL_TREASURE_02','大衍神念',4,'HL_TREASURE_02_FRAG',15,'PASSIVE',0.600,'{"type":"CONTROL_RESIST","value":15,"trigger":"BATTLE_START"}','大衍诀壮大神识。'),
(4,'韩立','HL_TREASURE_03','噬金虫群',4,'HL_TREASURE_03_FRAG',20,'ACTIVE',0.700,'{"type":"DAMAGE","shield_bonus":10}','无物不噬，克制器物护盾。'),
(4,'韩立','HL_TREASURE_04','风雷翅',4,'HL_TREASURE_04_FRAG',25,'PASSIVE',0.800,'{"type":"PLAYER_SPEED_UP","value":10,"duration":2,"trigger":"BATTLE_START"}','风雷齐动，争得斗法先机。'),
(4,'韩立','HL_TREASURE_05','辟邪神雷',4,'HL_TREASURE_05_FRAG',30,'ACTIVE',0.900,'{"type":"DAMAGE","resilience_down":8}','金雷竹蕴生神雷。'),
(4,'韩立','HL_TREASURE_06','大庚剑阵',5,'HL_TREASURE_06_FRAG',40,'ACTIVE',1.200,'{"type":"DAMAGE","defense_ignore":10}','三十六口以上飞剑布成杀阵。'),
(4,'韩立','HL_TREASURE_07','元磁神光',5,'HL_TREASURE_07_FRAG',50,'ACTIVE',1.500,'{"type":"DAMAGE_DISPEL","dispel":1}','五行元磁之力压制器物。'),
(4,'韩立','HL_TREASURE_08','梵圣真魔功',5,'HL_TREASURE_08_FRAG',60,'ACTIVE',1.800,'{"type":"DAMAGE","shield_percent":8}','梵圣法相护体，攻守一体。'),
(4,'韩立','HL_TREASURE_09','玄天斩灵剑投影',5,'HL_TREASURE_09_FRAG',70,'ACTIVE',2.000,'{"type":"DAMAGE","defense_ignore":15}','玄天之宝的受限投影。')
ON DUPLICATE KEY UPDATE name=VALUES(name),rarity=VALUES(rarity),fragment_cost=VALUES(fragment_cost),skill_type=VALUES(skill_type),skill_multiplier=VALUES(skill_multiplier),effect_json=VALUES(effect_json),lore_desc=VALUES(lore_desc),enabled=1;

INSERT INTO role_growth_stage_config
(role_template_id,role_name,growth_code,stage_no,stage_name,cost_json,unlock_condition_json,unlock_effect_json) VALUES
(4,'韩立','HAN_LI_SWORDS',1,'剑胚初炼','{"ROLE_4_GROWTH":0}','{"unlocked":1}','{"sword_count":0}'),
(4,'韩立','HAN_LI_SWORDS',2,'十二口飞剑','{"ROLE_4_GROWTH":12}','{"unlocked":1}','{"sword_count":12,"active_slot":1}'),
(4,'韩立','HAN_LI_SWORDS',3,'二十四口飞剑','{"ROLE_4_GROWTH":12}','{"unlocked":2}','{"sword_count":24,"second_target":30}'),
(4,'韩立','HAN_LI_SWORDS',4,'三十六口飞剑','{"ROLE_4_GROWTH":12}','{"unlocked":3}','{"sword_count":36,"combo":1}'),
(4,'韩立','HAN_LI_SWORDS',5,'四十八口飞剑','{"ROLE_4_GROWTH":12}','{"unlocked":4}','{"sword_count":48,"resilience_stance":1}'),
(4,'韩立','HAN_LI_SWORDS',6,'六十口飞剑','{"ROLE_4_GROWTH":12}','{"unlocked":5}','{"sword_count":60,"divine_thunder":1}'),
(4,'韩立','HAN_LI_SWORDS',7,'七十二口飞剑','{"ROLE_4_GROWTH":12}','{"unlocked":7}','{"sword_count":72,"combo_candidates":2,"passive_slots":2}')
ON DUPLICATE KEY UPDATE stage_name=VALUES(stage_name),cost_json=VALUES(cost_json),unlock_condition_json=VALUES(unlock_condition_json),unlock_effect_json=VALUES(unlock_effect_json),enabled=1;
