# -*- coding: utf-8 -*-
"""
装备系统核心代码
功能：装备背包、穿戴/卸下、强化、详情、副本掉落、战斗属性集成
"""

import asyncio
import random
from sql.mysql import *
from Tool.tool_user import *
from func.pd_func import *
from config import IMG_BASE_URL

# ================================
# 常量定义
# ================================

# 品质图标与倍率
QUALITY_ICON = {
    '凡品': '○',
    '良品': '◎',
    '精品': '◆',
    '仙品': '★',
    '神品': '✦'
}

QUALITY_MULTIPLIER = {
    '凡品': 1.0,
    '良品': 1.3,
    '精品': 1.8,
    '仙品': 2.5,
    '神品': 3.5
}

# 品质掉落概率
QUALITY_DROP_RATE = [
    (55, '凡品'),
    (82, '良品'),
    (95, '精品'),
    (99.5, '仙品'),
    (100, '神品')
]

# 强化成功率
ENHANCE_SUCCESS_RATE = {
    1: 100, 2: 90, 3: 80, 4: 70, 5: 55,
    6: 40, 7: 30, 8: 20, 9: 12, 10: 8
}

# 强化保底：连续失败N次后下次必定成功
ENHANCE_PITY = {
    5: 4,
    6: 5,
    7: 6,
    8: 8,
    9: 12,
    10: 18
}

# 强化消耗基础值（按装备所属副本等级缩放）
ENHANCE_BASE_COST = {
    # min_level: 基础消耗（强化+1的消耗，后续每级 ×level）
    1:   500,
    10:  1500,
    20:  4000,
    30:  10000,
    40:  25000,
    50:  60000,
    60:  130000,
    70:  280000,
    80:  600000,
    90:  1200000,
}

# 装备出售基础价（按装备等级档位）
EQUIP_SELL_BASE_PRICE = {
    1: 75,
    10: 225,
    20: 600,
    30: 1500,
    40: 3750,
    50: 9000,
    60: 19500,
    70: 42000,
    80: 90000,
    90: 180000,
}

# 强化返还比例
EQUIP_SELL_ENHANCE_REFUND_RATE = 0.85

def get_enhance_cost(equip_min_level, target_level):
    """计算强化消耗 = 基础消耗 × 目标等级"""
    sorted_keys = sorted(ENHANCE_BASE_COST.keys(), reverse=True)
    base_cost = ENHANCE_BASE_COST[1]  # 默认
    for key in sorted_keys:
        if equip_min_level >= key:
            base_cost = ENHANCE_BASE_COST[key]
            break
    return base_cost * target_level


def get_equip_sell_base_price(equip_min_level):
    """获取装备出售基础价（按装备最低等级匹配档位）"""
    sorted_keys = sorted(EQUIP_SELL_BASE_PRICE.keys(), reverse=True)
    base_price = EQUIP_SELL_BASE_PRICE[1]
    for key in sorted_keys:
        if equip_min_level >= key:
            base_price = EQUIP_SELL_BASE_PRICE[key]
            break
    return base_price


def get_enhance_total_cost(equip_min_level, enhance_level):
    """计算装备当前强化等级累计消耗"""
    enhance_level = max(0, int(enhance_level))
    total_cost = 0
    for target_level in range(1, enhance_level + 1):
        total_cost += get_enhance_cost(equip_min_level, target_level)
    return total_cost


def calc_equip_sell_info(equip_min_level, quality, enhance_level):
    """计算装备出售价格明细"""
    quality_multiplier = QUALITY_MULTIPLIER.get(quality, 1.0)
    base_price = int(round(get_equip_sell_base_price(equip_min_level) * quality_multiplier))
    enhance_total_cost = get_enhance_total_cost(equip_min_level, enhance_level)
    enhance_refund = int(round(enhance_total_cost * EQUIP_SELL_ENHANCE_REFUND_RATE))
    return {
        'base_price': base_price,
        'enhance_total_cost': enhance_total_cost,
        'enhance_refund': enhance_refund,
        'total_price': base_price + enhance_refund
    }

# 强化加成
ENHANCE_BONUS_PER_LEVEL = 0.1  # 每级加成10%基础属性

# 套装加成
SET_BONUS = {
    2: 0.20,  # 2件套+20%
    4: 0.40,  # 4件套+40%
    6: 0.60   # 6件套+60%
}

# 部位图标与中文名
PART_ICON = {
    'weapon': f'![text #20px #20px]({IMG_BASE_URL}/wuqi.png)',
    'helmet': f'![text #20px #20px]({IMG_BASE_URL}/toukui.png)',
    'armor': f'![text #20px #20px]({IMG_BASE_URL}/kaijia.png)',
    'pants': f'![text #20px #20px]({IMG_BASE_URL}/hutui.png)',
    'shoes': f'![text #20px #20px]({IMG_BASE_URL}/xiezi.png)',
    'accessory': f'![text #20px #20px]({IMG_BASE_URL}/shipin.png)'
}

PART_CN = {
    'weapon': '武器',
    'helmet': '头盔',
    'armor': '铠甲',
    'pants': '护腿',
    'shoes': '鞋子',
    'accessory': '饰品'
}

PART_EN = {
    '武器': 'weapon',
    '头盔': 'helmet',
    '铠甲': 'armor',
    '护腿': 'pants',
    '鞋子': 'shoes',
    '饰品': 'accessory'
}

PAGE_SIZE = 6

PART_COLUMN_MAP = {
    'weapon': 'equip_weapon',
    'helmet': 'equip_helmet',
    'armor': 'equip_armor',
    'pants': 'equip_pants',
    'shoes': 'equip_shoes',
    'accessory': 'equip_accessory'
}


# ================================
# 数据库操作函数（内部函数）
# ================================

