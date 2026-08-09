-- P10 副本次数与限购经济保护（MySQL 5.7，可重复执行）

CREATE TABLE IF NOT EXISTS user_dungeon_daily_usage (
    uid INT NOT NULL,
    stat_date DATE NOT NULL,
    used_count INT NOT NULL DEFAULT 0,
    attempt_limit INT NOT NULL DEFAULT 20,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (uid, stat_date),
    KEY idx_dungeon_usage_date (stat_date, used_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_副本每日累计挑战与扫荡次数';

-- 兼容运行时曾创建的旧表结构。
SET @has_attempt_limit=(
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA=DATABASE()
      AND TABLE_NAME='user_dungeon_daily_usage'
      AND COLUMN_NAME='attempt_limit'
);
SET @add_attempt_limit_sql=IF(
    @has_attempt_limit=0,
    'ALTER TABLE user_dungeon_daily_usage ADD COLUMN attempt_limit INT NOT NULL DEFAULT 20 AFTER used_count',
    'SELECT 1'
);
PREPARE add_attempt_limit_stmt FROM @add_attempt_limit_sql;
EXECUTE add_attempt_limit_stmt;
DEALLOCATE PREPARE add_attempt_limit_stmt;

-- 兼容当天已发生的行为：旧剩余次数与扫荡流水取较大值；超过20次的玩家当天直接封顶。
INSERT INTO user_dungeon_daily_usage(uid,stat_date,used_count,attempt_limit)
SELECT z.id,CURDATE(),GREATEST(
    CASE
        WHEN z.daily_dungeon_reset_time=CURDATE()
        THEN GREATEST(0,20-LEAST(20,COALESCE(z.dungeon_num,20)))
        ELSE 0
    END,
    COALESCE(s.sweep_count,0)
),20
FROM user_zt z
LEFT JOIN (
    SELECT uid,COUNT(*) AS sweep_count
    FROM user_dungeon_sweep_log
    WHERE created_at>=CURDATE() AND created_at<CURDATE()+INTERVAL 1 DAY
    GROUP BY uid
) s ON s.uid=z.id
ON DUPLICATE KEY UPDATE used_count=GREATEST(used_count,VALUES(used_count));

UPDATE user_zt z
JOIN user_dungeon_daily_usage u ON u.uid=z.id AND u.stat_date=CURDATE()
SET z.dungeon_num=GREATEST(0,u.attempt_limit-u.used_count),
    z.daily_dungeon_reset_time=CURDATE();

-- 扫荡券恢复每日限购10张；体力药每日4瓶、正常供给。
UPDATE data_shop_item SET daily_limit=10 WHERE item_id=211;
UPDATE data_shop_item SET enabled=1,daily_limit=4 WHERE item_id=209;

-- 下架所有商城限购便利道具订单；出售单退物，收购单退还预存灵石。
INSERT INTO user_item(uid,item_id,item_num)
SELECT owner_uid,item_id,SUM(remaining_quantity)
FROM user_market_order
WHERE status='OPEN' AND order_type='SELL'
  AND item_id IN (208,209,210,211,212)
GROUP BY owner_uid,item_id
ON DUPLICATE KEY UPDATE item_num=item_num+VALUES(item_num);

UPDATE user_zt z
JOIN (
    SELECT owner_uid,SUM(reserved_lingshi) AS refund
    FROM user_market_order
    WHERE status='OPEN' AND order_type='BUY'
      AND item_id IN (208,209,210,211,212)
    GROUP BY owner_uid
) r ON r.owner_uid=z.id
SET z.lingshi=z.lingshi+r.refund;

UPDATE user_market_order
SET remaining_quantity=0,reserved_lingshi=0,status='CANCELLED',closed_at=UTC_TIMESTAMP()
WHERE status='OPEN' AND item_id IN (208,209,210,211,212);
