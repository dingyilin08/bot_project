-- 日常任务：每日按真实玩法事件完成，单项奖励与全勤礼包均可防重领取。
CREATE TABLE IF NOT EXISTS user_daily_task_progress (
    id BIGINT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    task_date DATE NOT NULL,
    task_code VARCHAR(32) NOT NULL,
    completed_at DATETIME NULL,
    claimed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_daily_task (uid, task_date, task_code),
    KEY idx_daily_task_uid_date (uid, task_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_日常任务进度';

CREATE TABLE IF NOT EXISTS user_daily_task_bonus (
    id BIGINT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    task_date DATE NOT NULL,
    bonus_code VARCHAR(32) NOT NULL,
    reward_json JSON NOT NULL,
    claimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_daily_task_bonus (uid, task_date, bonus_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_日常任务全勤奖励';
