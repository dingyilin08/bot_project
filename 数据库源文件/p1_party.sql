-- P1 队伍与阵法：请在备份后执行；仅保存同群招募与编队，不转移任何资产。
CREATE TABLE IF NOT EXISTS party (
    id BIGINT NOT NULL AUTO_INCREMENT, party_code CHAR(8) NOT NULL, group_openid VARCHAR(128) NOT NULL,
    leader_uid INT NOT NULL, formation VARCHAR(16) NOT NULL DEFAULT '锋矢', state VARCHAR(16) NOT NULL DEFAULT 'LOBBY',
    max_members TINYINT NOT NULL DEFAULT 4, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uk_party_code (party_code), KEY idx_party_group_state (group_openid, state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS party_member (
    id BIGINT NOT NULL AUTO_INCREMENT, party_id BIGINT NOT NULL, uid INT NOT NULL, ready TINYINT NOT NULL DEFAULT 0,
    position VARCHAR(16) NOT NULL DEFAULT '后列', member_state VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, left_at DATETIME NULL,
    PRIMARY KEY (id), UNIQUE KEY uk_party_uid (party_id, uid), KEY idx_party_member_uid (uid, member_state),
    CONSTRAINT fk_party_member_party FOREIGN KEY (party_id) REFERENCES party(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
