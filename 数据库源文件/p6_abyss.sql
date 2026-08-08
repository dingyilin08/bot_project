-- 轮海深渊子系统迁移。
-- 仅新增表和索引；可重复执行，不删除现有玩家数据。

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
