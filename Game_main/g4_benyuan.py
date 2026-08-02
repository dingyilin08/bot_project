from Tool.tool_command import *
from sql.mysql import *
from Tool.tool_user import *
from func.pd_func import *
import time
import random
import logging


logger = logging.getLogger(__name__)


BENYUAN_SKILL_SEED = [
    # 萧炎 - 斗破苍穹
    {"id": 1001, "role_name": "萧炎", "benyuan_name": "异火本源", "unlock_level": 20, "skill_name": "异火灼脉", "skill_type": 4, "value": 35, "is_percent": 1, "cooldown": 3, "buff_type": "HP_down", "buff_value": 8, "buff_duration": 3, "buff_target": 2, "skill_desc": "异火灼脉，持续焚烧敌方本源。", "priority": 1},
    {"id": 1002, "role_name": "萧炎", "benyuan_name": "异火本源", "unlock_level": 40, "skill_name": "佛怒火莲", "skill_type": 1, "value": 55, "is_percent": 1, "cooldown": 4, "buff_type": "pofang_up", "buff_value": 25, "buff_duration": 2, "buff_target": 1, "skill_desc": "火莲爆裂，破防贯穿。", "priority": 2},
    {"id": 1003, "role_name": "萧炎", "benyuan_name": "异火本源", "unlock_level": 60, "skill_name": "帝炎领域", "skill_type": 4, "value": 70, "is_percent": 1, "cooldown": 7, "buff_type": "all_stat_up", "buff_value": 25, "buff_duration": 3, "buff_target": 1, "skill_desc": "万火归宗，帝炎焚世。", "priority": 3},

    # 王林 - 仙逆
    {"id": 1004, "role_name": "王林", "benyuan_name": "轮回本源", "unlock_level": 20, "skill_name": "因果锁", "skill_type": 4, "value": 30, "is_percent": 1, "cooldown": 3, "buff_type": "gongji_down", "buff_value": 25, "buff_duration": 3, "buff_target": 2, "skill_desc": "因果缠身，削弱敌势。", "priority": 1},
    {"id": 1005, "role_name": "王林", "benyuan_name": "轮回本源", "unlock_level": 40, "skill_name": "逆命轮回", "skill_type": 2, "value": 35, "is_percent": 1, "cooldown": 4, "buff_type": "reflect", "buff_value": 35, "buff_duration": 2, "buff_target": 1, "skill_desc": "逆转生死，反伤回环。", "priority": 2},
    {"id": 1006, "role_name": "王林", "benyuan_name": "轮回本源", "unlock_level": 60, "skill_name": "戮默轮回", "skill_type": 4, "value": 65, "is_percent": 1, "cooldown": 7, "buff_type": "death_sentence", "buff_value": 0, "buff_duration": 2, "buff_target": 2, "skill_desc": "轮回裁决，临终审判。", "priority": 3},

    # 韩立 - 凡人修仙传
    {"id": 1007, "role_name": "韩立", "benyuan_name": "掌天本源", "unlock_level": 20, "skill_name": "掌天回息", "skill_type": 3, "value": 18, "is_percent": 1, "cooldown": 3, "buff_type": "HP_up", "buff_value": 6, "buff_duration": 3, "buff_target": 1, "skill_desc": "掌天瓶息，缓续生机。", "priority": 1},
    {"id": 1008, "role_name": "韩立", "benyuan_name": "掌天本源", "unlock_level": 40, "skill_name": "时间迟滞", "skill_type": 4, "value": 45, "is_percent": 1, "cooldown": 4, "buff_type": "sudu_down", "buff_value": 40, "buff_duration": 2, "buff_target": 2, "skill_desc": "时间法则，迟滞万象。", "priority": 2},
    {"id": 1009, "role_name": "韩立", "benyuan_name": "掌天本源", "unlock_level": 60, "skill_name": "玄天斩灵", "skill_type": 1, "value": 68, "is_percent": 1, "cooldown": 6, "buff_type": "pofang_up", "buff_value": 35, "buff_duration": 2, "buff_target": 1, "skill_desc": "玄天一斩，断灵灭魄。", "priority": 3},

    # 石昊 - 完美世界
    {"id": 1010, "role_name": "石昊", "benyuan_name": "至尊本源", "unlock_level": 20, "skill_name": "至尊骨护体", "skill_type": 2, "value": 30, "is_percent": 1, "cooldown": 3, "buff_type": "shield", "buff_value": 30, "buff_duration": 2, "buff_target": 1, "skill_desc": "至尊骨鸣，护体无双。", "priority": 1},
    {"id": 1011, "role_name": "石昊", "benyuan_name": "至尊本源", "unlock_level": 40, "skill_name": "他化自在", "skill_type": 2, "value": 40, "is_percent": 1, "cooldown": 4, "buff_type": "all_stat_up", "buff_value": 18, "buff_duration": 3, "buff_target": 1, "skill_desc": "他化万法，战意升华。", "priority": 2},
    {"id": 1012, "role_name": "石昊", "benyuan_name": "至尊本源", "unlock_level": 60, "skill_name": "荒天帝印", "skill_type": 4, "value": 72, "is_percent": 1, "cooldown": 7, "buff_type": "un_action", "buff_value": 0, "buff_duration": 1, "buff_target": 2, "skill_desc": "帝印镇世，威压八荒。", "priority": 3},

    # 叶凡 - 遮天
    {"id": 1013, "role_name": "叶凡", "benyuan_name": "母气本源", "unlock_level": 20, "skill_name": "母气护身", "skill_type": 2, "value": 32, "is_percent": 1, "cooldown": 3, "buff_type": "fangyu_up", "buff_value": 35, "buff_duration": 3, "buff_target": 1, "skill_desc": "万物母气，固若神岳。", "priority": 1},
    {"id": 1014, "role_name": "叶凡", "benyuan_name": "母气本源", "unlock_level": 40, "skill_name": "皆字秘", "skill_type": 1, "value": 50, "is_percent": 1, "cooldown": 4, "buff_type": "baoji_up", "buff_value": 45, "buff_duration": 2, "buff_target": 1, "skill_desc": "斗战皆字，瞬爆极限。", "priority": 2},
    {"id": 1015, "role_name": "叶凡", "benyuan_name": "母气本源", "unlock_level": 60, "skill_name": "六道轮回拳", "skill_type": 4, "value": 75, "is_percent": 1, "cooldown": 7, "buff_type": "fangyu_down", "buff_value": 40, "buff_duration": 2, "buff_target": 2, "skill_desc": "轮回六道，拳镇诸天。", "priority": 3},

    # 孟川 - 沧元图
    {"id": 1016, "role_name": "孟川", "benyuan_name": "心魂本源", "unlock_level": 20, "skill_name": "心刀明镜", "skill_type": 2, "value": 28, "is_percent": 1, "cooldown": 3, "buff_type": "mingzhong_up", "buff_value": 35, "buff_duration": 3, "buff_target": 1, "skill_desc": "心魂如镜，刀意通明。", "priority": 1},
    {"id": 1017, "role_name": "孟川", "benyuan_name": "心魂本源", "unlock_level": 40, "skill_name": "沧元刀域", "skill_type": 4, "value": 48, "is_percent": 1, "cooldown": 4, "buff_type": "HP_down", "buff_value": 10, "buff_duration": 3, "buff_target": 2, "skill_desc": "刀域展开，层层蚀命。", "priority": 2},
    {"id": 1018, "role_name": "孟川", "benyuan_name": "心魂本源", "unlock_level": 60, "skill_name": "八劫绝斩", "skill_type": 4, "value": 78, "is_percent": 1, "cooldown": 7, "buff_type": "pofang_up", "buff_value": 40, "buff_duration": 2, "buff_target": 1, "skill_desc": "八劫归一，一斩绝空。", "priority": 3},
]

