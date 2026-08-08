-- P7 灵兽角色绑定与战力分项
-- MySQL 5.7 可重放迁移；上线顺序：先执行本文件，再发布应用代码。

SET @beast_role_column_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE user_spirit_beast ADD COLUMN equipped_role_id INT NULL COMMENT ''绑定角色ID；一名角色一只灵兽'' AFTER is_active',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_spirit_beast'
      AND COLUMN_NAME = 'equipped_role_id'
);
PREPARE beast_role_column_stmt FROM @beast_role_column_ddl;
EXECUTE beast_role_column_stmt;
DEALLOCATE PREPARE beast_role_column_stmt;

-- 将旧版“账号唯一出战灵兽”平滑绑定到当时的出战角色。
UPDATE user_spirit_beast AS beast
JOIN user_role AS role
  ON role.uid = beast.uid AND role.is_chuzhan = 1
SET beast.equipped_role_id = role.id
WHERE beast.is_active = 1
  AND beast.equipped_role_id IS NULL;

-- 极端旧数据若同一角色存在多条 active，只保留编号最大的灵兽绑定。
UPDATE user_spirit_beast AS older
JOIN user_spirit_beast AS newer
  ON newer.uid = older.uid
 AND newer.equipped_role_id = older.equipped_role_id
 AND newer.id > older.id
SET older.equipped_role_id = NULL,
    older.is_active = 0
WHERE older.equipped_role_id IS NOT NULL;

SET @beast_role_unique_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE user_spirit_beast ADD UNIQUE KEY uk_spirit_beast_role (uid, equipped_role_id)',
        'SELECT 1')
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_spirit_beast'
      AND INDEX_NAME = 'uk_spirit_beast_role'
);
PREPARE beast_role_unique_stmt FROM @beast_role_unique_ddl;
EXECUTE beast_role_unique_stmt;
DEALLOCATE PREPARE beast_role_unique_stmt;

SET @power_beast_column_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE user_zt ADD COLUMN power_beast BIGINT NOT NULL DEFAULT 0 COMMENT ''当前角色灵兽战力'' AFTER power_skill',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_zt'
      AND COLUMN_NAME = 'power_beast'
);
PREPARE power_beast_column_stmt FROM @power_beast_column_ddl;
EXECUTE power_beast_column_stmt;
DEALLOCATE PREPARE power_beast_column_stmt;

-- is_active 仅保留为当前出战角色的兼容标记，真实绑定以 equipped_role_id 为准。
UPDATE user_spirit_beast AS beast
LEFT JOIN user_role AS role
  ON role.uid = beast.uid AND role.id = beast.equipped_role_id
SET beast.is_active = IF(role.is_chuzhan = 1, 1, 0);
