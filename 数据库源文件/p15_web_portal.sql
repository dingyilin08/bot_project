-- 网页玩家端与隔离管理端：一次性 QQ 绑定码、短时会话和网页管理审计。
-- 生产部署前必须配置至少 32 字符的 WEB_AUTH_SECRET。

CREATE TABLE IF NOT EXISTS web_link_code (
  id BIGINT NOT NULL AUTO_INCREMENT,
  uid INT NOT NULL,
  scope VARCHAR(16) NOT NULL,
  code_hash CHAR(64) NOT NULL,
  expires_at DATETIME NOT NULL,
  consumed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_web_link_code_hash (code_hash),
  KEY idx_web_link_uid_scope (uid, scope, created_at),
  KEY idx_web_link_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS web_session (
  id BIGINT NOT NULL AUTO_INCREMENT,
  session_hash CHAR(64) NOT NULL,
  csrf_hash CHAR(64) NOT NULL,
  uid INT NOT NULL,
  scope VARCHAR(16) NOT NULL,
  expires_at DATETIME NOT NULL,
  last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  revoked_at DATETIME NULL,
  client_ip_hash CHAR(64) NOT NULL DEFAULT '',
  user_agent_hash CHAR(64) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_web_session_hash (session_hash),
  KEY idx_web_session_uid_scope (uid, scope, expires_at),
  KEY idx_web_session_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS web_admin_audit (
  id BIGINT NOT NULL AUTO_INCREMENT,
  request_id VARCHAR(80) NOT NULL,
  operator_uid INT NOT NULL,
  target_uid INT NULL,
  action VARCHAR(32) NOT NULL,
  status VARCHAR(16) NOT NULL,
  detail_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_web_admin_request_action (request_id, action),
  KEY idx_web_admin_operator_time (operator_uid, created_at),
  KEY idx_web_admin_target_time (target_uid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 会话表只保存摘要；定时任务可安全清理过期或已撤销 30 天以上的数据。
-- DELETE FROM web_link_code WHERE expires_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 DAY);
-- DELETE FROM web_session WHERE expires_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL 30 DAY);
