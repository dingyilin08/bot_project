-- P3 专属组合装备态：每个角色同一时间至多装备一个组合。
-- NULL表示未装备；MySQL唯一索引允许多行NULL，只限制slot=1的记录。

SET @role_combo_slot_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE user_role_special_combo ADD COLUMN equipped_slot TINYINT NULL DEFAULT NULL COMMENT ''装备槽：1=当前装备，NULL=未装备'' AFTER status',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_role_special_combo'
      AND COLUMN_NAME = 'equipped_slot'
);
PREPARE role_combo_slot_stmt FROM @role_combo_slot_ddl;
EXECUTE role_combo_slot_stmt;
DEALLOCATE PREPARE role_combo_slot_stmt;

SET @role_combo_unique_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE user_role_special_combo ADD UNIQUE KEY uk_role_combo_equipped (uid, role_id, equipped_slot)',
        'SELECT 1')
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_role_special_combo'
      AND INDEX_NAME = 'uk_role_combo_equipped'
);
PREPARE role_combo_unique_stmt FROM @role_combo_unique_ddl;
EXECUTE role_combo_unique_stmt;
DEALLOCATE PREPARE role_combo_unique_stmt;
