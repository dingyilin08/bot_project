-- P1 洞府生产中枢：请在备份后执行。仅使用已有灵石货币。
CREATE TABLE IF NOT EXISTS user_estate_building (
    uid INT NOT NULL, building_type VARCHAR(32) NOT NULL, level TINYINT NOT NULL DEFAULT 1,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (uid, building_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS user_estate_claim (
    uid INT NOT NULL, claim_date DATE NOT NULL, claim_mode VARCHAR(16) NOT NULL,
    claimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (uid, claim_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
