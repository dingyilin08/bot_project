-- 轮海深渊子系统迁移。
-- 仅新增表和索引；可重复执行，不删除现有玩家数据。

-- 深渊复用现有技能战斗快照。旧服若未执行队伍战斗 v2 迁移，需在此补齐
-- 明确的技能法力消耗字段，避免挑战初始化读取技能时失败。
SET @abyss_data_skill_mana_missing = (
  SELECT COUNT(*) = 0
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'data_skill'
    AND COLUMN_NAME = 'mana_cost'
);
SET @abyss_data_skill_mana_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE data_skill ADD COLUMN mana_cost SMALLINT UNSIGNED NOT NULL DEFAULT 20 AFTER cooldown',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'data_skill'
    AND COLUMN_NAME = 'mana_cost'
);
PREPARE abyss_data_skill_mana_stmt FROM @abyss_data_skill_mana_ddl;
EXECUTE abyss_data_skill_mana_stmt;
DEALLOCATE PREPARE abyss_data_skill_mana_stmt;

UPDATE data_skill
SET mana_cost = CASE CAST(skill_type AS UNSIGNED)
  WHEN 1 THEN 25
  WHEN 2 THEN 18
  WHEN 3 THEN 22
  WHEN 4 THEN 28
  ELSE 20
END
WHERE @abyss_data_skill_mana_missing = 1;

SET @abyss_user_skill_mana_missing = (
  SELECT COUNT(*) = 0
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'user_skill'
    AND COLUMN_NAME = 'mana_cost'
);
SET @abyss_user_skill_mana_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE user_skill ADD COLUMN mana_cost SMALLINT UNSIGNED NOT NULL DEFAULT 20 AFTER cooldown',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'user_skill'
    AND COLUMN_NAME = 'mana_cost'
);
PREPARE abyss_user_skill_mana_stmt FROM @abyss_user_skill_mana_ddl;
EXECUTE abyss_user_skill_mana_stmt;
DEALLOCATE PREPARE abyss_user_skill_mana_stmt;

UPDATE user_skill
SET mana_cost = CASE CAST(skill_type AS UNSIGNED)
  WHEN 1 THEN 25
  WHEN 2 THEN 18
  WHEN 3 THEN 22
  WHEN 4 THEN 28
  ELSE 20
END
WHERE @abyss_user_skill_mana_missing = 1;

UPDATE user_skill us
JOIN data_skill ds ON us.is_data_skill = 1 AND us.skill_id = ds.id
SET us.mana_cost = ds.mana_cost
WHERE @abyss_user_skill_mana_missing = 1;

CREATE TABLE IF NOT EXISTS `user_abyss_profile` (
  `uid` int NOT NULL,
  `highest_cleared_layer` int NOT NULL DEFAULT 0,
  `total_kills` bigint NOT NULL DEFAULT 0,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`uid`),
  KEY `idx_abyss_rank` (`highest_cleared_layer`, `total_kills`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `user_abyss_layer_record` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `uid` int NOT NULL,
  `layer_no` int NOT NULL,
  `best_stars` tinyint NOT NULL DEFAULT 0,
  `best_kills` tinyint NOT NULL DEFAULT 0,
  `clear_count` int NOT NULL DEFAULT 0,
  `exp_rewarded` tinyint(1) NOT NULL DEFAULT 0,
  `rewarded_stars` tinyint NOT NULL DEFAULT 0,
  `first_cleared_at` datetime NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_abyss_layer` (`uid`, `layer_no`),
  KEY `idx_abyss_layer_rank` (`layer_no`, `best_stars`, `first_cleared_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `abyss_run` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_uuid` char(36) NOT NULL,
  `uid` int NOT NULL,
  `run_type` varchar(16) NOT NULL DEFAULT 'NORMAL',
  `layer_no` int NOT NULL,
  `role_id` int NULL,
  `source_world` varchar(64) NOT NULL,
  `source_dungeon_id` int NOT NULL,
  `rng_seed` varchar(128) NOT NULL,
  `state` varchar(24) NOT NULL DEFAULT 'READY',
  `wave_no` tinyint NOT NULL DEFAULT 1,
  `kill_count` tinyint NOT NULL DEFAULT 0,
  `player_hp_ratio` decimal(8,6) NOT NULL DEFAULT 1.000000,
  `version` int NOT NULL DEFAULT 0,
  `role_snapshot_json` json NULL,
  `effect_snapshot_json` json NULL,
  `reward_snapshot_json` json NULL,
  `settlement_json` json NULL,
  `active_uid` int GENERATED ALWAYS AS (
    CASE WHEN `state` IN ('READY','FIGHTING','QUALIFIED','SETTLING') THEN `uid` ELSE NULL END
  ) STORED,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `settled_at` datetime NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_abyss_run_uuid` (`run_uuid`),
  UNIQUE KEY `uk_abyss_active_uid` (`active_uid`),
  KEY `idx_abyss_run_uid_created` (`uid`, `created_at`),
  KEY `idx_abyss_run_state` (`state`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `abyss_run_monster` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `run_uuid` char(36) NOT NULL,
  `wave_no` tinyint NOT NULL,
  `slot_no` tinyint NOT NULL,
  `source_monster_id` int NOT NULL,
  `monster_name` varchar(128) NOT NULL,
  `monster_type` varchar(16) NOT NULL,
  `monster_snapshot_json` json NOT NULL,
  `state` varchar(16) NOT NULL DEFAULT 'READY',
  `battle_uuid` char(36) NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `defeated_at` datetime NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_abyss_wave_slot` (`run_uuid`, `wave_no`, `slot_no`),
  UNIQUE KEY `uk_abyss_monster_battle` (`battle_uuid`),
  KEY `idx_abyss_monster_run_state` (`run_uuid`, `state`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
