-- P1 三千道途：群组异步秘境、节点投票、因果印记。
CREATE TABLE IF NOT EXISTS expedition_session (
    id CHAR(32) NOT NULL, party_id BIGINT NOT NULL, group_openid VARCHAR(128) NOT NULL,
    leader_uid INT NOT NULL, state VARCHAR(16) NOT NULL DEFAULT 'ACTIVE', current_node TINYINT NOT NULL DEFAULT 1,
    node_deadline DATETIME NOT NULL, session_deadline DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at DATETIME NULL,
    PRIMARY KEY (id), KEY idx_expedition_group_state (group_openid, state), KEY idx_expedition_party (party_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS expedition_member (
    id BIGINT NOT NULL AUTO_INCREMENT, session_id CHAR(32) NOT NULL, uid INT NOT NULL,
    last_vote VARCHAR(16) NULL, member_state VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, left_at DATETIME NULL,
    PRIMARY KEY (id), UNIQUE KEY uk_expedition_member (session_id, uid), KEY idx_expedition_member_uid (uid, member_state),
    CONSTRAINT fk_expedition_member_session FOREIGN KEY (session_id) REFERENCES expedition_session(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS expedition_vote (
    id BIGINT NOT NULL AUTO_INCREMENT, session_id CHAR(32) NOT NULL, node_no TINYINT NOT NULL,
    uid INT NOT NULL, vote_choice VARCHAR(16) NOT NULL, voted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uk_expedition_vote (session_id, node_no, uid), KEY idx_expedition_vote_node (session_id, node_no),
    CONSTRAINT fk_expedition_vote_session FOREIGN KEY (session_id) REFERENCES expedition_session(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS expedition_node_log (
    id BIGINT NOT NULL AUTO_INCREMENT, session_id CHAR(32) NOT NULL, node_no TINYINT NOT NULL,
    node_type VARCHAR(16) NOT NULL, selected_choice VARCHAR(16) NOT NULL, reward_lingshi INT NOT NULL,
    summary VARCHAR(255) NOT NULL, resolved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uk_expedition_node (session_id, node_no),
    CONSTRAINT fk_expedition_log_session FOREIGN KEY (session_id) REFERENCES expedition_session(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_causal_mark (
    id BIGINT NOT NULL AUTO_INCREMENT, uid INT NOT NULL, mark_name VARCHAR(32) NOT NULL,
    stack_count INT NOT NULL DEFAULT 1, last_session_id CHAR(32) NULL, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uk_causal_mark (uid, mark_name), KEY idx_causal_uid (uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
