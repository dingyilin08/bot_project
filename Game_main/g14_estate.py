# -*- coding: utf-8 -*-
"""P1 洞府生产中枢：建筑升级与每日离线产出。"""

from datetime import date
from hashlib import sha256
from random import Random

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


MAX_LEVEL = 10
BUILDINGS = {
    "聚灵阵": ("提升参悟效率；每日提供稳定灵气", "参悟效率", 1),
    "炼器台": ("副本材料的炼器研究场；每日提供锻造灵息", "锻造灵息", 2),
    "灵兽园": ("扩展灵兽培养环境；每日提供御兽灵息", "御兽灵息", 2),
    "藏经阁": ("记录流派心得；每日提供研习灵息", "研习灵息", 3),
}


def upgrade_cost(building, next_level):
    """统一且公开的灵石升级成本；不使用付费专属货币。"""
    if building not in BUILDINGS or not 2 <= next_level <= MAX_LEVEL:
        return None
    weight = BUILDINGS[building][2]
    return 120 * weight * (next_level - 1) ** 2


def claim_reward(levels, mode, uid, claim_date):
    """生成可重放的每日产出，避免重试改变结算结果。"""
    total_level = sum(int(level) for level in levels.values())
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


async def _levels(uid, cursor, for_update=False):
    suffix = " FOR UPDATE" if for_update else ""
    await cursor.execute(f"SELECT building_type, level FROM user_estate_building WHERE uid = %s{suffix}", (uid,))
    return {name: int(level) for name, level in await cursor.fetchall()}


@reg_xz_func
async def estate_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_estate_rows(uid, cursor)
            levels = await _levels(uid, cursor)
            await conn.commit()
    output = "##### 🏯 洞府\n\n"
    output += "离线灵气每日可选一次收取；冒险共鸣只改变当日灵石品质，不售卖加速。\n\n"
    for name, (description, benefit, _) in BUILDINGS.items():
        level = levels.get(name, 1)
        next_cost = upgrade_cost(name, level + 1)
        cost_text = f"下级消耗 {next_cost} 灵石" if next_cost else "已达满级"
        output += f"**{name} Lv.{level}/{MAX_LEVEL}**\n> {description}\n> 即时收益：{benefit}｜{cost_text}\n\n"
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
            await _ensure_estate_rows(uid, cursor)
            levels = await _levels(uid, cursor, for_update=True)
            current = levels[name]
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
            await _ensure_estate_rows(uid, cursor)
            levels = await _levels(uid, cursor, for_update=True)
            await cursor.execute("INSERT IGNORE INTO user_estate_claim (uid, claim_date, claim_mode) VALUES (%s, %s, %s)", (uid, today, mode))
            if cursor.rowcount <= 0:
                await conn.rollback()
                return {"type": "markdown", "content": "今日已收取洞府产出，请明日再来。"}
            reward, description = claim_reward(levels, mode, uid, today)
            await cursor.execute("UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s", (reward, uid))
            await conn.commit()
    return {"type": "markdown", "content": f"##### ✨ 洞府收取\n\n方式：{mode}\n获得灵石：**{reward}**\n> {description}\n\n<qqbot-cmd-input text='洞府' show='查看洞府' />"}
