# -*- coding: utf-8 -*-
"""
波次副本系统
- 挑战副本随机生成5个怪物（含1个Boss）
- 共3波，第3波含2个Boss
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

# 导入战斗系统
from Tool.combat_system import (
    CombatManager, CombatEntity, Skill, Buff,
    create_skill_from_db, create_combat_entity
)


# ================================
# 配置参数
# ================================

# 每日免费挑战次数
FREE_DAILY_CHALLENGES = 5

# 波次难度递增系数（调整后更平滑）
WAVE_DIFFICULTY_MULTIPLIER = {
    1: 1.0,   # 第1波：基准难度
    2: 1.08,  # 第2波：+8%难度
    3: 1.18   # 第3波：+18%难度（含2Boss）
}

# Boss掉落概率（百分比）
BOSS_DROP_RATE = 30

# 连杀奖励阈值
KILL_STREAK_REWARDS = {
    3: 1.1,    # 连杀3个：奖励+10%
    5: 1.2,    # 连杀5个：奖励+20%
    10: 1.35,  # 连杀10个：奖励+35%
    15: 1.5    # 连杀15个：奖励+50%
}

# 经验灵石倍率（让玩家快速升级，提升爽感）
# 1级升10级需75000经验，5次副本完成，每次需15000经验
# 副本1基础reward_exp=100，15个怪物约100经验，需要150倍
EXP_LINGSHI_MULTIPLIER = 150  # 经验灵石获得倍率


# ================================
# 数据库操作函数
# ================================

async def get_role_base_attr(role_name):
    """获取角色基础属性"""
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


async def get_dungeon_monsters_by_type(dungeon_id, monster_type='normal'):
    """获取指定类型的怪物列表（用于随机生成）"""
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


async def get_dungeon_info(dungeon_id):
    """获取副本信息"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT id, name, world, min_level, min_stage, description,
                       reward_exp, reward_lingshi, reward_benyuan, rate_benyuan,
                       reward_skill, rate_skill
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
                    'rate_skill': result[11]
                }
            return None


async def get_dungeon_list_by_level(level=0):
    """获取副本列表"""
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


async def create_monster_skill(skill_id):
    """为Boss创建技能"""
    if not skill_id:
        return None

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT id, skill_name, skill_type, value, is_percent,
                       mana_cost, cooldown, buff_type, buff_value,
                       buff_duration, buff_target
                FROM data_skill
                WHERE id = %s
                LIMIT 1
            """
            await cursor.execute(sql, (skill_id,))
            result = await cursor.fetchone()

            if result:
                return Skill(
                    id=result[0],
                    name=result[1],
                    skill_type=result[2],
                    target_type="enemy" if result[10] == 2 else "self",
                    value=result[3],
                    is_percent=result[4],
                    cooldown=result[6] or 0,
                    mana_cost=result[5] or 0,
                    buff_type=result[7],
                    buff_value=result[8] or 0,
                    buff_duration=result[9] or 0,
                    buff_target=result[10] or 2,
                )
            return None


# ================================
# 玩家副本进度管理
# ================================

async def get_player_dungeon_progress(uid, dungeon_id):
    """获取玩家在副本中的进度"""
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


async def create_dungeon_progress(uid, dungeon_id, wave=1):
    """创建新的副本进度并生成怪物"""
    # 获取副本的所有怪物
    normal_monsters = await get_dungeon_monsters_by_type(dungeon_id, 'normal')
    boss_monsters = await get_dungeon_monsters_by_type(dungeon_id, 'boss')

    if not normal_monsters or not boss_monsters:
        return None

    # 生成当前波次的怪物列表
    monsters = []

    # 第3波：2个Boss + 3个普通怪物
    if wave == 3:
        # 取min(2, 可用Boss数量)
        boss_count = min(2, len(boss_monsters))
        normal_count = min(3, len(normal_monsters))
        selected_bosses = random.sample(boss_monsters, boss_count) if boss_count > 0 else []
        selected_normals = random.sample(normal_monsters, normal_count) if normal_count > 0 else []
        monsters = selected_bosses + selected_normals
    else:
        # 第1、2波：1个Boss + 4个普通怪物
        boss_count = min(1, len(boss_monsters))
        normal_count = min(4, len(normal_monsters))
        selected_boss = random.sample(boss_monsters, boss_count) if boss_count > 0 else []
        selected_normals = random.sample(normal_monsters, normal_count) if normal_count > 0 else []
        monsters = selected_boss + selected_normals

    # 如果怪物不足5个，用重复的怪物补齐（使用深拷贝）
    import copy
    while len(monsters) < 5:
        # 优先补充普通怪物
        if len(normal_monsters) > 0:
            new_monster = copy.deepcopy(random.choice(normal_monsters))
            monsters.append(new_monster)
        # 再补充Boss
        elif len(boss_monsters) > 0:
            new_monster = copy.deepcopy(random.choice(boss_monsters))
            monsters.append(new_monster)
        else:
            break

    # 打乱顺序
    random.shuffle(monsters)

    # 标记怪物状态并转换为JSON可序列化的格式
    for i, monster in enumerate(monsters):
        monster['index'] = i + 1
        monster['defeated'] = False
        # 将Decimal类型转换为float
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


async def update_dungeon_progress(uid, dungeon_id, monster_index, player_hp_ratio, won):
    """更新副本进度"""
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
        # 进入下一波或完成
        if progress['wave'] < progress['total_waves']:
            # 进入下一波
            return await create_dungeon_progress(uid, dungeon_id, progress['wave'] + 1)
        else:
            # 完成所有波次
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


async def set_dungeon_status(uid, dungeon_id, status):
    """设置副本状态"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "UPDATE user_dungeon_progress SET status = %s WHERE uid = %s AND dungeon_id = %s"
            await cursor.execute(sql, (status, uid, dungeon_id))
            await conn.commit()


