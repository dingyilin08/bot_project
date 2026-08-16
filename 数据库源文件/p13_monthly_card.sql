-- P13 月卡权益、兑换码与每日领取流水（MySQL 5.7，可重复执行）

CREATE TABLE IF NOT EXISTS monthly_card_redeem_code (
    id BIGINT NOT NULL AUTO_INCREMENT,
    redeem_code VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    days SMALLINT NOT NULL DEFAULT 30,
    activation_xianyu INT NOT NULL DEFAULT 600,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    batch_id CHAR(32) NOT NULL,
    created_by INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    redeemed_by INT NULL,
    redeemed_at DATETIME NULL,
    expires_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_monthly_card_code (redeem_code),
    KEY idx_monthly_card_code_status (status, created_at),
    KEY idx_monthly_card_code_user (redeemed_by, redeemed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='月卡一次性兑换码';

CREATE TABLE IF NOT EXISTS user_monthly_card (
    uid INT NOT NULL,
    expires_on DATE NOT NULL,
    total_days_activated INT NOT NULL DEFAULT 0,
    total_days_claimed INT NOT NULL DEFAULT 0,
    last_claim_date DATE NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (uid),
    KEY idx_user_monthly_card_expiry (expires_on)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_月卡权益';

CREATE TABLE IF NOT EXISTS user_monthly_card_activation_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    code_id BIGINT NOT NULL,
    uid INT NOT NULL,
    days SMALLINT NOT NULL,
    previous_expires_on DATE NULL,
    new_expires_on DATE NOT NULL,
    activation_xianyu INT NOT NULL,
    balance_before BIGINT NOT NULL,
    balance_after BIGINT NOT NULL,
    activated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_monthly_card_activation_code (code_id),
    KEY idx_monthly_card_activation_user (uid, activated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_月卡激活流水';

CREATE TABLE IF NOT EXISTS user_monthly_card_claim_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    claim_date DATE NOT NULL,
    reward_xianyu INT NOT NULL,
    reward_lingshi BIGINT NOT NULL,
    xianyu_before BIGINT NOT NULL,
    xianyu_after BIGINT NOT NULL,
    lingshi_before BIGINT NOT NULL,
    lingshi_after BIGINT NOT NULL,
    claimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_monthly_card_daily_claim (uid, claim_date),
    KEY idx_monthly_card_claim_user (uid, claimed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_月卡每日领取流水';

CREATE TABLE IF NOT EXISTS user_monthly_card_presence (
    uid INT NOT NULL,
    last_seen_at DATETIME NOT NULL,
    last_announced_at DATETIME NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (uid),
    KEY idx_monthly_card_presence_seen (last_seen_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_月卡在线状态';

CREATE TABLE IF NOT EXISTS world_message_event_queue (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_key VARCHAR(96) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    content VARCHAR(180) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_world_message_event_key (event_key),
    KEY idx_world_message_event_pending (status, available_at, expires_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='临时世界消息事件队列';
