# -*- coding: utf-8 -*-
"""洞府生产中枢：建筑升级、规则效果与每日离线产出。"""

from datetime import date
from hashlib import sha256
import json
from random import Random

import aiomysql

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql
from Game_domain.role_trait_service import calculate_lingshi_output


MAX_LEVEL = 10
ESTATE_RULE_VERSION = "estate.v1"
ESTATE_SNAPSHOT_SCHEMA_VERSION = 1
BASIS_POINTS = 10000
MIN_CANWU_SECONDS = 30

# 数据库旧表仍保存中文建筑名；所有新快照和跨模块接口只使用稳定 code。
BUILDING_CODE_TO_NAME = {
    "spirit_array": "聚灵阵",
    "forge_table": "炼器台",
    "beast_garden": "灵兽园",
    "scripture_library": "藏经阁",
}
BUILDING_NAME_TO_CODE = {name: code for code, name in BUILDING_CODE_TO_NAME.items()}
BUILDINGS = {
    "聚灵阵": ("提升参悟效率；每日提供稳定灵气", "参悟效率", 1),
    "炼器台": ("副本材料的炼器研究场；每日提供锻造灵息", "锻造灵息", 2),
    "灵兽园": ("扩展灵兽培养环境；每日提供御兽灵息", "御兽灵息", 2),
    "藏经阁": ("记录流派心得；每日提供研习灵息", "研习灵息", 3),
}

_ESTATE_CLAIM_SCHEMA_READY = False


def clamp_estate_level(value):
    """将旧库或外部输入的建筑等级限制在首版规则范围内。"""
    try:
        level = int(value)
    except (TypeError, ValueError):
        level = 1
    return min(MAX_LEVEL, max(1, level))


def normalize_estate_levels(levels_or_rows=None):
    """白名单化建筑等级，并返回稳定 code 键；未知建筑不会进入规则。"""
    normalized = {code: 1 for code in BUILDING_CODE_TO_NAME}
    if isinstance(levels_or_rows, dict):
        rows = levels_or_rows.items()
    else:
        rows = levels_or_rows or ()
    for raw_key, raw_level in rows:
        key = str(raw_key or "").strip()
        code = key if key in BUILDING_CODE_TO_NAME else BUILDING_NAME_TO_CODE.get(key)
        if code:
            normalized[code] = clamp_estate_level(raw_level)
    return normalized


def get_estate_level(levels, building_code):
    """从中文旧键或稳定 code 映射中读取一个白名单等级。"""
    if building_code not in BUILDING_CODE_TO_NAME:
        raise ValueError("未知洞府建筑 code")
    return normalize_estate_levels(levels)[building_code]


def cultivation_duration_reduction_bp(level):
    """聚灵阵每个额外等级减少2%参悟时长，最多18%。"""
    return min(1800, (clamp_estate_level(level) - 1) * 200)


def apply_cultivation_duration(base_seconds, level):
    """按基点向上取整参悟时长，并保证最低30秒。"""
    base_seconds = max(0, int(base_seconds))
    reduction_bp = cultivation_duration_reduction_bp(level)
    duration = (base_seconds * (BASIS_POINTS - reduction_bp) + BASIS_POINTS - 1) // BASIS_POINTS
    return max(MIN_CANWU_SECONDS, duration)


def forge_success_bonus_bp(level):
    """炼器台每个额外等级增加0.5个百分点，最多4.5个百分点。"""
    return min(450, (clamp_estate_level(level) - 1) * 50)


def spirit_beast_capacity(level):
    """灵兽园容量：Lv.1-3/4-6/7-9/10分别为4/5/6/7。"""
    return 4 + (clamp_estate_level(level) - 1) // 3


def scripture_skill_effect_bonus_bp(level):
    """藏经阁对新建PVE快照中已装备技能的效果加成，最多4.5%。"""
    return min(450, (clamp_estate_level(level) - 1) * 50)


def build_estate_effect_snapshot(levels):
    """供参悟、灵兽与PVE消费者复用的可序列化效果快照。"""
    normalized = normalize_estate_levels(levels)
    return {
        "schema_version": ESTATE_SNAPSHOT_SCHEMA_VERSION,
        "rule_version": ESTATE_RULE_VERSION,
        "levels": normalized,
        "effects": {
            "cultivation_duration_reduction_bp": cultivation_duration_reduction_bp(
                normalized["spirit_array"]
            ),
            "forge_success_bonus_bp": forge_success_bonus_bp(normalized["forge_table"]),
            "spirit_beast_capacity": spirit_beast_capacity(normalized["beast_garden"]),
            "pve_skill_effect_bonus_bp": scripture_skill_effect_bonus_bp(
                normalized["scripture_library"]
            ),
        },
    }