# 查询装备模板
async def get_equip_template(equip_id):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT id, name, set_name, set_id, dungeon_id, world, part,
                       base_gongji, base_fangyu, base_qixue, base_fali, base_sudu,
                       base_baoji, base_baoshang, base_shanbi, base_mingzhong, base_pofang, base_xixue, min_level
                FROM data_equip
                WHERE id = %s
                LIMIT 1
            """
            await cursor.execute(sql, (equip_id,))
            result = await cursor.fetchone()

            if result:
                return {
                    'id': result[0],
                    'name': result[1],
                    'set_name': result[2],
                    'set_id': result[3],
                    'dungeon_id': result[4],
                    'world': result[5],
                    'part': result[6],
                    'base_gongji': result[7],
                    'base_fangyu': result[8],
                    'base_qixue': result[9],
                    'base_fali': result[10],
                    'base_sudu': result[11],
                    'base_baoji': result[12],
                    'base_baoshang': result[13],
                    'base_shanbi': result[14],
                    'base_mingzhong': result[15],
                    'base_pofang': result[16],
                    'base_xixue': result[17],
                    'min_level': result[18]
                }
            return None


async def get_equip_templates_by_dungeon(dungeon_id):
    """查询副本对应的装备模板列表"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT id, name, set_name, set_id, part, world, min_level
                FROM data_equip
                WHERE dungeon_id = %s
            """
            await cursor.execute(sql, (dungeon_id,))
            results = await cursor.fetchall()

            return [{
                'id': row[0],
                'name': row[1],
                'set_name': row[2],
                'set_id': row[3],
                'part': row[4],
                'world': row[5],
                'min_level': row[6]
            } for row in results]


async def get_user_equip(equip_instance_id, cursor=None):
    """查询玩家装备实例"""
    async def _do_query(cur):
        sql = """
            SELECT ue.id, ue.uid, ue.equip_id, ue.level, ue.quality, ue.enhance_fail_count, ue.is_equipped, ue.equipped_role_id,
                   de.name, de.set_name, de.part, de.min_level,
                   de.base_gongji, de.base_fangyu, de.base_qixue, de.base_fali, de.base_sudu,
                   de.base_baoji, de.base_baoshang, de.base_shanbi, de.base_mingzhong, de.base_pofang, de.base_xixue,
                   ue.create_time
            FROM user_equip ue
            JOIN data_equip de ON ue.equip_id = de.id
            WHERE ue.id = %s
            LIMIT 1
        """
        await cur.execute(sql, (equip_instance_id,))
        result = await cur.fetchone()

        if result:
            return {
                'id': result[0],
                'uid': result[1],
                'equip_id': result[2],
                'level': result[3],
                'quality': result[4],
                'enhance_fail_count': result[5],
                'is_equipped': result[6],
                'equipped_role_id': result[7],
                'template_name': result[8],
                'set_name': result[9],
                'part': result[10],
                'min_level': result[11],
                'base_gongji': result[12],
                'base_fangyu': result[13],
                'base_qixue': result[14],
                'base_fali': result[15],
                'base_sudu': result[16],
                'base_baoji': result[17],
                'base_baoshang': result[18],
                'base_shanbi': result[19],
                'base_mingzhong': result[20],
                'base_pofang': result[21],
                'base_xixue': result[22],
                'create_time': result[23]
            }
        return None

    if cursor:
        return await _do_query(cursor)
    else:
        async with connect_mysql() as conn:
            async with conn.cursor() as cur:
                return await _do_query(cur)


async def get_user_equip_list(uid, page=1, page_size=6):
    """分页查询玩家装备列表"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 查询总数
            sql_count = "SELECT COUNT(*) FROM user_equip WHERE uid = %s"
            await cursor.execute(sql_count, (uid,))
            total_count = (await cursor.fetchone())[0]

            # 分页查询
            offset = (page - 1) * page_size
            sql = """
                SELECT ue.id, ue.equip_id, ue.level, ue.quality, ue.is_equipped, ue.equipped_role_id,
                       de.name, de.set_name, de.part, de.min_level,
                       de.base_gongji, de.base_fangyu, de.base_qixue, de.base_fali, de.base_sudu,
                       de.base_baoji, de.base_baoshang, de.base_shanbi, de.base_mingzhong, de.base_pofang, de.base_xixue
                FROM user_equip ue
                JOIN data_equip de ON ue.equip_id = de.id
                WHERE ue.uid = %s
                ORDER BY ue.id DESC
                LIMIT %s OFFSET %s
            """
            await cursor.execute(sql, (uid, page_size, offset))
            results = await cursor.fetchall()

            equipments = []
            for row in results:
                equipments.append({
                    'id': row[0],
                    'equip_id': row[1],
                    'level': row[2],
                    'quality': row[3],
                    'is_equipped': row[4],
                    'equipped_role_id': row[5],
                    'template_name': row[6],
                    'set_name': row[7],
                    'part': row[8],
                    'min_level': row[9],
                    'base_gongji': row[10],
                    'base_fangyu': row[11],
                    'base_qixue': row[12],
                    'base_fali': row[13],
                    'base_sudu': row[14],
                    'base_baoji': row[15],
                    'base_baoshang': row[16],
                    'base_shanbi': row[17],
                    'base_mingzhong': row[18],
                    'base_pofang': row[19],
                    'base_xixue': row[20]
                })

            return equipments, total_count


async def create_user_equip(uid, equip_id, quality):
    """创建装备实例（副本掉落时调用）"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                INSERT INTO user_equip (uid, equip_id, level, quality, is_equipped)
                VALUES (%s, %s, 0, %s, 0)
            """
            await cursor.execute(sql, (uid, equip_id, quality))
            await conn.commit()

            # 返回新创建的装备实例ID
            return cursor.lastrowid


async def get_role_equipped_items(role_id):
    """获取角色已穿戴的所有装备"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT ue.id, ue.equip_id, ue.level, ue.quality,
                       de.name, de.set_name, de.part, de.min_level,
                       de.base_gongji, de.base_fangyu, de.base_qixue, de.base_fali, de.base_sudu,
                       de.base_baoji, de.base_baoshang, de.base_shanbi, de.base_mingzhong, de.base_pofang, de.base_xixue
                FROM user_equip ue
                JOIN data_equip de ON ue.equip_id = de.id
                WHERE ue.equipped_role_id = %s
            """
            await cursor.execute(sql, (role_id,))
            results = await cursor.fetchall()

            equipments = []
            for row in results:
                equipments.append({
                    'id': row[0],
                    'equip_id': row[1],
                    'level': row[2],
                    'quality': row[3],
                    'template_name': row[4],
                    'set_name': row[5],
                    'part': row[6],
                    'min_level': row[7],
                    'base_gongji': row[8],
                    'base_fangyu': row[9],
                    'base_qixue': row[10],
                    'base_fali': row[11],
                    'base_sudu': row[12],
                    'base_baoji': row[13],
                    'base_baoshang': row[14],
                    'base_shanbi': row[15],
                    'base_mingzhong': row[16],
                    'base_pofang': row[17],
                    'base_xixue': row[18]
                })

            return equipments


def calc_equip_final_attrs(equip_instance):
    """计算单件装备最终属性（基础×品质×强化）"""
    quality = equip_instance['quality']
    level = equip_instance['level']
    quality_multiplier = QUALITY_MULTIPLIER.get(quality, 1.0)
    enhance_multiplier = 1 + (level * ENHANCE_BONUS_PER_LEVEL)

    final_attrs = {
        'gongji': int(equip_instance['base_gongji'] * quality_multiplier * enhance_multiplier),
        'fangyu': int(equip_instance['base_fangyu'] * quality_multiplier * enhance_multiplier),
        'qixue': int(equip_instance['base_qixue'] * quality_multiplier * enhance_multiplier),
        'fali': int(equip_instance['base_fali'] * quality_multiplier * enhance_multiplier),
        'sudu': int(equip_instance['base_sudu'] * quality_multiplier * enhance_multiplier),
        'baoji': int(equip_instance['base_baoji'] * quality_multiplier * enhance_multiplier),
        'baoshang': int(equip_instance['base_baoshang'] * quality_multiplier * enhance_multiplier),
        'shanbi': int(equip_instance['base_shanbi'] * quality_multiplier * enhance_multiplier),
        'mingzhong': int(equip_instance['base_mingzhong'] * quality_multiplier * enhance_multiplier),
        'pofang': int(equip_instance['base_pofang'] * quality_multiplier * enhance_multiplier),
        'xixue': int(equip_instance['base_xixue'] * quality_multiplier * enhance_multiplier)
    }

    return final_attrs


