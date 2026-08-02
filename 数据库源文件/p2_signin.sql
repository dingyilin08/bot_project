-- 三十日滚动签到：漏签不清零，每个自然日最多领取一次。
CREATE TABLE IF NOT EXISTS user_signin_progress (
    uid INT NOT NULL,
    cycle_no INT NOT NULL DEFAULT 1,
    cycle_day TINYINT NOT NULL DEFAULT 0,
    total_signins INT NOT NULL DEFAULT 0,
    last_signin_date DATE NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (uid),
    KEY idx_signin_last_date (last_signin_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_三十日签到进度';

CREATE TABLE IF NOT EXISTS user_signin_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    cycle_no INT NOT NULL,
    cycle_day TINYINT NOT NULL,
    sign_date DATE NOT NULL,
    daily_reward_json JSON NOT NULL,
    milestone_reward_json JSON NULL,
    total_reward_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_signin_date (uid, sign_date),
    UNIQUE KEY uk_signin_cycle_day (uid, cycle_no, cycle_day),
    KEY idx_signin_log_uid_time (uid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_签到领奖流水';