def format_basis_points(bp):
    """将基点展示为最多一位小数的百分数值。"""
    value = int(bp) / 100
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def building_effect_text(building_code, level):
    """返回洞府首页使用的当前真实效果说明。"""
    if building_code == "spirit_array":
        value = format_basis_points(cultivation_duration_reduction_bp(level))
        return f"新开始的参悟时长 -{value}%（最低{MIN_CANWU_SECONDS}秒）"
    if building_code == "forge_table":
        value = format_basis_points(forge_success_bonus_bp(level))
        return f"装备强化成功率 +{value}个百分点"
    if building_code == "beast_garden":
        level = clamp_estate_level(level)
        slot_text = "主契"
        if level >= 7:
            slot_text = "主契/护契/辅契"
        elif level >= 4:
            slot_text = "主契/护契"
        extra = "；一键照料与三套预设" if level >= 10 else ""
        return (
            f"灵兽容量 {spirit_beast_capacity(level)}只；"
            f"御兽灵息日产 {20 + level * 10}；灵阵位 {slot_text}{extra}"
        )
    if building_code == "scripture_library":
        value = format_basis_points(scripture_skill_effect_bonus_bp(level))
        return f"新建PVE快照的已装备技能效果 +{value}%"
    raise ValueError("未知洞府建筑 code")


def upgrade_cost(building, next_level):
    """统一且公开的灵石升级成本；不使用付费专属货币。"""
    if building not in BUILDINGS or not 2 <= next_level <= MAX_LEVEL:
        return None
    weight = BUILDINGS[building][2]
    return 120 * weight * (next_level - 1) ** 2


def claim_reward(levels, mode, uid, claim_date):
    """生成可重放的每日产出，避免重试改变结算结果。"""
    total_level = sum(normalize_estate_levels(levels).values())
    base = 20 + total_level * 8
    if mode == "稳健":
        return base, "稳定收取，没有额外风险。"
    rng = Random(sha256(f"estate:{uid}:{claim_date}".encode()).hexdigest())
    roll = rng.random()
    if roll < 0.20:
        return base * 2, "灵脉共鸣成功，产出翻倍！"
    if roll < 0.55:
        return int(base * 1.35), "灵脉泛起涟漪，获得额外产出。"
    return int(base * 0.7), "灵脉略有波动，本次产出减少，但建筑经验不受影响。"


async def _ensure_estate_rows(uid, cursor):
    for name in BUILDINGS:
        await cursor.execute("""
            INSERT IGNORE INTO user_estate_building (uid, building_type, level)
            VALUES (%s, %s, 1)
        """, (uid, name))


async def read_estate_levels(uid, cursor, for_update=False, ensure_rows=True):
    """读取白名单建筑等级；缺失、越界和未知旧数据均安全归一化。"""
    if ensure_rows:
        await _ensure_estate_rows(uid, cursor)
    suffix = " FOR UPDATE" if for_update else ""
    await cursor.execute(
        f"SELECT building_type, level FROM user_estate_building "
        f"WHERE uid = %s ORDER BY building_type{suffix}",
        (uid,),
    )
    return normalize_estate_levels(await cursor.fetchall())


async def _levels(uid, cursor, for_update=False):
    """保留旧内部调用名，返回稳定 code 等级映射。"""
    return await read_estate_levels(uid, cursor, for_update=for_update)


