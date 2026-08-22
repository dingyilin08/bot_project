-- 低等级玩家删号审计。只保留不可逆操作所需的最小化哈希记录。
CREATE TABLE IF NOT EXISTS account_deletion_log (
    openid_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    last_uid INT NOT NULL,
    role_count INT UNSIGNED NOT NULL,
    highest_role_level INT UNSIGNED NOT NULL,
    deletion_count INT UNSIGNED NOT NULL DEFAULT 1,
    first_deleted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_deleted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (openid_hash),
    KEY idx_account_deletion_uid (last_uid),
    KEY idx_account_deletion_time (last_deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='玩家主动删号的最小化防滥用审计';
