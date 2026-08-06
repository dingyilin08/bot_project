-- 玩家邀请码：存量账号仅建立管理员归属，不补发奖励；新注册绑定才会生成奖励流水。
CREATE TABLE IF NOT EXISTS user_invitation_profile (
    uid INT NOT NULL,
    invite_code CHAR(8) NOT NULL,
    inviter_uid INT NULL,
    reward_eligible TINYINT NOT NULL DEFAULT 0,
    bound_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (uid),
    UNIQUE KEY uk_invitation_code (invite_code),
    KEY idx_invitation_inviter (inviter_uid, reward_eligible)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家邀请码与邀请归属';

CREATE TABLE IF NOT EXISTS user_invitation_reward (
    id BIGINT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    inviter_uid INT NOT NULL,
    invitee_uid INT NOT NULL,
    reward_code VARCHAR(24) NOT NULL,
    lingshi INT NOT NULL DEFAULT 0,
    xianyu INT NOT NULL DEFAULT 0,
    available_at DATETIME NULL,
    claimed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_invitation_reward (uid, invitee_uid, reward_code),
    KEY idx_invitation_reward_claim (uid, available_at, claimed_at),
    KEY idx_invitation_reward_invitee (invitee_uid, reward_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家邀请奖励流水';