async def calc_role_equip_bonus(role_id):
    """计算角色装备总加成（含套装效果）"""
    equipments = await get_role_equipped_items(role_id)

    if not equipments:
        return {
            'gongji': 0, 'fangyu': 0, 'qixue': 0, 'fali': 0,
            'sudu': 0, 'baoji': 0, 'baoshang': 0, 'shanbi': 0,
            'mingzhong': 0, 'pofang': 0, 'xixue': 0,
            'set_info': []
        }

    # 累加所有装备的最终属性
    base_bonus = {
        'gongji': 0, 'fangyu': 0, 'qixue': 0, 'fali': 0,
        'sudu': 0, 'baoji': 0, 'baoshang': 0, 'shanbi': 0,
        'mingzhong': 0, 'pofang': 0, 'xixue': 0
    }

    set_count = {}  # 统计同套装件数

    for equip in equipments:
        final_attrs = calc_equip_final_attrs(equip)

        # 累加到基础加成
        for attr in base_bonus:
            base_bonus[attr] += final_attrs[attr]

        # 统计套装件数
        set_name = equip['set_name']
        set_count[set_name] = set_count.get(set_name, 0) + 1

    # 确定套装加成（取最高档，不叠加）
    max_set_bonus = 0
    set_info = []

    for set_name, count in set_count.items():
        if count >= 6:
            max_set_bonus = max(max_set_bonus, SET_BONUS[6])
            set_info.append(f"{set_name}({count}件)")
        elif count >= 4:
            max_set_bonus = max(max_set_bonus, SET_BONUS[4])
            set_info.append(f"{set_name}({count}件)")
        elif count >= 2:
            max_set_bonus = max(max_set_bonus, SET_BONUS[2])
            set_info.append(f"{set_name}({count}件)")

    # 应用套装加成
    final_bonus = {}
    for attr in base_bonus:
        final_bonus[attr] = int(base_bonus[attr] * (1 + max_set_bonus))

    final_bonus['set_info'] = set_info
    final_bonus['set_bonus_pct'] = int(max_set_bonus * 100)

    return final_bonus


# ================================
# Markdown格式化函数
# ================================

def format_equip_bag_markdown(equipments, page, total_pages, role_info):
    """格式化装备背包"""
    lines = []
    lines.append(f"##### 装备背包 ({page}/{total_pages}页)")
    lines.append(f"**当前角色：** [{role_info['id']}] {role_info['name']} Lv.{role_info['level']}")
    lines.append("***")

    if not equipments:
        lines.append("> 你的装备背包空空如也")
        lines.append("> 快去挑战副本获取装备吧！")
    else:
        for equip in equipments:
            quality_icon = QUALITY_ICON.get(equip['quality'], '○')

            lines.append(f"**[{equip['id']}] {equip['template_name']}** {quality_icon}{equip['quality']}+{equip['level']}\n")

            if equip['is_equipped']:
                lines.append(f"> <qqbot-cmd-input text='卸下装备 {PART_CN.get(equip['part'])}' show='卸下装备 {PART_CN.get(equip['part'])}' /> <qqbot-cmd-input text='装备详情 {equip['id']}' show='装备详情 {equip['id']}' /> <qqbot-cmd-input text='强化装备 {equip['id']}' show='强化装备 {equip['id']}' />\n")
            else:
                lines.append(f"> <qqbot-cmd-input text='穿戴装备 {equip['id']}' show='穿戴装备 {equip['id']}' /> <qqbot-cmd-input text='装备详情 {equip['id']}' show='装备详情 {equip['id']}' /> <qqbot-cmd-input text='强化装备 {equip['id']}' show='强化装备 {equip['id']}' /> <qqbot-cmd-input text='出售装备 {equip['id']}' show='出售装备 {equip['id']}' />\n")

    if total_pages > 1:
        prev_page = page - 1 if page > 1 else 1
        next_page = page + 1 if page < total_pages else page
        lines.append(f"<qqbot-cmd-input text='装备背包 {prev_page}' show='装备背包 {prev_page}' /> | <qqbot-cmd-input text='装备背包' show='跳转[页码]' /> | <qqbot-cmd-input text='装备背包 {next_page}' show='装备背包 {next_page}' />\n")

    lines.append("***")

    lines.append(f"<qqbot-cmd-input text='当前装备' show='当前装备' /> | <qqbot-cmd-input text='当前角色' show='当前角色' /> | <qqbot-cmd-input text='角色背包' show='角色背包' />")

    return "\n".join(lines)


def format_current_equip_markdown(role_info, equipped_items, equip_bonus):
    """格式化当前装备"""
    lines = []
    lines.append(f"##### 当前装备")
    lines.append(f"**角色：** [{role_info['id']}] {role_info['name']} Lv.{role_info['level']}")
    lines.append("***")

    # 装备槽位
    lines.append("**装备槽位**")

    # 创建装备槽位字典
    equip_slots = {}
    for item in equipped_items:
        equip_slots[item['part']] = item

    slot_order = ['weapon', 'helmet', 'armor', 'pants', 'shoes', 'accessory']
    for part in slot_order:
        part_icon = PART_ICON[part]
        part_cn = PART_CN[part]
        if part in equip_slots:
            equip = equip_slots[part]
            quality_icon = QUALITY_ICON.get(equip['quality'], '○')
            lines.append(f"> {part_icon} {part_cn}：{equip['template_name']} {quality_icon}{equip['quality']}+{equip['level']}")
        else:
            lines.append(f"> {part_icon} {part_cn}：[空]")

    # 套装效果
    lines.append("")
    lines.append("**套装效果**")
    if equip_bonus['set_info']:
        set_bonus_pct = equip_bonus.get('set_bonus_pct', 0)
        if set_bonus_pct > 0:
            lines.append(f"> {'、'.join(equip_bonus['set_info'])}：全属性+{set_bonus_pct}%")
        else:
            lines.append("> 未激活任何套装效果")
    else:
        lines.append("> 未激活任何套装效果")

    # 装备总加成
    lines.append("")
    lines.append("**装备加成**")
    attrs = []
    if equip_bonus['gongji'] > 0:
        attrs.append(f"攻击+{equip_bonus['gongji']}")
    if equip_bonus['fangyu'] > 0:
        attrs.append(f"防御+{equip_bonus['fangyu']}")

    if equip_bonus['qixue'] > 0:
        attrs.append(f"气血+{equip_bonus['qixue']}")
    if equip_bonus['fali'] > 0:
        attrs.append(f"法力+{equip_bonus['fali']}")

    if equip_bonus['sudu'] > 0:
        attrs.append(f"速度+{equip_bonus['sudu']}")
    if equip_bonus['shanbi'] > 0:
        attrs.append(f"闪避+{equip_bonus['shanbi']}")

    if equip_bonus['baoji'] > 0:
        attrs.append(f"暴击+{equip_bonus['baoji']}")
    if equip_bonus['baoshang'] > 0:
        attrs.append(f"暴伤+{equip_bonus['baoshang']}")

    if equip_bonus['mingzhong'] > 0:
        attrs.append(f"命中+{equip_bonus['mingzhong']}")
    if equip_bonus['pofang'] > 0:
        attrs.append(f"破防+{equip_bonus['pofang']}")

    if equip_bonus['xixue'] > 0:
        attrs.append(f"吸血+{equip_bonus['xixue']}")

    if attrs:
        for i in range(0, len(attrs), 2):
            lines.append(' | '.join(attrs[i:i+2]))
    else:
        lines.append("无装备加成")

    lines.append("***")
    lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='收回' show='收回' />")

    return "\n".join(lines)


