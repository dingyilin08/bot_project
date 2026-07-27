# -*- coding: utf-8 -*-
"""
波次副本系统 - Markdown版本
- 挑战副本随机生成5个怪物（含1个Boss）
- 共3波，每波5只怪物（第5位固定为Boss）
- 战胜怪物获得经验灵石
- Boss掉落本源材料和技能卷轴
"""

from sql.mysql import *
from Tool.tool_user import *
from func.pd_func import *
from Tool.tool_command import *
import random
import json
import asyncio
import copy
from uuid import NAMESPACE_URL, uuid5

# 导入战斗系统
from Tool.combat_system import (
    CombatManager, CombatEntity, Skill, Buff,
    create_skill_from_db, create_combat_entity
)

# 导入装备系统（用于副本掉落和战斗属性集成）
from Game_main.g7_equip import (
    get_equip_templates_by_dungeon, QUALITY_DROP_RATE,
    calc_role_equip_bonus
)
from Game_main.g4_benyuan import get_role_benyuan_skills_for_battle
from Game_domain.reward_service import MySQLRewardService, RewardEquipment, RewardItem

# ================================
# 配置参数
# ================================

# 每日免费挑战次数
FREE_DAILY_CHALLENGES = 20

# 波次难度递增系数
WAVE_DIFFICULTY_MULTIPLIER = {
    1: 1.0,
    2: 1.1,
    3: 1.15
}

# Boss掉落概率（百分比）
BOSS_DROP_RATE = 30

# 连杀奖励阈值
KILL_STREAK_REWARDS = {
    3: 1.1,
    5: 1.2,
    10: 1.35,
    15: 1.5
}

# 经验灵石倍率
EXP_MULTIPLIER = 15  # 经验获得倍率
LINGSHI_MULTIPLIER = 50  # 灵石获得倍率（单独控制）

# 不同世界挑战难度加成（境界克制）
DIFFERENT_WORLD_MULTIPLIER = 1.20  # 不同世界挑战时怪物属性+20%

# ================================
# 副本等级基础属性表
# ================================
# 设计原则：
# 1. 每10级一个档次，档次间属性约翻2倍
# 2. 档次内通过线性插值平滑过渡
# 3. 玩家Lv.N的裸装属性应略高于Lv.N副本小怪，穿装备后明显碾压
#
# 参考：角色重构后 萧炎Lv.1裸装 攻击950/防御680/气血4200
#       每级升级增长约 攻击+19/防御+7/气血+42
#       萧炎Lv.10裸装约 攻击1121/防御743/气血4578
#       萧炎Lv.50裸装约 攻击1880/防御1020/气血6280
#
# 小怪基础属性设计为同级玩家裸装的60%~75%，穿装备后可碾压
# Boss基础属性在小怪基础上 ×2.5血量 ×1.3攻击 ×1.2防御

DUNGEON_BASE_STATS = {
    # min_level: (攻击, 防御, 气血, 速度, 暴击, 暴伤, 闪避, 命中, 破防, 吸血)
    1: (550, 380, 2800, 65, 800, 3500, 800, 3000, 100, 0),
    10: (650, 450, 3500, 70, 1100, 4000, 1000, 3500, 200, 0),
    20: (750, 520, 4200, 76, 1300, 4500, 1280, 4200, 320, 100),
    30: (880, 612, 6000, 85, 1550, 5000, 1450, 4150, 410, 200),
    40: (1500, 1050, 10000, 105, 1950, 5500, 1650, 4510, 650, 300),
    50: (2200, 1300, 15000, 115, 2350, 6000, 2050, 5500, 750, 400),
    60: (5800, 3500, 95000, 140, 3300, 6500, 3100, 7000, 1100, 500),
    70: (8800, 5300, 165000, 155, 3800, 7000, 3600, 7800, 1400, 600),
    80: (13500, 8000, 325000, 168, 4300, 7500, 4100, 8500, 1700, 700),
    90: (20000, 12000, 625000, 182, 4800, 8000, 4600, 9200, 2000, 800),
}


def _interpolate_base_stats(dungeon_level):
    """根据副本等级插值计算基础属性"""
    sorted_keys = sorted(DUNGEON_BASE_STATS.keys())

    # 找到当前等级所在的区间
    lower_key = sorted_keys[0]
    upper_key = sorted_keys[-1]

    for i, key in enumerate(sorted_keys):
        if key <= dungeon_level:
            lower_key = key
        if key > dungeon_level:
            upper_key = key
            break
    else:
        # dungeon_level >= 最大key，使用最大档
        upper_key = lower_key

    if lower_key == upper_key:
        return DUNGEON_BASE_STATS[lower_key]

    # 线性插值
    progress = (dungeon_level - lower_key) / (upper_key - lower_key)
    lower_stats = DUNGEON_BASE_STATS[lower_key]
    upper_stats = DUNGEON_BASE_STATS[upper_key]

    return tuple(
        int(lower_stats[i] + (upper_stats[i] - lower_stats[i]) * progress)
        for i in range(len(lower_stats))
    )


# ================================
# 数据库操作函数（保持不变）
# ================================

# 获取角色基础属性
async def get_role_base_attr(role_name):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT gongji, fangyu, qixue, sudu, baoji, baoshang, shanbi, mingzhong FROM data_role WHERE `name` = %s LIMIT 1"
            await cursor.execute(sql, (role_name,))
            result = await cursor.fetchone()
            if result:
                return {
                    'gongji': result[0],
                    'fangyu': result[1],
                    'qixue': result[2],
                    'sudu': result[3],
                    'baoji': result[4],
                    'baoshang': result[5],
                    'shanbi': result[6],
                    'mingzhong': result[7]
                }
            return None


# 获取指定类型的怪物列表（用于随机生成）
async def get_dungeon_monsters_by_type(dungeon_id, monster_type='normal'):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT id, dungeon_id, name, type, description, hp_ratio, atk_ratio, def_ratio,
                       spd_ratio, crit_ratio, crit_dmg_ratio, dodge_ratio, hit_ratio, skill_id, world
                FROM data_monster
                WHERE dungeon_id = %s AND type = %s
                ORDER BY RAND()
            """
            await cursor.execute(sql, (dungeon_id, monster_type))
            results = await cursor.fetchall()

            monsters = []
            for row in results:
                monsters.append({
                    'id': row[0],
                    'dungeon_id': row[1],
                    'name': row[2],
                    'type': row[3],
                    'description': row[4],
                    'hp_ratio': float(row[5]) if row[5] else 1.0,
                    'atk_ratio': float(row[6]) if row[6] else 1.0,
                    'def_ratio': float(row[7]) if row[7] else 1.0,
                    'spd_ratio': float(row[8]) if row[8] else 1.0,
                    'crit_ratio': float(row[9]) if row[9] else 1.0,
                    'crit_dmg_ratio': float(row[10]) if row[10] else 1.0,
                    'dodge_ratio': float(row[11]) if row[11] else 1.0,
                    'hit_ratio': float(row[12]) if row[12] else 1.0,
                    'skill_id': row[13],
                    'world': row[14]
                })
            return monsters


# 获取副本信息
async def get_dungeon_info(dungeon_id):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT id, name, world, min_level, min_stage, description,
                       reward_exp, reward_lingshi, reward_benyuan, rate_benyuan,
                       reward_skill, rate_skill, reward_pojing_dan, rate_pojing_dan,
                       reward_cl_boss, reward_cl_boss_count, reward_cl_normal, reward_cl_normal_count
                FROM data_dungeon
                WHERE id = %s
                LIMIT 1
            """
            await cursor.execute(sql, (dungeon_id,))
            result = await cursor.fetchone()

            if result:
                return {
                    'id': result[0],
                    'name': result[1],
                    'world': result[2],
                    'min_level': result[3],
                    'min_stage': result[4],
                    'description': result[5],
                    'reward_exp': result[6],
                    'reward_lingshi': result[7],
                    'reward_benyuan': result[8],
                    'rate_benyuan': result[9],
                    'reward_skill': result[10],
                    'rate_skill': result[11],
                    'reward_pojing_dan': result[12],
                    'rate_pojing_dan': result[13],
                    'reward_cl_boss': result[14],
                    'reward_cl_boss_count': result[15],
                    'reward_cl_normal': result[16],
                    'reward_cl_normal_count': result[17]
                }
            return None


# 获取副本列表
async def get_dungeon_list_by_level(level=0):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            if level:
                sql = "SELECT id, name, world, min_level, min_stage, description FROM data_dungeon WHERE min_level <= %s ORDER BY id"
                await cursor.execute(sql, (level,))
            else:
                sql = "SELECT id, name, world, min_level, min_stage, description FROM data_dungeon ORDER BY id"
                await cursor.execute(sql)

            results = await cursor.fetchall()
            dungeons = []
            for row in results:
                dungeons.append({
                    'id': row[0],
                    'name': row[1],
                    'world': row[2],
                    'min_level': row[3],
                    'min_stage': row[4],
                    'description': row[5]
                })
            return dungeons


