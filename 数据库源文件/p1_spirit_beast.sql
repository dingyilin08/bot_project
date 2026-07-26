-- P1 灵兽：请在备份后执行。灵兽仅来自副本后的每日寻访，不进入商城。
CREATE TABLE IF NOT EXISTS data_spirit_beast (
    id INT NOT NULL, name VARCHAR(32) NOT NULL, role VARCHAR(16) NOT NULL, element VARCHAR(16) NOT NULL,
    passive_name VARCHAR(64) NOT NULL, description VARCHAR(255) NOT NULL,
    PRIMARY KEY (id), UNIQUE KEY uk_spirit_beast_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS user_spirit_beast (
    id BIGINT NOT NULL AUTO_INCREMENT, uid INT NOT NULL, beast_id INT NOT NULL, aptitude TINYINT NOT NULL,
    temperament VARCHAR(16) NOT NULL, bond_exp INT NOT NULL DEFAULT 0, is_active TINYINT NOT NULL DEFAULT 0,
    obtained_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (id), KEY idx_spirit_beast_uid_active (uid, is_active),
    CONSTRAINT fk_user_spirit_beast_template FOREIGN KEY (beast_id) REFERENCES data_spirit_beast(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS user_spirit_beast_capture (
    uid INT NOT NULL, capture_date DATE NOT NULL, beast_instance_id BIGINT NOT NULL,
    PRIMARY KEY (uid, capture_date), UNIQUE KEY uk_capture_instance (beast_instance_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT INTO data_spirit_beast (id, name, role, element, passive_name, description) VALUES
    (1, '赤焰灵狐', 'STRIKER', '火', '焰尾追击', '主角攻击后留下炽热灵契，擅长火行追击。'),
    (2, '玄甲龟', 'GUARDIAN', '土', '玄甲护主', '以厚甲护主，适合承受 Boss 阶段伤害。'),
    (3, '青木鹿', 'HEALER', '木', '回春灵息', '回合结算时为主人带来温和疗愈。'),
    (4, '寒翎雀', 'DISRUPTOR', '水', '霜羽迟滞', '以灵动身法抢占先手并扰乱敌方节奏。')
ON DUPLICATE KEY UPDATE name = VALUES(name), role = VALUES(role), element = VALUES(element), passive_name = VALUES(passive_name), description = VALUES(description);
