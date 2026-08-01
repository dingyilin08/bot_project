-- GM 操作审计（永久管理员与图片模式保存在本地 gm_state.yaml）。
CREATE TABLE IF NOT EXISTS gm_operation_log (
  id BIGINT NOT NULL AUTO_INCREMENT,
  request_id VARCHAR(80) NOT NULL,
  operator_uid INT NOT NULL,
  target_uid INT NOT NULL,
  operation_type VARCHAR(24) NOT NULL,
  item_id INT NULL,
  amount BIGINT NOT NULL,
  balance_before BIGINT NOT NULL,
  balance_after BIGINT NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'SUCCESS',
  result_json JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_gm_operation_request (request_id),
  KEY idx_gm_operator_time (operator_uid, created_at),
  KEY idx_gm_target_time (target_uid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