async def abandon_dungeon(uid, dungeon_id):
    """放弃副本挑战"""
    await set_dungeon_status(uid, dungeon_id, 'abandoned')


async def get_daily_challenge_count(uid, dungeon_id):
    """获取今日挑战次数"""
    from datetime import date
    today = date.today()

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT challenge_count, sweep_count FROM user_dungeon_daily
                WHERE uid = %s AND dungeon_id = %s AND date = %s
                LIMIT 1
            """
            await cursor.execute(sql, (uid, dungeon_id, today))
            result = await cursor.fetchone()

            if result:
                return result[0], result[1]
            return 0, 0


async def increment_daily_challenge(uid, dungeon_id):
    """增加今日挑战次数"""
    from datetime import date
    today = date.today()

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                INSERT INTO user_dungeon_daily (uid, dungeon_id, date, challenge_count)
                VALUES (%s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE challenge_count = challenge_count + 1
            """
            await cursor.execute(sql, (uid, dungeon_id, today))
            await conn.commit()


async def record_dungeon_drop(uid, dungeon_id, monster_name, monster_type, drop_item_id, drop_item_name, drop_count, wave):
    """记录副本掉落"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                INSERT INTO user_dungeon_drop
                (uid, dungeon_id, monster_name, monster_type, drop_item_id, drop_item_name, drop_count, wave)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            await cursor.execute(sql, (uid, dungeon_id, monster_name, monster_type, drop_item_id, drop_item_name, drop_count, wave))
            await conn.commit()


# ================================
# 怪物属性生成
# ================================

async def generate_monster_attr_by_ratio(dungeon_level, monster_data, player_level, wave, player_role_attr=None):
    """
    根据怪物倍率数据生成实际怪物属性
    使用副本等级基准属性，确保难度适中

    参数:
        dungeon_level: 副本等级
        monster_data: 怪物数据（包含倍率）
        player_level: 玩家等级
        wave: 当前波次
        player_role_attr: 玩家角色属性（仅用于参考，不直接作为基准）
    """
    # 基础属性：根据副本等级计算的"标准角色"属性
    # 这样可以保证不同角色的游戏体验一致
    base_gongji = 800 + (dungeon_level * 120)
    base_fangyu = 600 + (dungeon_level * 100)
    base_qixue = 3500 + (dungeon_level * 500)
    base_sudu = 90 + (dungeon_level * 5)
    base_baoji = 800
    base_baoshang = 5000
    base_shanbi = 500
    base_mingzhong = 1000

    # 波次难度系数（调整后的更合理的值）
    wave_multiplier = WAVE_DIFFICULTY_MULTIPLIER.get(wave, 1.0)

    # 获取怪物倍率
    hp_ratio = float(monster_data.get('hp_ratio', 1.0))
    atk_ratio = float(monster_data.get('atk_ratio', 1.0))
    def_ratio = float(monster_data.get('def_ratio', 1.0))
    spd_ratio = float(monster_data.get('spd_ratio', 1.0))
    crit_ratio = float(monster_data.get('crit_ratio', 1.0))
    crit_dmg_ratio = float(monster_data.get('crit_dmg_ratio', 1.0))
    dodge_ratio = float(monster_data.get('dodge_ratio', 1.0))
    hit_ratio = float(monster_data.get('hit_ratio', 1.0))

    # 计算怪物属性
    # 普通怪物：标准属性 * 倍率 * 波次系数
    # Boss：额外加成
    hp = int(base_qixue * hp_ratio * wave_multiplier)
    attack = int(base_gongji * atk_ratio * wave_multiplier)
    defense = int(base_fangyu * def_ratio * wave_multiplier)
    speed = int(base_sudu * spd_ratio * wave_multiplier)
    crit = int(base_baoji * crit_ratio * wave_multiplier)
    crit_dmg = int(base_baoshang * crit_dmg_ratio * wave_multiplier)
    dodge = int(base_shanbi * dodge_ratio * wave_multiplier)
    hit = int(base_mingzhong * hit_ratio * wave_multiplier)

    # Boss额外加成
    if monster_data.get('type') == 'boss':
        hp = int(hp * 1.3)      # Boss血量+30%
        attack = int(attack * 1.2)  # Boss攻击+20%
        defense = int(defense * 1.15)  # Boss防御+15%

    # 确保属性在合理范围内
    # 攻击力不能太高，否则会秒杀玩家
    max_attack = int(base_gongji * 1.5)  # 最高1.5倍基础攻击
    attack = min(attack, max_attack)

    return {
        'qixue': max(500, hp),
        'gongji': max(80, attack),
        'fangyu': max(60, defense),
        'sudu': max(50, speed),
        'baoji': max(300, crit),
        'baoshang': max(100, crit_dmg),
        'shanbi': max(300, dodge),
        'mingzhong': max(800, hit),
        'pofang': 0,
        'xixue': 0,
        'max_fali': 100
    }


# ================================
# 副本系统功能函数
# ================================

@reg_xz_func
async def dungeon_list(uid, qz, page=1):
    """查看副本列表"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                return qz + "您当前没有出战角色，无法查看副本列表。\n请先使用[出战 角色编号]指令出战角色。"

            role_id, role_name, role_level, role_world = role_result

            # 获取可挑战的副本
            dungeons = await get_dungeon_list_by_level(level=role_level)

            if not dungeons:
                return qz + f"当前没有适合您角色等级[{role_level}级]的副本。\n请继续升级后查看。"

            # 分页显示
            page_size = 5
            page = max(1, int(page) if isinstance(page, (int, str)) and str(page).isdigit() else 1)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_dungeons = dungeons[start_idx:end_idx]
            total_pages = (len(dungeons) + page_size - 1) // page_size

            output = f"【副本列表】（第{page}/{total_pages}页）\n"
            output += f"当前角色：[{role_id}]{role_name} Lv.{role_level}\n"
            output += f"可挑战世界：{role_world}\n"
            output += f"每日免费挑战：{FREE_DAILY_CHALLENGES}次\n"

            for dungeon in page_dungeons:
                can_challenge = dungeon['min_level'] <= role_level
                status = "[✓可挑战]" if can_challenge else "[✗等级不足]"

                # 获取今日挑战次数
                challenge_count, _ = await get_daily_challenge_count(uid, dungeon['id'])
                remaining = max(0, FREE_DAILY_CHALLENGES - challenge_count)

                output += f"┌────────────────────────────────┐\n"
                output += f"│ [{dungeon['id']}] {dungeon['name']} {status}\n"
                output += f"│ 世界：{dungeon['world']} | 等级要求：{dungeon['min_level']}级+\n"
                output += f"│ 今日剩余：{remaining}次\n"
                output += f"└────────────────────────────────┘\n"

            kj = await all_write_cmd(uid, [
                ("副本信息", 1),
                ("挑战副本", 1),
                ("放弃副本", 0),
                ("当前角色", 0)
            ])

            return qz + output + kj


