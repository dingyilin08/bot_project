-- P3 洞府真实效果与日领奖励快照。
-- MySQL 5.7 不支持 ADD COLUMN IF NOT EXISTS，使用 information_schema 保持迁移可重放。

SET @estate_reward_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE user_estate_claim ADD COLUMN reward_lingshi BIGINT NULL COMMENT ''本次实际灵石奖励''',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_estate_claim'
      AND COLUMN_NAME = 'reward_lingshi'
);
PREPARE estate_reward_stmt FROM @estate_reward_ddl;
EXECUTE estate_reward_stmt;
DEALLOCATE PREPARE estate_reward_stmt;

SET @estate_levels_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE user_estate_claim ADD COLUMN levels_json JSON NULL COMMENT ''领取时建筑等级快照（稳定code）''',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_estate_claim'
      AND COLUMN_NAME = 'levels_json'
);
PREPARE estate_levels_stmt FROM @estate_levels_ddl;
EXECUTE estate_levels_stmt;
DEALLOCATE PREPARE estate_levels_stmt;

SET @estate_rule_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE user_estate_claim ADD COLUMN rule_version VARCHAR(32) NULL COMMENT ''洞府规则版本''',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_estate_claim'
      AND COLUMN_NAME = 'rule_version'
);
PREPARE estate_rule_stmt FROM @estate_rule_ddl;
EXECUTE estate_rule_stmt;
DEALLOCATE PREPARE estate_rule_stmt;
