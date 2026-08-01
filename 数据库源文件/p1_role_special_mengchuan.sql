-- 孟川：元神、刀法与真实战斗绘卷（依赖 p1_role_special_growth.sql）
CREATE TABLE IF NOT EXISTS user_role_special_scroll (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  role_id INT NOT NULL,
  battle_id VARCHAR(64) NOT NULL,
  quality VARCHAR(12) NOT NULL,
  detail_json JSON NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'READY',
  used_combo_id BIGINT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_role_scroll_battle (uid,role_id,battle_id),
  KEY idx_role_scroll_ready (uid,role_id,status,quality)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO role_special_collection_config
(role_template_id,role_name,collection_code,name,rarity,fragment_code,fragment_cost,skill_type,skill_multiplier,effect_json,lore_desc) VALUES
(7,'孟川','MC_BLADE_01','拔刀式',4,'MC_BLADE_01_FRAG',10,'ACTIVE',0.500,'{"type":"DAMAGE","first_round_bonus":10}','快刀出鞘一瞬决胜。'),
(7,'孟川','MC_BLADE_02','心刀式',4,'MC_BLADE_02_FRAG',15,'ACTIVE',0.600,'{"type":"DAMAGE","resilience_down":10}','心刀锁定最高威胁。'),
(7,'孟川','MC_BLADE_03','天地游龙刀',4,'MC_BLADE_03_FRAG',20,'PASSIVE',0.700,'{"type":"PLAYER_SPEED_UP","value":10,"duration":2,"trigger":"BATTLE_START"}','身法如游龙。'),
(7,'孟川','MC_BLADE_04','雷霆灭世魔体',4,'MC_BLADE_04_FRAG',25,'ACTIVE',0.800,'{"type":"DAMAGE","resilience_down":8}','雷霆淬炼肉身。'),
(7,'孟川','MC_BLADE_05','意之刀',4,'MC_BLADE_05_FRAG',30,'ACTIVE',0.900,'{"type":"DAMAGE","boss_bonus":10}','洞察破局后以刀意乘势。'),
(7,'孟川','MC_BLADE_06','魔锥秘术',5,'MC_BLADE_06_FRAG',40,'ACTIVE',1.200,'{"type":"DAMAGE","resilience_down":12}','元神魔锥攻伐。'),
(7,'孟川','MC_BLADE_07','元神星辰',5,'MC_BLADE_07_FRAG',50,'PASSIVE',1.500,'{"type":"PLAYER_DEFENSE_UP","value":10,"duration":2,"trigger":"BATTLE_START"}','元神星辰镇守识海。'),
(7,'孟川','MC_BLADE_08','无尽刀',5,'MC_BLADE_08_FRAG',60,'ACTIVE',1.800,'{"type":"DAMAGE","round_at_least":5,"damage_bonus":10}','第五回合后刀势绵长。'),
(7,'孟川','MC_BLADE_09','时空刀印',5,'MC_BLADE_09_FRAG',70,'ACTIVE',2.000,'{"type":"DAMAGE","copy_weak":1}','记录一次行动并复制弱化效果。')
ON DUPLICATE KEY UPDATE name=VALUES(name),rarity=VALUES(rarity),fragment_cost=VALUES(fragment_cost),skill_type=VALUES(skill_type),skill_multiplier=VALUES(skill_multiplier),effect_json=VALUES(effect_json),lore_desc=VALUES(lore_desc),enabled=1;

INSERT INTO role_growth_stage_config
(role_template_id,role_name,growth_code,stage_no,stage_name,cost_json,unlock_condition_json,unlock_effect_json) VALUES
(7,'孟川','MENG_CHUAN_SPIRIT',1,'元神一层','{"ROLE_7_GROWTH":0}','{"unlocked":1}','{"active_slot":1}'),
(7,'孟川','MENG_CHUAN_SPIRIT',2,'元神二层','{"ROLE_7_GROWTH":5}','{"unlocked":2}','{"threat_speed":1}'),
(7,'孟川','MENG_CHUAN_SPIRIT',3,'元神三层','{"ROLE_7_GROWTH":8}','{"unlocked":3}','{"passive_slot":1}'),
(7,'孟川','MENG_CHUAN_SPIRIT',4,'元神四层','{"ROLE_7_GROWTH":12}','{"unlocked":3}','{"magic_cone":1,"combo":1}'),
(7,'孟川','MENG_CHUAN_SPIRIT',5,'元神五层','{"ROLE_7_GROWTH":16}','{"unlocked":4}','{"scroll_break_round":1}'),
(7,'孟川','MENG_CHUAN_SPIRIT',6,'元神六层','{"ROLE_7_GROWTH":20}','{"unlocked":5}','{"presets":2}'),
(7,'孟川','MENG_CHUAN_SPIRIT',7,'元神七层','{"ROLE_7_GROWTH":25}','{"unlocked":7}','{"combo_candidates":2}'),
(7,'孟川','MENG_CHUAN_SPIRIT',8,'元神八层','{"ROLE_7_GROWTH":30}','{"unlocked":9}','{"average_protection":1,"spirit_appearance":1,"passive_slots":2}')
ON DUPLICATE KEY UPDATE stage_name=VALUES(stage_name),cost_json=VALUES(cost_json),unlock_condition_json=VALUES(unlock_condition_json),unlock_effect_json=VALUES(unlock_effect_json),enabled=1;
