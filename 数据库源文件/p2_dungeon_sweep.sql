-- 副本扫荡：永久通关记录、幂等结算日志与商城扫荡券。

CREATE TABLE IF NOT EXISTS `user_dungeon_clear` (
  `uid` int NOT NULL,
  `dungeon_id` int NOT NULL,
  `clear_count` int NOT NULL DEFAULT 1,
  `first_clear_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `last_clear_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`uid`, `dungeon_id`),
  KEY `idx_dungeon_id` (`dungeon_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_副本永久通关记录';

INSERT IGNORE INTO `user_dungeon_clear`
  (`uid`, `dungeon_id`, `clear_count`, `first_clear_at`, `last_clear_at`)
SELECT `uid`, `dungeon_id`, 1, COALESCE(`start_time`, CURRENT_TIMESTAMP),
       COALESCE(`last_update`, CURRENT_TIMESTAMP)
FROM `user_dungeon_progress`
WHERE `status` = 'completed';

CREATE TABLE IF NOT EXISTS `user_dungeon_sweep_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `request_key` char(64) NOT NULL,
  `uid` int NOT NULL,
  `dungeon_id` int NOT NULL,
  `role_id` int NOT NULL,
  `reward_json` longtext NOT NULL,
  `remaining_challenges` int NOT NULL,
  `remaining_tickets` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_request_key` (`request_key`),
  KEY `idx_uid_created` (`uid`, `created_at`),
  KEY `idx_uid_dungeon` (`uid`, `dungeon_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_副本扫荡记录';

CREATE TABLE IF NOT EXISTS `data_shop_item` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(50) NOT NULL,
  `item_id` int NOT NULL,
  `price` int NOT NULL,
  `category` varchar(20) NOT NULL,
  `description` varchar(255) NOT NULL,
  `daily_limit` int NOT NULL DEFAULT 0,
  `enabled` tinyint NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_name` (`name`),
  UNIQUE KEY `uk_item_id` (`item_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_灵石商城商品';

INSERT INTO `data_item` (`id`, `name`, `type`, `desc`, `access`)
VALUES (211, '扫荡副本券', 3, '可一键扫荡已通关副本。', '灵石商城')
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`), `desc` = VALUES(`desc`), `access` = VALUES(`access`);

INSERT INTO `data_shop_item`
  (`name`, `item_id`, `price`, `category`, `description`, `daily_limit`, `enabled`)
VALUES
  ('扫荡副本券', 211, 800, '历练', '消耗1张可一键扫荡已通关副本，同时消耗1次副本历练次数。', 20, 1)
ON DUPLICATE KEY UPDATE
  `item_id` = VALUES(`item_id`), `price` = VALUES(`price`),
  `category` = VALUES(`category`), `description` = VALUES(`description`),
  `daily_limit` = VALUES(`daily_limit`), `enabled` = 1;
