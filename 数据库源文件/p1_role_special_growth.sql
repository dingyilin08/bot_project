-- P1 角色专属战斗养成共享结构（MySQL 5.7）
-- 仅创建新表，不修改现有玩家表；角色配置使用幂等 upsert。

CREATE TABLE IF NOT EXISTS role_special_collection_config (
  id INT NOT NULL AUTO_INCREMENT,
  role_template_id INT NOT NULL,
  role_name VARCHAR(12) NOT NULL,
  collection_code VARCHAR(32) NOT NULL,
  name VARCHAR(30) NOT NULL,
  rarity TINYINT NOT NULL,
  fragment_code VARCHAR(40) NOT NULL,
  fragment_cost INT NOT NULL,
  skill_type VARCHAR(12) NOT NULL,
  skill_multiplier DECIMAL(6,3) NOT NULL DEFAULT 0,
  effect_json JSON NOT NULL,
  lore_desc VARCHAR(255) NOT NULL DEFAULT '',
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_role_special_code (role_template_id, collection_code),
  KEY idx_role_special_pool (role_template_id, rarity, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS role_growth_stage_config (
  id INT NOT NULL AUTO_INCREMENT,
  role_template_id INT NOT NULL,
  role_name VARCHAR(12) NOT NULL,
  growth_code VARCHAR(32) NOT NULL,
  stage_no TINYINT NOT NULL,
  stage_name VARCHAR(30) NOT NULL,
  cost_json JSON NOT NULL,
  unlock_condition_json JSON NOT NULL,
  unlock_effect_json JSON NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uk_role_growth_stage (role_template_id, growth_code, stage_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_role_special_progress (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  role_id INT NOT NULL COMMENT 'user_role.id',
  role_template_id INT NOT NULL COMMENT 'data_role.id',
  role_name VARCHAR(12) NOT NULL,
  growth_code VARCHAR(32) NOT NULL,
  growth_stage TINYINT NOT NULL DEFAULT 1,
  growth_value INT NOT NULL DEFAULT 0,
  active_skill_id INT NULL,
  active_passive_id INT NULL,
  preset_json JSON NULL,
  daily_drop_date DATE NULL,
  daily_drop_count TINYINT NOT NULL DEFAULT 0,
  world_insight_key VARCHAR(16) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_uid_role_special (uid, role_id),
  KEY idx_role_special_rank (role_template_id, growth_stage, growth_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_role_special_material (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  role_id INT NOT NULL,
  material_code VARCHAR(40) NOT NULL,
  amount INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_uid_role_material (uid, role_id, material_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS role_special_material_ledger (
  id BIGINT NOT NULL AUTO_INCREMENT,
  request_id VARCHAR(64) NOT NULL,
  battle_id VARCHAR(64) NULL,
  uid INT NOT NULL,
  role_id INT NOT NULL,
  material_code VARCHAR(40) NOT NULL,
  change_amount INT NOT NULL,
  balance_before INT NOT NULL,
  balance_after INT NOT NULL,
  source_type VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_special_ledger_request (request_id, material_code),
  KEY idx_special_ledger_battle (battle_id, uid, role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_role_special_collection (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  role_id INT NOT NULL,
  collection_id INT NOT NULL,
  fragment_amount INT NOT NULL DEFAULT 0,
  unlocked TINYINT(1) NOT NULL DEFAULT 0,
  unlocked_at DATETIME NULL,
  equipped_slot VARCHAR(12) NULL,
  effect_snapshot_json JSON NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_uid_role_collection (uid, role_id, collection_id),
  KEY idx_role_collection_equipped (uid, role_id, equipped_slot)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS role_special_pity (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  role_id INT NOT NULL,
  pool_version VARCHAR(20) NOT NULL DEFAULT 'v1',
  total_count INT NOT NULL DEFAULT 0,
  rare_pity_count TINYINT NOT NULL DEFAULT 0,
  target_collection_id INT NULL,
  target_miss_count TINYINT NOT NULL DEFAULT 0,
  daily_pray_date DATE NULL,
  daily_pray_count TINYINT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_uid_role_pool (uid, role_id, pool_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_role_special_combo (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  role_id INT NOT NULL,
  combo_type VARCHAR(30) NOT NULL,
  custom_name VARCHAR(30) NOT NULL,
  normalized_name VARCHAR(30) NOT NULL,
  material_collection_ids_json JSON NOT NULL,
  slot_order_json JSON NOT NULL,
  multiplier DECIMAL(6,3) NOT NULL,
  effect_json JSON NOT NULL,
  seed BIGINT NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'ACTIVE',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_role_combo_name (uid, role_id, normalized_name),
  KEY idx_role_combo_rank (role_id, status, multiplier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS role_special_battle_log (
  id BIGINT NOT NULL AUTO_INCREMENT,
  battle_id VARCHAR(64) NOT NULL,
  uid INT NOT NULL,
  role_id INT NOT NULL,
  skill_id INT NULL,
  combo_id BIGINT NULL,
  trigger_round INT NOT NULL,
  target_id VARCHAR(64) NULL,
  base_value BIGINT NOT NULL DEFAULT 0,
  multiplier DECIMAL(6,3) NOT NULL DEFAULT 0,
  final_value BIGINT NOT NULL DEFAULT 0,
  effect_result_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_battle_special_trigger (battle_id, uid, role_id, skill_id, trigger_round)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS role_special_operation_log (
  id BIGINT NOT NULL AUTO_INCREMENT,
  request_id VARCHAR(64) NOT NULL,
  uid INT NOT NULL,
  role_id INT NOT NULL,
  operation_type VARCHAR(24) NOT NULL,
  result_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_role_special_request (request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS role_special_rank_record (
  id BIGINT NOT NULL AUTO_INCREMENT,
  season_key VARCHAR(20) NOT NULL,
  role_template_id INT NOT NULL,
  rank_type VARCHAR(24) NOT NULL,
  uid INT NOT NULL,
  score_primary DECIMAL(14,3) NOT NULL DEFAULT 0,
  score_secondary DECIMAL(14,3) NOT NULL DEFAULT 0,
  detail_json JSON NOT NULL,
  replay_id VARCHAR(64) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_season_role_rank (season_key, role_template_id, rank_type, uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 萧炎：异火图鉴
INSERT INTO role_special_collection_config
(role_template_id, role_name, collection_code, name, rarity, fragment_code, fragment_cost, skill_type, skill_multiplier, effect_json, lore_desc)
VALUES
(1,'萧炎','XY_FLAME_01','青莲地心火',4,'XY_FLAME_01_FRAG',10,'ACTIVE',0.500,'{"type":"DAMAGE","burn":1}','地底岩浆孕育，火中生莲。'),
(1,'萧炎','XY_FLAME_02','陨落心炎',4,'XY_FLAME_02_FRAG',20,'ACTIVE',0.600,'{"type":"DAMAGE","resilience_down":10}','无形心火淬炼斗气。'),
(1,'萧炎','XY_FLAME_03','海心焰',4,'XY_FLAME_03_FRAG',15,'ACTIVE',0.700,'{"type":"DAMAGE","shield_bonus":10}','深蓝火焰如海潮翻涌。'),
(1,'萧炎','XY_FLAME_04','骨灵冷火',4,'XY_FLAME_04_FRAG',20,'PASSIVE',0.800,'{"type":"ENEMY_ATTACK_DOWN","value":10,"duration":1,"trigger":"BATTLE_START"}','极寒与极热相融。'),
(1,'萧炎','XY_FLAME_05','三千焱炎火',4,'XY_FLAME_05_FRAG',25,'ACTIVE',0.900,'{"type":"DAMAGE_HEAL","heal_percent":5}','星空中形成的不死之火。'),
(1,'萧炎','XY_FLAME_06','金帝焚天炎',5,'XY_FLAME_06_FRAG',50,'ACTIVE',1.200,'{"type":"DAMAGE","defense_ignore":10}','古族传承，号称焚尽万物。'),
(1,'萧炎','XY_FLAME_07','净莲妖火',5,'XY_FLAME_07_FRAG',60,'ACTIVE',1.500,'{"type":"DAMAGE_DISPEL","dispel":1}','可净化万物的妖火。'),
(1,'萧炎','XY_FLAME_08','虚无吞炎',5,'XY_FLAME_08_FRAG',70,'ACTIVE',1.800,'{"type":"DAMAGE_HEAL","heal_damage_percent":5,"heal_percent_cap":5}','生于虚无，拥有吞噬之能。'),
(1,'萧炎','XY_FLAME_09','帝炎',5,'XY_FLAME_09_FRAG',80,'ACTIVE',2.000,'{"type":"DAMAGE","defense_ignore":15}','万火归一的传承投影。')
ON DUPLICATE KEY UPDATE name=VALUES(name), rarity=VALUES(rarity), fragment_cost=VALUES(fragment_cost), skill_type=VALUES(skill_type), skill_multiplier=VALUES(skill_multiplier), effect_json=VALUES(effect_json), lore_desc=VALUES(lore_desc), enabled=1;

INSERT INTO role_growth_stage_config
(role_template_id, role_name, growth_code, stage_no, stage_name, cost_json, unlock_condition_json, unlock_effect_json)
VALUES
(1,'萧炎','XIAO_YAN_FENJUE',1,'黄阶','{"XY_GROWTH":0}','{"unlocked":1}','{"active_slot":1}'),
(1,'萧炎','XIAO_YAN_FENJUE',2,'玄阶','{"XY_GROWTH":10}','{"unlocked":3}','{"ability_trait":1}'),
(1,'萧炎','XIAO_YAN_FENJUE',3,'地阶','{"XY_GROWTH":20}','{"unlocked":5}','{"combo":1}'),
(1,'萧炎','XIAO_YAN_FENJUE',4,'准天阶','{"XY_GROWTH":35}','{"unlocked":7}','{"presets":2}'),
(1,'萧炎','XIAO_YAN_FENJUE',5,'天阶','{"XY_GROWTH":50}','{"unlocked":9}','{"average_protection":1,"passive_slots":2}')
ON DUPLICATE KEY UPDATE stage_name=VALUES(stage_name), cost_json=VALUES(cost_json), unlock_condition_json=VALUES(unlock_condition_json), unlock_effect_json=VALUES(unlock_effect_json), enabled=1;
