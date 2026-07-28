CREATE TABLE IF NOT EXISTS party_battle_session (
    id CHAR(32) NOT NULL, party_id BIGINT NOT NULL, round_no INT NOT NULL DEFAULT 1,
    state VARCHAR(16) NOT NULL DEFAULT 'ACTIVE', snapshot_json JSON NOT NULL,
    deadline_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (id), KEY idx_party_battle_state (party_id, state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- MySQL 5.7 不支持 ADD COLUMN IF NOT EXISTS；以下语句兼容已部署旧表和新表。
SET @party_battle_deadline_ddl = (
    SELECT IF(COUNT(*) = 0,
        'ALTER TABLE party_battle_session ADD COLUMN deadline_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP',
        'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'party_battle_session'
      AND COLUMN_NAME = 'deadline_at'
);
PREPARE party_battle_deadline_stmt FROM @party_battle_deadline_ddl;
EXECUTE party_battle_deadline_stmt;
DEALLOCATE PREPARE party_battle_deadline_stmt;
CREATE TABLE IF NOT EXISTS party_battle_member (
    id BIGINT NOT NULL AUTO_INCREMENT, session_id CHAR(32) NOT NULL, uid INT NOT NULL,
    PRIMARY KEY (id), UNIQUE KEY uk_party_battle_member (session_id, uid), KEY idx_party_battle_member (uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS party_battle_action (
    id BIGINT NOT NULL AUTO_INCREMENT, session_id CHAR(32) NOT NULL, round_no INT NOT NULL, uid INT NOT NULL, action_type VARCHAR(16) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (id), UNIQUE KEY uk_party_battle_action (session_id, round_no, uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
