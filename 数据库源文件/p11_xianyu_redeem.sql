-- P11 一次性仙玉兑换码（MySQL 5.7，可重复执行）

CREATE TABLE IF NOT EXISTS xianyu_redeem_code (
    id BIGINT NOT NULL AUTO_INCREMENT,
    redeem_code VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    amount INT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    batch_id CHAR(32) NOT NULL,
    created_by INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    redeemed_by INT NULL,
    redeemed_at DATETIME NULL,
    expires_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_xianyu_redeem_code (redeem_code),
    KEY idx_xianyu_redeem_status (status, amount, created_at),
    KEY idx_xianyu_redeem_user (redeemed_by, redeemed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仙玉一次性兑换码';

CREATE TABLE IF NOT EXISTS user_xianyu_redeem_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    code_id BIGINT NOT NULL,
    uid INT NOT NULL,
    amount INT NOT NULL,
    balance_before BIGINT NOT NULL,
    balance_after BIGINT NOT NULL,
    redeemed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_xianyu_redeem_log_code (code_id),
    KEY idx_xianyu_redeem_log_user (uid, redeemed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_仙玉兑换流水';
