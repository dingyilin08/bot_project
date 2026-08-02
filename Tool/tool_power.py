# -*- coding: utf-8 -*-
"""
战力计算工具模块
功能：计算角色综合战力及各分项战力
"""
from typing import Dict, Tuple
from sql.mysql import connect_mysql
from Game_domain.equipment_rules import (
    EQUIPMENT_ENHANCE_BONUS_PER_LEVEL,
    EQUIPMENT_QUALITY_MULTIPLIER,
    EQUIPMENT_SET_BONUS,
)


ATTR_WEIGHTS = {
    'gongji': 1.0,
    'fangyu': 0.8,
    'qixue': 0.1,
    'fali': 0.05,
    'sudu': 2.0,
}

COMBAT_ATTR_WEIGHTS = {
    'baoji': 0.5,
    'baoshang': 0.25,
    'shanbi': 0.3,
    'mingzhong': 0.2,
    'pofang': 0.4,
    'xixue': 0.35,
}

QUALITY_MULTIPLIER = EQUIPMENT_QUALITY_MULTIPLIER
SET_BONUS = EQUIPMENT_SET_BONUS

SKILL_QUALITY_COEF = {'凡': 1, '灵': 2, '玄': 3, '地': 5, '天': 8}

ENHANCE_BONUS_PER_LEVEL = EQUIPMENT_ENHANCE_BONUS_PER_LEVEL


def _number(value) -> float:
    """将 MySQL DECIMAL、整数和空值统一为可参与权重计算的数值。"""
    return float(value or 0)


async def calculate_base_power(role_data: Dict) -> int:
    """
    计算基础战力（属性战力）
    
    Args:
        role_data: 角色数据字典（包含所有属性字段）
    
    Returns:
        基础战力值
    """
    power = 0
    
    power += _number(role_data.get('gongji')) * ATTR_WEIGHTS['gongji']
    power += _number(role_data.get('fangyu')) * ATTR_WEIGHTS['fangyu']
    power += _number(role_data.get('qixue')) * ATTR_WEIGHTS['qixue']
    power += _number(role_data.get('fali')) * ATTR_WEIGHTS['fali']
    power += _number(role_data.get('sudu')) * ATTR_WEIGHTS['sudu']
    
    power += _number(role_data.get('baoji')) * COMBAT_ATTR_WEIGHTS['baoji']
    power += _number(role_data.get('baoshang')) * COMBAT_ATTR_WEIGHTS['baoshang']
    power += _number(role_data.get('shanbi')) * COMBAT_ATTR_WEIGHTS['shanbi']
    power += _number(role_data.get('mingzhong')) * COMBAT_ATTR_WEIGHTS['mingzhong']
    power += _number(role_data.get('pofang')) * COMBAT_ATTR_WEIGHTS['pofang']
    power += _number(role_data.get('xixue')) * COMBAT_ATTR_WEIGHTS['xixue']
    
    return int(power)


async def calculate_level_power(level: int) -> int:
    """
    计算等级战力
    
    Args:
        level: 角色等级
    
    Returns:
        等级战力值
    """
    level = _number(level)
    linear_power = level * 200
    quadratic_power = ((level / 10) ** 2) * 500
    return int(linear_power + quadratic_power)


