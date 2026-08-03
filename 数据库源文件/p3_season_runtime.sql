-- 赛季展示项实装：机器可读 PVE 规则与可领取、可佩戴装扮。
CREATE TABLE IF NOT EXISTS season_effect_rule (
    id BIGINT NOT NULL AUTO_INCREMENT,
    season_id BIGINT NOT NULL,
    rule_code VARCHAR(32) NOT NULL,
    rule_name VARCHAR(64) NOT NULL,
    rule_text VARCHAR(255) NOT NULL,
    effect_value_bp INT NOT NULL DEFAULT 0,
    rule_version SMALLINT NOT NULL DEFAULT 1,
    enabled TINYINT NOT NULL DEFAULT 1,
    starts_at DATETIME NULL,
    ends_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_season_effect_code (season_id, rule_code),
    KEY idx_season_effect_active (season_id, enabled, starts_at, ends_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cosmetic_catalog (
    cosmetic_code VARCHAR(96) NOT NULL,
    season_id BIGINT NOT NULL,
    reward_tier INT NOT NULL,
    cosmetic_type VARCHAR(16) NOT NULL,
    cosmetic_name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NOT NULL,
    PRIMARY KEY (cosmetic_code),
    KEY idx_cosmetic_season (season_id, reward_tier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_cosmetic (
    id BIGINT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    cosmetic_code VARCHAR(96) NOT NULL,
    source_season_id BIGINT NOT NULL,
    acquired_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_cosmetic (uid, cosmetic_code),
    KEY idx_user_cosmetic_uid (uid, acquired_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_cosmetic_equipped (
    uid INT NOT NULL,
    cosmetic_type VARCHAR(16) NOT NULL,
    cosmetic_code VARCHAR(96) NOT NULL,
    equipped_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (uid, cosmetic_type),
    KEY idx_equipped_cosmetic (cosmetic_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