# 为Boss创建技能
async def create_monster_skill(skill_id):
    """
    Args:
        skill_id: 技能ID (121-180为Boss技能)

    Returns:
        Skill对象或None
    """
    if not skill_id:
        return None

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            try:
                # data_skill表字段: id, role_name, skill_name, skill_type, value, is_percent,
                #                  item_id, buff_type, buff_value, buff_duration, buff_target,
                #                  buff_desc, buff_name
                sql = """
                    SELECT id, role_name, skill_name, skill_type, value, is_percent,
                           item_id, buff_type, buff_value, buff_duration, buff_target,
                           buff_desc, buff_name
                    FROM data_skill
                    WHERE id = %s
                    LIMIT 1
                """
                await cursor.execute(sql, (skill_id,))
                result = await cursor.fetchone()

                if result:
                    # 根据buff_target确定target_type (1:我方/self, 2:敌方/enemy)
                    buff_target = result[10] if result[10] else 0
                    target_type = "enemy" if buff_target == 2 else "self"

                    # Boss技能设置5回合冷却
                    return Skill(
                        id=result[0],  # id
                        name=result[2],  # skill_name
                        skill_type=result[3],  # skill_type (1攻击 2防御 3回复 4穿透)
                        target_type=target_type,  # 根据 buff_target 转换
                        value=result[4],  # value
                        is_percent=result[5],  # is_percent
                        item_id=result[6],  # item_id
                        cooldown=5,  # Boss技能5回合冷却
                        mana_cost=0,  # Boss技能无法力消耗
                        buff_type=result[7],  # buff_type
                        buff_value=result[8] or 0,  # buff_value
                        buff_duration=result[9] or 0,  # buff_duration
                        buff_target=buff_target,  # buff_target (1:我方, 2:敌方)
                        buff_name=result[12] or "",  # buff_name
                        description=result[11] or ""  # buff_desc
                    )
            except Exception as e:
                # 如果data_skill表不存在或查询失败，返回None（Boss不使用技能）
                print(f"Boss技能加载失败 (ID: {skill_id}): {e}")
                return None

    return None


async def get_boss_mechanics(cursor, dungeon_id, boss_name):
    """读取可覆盖默认天机的副本配置；迁移未部署时安全使用代码默认值。"""
    try:
        await cursor.execute("""
            SELECT trigger_stage, trigger_threshold, mechanic_name, counter_element,
                   counter_name, fail_effect, fail_value, duration_rounds, break_drop_weight
            FROM data_boss_mechanic
            WHERE dungeon_id IN (0, %s) AND (boss_name = '*' OR boss_name = %s)
            ORDER BY dungeon_id DESC, boss_name DESC, trigger_threshold ASC
        """, (dungeon_id, boss_name))
        rows = await cursor.fetchall()
    except Exception:
        return []
    return [{
        "stage": row[0], "threshold": float(row[1]), "name": row[2],
        "counter_element": row[3], "counter_name": row[4], "effect": row[5],
        "value": int(row[6]), "duration": int(row[7]), "drop_weight": int(row[8]),
    } for row in rows]


# ================================
# 玩家副本进度管理
# ================================

# 获取玩家在副本中的进度
async def get_player_dungeon_progress(uid, dungeon_id):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT uid, dungeon_id, wave, total_waves, monsters, defeated_count,
                       player_hp_ratio, kill_streak, total_kills, start_time, status
                FROM user_dungeon_progress
                WHERE uid = %s AND dungeon_id = %s
                LIMIT 1
            """
            await cursor.execute(sql, (uid, dungeon_id))
            result = await cursor.fetchone()

            if result:
                return {
                    'uid': result[0],
                    'dungeon_id': result[1],
                    'wave': result[2],
                    'total_waves': result[3],
                    'monsters': json.loads(result[4]) if result[4] else [],
                    'defeated_count': result[5],
                    'player_hp_ratio': float(result[6]),
                    'kill_streak': result[7],
                    'total_kills': result[8],
                    'start_time': result[9],
                    'status': result[10]
                }
            return None


# 创建新的副本进度并生成怪物
async def create_dungeon_progress(uid, dungeon_id, wave=1):
    # 获取副本的所有怪物
    normal_monsters = await get_dungeon_monsters_by_type(dungeon_id, 'normal')
    boss_monsters = await get_dungeon_monsters_by_type(dungeon_id, 'boss')

    if not normal_monsters or not boss_monsters:
        return None

    # 生成当前波次的怪物列表（固定第5位为Boss，普通怪允许重复）
    monsters = []

    # 第1~3波：1个Boss + 4个普通怪物（普通怪可重复）
    boss_count = min(1, len(boss_monsters))
    selected_boss = random.sample(boss_monsters, boss_count) if boss_count > 0 else []

    selected_normals = []
    for _ in range(4):
        if len(normal_monsters) > 0:
            selected_normals.append(copy.deepcopy(random.choice(normal_monsters)))

    # 普通怪不足时补齐
    while len(selected_normals) < 4:
        if len(normal_monsters) > 0:
            selected_normals.append(copy.deepcopy(random.choice(normal_monsters)))
        elif len(boss_monsters) > 0:
            selected_normals.append(copy.deepcopy(random.choice(boss_monsters)))
        else:
            break

    monsters = selected_normals[:4] + selected_boss

    # 兜底：Boss缺失时补齐到5个
    while len(monsters) < 5:
        if len(normal_monsters) > 0:
            monsters.append(copy.deepcopy(random.choice(normal_monsters)))
        elif len(boss_monsters) > 0:
            monsters.append(copy.deepcopy(random.choice(boss_monsters)))
        else:
            break

    # 保证第5位是Boss（若有Boss）
    if len(monsters) >= 5 and len(selected_boss) > 0:
        monsters[4] = copy.deepcopy(selected_boss[0])

    # 标记怪物状态并转换为JSON可序列化的格式
    for i, monster in enumerate(monsters):
        monster['index'] = i + 1
        monster['defeated'] = False
        monster['hp_ratio'] = float(monster.get('hp_ratio', 1.0))
        monster['atk_ratio'] = float(monster.get('atk_ratio', 1.0))
        monster['def_ratio'] = float(monster.get('def_ratio', 1.0))
        monster['spd_ratio'] = float(monster.get('spd_ratio', 1.0))
        monster['crit_ratio'] = float(monster.get('crit_ratio', 1.0))
        monster['crit_dmg_ratio'] = float(monster.get('crit_dmg_ratio', 1.0))
        monster['dodge_ratio'] = float(monster.get('dodge_ratio', 1.0))
        monster['hit_ratio'] = float(monster.get('hit_ratio', 1.0))

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                INSERT INTO user_dungeon_progress
                (uid, dungeon_id, wave, monsters, defeated_count, player_hp_ratio, kill_streak, total_kills, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                wave = %s, monsters = %s, defeated_count = %s, player_hp_ratio = %s, status = %s
            """
            monsters_json = json.dumps(monsters, ensure_ascii=False)
            await cursor.execute(sql, (
                uid, dungeon_id, wave, monsters_json, 0, 1.00, 0, 0, 'fighting',
                wave, monsters_json, 0, 1.00, 'fighting'
            ))
            await conn.commit()

    return await get_player_dungeon_progress(uid, dungeon_id)