@reg_xz_func
async def dungeon_info(uid, qz, dungeon_id):
    """查看副本详细信息"""
    try:
        dungeon_id = int(dungeon_id)
    except (ValueError, TypeError):
        return qz + "副本ID格式错误，请输入正确的副本ID。\n示例：副本信息 1"

    dungeon = await get_dungeon_info(dungeon_id)
    if dungeon is None:
        return qz + f"副本ID [{dungeon_id}] 不存在，请检查副本ID是否正确。"

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = "SELECT id, `name`, dengji FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                return qz + "您当前没有出战角色。\n请先使用[出战 角色编号]指令出战角色。"

            role_id, role_name, role_level = role_result

            can_challenge = dungeon['min_level'] <= role_level
            challenge_count, _ = await get_daily_challenge_count(uid, dungeon_id)

            output = f"【{dungeon['name']}】详细信息\n"
            output += f"════════════════════════════════\n"
            output += f"副本ID：{dungeon['id']} | 世界：{dungeon['world']}\n"
            output += f"等级要求：{dungeon['min_level']}级+ | 境界要求：{dungeon['min_stage']}\n"
            output += f"您的等级：{role_level}级 | 今日已挑战：{challenge_count}次\n"
            output += f"挑战状态：{'✓ 可挑战' if can_challenge else '✗ 等级不符'}\n"
            output += f"════════════════════════════════\n"
            output += f"副本描述：\n{dungeon['description']}\n"
            output += f"════════════════════════════════\n"
            output += f"【挑战规则】\n"
            output += f"· 每次挑战生成3波怪物，每波5个\n"
            output += f"· 第1-2波：4个普通 + 1个Boss\n"
            output += f"· 第3波：3个普通 + 2个Boss\n"
            output += f"· 战胜怪物获得经验灵石\n"
            output += f"· Boss可掉落本源材料和技能卷轴\n"
            output += f"════════════════════════════════\n"
            output += f"【通关奖励】\n"
            # 显示应用倍率后的实际奖励（单次挑战约15个怪物）
            actual_exp = dungeon['reward_exp'] * EXP_LINGSHI_MULTIPLIER
            actual_lingshi = dungeon['reward_lingshi'] * EXP_LINGSHI_MULTIPLIER
            output += f"· 经验值：约{actual_exp} (单次挑战)\n"
            output += f"· 灵石：约{actual_lingshi} (单次挑战)\n"

            kj = await all_write_cmd(uid, [
                ("挑战副本", 1),
                ("副本列表", 0),
                ("当前角色", 0)
            ])

            return qz + output + kj