def format_wear_result_markdown(role_info, equip, old_equip=None, attrs_change=None):
    """格式化穿戴结果"""
    lines = []

    if old_equip:
        lines.append("##### 装备替换")
        lines.append(f"**角色：** [{role_info['id']}] {role_info['name']} Lv.{role_info['level']}")
        lines.append("***")
        lines.append("**卸下装备**")
        old_quality_icon = QUALITY_ICON.get(old_equip['quality'], '○')
        part_icon = PART_ICON.get(old_equip['part'])
        lines.append(f">{part_icon} ~~{old_equip['template_name']}~~ {old_quality_icon}{old_equip['quality']}+{old_equip['level']}")
        lines.append("> _已放回装备背包_")
        lines.append("")
        lines.append("**穿戴装备**")
        new_quality_icon = QUALITY_ICON.get(equip['quality'], '○')
        lines.append(f">{part_icon} **{equip['template_name']}** {new_quality_icon}{equip['quality']}+{equip['level']}")
        lines.append(f"> _已成功穿戴到{PART_CN.get(equip['part'], equip['part'])}槽_")
    else:
        lines.append("##### ✅ 穿戴成功")
        lines.append(f"**角色：** [{role_info['id']}] {role_info['name']} Lv.{role_info['level']}")
        lines.append("***")
        lines.append("**装备信息**")
        part_icon = PART_ICON.get(equip['part'])
        quality_icon = QUALITY_ICON.get(equip['quality'], '○')
        lines.append(f">{part_icon} **{equip['template_name']}** {quality_icon}{equip['quality']}+{equip['level']}")
        lines.append("**穿戴结果**")
        lines.append(f"> 已成功穿戴到{PART_CN.get(equip['part'], equip['part'])}槽")

    lines.append("")
    lines.append("**属性变化**")
    if attrs_change:
        changes = []
        if attrs_change.get('gongji', 0) != 0:
            changes.append(f"攻击{attrs_change['gongji']:+}")
        if attrs_change.get('fangyu', 0) != 0:
            changes.append(f"防御{attrs_change['fangyu']:+}")
        if attrs_change.get('qixue', 0) != 0:
            changes.append(f"气血{attrs_change['qixue']:+}")
        if attrs_change.get('fali', 0) != 0:
            changes.append(f"法力{attrs_change['fali']:+}")
        if attrs_change.get('sudu', 0) != 0:
            changes.append(f"速度{attrs_change['sudu']:+}")
        if attrs_change.get('baoji', 0) != 0:
            changes.append(f"暴击{attrs_change['baoji']:+}")
        if attrs_change.get('baoshang', 0) != 0:
            changes.append(f"暴伤{attrs_change['baoshang']:+}")
        if attrs_change.get('shanbi', 0) != 0:
            changes.append(f"闪避{attrs_change['shanbi']:+}")
        if attrs_change.get('mingzhong', 0) != 0:
            changes.append(f"命中{attrs_change['mingzhong']:+}")
        if attrs_change.get('pofang', 0) != 0:
            changes.append(f"破防{attrs_change['pofang']:+}")
        if attrs_change.get('xixue', 0) != 0:
            changes.append(f"吸血{attrs_change['xixue']:+}")

        lines.append(f"{' | '.join(changes)}")

    lines.append("***")
    lines.append("<qqbot-cmd-input text='当前装备' show='当前装备' /> | <qqbot-cmd-input text='装备背包' show='装备背包' />")

    return "\n".join(lines)


def format_remove_result_markdown(role_info, equip, final_bonus):
    """格式化卸下结果"""
    lines = []
    lines.append("##### 卸下成功")
    lines.append(f"**角色：** [{role_info['id']}] {role_info['name']} Lv.{role_info['level']}")
    lines.append("***")

    lines.append("**卸下装备**")
    part_icon = PART_ICON.get(equip['part'])
    quality_icon = QUALITY_ICON.get(equip['quality'], '○')
    lines.append(f">{part_icon} **{equip['template_name']}** {quality_icon}{equip['quality']}+{equip['level']}")
    lines.append("> 已放回装备背包")

    lines.append("")
    lines.append("**属性变化**")
    changes = []
    if final_bonus['gongji'] < 0:
        changes.append(f"攻击{final_bonus['gongji']}")
    if final_bonus['fangyu'] < 0:
        changes.append(f"防御{final_bonus['fangyu']}")
    if final_bonus['qixue'] < 0:
        changes.append(f"气血{final_bonus['qixue']}")
    if final_bonus['fali'] < 0:
        changes.append(f"法力{final_bonus['fali']}")
    if final_bonus['sudu'] < 0:
        changes.append(f"速度{final_bonus['sudu']}")
    if final_bonus['baoji'] < 0:
        changes.append(f"暴击{final_bonus['baoji']}")
    if final_bonus['baoshang'] < 0:
        changes.append(f"暴伤{final_bonus['baoshang']}")
    if final_bonus['shanbi'] < 0:
        changes.append(f"闪避{final_bonus['shanbi']}")
    if final_bonus['mingzhong'] < 0:
        changes.append(f"命中{final_bonus['mingzhong']}")
    if final_bonus['pofang'] < 0:
        changes.append(f"破防{final_bonus['pofang']}")
    if final_bonus.get('xixue', 0) < 0:
        changes.append(f"吸血{final_bonus['xixue']}")

    if changes:
        lines.append(f"{' | '.join(changes)}")
    else:
        lines.append("> 无属性变化")

    lines.append("***")
    lines.append("<qqbot-cmd-input text='当前装备' show='当前装备' /> | <qqbot-cmd-input text='装备背包' show='装备背包' />")

    return "\n".join(lines)


def format_enhance_result_markdown(role_info, equip, success, new_level, old_attrs, new_attrs, cost_lingshi, current_lingshi):
    """格式化强化结果"""
    lines = []

    if success:
        lines.append("##### ✨ 强化成功")
    else:
        lines.append("##### 💔 强化失败")

    part_icon = PART_ICON.get(equip['part'])
    quality_icon = QUALITY_ICON.get(equip['quality'], '○')
    lines.append(f"**装备：** {part_icon} {equip['template_name']} {quality_icon}{equip['quality']}")

    lines.append("***")

    lines.append("**强化结果**")
    if success:
        if new_level >= 10:
            lines.append(f"> 强化等级：+{new_level} (MAX)")
        else:
            lines.append(f"> 强化等级：+{equip['level']} ➜ +{new_level}")
    else:
        lines.append(f"> 强化等级：+{equip['level']} (保持不变)")
        lines.append("")
        lines.append("> 强化失败了！装备等级不变")
        if equip['level'] < 10:
            next_rate = ENHANCE_SUCCESS_RATE.get(equip['level'] + 1, 0)
            lines.append(f"> 下次成功率为{next_rate}%")

    lines.append("")
    lines.append("**属性变化**")
    changes = []
    for attr in ['gongji', 'fangyu', 'qixue', 'fali', 'sudu', 'baoji', 'baoshang', 'shanbi', 'mingzhong', 'pofang', 'xixue']:
        if old_attrs[attr] != new_attrs[attr]:
            attr_cn = {'gongji': '攻击', 'fangyu': '防御', 'qixue': '气血', 'fali': '法力',
                       'sudu': '速度', 'baoji': '暴击', 'baoshang': '暴伤', 'shanbi': '闪避',
                       'mingzhong': '命中', 'pofang': '破防', 'xixue': '吸血'}.get(attr, attr)
            diff = new_attrs[attr] - old_attrs[attr]
            changes.append(f"{attr_cn}：{old_attrs[attr]} ➜ {new_attrs[attr]} ({diff:+})")

    if changes:
        lines.extend(f"> {change}" for change in changes)
    else:
        lines.append("> 属性无变化")

    lines.append("")
    lines.append("**消耗**")
    lines.append(f"> 灵石-{cost_lingshi}")
    lines.append("")
    lines.append(f"**当前灵石：** {current_lingshi}")

    lines.append("***")
    if equip['level'] < 10:
        lines.append("<qqbot-cmd-input text='强化装备 {}' show='强化装备 {}' /> | <qqbot-cmd-input text='装备详情 {}' show='装备详情 {}' />".format(equip['id'], equip['id']))
    else:
        lines.append("<qqbot-cmd-input text='装备详情 {}' show='装备详情 {}' /> | <qqbot-cmd-input text='当前装备' show='当前装备' />".format(equip['id']))

    return "\n".join(lines)


