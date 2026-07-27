-- P0 Boss 天机配置：dungeon_id=0、boss_name='*' 是默认值，可按副本和 Boss 名称覆盖。
CREATE TABLE IF NOT EXISTS data_boss_mechanic (
    id BIGINT NOT NULL AUTO_INCREMENT, dungeon_id INT NOT NULL DEFAULT 0, boss_name VARCHAR(64) NOT NULL DEFAULT '*',
    trigger_stage VARCHAR(16) NOT NULL, trigger_threshold DECIMAL(4,2) NOT NULL,
    mechanic_name VARCHAR(64) NOT NULL, counter_element VARCHAR(16) NOT NULL, counter_name VARCHAR(32) NOT NULL,
    fail_effect VARCHAR(32) NOT NULL, fail_value INT NOT NULL, duration_rounds TINYINT NOT NULL DEFAULT 2,
    break_drop_weight TINYINT NOT NULL DEFAULT 0, PRIMARY KEY (id),
    UNIQUE KEY uk_boss_mechanic (dungeon_id, boss_name, trigger_stage)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO data_boss_mechanic
    (dungeon_id, boss_name, trigger_stage, trigger_threshold, mechanic_name, counter_element, counter_name, fail_effect, fail_value, duration_rounds, break_drop_weight)
VALUES
    (0, '*', 'first', 0.75, '天机·护体', 'METAL', '金行', 'defense_up', 35, 2, 15),
    (0, '*', 'second', 0.40, '天机·蓄力', 'WATER', '水行', 'attack_up', 30, 2, 20)
ON DUPLICATE KEY UPDATE mechanic_name = VALUES(mechanic_name), counter_element = VALUES(counter_element),
    counter_name = VALUES(counter_name), fail_effect = VALUES(fail_effect), fail_value = VALUES(fail_value),
    duration_rounds = VALUES(duration_rounds), break_drop_weight = VALUES(break_drop_weight);