# 更新副本进度
async def update_dungeon_progress(uid, dungeon_id, monster_index, player_hp_ratio, won):
    progress = await get_player_dungeon_progress(uid, dungeon_id)
    if not progress:
        return None

    monsters = progress['monsters']

    # 标记怪物为已击败
    for monster in monsters:
        if monster['index'] == monster_index:
            monster['defeated'] = True
            break

    defeated_count = sum(1 for m in monsters if m['defeated'])
    kill_streak = progress['kill_streak'] + 1 if won else 0
    total_kills = progress['total_kills'] + 1 if won else progress['total_kills']

    # 检查是否所有怪物都被击败
    if defeated_count >= len(monsters):
        if progress['wave'] < progress['total_waves']:
            return await create_dungeon_progress(uid, dungeon_id, progress['wave'] + 1)
        else:
            await set_dungeon_status(uid, dungeon_id, 'completed')
            return {
                'wave_completed': True,
                'dungeon_completed': True,
                'new_progress': None
            }

    # 更新进度
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                UPDATE user_dungeon_progress
                SET monsters = %s, defeated_count = %s, player_hp_ratio = %s,
                    kill_streak = %s, total_kills = %s
                WHERE uid = %s AND dungeon_id = %s
            """
            await cursor.execute(sql, (
                json.dumps(monsters, ensure_ascii=False), defeated_count,
                player_hp_ratio, kill_streak, total_kills, uid, dungeon_id
            ))
            await conn.commit()

    return {
        'wave_completed': False,
        'dungeon_completed': False,
        'defeated_count': defeated_count
    }


# 设置副本状态
async def set_dungeon_status(uid, dungeon_id, status):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "UPDATE user_dungeon_progress SET status = %s WHERE uid = %s AND dungeon_id = %s"
            await cursor.execute(sql, (status, uid, dungeon_id))
            await conn.commit()


# 放弃副本
async def abandon_dungeon(uid, dungeon_id):
    await set_dungeon_status(uid, dungeon_id, 'abandoned')


# 获取今日剩余挑战次数
async def get_daily_remaining_count(uid):
    from datetime import date
    today = date.today()

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 检查是否需要重置
            sql = "SELECT dungeon_num, daily_dungeon_reset_time FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()

            if not result:
                return FREE_DAILY_CHALLENGES

            remaining = result[0] or FREE_DAILY_CHALLENGES
            last_reset = result[1]

            # 如果日期不同，重置次数
            if last_reset != today:
                await reset_daily_challenge_count(uid)
                return FREE_DAILY_CHALLENGES

            return max(0, remaining)


# 重置每日挑战次数
async def reset_daily_challenge_count(uid):
    from datetime import date
    today = date.today()

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "UPDATE user_zt SET dungeon_num = %s, daily_dungeon_reset_time = %s WHERE id = %s"
            await cursor.execute(sql, (FREE_DAILY_CHALLENGES, today, uid))
            await conn.commit()


# 增加今日挑战次数
async def increment_daily_challenge(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 先确保今日已重置
            remaining = await get_daily_remaining_count(uid)
            if remaining <= 0:
                return False

            sql = "UPDATE user_zt SET dungeon_num = dungeon_num - 1 WHERE id = %s AND dungeon_num > 0"
            await cursor.execute(sql, (uid,))
            await conn.commit()
            return True


# 添加副本掉落
async def record_dungeon_drop(uid, dungeon_id, monster_name, monster_type, drop_item_id, drop_item_name, drop_count, wave):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT 1 FROM user_dungeon_drop
                WHERE uid = %s AND dungeon_id = %s AND monster_name = %s
                  AND monster_type = %s AND drop_item_id = %s
                  AND drop_item_name = %s AND drop_count = %s AND wave = %s
                LIMIT 1
                """,
                (uid, dungeon_id, monster_name, monster_type, drop_item_id, drop_item_name, drop_count, wave),
            )
            if await cursor.fetchone():
                return
            sql = """
                INSERT INTO user_dungeon_drop
                (uid, dungeon_id, monster_name, monster_type, drop_item_id, drop_item_name, drop_count, wave)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            await cursor.execute(sql, (uid, dungeon_id, monster_name, monster_type, drop_item_id, drop_item_name, drop_count, wave))
            await conn.commit()


async def _get_item_names_by_ids(item_ids):
    item_ids = [int(item_id) for item_id in dict.fromkeys(item_ids) if int(item_id) > 0]
    if not item_ids:
        return {}

    placeholders = ",".join(["%s"] * len(item_ids))
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                f"SELECT id, name FROM data_item WHERE id IN ({placeholders})",
                tuple(item_ids),
            )
            rows = await cursor.fetchall()
    return {int(row[0]): row[1] for row in rows}


# ================================
# 怪物属性生成
# ================================

# 生成怪物属性
async def generate_monster_attr_by_ratio(dungeon_level, monster_data, player_level, wave,
                                         player_role_attr=None, is_different_world=False):
    """
    基于副本等级生成怪物属性（不再跟随玩家属性）

    Args:
        dungeon_level: 副本最低等级要求（data_dungeon.min_level）
        monster_data: 怪物模板数据（含各属性倍率）
        player_level: 玩家等级（仅用于日志，不影响计算）
        wave: 当前波次（1/2/3）
        player_role_attr: 玩家属性（不再使用，保留参数兼容性）
        is_different_world: 是否跨世界挑战
    """

    # ========== 1. 获取副本等级对应的基础属性 ==========
    base_stats = _interpolate_base_stats(dungeon_level)
    base_gongji = base_stats[0]
    base_fangyu = base_stats[1]
    base_qixue = base_stats[2]
    base_sudu = base_stats[3]
    base_baoji = base_stats[4]
    base_baoshang = base_stats[5]
    base_shanbi = base_stats[6]
    base_mingzhong = base_stats[7]
    base_pofang = base_stats[8]
    base_xixue = base_stats[9]

    # ========== 2. 应用怪物个体倍率（来自data_monster表） ==========
    hp_ratio = float(monster_data.get('hp_ratio', 1.0))
    atk_ratio = float(monster_data.get('atk_ratio', 1.0))
    def_ratio = float(monster_data.get('def_ratio', 1.0))
    spd_ratio = float(monster_data.get('spd_ratio', 1.0))
    crit_ratio = float(monster_data.get('crit_ratio', 1.0))
    crit_dmg_ratio = float(monster_data.get('crit_dmg_ratio', 1.0))
    dodge_ratio = float(monster_data.get('dodge_ratio', 1.0))
    hit_ratio = float(monster_data.get('hit_ratio', 1.0))

    # ========== 3. 波次难度递增 ==========
    wave_multiplier = {1: 1.0, 2: 1.1, 3: 1.15}.get(wave, 1.0)

    # ========== 4. 跨世界惩罚 ==========
    world_multiplier = 1.15 if is_different_world else 1.0

    # ========== 5. 最终属性计算 ==========
    gongji = int(base_gongji * atk_ratio * wave_multiplier * world_multiplier)
    fangyu = int(base_fangyu * def_ratio * wave_multiplier * world_multiplier)
    qixue = int(base_qixue * hp_ratio * wave_multiplier * world_multiplier)
    sudu = int(base_sudu * spd_ratio * wave_multiplier * world_multiplier)
    baoji = int(base_baoji * crit_ratio * wave_multiplier)
    baoshang = int(base_baoshang * crit_dmg_ratio * wave_multiplier)
    shanbi = int(base_shanbi * dodge_ratio * wave_multiplier)
    mingzhong = int(base_mingzhong * hit_ratio * wave_multiplier)
    pofang = int(base_pofang * wave_multiplier)
    xixue = int(base_xixue * wave_multiplier)

    # ========== 7. 返回最终属性 ==========
    return {
        'qixue': max(500, qixue),
        'gongji': max(80, gongji),
        'fangyu': max(60, fangyu),
        'sudu': max(50, sudu),
        'baoji': max(300, baoji),
        'baoshang': max(2000, baoshang),
        'shanbi': max(300, shanbi),
        'mingzhong': max(800, mingzhong),
        'pofang': pofang,
        'xixue': xixue,
        'max_fali': 100
    }


# ================================
# Markdown格式化函数
# ================================

# 副本列表（Markdown）
def format_dungeon_markdown(dungeons, page, total_pages, role_info, remaining_count):
    lines = []
    lines.append(f"##### 📜副本列表({page}/{total_pages}页)")
    lines.append(f"**当前角色：** [{role_info['id']}] {role_info['name']} Lv.{role_info['level']}")
    lines.append(f"**所属世界：** {role_info['world']}")
    lines.append(f"**剩余挑战次数：** {remaining_count}")
    lines.append("***")

    for dungeon in dungeons:
        dungeon_id = dungeon['id']
        can_challenge = dungeon['min_level'] <= role_info['level']
        status = "✓" if can_challenge else "✗"

        if can_challenge and remaining_count > 0:
            lines.append(f"**{dungeon_id}. {dungeon['name']}**")
            lines.append(f"> 所属世界：{dungeon['world']} | {dungeon['min_level']}级可挑战")
            lines.append(f"> 🗒︎<qqbot-cmd-input text='副本信息 {dungeon_id}' show='详情：{dungeon['name']}' /> ⚔️<qqbot-cmd-input text='挑战副本 {dungeon_id}' show='挑战：{dungeon['name']}' />")
        elif can_challenge:
            lines.append(f"**{dungeon_id}. {dungeon['name']}**)")
            lines.append(f"> 所属世界：{dungeon['world']} | {dungeon['min_level']}级可挑战")
            lines.append(f"> 🗒︎<qqbot-cmd-input text='副本信息 {dungeon_id}' show='详情：{dungeon['name']}' /> 挑战次数已耗尽")
        else:
            lines.append(f"{dungeon_id}. {dungeon['name']} [{dungeon['world']}] (等级{dungeon['min_level']}级)")

        lines.append("")

    lines.append("***")
    lines.append("⚠️跨界挑战将有因果压制，怪物全属性提升15%")
    lines.append("***")
    lines.append(f"<qqbot-cmd-input text='副本列表 {page - 1}' show='副本列表 {page - 1}' /> | <qqbot-cmd-input text='副本列表' show='跳转【页数】' /> | <qqbot-cmd-input text='副本列表 {page + 1}' show='副本列表 {page + 1}' />")

    return "\n".join(lines)


# 副本信息（Markdown）
def format_dungeon_info_markdown(dungeon, role_info, remaining_count, is_different_world=False, drops=None):
    lines = []
    lines.append(f"##### {dungeon['name']} (ID:{dungeon['id']})")
    lines.append("")

    can_challenge = dungeon['min_level'] <= role_info['level']
    status = "达成" if can_challenge else "不足"
    world_desc = "此方世界" if role_info['world'] == dungeon['world'] else "非此世界"

    lines.append(f"**出战角色:** Lv.{role_info['level']} {role_info['name']}〔{role_info['world']}〕")
    lines.append(f"**剩余挑战次数:** {remaining_count}次")

    lines.append(f"***")
    lines.append(f"🥊**副本要求**")
    lines.append(f">等级要求: Lv.{dungeon['min_level']} (等级{status})")
    lines.append(f">所属世界: {dungeon['world']}({world_desc})")
    lines.append("")
    lines.append(f"📋**副本描述**")
    lines.append(f"> _{dungeon['description']}_")
    lines.append("")

    lines.append(f"🏆️**副本奖励**")

    # 掉落信息
    if drops:
        # 本源突破材料掉落信息
        if drops.get('benyuan'):
            lines.append(f">本源突破材料(概率)：_{drops['benyuan']}_")
        else:
            lines.append(">本源突破材料(概率)：_无_")
        # 本源升级材料掉落信息
        if drops.get('cl_names'):
            cl_text = "、".join(drops['cl_names'])
            lines.append(f">本源升级材料：_{cl_text}_")
        else:
            lines.append(">本源升级材料：_无_")
        # 技能卷轴掉落信息
        if drops.get('skills'):
            skills_text = "、".join(drops['skills'])
            lines.append(f">技能卷轴(概率)：_{skills_text}_")
        else:
            lines.append(">技能卷轴(概率)：_无_")
        # 破境丹掉落信息
        if drops.get('pojing_dan') and drops.get('pojing_dan_rate'):
            lines.append(f">破境丹(概率)：_{drops['pojing_dan']}_")
        else:
            lines.append(">破境丹(概率)：_无_")
        # 装备套装掉落信息
        if drops.get('equip_sets'):
            sets_text = "、".join(drops['equip_sets'])
            lines.append(f">装备套装：_{sets_text}_")
        else:
            lines.append(">装备套装：_无_")

    else:
        lines.append(">本源突破材料：_无_")
        lines.append(">本源升级材料：_无_")
        lines.append(">技能卷轴：_无_")
        lines.append(">破境丹(概率)：_无_")
        lines.append(">装备套装：_无_")

    actual_exp = dungeon['reward_exp'] * EXP_MULTIPLIER
    per_monster_lingshi = dungeon['reward_lingshi'] // 15 * LINGSHI_MULTIPLIER
    per_boss_lingshi = per_monster_lingshi * 2
    estimated_total = per_monster_lingshi * 12 + per_boss_lingshi * 3
    lines.append(f">奖励经验：{actual_exp}")
    lines.append(f">奖励灵石：{estimated_total}")

    # 跨界挑战警告
    if is_different_world:
        lines.append("***")
        lines.append(f"⚠️**跨界挑战：怪物属性+15%**")

    fb_show = "🚀 挑战副本" if role_info['world'] == dungeon['world'] else "🚀 跨界挑战"

    if can_challenge and remaining_count > 0:
        lines.append("***")
        lines.append(f" <qqbot-cmd-input text='挑战副本 {dungeon['id']}' show='挑战：{dungeon['name']}' /> | <qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='收回' show='收回' />")

    return "\n".join(lines)


# 怪物列表（Markdown）
def format_monster_list_markdown(dungeon_name, progress, dungeon, is_different_world=False):
    def clean_text(text):
        if not text:
            return ""
        return str(text).replace('"', '&quot;').replace("'", '&apos;').replace('\\', '\\\\')

    lines = []
    # 头部信息
    lines.append(f"##### 🏰 {dungeon_name}")
    lines.append("")

    # 进度条
    defeated = progress['defeated_count']
    total = 5
    progress_bar = "█" * defeated + "░" * (total - defeated)
    lines.append(f"**进度：** {progress_bar} {defeated}/{total}")
    lines.append(f"**波次：** 第 {progress['wave']} 波 | **连杀：** 🔥{progress['kill_streak']}")

    # 跨界挑战警告
    if is_different_world:
        lines.append("")
        lines.append(f"> ⚠️ **跨界挑战中** | 怪物属性已提升15%")

    lines.append("")
    lines.append("***")
    lines.append("")

    # 怪物列表
    for monster in progress['monsters']:
        monster_name = clean_text(monster.get('name', ''))
        if monster['index'] == 1:
            xuhao = '①'
        elif monster['index'] == 2:
            xuhao = '②'
        elif monster['index'] == 3:
            xuhao = '③'
        elif monster['index'] == 4:
            xuhao = '④'
        elif monster['index'] == 5:
            xuhao = '⑤'
        else:
            xuhao = ''
        if monster['defeated']:
            monster_type = "[BOSS]" if monster['type'] == 'boss' else "[普通]"
            lines.append(f"~~{xuhao} {monster_name}~~ {monster_type}")
        else:
            monster_type = "[BOSS]" if monster['type'] == 'boss' else "[普通]"
            lines.append(f"{xuhao} <qqbot-cmd-input text='挑战怪物 {monster['index']}' show='{monster_name}'/> {monster_type}")

    lines.append("> 点击蓝字可直接挑战怪物噢~")

    # 底部操作
    lines.append("***")
    lines.append("<qqbot-cmd-input text='放弃副本' show='放弃副本' /> | <qqbot-cmd-input text='当前角色' show='当前角色' /> | <qqbot-cmd-input text='收回' show='收回' />")

    return "\n".join(lines)


# 战斗结果（Markdown）
def format_combat_result_markdown(winner, player_name, monster_name, monster_type, combat_summary, rewards, dungeon, combat_logs=None):
    lines = []

    # 战斗结果标题
    player_won = (winner.name == player_name) if hasattr(winner, 'name') else (winner == player_name)

    if player_won:
        lines.append(f"##### 🏆 战斗胜利")
        lines.append(f"**{player_name}** 击败了 **{monster_name}**({monster_type})")
        lines.append(f"战斗回合: {combat_summary['total_rounds']} | 连杀: {rewards.get('kill_streak', 0)}")
        lines.append("")
        lines.append(f"🎁 **获得奖励**")
        lines.append(f"> 经验值: +{rewards['exp']}")
        if rewards.get('streak_bonus') > 1.0:
            bonus_pct = int(rewards['streak_bonus'] * 100) - 100
            lines.append(f"> _(连杀加成 x{rewards['kill_streak']} +{bonus_pct}%)_")
        lines.append(f"> 灵石: +{rewards['lingshi']}")

        if rewards.get('level_up'):
            lines.append("")
            lines.append(f"🆙 **等级提升**")
            lines.append(f"> 等级：Lv.{rewards['new_level'] - 1} ➜ Lv.{rewards['new_level']}")
            lines.append(f"> 攻击: +{rewards['add_gongji']}")
            lines.append(f"> 防御: +{rewards['add_fangyu']}")
            lines.append(f"> 气血: +{rewards['add_qixue']}")

        if rewards.get('need_breakthrough'):
            lines.append("")
            lines.append(f"⚠️ **境界巅峰**")
            lines.append(f"> 当前等级：Lv.{rewards['current_level']}")
            lines.append(f"> 您已修至本阶至强，需使用破境丹进行悟道进阶")
            lines.append(f"> 经验已累积，突破后将自动结算")

        if rewards.get('drops'):
            lines.append("")
            lines.append(f"🎁 **获得掉落**")
            for drop in rewards['drops']:
                lines.append(f"> {drop}")

        if rewards.get('dungeon_completed'):
            lines.append("")
            lines.append(f"🎉 **副本通关** {dungeon['name']}!")
    else:
        lines.append(f"##### 💀 战斗失败")
        lines.append(f"**{player_name}** 被 **{monster_name}** 击败")
        lines.append("")
        lines.append("请提升实力后重新挑战")

    # 战斗日志
    if combat_logs:
        lines.append("")
        lines.append(f"📜 **战斗详情**")
        lines.append("")

        # 使用代码块显示战斗过程
        log_lines = []
        for log in combat_logs:
            log_type = log.get('type', '')
            log_message = log.get('message', '')
            if log_message:
                if log_type == 'round':
                    log_lines.append(f"\n{log_message}")
                elif log_type == 'round_end':
                    log_lines.append(f"{log_message}")
                elif log_type == 'combat_end':
                    log_lines.append(f"{log_message}")
                else:
                    log_lines.append(log_message)

        combat_text = "\n".join(log_lines)
        lines.append(f"```python\n{combat_text}\n```")

    # 剩余血量（确保显示整数，小于0显示0）
    lines.append("")
    lines.append("***")
    lines.append("")
    player_hp = max(0, int(rewards.get('player_hp', 0)))
    max_hp = int(rewards.get('max_hp', 0))
    hp_pct = int(rewards.get('hp_ratio', 0) * 100)
    hp_pct = max(0, min(100, hp_pct))  # 确保百分比在0-100范围内
    lines.append(f"**剩余血量**: {player_hp}/{max_hp} ({hp_pct}%)")

    return "\n".join(lines)


# ================================
# 副本系统功能函数
# ================================


# 副本列表
@reg_xz_func
async def dungeon_list(uid, qz, page=1):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                lines = []
                lines.append("没有出战角色，请先出战[角色ID]")
                lines.append("<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战' show='出战' /> | <qqbot-cmd-input text='收回' show='收回' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            role_id, role_name, role_level, role_world = role_result

            # 获取可挑战的副本
            dungeons = await get_dungeon_list_by_level(level=role_level)

            if not dungeons:
                return qz + f"当前没有适合Lv.{role_level}的副本\n请继续升级后查看"

            # 获取今日剩余挑战次数
            remaining_count = await get_daily_remaining_count(uid)

            # 分页显示
            page_size = 6
            page = max(1, int(page) if isinstance(page, (int, str)) and str(page).isdigit() else 1)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_dungeons = dungeons[start_idx:end_idx]
            total_pages = (len(dungeons) + page_size - 1) // page_size

            role_info = {
                'id': role_id,
                'name': role_name,
                'level': role_level,
                'world': role_world
            }

            markdown_content = format_dungeon_markdown(page_dungeons, page, total_pages, role_info, remaining_count)

            return {"type": "markdown", "content": markdown_content}


# 副本信息
@reg_xz_func
async def dungeon_info(uid, qz, dungeon_id):
    try:
        dungeon_id = int(dungeon_id)
    except (ValueError, TypeError):
        lines = []
        lines.append("副本ID格式错误，请输入正确的副本ID")
        lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    dungeon = await get_dungeon_info(dungeon_id)
    if dungeon is None:
        lines = []
        lines.append("副本ID不存在，请输入正确的副本ID")
        lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                lines = []
                lines.append("当前没有出战角色，请先出战[角色ID]")
                lines.append("<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战' show='出战' /> | <qqbot-cmd-input text='收回' show='收回' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            role_id, role_name, role_level, role_world = role_result

            remaining_count = await get_daily_remaining_count(uid)
            is_different_world = role_world != dungeon['world']

            role_info = {
                'level': role_level,
                'name': role_name,
                'world': role_world
            }

            # 获取掉落物品信息
            benyuan_name = None
            skill_names = []
            pojing_dan_name = None
            pojing_dan_rate = None
            equip_set_names = []
            cl_names = []

            if dungeon.get('reward_benyuan'):
                await cursor.execute("SELECT name FROM data_item WHERE id = %s", (dungeon['reward_benyuan'],))
                benyuan_result = await cursor.fetchone()
                if benyuan_result:
                    benyuan_name = benyuan_result[0]

            # 获取本源升级材料掉落信息
            if dungeon.get('reward_cl_boss'):
                cl_ids = str(dungeon['reward_cl_boss']).split('|')
                for cl_id in cl_ids:
                    if cl_id.strip():
                        await cursor.execute("SELECT name FROM data_item WHERE id = %s", (int(cl_id.strip()),))
                        cl_result = await cursor.fetchone()
                        if cl_result:
                            cl_names.append(cl_result[0])

            if dungeon.get('reward_skill'):
                skill_ids = str(dungeon['reward_skill']).split('|')
                for skill_id in skill_ids:
                    if skill_id.strip():
                        await cursor.execute("SELECT name FROM data_item WHERE id = %s", (int(skill_id.strip()),))
                        skill_result = await cursor.fetchone()
                        if skill_result:
                            skill_names.append(skill_result[0])

            # 获取破境丹掉落信息
            if dungeon.get('reward_pojing_dan') and dungeon.get('rate_pojing_dan'):
                await cursor.execute("SELECT name FROM data_item WHERE id = %s", (dungeon['reward_pojing_dan'],))
                pojing_dan_result = await cursor.fetchone()
                if pojing_dan_result:
                    pojing_dan_name = pojing_dan_result[0]
                    pojing_dan_rate = dungeon['rate_pojing_dan']

            # 获取装备掉落信息（套装名称）
            from Game_main.g7_equip import get_equip_templates_by_dungeon
            equip_templates = await get_equip_templates_by_dungeon(dungeon['id'])
            if equip_templates:
                set_names = set()
                for template in equip_templates:
                    if template.get('set_name'):
                        set_names.add(template['set_name'])
                equip_set_names = list(set_names)

            drops = {
                'benyuan': benyuan_name,
                'skills': skill_names,
                'pojing_dan': pojing_dan_name,
                'pojing_dan_rate': pojing_dan_rate,
                'equip_sets': equip_set_names,
                'cl_names': cl_names
            }

            markdown_content = format_dungeon_info_markdown(dungeon, role_info, remaining_count, is_different_world, drops)
            return {"type": "markdown", "content": markdown_content}


# 挑战副本
@reg_xz_func
async def challenge_dungeon(uid, qz):
    """开始挑战副本 - Markdown版本"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = """SELECT id, `name`, dengji, gongji, fangyu, qixue, sudu, baoji, baoshang,
                     shanbi, mingzhong, pofang, xixue, fali, gongji_jc, fangyu_jc, qixue_jc,
                     skill1_id, skill2_id, skill3_id, world, by_id
                     FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"""
            await cursor.execute(sql, (uid,))
            role_data = await cursor.fetchone()

            if role_data is None:
                lines = []
                lines.append("当前没有出战角色，请先出战[角色ID]")
                lines.append("<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战' show='出战' /> | <qqbot-cmd-input text='收回' show='收回' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            (role_id, role_name, role_level, gongji, fangyu, qixue, sudu, baoji, baoshang,
             shanbi, mingzhong, pofang, xixue, fali, gongji_jc, fangyu_jc, qixue_jc,
             skill1_id, skill2_id, skill3_id, role_world, by_id) = role_data

            # 检查是否有正在进行的副本
            sql = "SELECT dungeon_id FROM user_dungeon_progress WHERE uid = %s AND status = 'fighting' LIMIT 1"
            await cursor.execute(sql, (uid,))
            existing = await cursor.fetchone()

            if existing:
                dungeon_id = existing[0]
                dungeon = await get_dungeon_info(dungeon_id)
                return {"type": "markdown", "content": f"正在进行**{dungeon['name']}**的挑战\n\n请先放弃当前挑战\n\n<qqbot-cmd-input text='查看怪物' show='查看怪物' /> <qqbot-cmd-input text='放弃副本' show='放弃副本' />"}

            # 获取可挑战的副本列表
            dungeons = await get_dungeon_list_by_level(level=role_level)
            remaining_count = await get_daily_remaining_count(uid)

            lines = []
            lines.append("**选择要挑战的副本**")
            lines.append(f"剩余次数: {remaining_count}")
            lines.append("")

            for dungeon in dungeons[:10]:
                can_challenge = dungeon['min_level'] <= role_level

                if remaining_count > 0 and can_challenge:
                    lines.append(f"**{dungeon['id']}. {dungeon['name']}** ({dungeon['min_level']}级+)")
                    lines.append(f"<qqbot-cmd-input text='副本信息 {dungeon['id']}' show='副本信息 {dungeon['id']}' /> <qqbot-cmd-input text='挑战副本 {dungeon['id']}' show='挑战副本 {dungeon['id']}' />")
                elif can_challenge:
                    lines.append(f"**{dungeon['id']}. {dungeon['name']}** ({dungeon['min_level']}级+ 次数用尽)")
                    lines.append(f"<qqbot-cmd-input text='副本信息 {dungeon['id']}' show='副本信息 {dungeon['id']}' />")
                else:
                    lines.append(f"{dungeon['id']}. {dungeon['name']} (等级{dungeon['min_level']}级+)")

            return {"type": "markdown", "content": "\n".join(lines)}


# 挑战指定副本
@reg_xz_func
async def start_challenge_dungeon(uid, qz, dungeon_id):
    try:
        dungeon_id = int(dungeon_id)
    except (ValueError, TypeError):
        lines = []
        lines.append("副本ID格式错误，请输入正确的副本ID")
        lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' /> | <qqbot-cmd-input text='挑战副本' show='挑战副本' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    dungeon = await get_dungeon_info(dungeon_id)
    if dungeon is None:
        lines = []
        lines.append("副本ID不存在，请输入正确的副本ID")
        lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' /> | <qqbot-cmd-input text='挑战副本' show='挑战副本' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                lines = []
                lines.append("当前没有出战角色，请先出战[角色ID]")
                lines.append("<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战' show='出战' /> | <qqbot-cmd-input text='收回' show='收回' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            role_id, role_name, role_level, role_world = role_result

            # 检查等级限制
            if role_level < dungeon['min_level']:
                return qz + f"等级不足\n需要: Lv.{dungeon['min_level']}+ 您: Lv.{role_level}"

            # 检查世界是否匹配（不同世界会增加难度）
            is_different_world = role_world != dungeon['world']

            # 检查挑战次数
            remaining_count = await get_daily_remaining_count(uid)
            if remaining_count <= 0:
                return qz + f"今日挑战次数已用完\n每日{FREE_DAILY_CHALLENGES}次 明日重置"

            # 增加挑战次数
            success = await increment_daily_challenge(uid)
            if not success:
                return qz + "挑战次数扣除失败"

            # 创建副本进度（生成第一波怪物）
            progress = await create_dungeon_progress(uid, dungeon_id, 1)

            if not progress:
                return qz + "副本怪物数据初始化失败，请联系管理员处理。"

            return await show_monster_list(uid)


# 怪物列表
@reg_xz_func
async def show_monster_list(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT dungeon_id FROM user_dungeon_progress WHERE uid = %s AND status = 'fighting' LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()

            if not result:
                lines = []
                lines.append("没有正在进行的副本，请输入发送挑战副本[副本ID]开始挑战吧！")
                lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' /> | <qqbot-cmd-input text='挑战副本' show='挑战副本 1' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            dungeon_id = result[0]

            # 获取玩家角色世界
            sql2 = "SELECT world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql2, (uid,))
            role_result = await cursor.fetchone()
            role_world = role_result[0] if role_result else None

    progress = await get_player_dungeon_progress(uid, dungeon_id)
    dungeon = await get_dungeon_info(dungeon_id)

    # 检查是否为不同世界挑战
    is_different_world = role_world != dungeon['world'] if role_world else False

    markdown_content = format_monster_list_markdown(dungeon['name'], progress, dungeon, is_different_world)

    return {"type": "markdown", "content": markdown_content}


# 挑战怪物
@reg_xz_func
async def fight_monster(uid, qz, monster_index, combat_manager=None):
    try:
        monster_index = int(monster_index)
    except (ValueError, TypeError):
        lines = []
        lines.append("怪物编号格式错误，请输入发送正确的格式开始挑战吧！")
        lines.append("<qqbot-cmd-input text='查看怪物' show='查看怪物' /> | <qqbot-cmd-input text='挑战怪物 1' show='挑战怪物 1' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT dungeon_id FROM user_dungeon_progress WHERE uid = %s AND status = 'fighting' LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()

            if not result:
                lines = []
                lines.append("没有正在进行的副本，请输入发送挑战副本[副本ID]开始挑战吧！")
                lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' /> | <qqbot-cmd-input text='挑战副本' show='挑战副本 1' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            dungeon_id = result[0]

    progress = await get_player_dungeon_progress(uid, dungeon_id)
    dungeon = await get_dungeon_info(dungeon_id)

    # 查找指定怪物
    target_monster = None
    for monster in progress['monsters']:
        if monster['index'] == monster_index:
            target_monster = monster
            break

    if not target_monster:
        lines = []
        lines.append("怪物编号不存在，请输入发送正确的怪物编号")
        lines.append("<qqbot-cmd-input text='查看怪物' show='查看怪物' /> | <qqbot-cmd-input text='挑战怪物 1' show='挑战怪物 1' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    if target_monster['defeated']:
        lines = []
        lines.append("该怪物已被击败，请挑战其他怪物吧")
        lines.append("<qqbot-cmd-input text='查看怪物' show='查看怪物' /> | <qqbot-cmd-input text='挑战怪物' show='挑战怪物' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    # 获取玩家角色数据
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """SELECT id, `name`, dengji, gongji, fangyu, qixue, sudu, baoji, baoshang,
                     shanbi, mingzhong, pofang, xixue, fali, gongji_jc, fangyu_jc, qixue_jc,
                     skill1_id, skill2_id, skill3_id, world
                     FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"""
            await cursor.execute(sql, (uid,))
            role_data = await cursor.fetchone()

            if role_data is None:
                lines = []
                lines.append("当前没有出战角色，请先出战[角色ID]")
                lines.append("<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战' show='出战' /> | <qqbot-cmd-input text='收回' show='收回' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            (role_id, role_name, role_level, gongji, fangyu, qixue, sudu, baoji, baoshang,
             shanbi, mingzhong, pofang, xixue, fali, gongji_jc, fangyu_jc, qixue_jc,
             skill1_id, skill2_id, skill3_id, role_world) = role_data

            # 检查是否为不同世界挑战（境界克制）
            is_different_world = role_world != dungeon['world']

            # 计算装备加成（战斗属性集成）
            equip_bonus = await calc_role_equip_bonus(role_id)

            # 计算角色实际属性（基础×加成百分比 + 装备加成）
            final_gongji = int(gongji * (1 + gongji_jc / 100)) + equip_bonus.get('gongji', 0)
            final_fangyu = int(fangyu * (1 + fangyu_jc / 100)) + equip_bonus.get('fangyu', 0)
            final_qixue = int(qixue * (1 + qixue_jc / 100)) + equip_bonus.get('qixue', 0)
            final_sudu = int(sudu) + equip_bonus.get('sudu', 0)
            final_baoji = int(baoji) + equip_bonus.get('baoji', 0)
            final_baoshang = int(baoshang) + equip_bonus.get('baoshang', 0)
            final_shanbi = int(shanbi) + equip_bonus.get('shanbi', 0)
            final_mingzhong = int(mingzhong) + equip_bonus.get('mingzhong', 0)
            final_pofang = int(pofang) + equip_bonus.get('pofang', 0)
            final_xixue = int(xixue) + equip_bonus.get('xixue', 0)

            # 应用血量继承
            hp_ratio = progress['player_hp_ratio']
            current_qixue = int(final_qixue * hp_ratio)
            current_qixue = max(current_qixue, int(final_qixue * 0.3))

            # 构建玩家战斗数据
            player_role_data = {
                'name': role_name,
                'qixue': current_qixue,
                'gongji': final_gongji,
                'fangyu': final_fangyu,
                'sudu': final_sudu,
                'baoji': final_baoji,
                'baoshang': final_baoshang,
                'shanbi': final_shanbi,
                'mingzhong': final_mingzhong,
                'pofang': final_pofang,
                'xixue': final_xixue,
                'max_fali': fali
            }

            # 获取玩家技能（从user_skill表获取，然后根据is_data_skill决定查询来源）
            player_skills = []
            for skill_id in [skill1_id, skill2_id, skill3_id]:
                if skill_id:
                    # 先从user_skill表获取技能信息（user_skill表没有buff_name和buff_desc字段）
                    await cursor.execute("""
                        SELECT skill_id, is_data_skill, skill_name, skill_type, value, is_percent,
                               cooldown
                        FROM user_skill
                        WHERE id = %s
                        LIMIT 1
                    """, (skill_id,))
                    user_skill_result = await cursor.fetchone()
                    if user_skill_result:
                        data_skill_id, is_data_skill, skill_name, skill_type, value, is_percent, cooldown = user_skill_result

                        if is_data_skill == 1:
                            # 基础技能：从data_skill表获取完整信息（包含buff相关字段）
                            await cursor.execute("""
                                SELECT id, role_name, skill_name, skill_type, value, is_percent,
                                       item_id, buff_type, buff_value, buff_duration, buff_target,
                                       buff_desc, buff_name, cooldown
                                FROM data_skill
                                WHERE id = %s
                                LIMIT 1
                            """, (data_skill_id,))
                            skill_result = await cursor.fetchone()
                            if skill_result:
                                buff_target = skill_result[10] if skill_result[10] else 2
                                target_type = "enemy" if buff_target == 2 else "self"

                                player_skills.append(Skill(
                                    id=skill_result[0],
                                    name=skill_result[2],
                                    skill_type=skill_result[3],
                                    target_type=target_type,
                                    value=int(float(str(skill_result[4]))) if isinstance(skill_result[4], str) else skill_result[4],
                                    is_percent=skill_result[5],
                                    item_id=skill_result[6],
                                    cooldown=skill_result[13] or 0,
                                    mana_cost=0,
                                    buff_type=skill_result[7],
                                    buff_value=skill_result[8] or 0,
                                    buff_duration=skill_result[9] or 0,
                                    buff_target=buff_target,
                                    buff_name=skill_result[12] or "",
                                    description=skill_result[11] or ""
                                ))
                        else:
                            # 融合技能：通过skill_1（存储的是data_skill.id）直接查询buff信息
                            # 获取融合技能的skill_1字段（原基础技能的data_skill.id）
                            await cursor.execute("""
                                SELECT skill_1 FROM user_skill WHERE id = %s
                            """, (skill_id,))
                            fuse_result = await cursor.fetchone()

                            buff_type = None
                            buff_value = 0
                            buff_duration = 0
                            buff_target = 2
                            buff_desc = ""
                            buff_name_result = ""

                            if fuse_result and fuse_result[0]:
                                # 直接通过data_skill.id获取buff信息
                                await cursor.execute("""
                                    SELECT buff_type, buff_value, buff_duration, buff_target, buff_desc, buff_name
                                    FROM data_skill
                                    WHERE id = %s
                                    LIMIT 1
                                """, (fuse_result[0],))
                                buff_result = await cursor.fetchone()
                                if buff_result:
                                    buff_type = buff_result[0]
                                    buff_value = buff_result[1] or 0
                                    buff_duration = buff_result[2] or 0
                                    buff_target = buff_result[3] if buff_result[3] else 2
                                    buff_desc = buff_result[4] or ""
                                    buff_name_result = buff_result[5] or ""

                            target_type = "enemy" if buff_target == 2 else "self"

                            player_skills.append(Skill(
                                id=skill_id,
                                name=skill_name,
                                skill_type=skill_type,
                                target_type=target_type,
                                value=int(float(str(value))) if isinstance(value, str) else value,
                                is_percent=is_percent,
                                item_id=0,
                                cooldown=cooldown or 0,
                                mana_cost=0,
                                buff_type=buff_type,
                                buff_value=buff_value,
                                buff_duration=buff_duration,
                                buff_target=buff_target,
                                buff_name=buff_name_result,
                                description=buff_desc
                            ))

            # 注入本源技能（独立于普通技能槽）
            benyuan_skills = await get_role_benyuan_skills_for_battle(uid, role_id, role_name, cursor)
            for by_skill in benyuan_skills:
                buff_target = by_skill.get('buff_target', 2) or 2
                target_type = "enemy" if buff_target == 2 else "self"
                player_skills.append(Skill(
                    id=by_skill['id'],
                    name=by_skill['skill_name'],
                    skill_type=by_skill['skill_type'],
                    target_type=target_type,
                    value=int(float(str(by_skill['value']))) if isinstance(by_skill['value'], str) else by_skill['value'],
                    is_percent=by_skill['is_percent'],
                    item_id=0,
                    cooldown=by_skill.get('cooldown', 0) or 0,
                    mana_cost=0,
                    buff_type=by_skill.get('buff_type'),
                    buff_value=by_skill.get('buff_value', 0) or 0,
                    buff_duration=by_skill.get('buff_duration', 0) or 0,
                    buff_target=buff_target,
                    buff_name=f"本源·{by_skill['skill_name']}",
                    description=by_skill.get('skill_desc', '')
                ))

            # 生成怪物属性
            player_base_attr = {
                'gongji': final_gongji,
                'fangyu': final_fangyu,
                'qixue': final_qixue,
                'sudu': sudu,
                'baoji': baoji,
                'baoshang': baoshang,
                'shanbi': shanbi,
                'mingzhong': mingzhong
            }

            monster_attr = await generate_monster_attr_by_ratio(
                dungeon['min_level'],
                target_monster,
                role_level,
                progress['wave'],
                player_base_attr,
                is_different_world
            )

            # 创建怪物技能（Boss专属）
            monster_skills = []
            if target_monster['type'] == 'boss' and target_monster['skill_id']:
                boss_skill = await create_monster_skill(target_monster['skill_id'])
                if boss_skill:
                    monster_skills.append(boss_skill)
            boss_mechanics = await get_boss_mechanics(cursor, dungeon_id, target_monster['name']) if target_monster['type'] == 'boss' else []

    # 创建战斗实体（不占用数据库连接）
    player_entity = CombatEntity(role_name, player_role_data, player_skills)
    # P1：出战灵兽以可序列化 Buff 注入战斗快照，重启后不会丢失效果。
    from Game_main.g12_spirit_beast import apply_active_beast_to_entity
    active_beast = await apply_active_beast_to_entity(uid, player_entity)
    monster_attr['entity_type'] = target_monster.get('type', 'normal')  # 'normal' 或 'boss'
    if boss_mechanics:
        monster_attr['boss_mechanics'] = boss_mechanics
    monster_entity = CombatEntity(target_monster['name'], monster_attr, monster_skills)

    # P0：首次挑战只创建可恢复的回合会话；战斗结束后再进入下方既有奖励结算。
    if combat_manager is None:
        from Game_main.g11_battle import get_battle_service, render_battle_panel

        service = get_battle_service()
        active_session = await service.get_active_battle(uid)
        if active_session:
            return render_battle_panel(active_session, "你已有进行中的战斗，请先完成该回合。")
        combat_manager = CombatManager(player_entity, monster_entity, max_rounds=50)
        if active_beast:
            combat_manager._log(
                "spirit_beast",
                f"🐾 出战灵兽「{active_beast['name']}」发动{active_beast['combat_bonus']['label']}，"
                f"获得{active_beast['combat_bonus']['value']}%灵契加成！"
            )
        session = await service.create_battle(
            uid=uid,
            manager=combat_manager,
            battle_type="SOLO_DUNGEON",
            metadata={
                "participants": [uid],
                "dungeon_id": dungeon_id,
                "monster_index": monster_index,
                "monster_name": target_monster["name"],
                "monster_type": target_monster.get("type", "normal"),
            },
        )
        return render_battle_panel(session, f"遭遇 {target_monster['name']}，请选择本回合行动。")

    # 会话已结束，使用快照内的实体与战报走原有结算，确保奖励与历史记录不回归。
    player_entity = combat_manager.player
    monster_entity = combat_manager.enemy
    winner = combat_manager.winner
    combat_logs = combat_manager.combat_log

    # 计算战斗后的血量比例
    final_hp_ratio = player_entity.hp / player_entity.max_hp
    next_hp_ratio = min(1.0, final_hp_ratio + 0.3)

    # 获取战斗摘要
    summary = combat_manager.get_combat_summary()

    # 构建奖励信息
    base_exp = dungeon['reward_exp'] // 15 * EXP_MULTIPLIER
    base_lingshi = dungeon['reward_lingshi'] // 15 * LINGSHI_MULTIPLIER
    monster_bonus = 2.0 if target_monster['type'] == 'boss' else 1.0
    total_exp = int(base_exp * monster_bonus)
    total_lingshi = int(base_lingshi * monster_bonus)

    kill_streak = progress['kill_streak'] + 1
    streak_bonus = 1.0
    for threshold, bonus in KILL_STREAK_REWARDS.items():
        if kill_streak >= threshold:
            streak_bonus = max(streak_bonus, bonus)

    total_exp = int(total_exp * streak_bonus)
    total_lingshi = int(total_lingshi * streak_bonus)

    rewards = {
        'exp': total_exp,
        'lingshi': total_lingshi,
        'kill_streak': kill_streak,
        'streak_bonus': streak_bonus,
        'player_hp': max(0, player_entity.hp),
        'max_hp': player_entity.max_hp,
        'hp_ratio': final_hp_ratio
    }

    # 第二步：根据战斗结果更新数据库
    if winner == player_entity:
        progress_instance = str(progress.get('start_time') or 'unknown')
        reward_battle_key = f"legacy-dungeon:{uid}:{dungeon_id}:{progress_instance}:{progress['wave']}:{monster_index}"
        reward_battle_id = str(uuid5(NAMESPACE_URL, reward_battle_key))
        reward_rng = random.Random(reward_battle_id)
        reward_service = MySQLRewardService()
        reward_items = []
        reward_equipments = []
        drop_specs = []
        item_names = {}
        is_boss = target_monster['type'] == 'boss'
        break_weight = int(combat_manager.boss_tianji.get('reward_weight_bonus', 0)) if is_boss else 0
        if break_weight:
            rewards['boss_break_weight'] = break_weight

        if is_boss:
            if dungeon.get('reward_benyuan') and dungeon.get('rate_benyuan'):
                if reward_rng.randint(1, 100) <= int(dungeon['rate_benyuan']):
                    item_id = int(dungeon['reward_benyuan'])
                    reward_items.append(RewardItem(item_id, 1))
                    drop_specs.append({
                        'item_id': item_id,
                        'item_name': None,
                        'drop_count': 1,
                        'monster_type': 'boss',
                        'render': 'plain',
                    })

            if dungeon.get('reward_skill'):
                skill_ids = [int(s) for s in str(dungeon['reward_skill']).split('|') if s.strip().isdigit()]
                for skill_id in skill_ids:
                    if reward_rng.randint(1, 100) <= int(dungeon.get('rate_skill') or 0):
                        reward_items.append(RewardItem(skill_id, 1))
                        drop_specs.append({
                            'item_id': skill_id,
                            'item_name': None,
                            'drop_count': 1,
                            'monster_type': 'boss',
                            'render': 'scroll',
                        })

        drop_pool_raw = dungeon.get('reward_cl_boss') if is_boss else (dungeon.get('reward_cl_normal') or dungeon.get('reward_cl_boss'))
        if drop_pool_raw:
            cl_item_ids = list(dict.fromkeys(int(s) for s in str(drop_pool_raw).split('|') if s.strip().isdigit()))
            if cl_item_ids:
                selected_ids = reward_rng.sample(cl_item_ids, min(2 if is_boss else 1, len(cl_item_ids)))
                for cl_item_id in selected_ids:
                    drop_count = reward_rng.randint(1, 3)
                    reward_items.append(RewardItem(cl_item_id, drop_count))
                    drop_specs.append({
                        'item_id': cl_item_id,
                        'item_name': None,
                        'drop_count': drop_count,
                        'monster_type': 'boss' if is_boss else 'normal',
                        'render': 'count',
                    })
                if is_boss and break_weight and reward_rng.randint(1, 100) <= min(100, break_weight):
                    bonus_item_id = reward_rng.choice(cl_item_ids)
                    reward_items.append(RewardItem(bonus_item_id, 1))
                    drop_specs.append({
                        'item_id': bonus_item_id, 'item_name': None, 'drop_count': 1,
                        'monster_type': 'boss_break', 'render': 'count',
                    })

        dungeon_completed = progress['wave'] >= progress['total_waves'] and all(
            monster.get('defeated') or monster.get('index') == monster_index
            for monster in progress['monsters']
        )

        if dungeon_completed:
            equip_templates = await get_equip_templates_by_dungeon(dungeon_id)
            if equip_templates:
                selected_template = reward_rng.choice(equip_templates)
                roll = reward_rng.uniform(0, 100)
                quality = '凡品'
                for threshold, q in QUALITY_DROP_RATE:
                    if roll <= threshold:
                        quality = q
                        break
                reward_equipments.append(RewardEquipment(selected_template['id'], quality))
                drop_specs.append({
                    'equip_name': selected_template['name'],
                    'quality': quality,
                    'render': 'equipment',
                })

            if dungeon.get('reward_pojing_dan') and dungeon.get('rate_pojing_dan'):
                if reward_rng.randint(1, 100) <= int(dungeon['rate_pojing_dan']):
                    item_id = int(dungeon['reward_pojing_dan'])
                    reward_items.append(RewardItem(item_id, 1))
                    drop_specs.append({
                        'item_id': item_id,
                        'item_name': None,
                        'drop_count': 1,
                        'monster_type': 'completion',
                        'render': 'plain',
                    })

        item_names = await _get_item_names_by_ids(
            [spec['item_id'] for spec in drop_specs if spec.get('item_id')]
        )

        reward_result = await reward_service.grant_battle_rewards(
            battle_id=reward_battle_id,
            uid=uid,
            role_id=role_id,
            exp=total_exp,
            lingshi=total_lingshi,
            items=reward_items,
            equipments=reward_equipments,
        )

        if reward_result.level_after is not None and reward_result.level_before is not None:
            if reward_result.need_breakthrough:
                rewards['need_breakthrough'] = True
                rewards['current_level'] = reward_result.level_before
            elif reward_result.level_after > reward_result.level_before:
                rewards['level_up'] = True
                rewards['new_level'] = reward_result.level_after
                rewards['add_gongji'] = reward_result.add_gongji
                rewards['add_fangyu'] = reward_result.add_fangyu
                rewards['add_qixue'] = reward_result.add_qixue

        rewards['drops'] = rewards.get('drops', [])
        for spec in drop_specs:
            if spec.get('render') == 'equipment':
                quality_icon = {'凡品': '○', '良品': '◎', '精品': '◆', '仙品': '★', '神品': '✦'}.get(spec['quality'], '○')
                rewards['drops'].append(f"{spec['equip_name']}({quality_icon}{spec['quality']})")
                continue

            item_id = spec['item_id']
            item_name = item_names.get(item_id, f"物品#{item_id}")
            spec['item_name'] = item_name
            if spec.get('render') == 'scroll':
                rewards['drops'].append(f"<qqbot-cmd-input text='卷轴信息 {item_name}' show='卷轴信息 {item_name}' />")
            elif spec.get('render') == 'count':
                rewards['drops'].append(f"{item_name}×{spec['drop_count']}")
            else:
                rewards['drops'].append(item_name)

            await record_dungeon_drop(
                uid,
                dungeon_id,
                target_monster['name'] if spec['monster_type'] != 'completion' else '副本通关',
                spec['monster_type'],
                item_id,
                item_name,
                spec['drop_count'],
                progress['wave'],
            )

        update_result = await update_dungeon_progress(uid, dungeon_id, monster_index, next_hp_ratio, True)

        if update_result and update_result.get('dungeon_completed'):
            await set_dungeon_status(uid, dungeon_id, 'completed')
            rewards['dungeon_completed'] = True
        from Game_main.g16_onboarding import record_onboarding_event
        await record_onboarding_event(uid, "BATTLE")

    else:
        # 战败处理 - 删除副本进度，不归还挑战次数
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                # 删除当前副本进度
                await cursor.execute(
                    "DELETE FROM user_dungeon_progress WHERE uid = %s AND dungeon_id = %s",
                    (uid, dungeon_id)
                )
                await conn.commit()

    # 格式化战斗结果（在所有数据库事务之后）
    monster_type = "Boss" if target_monster['type'] == 'boss' else "普通"
    markdown_content = format_combat_result_markdown(
        winner, role_name, target_monster['name'], monster_type, summary, rewards, dungeon, combat_logs
    )

    # 添加快捷按钮
    if rewards.get('dungeon_completed'):
        markdown_content += "\n\n<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='战斗记录' show='战斗记录' />"
    elif winner == player_entity:
        markdown_content += "\n\n<qqbot-cmd-input text='查看怪物' show='查看怪物' /> | <qqbot-cmd-input text='放弃副本' show='放弃副本' />"
    else:
        # 战败后显示退出副本和重新挑战按钮
        markdown_content += "\n\n挑战失败，已自动退出副本"
        markdown_content += f"\n<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='挑战副本 {dungeon_id}' show='挑战副本 {dungeon_id}' />"

    return {"type": "markdown", "content": markdown_content}


# 放弃副本
@reg_xz_func
async def abandon_dungeon_cmd(uid, qz):
    """放弃副本挑战 - Markdown版本"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT dungeon_id FROM user_dungeon_progress WHERE uid = %s AND status = 'fighting' LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()

            if not result:
                lines = []
                lines.append("当前没有正在进行的副本，请点击[挑战副本]开始挑战吧！")
                lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' /> | <qqbot-cmd-input text='挑战副本' show='挑战副本' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            dungeon_id = result[0]
            dungeon = await get_dungeon_info(dungeon_id)

            await abandon_dungeon(uid, dungeon_id)

            lines = []
            lines.append(f"已放弃**{dungeon['name']}**\n进度已重置")
            lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' /> | <qqbot-cmd-input text='挑战副本' show='挑战副本' />")
            return {"type": "markdown", "content": "\n".join(lines)}


