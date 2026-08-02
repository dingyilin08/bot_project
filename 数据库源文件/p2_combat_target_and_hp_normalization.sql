-- 兼容旧版技能配置：0 与 1 均表示自身，2 表示敌方。
UPDATE data_skill
SET buff_target = 1
WHERE buff_target = 0;

-- 同等级 Boss 使用统一生命倍率；波次与跨界加成仍由战斗公式叠加。
UPDATE data_monster m
JOIN data_dungeon d ON d.id = m.dungeon_id
SET m.hp_ratio = CASE d.min_level
    WHEN 1 THEN 2.50
    WHEN 10 THEN 2.80
    WHEN 20 THEN 3.20
    WHEN 30 THEN 3.50
    WHEN 40 THEN 3.80
    WHEN 50 THEN 4.20
    WHEN 60 THEN 4.50
    WHEN 70 THEN 4.80
    WHEN 80 THEN 5.00
    WHEN 90 THEN 5.50
    ELSE m.hp_ratio
END
WHERE m.type = 'boss';