@reg_xz_func
async def challenge_dungeon(uid, qz):
    """开始挑战副本"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = """SELECT id, `name`, dengji, gongji, fangyu, qixue, sudu, baoji, baoshang,
                     shanbi, mingzhong, pofang, xixue, fali, gongji_jc, fangyu_jc, qixue_jc,
                     skill1_id, skill2_id, world
                     FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"""
            await cursor.execute(sql, (uid,))
            role_data = await cursor.fetchone()

            if role_data is None:
                return qz + "您当前没有出战角色，无法挑战副本。\n请先使用[出战 角色编号]指令出战角色。"

            (role_id, role_name, role_level, gongji, fangyu, qixue, sudu, baoji, baoshang,
             shanbi, mingzhong, pofang, xixue, fali, gongji_jc, fangyu_jc, qixue_jc,
             skill1_id, skill2_id, role_world) = role_data

            # 检查是否有正在进行的副本
            sql = "SELECT dungeon_id FROM user_dungeon_progress WHERE uid = %s AND status = 'fighting' LIMIT 1"
            await cursor.execute(sql, (uid,))
            existing = await cursor.fetchone()

            if existing:
                dungeon_id = existing[0]
                dungeon = await get_dungeon_info(dungeon_id)
                return qz + f"您正在进行【{dungeon['name']}】的挑战！\n请使用[放弃副本]结束当前挑战后再开始新的挑战。\n\n发送[查看怪物]可查看当前波次的怪物列表。"

            output = f"【副本挑战】\n"
            output += f"════════════════════════════════\n"
            output += f"请输入要挑战的副本ID：\n\n"

            # 获取可挑战的副本列表
            dungeons = await get_dungeon_list_by_level(level=role_level)

            for dungeon in dungeons[:10]:  # 最多显示10个
                can_challenge = dungeon['min_level'] <= role_level
                challenge_count, _ = await get_daily_challenge_count(uid, dungeon['id'])
                remaining = max(0, FREE_DAILY_CHALLENGES - challenge_count)

                if remaining > 0 and can_challenge:
                    output += f"[{dungeon['id']}] {dungeon['name']} - 剩余{remaining}次\n"
                else:
                    output += f"[{dungeon['id']}] {dungeon['name']} - 不可用\n"

            output += f"\n请使用[挑战副本 副本ID]开始挑战\n"
            output += f"例如：挑战副本 1"

            kj = await all_write_cmd(uid, [
                ("副本列表", 0),
                ("当前角色", 0)
            ])

            return qz + output + kj


@reg_xz_func
async def start_challenge_dungeon(uid, qz, dungeon_id):
    """开始挑战指定副本"""
    try:
        dungeon_id = int(dungeon_id)
    except (ValueError, TypeError):
        return qz + "副本ID格式错误，请输入正确的副本ID。\n示例：挑战副本 1"

    dungeon = await get_dungeon_info(dungeon_id)
    if dungeon is None:
        return qz + f"副本ID [{dungeon_id}] 不存在。"

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                return qz + "您当前没有出战角色。\n请先使用[出战 角色编号]指令出战角色。"

            role_id, role_name, role_level, role_world = role_result

            # 检查等级限制
            if role_level < dungeon['min_level']:
                return qz + f"您的角色等级不符合挑战要求。\n需要等级：{dungeon['min_level']}级+\n您的等级：{role_level}级"

            # 检查世界匹配
            if role_world != dungeon['world']:
                return qz + f"您的角色世界不匹配此副本。\n副本世界：{dungeon['world']}\n您的角色世界：{role_world}"

            # 检查挑战次数
            challenge_count, _ = await get_daily_challenge_count(uid, dungeon_id)
            if challenge_count >= FREE_DAILY_CHALLENGES:
                return qz + f"今日挑战次数已用完！\n每日免费挑战次数：{FREE_DAILY_CHALLENGES}次\n明日重置。"

            # 增加挑战次数
            await increment_daily_challenge(uid, dungeon_id)

            # 创建副本进度（生成第一波怪物）
            progress = await create_dungeon_progress(uid, dungeon_id, 1)

            if not progress:
                return qz + "副本怪物数据初始化失败，请联系管理员。"

            return await show_monster_list(uid)


@reg_xz_func
async def show_monster_list(uid, qz):
    """查看当前波次怪物列表"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT dungeon_id FROM user_dungeon_progress WHERE uid = %s AND status = 'fighting' LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()

            if not result:
                return qz + "您当前没有正在进行的副本挑战。\n请使用[挑战副本]开始新的挑战。"

            dungeon_id = result[0]

    progress = await get_player_dungeon_progress(uid, dungeon_id)
    dungeon = await get_dungeon_info(dungeon_id)

    output = f"【{dungeon['name']}】第{progress['wave']}波怪物\n"
    output += f"════════════════════════════════\n"
    output += f"已击败：{progress['defeated_count']}/5 | 连杀：{progress['kill_streak']}\n"
    output += f"════════════════════════════════\n"

    for monster in progress['monsters']:
        status = "✓已击败" if monster['defeated'] else "未挑战"
        monster_type = "Boss" if monster['type'] == 'boss' else "普通"
        if monster['defeated']:
            output += f"×. {monster['name']} [{monster_type}] - {status}\n"
        else:
            output += f"→. [{monster['index']}] {monster['name']} [{monster_type}] - {status}\n"

    output += f"════════════════════════════════\n"
    output += f"发送[挑战怪物 编号]开始战斗\n"
    output += f"例如：挑战怪物 1\n"
    output += f"发送[放弃副本]可放弃当前挑战\n"

    kj = await all_write_cmd(uid, [
        ("挑战副本", 1),
        ("放弃副本", 0),
        ("当前角色", 0)
    ])

    return qz + output + kj


