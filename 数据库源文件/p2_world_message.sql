-- 世界消息攻略库与普通回复尾注的全局轮换游标。
CREATE TABLE IF NOT EXISTS world_message (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  content VARCHAR(180) NOT NULL,
  content_hash CHAR(64) NOT NULL,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  created_by INT NOT NULL DEFAULT 0,
  updated_by INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_world_message_hash (content_hash),
  KEY idx_world_message_rotation (enabled, is_deleted, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS world_message_state (
  state_key VARCHAR(32) NOT NULL,
  next_source TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0=官方群，1=世界消息',
  last_message_id BIGINT UNSIGNED NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (state_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO world_message_state (state_key, next_source, last_message_id)
VALUES ('reply_footer', 0, NULL);

INSERT INTO world_message
  (content, content_hash, enabled, is_deleted, created_by, updated_by)
VALUES
  ('新道友可先完成“问道札记”，快速熟悉角色、装备与副本流程。', SHA2('新道友可先完成“问道札记”，快速熟悉角色、装备与副本流程。', 256), 1, 0, 0, 0),
  ('每天发送“签到”和“日常任务”，可以稳定积累养成资源。', SHA2('每天发送“签到”和“日常任务”，可以稳定积累养成资源。', 256), 1, 0, 0, 0),
  ('挑战副本前可查看“当前装备”和“技能背包”，确认出战配置。', SHA2('挑战副本前可查看“当前装备”和“技能背包”，确认出战配置。', 256), 1, 0, 0, 0),
  ('药园种植与炼丹能补充成长资源，记得及时采摘和收丹。', SHA2('药园种植与炼丹能补充成长资源，记得及时采摘和收丹。', 256), 1, 0, 0, 0),
  ('组队成员准备完成后，再开启道途或队伍战斗会更加顺畅。', SHA2('组队成员准备完成后，再开启道途或队伍战斗会更加顺畅。', 256), 1, 0, 0, 0),
  ('世界 Boss 开放时发送“世界BOSS”，可查看挑战状态、排行与奖励。', SHA2('世界 Boss 开放时发送“世界BOSS”，可查看挑战状态、排行与奖励。', 256), 1, 0, 0, 0)
ON DUPLICATE KEY UPDATE content=VALUES(content);
