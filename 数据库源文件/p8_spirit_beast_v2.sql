-- 《诸天灵契》V2 完整迁移（MySQL 5.7）
-- 前置：p1_spirit_beast.sql、p7_role_spirit_beast.sql。执行前请备份。

CREATE TABLE IF NOT EXISTS spirit_beast_template (
    id INT NOT NULL, name VARCHAR(32) NOT NULL, world VARCHAR(24) NOT NULL,
    quality VARCHAR(8) NOT NULL, role_code VARCHAR(16) NOT NULL, element VARCHAR(8) NOT NULL,
    talent_code VARCHAR(32) NOT NULL, talent_name VARCHAR(40) NOT NULL,
    description VARCHAR(255) NOT NULL, enabled TINYINT NOT NULL DEFAULT 1,
    PRIMARY KEY (id), UNIQUE KEY uk_beast_v2_name (name), KEY idx_beast_v2_world (world, quality)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO spirit_beast_template
    (id,name,world,quality,role_code,element,talent_code,talent_name,description) VALUES
(1,'赤焰灵狐','诸天通用','灵品','STRIKER','火','BURN_CHASE','焰尾追击','灼烧后弱化追击，每场最多2次。'),
(2,'玄甲龟','诸天通用','灵品','GUARDIAN','土','LOW_HP_SHIELD','玄甲护主','首次低于半血时生成护盾。'),
(3,'青木鹿','诸天通用','灵品','HEALER','木','PERIODIC_HEAL','回春灵息','每三回合回复并减轻持续伤害。'),
(4,'寒翎雀','诸天通用','灵品','DISRUPTOR','水','OPENING_SLOW','霜羽迟滞','开场加速，首次命中降低敌速。'),
(101,'紫晶翼狮','斗气大陆','地品','STRIKER','火','PURPLE_FIRE','紫火震击','强化灼烧目标受到的首次追击。'),
(102,'太虚幼龙','斗气大陆','天品','BREAKER','空','VOID_BREAK','虚空挪移','移除一层护盾并提高破甲。'),
(103,'天妖凰影','斗气大陆','地品','DISRUPTOR','风','PHOENIX_SPEED','凰翼掠空','抢先手并规避一次速度压制。'),
(201,'蚊兽','仙罡星域','玄品','DISRUPTOR','血','DEBUFF_TOUGHNESS','血翅噬灵','目标带减益时追加削韧。'),
(202,'雷蛙','仙罡星域','地品','BREAKER','雷','CAST_BREAK','天雷震魂','首领蓄力时提高破局效率。'),
(203,'望月幼灵','仙罡星域','天品','GUARDIAN','月','MOON_GUARD','古神月守','高血护主，低血转为回复。'),
(301,'狻猊','大荒','地品','BREAKER','雷','THUNDER_BREAK','狻猊雷印','雷行伤害追加削韧。'),
(302,'朱厌','大荒','地品','GUARDIAN','土','MOUNTAIN_BODY','搬山战躯','受击后短暂提高攻防。'),
(303,'九头狮子','大荒','天品','STRIKER','金','WAVE_WILL','九首齐啸','多波战斗保留一次战意。'),
(401,'黑皇道影','北斗星域','天品','DISRUPTOR','阵','FORMATION_HINT','无始阵纹','提示首领机制并降低阵法伤害。'),
(402,'龙马','北斗星域','地品','STRIKER','风','FIRST_STRIKE','星路奔袭','取得先手时追加冲击。'),
(403,'九变神蚕','北斗星域','天品','HEALER','光','COCOON_REBIRTH','神蚕九变','首次濒危时蜕变回复。'),
(501,'噬金虫群','人界灵界','地品','BREAKER','金','ARTIFACT_BREAK','万虫噬器','对护盾、法宝机制额外削韧。'),
(502,'啼魂兽','人界灵界','天品','DISRUPTOR','魂','SOUL_CLEANSE','啼魂镇煞','清除魂系减益并反制阴魂。'),
(503,'豹麟兽','人界灵界','地品','STRIKER','风','EXECUTE_CHASE','豹麟追影','敌方低于三成气血时追击。'),
(601,'镜湖雷隼','沧元界','地品','DISRUPTOR','雷','RESET_CHASE','雷隼掠影','首回合加速，破局后重置追击。'),
(602,'城关玄犀','沧元界','地品','GUARDIAN','土','TEAM_GUARD','城关不退','组队或世界首领中分担高额伤害。'),
(603,'元神梦貘','沧元界','天品','HEALER','魂','THREAT_SIGHT','梦境观敌','显示最高威胁并降低首次元神伤害。')
ON DUPLICATE KEY UPDATE world=VALUES(world),quality=VALUES(quality),role_code=VALUES(role_code),
element=VALUES(element),talent_code=VALUES(talent_code),talent_name=VALUES(talent_name),description=VALUES(description);

CREATE TABLE IF NOT EXISTS spirit_beast_skill (
    id INT NOT NULL, name VARCHAR(40) NOT NULL, category VARCHAR(8) NOT NULL,
    effect_code VARCHAR(32) NOT NULL, effect_value TINYINT NOT NULL,
    cooldown TINYINT NOT NULL, trigger_limit TINYINT NOT NULL, page_cost SMALLINT NOT NULL,
    PRIMARY KEY(id), UNIQUE KEY uk_beast_skill_name(name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT INTO spirit_beast_skill VALUES
(1,'烈焰追袭','攻伐','SKILL_ATTACK',6,2,3,12),(2,'玄灵护障','守御','SKILL_SHIELD',8,3,2,12),
(3,'万木回春','生息','SKILL_HEAL',6,3,2,12),(4,'霜风定势','控场','SKILL_SPEED',6,3,2,12),
(5,'碎阵灵鸣','破阵','SKILL_BREAK',8,3,2,12),(6,'焚脉紫炎','攻伐','SKILL_BURN',8,3,2,24),
(7,'生死轮转','生息','SKILL_EMERGENCY_HEAL',8,99,1,24),(8,'雷印破妄','破阵','SKILL_TOUGHNESS',10,4,2,24),
(9,'阵纹先觉','控场','SKILL_HINT',5,99,1,24),(10,'城关同守','守御','SKILL_TEAM_GUARD',10,99,1,24)
ON DUPLICATE KEY UPDATE category=VALUES(category),effect_code=VALUES(effect_code),effect_value=VALUES(effect_value),
cooldown=VALUES(cooldown),trigger_limit=VALUES(trigger_limit),page_cost=VALUES(page_cost);

CREATE TABLE IF NOT EXISTS user_spirit_beast_v2 (
    id BIGINT NOT NULL AUTO_INCREMENT, uid INT NOT NULL, template_id INT NOT NULL,
    nickname VARCHAR(24) NULL, level TINYINT NOT NULL DEFAULT 1, level_exp INT NOT NULL DEFAULT 0,
    stage TINYINT NOT NULL DEFAULT 0, temperament VARCHAR(8) NOT NULL DEFAULT '沉稳',
    bond_exp INT NOT NULL DEFAULT 0, locked TINYINT NOT NULL DEFAULT 0,
    initial_contract TINYINT NOT NULL DEFAULT 0, obtained_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(id), KEY idx_beast_v2_uid(uid), KEY idx_beast_v2_template(uid,template_id),
    CONSTRAINT fk_beast_v2_template FOREIGN KEY(template_id) REFERENCES spirit_beast_template(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_spirit_beast_aptitude (
    beast_id BIGINT NOT NULL, spirit TINYINT NOT NULL, body TINYINT NOT NULL,
    soul TINYINT NOT NULL, speed TINYINT NOT NULL, highest_total SMALLINT NOT NULL,
    miss_count TINYINT NOT NULL DEFAULT 0, pending_spirit TINYINT NULL, pending_body TINYINT NULL,
    pending_soul TINYINT NULL, pending_speed TINYINT NULL, pending_token CHAR(32) NULL,
    pending_at DATETIME NULL, PRIMARY KEY(beast_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_spirit_beast_bloodline (
    uid INT NOT NULL, template_id INT NOT NULL, nodes TINYINT NOT NULL DEFAULT 0,
    essence INT NOT NULL DEFAULT 0, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY(uid,template_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_spirit_beast_skill_book (
    uid INT NOT NULL, skill_id INT NOT NULL, unlocked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(uid,skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS user_spirit_beast_skill_slot (
    beast_id BIGINT NOT NULL, slot_no TINYINT NOT NULL, skill_id INT NOT NULL,
    priority TINYINT NOT NULL DEFAULT 1, PRIMARY KEY(beast_id,slot_no),
    UNIQUE KEY uk_beast_skill_once(beast_id,skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_spirit_beast_formation (
    uid INT NOT NULL, role_id INT NOT NULL, preset_no TINYINT NOT NULL DEFAULT 1,
    slot_type VARCHAR(8) NOT NULL, beast_id BIGINT NOT NULL, version INT NOT NULL DEFAULT 1,
    PRIMARY KEY(uid,role_id,preset_no,slot_type),
    UNIQUE KEY uk_beast_formation_instance(uid,role_id,preset_no,beast_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS user_spirit_beast_setting (
    uid INT NOT NULL, role_id INT NOT NULL, active_preset TINYINT NOT NULL DEFAULT 1,
    starter_claimed TINYINT NOT NULL DEFAULT 0, free_return_until DATE NULL,
    PRIMARY KEY(uid,role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_spirit_beast_codex (
    uid INT NOT NULL, template_id INT NOT NULL, obtained_count INT NOT NULL DEFAULT 0,
    research_level TINYINT NOT NULL DEFAULT 0, story_chapter TINYINT NOT NULL DEFAULT 0,
    story_choice VARCHAR(64) NULL, highest_aptitude SMALLINT NOT NULL DEFAULT 0,
    memorial TINYINT NOT NULL DEFAULT 0, PRIMARY KEY(uid,template_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS spirit_beast_trace (
    id BIGINT NOT NULL AUTO_INCREMENT, uid INT NOT NULL, trace_date DATE NOT NULL,
    world VARCHAR(24) NOT NULL, clue_type VARCHAR(8) NULL, state VARCHAR(16) NOT NULL DEFAULT 'DISCOVERED',
    seed CHAR(64) NOT NULL, event_text VARCHAR(255) NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(id), UNIQUE KEY uk_beast_trace_day(uid,trace_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_spirit_beast_wallet (
    uid INT NOT NULL, beast_trace INT NOT NULL DEFAULT 0, soul_stone INT NOT NULL DEFAULT 0,
    spirit_essence INT NOT NULL DEFAULT 0, beast_material INT NOT NULL DEFAULT 0,
    wash_dew INT NOT NULL DEFAULT 0, bloodline_essence INT NOT NULL DEFAULT 0,
    skill_page INT NOT NULL DEFAULT 0, story_token INT NOT NULL DEFAULT 0,
    nameplate INT NOT NULL DEFAULT 0, soul_fragment INT NOT NULL DEFAULT 0,
    PRIMARY KEY(uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS user_spirit_beast_pity (
    uid INT NOT NULL, ten_count TINYINT NOT NULL DEFAULT 0, sixty_count TINYINT NOT NULL DEFAULT 0,
    total_identify INT NOT NULL DEFAULT 0, PRIMARY KEY(uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS spirit_beast_pending_choice (
    uid INT NOT NULL, choice_type VARCHAR(16) NOT NULL, beast_id BIGINT NULL,
    template_id INT NULL, payload_json JSON NOT NULL, token CHAR(32) NOT NULL,
    expires_at DATETIME NOT NULL, PRIMARY KEY(uid,choice_type), UNIQUE KEY uk_beast_pending_token(token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS spirit_beast_reward_ledger (
    id BIGINT NOT NULL AUTO_INCREMENT, uid INT NOT NULL, business_key VARCHAR(96) NOT NULL,
    action_type VARCHAR(32) NOT NULL, payload_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(id),
    UNIQUE KEY uk_beast_reward_business(uid,business_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS spirit_beast_dispatch (
    id BIGINT NOT NULL AUTO_INCREMENT, uid INT NOT NULL, beast_id BIGINT NOT NULL,
    dispatch_type VARCHAR(8) NOT NULL, started_at DATETIME NOT NULL, ends_at DATETIME NOT NULL,
    reward_json JSON NOT NULL, state VARCHAR(12) NOT NULL DEFAULT 'ACTIVE',
    PRIMARY KEY(id), KEY idx_beast_dispatch(beast_id,state), KEY idx_dispatch_uid(uid,state)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS spirit_beast_daily_activity (
    uid INT NOT NULL, activity_date DATE NOT NULL, cared TINYINT NOT NULL DEFAULT 0,
    pve_bond_count TINYINT NOT NULL DEFAULT 0, interaction_type VARCHAR(8) NULL,
    interaction_streak TINYINT NOT NULL DEFAULT 0, PRIMARY KEY(uid,activity_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS spirit_beast_weekly_journal (
    uid INT NOT NULL, week_key VARCHAR(10) NOT NULL, pve_count INT NOT NULL DEFAULT 0,
    care_count INT NOT NULL DEFAULT 0, dispatch_count INT NOT NULL DEFAULT 0,
    claimed TINYINT NOT NULL DEFAULT 0, PRIMARY KEY(uid,week_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS spirit_beast_realm_log (
    uid INT NOT NULL, week_key VARCHAR(10) NOT NULL, attempt_no TINYINT NOT NULL,
    world VARCHAR(24) NOT NULL, route VARCHAR(8) NOT NULL, won TINYINT NOT NULL,
    reward_json JSON NOT NULL, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(uid,week_key,attempt_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS spirit_beast_return_log (
    uid INT NOT NULL, week_key VARCHAR(10) NOT NULL, return_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY(uid,week_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sect_spirit_beast_guardian (
    sect_id INT NOT NULL, week_key VARCHAR(10) NOT NULL, level INT NOT NULL DEFAULT 1,
    supply INT NOT NULL DEFAULT 0, PRIMARY KEY(sect_id,week_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS sect_spirit_beast_supply (
    sect_id INT NOT NULL, uid INT NOT NULL, week_key VARCHAR(10) NOT NULL,
    supplied INT NOT NULL DEFAULT 0, claimed TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY(sect_id,uid,week_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 老灵兽原编号迁入V2，四维资质不降低原资质，羁绊与获取时间守恒。
INSERT IGNORE INTO user_spirit_beast_v2
    (id,uid,template_id,level,level_exp,stage,temperament,bond_exp,initial_contract,obtained_at)
SELECT id,uid,beast_id,1,0,0,
       CASE WHEN temperament='狡黠' THEN '机敏' ELSE temperament END,
       bond_exp,1,obtained_at
FROM user_spirit_beast;
INSERT IGNORE INTO user_spirit_beast_aptitude
    (beast_id,spirit,body,soul,speed,highest_total)
SELECT id,aptitude,aptitude,aptitude,aptitude,aptitude*4 FROM user_spirit_beast;
INSERT INTO user_spirit_beast_codex
    (uid,template_id,obtained_count,research_level,highest_aptitude,memorial)
SELECT uid,beast_id,COUNT(*),0,MAX(aptitude*4),1 FROM user_spirit_beast GROUP BY uid,beast_id
ON DUPLICATE KEY UPDATE obtained_count=GREATEST(obtained_count,VALUES(obtained_count)),
highest_aptitude=GREATEST(highest_aptitude,VALUES(highest_aptitude)),memorial=1;
INSERT IGNORE INTO user_spirit_beast_formation(uid,role_id,preset_no,slot_type,beast_id)
SELECT uid,equipped_role_id,1,'主契',id FROM user_spirit_beast WHERE equipped_role_id IS NOT NULL;
INSERT INTO user_spirit_beast_setting(uid,role_id,starter_claimed,free_return_until)
SELECT uid,id,IF(EXISTS(SELECT 1 FROM user_spirit_beast_v2 b WHERE b.uid=user_role.uid),1,0),DATE('2026-08-15')
FROM user_role
ON DUPLICATE KEY UPDATE free_return_until=GREATEST(COALESCE(free_return_until,CURDATE()),VALUES(free_return_until));
INSERT IGNORE INTO user_spirit_beast_wallet(uid) SELECT id FROM user_zt;
INSERT IGNORE INTO user_spirit_beast_pity(uid) SELECT id FROM user_zt;

-- 基础兽材进入普通背包目录，可由坊市规则作为基础材料交易；其他资源均绑定。
INSERT INTO data_item(id,name,type,`desc`,access) VALUES
(3200,'基础兽材',2,'灵兽突破所需的通用兽材，可从秘境、派遣与深渊获得。','万灵秘境、派遣、深渊')
ON DUPLICATE KEY UPDATE name=VALUES(name),type=VALUES(type),`desc`=VALUES(`desc`),access=VALUES(access);
-- 若曾短暂运行过仅钱包版本，将存量兽材一次性搬入可交易背包；重复执行不会重复增加。
INSERT INTO user_item(uid,item_id,item_num)
SELECT uid,3200,beast_material FROM user_spirit_beast_wallet WHERE beast_material>0
ON DUPLICATE KEY UPDATE item_num=item_num+VALUES(item_num);
UPDATE user_spirit_beast_wallet SET beast_material=0 WHERE beast_material<>0;

-- 将 AUTO_INCREMENT 推进到旧编号之后；后续新实例不会与迁移ID冲突。
SET @next_beast_id = (SELECT GREATEST(1000,COALESCE(MAX(id),0)+1) FROM user_spirit_beast_v2);
SET @auto_sql = CONCAT('ALTER TABLE user_spirit_beast_v2 AUTO_INCREMENT=',@next_beast_id);
PREPARE beast_auto_stmt FROM @auto_sql; EXECUTE beast_auto_stmt; DEALLOCATE PREPARE beast_auto_stmt;