@reg_xz_func
async def fight_monster(uid, qz, monster_index):
    """挑战指定怪物"""
    try:
        monster_index = int(monster_index)
    except (ValueError, TypeError):
        return qz + "怪物编号格式错误，请输入正确的编号。\n示例：挑战怪物 1"

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT dungeon_id FROM user_dungeon_progress WHERE uid = %s AND status = 'fighting' LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()

            if not result:
                return qz + "您当前没有正在进行的副本挑战。\n请使用[挑战副本]开始新的挑战。"

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
        return qz + f"怪物编号 [{monster_index}] 不存在。\n请使用[查看怪物]查看当前波次怪物列表。"

    if target_monster['defeated']:
        return qz + f"该怪物已经被击败了！\n请选择其他未挑战的怪物。"

    # 获取玩家角色数据
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """SELECT id, `name`, dengji, gongji, fangyu, qixue, sudu, baoji, baoshang,
                     shanbi, mingzhong, pofang, xixue, fali, gongji_jc, fangyu_jc, qixue_jc,
                     skill1_id, skill2_id
                     FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"""
            await cursor.execute(sql, (uid,))
            role_data = await cursor.fetchone()

            if role_data is None:
                return qz + "您当前没有出战角色，无法挑战副本。\n请先使用[出战 角色编号]指令出战角色。"

            (role_id, role_name, role_level, gongji, fangyu, qixue, sudu, baoji, baoshang,
             shanbi, mingzhong, pofang, xixue, fali, gongji_jc, fangyu_jc, qixue_jc,
             skill1_id, skill2_id) = role_data

            # 计算角色实际属性（含本源加成）
            final_gongji = int(gongji * (1 + gongji_jc / 100))
            final_fangyu = int(fangyu * (1 + fangyu_jc / 100))
            final_qixue = int(qixue * (1 + qixue_jc / 100))

            # 应用血量继承（根据上一场战斗的血量比例）
            hp_ratio = progress['player_hp_ratio']
            current_qixue = int(final_qixue * hp_ratio)
            current_qixue = max(current_qixue, int(final_qixue * 0.3))  # 最多保留30%血量

            # 构建玩家战斗数据
            player_role_data = {
                'name': role_name,
                'qixue': current_qixue,
                'gongji': final_gongji,
                'fangyu': final_fangyu,
                'sudu': sudu,
                'baoji': baoji,
                'baoshang': baoshang,
                'shanbi': shanbi,
                'mingzhong': mingzhong,
                'pofang': pofang,
                'xixue': xixue,
                'max_fali': fali
            }

            # 获取玩家技能
            player_skills = []
            for skill_id in [skill1_id, skill2_id]:
                if skill_id:
                    await cursor.execute("SELECT * FROM user_skill WHERE id = %s", (skill_id,))
                    skill_result = await cursor.fetchone()
                    if skill_result:
                        player_skills.append(Skill(
                            id=skill_result[0],
                            name=skill_result[2],
                            skill_type=skill_result[3],
                            target_type="enemy",
                            value=int(float(str(skill_result[4]))) if isinstance(skill_result[4], str) else skill_result[4],
                            is_percent=skill_result[5],
                            cooldown=0,
                            mana_cost=0
                        ))

            # 生成怪物属性（基于玩家实际属性）
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
                player_base_attr
            )

            # 创建怪物技能（Boss专属）
            monster_skills = []
            if target_monster['type'] == 'boss' and target_monster['skill_id']:
                boss_skill = await create_monster_skill(target_monster['skill_id'])
                if boss_skill:
                    monster_skills.append(boss_skill)

            # 创建战斗实体
            player_entity = CombatEntity(role_name, player_role_data, player_skills)
            monster_entity = CombatEntity(target_monster['name'], monster_attr, monster_skills)

            # 开始战斗
            combat_manager = CombatManager(player_entity, monster_entity, max_rounds=50)
            winner, combat_logs = combat_manager.start_combat()

            # 计算战斗后的血量比例
            final_hp_ratio = player_entity.hp / player_entity.max_hp
            # 战斗后恢复30%血量
            next_hp_ratio = min(1.0, final_hp_ratio + 0.3)

            # 获取战斗摘要
            summary = combat_manager.get_combat_summary()

            # 构建返回结果
            output = f"【战斗结果】\n"
            output += f"════════════════════════════════\n"
            output += f"挑战怪物：{target_monster['name']} ({'Boss' if target_monster['type'] == 'boss' else '普通'})\n"
            output += f"战斗回合：{summary['total_rounds']}回合\n"
            output += f"════════════════════════════════\n"

            if winner == player_entity:
                output += f"🏆 恭喜！[{role_name}] 成功击败了 {target_monster['name']}！\n\n"

                # 计算基础奖励（应用经验倍率让玩家爽）
                base_exp = dungeon['reward_exp'] // 15 * EXP_LINGSHI_MULTIPLIER  # 应用倍率
                base_lingshi = dungeon['reward_lingshi'] // 15 * EXP_LINGSHI_MULTIPLIER

                # Boss额外奖励
                monster_bonus = 2.0 if target_monster['type'] == 'boss' else 1.0
                total_exp = int(base_exp * monster_bonus)
                total_lingshi = int(base_lingshi * monster_bonus)

                # 连杀奖励加成
                kill_streak = progress['kill_streak'] + 1
                streak_bonus = 1.0
                for threshold, bonus in KILL_STREAK_REWARDS.items():
                    if kill_streak >= threshold:
                        streak_bonus = max(streak_bonus, bonus)

                total_exp = int(total_exp * streak_bonus)
                total_lingshi = int(total_lingshi * streak_bonus)

                output += f"获得奖励：\n"
                output += f"· 经验值：+{total_exp}"
                if streak_bonus > 1.0:
                    output += f" (连杀x{kill_streak}加成{int(streak_bonus*100)-100}%)"
                output += f"\n"
                output += f"· 灵石：+{total_lingshi}\n"

                # 应用经验奖励
                await cursor.execute(
                    "UPDATE user_role SET exp = exp + %s WHERE id = %s",
                    (total_exp, role_id)
                )

                # 添加灵石奖励
                await cursor.execute(
                    "UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s",
                    (total_lingshi, uid)
                )

                # 检查是否升级
                await cursor.execute("SELECT dengji, exp FROM user_role WHERE id = %s", (role_id,))
                new_dengji, new_exp = await cursor.fetchone()
                max_exp = await up_need_exp(new_dengji)

                if new_exp >= max_exp and new_dengji < 100:
                    add_gongji, add_fangyu, add_qixue = await up_lvl(role_id, max_exp)
                    output += f"\n✨ 恭喜升级！等级提升至 {new_dengji + 1} 级\n"
                    output += f"属性提升：攻击+{add_gongji} 防御+{add_fangyu} 气血+{add_qixue}\n"

                # Boss掉落处理
                if target_monster['type'] == 'boss':
                    drops = []
                    # 本源材料掉落
                    if dungeon['reward_benyuan'] and dungeon['rate_benyuan']:
                        if random.randint(1, 100) <= dungeon['rate_benyuan']:
                            drops.append(('本源材料', dungeon['reward_benyuan']))

                    # 技能卷轴掉落
                    if dungeon['reward_skill']:
                        skill_ids = [int(s) for s in dungeon['reward_skill'].split('|') if s.strip().isdigit()]
                        for skill_id in skill_ids:
                            if random.randint(1, 100) <= dungeon['rate_skill']:
                                await cursor.execute("SELECT name FROM data_item WHERE id = %s LIMIT 1", (skill_id,))
                                item_result = await cursor.fetchone()
                                if item_result:
                                    drops.append(('技能卷轴', skill_id))

                    # 处理掉落
                    for drop_type, drop_id in drops:
                        if drop_type == '本源材料':
                            await cursor.execute("SELECT name FROM data_item WHERE id = %s LIMIT 1", (drop_id,))
                            item_name = await cursor.fetchone()
                            if item_name:
                                item_name = item_name[0]
                                await add_bag_item(uid, drop_id, 1)
                                output += f"\n🎁 获得掉落：{item_name}\n"
                                await record_dungeon_drop(uid, dungeon_id, target_monster['name'], 'boss', drop_id, item_name, 1, progress['wave'])
                        elif drop_type == '技能卷轴':
                            await cursor.execute("SELECT name FROM data_item WHERE id = %s LIMIT 1", (drop_id,))
                            item_name = await cursor.fetchone()
                            if item_name:
                                item_name = item_name[0]
                                await add_bag_item(uid, drop_id, 1)
                                output += f"\n🎁 获得掉落：{item_name}\n"
                                await record_dungeon_drop(uid, dungeon_id, target_monster['name'], 'boss', drop_id, item_name, 1, progress['wave'])

                    if not drops:
                        output += f"\n本次未获得额外掉落，再接再厉！\n"

                # 更新副本进度
                update_result = await update_dungeon_progress(uid, dungeon_id, monster_index, next_hp_ratio, True)

                if update_result and update_result.get('dungeon_completed'):
                    # 完成所有波次
                    output += f"\n{'='*20} 副本通关 {'='*20}\n"
                    output += f"🎉 恭喜！您成功通关了【{dungeon['name']}】！\n"
                    output += f"总击杀：{progress['total_kills'] + 1}\n"
                    await set_dungeon_status(uid, dungeon_id, 'completed')

                await conn.commit()

            else:
                output += f"💀 遗憾！[{role_name}] 被 {target_monster['name']} 击败了...\n\n"
                output += f"挑战失败，未能获得奖励。\n"
                output += f"请提升实力后重新挑战！\n"

                # 战败后血量恢复到30%
                await update_dungeon_progress(uid, dungeon_id, monster_index, 0.3, False)
                if monster_entity.hp < 0:
                    monster_entity.hp = 0
                if player_entity.hp < 0:
                    player_entity.hp = 0

            output += f"════════════════════════════════\n"
            output += f"剩余生命：{player_entity.hp}/{player_entity.max_hp} ({int(final_hp_ratio*100)}%)\n"
            output += f"敌方生命：{monster_entity.hp}/{monster_entity.max_hp}\n"

            kj = await all_write_cmd(uid, [
                ("查看怪物", 0),
                ("挑战副本", 1),
                ("放弃副本", 0),
                ("当前角色", 0)
            ])

            return qz + output + kj


