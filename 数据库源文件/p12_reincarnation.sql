-- 角色轮回：每名角色默认第1世，最高第9世。
SET @has_reincarnation_count := (
    SELECT COUNT(1)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_role'
      AND COLUMN_NAME = 'reincarnation_count'
);
SET @reincarnation_sql := IF(
    @has_reincarnation_count = 0,
    'ALTER TABLE user_role ADD COLUMN reincarnation_count TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT ''角色当前世数，1至9''',
    'SELECT 1'
);
PREPARE reincarnation_stmt FROM @reincarnation_sql;
EXECUTE reincarnation_stmt;
DEALLOCATE PREPARE reincarnation_stmt;
