-- 问道札记：完成和领奖分开保存，避免重复消息重复到账。
CREATE TABLE IF NOT EXISTS user_onboarding_progress (
    id BIGINT NOT NULL AUTO_INCREMENT, uid INT NOT NULL, task_code VARCHAR(32) NOT NULL,
    completed_at DATETIME NULL, claimed_at DATETIME NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uk_onboarding_task (uid, task_code), KEY idx_onboarding_uid (uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