_BENYUAN_SKILL_SCHEMA_READY = False


def _benyuan_material_requirements(level, stage_item_ids, common_item_ids):
    """返回本次升级所需材料及是否进阶；合并重复物品避免少扣。"""
    if level == 19:
        raw_requirements = [(stage_item_ids[0], 1)]
        is_stage = True
    elif level == 39:
        raw_requirements = [(stage_item_ids[0], 2), (stage_item_ids[1], 1)]
        is_stage = True
    elif level == 59:
        raw_requirements = [
            (stage_item_ids[0], 3),
            (stage_item_ids[1], 2),
            (stage_item_ids[2], 1),
        ]
        is_stage = True
    else:
        raw_requirements = [
            (common_item_ids[0], level * 5),
            (common_item_ids[1], level * 3),
            (common_item_ids[2], level * 2),
        ]
        is_stage = False

    merged = {}
    for item_id, amount in raw_requirements:
        if item_id and amount > 0:
            merged[item_id] = merged.get(item_id, 0) + amount
    return list(merged.items()), is_stage


async def _lock_and_consume_benyuan_materials(cursor, uid, requirements):
    """先锁定并完整校验材料，再在当前事务中统一扣除。"""
    missing = []
    for item_id, amount in requirements:
        await cursor.execute(
            "SELECT item_num FROM user_item WHERE uid = %s AND item_id = %s LIMIT 1 FOR UPDATE",
            (uid, item_id),
        )
        row = await cursor.fetchone()
        current_amount = int(row[0]) if row else 0
        if current_amount < amount:
            missing.append((item_id, amount, current_amount))

    if missing:
        return missing

    for item_id, amount in requirements:
        await cursor.execute(
            "UPDATE user_item SET item_num = item_num - %s "
            "WHERE uid = %s AND item_id = %s AND item_num >= %s",
            (amount, uid, item_id, amount),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("本源升级材料并发扣除失败")
        await cursor.execute(
            "DELETE FROM user_item WHERE uid = %s AND item_id = %s AND item_num = 0",
            (uid, item_id),
        )
    return []


def _skill_type_name(skill_type):
    mapping = {
        1: "攻击型",
        2: "防御型",
        3: "回复型",
        4: "穿透型",
        "1": "攻击型",
        "2": "防御型",
        "3": "回复型",
        "4": "穿透型",
    }
    return mapping.get(skill_type, "特殊型")


def _buff_type_name_cn(buff_type):
    mapping = {
        "HP_down": "持续灼伤",
        "HP_up": "持续回复",
        "pofang_up": "破防提升",
        "all_stat_up": "全属性提升",
        "gongji_down": "攻击削弱",
        "reflect": "伤害反弹",
        "death_sentence": "死亡宣告",
        "sudu_down": "速度降低",
        "shield": "护盾",
        "un_action": "眩晕控制",
        "fangyu_up": "防御提升",
        "baoji_up": "暴击提升",
        "fangyu_down": "防御削弱",
        "mingzhong_up": "命中提升",
    }
    return mapping.get(buff_type, buff_type)


def _benyuan_lore_buff_name(skill_name, buff_type):
    lore_name = {
        "异火灼脉": "帝炎灼脉",
        "佛怒火莲": "火莲破甲",
        "帝炎领域": "帝炎共鸣",
        "因果锁": "因果缚魂",
        "逆命轮回": "逆命回环",
        "戮默轮回": "轮回断命",
        "掌天回息": "掌天回元",
        "时间迟滞": "时滞锁域",
        "玄天斩灵": "斩灵破界",
        "至尊骨护体": "至尊骨盾",
        "他化自在": "自在法相",
        "荒天帝印": "帝印镇压",
        "母气护身": "母气护体",
        "皆字秘": "皆字极境",
        "六道轮回拳": "六道压制",
        "心刀明镜": "明镜刀心",
        "沧元刀域": "沧元蚀命",
        "八劫绝斩": "八劫破灭",
    }
    return lore_name.get(skill_name, _buff_type_name_cn(buff_type))


def _format_benyuan_buff_display(skill_name, buff_type, buff_value, buff_duration, buff_target):
    if not buff_type:
        return "无"

    target_text = "自身" if buff_target == 1 else "敌方"
    buff_cn = _buff_type_name_cn(buff_type)
    lore_name = _benyuan_lore_buff_name(skill_name, buff_type)

    if buff_type in ("un_action", "death_sentence"):
        value_text = "效果值固定"
    else:
        value_text = f"效果值{buff_value}%"

    duration_text = f"{buff_duration}回合" if buff_duration and buff_duration > 0 else "即时"
    return f"{lore_name}（{buff_cn}，{value_text}，持续{duration_text}，目标:{target_text}）"


async def ensure_benyuan_skill_schema(cursor):
    global _BENYUAN_SKILL_SCHEMA_READY
    if _BENYUAN_SKILL_SCHEMA_READY:
        return

    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_benyuan_skill (
            id INT NOT NULL,
            role_name VARCHAR(25) NOT NULL,
            benyuan_name VARCHAR(50) NOT NULL,
            unlock_level INT NOT NULL,
            skill_name VARCHAR(50) NOT NULL,
            skill_type TINYINT NOT NULL,
            value INT NOT NULL DEFAULT 0,
            is_percent TINYINT NOT NULL DEFAULT 1,
            cooldown TINYINT NOT NULL DEFAULT 0,
            buff_type VARCHAR(50) NULL,
            buff_value INT NULL DEFAULT 0,
            buff_duration TINYINT NULL DEFAULT 0,
            buff_target TINYINT NULL DEFAULT 2,
            skill_desc VARCHAR(255) NULL,
            priority TINYINT NOT NULL DEFAULT 1,
            PRIMARY KEY (id),
            UNIQUE KEY uk_role_unlock (role_name, unlock_level),
            KEY idx_role_name (role_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_benyuan_skill (
            id BIGINT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            role_id INT NOT NULL,
            by_id INT NOT NULL,
            benyuan_skill_id INT NOT NULL,
            unlocked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_equipped TINYINT NOT NULL DEFAULT 1,
            slot TINYINT NULL DEFAULT NULL,
            PRIMARY KEY (id),
            UNIQUE KEY uk_role_skill (role_id, benyuan_skill_id),
            KEY idx_uid_role (uid, role_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    insert_sql = """
        INSERT INTO data_benyuan_skill (
            id, role_name, benyuan_name, unlock_level, skill_name, skill_type, `value`,
            is_percent, cooldown, buff_type, buff_value, buff_duration, buff_target, skill_desc, priority
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            role_name = VALUES(role_name),
            benyuan_name = VALUES(benyuan_name),
            unlock_level = VALUES(unlock_level),
            skill_name = VALUES(skill_name),
            skill_type = VALUES(skill_type),
            `value` = VALUES(`value`),
            is_percent = VALUES(is_percent),
            cooldown = VALUES(cooldown),
            buff_type = VALUES(buff_type),
            buff_value = VALUES(buff_value),
            buff_duration = VALUES(buff_duration),
            buff_target = VALUES(buff_target),
            skill_desc = VALUES(skill_desc),
            priority = VALUES(priority)
    """

    for skill in BENYUAN_SKILL_SEED:
        await cursor.execute(insert_sql, (
            skill["id"], skill["role_name"], skill["benyuan_name"], skill["unlock_level"],
            skill["skill_name"], skill["skill_type"], skill["value"], skill["is_percent"],
            skill["cooldown"], skill["buff_type"], skill["buff_value"], skill["buff_duration"],
            skill["buff_target"], skill["skill_desc"], skill["priority"]
        ))

    _BENYUAN_SKILL_SCHEMA_READY = True


async def sync_unlock_benyuan_skills(uid, role_id, by_id, role_name, benyuan_level, cursor):
    await ensure_benyuan_skill_schema(cursor)

    await cursor.execute("""
        SELECT benyuan_skill_id
        FROM user_benyuan_skill
        WHERE uid = %s AND role_id = %s
    """, (uid, role_id))
    exists = {row[0] for row in (await cursor.fetchall() or [])}

    await cursor.execute("""
        SELECT id, unlock_level, skill_name
        FROM data_benyuan_skill
        WHERE role_name = %s
        ORDER BY unlock_level ASC
    """, (role_name,))
    skills = await cursor.fetchall()

    unlocked = []
    for skill_id, unlock_level, skill_name in skills:
        if benyuan_level >= unlock_level and skill_id not in exists:
            await cursor.execute("""
                INSERT INTO user_benyuan_skill (uid, role_id, by_id, benyuan_skill_id, is_equipped, slot)
                VALUES (%s, %s, %s, %s, 1, NULL)
            """, (uid, role_id, by_id, skill_id))
            unlocked.append({"id": skill_id, "skill_name": skill_name, "unlock_level": unlock_level})
    return unlocked


async def get_role_benyuan_skills_for_battle(uid, role_id, role_name, cursor=None):
    async def _query(cur):
        await ensure_benyuan_skill_schema(cur)

        await cur.execute("""
            SELECT ur.by_id, ub.dengji
            FROM user_role ur
            JOIN user_benyuan ub ON ub.id = ur.by_id AND ub.uid = ur.uid
            WHERE ur.uid = %s AND ur.id = %s
            LIMIT 1
        """, (uid, role_id))
        base_info = await cur.fetchone()
        if not base_info:
            return []

        by_id, benyuan_level = base_info
        await sync_unlock_benyuan_skills(uid, role_id, by_id, role_name, benyuan_level, cur)

        await cur.execute("""
            SELECT dbs.id, dbs.skill_name, dbs.skill_type, dbs.value, dbs.is_percent,
                   dbs.cooldown, dbs.buff_type, dbs.buff_value, dbs.buff_duration,
                   dbs.buff_target, dbs.skill_desc, dbs.priority
            FROM user_benyuan_skill ubs
            JOIN data_benyuan_skill dbs ON dbs.id = ubs.benyuan_skill_id
            WHERE ubs.uid = %s AND ubs.role_id = %s AND ubs.is_equipped = 1
            ORDER BY dbs.priority DESC, dbs.unlock_level ASC
        """, (uid, role_id))
        rows = await cur.fetchall()

        result = []
        for row in rows:
            result.append({
                "id": row[0],
                "skill_name": row[1],
                "skill_type": row[2],
                "value": row[3],
                "is_percent": row[4],
                "cooldown": row[5],
                "buff_type": row[6],
                "buff_value": row[7],
                "buff_duration": row[8],
                "buff_target": row[9] if row[9] else 2,
                "skill_desc": row[10] or "",
                "priority": row[11] or 1
            })
        return result

    if cursor:
        return await _query(cursor)

    async with connect_mysql() as conn:
        async with conn.cursor() as cur:
            skills = await _query(cur)
            await conn.commit()
            return skills


# 查看本源
@reg_xz_func
async def ck_benyuan(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name`, dengji, by_id FROM user_role WHERE uid = %s and is_chuzhan = 1 limit 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您当前未出战角色，无法查看出战角色本源。示例：出战+角色编号"}
            role_id, role_name, dengji, by_id = result
            sql = "SELECT `name`, need_item_1, need_item_2, need_item_3, need_cl_1, need_cl_2, need_cl_3 FROM data_benyuan WHERE role_name = %s LIMIT 1"
            await cursor.execute(sql, (role_name,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "当前角色缺少本源配置，无法查看。\n"}
            by_name, item_1_id, item_2_id, item_3_id, cl_1_id, cl_2_id, cl_3_id = result
            sql = "SELECT `name`, dengji, qx_jc, gj_jc, fy_jc, bj_jc, bs_jc, sb_jc, mz_jc, pf_jc, xx_jc FROM user_benyuan WHERE id = %s and uid = %s LIMIT 1"
            await cursor.execute(sql, (by_id, uid,))
            result = await cursor.fetchone()
            by_name, benyuan_dengji, qx_jc, gj_jc, fy_jc, bj_jc, bs_jc, sb_jc, mz_jc, pf_jc, xx_jc = result

            cl_1_name = await get_item_name(cursor, cl_1_id)
            cl_2_name = await get_item_name(cursor, cl_2_id)
            cl_3_name = await get_item_name(cursor, cl_3_id)

            cl_1_num = benyuan_dengji * 5
            cl_2_num = benyuan_dengji * 3
            cl_3_num = benyuan_dengji * 2

            if benyuan_dengji == 20:
                item_1_name = await get_item_name(cursor, item_1_id)
                item_1_num = 1
                up_stage_txt = f"进阶所需材料：\n{item_1_name}×{item_1_num}\n"
            elif benyuan_dengji == 40:
                item_1_name = await get_item_name(cursor, item_1_id)
                item_2_name = await get_item_name(cursor, item_2_id)
                item_1_num = 2
                item_2_num = 1
                up_stage_txt = f"进阶所需材料：\n{item_1_name}×{item_1_num}，{item_2_name}×{item_2_num}\n"
            elif benyuan_dengji == 60:
                item_1_name = await get_item_name(cursor, item_1_id)
                item_2_name = await get_item_name(cursor, item_2_id)
                item_3_name = await get_item_name(cursor, item_3_id)
                item_1_num = 3
                item_2_num = 2
                item_3_num = 1
                up_stage_txt = f"进阶所需材料：\n{item_1_name}×{item_1_num}，{item_2_name}×{item_2_num}，{item_3_name}×{item_3_num}\n"
            else:
                up_stage_txt = ""

            if 20 <= benyuan_dengji < 40:
                stage = "五转·"
            elif 40 <= benyuan_dengji < 60:
                stage = "天启·"
            elif benyuan_dengji >= 60:
                stage = "终焉·"
            else:
                stage = ""

            output = f"[{role_name}]本源信息如下：\n"
            output += f"本源名称：{stage}{by_name}\n"
            output += f"本源等级：{benyuan_dengji}/60\n"
            output += f"本源为角色属性提供的加成如下：\n"
            output += f"气血：{qx_jc}%\n"
            output += f"攻击：{gj_jc}% | 防御：{fy_jc}%\n"
            output += f"暴击：{round((bj_jc / 100), 1)}% | 暴伤：{round((bs_jc / 100), 1)}%\n"
            output += f"闪避：{round((sb_jc / 100), 1)}% | 命中：{round((mz_jc / 100), 1)}%\n"
            output += f"破防：{round((pf_jc / 100), 1)}% | 吸血：{round((xx_jc / 100), 1)}%\n"

            output += f"升级所需材料：\n> {cl_1_name}×{cl_1_num}，{cl_2_name}×{cl_2_num}，{cl_3_name}×{cl_3_num}\n"
            output += up_stage_txt

            kj = await all_write_command(uid, (f"本源升级", "物品背包", "当前角色"))

            return {"type": "markdown", "content": output + kj}


# 本源升级
@reg_xz_func
async def up_benyuan(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 表结构/技能种子初始化可能触发 DDL 隐式提交，必须在升级事务开始前完成。
            await ensure_benyuan_skill_schema(cursor)
            await conn.commit()
            sql = "SELECT id, `name`, dengji, by_id, gongji, fangyu, qixue, baoji, baoshang FROM user_role WHERE uid = %s and is_chuzhan = 1 limit 1 FOR UPDATE"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您当前未出战角色，无法升级出战角色本源。示例：出战+角色编号\n"}
            role_id, role_name, dengji, by_id, gongji, fangyu, qixue, baoji, baoshang = result
            sql = "SELECT `name`, need_item_1, need_item_2, need_item_3, need_cl_1, need_cl_2, need_cl_3 FROM data_benyuan WHERE role_name = %s LIMIT 1"
            await cursor.execute(sql, (role_name,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "当前角色缺少本源配置，无法升级。\n"}
            by_name, item_1_id, item_2_id, item_3_id, cl_1_id, cl_2_id, cl_3_id = result
            sql = "SELECT `name`, dengji, qx_jc, gj_jc, fy_jc, bj_jc, bs_jc, sb_jc, mz_jc, pf_jc, xx_jc FROM user_benyuan WHERE id = %s and uid = %s LIMIT 1 FOR UPDATE"
            await cursor.execute(sql, (by_id, uid,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "当前角色本源数据异常，无法升级。\n"}
            by_name, benyuan_dengji, qx_jc, gj_jc, fy_jc, bj_jc, bs_jc, sb_jc, mz_jc, pf_jc, xx_jc = result

            if benyuan_dengji >= 60:
                return {"type": "markdown", "content": qz + "本源已达到等级上限，无法升级。\n"}

            requirements, is_up_stage = _benyuan_material_requirements(
                benyuan_dengji,
                (item_1_id, item_2_id, item_3_id),
                (cl_1_id, cl_2_id, cl_3_id),
            )
            item_names = {
                item_id: (await get_item_name(cursor, item_id) or f"物品#{item_id}")
                for item_id, _ in requirements
            }
            missing = await _lock_and_consume_benyuan_materials(cursor, uid, requirements)
            if missing:
                await conn.rollback()
                missing_text = "，".join(
                    f"{item_names[item_id]}×{need}（现有{current}）"
                    for item_id, need, current in missing
                )
                all_text = "，".join(
                    f"{item_names[item_id]}×{amount}" for item_id, amount in requirements
                )
                material_type = "进阶" if is_up_stage else "升级"
                return {
                    "type": "markdown",
                    "content": qz + f"您当前缺少{material_type}材料：{missing_text}，无法升级本源。\n"
                    f"本次所需材料：{all_text}\n",
                }

            r = random.randint(1, 9)
            ATTR_CONFIG = {
                1: {'role_field': 'gongji_jc', 'by_field': 'gj_jc', 'base_inc': 1, 'percent': '%'},
                2: {'role_field': 'fangyu_jc', 'by_field': 'fy_jc', 'base_inc': 1, 'percent': '%'},
                3: {'role_field': 'qixue_jc', 'by_field': 'qx_jc', 'base_inc': 1, 'percent': '%'},
                4: {'role_field': 'baoji', 'by_field': 'bj_jc', 'base_inc': 10, 'percent': '0.1%'},
                5: {'role_field': 'baoshang', 'by_field': 'bs_jc', 'base_inc': 10, 'percent': '0.1%'},
                6: {'role_field': 'shanbi', 'by_field': 'sb_jc', 'base_inc': 10, 'percent': '0.1%'},
                7: {'role_field': 'mingzhong', 'by_field': 'mz_jc', 'base_inc': 10, 'percent': '0.1%'},
                8: {'role_field': 'pofang', 'by_field': 'pf_jc', 'base_inc': 10, 'percent': '0.1%'},
                9: {'role_field': 'xixue', 'by_field': 'xx_jc', 'base_inc': 10, 'percent': '0.1%'},
            }
            config = ATTR_CONFIG.get(r)
            # 计算增量值
            multiplier = 2 if is_up_stage == 1 else 1
            inc_value = config['base_inc'] * multiplier
            display_value = float(config['base_inc'] * multiplier) / (100 if '%' in config['percent'] else 1)
            # 更新角色表
            role_sql = f"UPDATE user_role SET {config['role_field']} = {config['role_field']} + %s WHERE uid = %s AND id = %s LIMIT 1"
            await cursor.execute(role_sql, (inc_value, uid, role_id))
            if cursor.rowcount != 1:
                raise RuntimeError("本源升级角色属性更新失败")
            # 更新本源表
            by_sql = f"UPDATE user_benyuan SET {config['by_field']} = {config['by_field']} + %s, dengji = dengji + 1 WHERE id = %s AND uid = %s AND dengji = %s LIMIT 1"
            await cursor.execute(by_sql, (inc_value, by_id, uid, benyuan_dengji))
            if cursor.rowcount != 1:
                raise RuntimeError("本源等级更新失败")

            by_dengji = benyuan_dengji + 1
            unlocked_skills = await sync_unlock_benyuan_skills(uid, role_id, by_id, role_name, by_dengji, cursor)
            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)

            # 材料、本源、角色属性与战力快照一次提交。
            await conn.commit()

            # 设置显示文本
            up_attr = f"{config['role_field'].split('_')[0].capitalize()}+{display_value}{config['percent']}"
            if 20 <= by_dengji < 40:
                stage = f"五转·"
            elif 40 <= by_dengji < 60:
                stage = f"天启·"
            elif by_dengji == 60:
                stage = f"终焉·"
            else:
                stage = ""

            output = f"恭喜您升级本源成功！\n"
            output += f"本源名称：{stage}{by_name}\n"
            output += f"本源等级：{by_dengji}级\n"
            output += f"本次本源加成的属性为：{up_attr}\n"
            if unlocked_skills:
                unlocked_names = "、".join(skill["skill_name"] for skill in unlocked_skills)
                output += f"🎉 本次解锁本源技能：{unlocked_names}\n"
            output += "Tips:角色本源提升可为角色随机单属性提供百分比增幅。\n"

            kj = await all_write_command(uid, (f"查看本源", "本源技能", "物品背包"))

            return {"type": "markdown", "content": output + kj}


# 本源技能
@reg_xz_func
async def by_skill(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name`, dengji, by_id FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您当前没有出战角色，无法查看本源技能。\n"}
            role_id, role_name, role_dengji, by_id = result

            await cursor.execute("SELECT `name`, dengji FROM user_benyuan WHERE id = %s AND uid = %s LIMIT 1", (by_id, uid))
            benyuan_result = await cursor.fetchone()
            if benyuan_result is None:
                return {"type": "markdown", "content": qz + "当前角色本源数据异常，请重新收回并出战角色后重试。\n"}
            by_name, benyuan_level = benyuan_result

            unlocked_now = await sync_unlock_benyuan_skills(uid, role_id, by_id, role_name, benyuan_level, cursor)
            if unlocked_now:
                await conn.commit()

            await cursor.execute("""
                SELECT id, unlock_level, skill_name, skill_type, `value`, is_percent, cooldown,
                       buff_type, buff_value, buff_duration, buff_target, skill_desc, priority
                FROM data_benyuan_skill
                WHERE role_name = %s
                ORDER BY unlock_level ASC
            """, (role_name,))
            all_skills = await cursor.fetchall()

            await cursor.execute("""
                SELECT benyuan_skill_id
                FROM user_benyuan_skill
                WHERE uid = %s AND role_id = %s
            """, (uid, role_id))
            unlocked_ids = {row[0] for row in (await cursor.fetchall() or [])}

            if 20 <= benyuan_level < 40:
                stage = "五转"
            elif 40 <= benyuan_level < 60:
                stage = "天启"
            elif benyuan_level >= 60:
                stage = "终焉"
            else:
                stage = "初源"

            lines = []
            lines.append(f"##### 本源技能")
            lines.append(f"**出战角色：** [{role_id}] {role_name} Lv.{role_dengji}")
            lines.append(f"**本源状态：** {stage}·{by_name}（{benyuan_level}/60）")
            lines.append("***")

            if unlocked_now:
                now_names = "、".join(skill["skill_name"] for skill in unlocked_now)
                lines.append(f"🎉 **本次新增解锁：** {now_names}")
                lines.append("")

            if not all_skills:
                lines.append("> 当前角色暂无本源技能配置，请联系管理员补充 data_benyuan_skill。")
            else:
                for skill in all_skills:
                    (skill_id, unlock_level, skill_name, skill_type, value, is_percent, cooldown,
                     buff_type, buff_value, buff_duration, buff_target, skill_desc, priority) = skill

                    unlocked = skill_id in unlocked_ids
                    status = "✅ 已解锁" if unlocked else "🔒 未解锁"
                    value_text = f"{value}%" if is_percent == 1 else f"{value}"
                    buff_text = _format_benyuan_buff_display(skill_name, buff_type, buff_value, buff_duration, buff_target)

                    lines.append(f"**[{status}] {skill_name}**（Lv.{unlock_level}解锁）")
                    lines.append(f"> 类型：{_skill_type_name(skill_type)} | 强度：{value_text} | 冷却：{cooldown}回合 | 优先级：{priority}")
                    lines.append(f"> 效果：{skill_desc if skill_desc else '无描述'}")
                    lines.append(f"> BUFF：{buff_text}")
                    lines.append("")

            next_unlock = None
            for lv in (20, 40, 60):
                if benyuan_level < lv:
                    next_unlock = lv
                    break
            if next_unlock:
                lines.append(f"> 下一本源技能解锁等级：Lv.{next_unlock}")
            else:
                lines.append("> 已解锁全部本源技能。")

            lines.append("***")
            kj = await all_write_command(uid, ("查看本源", "本源升级", "副本列表"))
            lines.append(kj)

            return {"type": "markdown", "content": qz + "\n".join(lines)}
