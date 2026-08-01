-- P0 药园炼丹基础表与首发目录（MySQL 5.7）
-- 适用世界：斗破苍穹、仙逆、凡人修仙传、完美世界、遮天、沧元图
-- 数据规模：48 种药材、48 种种子、24 种丹药、24 张丹方。
--
-- 命名原则：原著明确出现的名称优先使用；其余名称依据各作品的地点、境界、
-- 修炼体系与标志性意象作游戏化衍生，不宣称为原著中的正式丹方。
--
-- 保留 ID：
--   data_seed/data_herb  1001-1508
--   data_recipe/data_pill 2001-2504
--   data_item 药材 11001-11508，丹药 12001-12504
-- 导入前请确认这些保留 ID 未被自定义数据占用。

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS data_seed (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    cl_name VARCHAR(50) NOT NULL,
    cl_id INT NOT NULL,
    price INT NOT NULL,
    tier TINYINT NOT NULL DEFAULT 1,
    world VARCHAR(20) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_name (name),
    KEY idx_world_tier (world, tier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_种子表';

CREATE TABLE IF NOT EXISTS data_herb (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(255) NULL,
    sell_price INT NOT NULL DEFAULT 0,
    tier TINYINT NOT NULL DEFAULT 1,
    world VARCHAR(20) NULL,
    item_id INT NULL DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_name (name),
    KEY idx_world_tier (world, tier)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_药材表';

CREATE TABLE IF NOT EXISTS data_recipe (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    pill_id INT NOT NULL,
    ingredients VARCHAR(255) NOT NULL,
    need_num INT NOT NULL DEFAULT 10,
    cost INT NOT NULL DEFAULT 200,
    category TINYINT NOT NULL DEFAULT 1,
    world VARCHAR(20) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_name_world (name, world),
    KEY idx_world_category (world, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_丹方表';

CREATE TABLE IF NOT EXISTS data_pill (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    description VARCHAR(255) NULL,
    effect_type VARCHAR(50) NOT NULL,
    effect_value VARCHAR(50) NOT NULL,
    is_percent TINYINT NOT NULL DEFAULT 0,
    max_use INT NOT NULL DEFAULT 1000,
    category TINYINT NOT NULL DEFAULT 1,
    world VARCHAR(20) NULL,
    item_id INT NULL DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_name (name),
    KEY idx_world_category (world, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_丹药表';

CREATE TABLE IF NOT EXISTS user_yaotian (
    id INT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    yt_1 JSON NULL, yt_2 JSON NULL, yt_3 JSON NULL, yt_4 JSON NULL,
    yt_5 JSON NULL, yt_6 JSON NULL, yt_7 JSON NULL, yt_8 JSON NULL,
    yt_9 JSON NULL, yt_10 JSON NULL, yt_11 JSON NULL, yt_12 JSON NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_uid (uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_药田表';

CREATE TABLE IF NOT EXISTS user_danlu (
    id INT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    dl_1 JSON NULL, dl_2 JSON NULL, dl_3 JSON NULL,
    dl_4 JSON NULL, dl_5 JSON NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_uid (uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_丹炉表';

CREATE TABLE IF NOT EXISTS user_seed_bag (
    id INT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    zz_id INT NOT NULL,
    zz_num INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_uid_seed (uid, zz_id),
    KEY idx_uid (uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_种子背包';

CREATE TABLE IF NOT EXISTS user_liandan_fire_daily (
    id INT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    stat_date DATE NOT NULL,
    help_used_times INT NOT NULL DEFAULT 0,
    be_helped_times INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_uid_date (uid, stat_date),
    KEY idx_date (stat_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_炼丹添火日统计';

CREATE TABLE IF NOT EXISTS user_liandan_fire_log (
    id BIGINT NOT NULL AUTO_INCREMENT,
    helper_uid INT NOT NULL,
    target_uid INT NOT NULL,
    furnace_no TINYINT NOT NULL,
    batch_ts INT NOT NULL,
    reduce_seconds INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_once (helper_uid, target_uid, furnace_no, batch_ts),
    KEY idx_target_created (target_uid, created_at),
    KEY idx_helper_created (helper_uid, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_炼丹添火记录';

CREATE TABLE IF NOT EXISTS user_alchemy_mastery (
    id BIGINT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    recipe_name VARCHAR(64) NOT NULL,
    mastery INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_alchemy_mastery (uid, recipe_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_丹方熟练度';

CREATE TABLE IF NOT EXISTS user_pill_tolerance (
    id BIGINT NOT NULL AUTO_INCREMENT,
    uid INT NOT NULL,
    pill_name VARCHAR(64) NOT NULL,
    use_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pill_tolerance (uid, pill_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_丹药耐药记录';

-- 兼容曾按早期设计文档创建、但缺少世界与物品映射字段的数据库。
SET @ddl = IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'data_seed' AND COLUMN_NAME = 'world') = 0,
    'ALTER TABLE data_seed ADD COLUMN world VARCHAR(20) NULL',
    'SELECT 1'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 早期方案把 effect_value 定义为 DECIMAL，无法保存多属性的逗号分隔数值。
ALTER TABLE data_pill
    MODIFY COLUMN effect_type VARCHAR(50) NOT NULL,
    MODIFY COLUMN effect_value VARCHAR(50) NOT NULL;

SET @ddl = IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'data_herb' AND COLUMN_NAME = 'tier') = 0,
    'ALTER TABLE data_herb ADD COLUMN tier TINYINT NOT NULL DEFAULT 1',
    'SELECT 1'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'data_herb' AND COLUMN_NAME = 'world') = 0,
    'ALTER TABLE data_herb ADD COLUMN world VARCHAR(20) NULL',
    'SELECT 1'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'data_herb' AND COLUMN_NAME = 'item_id') = 0,
    'ALTER TABLE data_herb ADD COLUMN item_id INT NULL DEFAULT NULL',
    'SELECT 1'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'data_recipe' AND COLUMN_NAME = 'world') = 0,
    'ALTER TABLE data_recipe ADD COLUMN world VARCHAR(20) NULL',
    'SELECT 1'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'data_pill' AND COLUMN_NAME = 'world') = 0,
    'ALTER TABLE data_pill ADD COLUMN world VARCHAR(20) NULL',
    'SELECT 1'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'data_pill' AND COLUMN_NAME = 'item_id') = 0,
    'ALTER TABLE data_pill ADD COLUMN item_id INT NULL DEFAULT NULL',
    'SELECT 1'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
    (SELECT COUNT(*) FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_role' AND COLUMN_NAME = 'pill_usage') = 0,
    'ALTER TABLE user_role ADD COLUMN pill_usage JSON NULL DEFAULT NULL COMMENT ''丹药使用计数''',
    'SELECT 1'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

START TRANSACTION;

-- 药材：每世界四个品阶各两种。item_id 对应通用物品表 data_item.id。
INSERT INTO data_herb
    (id, name, description, sell_price, tier, world, item_id)
VALUES
-- 斗破苍穹：冰灵焰草、血莲精等取自原著炼药语汇，高阶条目作游戏化衍生。
(1001, '冰灵焰草', '寒火并生的奇草，是炼制血莲类丹药的重要药材。', 60, 1, '斗破苍穹', 11001),
(1002, '血莲精', '血色莲花凝成的药精，药性温烈，适合恢复气血。', 80, 1, '斗破苍穹', 11002),
(1003, '青木仙藤', '蕴含旺盛木属性生机的藤类药材。', 180, 2, '斗破苍穹', 11003),
(1004, '蛇涎果', '魔兽山脉中受蛇类气息滋养的灵果。', 220, 2, '斗破苍穹', 11004),
(1005, '龙须冰火果', '冰火两性共存的珍果，药力猛烈而均衡。', 600, 3, '斗破苍穹', 11005),
(1006, '地心火芝', '生于地火深处的火属性灵芝。', 800, 3, '斗破苍穹', 11006),
(1007, '菩提古树芽', '承载菩提古树意象的稀世嫩芽，属游戏化衍生药材。', 1800, 4, '斗破苍穹', 11007),
(1008, '九彩丹灵花', '依丹塔与九色丹雷意象衍生的仙品药花。', 2400, 4, '斗破苍穹', 11008),

-- 仙逆：围绕恒岳、朱雀、罗天、踏天与轮回体系设计。
(1101, '凝气苔', '灵气汇聚处生长的基础药苔。', 60, 1, '仙逆', 11101),
(1102, '恒岳灵芽', '恒岳山脉灵气滋养的嫩芽。', 80, 1, '仙逆', 11102),
(1103, '轮回叶', '叶脉如轮，蕴含微弱生死轮回气息。', 180, 2, '仙逆', 11103),
(1104, '天运藤', '依天运宗意象衍生的命数灵藤。', 220, 2, '仙逆', 11104),
(1105, '朱雀翎草', '受朱雀星火意滋养、形似翎羽的灵草。', 600, 3, '仙逆', 11105),
(1106, '罗天星辰果', '吸收罗天星域星辉凝成的灵果。', 800, 3, '仙逆', 11106),
(1107, '太古神根', '依古神体系衍生的仙品根茎，蕴含强横生机。', 1800, 4, '仙逆', 11107),
(1108, '踏天道花', '依踏天境意象衍生的道韵之花。', 2400, 4, '仙逆', 11108),

-- 凡人修仙传：紫猴花、天灵果、玉髓芝等用于筑基丹相关剧情。
(1201, '黄精芝', '低阶修士常用的温养药材。', 60, 1, '凡人修仙传', 11201),
(1202, '清灵草', '药性平和、适合炼制入门丹药的灵草。', 80, 1, '凡人修仙传', 11202),
(1203, '紫猴花', '血色禁地中的珍稀灵花，筑基丹主材之一。', 180, 2, '凡人修仙传', 11203),
(1204, '天灵果', '筑基丹所需的重要灵果。', 220, 2, '凡人修仙传', 11204),
(1205, '玉髓芝', '形如玉髓的灵芝，筑基丹主材之一。', 600, 3, '凡人修仙传', 11205),
(1206, '霓裳草', '会吸引妖兽的奇草，年份越高药性越强。', 800, 3, '凡人修仙传', 11206),
(1207, '九曲灵参', '根形九曲、灵气深厚的罕见灵参。', 1800, 4, '凡人修仙传', 11207),
(1208, '玄天仙藤', '依玄天仙藤意象设置的仙品藤种。', 2400, 4, '凡人修仙传', 11208),

-- 完美世界：围绕大荒、搬血、神火、白龟驮仙与世界树设计。
(1301, '大荒血草', '大荒中常见、可滋养血气的基础宝草。', 60, 1, '完美世界', 11301),
(1302, '石村药果', '石村山林中采集的温补药果。', 80, 1, '完美世界', 11302),
(1303, '碧血草', '草叶碧绿而汁液如血，可用于搬血淬体。', 180, 2, '完美世界', 11303),
(1304, '黄金果', '金霞流转的宝果，蕴含旺盛精气。', 220, 2, '完美世界', 11304),
(1305, '银桃', '晶莹如银的灵桃，果肉蕴含纯净神性。', 600, 3, '完美世界', 11305),
(1306, '神藤花', '神藤孕育的宝花，适合神火境淬炼。', 800, 3, '完美世界', 11306),
(1307, '白龟驮仙果', '依白龟驮仙奇药意象设置的仙品宝果。', 1800, 4, '完美世界', 11307),
(1308, '世界树嫩芽', '世界树新生嫩芽，内蕴浩瀚生命精气。', 2400, 4, '完美世界', 11308),

-- 遮天：围绕轮海、火域、悟道茶与不死神药设计。
(1401, '灵墟草', '灵墟洞天附近生长的基础灵草。', 60, 1, '遮天', 11401),
(1402, '命泉芽', '受命泉精气滋润而萌发的嫩芽。', 80, 1, '遮天', 11402),
(1403, '源石花', '扎根源石裂隙、吸收源气生长的奇花。', 180, 2, '遮天', 11403),
(1404, '火域莲', '在火域高温中盛开的火属性灵莲。', 220, 2, '遮天', 11404),
(1405, '化龙果', '依化龙秘境意象衍生的龙形灵果。', 600, 3, '遮天', 11405),
(1406, '悟道茶芽', '悟道茶树新芽，叶脉天然承载道韵。', 800, 3, '遮天', 11406),
(1407, '九妙神果', '九妙不死药结出的神果，蕴含磅礴生命精气。', 1800, 4, '遮天', 11407),
(1408, '麒麟神药叶', '麒麟不死神药的珍叶，药性温厚而悠长。', 2400, 4, '遮天', 11408),

-- 沧元图：围绕镜湖、元初山、神魔修炼、暗星与心魂设计。
(1501, '镜湖灵草', '东宁府镜湖畔生长的基础灵草。', 60, 1, '沧元图', 11501),
(1502, '元初山灵苔', '元初山石壁上凝聚天地元气的灵苔。', 80, 1, '沧元图', 11502),
(1503, '洗髓草', '适合神魔筑基、洗炼筋骨的药草。', 180, 2, '沧元图', 11503),
(1504, '九玄洞天果', '九玄洞天中孕育的灵果。', 220, 2, '沧元图', 11504),
(1505, '大日金莲', '依大日境意象衍生、流转金辉的灵莲。', 600, 3, '沧元图', 11505),
(1506, '暗星幽兰', '依暗星境意象衍生、吸纳幽暗元气的兰草。', 800, 3, '沧元图', 11506),
(1507, '时空道果', '受时空长河气息浸润而成的仙品道果。', 1800, 4, '沧元图', 11507),
(1508, '心魂本源花', '依心魂一脉衍生的本源之花。', 2400, 4, '沧元图', 11508)
ON DUPLICATE KEY UPDATE
    name = VALUES(name), description = VALUES(description),
    sell_price = VALUES(sell_price), tier = VALUES(tier),
    world = VALUES(world), item_id = VALUES(item_id);

-- 种子与药材一一对应；价格按品阶统一，便于后续平衡调整。
INSERT INTO data_seed (id, name, cl_name, cl_id, price, tier, world)
SELECT id, CONCAT(name, '种子'), name, id,
       CASE tier WHEN 1 THEN IF(MOD(id, 100) = 1, 600, 800)
                 WHEN 2 THEN IF(MOD(id, 100) = 3, 1800, 2200)
                 WHEN 3 THEN IF(MOD(id, 100) = 5, 6000, 8000)
                 ELSE IF(MOD(id, 100) = 7, 18000, 24000) END,
       tier, world
FROM data_herb
WHERE id BETWEEN 1001 AND 1508
  AND MOD(id, 100) BETWEEN 1 AND 8
ON DUPLICATE KEY UPDATE
    name = VALUES(name), cl_name = VALUES(cl_name), cl_id = VALUES(cl_id),
    price = VALUES(price), tier = VALUES(tier), world = VALUES(world);

-- 丹药效果只使用当前 fu_dan() 已支持的属性键。
-- rate 类属性采用 is_percent=1，0.05 表示 +0.05%，0.1 表示 +0.1%。
INSERT INTO data_pill
    (id, name, description, effect_type, effect_value, is_percent, max_use, category, world, item_id)
VALUES
(2001, '回气丹', '斗气大陆常用恢复丹药，永久增加少量法力。', 'fali', '20', 0, 200, 1, '斗破苍穹', 12001),
(2002, '三纹青灵丹', '依原著三纹青灵丹意象设计，兼顾攻击与防御成长。', 'gongji,fangyu', '8,5', 0, 150, 1, '斗破苍穹', 12002),
(2003, '地灵丹', '借地火之力淬炼灵性，永久增加暴击。', 'baoji', '0.05', 1, 80, 2, '斗破苍穹', 12003),
(2004, '菩提丹', '依菩提古树机缘设计的高阶丹药，增加暴击与暴伤。', 'baoji,baoshang', '0.1,0.05', 1, 40, 3, '斗破苍穹', 12004),

(2101, '凝气丹', '凝聚天地灵气，永久增加少量法力。', 'fali', '20', 0, 200, 1, '仙逆', 12101),
(2102, '天离丹', '取原著天离丹之名，游戏中增加攻击与速度。', 'gongji,sudu', '7,3', 0, 150, 1, '仙逆', 12102),
(2103, '问鼎丹', '依问鼎境意象衍生，永久增加命中。', 'mingzhong', '0.05', 1, 80, 2, '仙逆', 12103),
(2104, '涅空丹', '依原著高阶丹药涅空丹意象设计，增加命中与闪避。', 'mingzhong,shanbi', '0.1,0.05', 1, 40, 3, '仙逆', 12104),

(2201, '黄龙丹', '低阶修士常用丹药，永久增加气血。', 'qixue', '30', 0, 200, 1, '凡人修仙传', 12201),
(2202, '筑基丹', '以紫猴花、天灵果等炼成，增加攻击与防御。', 'gongji,fangyu', '6,6', 0, 150, 1, '凡人修仙传', 12202),
(2203, '造化丹', '依造化机缘衍生的高阶丹药，永久增加破防。', 'pofang', '0.05', 1, 80, 2, '凡人修仙传', 12203),
(2204, '九曲灵参丹', '以九曲灵参为主药，增加吸血与命中。', 'xixue,mingzhong', '0.1,0.05', 1, 40, 3, '凡人修仙传', 12204),

(2301, '百草液', '以大荒百草熬炼的药液，永久增加气血。', 'qixue', '30', 0, 200, 1, '完美世界', 12301),
(2302, '搬血宝丹', '强化搬血淬体，永久增加攻击与防御。', 'gongji,fangyu', '8,4', 0, 150, 1, '完美世界', 12302),
(2303, '神火涅槃丹', '依神火境与涅槃意象衍生，永久增加暴伤。', 'baoshang', '0.05', 1, 80, 2, '完美世界', 12303),
(2304, '至尊道丹', '汇聚至尊道韵，永久增加暴击与暴伤。', 'baoji,baoshang', '0.1,0.05', 1, 40, 3, '完美世界', 12304),

(2401, '苦海养元丹', '温养轮海苦海，永久增加气血。', 'qixue', '30', 0, 200, 1, '遮天', 12401),
(2402, '道宫清灵丹', '滋养道宫，永久增加法力与速度。', 'fali,sudu', '15,3', 0, 150, 1, '遮天', 12402),
(2403, '化龙铸体丹', '依化龙秘境意象衍生，永久增加闪避。', 'shanbi', '0.05', 1, 80, 2, '遮天', 12403),
(2404, '九妙悟道丹', '由九妙神果与麒麟神药叶炼成，增加闪避与命中。', 'shanbi,mingzhong', '0.1,0.05', 1, 40, 3, '遮天', 12404),

(2501, '凝神丹', '凝练精神意志，永久增加法力。', 'fali', '20', 0, 200, 1, '沧元图', 12501),
(2502, '洗髓丹', '辅助洗髓筑基，永久增加攻击与防御。', 'gongji,fangyu', '7,5', 0, 150, 1, '沧元图', 12502),
(2503, '大日炼体丹', '依大日境意象衍生，永久增加吸血。', 'xixue', '0.05', 1, 80, 2, '沧元图', 12503),
(2504, '心魂无间丹', '融合心魂与时空意象，永久增加吸血与命中。', 'xixue,mingzhong', '0.1,0.05', 1, 40, 3, '沧元图', 12504)
ON DUPLICATE KEY UPDATE
    name = VALUES(name), description = VALUES(description),
    effect_type = VALUES(effect_type), effect_value = VALUES(effect_value),
    is_percent = VALUES(is_percent), max_use = VALUES(max_use),
    category = VALUES(category), world = VALUES(world), item_id = VALUES(item_id);

-- 每个世界四张丹方依次消耗本世界凡品、良品、精品、仙品药材。
INSERT INTO data_recipe
    (id, name, pill_id, ingredients, need_num, cost, category, world)
VALUES
(2001, '回气丹', 2001, '1001|1002', 6, 400, 1, '斗破苍穹'),
(2002, '三纹青灵丹', 2002, '1003|1004', 5, 1000, 1, '斗破苍穹'),
(2003, '地灵丹', 2003, '1005|1006', 3, 3000, 2, '斗破苍穹'),
(2004, '菩提丹', 2004, '1007|1008', 2, 8000, 3, '斗破苍穹'),

(2101, '凝气丹', 2101, '1101|1102', 6, 400, 1, '仙逆'),
(2102, '天离丹', 2102, '1103|1104', 5, 1000, 1, '仙逆'),
(2103, '问鼎丹', 2103, '1105|1106', 3, 3000, 2, '仙逆'),
(2104, '涅空丹', 2104, '1107|1108', 2, 8000, 3, '仙逆'),

(2201, '黄龙丹', 2201, '1201|1202', 6, 400, 1, '凡人修仙传'),
(2202, '筑基丹', 2202, '1203|1204|1205', 4, 1200, 1, '凡人修仙传'),
(2203, '造化丹', 2203, '1205|1206', 3, 3000, 2, '凡人修仙传'),
(2204, '九曲灵参丹', 2204, '1207|1208', 2, 8000, 3, '凡人修仙传'),

(2301, '百草液', 2301, '1301|1302', 6, 400, 1, '完美世界'),
(2302, '搬血宝丹', 2302, '1303|1304', 5, 1000, 1, '完美世界'),
(2303, '神火涅槃丹', 2303, '1305|1306', 3, 3000, 2, '完美世界'),
(2304, '至尊道丹', 2304, '1307|1308', 2, 8000, 3, '完美世界'),

(2401, '苦海养元丹', 2401, '1401|1402', 6, 400, 1, '遮天'),
(2402, '道宫清灵丹', 2402, '1403|1404', 5, 1000, 1, '遮天'),
(2403, '化龙铸体丹', 2403, '1405|1406', 3, 3000, 2, '遮天'),
(2404, '九妙悟道丹', 2404, '1407|1408', 2, 8000, 3, '遮天'),

(2501, '凝神丹', 2501, '1501|1502', 6, 400, 1, '沧元图'),
(2502, '洗髓丹', 2502, '1503|1504', 5, 1000, 1, '沧元图'),
(2503, '大日炼体丹', 2503, '1505|1506', 3, 3000, 2, '沧元图'),
(2504, '心魂无间丹', 2504, '1507|1508', 2, 8000, 3, '沧元图')
ON DUPLICATE KEY UPDATE
    name = VALUES(name), pill_id = VALUES(pill_id),
    ingredients = VALUES(ingredients), need_num = VALUES(need_num),
    cost = VALUES(cost), category = VALUES(category), world = VALUES(world);

-- 采摘和收丹最终都写入 user_item，因此同步建立通用物品目录映射。
INSERT INTO data_item (id, name, type, `desc`, access)
SELECT item_id, name, 1, description, CONCAT(world, '药园种植采摘')
FROM data_herb
WHERE id BETWEEN 1001 AND 1508
  AND MOD(id, 100) BETWEEN 1 AND 8
ON DUPLICATE KEY UPDATE
    name = VALUES(name), type = VALUES(type),
    `desc` = VALUES(`desc`), access = VALUES(access);

INSERT INTO data_item (id, name, type, `desc`, access)
SELECT item_id, name, 4, description, CONCAT(world, '炼丹产出')
FROM data_pill
WHERE id BETWEEN 2001 AND 2504
  AND MOD(id, 100) BETWEEN 1 AND 4
ON DUPLICATE KEY UPDATE
    name = VALUES(name), type = VALUES(type),
    `desc` = VALUES(`desc`), access = VALUES(access);

COMMIT;

-- 导入后核验：正常结果应为每个世界 8 种种子/药材、4 种丹药/丹方，孤儿数均为 0。
SELECT world, COUNT(*) AS seed_count
FROM data_seed
WHERE id BETWEEN 1001 AND 1508 AND MOD(id, 100) BETWEEN 1 AND 8
GROUP BY world ORDER BY world;

SELECT world, COUNT(*) AS recipe_count
FROM data_recipe
WHERE id BETWEEN 2001 AND 2504 AND MOD(id, 100) BETWEEN 1 AND 4
GROUP BY world ORDER BY world;

SELECT COUNT(*) AS orphan_seed_count
FROM data_seed s LEFT JOIN data_herb h ON h.id = s.cl_id
WHERE s.id BETWEEN 1001 AND 1508 AND MOD(s.id, 100) BETWEEN 1 AND 8 AND h.id IS NULL;

SELECT COUNT(*) AS orphan_recipe_count
FROM data_recipe r LEFT JOIN data_pill p ON p.id = r.pill_id
WHERE r.id BETWEEN 2001 AND 2504 AND MOD(r.id, 100) BETWEEN 1 AND 4 AND p.id IS NULL;
