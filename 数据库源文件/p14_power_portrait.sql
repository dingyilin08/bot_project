-- P14 玩家战力立绘提交与 GM 审核（MySQL 5.7，可重复执行）

CREATE TABLE IF NOT EXISTS power_portrait_submission (
    id BIGINT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    status VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'PENDING',
    storage_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    original_filename VARCHAR(255) NOT NULL DEFAULT '',
    content_type VARCHAR(80) CHARACTER SET ascii COLLATE ascii_general_ci NOT NULL DEFAULT 'image',
    width INT UNSIGNED NOT NULL,
    height INT UNSIGNED NOT NULL,
    file_size INT UNSIGNED NOT NULL,
    sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    platform_request_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
    reviewed_by INT NULL,
    reject_reason VARCHAR(120) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_power_portrait_storage (storage_key),
    UNIQUE KEY uk_power_portrait_request (platform_request_id),
    KEY idx_power_portrait_queue (status, id),
    KEY idx_power_portrait_user (uid, status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家战力立绘提交与GM审核';
