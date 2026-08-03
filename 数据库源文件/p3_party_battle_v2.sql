-- 队伍战斗 v2：执行前请备份。所有 DDL 均可重复执行，旧 snapshot 由 reader 兼容。

SET @party_battle_schema_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE party_battle_session ADD COLUMN schema_version TINYINT NOT NULL DEFAULT 1 AFTER snapshot_json',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'party_battle_session'
      AND COLUMN_NAME = 'schema_version'
);
PREPARE party_battle_schema_stmt FROM @party_battle_schema_ddl;
EXECUTE party_battle_schema_stmt;
DEALLOCATE PREPARE party_battle_schema_stmt;

SET @party_battle_resolved_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE party_battle_session ADD COLUMN resolved_at DATETIME NULL AFTER deadline_at',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'party_battle_session'
      AND COLUMN_NAME = 'resolved_at'
);
PREPARE party_battle_resolved_stmt FROM @party_battle_resolved_ddl;
EXECUTE party_battle_resolved_stmt;
DEALLOCATE PREPARE party_battle_resolved_stmt;

SET @party_action_payload_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE party_battle_action ADD COLUMN action_payload JSON NULL AFTER action_type',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'party_battle_action'
      AND COLUMN_NAME = 'action_payload'
);
PREPARE party_action_payload_stmt FROM @party_action_payload_ddl;
EXECUTE party_action_payload_stmt;
DEALLOCATE PREPARE party_action_payload_stmt;

SET @party_action_request_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE party_battle_action ADD COLUMN request_id VARCHAR(128) NULL AFTER action_payload',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'party_battle_action'
      AND COLUMN_NAME = 'request_id'
);
PREPARE party_action_request_stmt FROM @party_action_request_ddl;
EXECUTE party_action_request_stmt;
DEALLOCATE PREPARE party_action_request_stmt;

SET @party_action_request_unique_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE party_battle_action ADD UNIQUE KEY uk_party_battle_action_request (session_id, uid, request_id)',
        'SELECT 1')
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'party_battle_action'
      AND INDEX_NAME = 'uk_party_battle_action_request'
);
PREPARE party_action_request_unique_stmt FROM @party_action_request_unique_ddl;
EXECUTE party_action_request_unique_stmt;
DEALLOCATE PREPARE party_action_request_unique_stmt;

-- action 主表只保留每人每回合的最终选择；独立请求账本保存该玩家本场收到的
-- 每一个 QQ 消息 ID，避免改动作后旧消息在下一回合被误投。
CREATE TABLE IF NOT EXISTS party_battle_action_request (
    id BIGINT NOT NULL AUTO_INCREMENT,
    session_id CHAR(32) NOT NULL,
    uid INT NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    round_no INT NOT NULL,
    action_type VARCHAR(16) NOT NULL,
    action_payload JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_party_battle_request (session_id, uid, request_id),
    KEY idx_party_battle_request_lookup (uid, request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 旧版本可能因并发留下同队多条 ACTIVE。稳定保留 created_at/id 最新的一条，
-- 其余只关闭会话，不删除快照和 action，便于审计。
UPDATE party_battle_session older
JOIN party_battle_session newer
  ON newer.party_id = older.party_id
 AND newer.state = 'ACTIVE'
 AND older.state = 'ACTIVE'
 AND (
      newer.created_at > older.created_at
      OR (newer.created_at = older.created_at AND newer.id > older.id)
 )
SET older.state = 'CANCELLED', older.resolved_at = COALESCE(older.resolved_at, NOW());

-- MySQL 5.7 没有 partial unique index；ACTIVE 会话投影为 party_id，其他状态为 NULL。
SET @party_active_key_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE party_battle_session ADD COLUMN active_party_id BIGINT GENERATED ALWAYS AS (CASE WHEN state = ''ACTIVE'' THEN party_id ELSE NULL END) STORED',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'party_battle_session'
      AND COLUMN_NAME = 'active_party_id'
);
PREPARE party_active_key_stmt FROM @party_active_key_ddl;
EXECUTE party_active_key_stmt;
DEALLOCATE PREPARE party_active_key_stmt;

SET @party_active_unique_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE party_battle_session ADD UNIQUE KEY uk_party_battle_active_party (active_party_id)',
        'SELECT 1')
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'party_battle_session'
      AND INDEX_NAME = 'uk_party_battle_active_party'
);
PREPARE party_active_unique_stmt FROM @party_active_unique_ddl;
EXECUTE party_active_unique_stmt;
DEALLOCATE PREPARE party_active_unique_stmt;