def format_sell_result_markdown(role_info, equip, sell_info, current_lingshi):
    """格式化出售装备结果"""
    lines = []
    lines.append("##### 💰 出售成功")
    if role_info:
        lines.append(f"**当前角色：** [{role_info['id']}] {role_info['name']} Lv.{role_info['level']}")
    lines.append("***")

    part_icon = PART_ICON.get(equip['part'], '📦')
    quality_icon = QUALITY_ICON.get(equip['quality'], '○')
    lines.append(f"**出售装备**")
    lines.append(f"> {part_icon} {equip['template_name']} {quality_icon}{equip['quality']}+{equip['level']}")

    lines.append("")
    lines.append("**回收明细**")
    lines.append(f"> 基础回收：{sell_info['base_price']}灵石")
    if equip['level'] > 0:
        lines.append(f"> 强化返还：{sell_info['enhance_refund']}灵石 (按85%计算)")
    else:
        lines.append("> 强化返还：0灵石")
    lines.append(f"> 本次获得：{sell_info['total_price']}灵石")

    lines.append("")
    lines.append(f"**当前灵石：** {current_lingshi}")
    lines.append("***")
    lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='当前装备' show='当前装备' />")

    return "\n".join(lines)


def format_equip_detail_markdown(equip, final_attrs, role_info=None, equipped_info=None):
    """格式化装备详情"""
    lines = []
    part_icon = PART_ICON.get(equip['part'], '📦')
    quality_icon = QUALITY_ICON.get(equip['quality'], '○')

    lines.append(f"##### 📋 装备详情")
    lines.append(f"**装备：** [{equip['id']}] {part_icon} {equip['template_name']} {quality_icon}{equip['quality']}+{equip['level']}")
    lines.append("***")

    lines.append("**基础信息**")
    lines.append(f"> 所属套装：{equip['set_name']}")
    lines.append(f"> 装备部位：{PART_CN.get(equip['part'], equip['part'])}")
    lines.append(f"> 等级要求：Lv.{equip['min_level']}")
    lines.append(f"> 强化等级：+{equip['level']}/10")

    lines.append("")
    lines.append("**属性明细**")

    # quality_multiplier = QUALITY_MULTIPLIER.get(equip['quality'], 1.0)
    # enhance_multiplier = 1 + (equip['level'] * ENHANCE_BONUS_PER_LEVEL)

    attrs_list = [
        ('攻击', 'base_gongji'), ('防御', 'base_fangyu'), ('气血', 'base_qixue'), ('法力', 'base_fali'),
        ('速度', 'base_sudu'), ('暴击', 'base_baoji'), ('暴伤', 'base_baoshang'),
        ('闪避', 'base_shanbi'), ('命中', 'base_mingzhong'), ('破防', 'base_pofang'), ('吸血', 'base_xixue')
    ]

    for attr_cn, attr_key in attrs_list:
        base_val = equip[attr_key]
        if base_val > 0:
            final_val = final_attrs[attr_key.replace('base_', '')]
            # quality_pct = int((quality_multiplier - 1) * 100)
            # enhance_pct = int((enhance_multiplier - 1) * 100)
            lines.append(f"> {attr_cn}: {final_val}")

    lines.append("")
    lines.append("**套装信息**")
    lines.append(f"> 套装名称：{equip['set_name']}")
    lines.append("> 套装效果：")
    lines.append(f"> - 2件套：全属性+{int(SET_BONUS[2]*100)}%")
    lines.append(f"> - 4件套：全属性+{int(SET_BONUS[4]*100)}%")
    lines.append(f"> - 6件套：全属性+{int(SET_BONUS[6]*100)}%")
    lines.append("> _注：多套装效果不叠加，仅生效最高档位_")

    lines.append("")
    lines.append("**状态信息**")
    sell_info = calc_equip_sell_info(equip['min_level'], equip['quality'], equip['level'])
    if equipped_info:
        lines.append(f"> 穿戴状态：已穿戴")
        lines.append(f"> 穿戴角色：[{equipped_info['id']}] {equipped_info['name']} Lv.{equipped_info['level']}")
    else:
        lines.append("> 穿戴状态：未穿戴")

    lines.append(f"> 获得时间：{equip['create_time'].strftime('%Y-%m-%d %H:%M') if hasattr(equip['create_time'], 'strftime') else equip['create_time']}")
    lines.append("")
    lines.append("**出售预估**")
    lines.append(f"> 基础回收：{sell_info['base_price']}灵石")
    if equip['level'] > 0:
        lines.append(f"> 强化返还：{sell_info['enhance_refund']}灵石 (按85%计算)")
    else:
        lines.append("> 强化返还：0灵石")
    lines.append(f"> 预计总回收：{sell_info['total_price']}灵石")

    lines.append("***")

    if not equipped_info:
        lines.append("<qqbot-cmd-input text='穿戴装备 {}' show='穿戴装备 {}' /> | <qqbot-cmd-input text='强化装备 {}' show='强化装备 {}' /> | <qqbot-cmd-input text='出售装备 {}' show='出售装备 {}' /> | <qqbot-cmd-input text='装备背包' show='装备背包' />".format(equip['id'], equip['id'], equip['id']))
    else:
        lines.append("<qqbot-cmd-input text='卸下装备 {}' show='卸下装备 {}' /> | <qqbot-cmd-input text='强化装备 {}' show='强化装备 {}' /> | <qqbot-cmd-input text='装备背包' show='装备背包' />".format(PART_CN.get(equip['part'], equip['part']), equip['id']))

    return "\n".join(lines)


# ================================
# 玩家指令函数
# ================================