@reg_xz_func
async def abandon_dungeon_cmd(uid, qz):
    """放弃副本挑战"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT dungeon_id FROM user_dungeon_progress WHERE uid = %s AND status = 'fighting' LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()

            if not result:
                return qz + "您当前没有正在进行的副本挑战。"

            dungeon_id = result[0]
            dungeon = await get_dungeon_info(dungeon_id)

            await abandon_dungeon(uid, dungeon_id)

            return qz + f"您已放弃【{dungeon['name']}】的挑战。\n副本进度已重置，下次挑战将重新开始。"


@reg_xz_func
async def combat_history(uid, qz, limit=10):
    """查看战斗记录"""
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
                return qz + "您暂时还没有战斗记录。\n快去挑战副本吧！"

            output = f"【战斗记录】（最近{len(results)}条）\n"
            output += f"════════════════════════════════\n"

            for dungeon_id, monster_name, monster_type, drop_item_name, wave, drop_time in results:
                result_emoji = "🏆" if monster_type == 'boss' else "⚔"
                drop_info = f" 掉落:{drop_item_name}" if drop_item_name else ""
                output += f"{result_emoji} {monster_name} - 第{wave}波{drop_info}\n"
                output += f"   时间：{drop_time.strftime('%m-%d %H:%M')}\n"

            kj = await all_write_cmd(uid, [
                ("副本列表", 0),
                ("挑战副本", 1),
                ("当前角色", 0)
            ])

            return qz + output + kj
