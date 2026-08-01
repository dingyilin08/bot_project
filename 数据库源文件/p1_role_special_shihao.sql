-- 石昊：十洞天与六道轮回（依赖 p1_role_special_growth.sql）
INSERT INTO role_special_collection_config
(role_template_id,role_name,collection_code,name,rarity,fragment_code,fragment_cost,skill_type,skill_multiplier,effect_json,lore_desc) VALUES
(5,'石昊','SH_ART_01','狻猊宝术',4,'SH_ART_01_FRAG',10,'ACTIVE',0.500,'{"type":"DAMAGE","resilience_down":8}','狻猊雷霆符文。'),
(5,'石昊','SH_ART_02','朱厌宝术',4,'SH_ART_02_FRAG',15,'PASSIVE',0.600,'{"type":"PLAYER_DEFENSE_UP","value":8,"duration":2,"trigger":"BATTLE_START"}','刚猛善战，以符文护体。'),
(5,'石昊','SH_ART_03','金翅大鹏宝术',4,'SH_ART_03_FRAG',20,'PASSIVE',0.700,'{"type":"PLAYER_SPEED_UP","value":10,"duration":2,"trigger":"BATTLE_START"}','大鹏极速横渡战场。'),
(5,'石昊','SH_ART_04','麒麟步投影',4,'SH_ART_04_FRAG',25,'ACTIVE',0.800,'{"type":"DAMAGE","speed_down":10}','麒麟步震荡虚空。'),
(5,'石昊','SH_ART_05','鲲鹏宝术',4,'SH_ART_05_FRAG',30,'ACTIVE',0.900,'{"type":"DAMAGE","shield_percent":6}','阴阳变化，攻守换形。'),
(5,'石昊','SH_ART_06','真凰宝术',5,'SH_ART_06_FRAG',40,'PASSIVE',1.200,'{"type":"PLAYER_HEAL","value":8,"trigger":"LOW_HP","threshold":20}','真凰涅槃恢复生机。'),
(5,'石昊','SH_ART_07','雷帝宝术',5,'SH_ART_07_FRAG',50,'ACTIVE',1.500,'{"type":"DAMAGE","boss_bonus":10}','雷帝执掌天罚。'),
(5,'石昊','SH_ART_08','草字剑诀',5,'SH_ART_08_FRAG',60,'ACTIVE',1.800,'{"type":"DAMAGE","defense_ignore":10}','一株草斩尽日月星辰。'),
(5,'石昊','SH_ART_09','他化自在大法投影',5,'SH_ART_09_FRAG',80,'ACTIVE',2.000,'{"type":"COPY_WEAK","copy_weak":1}','受限最终投影，不参与六道轮回。')
ON DUPLICATE KEY UPDATE name=VALUES(name),rarity=VALUES(rarity),fragment_cost=VALUES(fragment_cost),skill_type=VALUES(skill_type),skill_multiplier=VALUES(skill_multiplier),effect_json=VALUES(effect_json),lore_desc=VALUES(lore_desc),enabled=1;

INSERT INTO role_growth_stage_config
(role_template_id,role_name,growth_code,stage_no,stage_name,cost_json,unlock_condition_json,unlock_effect_json) VALUES
(5,'石昊','SHI_HAO_CAVES',1,'洞天未开','{"ROLE_5_GROWTH":0}','{"unlocked":1}','{"cave_count":0}'),
(5,'石昊','SHI_HAO_CAVES',2,'一洞天','{"ROLE_5_GROWTH":10}','{"unlocked":1}','{"cave_count":1,"active_slot":1}'),
(5,'石昊','SHI_HAO_CAVES',3,'二洞天','{"ROLE_5_GROWTH":10}','{"unlocked":1}','{"cave_count":2}'),
(5,'石昊','SHI_HAO_CAVES',4,'三洞天','{"ROLE_5_GROWTH":10}','{"unlocked":2}','{"cave_count":3,"passive_slot":1}'),
(5,'石昊','SHI_HAO_CAVES',5,'四洞天','{"ROLE_5_GROWTH":10}','{"unlocked":2}','{"cave_count":4}'),
(5,'石昊','SHI_HAO_CAVES',6,'五洞天','{"ROLE_5_GROWTH":10}','{"unlocked":3}','{"cave_count":5,"stances":2}'),
(5,'石昊','SHI_HAO_CAVES',7,'六洞天','{"ROLE_5_GROWTH":10}','{"unlocked":3}','{"cave_count":6}'),
(5,'石昊','SHI_HAO_CAVES',8,'七洞天','{"ROLE_5_GROWTH":10}','{"unlocked":4}','{"cave_count":7,"presets":2}'),
(5,'石昊','SHI_HAO_CAVES',9,'八洞天','{"ROLE_5_GROWTH":10}','{"unlocked":4}','{"cave_count":8}'),
(5,'石昊','SHI_HAO_CAVES',10,'九洞天','{"ROLE_5_GROWTH":10}','{"unlocked":5}','{"cave_count":9,"average_protection":1}'),
(5,'石昊','SHI_HAO_CAVES',11,'十洞天','{"ROLE_5_GROWTH":10}','{"unlocked":6}','{"cave_count":10,"unity_trial":1}'),
(5,'石昊','SHI_HAO_CAVES',12,'唯一洞天','{"ROLE_5_CORE":10}','{"unlocked":9}','{"unique_cave":1,"combo":1,"passive_slots":2}')
ON DUPLICATE KEY UPDATE stage_name=VALUES(stage_name),cost_json=VALUES(cost_json),unlock_condition_json=VALUES(unlock_condition_json),unlock_effect_json=VALUES(unlock_effect_json),enabled=1;
