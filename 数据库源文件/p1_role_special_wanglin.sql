-- 王林：意境与本源（依赖 p1_role_special_growth.sql）
INSERT INTO role_special_collection_config
(role_template_id,role_name,collection_code,name,rarity,fragment_code,fragment_cost,skill_type,skill_multiplier,effect_json,lore_desc) VALUES
(3,'王林','WL_CONCEPT_01','极境神识',4,'WL_CONCEPT_01_FRAG',10,'ACTIVE',0.500,'{"type":"DAMAGE","resilience_down":10}','极境神识破开桎梏。'),
(3,'王林','WL_CONCEPT_02','黄泉指',4,'WL_CONCEPT_02_FRAG',15,'ACTIVE',0.600,'{"type":"DAMAGE","target_hp_below":30,"damage_bonus":10}','一指黄泉，取生死轮转之意。'),
(3,'王林','WL_CONCEPT_03','寂灭指',4,'WL_CONCEPT_03_FRAG',20,'ACTIVE',0.700,'{"type":"DAMAGE","healing_down":20}','寂灭之力压制后续恢复。'),
(3,'王林','WL_CONCEPT_04','古神一击',4,'WL_CONCEPT_04_FRAG',25,'ACTIVE',0.800,'{"type":"DAMAGE","self_hp_above":70,"defense_ignore":8}','古神本尊凝聚肉身之力。'),
(3,'王林','WL_CONCEPT_05','生死意境',4,'WL_CONCEPT_05_FRAG',30,'PASSIVE',0.900,'{"type":"PLAYER_SHIELD","value":8,"trigger":"LOW_HP","threshold":30}','于死境中留下一线生机。'),
(3,'王林','WL_CONCEPT_06','因果意境',5,'WL_CONCEPT_06_FRAG',40,'PASSIVE',1.200,'{"type":"PLAYER_DEFENSE_UP","value":8,"duration":2,"trigger":"BATTLE_START"}','因果之线牵引战局。'),
(3,'王林','WL_CONCEPT_07','真假意境',5,'WL_CONCEPT_07_FRAG',50,'PASSIVE',1.500,'{"type":"CONTROL_RESIST","value":25,"trigger":"BATTLE_START"}','真假互易，抵抗外来控制。'),
(3,'王林','WL_CONCEPT_08','残夜',5,'WL_CONCEPT_08_FRAG',60,'ACTIVE',1.800,'{"type":"DAMAGE","boss_bonus":10}','天地至暗之后迎来破晓。'),
(3,'王林','WL_CONCEPT_09','轮回本源',5,'WL_CONCEPT_09_FRAG',70,'ACTIVE',2.000,'{"type":"DAMAGE_HEAL","heal_percent":5}','轮回本源收回部分生命差值。')
ON DUPLICATE KEY UPDATE name=VALUES(name),rarity=VALUES(rarity),fragment_cost=VALUES(fragment_cost),skill_type=VALUES(skill_type),skill_multiplier=VALUES(skill_multiplier),effect_json=VALUES(effect_json),lore_desc=VALUES(lore_desc),enabled=1;

INSERT INTO role_growth_stage_config
(role_template_id,role_name,growth_code,stage_no,stage_name,cost_json,unlock_condition_json,unlock_effect_json) VALUES
(3,'王林','WANG_LIN_ANCIENT_GOD',1,'古神一星','{"ROLE_3_GROWTH":0}','{"unlocked":1}','{"active_slot":1}'),
(3,'王林','WANG_LIN_ANCIENT_GOD',2,'古神二星','{"ROLE_3_GROWTH":5}','{"unlocked":2}','{"resilience_bonus":1}'),
(3,'王林','WANG_LIN_ANCIENT_GOD',3,'古神三星','{"ROLE_3_GROWTH":10}','{"unlocked":3}','{"passive_slot":1}'),
(3,'王林','WANG_LIN_ANCIENT_GOD',4,'古神四星','{"ROLE_3_GROWTH":15}','{"unlocked":4}','{"combo_discount":10}'),
(3,'王林','WANG_LIN_ANCIENT_GOD',5,'古神五星','{"ROLE_3_GROWTH":20}','{"unlocked":5}','{"ancient_god_stance":1}'),
(3,'王林','WANG_LIN_ANCIENT_GOD',6,'古神六星','{"ROLE_3_GROWTH":25}','{"unlocked":6}','{"presets":2}'),
(3,'王林','WANG_LIN_ANCIENT_GOD',7,'古神七星','{"ROLE_3_GROWTH":30}','{"unlocked":7}','{"combo_candidates":2}'),
(3,'王林','WANG_LIN_ANCIENT_GOD',8,'古神八星','{"ROLE_3_GROWTH":40}','{"unlocked":9}','{"average_protection":1,"passive_slots":2}')
ON DUPLICATE KEY UPDATE stage_name=VALUES(stage_name),cost_json=VALUES(cost_json),unlock_condition_json=VALUES(unlock_condition_json),unlock_effect_json=VALUES(unlock_effect_json),enabled=1;