CREATE TABLE IF NOT EXISTS party_battle_round_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    session_id CHAR(32) NOT NULL,
    round_no INT NOT NULL,
    result_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_party_battle_round_result (session_id, round_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS party_battle_reward (
    id BIGINT NOT NULL AUTO_INCREMENT,
    session_id CHAR(32) NOT NULL,
    uid INT NOT NULL,
    reward_type VARCHAR(24) NOT NULL,
    amount BIGINT NOT NULL,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_party_battle_reward (session_id, uid, reward_type),
    KEY idx_party_battle_reward_uid (uid, granted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 技能法力消耗是明确配置，不由运行时按技能名或伤害临时推算。
SET @data_skill_mana_missing = (
    SELECT COUNT(*) = 0
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'data_skill'
      AND COLUMN_NAME = 'mana_cost'
);
SET @data_skill_mana_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE data_skill ADD COLUMN mana_cost SMALLINT UNSIGNED NOT NULL DEFAULT 20 AFTER cooldown',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'data_skill'
      AND COLUMN_NAME = 'mana_cost'
);
PREPARE data_skill_mana_stmt FROM @data_skill_mana_ddl;
EXECUTE data_skill_mana_stmt;
DEALLOCATE PREPARE data_skill_mana_stmt;

UPDATE data_skill
SET mana_cost = CASE CAST(skill_type AS UNSIGNED)
    WHEN 1 THEN 25
    WHEN 2 THEN 18
    WHEN 3 THEN 22
    WHEN 4 THEN 28
    ELSE 20
END
WHERE @data_skill_mana_missing = 1;

SET @user_skill_mana_missing = (
    SELECT COUNT(*) = 0
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_skill'
      AND COLUMN_NAME = 'mana_cost'
);
SET @user_skill_mana_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE user_skill ADD COLUMN mana_cost SMALLINT UNSIGNED NOT NULL DEFAULT 20 AFTER cooldown',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_skill'
      AND COLUMN_NAME = 'mana_cost'
);
PREPARE user_skill_mana_stmt FROM @user_skill_mana_ddl;
EXECUTE user_skill_mana_stmt;
DEALLOCATE PREPARE user_skill_mana_stmt;

UPDATE user_skill
SET mana_cost = CASE CAST(skill_type AS UNSIGNED)
    WHEN 1 THEN 25
    WHEN 2 THEN 18
    WHEN 3 THEN 22
    WHEN 4 THEN 28
    ELSE 20
END
WHERE @user_skill_mana_missing = 1;

UPDATE user_skill us
JOIN data_skill ds ON us.is_data_skill = 1 AND us.skill_id = ds.id
SET us.mana_cost = ds.mana_cost
WHERE @user_skill_mana_missing = 1;

-- 迁移后让真实会话和队伍生命周期对齐；不删除任何历史队伍。
UPDATE party p
JOIN party_battle_session b ON b.party_id = p.id AND b.state = 'ACTIVE'
SET p.state = 'BATTLE'
WHERE p.state = 'LOBBY';

UPDATE party p
LEFT JOIN party_battle_session b ON b.party_id = p.id AND b.state = 'ACTIVE'
SET p.state = 'LOBBY'
WHERE p.state = 'BATTLE' AND b.id IS NULL;