async def calculate_equip_power(conn, role_id: int, uid: int) -> Tuple[int, Dict]:
    """
    计算装备战力
    
    Args:
        conn: 数据库连接
        role_id: 角色ID
        uid: 玩家ID
    
    Returns:
        (装备战力值, 套装信息字典)
    """
    async with conn.cursor() as cursor:
        await cursor.execute("""
            SELECT ue.id, ue.level, ue.quality,
                   de.base_gongji, de.base_fangyu, de.base_qixue,
                   de.base_fali, de.base_sudu, de.base_baoji, de.base_baoshang,
                   de.base_shanbi, de.base_mingzhong, de.base_pofang, de.base_xixue,
                   de.set_name, de.name, de.part
            FROM user_equip ue
            LEFT JOIN data_equip de ON ue.equip_id = de.id
            WHERE ue.equipped_role_id = %s
        """, (role_id,))
        equipments = await cursor.fetchall()
    
    if not equipments:
        return 0, {}
    
    total_power = 0
    set_counts = {}
    equip_details = []
    
    for equip in equipments:
        equip_id, equip_level, quality = equip[0], _number(equip[1]), equip[2]
        base_gongji, base_fangyu, base_qixue = _number(equip[3]), _number(equip[4]), _number(equip[5])
        base_fali, base_sudu, base_baoji, base_baoshang = _number(equip[6]), _number(equip[7]), _number(equip[8]), _number(equip[9])
        base_shanbi, base_mingzhong, base_pofang, base_xixue = _number(equip[10]), _number(equip[11]), _number(equip[12]), _number(equip[13])
        set_name, equip_name, part = equip[14], equip[15], equip[16]
        
        quality_multi = QUALITY_MULTIPLIER.get(quality, 1.0)
        enhance_multi = 1 + equip_level * ENHANCE_BONUS_PER_LEVEL
        
        attr_power = 0
        attr_power += base_gongji * ATTR_WEIGHTS['gongji']
        attr_power += base_fangyu * ATTR_WEIGHTS['fangyu']
        attr_power += base_qixue * ATTR_WEIGHTS['qixue']
        attr_power += base_fali * ATTR_WEIGHTS['fali']
        attr_power += base_sudu * ATTR_WEIGHTS['sudu']
        attr_power += base_baoji * COMBAT_ATTR_WEIGHTS['baoji']
        attr_power += base_baoshang * COMBAT_ATTR_WEIGHTS['baoshang']
        attr_power += base_shanbi * COMBAT_ATTR_WEIGHTS['shanbi']
        attr_power += base_mingzhong * COMBAT_ATTR_WEIGHTS['mingzhong']
        attr_power += base_pofang * COMBAT_ATTR_WEIGHTS['pofang']
        attr_power += base_xixue * COMBAT_ATTR_WEIGHTS['xixue']
        
        single_power = attr_power * quality_multi * enhance_multi
        total_power += single_power
        
        if set_name:
            set_counts[set_name] = set_counts.get(set_name, 0) + 1
        
        equip_details.append({
            'name': equip_name,
            'part': part,
            'quality': quality,
            'level': equip_level,
            'power': int(single_power)
        })
    
    max_set_bonus = 0
    active_set = None
    for set_name, count in set_counts.items():
        for threshold in [6, 4, 2]:
            if count >= threshold:
                if SET_BONUS[threshold] > max_set_bonus:
                    max_set_bonus = SET_BONUS[threshold]
                    active_set = f"{set_name}({count}件)"
                break
    
    total_power = int(total_power * (1 + max_set_bonus))
    
    set_info = {
        'set_counts': set_counts,
        'active_set': active_set,
        'set_bonus': max_set_bonus,
        'equip_details': equip_details
    }
    
    return total_power, set_info


async def calculate_benyuan_power(conn, role_id: int, uid: int, role_data: Dict) -> int:
    """
    计算本源战力
    
    Args:
        conn: 数据库连接
        role_id: 角色ID
        uid: 玩家ID
        role_data: 角色数据（用于计算百分比加成）
    
    Returns:
        本源战力值
    """
    async with conn.cursor() as cursor:
        await cursor.execute("""
            SELECT ub.dengji, ub.qx_jc, ub.gj_jc, ub.fy_jc, ub.bj_jc, ub.bs_jc,
                   ub.sb_jc, ub.mz_jc, ub.pf_jc, ub.xx_jc
            FROM user_role ur
            LEFT JOIN user_benyuan ub ON ur.by_id = ub.id
            WHERE ur.id = %s AND ur.uid = %s
        """, (role_id, uid))
        benyuan = await cursor.fetchone()
    
    if not benyuan:
        return 0
    
    level_power = _number(benyuan[0]) * 300
    
    attr_power = 0
    
    qx_jc, gj_jc, fy_jc = _number(benyuan[1]), _number(benyuan[2]), _number(benyuan[3])
    bj_jc, bs_jc = _number(benyuan[4]), _number(benyuan[5])
    sb_jc, mz_jc = _number(benyuan[6]), _number(benyuan[7])
    pf_jc, xx_jc = _number(benyuan[8]), _number(benyuan[9])
    
    if qx_jc and qx_jc > 0:
        attr_power += _number(role_data.get('qixue')) * (qx_jc / 100) * ATTR_WEIGHTS['qixue']
    if gj_jc and gj_jc > 0:
        attr_power += _number(role_data.get('gongji')) * (gj_jc / 100) * ATTR_WEIGHTS['gongji']
    if fy_jc and fy_jc > 0:
        attr_power += _number(role_data.get('fangyu')) * (fy_jc / 100) * ATTR_WEIGHTS['fangyu']
    
    if bj_jc:
        attr_power += bj_jc * COMBAT_ATTR_WEIGHTS['baoji']
    if bs_jc:
        attr_power += bs_jc * COMBAT_ATTR_WEIGHTS['baoshang']
    if sb_jc:
        attr_power += sb_jc * COMBAT_ATTR_WEIGHTS['shanbi']
    if mz_jc:
        attr_power += mz_jc * COMBAT_ATTR_WEIGHTS['mingzhong']
    if pf_jc:
        attr_power += pf_jc * COMBAT_ATTR_WEIGHTS['pofang']
    if xx_jc:
        attr_power += xx_jc * COMBAT_ATTR_WEIGHTS['xixue']
    
    return int(level_power + attr_power)


