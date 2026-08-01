-- P0 六世界破境丹与丹方目录（MySQL 5.7）
-- 当前悟道进阶在 Lv.10/20/30/40/50/60/70/80/90 强制消耗下一境界破境丹。
-- 本迁移把既有 data_item 153-206 的 54 种破境丹接入药园炼丹系统。
-- 依赖：p0_yaoyuan_schema_and_catalog.sql 已执行。
-- 保留 ID：data_pill/data_recipe 3001-3509。

SET NAMES utf8mb4;

DROP TEMPORARY TABLE IF EXISTS tmp_breakthrough_recipe;
CREATE TEMPORARY TABLE tmp_breakthrough_recipe (
    pill_id INT NOT NULL,
    item_id INT NOT NULL,
    pill_name VARCHAR(50) NOT NULL,
    world VARCHAR(20) NOT NULL,
    ingredients VARCHAR(255) NOT NULL,
    need_num INT NOT NULL,
    cost INT NOT NULL,
    PRIMARY KEY (pill_id),
    UNIQUE KEY uk_item_id (item_id),
    UNIQUE KEY uk_pill_name (pill_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO tmp_breakthrough_recipe
    (pill_id, item_id, pill_name, world, ingredients, need_num, cost)
VALUES
-- 斗破苍穹：寒火调和起步，最终以菩提道韵和九彩丹灵合炼帝丹。
(3001, 153, '[穹]斗师破境丹', '斗破苍穹', '1001|1002', 6, 700),
(3002, 154, '[穹]大斗师破境丹', '斗破苍穹', '1002|1003', 6, 1200),
(3003, 155, '[穹]斗灵破境丹', '斗破苍穹', '1003|1004', 5, 2000),
(3004, 156, '[穹]斗王破境丹', '斗破苍穹', '1005|1006', 5, 3500),
(3005, 157, '[穹]斗皇破境丹', '斗破苍穹', '1004|1006|1007', 4, 5500),
(3006, 158, '[穹]斗宗破境丹', '斗破苍穹', '1005|1007', 4, 8500),
(3007, 159, '[穹]斗尊破境丹', '斗破苍穹', '1006|1008', 3, 13000),
(3008, 160, '[穹]斗圣破境丹', '斗破苍穹', '1007|1008', 3, 19000),
(3009, 161, '[穹]斗帝破境丹', '斗破苍穹', '1005|1006|1007|1008', 2, 30000),

-- 仙逆：由凝气入道，逐步融入轮回、朱雀、罗天、古神和踏天道韵。
(3101, 162, '[逆]筑基破境丹', '仙逆', '1101|1102', 6, 700),
(3102, 163, '[逆]结丹破境丹', '仙逆', '1101|1103', 6, 1200),
(3103, 164, '[逆]元婴破境丹', '仙逆', '1103|1104', 5, 2000),
(3104, 165, '[逆]化神破境丹', '仙逆', '1104|1105', 5, 3500),
(3105, 166, '[逆]婴变破境丹', '仙逆', '1105|1106', 4, 5500),
(3106, 167, '[逆]问鼎破境丹', '仙逆', '1103|1106|1107', 4, 8500),
(3107, 168, '[逆]阴虚破境丹', '仙逆', '1105|1107', 3, 13000),
(3108, 169, '[逆]阳实破境丹', '仙逆', '1106|1107|1108', 3, 19000),
(3109, 170, '[逆]踏天破境丹', '仙逆', '1105|1106|1107|1108', 2, 30000),

-- 凡人修仙传：低阶丹术重药性配伍，高阶以九曲灵参和玄天仙藤为君药。
(3201, 171, '[凡]结丹破境丹', '凡人修仙传', '1201|1202', 6, 700),
(3202, 172, '[凡]元婴破境丹', '凡人修仙传', '1202|1203', 6, 1200),
(3203, 173, '[凡]化神破境丹', '凡人修仙传', '1203|1204|1205', 5, 2000),
(3204, 174, '[凡]炼虚破境丹', '凡人修仙传', '1205|1206', 5, 3500),
(3205, 175, '[凡]合体破境丹', '凡人修仙传', '1204|1206|1207', 4, 5500),
(3206, 176, '[凡]大乘破境丹', '凡人修仙传', '1205|1207', 4, 8500),
(3207, 177, '[凡]真仙破境丹', '凡人修仙传', '1206|1208', 3, 13000),
(3208, 178, '[凡]大罗破境丹', '凡人修仙传', '1207|1208', 3, 19000),
(3209, 179, '[凡]道祖破境丹', '凡人修仙传', '1205|1206|1207|1208', 2, 30000),

-- 完美世界：以大荒宝药搬血筑基，后续引神火、奇药与世界树生命精气入丹。
(3301, 180, '[界]洞天破境丹', '完美世界', '1301|1302', 6, 700),
(3302, 181, '[界]化灵破境丹', '完美世界', '1302|1303', 6, 1200),
(3303, 182, '[界]铭纹破境丹', '完美世界', '1303|1304', 5, 2000),
(3304, 183, '[界]列阵破境丹', '完美世界', '1304|1305', 5, 3500),
(3305, 184, '[界]尊者破境丹', '完美世界', '1305|1306', 4, 5500),
(3306, 185, '[界]神火破境丹', '完美世界', '1304|1306|1307', 4, 8500),
(3307, 186, '[界]真一破境丹', '完美世界', '1305|1307', 3, 13000),
(3308, 187, '[界]天神破境丹', '完美世界', '1306|1307|1308', 3, 19000),
(3309, 188, '[界]至尊破境丹', '完美世界', '1305|1306|1307|1308', 2, 30000),

-- 遮天：依轮海至仙台的修行脉络配伍，终阶汇聚悟道茶与不死神药精粹。
(3401, 189, '[天]命泉破境丹', '遮天', '1401|1402', 6, 700),
(3402, 190, '[天]神桥破境丹', '遮天', '1402|1403', 6, 1200),
(3403, 191, '[天]彼岸破境丹', '遮天', '1403|1404', 5, 2000),
(3404, 192, '[天]道宫破境丹', '遮天', '1404|1405', 5, 3500),
(3405, 193, '[天]四极破境丹', '遮天', '1405|1406', 4, 5500),
(3406, 194, '[天]化龙破境丹', '遮天', '1404|1406|1407', 4, 8500),
(3407, 195, '[天]仙台破境丹', '遮天', '1405|1407', 3, 13000),
(3408, 196, '[天]圣人破境丹', '遮天', '1406|1407|1408', 3, 19000),
(3409, 197, '[天]大帝破境丹', '遮天', '1405|1406|1407|1408', 2, 30000),

-- 沧元图：从洗髓筑基到心魂、时空并炼，形成神魔体系的九阶丹路。
(3501, 198, '[沧]内炼破境丹', '沧元图', '1501|1502', 6, 700),
(3502, 199, '[沧]洗髓破境丹', '沧元图', '1502|1503', 6, 1200),
(3503, 200, '[沧]脱胎破境丹', '沧元图', '1503|1504', 5, 2000),
(3504, 201, '[沧]无漏破境丹', '沧元图', '1504|1505', 5, 3500),
(3505, 202, '[沧]丹云破境丹', '沧元图', '1505|1506', 4, 5500),
(3506, 203, '[沧]不灭破境丹', '沧元图', '1504|1506|1507', 4, 8500),
(3507, 204, '[沧]大日破境丹', '沧元图', '1505|1507', 3, 13000),
(3508, 205, '[沧]暗星破境丹', '沧元图', '1506|1507|1508', 3, 19000),
(3509, 206, '[沧]无间破境丹', '沧元图', '1505|1506|1507|1508', 2, 30000);

START TRANSACTION;

INSERT INTO data_pill
    (id, name, description, effect_type, effect_value, is_percent, max_use, category, world, item_id)
SELECT c.pill_id, c.pill_name,
       CONCAT(i.`desc`, '；仅在悟道进阶时自动消耗，不可直接服用。'),
       'breakthrough', '1', 0, 0, 2, c.world, c.item_id
FROM tmp_breakthrough_recipe c
JOIN data_item i ON i.id = c.item_id AND i.name = c.pill_name
ON DUPLICATE KEY UPDATE
    name = VALUES(name), description = VALUES(description),
    effect_type = VALUES(effect_type), effect_value = VALUES(effect_value),
    is_percent = VALUES(is_percent), max_use = VALUES(max_use),
    category = VALUES(category), world = VALUES(world), item_id = VALUES(item_id);

INSERT INTO data_recipe
    (id, name, pill_id, ingredients, need_num, cost, category, world)
SELECT pill_id, pill_name, pill_id, ingredients, need_num, cost, 2, world
FROM tmp_breakthrough_recipe
ON DUPLICATE KEY UPDATE
    name = VALUES(name), pill_id = VALUES(pill_id),
    ingredients = VALUES(ingredients), need_num = VALUES(need_num),
    cost = VALUES(cost), category = VALUES(category), world = VALUES(world);

UPDATE data_item i
JOIN tmp_breakthrough_recipe c ON c.item_id = i.id AND c.pill_name = i.name
SET i.type = 4,
    i.access = CONCAT('挑战', c.world, '世界副本概率掉落、', c.world, '药园炼丹');

COMMIT;

-- 正常结果：六个世界各 9 种破境丹/丹方，总数均为 54，孤儿数为 0。
SELECT world, COUNT(*) AS breakthrough_pill_count
FROM data_pill
WHERE id BETWEEN 3001 AND 3509 AND MOD(id, 100) BETWEEN 1 AND 9
GROUP BY world ORDER BY world;

SELECT world, COUNT(*) AS breakthrough_recipe_count
FROM data_recipe
WHERE id BETWEEN 3001 AND 3509 AND MOD(id, 100) BETWEEN 1 AND 9
GROUP BY world ORDER BY world;

SELECT COUNT(*) AS missing_item_mapping
FROM data_pill p LEFT JOIN data_item i ON i.id = p.item_id AND i.name = p.name
WHERE p.id BETWEEN 3001 AND 3509 AND MOD(p.id, 100) BETWEEN 1 AND 9 AND i.id IS NULL;

DROP TEMPORARY TABLE IF EXISTS tmp_breakthrough_recipe;
