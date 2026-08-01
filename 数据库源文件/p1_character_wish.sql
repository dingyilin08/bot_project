-- 仙玉祈愿子系统（MySQL 5.7+）
-- 本迁移只新增表与幂等种子，不改动既有玩家核心表。

CREATE TABLE IF NOT EXISTS character_wish_pool (
  id INT NOT NULL AUTO_INCREMENT,
  pool_code VARCHAR(32) NOT NULL,
  version VARCHAR(20) NOT NULL,
  name VARCHAR(50) NOT NULL,
  single_cost INT NOT NULL DEFAULT 160,
  ten_cost INT NOT NULL DEFAULT 1500,
  compose_fragment_cost INT NOT NULL DEFAULT 10,
  herb_rate_bp INT NOT NULL DEFAULT 3000,
  pill_rate_bp INT NOT NULL DEFAULT 3000,
  special4_rate_bp INT NOT NULL DEFAULT 2500,
  special5_rate_bp INT NOT NULL DEFAULT 1000,
  role_fragment_rate_bp INT NOT NULL DEFAULT 500,
  pity_count INT NOT NULL DEFAULT 80,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  starts_at DATETIME NULL,
  ends_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_character_wish_pool (pool_code, version),
  KEY idx_character_wish_enabled (enabled, starts_at, ends_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS character_wish_rarity_weight (
  id INT NOT NULL AUTO_INCREMENT,
  pool_id INT NOT NULL,
  reward_group VARCHAR(16) NOT NULL,
  rarity TINYINT NOT NULL,
  weight INT NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uk_character_wish_weight (pool_id, reward_group, rarity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_character_fragment (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  role_template_id INT NOT NULL,
  amount INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_character_fragment (uid, role_template_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS character_fragment_ledger (
  id BIGINT NOT NULL AUTO_INCREMENT,
  request_id VARCHAR(80) NOT NULL,
  uid INT NOT NULL,
  role_template_id INT NOT NULL,
  change_amount INT NOT NULL,
  balance_before INT NOT NULL,
  balance_after INT NOT NULL,
  source_type VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_character_fragment_request (request_id, role_template_id),
  KEY idx_character_fragment_uid (uid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS character_wish_pity (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  pool_id INT NOT NULL,
  pity_count INT NOT NULL DEFAULT 0,
  total_count INT NOT NULL DEFAULT 0,
  target_role_template_id INT NULL,
  full_reward_type VARCHAR(24) NULL,
  full_reward_role_template_id INT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_character_wish_pity (uid, pool_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS character_wish_order (
  id BIGINT NOT NULL AUTO_INCREMENT,
  request_id VARCHAR(80) NOT NULL,
  uid INT NOT NULL,
  pool_id INT NOT NULL,
  pool_version VARCHAR(20) NOT NULL,
  draw_count TINYINT NOT NULL,
  cost_xianyu INT NOT NULL,
  balance_before INT NOT NULL,
  balance_after INT NOT NULL,
  role_id INT NOT NULL,
  target_role_template_id INT NULL,
  pity_before INT NOT NULL,
  pity_after INT NOT NULL DEFAULT 0,
  status VARCHAR(16) NOT NULL DEFAULT 'PROCESSING',
  result_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_character_wish_request (request_id),
  KEY idx_character_wish_history (uid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS character_wish_result (
  id BIGINT NOT NULL AUTO_INCREMENT,
  order_id BIGINT NOT NULL,
  draw_index TINYINT NOT NULL,
  main_reward_type VARCHAR(24) NOT NULL,
  reward_json JSON NOT NULL,
  role_exp INT NOT NULL DEFAULT 0,
  fixed_reward_json JSON NOT NULL,
  pity_before INT NOT NULL,
  pity_after INT NOT NULL,
  is_pity TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_character_wish_draw (order_id, draw_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS character_compose_order (
  id BIGINT NOT NULL AUTO_INCREMENT,
  request_id VARCHAR(80) NOT NULL,
  uid INT NOT NULL,
  role_template_id INT NOT NULL,
  fragment_cost INT NOT NULL DEFAULT 10,
  role_id INT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'PROCESSING',
  result_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_character_compose_request (request_id),
  KEY idx_character_compose_uid (uid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_onboarding_bonus (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  bonus_code VARCHAR(32) NOT NULL,
  claimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reward_json JSON NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_onboarding_bonus (uid, bonus_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO character_wish_pool
  (pool_code, version, name, single_cost, ten_cost, compose_fragment_cost,
   herb_rate_bp, pill_rate_bp, special4_rate_bp, special5_rate_bp,
   role_fragment_rate_bp, pity_count, enabled)
VALUES ('PERMANENT', 'v1', '诸天角色祈愿', 160, 1500, 10, 3000, 3000, 2500, 1000, 500, 80, 1)
ON DUPLICATE KEY UPDATE
  name=VALUES(name), single_cost=VALUES(single_cost), ten_cost=VALUES(ten_cost),
  compose_fragment_cost=VALUES(compose_fragment_cost), herb_rate_bp=VALUES(herb_rate_bp),
  pill_rate_bp=VALUES(pill_rate_bp), special4_rate_bp=VALUES(special4_rate_bp),
  special5_rate_bp=VALUES(special5_rate_bp), role_fragment_rate_bp=VALUES(role_fragment_rate_bp),
  pity_count=VALUES(pity_count), enabled=VALUES(enabled);

INSERT INTO character_wish_rarity_weight (pool_id, reward_group, rarity, weight, enabled)
SELECT p.id, g.reward_group, w.rarity, w.weight, 1
FROM character_wish_pool p
JOIN (SELECT 'HERB' reward_group UNION ALL SELECT 'PILL') g
JOIN (
  SELECT 1 rarity, 100 weight UNION ALL SELECT 2, 40 UNION ALL
  SELECT 3, 15 UNION ALL SELECT 4, 5
) w
WHERE p.pool_code='PERMANENT' AND p.version='v1'
ON DUPLICATE KEY UPDATE weight=VALUES(weight), enabled=1;
