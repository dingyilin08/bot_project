-- 依据 2026-08-04 最近 1813 场单人副本战斗校准怪物难度。
-- 普通怪近期胜率为 95%~100%，保持 1~50 级模板差异；Boss 低档与50级胜率仅约45%，定向下调。

-- Boss 的生命、攻击、防御改为平滑档位，避免技能暴击造成秒杀或防御过高导致刮痧。
UPDATE data_monster m
JOIN data_dungeon d ON d.id = m.dungeon_id
SET m.hp_ratio = CASE d.min_level
        WHEN 1 THEN 2.10
        WHEN 10 THEN 2.30
        WHEN 20 THEN 2.50
        WHEN 30 THEN 2.70
        WHEN 40 THEN 2.80
        WHEN 50 THEN 2.90
        WHEN 60 THEN 3.00
        WHEN 70 THEN 3.10
        WHEN 80 THEN 3.20
        WHEN 90 THEN 3.30
        ELSE m.hp_ratio
    END,
    m.atk_ratio = CASE d.min_level
        WHEN 1 THEN 1.35
        WHEN 10 THEN 1.40
        WHEN 20 THEN 1.45
        WHEN 30 THEN 1.50
        WHEN 40 THEN 1.50
        WHEN 50 THEN 1.55
        WHEN 60 THEN 1.55
        WHEN 70 THEN 1.60
        WHEN 80 THEN 1.65
        WHEN 90 THEN 1.70
        ELSE m.atk_ratio
    END,
    m.def_ratio = CASE d.min_level
        WHEN 1 THEN 1.20
        WHEN 10 THEN 1.20
        WHEN 20 THEN 1.20
        WHEN 30 THEN 1.25
        WHEN 40 THEN 1.25
        WHEN 50 THEN 1.30
        WHEN 60 THEN 1.30
        WHEN 70 THEN 1.35
        WHEN 80 THEN 1.40
        WHEN 90 THEN 1.45
        ELSE m.def_ratio
    END,
    m.spd_ratio = LEAST(m.spd_ratio, 1.50),
    m.crit_ratio = LEAST(m.crit_ratio, 1.30),
    m.crit_dmg_ratio = LEAST(m.crit_dmg_ratio, 1.25),
    m.dodge_ratio = LEAST(m.dodge_ratio, 1.25),
    m.hit_ratio = LEAST(m.hit_ratio, 1.40)
WHERE m.type = 'boss';

-- 60级以后暂无有效实战样本，旧模板倍率与旧基础属性叠加会再次形成断层。
-- 保留各世界相对强弱，只限制普通怪的极端上限。
UPDATE data_monster m
JOIN data_dungeon d ON d.id = m.dungeon_id
SET m.hp_ratio = LEAST(m.hp_ratio, 1.55),
    m.atk_ratio = LEAST(m.atk_ratio, 1.50),
    m.def_ratio = LEAST(m.def_ratio, 1.45),
    m.spd_ratio = LEAST(m.spd_ratio, 1.45),
    m.crit_ratio = LEAST(m.crit_ratio, 1.35),
    m.crit_dmg_ratio = LEAST(m.crit_dmg_ratio, 1.30),
    m.dodge_ratio = LEAST(m.dodge_ratio, 1.40),
    m.hit_ratio = LEAST(m.hit_ratio, 1.60)
WHERE m.type = 'normal'
  AND d.min_level >= 60;
