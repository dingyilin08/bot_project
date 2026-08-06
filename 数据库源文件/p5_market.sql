-- P5 坊市：出售挂单、收购单、成交记录与防刷屏冷却。
-- 程序首次访问坊市会自动建表；生产环境可先执行本文件。

CREATE TABLE IF NOT EXISTS `user_market_order` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `owner_uid` int NOT NULL,
  `order_type` varchar(8) NOT NULL COMMENT 'SELL=出售，BUY=收购',
  `item_id` int NOT NULL,
  `item_name` varchar(255) NOT NULL,
  `category` varchar(20) NOT NULL,
  `initial_quantity` int NOT NULL,
  `remaining_quantity` int NOT NULL,
  `unit_price` bigint NOT NULL,
  `reserved_lingshi` bigint NOT NULL DEFAULT 0 COMMENT '收购单尚未结算的托管灵石',
  `status` varchar(12) NOT NULL DEFAULT 'OPEN' COMMENT 'OPEN/FILLED/CANCELLED/EXPIRED',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `expires_at` datetime NOT NULL,
  `closed_at` datetime NULL,
  PRIMARY KEY (`id`),
  KEY `idx_market_open` (`status`,`order_type`,`created_at`),
  KEY `idx_market_item` (`status`,`item_id`,`created_at`),
  KEY `idx_market_owner` (`owner_uid`,`status`,`created_at`),
  KEY `idx_market_expire` (`status`,`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_坊市挂单与收购单';

CREATE TABLE IF NOT EXISTS `user_market_trade` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `order_id` bigint NOT NULL,
  `buyer_uid` int NOT NULL,
  `seller_uid` int NOT NULL,
  `item_id` int NOT NULL,
  `item_name` varchar(255) NOT NULL,
  `quantity` int NOT NULL,
  `unit_price` bigint NOT NULL,
  `gross_lingshi` bigint NOT NULL,
  `fee_lingshi` bigint NOT NULL COMMENT '卖家收入的8%，直接销毁',
  `seller_income` bigint NOT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_trade_item` (`item_id`,`created_at`),
  KEY `idx_trade_buyer` (`buyer_uid`,`created_at`),
  KEY `idx_trade_seller` (`seller_uid`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_坊市成交记录';

CREATE TABLE IF NOT EXISTS `user_market_cooldown` (
  `uid` int NOT NULL,
  `action_name` varchar(20) NOT NULL,
  `last_at` bigint NOT NULL,
  PRIMARY KEY (`uid`,`action_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_坊市操作冷却';