async def calculate_skill_power(conn, role_id: int, uid: int) -> int:
    """
    计算技能战力
    
    Args:
        conn: 数据库连接
        role_id: 角色ID
        uid: 玩家ID
    
    Returns:
        技能战力值
    """
    async with conn.cursor() as cursor:
        await cursor.execute("""
            SELECT us.id, us.skill_name, us.skill_type, us.`value`
            FROM user_role ur
            LEFT JOIN user_skill us ON ur.skill1_id = us.id OR ur.skill2_id = us.id OR ur.skill3_id = us.id
            WHERE ur.id = %s AND ur.uid = %s AND us.id IS NOT NULL
        """, (role_id, uid))
        skills = await cursor.fetchall()
    
    if not skills:
        return 0
    
    total_power = 0
    for skill in skills:
        skill_id, skill_name, skill_type, value = skill
        
        skill_power = 100 + 200
        total_power += skill_power
    
    return int(total_power)


async def calculate_total_power(conn, uid: int, role_id: int) -> Tuple[int, Dict[str, int]]:
    """
    计算总战力及明细
    
    Args:
        conn: 数据库连接
        uid: 玩家ID
        role_id: 角色ID
    
    Returns:
        (总战力, 战力明细字典)
    """
    async with conn.cursor() as cursor:
        await cursor.execute("""
            SELECT dengji, gongji, fangyu, qixue, fali, sudu,
                   baoji, baoshang, shanbi, mingzhong, pofang, xixue,
                   gongji_jc, fangyu_jc, qixue_jc
            FROM user_role
            WHERE uid = %s AND id = %s
        """, (uid, role_id))
        role_data_raw = await cursor.fetchone()
    
    if not role_data_raw:
        return 0, {}
    
    dengji = role_data_raw[0]
    gongji, fangyu, qixue = role_data_raw[1], role_data_raw[2], role_data_raw[3]
    fali, sudu = role_data_raw[4], role_data_raw[5]
    baoji, baoshang = role_data_raw[6], role_data_raw[7]
    shanbi, mingzhong = role_data_raw[8], role_data_raw[9]
    pofang, xixue = role_data_raw[10], role_data_raw[11]
    gongji_jc, fangyu_jc, qixue_jc = role_data_raw[12], role_data_raw[13], role_data_raw[14]
    
    jc_gongji = int(gongji * (gongji_jc / 100)) if gongji_jc else 0
    jc_fangyu = int(fangyu * (fangyu_jc / 100)) if fangyu_jc else 0
    jc_qixue = int(qixue * (qixue_jc / 100)) if qixue_jc else 0
    
    role_data = {
        'dengji': dengji,
        'gongji': gongji + jc_gongji,
        'fangyu': fangyu + jc_fangyu,
        'qixue': qixue + jc_qixue,
        'fali': fali,
        'sudu': sudu,
        'baoji': baoji,
        'baoshang': baoshang,
        'shanbi': shanbi,
        'mingzhong': mingzhong,
        'pofang': pofang,
        'xixue': xixue
    }
    
    power_base = await calculate_base_power(role_data)
    power_level = await calculate_level_power(dengji)
    power_equip, set_info = await calculate_equip_power(conn, role_id, uid)
    power_benyuan = await calculate_benyuan_power(conn, role_id, uid, role_data)
    power_skill = await calculate_skill_power(conn, role_id, uid)
    
    total_power = power_base + power_level + power_equip + power_benyuan + power_skill
    
    power_details = {
        'power': total_power,
        'power_base': power_base,
        'power_level': power_level,
        'power_equip': power_equip,
        'power_benyuan': power_benyuan,
        'power_skill': power_skill,
        'set_info': set_info
    }
    
    return total_power, power_details


