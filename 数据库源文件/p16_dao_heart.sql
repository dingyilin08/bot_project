-- P16 道心问境：每日可复现事件、倾向、短效 Buff 与幂等奖励（MySQL 5.7）

CREATE TABLE IF NOT EXISTS `dao_heart_profile` (
  `uid` int NOT NULL,
  `clarity` int NOT NULL DEFAULT 0 COMMENT '清明倾向',
  `courage` int NOT NULL DEFAULT 0 COMMENT '勇毅倾向',
  `compassion` int NOT NULL DEFAULT 0 COMMENT '仁心倾向',
  `active_buff_code` varchar(48) DEFAULT NULL,
  `active_buff_value` int NOT NULL DEFAULT 0 COMMENT '基点或玩法定义值',
  `active_buff_expires_at` datetime DEFAULT NULL,
  `last_choice_date` date DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`uid`),
  KEY `idx_dao_heart_buff_expiry` (`active_buff_expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_道心倾向与短效增益';

CREATE TABLE IF NOT EXISTS `dao_heart_daily` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `uid` int NOT NULL,
  `event_date` date NOT NULL,
  `event_key` varchar(48) NOT NULL,
  `event_version` int NOT NULL,
  `event_seed` varchar(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `choice_key` varchar(24) DEFAULT NULL,
  `tendency_key` varchar(24) DEFAULT NULL,
  `tendency_delta` int NOT NULL DEFAULT 0,
  `reward_json` json DEFAULT NULL,
  `result_json` json DEFAULT NULL,
  `request_id` varchar(80) DEFAULT NULL,
  `chosen_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_dao_heart_uid_date` (`uid`,`event_date`),
  KEY `idx_dao_heart_request` (`request_id`),
  KEY `idx_dao_heart_date` (`event_date`,`choice_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_每日道心问境记录';
