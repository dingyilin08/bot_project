-- 定向熔炉分步交互状态（MySQL 5.7）
-- 执行前请备份数据库；本迁移可重复执行。

CREATE TABLE IF NOT EXISTS user_directional_smelt (
    uid INT NOT NULL,
    equip_id_1 BIGINT NULL,
    equip_id_2 BIGINT NULL,
    equip_id_3 BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (uid),
    KEY idx_directional_smelt_equip_1 (equip_id_1),
    KEY idx_directional_smelt_equip_2 (equip_id_2),
    KEY idx_directional_smelt_equip_3 (equip_id_3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