async def ensure_estate_claim_snapshot_columns(cursor):
    """兼容未先执行迁移的旧表；DDL仅在进程首次访问时检查一次。"""
    global _ESTATE_CLAIM_SCHEMA_READY
    if _ESTATE_CLAIM_SCHEMA_READY:
        return
    await cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'user_estate_claim'
          AND COLUMN_NAME IN (%s, %s, %s)
        """,
        ("reward_lingshi", "levels_json", "rule_version"),
    )
    existing = {str(row[0]) for row in await cursor.fetchall()}
    definitions = {
        "reward_lingshi": "BIGINT NULL COMMENT '本次实际灵石奖励'",
        "levels_json": "JSON NULL COMMENT '领取时建筑等级快照（稳定code）'",
        "rule_version": "VARCHAR(32) NULL COMMENT '洞府规则版本'",
    }
    for column, definition in definitions.items():
        if column in existing:
            continue
        try:
            await cursor.execute(
                f"ALTER TABLE user_estate_claim ADD COLUMN `{column}` {definition}"
            )
        except aiomysql.OperationalError as error:
            if not error.args or error.args[0] != 1060:
                raise
    _ESTATE_CLAIM_SCHEMA_READY = True


@reg_xz_func
async def estate_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            levels = await read_estate_levels(uid, cursor)
            await conn.commit()
    output = "##### 🏯 洞府\n\n"
    output += "离线灵气每日可选一次收取；冒险共鸣只改变当日灵石品质，不售卖加速。\n\n"
    for name, (description, benefit, _) in BUILDINGS.items():
        code = BUILDING_NAME_TO_CODE[name]
        level = levels[code]
        next_cost = upgrade_cost(name, level + 1)
        cost_text = f"下级消耗 {next_cost} 灵石" if next_cost else "已达满级"
        output += (
            f"**{name} Lv.{level}/{MAX_LEVEL}**\n"
            f"> {description}\n"
            f"> 当前生效：{building_effect_text(code, level)}\n"
            f"> 每日产出：{benefit}｜{cost_text}\n\n"
        )
    output += "<qqbot-cmd-input text='洞府收取 稳健' show='稳健收取' /> | <qqbot-cmd-input text='洞府收取 冒险' show='冒险共鸣' />\n\n"
    output += "<qqbot-cmd-input text='洞府升级 ' show='洞府升级 建筑名*' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def estate_upgrade(uid, qz, building):
    name = str(building or "").strip()
    if name not in BUILDINGS:
        return {"type": "markdown", "content": "建筑名称错误，可升级：聚灵阵、炼器台、灵兽园、藏经阁。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            levels = await read_estate_levels(uid, cursor, for_update=True)
            current = levels[BUILDING_NAME_TO_CODE[name]]
            if current >= MAX_LEVEL:
                return {"type": "markdown", "content": f"{name}已达满级。"}
            cost = upgrade_cost(name, current + 1)
            await cursor.execute("UPDATE user_zt SET lingshi = lingshi - %s WHERE id = %s AND lingshi >= %s", (cost, uid, cost))
            if cursor.rowcount <= 0:
                await conn.rollback()
                return {"type": "markdown", "content": f"灵石不足，{name}升至Lv.{current + 1}需要{cost}灵石。"}
            await cursor.execute("UPDATE user_estate_building SET level = level + 1 WHERE uid = %s AND building_type = %s", (uid, name))
            await conn.commit()
    return {"type": "markdown", "content": f"##### 🏯 洞府升级\n\n**{name}** 已升至 Lv.{current + 1}。\n消耗：{cost} 灵石\n\n<qqbot-cmd-input text='洞府' show='查看洞府' />"}


@reg_xz_func
async def estate_claim(uid, qz, mode):
    mode = str(mode or "").strip()
    if mode not in ("稳健", "冒险"):
        return {"type": "markdown", "content": "收取方式错误，请使用：洞府收取 稳健 或 洞府收取 冒险"}
    today = date.today().isoformat()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_estate_claim_snapshot_columns(cursor)
            levels = await read_estate_levels(uid, cursor, for_update=True)
            base_reward, description = claim_reward(levels, mode, uid, today)
            reward = await calculate_lingshi_output(cursor, uid, base_reward)
            levels_json = json.dumps(levels, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            await cursor.execute(
                """
                INSERT IGNORE INTO user_estate_claim
                    (uid, claim_date, claim_mode, reward_lingshi, levels_json, rule_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (uid, today, mode, reward, levels_json, ESTATE_RULE_VERSION),
            )
            if cursor.rowcount <= 0:
                await conn.rollback()
                return {"type": "markdown", "content": "今日已收取洞府产出，请明日再来。"}
            await cursor.execute("UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s", (reward, uid))
            beast_essence = 20 + levels["beast_garden"] * 10
            await cursor.execute("""
                INSERT INTO user_spirit_beast_wallet(uid,spirit_essence)
                VALUES(%s,%s)
                ON DUPLICATE KEY UPDATE
                    spirit_essence=spirit_essence+VALUES(spirit_essence)
            """, (uid, beast_essence))
            await conn.commit()
    trait_note = "\n> 叶凡特性「源术通灵」额外产出20%。" if reward > base_reward else ""
    return {"type": "markdown", "content": f"##### ✨ 洞府收取\n\n方式：{mode}\n获得灵石：**{reward}**\n获得御兽灵息：**{beast_essence}**\n> {description}{trait_note}\n\n<qqbot-cmd-input text='洞府' show='查看洞府' /> | <qqbot-cmd-input text='灵兽' show='诸天灵契' />"}