async def update_role_power(conn, uid: int) -> int:
    """
    更新玩家战力到数据库（user_zt表），但不提交事务。
    
    Args:
        conn: 数据库连接
        uid: 玩家ID（user_zt.id）
    
    Returns:
        更新后的总战力
    """
    async with conn.cursor() as cursor:
        await cursor.execute("""
            SELECT id, `name` FROM user_role
            WHERE uid = %s AND is_chuzhan = 1
            FOR UPDATE
        """, (uid,))
        current_role = await cursor.fetchone()
    
    if not current_role:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                UPDATE user_zt
                SET power = 0, power_base = 0, power_level = 0,
                    power_equip = 0, power_benyuan = 0, power_skill = 0,
                    power_role_name = '', power_update_time = NOW()
                WHERE id = %s
            """, (uid,))
        return 0
    
    role_id = current_role[0]
    role_name = current_role[1]
    
    total_power, details = await calculate_total_power(conn, uid, role_id)
    
    async with conn.cursor() as cursor:
        await cursor.execute("""
            UPDATE user_zt
            SET power = %s,
                power_base = %s,
                power_level = %s,
                power_equip = %s,
                power_benyuan = %s,
                power_skill = %s,
                power_role_name = %s,
                power_update_time = NOW()
            WHERE id = %s
        """, (
            details['power'],
            details['power_base'],
            details['power_level'],
            details['power_equip'],
            details['power_benyuan'],
            details['power_skill'],
            role_name,
            uid
        ))
    return total_power


async def get_user_power_rank(conn, uid: int) -> Tuple[int, int]:
    """
    获取玩家战力排名
    
    Args:
        conn: 数据库连接
        uid: 玩家ID
    
    Returns:
        (排名, 总玩家数)
    """
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT power FROM user_zt WHERE id = %s", (uid,))
        result = await cursor.fetchone()
        if not result or result[0] == 0:
            return 0, 0
        my_power = result[0]
        
        await cursor.execute("""
            SELECT COUNT(*) + 1 as rank
            FROM user_zt
            WHERE power > %s
        """, (my_power,))
        rank_row = await cursor.fetchone()
        my_rank = rank_row[0]
        
        await cursor.execute("SELECT COUNT(*) as total FROM user_zt WHERE power > 0")
        total_row = await cursor.fetchone()
        total_players = total_row[0]
        
        return my_rank, total_players


async def get_power_ranking(conn, rank_type: str = '全服', limit: int = 20) -> list:
    """
    获取战力排行榜
    
    Args:
        conn: 数据库连接
        rank_type: 排行榜类型（全服/角色名）
        limit: 返回数量
    
    Returns:
        排行榜列表
    """
    async with conn.cursor() as cursor:
        if rank_type == '全服':
            sql = """
                SELECT id, `name`, power_role_name, power
                FROM user_zt
                WHERE power > 0
                ORDER BY power DESC
                LIMIT %s
            """
            await cursor.execute(sql, (limit,))
        else:
            sql = """
                SELECT id, `name`, power_role_name, power
                FROM user_zt
                WHERE power_role_name = %s AND power > 0
                ORDER BY power DESC
                LIMIT %s
            """
            await cursor.execute(sql, (rank_type, limit))
        
        results = await cursor.fetchall()
        
        ranking = []
        for row in results:
            ranking.append({
                'uid': row[0],
                'name': row[1],
                'role_name': row[2],
                'power': row[3]
            })
        
        return ranking