# 战斗记录
@reg_xz_func
async def combat_history(uid, qz, limit=10):
    """查看战斗记录 - Markdown版本"""
    try:
        limit = min(20, max(1, int(limit)))
    except (ValueError, TypeError):
        limit = 10

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT dungeon_id, monster_name, monster_type, drop_item_name, wave, drop_time
                FROM user_dungeon_drop
                WHERE uid = %s
                ORDER BY drop_time DESC
                LIMIT %s
            """
            await cursor.execute(sql, (uid, limit))
            results = await cursor.fetchall()

            if not results:
                lines = []
                lines.append("暂无记录，快去挑战副本吧！")
                lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' /> | <qqbot-cmd-input text='挑战副本' show='挑战副本' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            lines = []
            lines.append(f"**战斗记录** (最近{len(results)}条)")
            lines.append("")

            for dungeon_id, monster_name, monster_type, drop_item_name, wave, drop_time in results:
                result_emoji = "👹" if monster_type == 'boss' else "⚔"
                drop_info = f" 掉:{drop_item_name}" if drop_item_name else ""
                lines.append(f"{result_emoji} {monster_name} 第{wave}波{drop_info}")
                lines.append(f"_{drop_time.strftime('%m-%d %H:%M')}_")
                lines.append("")

            lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='副本信息' show='副本信息' /> | <qqbot-cmd-input text='挑战副本' show='挑战副本' />")

            return {"type": "markdown", "content": "\n".join(lines)}
