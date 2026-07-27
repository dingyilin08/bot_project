CREATE TABLE IF NOT EXISTS party_battle_session (
    id CHAR(32) NOT NULL, party_id BIGINT NOT NULL, round_no INT NOT NULL DEFAULT 1,
    state VARCHAR(16) NOT NULL DEFAULT 'ACTIVE', snapshot_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (id), KEY idx_party_battle_state (party_id, state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS party_battle_member (
    id BIGINT NOT NULL AUTO_INCREMENT, session_id CHAR(32) NOT NULL, uid INT NOT NULL,
    PRIMARY KEY (id), UNIQUE KEY uk_party_battle_member (session_id, uid), KEY idx_party_battle_member (uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS party_battle_action (
    id BIGINT NOT NULL AUTO_INCREMENT, session_id CHAR(32) NOT NULL, round_no INT NOT NULL, uid INT NOT NULL, action_type VARCHAR(16) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (id), UNIQUE KEY uk_party_battle_action (session_id, round_no, uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