@reg_xz_func
async def equip_bag(uid, qz, page=1):
    """装备背包"""
    try:
        page = max(1, int(page) if isinstance(page, (int, str)) and str(page).isdigit() else 1)
    except (ValueError, TypeError):
        page = 1

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                lines = []
                lines.append("未出战角色，请先出战[角色ID]")
                lines.append("<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战' show='出战' /> | <qqbot-cmd-input text='收回' show='收回' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            role_id, role_name, role_level, role_world = role_result

            # 获取装备列表
            equipments, total_count = await get_user_equip_list(uid, page, PAGE_SIZE)

            # 计算总页数
            total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE

            # 验证页码
            if page > total_pages and total_pages > 0:
                lines = []
                lines.append(f"##### 🎒 装备背包")
                lines.append("")
                lines.append(f"> 页码超出范围，当前只有{total_pages}页")
                lines.append("***")
                lines.append(f"<qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='装备背包 {total_pages}' show='装备背包 {total_pages}' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            role_info = {'id': role_id, 'name': role_name, 'level': role_level, 'world': role_world}
            markdown_content = format_equip_bag_markdown(equipments, page, total_pages, role_info)

            return {"type": "markdown", "content": markdown_content}


@reg_xz_func
async def current_equip(uid, qz):
    """当前装备"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 获取当前出战角色
            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                lines = []
                lines.append("未出战角色，请先出战[角色ID]")
                lines.append("<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战' show='出战' /> | <qqbot-cmd-input text='收回' show='收回' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            role_id, role_name, role_level, role_world = role_result

            # 获取角色穿戴的装备
            equipped_items = await get_role_equipped_items(role_id)

            # 计算装备总加成
            equip_bonus = await calc_role_equip_bonus(role_id)

            role_info = {'id': role_id, 'name': role_name, 'level': role_level, 'world': role_world}
            markdown_content = format_current_equip_markdown(role_info, equipped_items, equip_bonus)

            return {"type": "markdown", "content": markdown_content}


@reg_xz_func
async def wear_equip(uid, qz, equip_instance_id):
    """穿戴装备"""
    try:
        equip_instance_id = int(equip_instance_id)
    except (ValueError, TypeError):
        lines = []
        lines.append("##### ❌ 指令错误")
        lines.append("")
        lines.append("> 指令格式错误")
        lines.append("> 正确指令：穿戴装备 装备编号")
        lines.append("> 示例：穿戴装备 1")
        lines.append("***")
        lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='帮助' show='帮助' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT ue.id, ue.uid, ue.equip_id, ue.level, ue.quality, ue.enhance_fail_count, ue.is_equipped, ue.equipped_role_id,"
                " de.name, de.set_name, de.part, de.min_level,"
                " de.base_gongji, de.base_fangyu, de.base_qixue, de.base_fali, de.base_sudu,"
                " de.base_baoji, de.base_baoshang, de.base_shanbi, de.base_mingzhong, de.base_pofang, de.base_xixue,"
                " ue.create_time FROM user_equip ue JOIN data_equip de ON ue.equip_id = de.id WHERE ue.id = %s FOR UPDATE",
                (equip_instance_id,)
            )
            result = await cursor.fetchone()

            if result is None:
                lines = []
                lines.append("##### ❌ 穿戴失败")
                lines.append("")
                lines.append("> 装备不存在或不属于你")
                lines.append("> 请检查装备编号是否正确")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='装备详情' show='装备详情' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            equip = {
                'id': result[0], 'uid': result[1], 'equip_id': result[2], 'level': result[3],
                'quality': result[4], 'enhance_fail_count': result[5], 'is_equipped': result[6],
                'equipped_role_id': result[7], 'template_name': result[8], 'set_name': result[9],
                'part': result[10], 'min_level': result[11], 'base_gongji': result[12],
                'base_fangyu': result[13], 'base_qixue': result[14], 'base_fali': result[15],
                'base_sudu': result[16], 'base_baoji': result[17], 'base_baoshang': result[18],
                'base_shanbi': result[19], 'base_mingzhong': result[20], 'base_pofang': result[21],
                'base_xixue': result[22], 'create_time': result[23]
            }

            if equip['uid'] != uid:
                lines = []
                lines.append("##### ❌ 穿戴失败")
                lines.append("")
                lines.append("> 装备不存在或不属于你")
                lines.append("> 请检查装备编号是否正确")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='装备详情' show='装备详情' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            if equip['is_equipped'] and equip['equipped_role_id']:
                sql = "SELECT `name`, dengji FROM user_role WHERE id = %s LIMIT 1"
                await cursor.execute(sql, (equip['equipped_role_id'],))
                other_role = await cursor.fetchone()

                if other_role:
                    lines = []
                    lines.append("##### ❌ 穿戴失败")
                    lines.append("")
                    lines.append(f"> 该装备已被角色[{equip['equipped_role_id']}]{other_role[0]} Lv.{other_role[1]}穿戴")
                    lines.append("> 请先让该角色卸下此装备")
                    lines.append("***")
                    lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='角色背包' show='角色背包' />")
                    return {"type": "markdown", "content": "\n".join(lines)}

            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                lines = []
                lines.append("##### ❌ 穿戴失败")
                lines.append("")
                lines.append("> 未出战角色，请先出战一个角色！")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战' show='出战角色' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            role_id, role_name, role_level, role_world = role_result

            if role_level < equip['min_level']:
                lines = []
                lines.append("##### ❌ 穿戴失败")
                lines.append(f"**角色：** [{role_id}] {role_name} Lv.{role_level}〔{role_world}〕")
                lines.append("***")
                lines.append(f"> 等级不足，无法穿戴此装备")
                lines.append(f"> 需要等级：Lv.{equip['min_level']}")
                lines.append(f"> 当前等级：Lv.{role_level}")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='当前角色' show='当前角色' /> | <qqbot-cmd-input text='装备背包' show='装备背包' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            old_bonus = await calc_role_equip_bonus(role_id)

            part_en = equip['part']
            column_name = PART_COLUMN_MAP.get(part_en)

            old_equip_instance_id = None
            old_equip = None

            sql_check = f"SELECT {column_name} FROM user_role WHERE id = %s"
            await cursor.execute(sql_check, (role_id,))
            current_equip_id = (await cursor.fetchone())[0]

            if current_equip_id:
                old_equip_instance_id = current_equip_id
                old_equip = await get_user_equip(old_equip_instance_id, cursor)

                if old_equip:
                    await cursor.execute(
                        "UPDATE user_equip SET is_equipped = 0, equipped_role_id = NULL WHERE id = %s",
                        (old_equip_instance_id,)
                    )

            await cursor.execute(
                f"UPDATE user_role SET {column_name} = %s WHERE id = %s",
                (equip_instance_id, role_id)
            )

            await cursor.execute(
                "UPDATE user_equip SET is_equipped = 1, equipped_role_id = %s WHERE id = %s",
                (role_id, equip_instance_id)
            )

            await conn.commit()

            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)

            new_bonus = await calc_role_equip_bonus(role_id)

            attrs_change = {}
            for attr in ['gongji', 'fangyu', 'qixue', 'fali', 'sudu', 'baoji', 'baoshang', 'shanbi', 'mingzhong', 'pofang', 'xixue']:
                attrs_change[attr] = new_bonus[attr] - old_bonus[attr]

            role_info = {'id': role_id, 'name': role_name, 'level': role_level, 'world': role_world}

            updated_equip = await get_user_equip(equip_instance_id, cursor)

            markdown_content = format_wear_result_markdown(role_info, updated_equip, old_equip, attrs_change)

            return {"type": "markdown", "content": markdown_content}


@reg_xz_func
async def remove_equip(uid, qz, part_name):
    """卸下装备"""
    # 验证部位名称
    if part_name in PART_EN:
        part_en = PART_EN[part_name]
    elif part_name in PART_CN.values():
        # 中文名转英文
        for en, cn in PART_CN.items():
            if cn == part_name:
                part_en = en
                break
    else:
        lines = []
        lines.append("##### ❌ 指令错误")
        lines.append("")
        lines.append("> 部位名称错误")
        lines.append("> 可选部位：武器、头盔、铠甲、护腿、鞋子、饰品")
        lines.append("> 示例：卸下装备 武器")
        lines.append("***")
        lines.append("<qqbot-cmd-input text='卸下装备 武器' show='卸下装备 武器' /> | <qqbot-cmd-input text='当前装备' show='当前装备' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    # 获取当前出战角色
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result is None:
                lines = []
                lines.append("##### ❌ 卸下失败")
                lines.append("")
                lines.append("> 未出战角色，请先出战一个角色！")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战' show='出战角色' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            role_id, role_name, role_level, role_world = role_result

            column_name = PART_COLUMN_MAP.get(part_en)

            sql_check = f"SELECT {column_name} FROM user_role WHERE id = %s"
            await cursor.execute(sql_check, (role_id,))
            result = await cursor.fetchone()
            current_equip_id = result[0]

            if current_equip_id is None or current_equip_id == 0:
                part_cn = PART_CN.get(part_en, part_en)
                lines = []
                lines.append("##### ❌ 卸下失败")
                lines.append(f"**角色：** [{role_id}] {role_name} Lv.{role_level}〔{role_world}〕")
                lines.append("***")
                lines.append(f"> 该部位没有装备")
                lines.append(f"> 当前{part_cn}槽为空")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='当前装备' show='当前装备' /> | <qqbot-cmd-input text='装备背包' show='装备背包' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            equip = await get_user_equip(current_equip_id, cursor)

            if not equip:
                lines = []
                lines.append("##### ❌ 卸下失败")
                lines.append("")
                lines.append("> 装备不存在")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='当前装备' show='当前装备' /> | <qqbot-cmd-input text='装备背包' show='装备背包' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            # 计算卸下前后属性变化
            old_bonus = await calc_role_equip_bonus(role_id)

            # 清空角色装备槽位
            await cursor.execute(
                f"UPDATE user_role SET {column_name} = NULL WHERE id = %s",
                (role_id,)
            )

            # 更新装备状态为未穿戴
            await cursor.execute(
                "UPDATE user_equip SET is_equipped = 0, equipped_role_id = NULL WHERE id = %s",
                (current_equip_id,)
            )

            await conn.commit()

            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)

            # 计算卸下后属性
            new_bonus = await calc_role_equip_bonus(role_id)

            final_bonus = {}
            for attr in ['gongji', 'fangyu', 'qixue', 'fali', 'sudu', 'baoji', 'baoshang', 'shanbi', 'mingzhong', 'pofang', 'xixue']:
                final_bonus[attr] = new_bonus[attr] - old_bonus[attr]

            role_info = {'id': role_id, 'name': role_name, 'level': role_level, 'world': role_world}

            markdown_content = format_remove_result_markdown(role_info, equip, final_bonus)

            return {"type": "markdown", "content": markdown_content}


@reg_xz_func
async def enhance_equip(uid, qz, equip_instance_id):
    """强化装备"""
    try:
        equip_instance_id = int(equip_instance_id)
    except (ValueError, TypeError):
        lines = []
        lines.append("##### ❌ 指令错误")
        lines.append("")
        lines.append("> 指令格式错误")
        lines.append("> 正确指令：强化装备 装备编号")
        lines.append("> 示例：强化装备 1")
        lines.append("***")
        lines.append("<qqbot-cmd-input text='强化装备 1' show='强化装备 1' /> | <qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='帮助' show='帮助' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT ue.id, ue.uid, ue.equip_id, ue.level, ue.quality, ue.enhance_fail_count, ue.is_equipped, ue.equipped_role_id,"
                " de.name, de.set_name, de.part, de.min_level,"
                " de.base_gongji, de.base_fangyu, de.base_qixue, de.base_fali, de.base_sudu,"
                " de.base_baoji, de.base_baoshang, de.base_shanbi, de.base_mingzhong, de.base_pofang, de.base_xixue,"
                " ue.create_time FROM user_equip ue JOIN data_equip de ON ue.equip_id = de.id WHERE ue.id = %s FOR UPDATE",
                (equip_instance_id,)
            )
            result = await cursor.fetchone()

            if result is None:
                lines = []
                lines.append("##### ❌ 强化失败")
                lines.append("")
                lines.append("> 装备不存在或不属于你")
                lines.append("> 请检查装备编号是否正确")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            equip = {
                'id': result[0], 'uid': result[1], 'equip_id': result[2], 'level': result[3],
                'quality': result[4], 'enhance_fail_count': result[5], 'is_equipped': result[6],
                'equipped_role_id': result[7], 'template_name': result[8], 'set_name': result[9],
                'part': result[10], 'min_level': result[11], 'base_gongji': result[12],
                'base_fangyu': result[13], 'base_qixue': result[14], 'base_fali': result[15],
                'base_sudu': result[16], 'base_baoji': result[17], 'base_baoshang': result[18],
                'base_shanbi': result[19], 'base_mingzhong': result[20], 'base_pofang': result[21],
                'base_xixue': result[22], 'create_time': result[23]
            }

            if equip['uid'] != uid:
                lines = []
                lines.append("##### ❌ 强化失败")
                lines.append("")
                lines.append("> 装备不存在或不属于你")
                lines.append("> 请检查装备编号是否正确")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            if equip['level'] >= 10:
                lines = []
                lines.append("##### ❌ 强化失败")
                lines.append("")
                lines.append("> 该装备已达最高强化等级")
                lines.append(f"> 当前等级：+10 (MAX)")
                lines.append("***")
                lines.append(f"<qqbot-cmd-input text='装备详情 {equip_instance_id}' show='装备详情 {equip_instance_id}' /> | <qqbot-cmd-input text='当前装备' show='当前装备' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s FOR UPDATE", (uid,))
            lingshi_result = await cursor.fetchone()
            current_lingshi = lingshi_result[0] if lingshi_result else 0

            current_level = equip['level']
            cost_lingshi = get_enhance_cost(equip['min_level'], current_level + 1)

            if current_lingshi < cost_lingshi:
                lines = []
                lines.append("##### ❌ 强化失败")
                lines.append("")
                lines.append(f"> 灵石不足，无法强化")
                lines.append(f"> 需要灵石：{cost_lingshi}")
                lines.append(f"> 当前灵石：{current_lingshi}")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='装备详情 {}' show='装备详情 {}' />".format(equip_instance_id))
                return {"type": "markdown", "content": "\n".join(lines)}

            target_level = current_level + 1
            success_rate = ENHANCE_SUCCESS_RATE.get(target_level, 100)

            fail_count = equip.get('enhance_fail_count', 0)
            pity_threshold = ENHANCE_PITY.get(target_level, 0)
            if pity_threshold > 0 and fail_count >= pity_threshold:
                success = True
                is_pity = True
            else:
                success = random.randint(1, 100) <= success_rate
                is_pity = False

            old_attrs = calc_equip_final_attrs(equip)

            if success:
                new_level = current_level + 1
                new_fail_count = 0
            else:
                new_level = current_level
                new_fail_count = fail_count + 1

            await cursor.execute(
                "UPDATE user_equip SET level = %s, enhance_fail_count = %s WHERE id = %s",
                (new_level, new_fail_count, equip_instance_id)
            )
            await cursor.execute(
                "UPDATE user_zt SET lingshi = lingshi - %s WHERE id = %s",
                (cost_lingshi, uid)
            )
            await conn.commit()

            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)

            equip['level'] = new_level
            new_attrs = calc_equip_final_attrs(equip)

            await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s", (uid,))
            lingshi_result = await cursor.fetchone()
            current_lingshi = lingshi_result[0] if lingshi_result else 0

            sql = "SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            role_result = await cursor.fetchone()

            if role_result:
                role_info = {'id': role_result[0], 'name': role_result[1], 'level': role_result[2], 'world': role_result[3]}
            else:
                role_info = None

            markdown_content = format_enhance_result_markdown(
                role_info, equip, success, new_level, old_attrs, new_attrs, cost_lingshi, current_lingshi
            )

            if not success and pity_threshold > 0:
                pity_line = f"\n> 保底进度：{new_fail_count}/{pity_threshold}"
                markdown_content = markdown_content.replace(
                "\n***\n<qqbot-cmd-input",
                f"{pity_line}\n***\n<qqbot-cmd-input",
                    1
                )
            if success and is_pity:
                pity_line = "\n> 🎉 保底触发！天道酬勤！"
                markdown_content = markdown_content.replace(
                "\n***\n<qqbot-cmd-input",
                f"{pity_line}\n***\n<qqbot-cmd-input",
                    1
                )

            return {"type": "markdown", "content": markdown_content}


@reg_xz_func
async def equip_detail(uid, qz, equip_instance_id):
    """装备详情"""
    try:
        equip_instance_id = int(equip_instance_id)
    except (ValueError, TypeError):
        lines = []
        lines.append("##### ❌ 指令错误")
        lines.append("")
        lines.append("> 指令格式错误")
        lines.append("> 正确指令：装备详情 装备编号")
        lines.append("> 示例：装备详情 1")
        lines.append("***")
        lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='装备详情 1' show='装备详情 1' /> | <qqbot-cmd-input text='帮助' show='帮助' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    # 获取装备信息
    equip = await get_user_equip(equip_instance_id)

    if equip is None or equip['uid'] != uid:
        lines = []
        lines.append("##### ❌ 查询失败")
        lines.append("")
        lines.append("> 装备不存在或不属于你")
        lines.append("> 请检查装备编号是否正确")
        lines.append("***")
        lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' /> | <qqbot-cmd-input text='装备详情' show='装备详情' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    final_attrs = calc_equip_final_attrs(equip)

    equipped_info = None

    if equip['is_equipped'] and equip['equipped_role_id']:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                sql = "SELECT id, `name`, dengji FROM user_role WHERE id = %s LIMIT 1"
                await cursor.execute(sql, (equip['equipped_role_id'],))
                result = await cursor.fetchone()

                if result:
                    equipped_info = {'id': result[0], 'name': result[1], 'level': result[2]}

    markdown_content = format_equip_detail_markdown(equip, final_attrs, None, equipped_info)

    return {"type": "markdown", "content": markdown_content}


@reg_xz_func
async def sell_equip(uid, qz, equip_instance_id):
    """出售装备"""
    try:
        equip_instance_id = int(equip_instance_id)
    except (ValueError, TypeError):
        lines = []
        lines.append("##### ❌ 指令错误")
        lines.append("")
        lines.append("> 指令格式错误")
        lines.append("> 正确指令：出售装备 装备编号")
        lines.append("> 示例：出售装备 1")
        lines.append("***")
        lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' />")
        return {"type": "markdown", "content": "\n".join(lines)}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT ue.id, ue.uid, ue.equip_id, ue.level, ue.quality, ue.enhance_fail_count, ue.is_equipped, ue.equipped_role_id,"
                " de.name, de.set_name, de.part, de.min_level,"
                " de.base_gongji, de.base_fangyu, de.base_qixue, de.base_fali, de.base_sudu,"
                " de.base_baoji, de.base_baoshang, de.base_shanbi, de.base_mingzhong, de.base_pofang, de.base_xixue,"
                " ue.create_time FROM user_equip ue JOIN data_equip de ON ue.equip_id = de.id WHERE ue.id = %s FOR UPDATE",
                (equip_instance_id,)
            )
            result = await cursor.fetchone()

            if result is None:
                lines = []
                lines.append("##### ❌ 出售失败")
                lines.append("")
                lines.append("> 装备不存在或不属于你")
                lines.append("> 请检查装备编号是否正确")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            equip = {
                'id': result[0], 'uid': result[1], 'equip_id': result[2], 'level': result[3],
                'quality': result[4], 'enhance_fail_count': result[5], 'is_equipped': result[6],
                'equipped_role_id': result[7], 'template_name': result[8], 'set_name': result[9],
                'part': result[10], 'min_level': result[11], 'base_gongji': result[12],
                'base_fangyu': result[13], 'base_qixue': result[14], 'base_fali': result[15],
                'base_sudu': result[16], 'base_baoji': result[17], 'base_baoshang': result[18],
                'base_shanbi': result[19], 'base_mingzhong': result[20], 'base_pofang': result[21],
                'base_xixue': result[22], 'create_time': result[23]
            }

            if equip['uid'] != uid:
                lines = []
                lines.append("##### ❌ 出售失败")
                lines.append("")
                lines.append("> 装备不存在或不属于你")
                lines.append("> 请检查装备编号是否正确")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='装备背包' show='装备背包' />")
                return {"type": "markdown", "content": "\n".join(lines)}

            if equip['is_equipped']:
                lines = []
                lines.append("##### ❌ 出售失败")
                lines.append("")
                lines.append("> 该装备当前处于穿戴状态，无法直接出售")
                lines.append("> 请先卸下装备后再出售")
                lines.append("***")
                lines.append("<qqbot-cmd-input text='卸下装备 {}' show='卸下装备 {}' /> | <qqbot-cmd-input text='装备详情 {}' show='装备详情 {}' />".format(PART_CN.get(equip['part'], equip['part']), equip_instance_id))
                return {"type": "markdown", "content": "\n".join(lines)}

            sell_info = calc_equip_sell_info(equip['min_level'], equip['quality'], equip['level'])

            await cursor.execute(
                "UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s",
                (sell_info['total_price'], uid)
            )
            await cursor.execute("DELETE FROM user_equip WHERE id = %s", (equip_instance_id,))
            await conn.commit()

            await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s", (uid,))
            lingshi_result = await cursor.fetchone()
            current_lingshi = lingshi_result[0] if lingshi_result else 0

            await cursor.execute("SELECT id, `name`, dengji, world FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1", (uid,))
            role_result = await cursor.fetchone()
            if role_result:
                role_info = {'id': role_result[0], 'name': role_result[1], 'level': role_result[2], 'world': role_result[3]}
            else:
                role_info = None

            markdown_content = format_sell_result_markdown(role_info, equip, sell_info, current_lingshi)
            return {"type": "markdown", "content": markdown_content}
