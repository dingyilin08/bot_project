# -*- coding: utf-8 -*-
"""P1 丹道研习：公开火候品质权重与分类耐药值。"""
from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql

FIRE_STYLES = {"保守": ("成功稳定，品质上限较低", (70, 23, 6, 1)), "均衡": ("成功与品质兼顾", (55, 30, 12, 3)), "冒险": ("更高品质权重，同时承受更高炸炉风险", (38, 34, 20, 8))}
QUALITIES = ("寻常", "小成", "大成", "圆满")

def quality_weights(style, mastery):
    if style not in FIRE_STYLES: return None
    base = list(FIRE_STYLES[style][1]); boost = min(12, int(mastery) // 10)
    base[0] -= boost; base[2] += boost // 2; base[3] += boost - boost // 2
    return dict(zip(QUALITIES, base))

def tolerance_multiplier(count):
    return (100, 85, 70, 55, 40)[min(4, max(0, int(count)))]

async def record_alchemy_start(uid, recipe_name):
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("INSERT INTO user_alchemy_mastery (uid, recipe_name, mastery) VALUES (%s, %s, 1) ON DUPLICATE KEY UPDATE mastery = mastery + 1", (uid, recipe_name))
                await conn.commit()
    except Exception: pass

async def record_pill_tolerance(uid, pill_name, count):
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("INSERT INTO user_pill_tolerance (uid, pill_name, use_count) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE use_count = use_count + VALUES(use_count)", (uid, pill_name, count))
                await conn.commit()
    except Exception: pass

@reg_xz_func
async def alchemy_study(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT recipe_name, mastery FROM user_alchemy_mastery WHERE uid = %s ORDER BY mastery DESC LIMIT 5", (uid,))
            rows = await cursor.fetchall()
    output = "##### 🧪 丹道研习\n\n火候会影响品质权重；熟练度每 10 点将部分寻常权重转为高品质权重。\n\n"
    for style, (desc, _) in FIRE_STYLES.items(): output += f"**{style}**：{desc}\n> 寻常/小成/大成/圆满：{'/'.join(map(str, quality_weights(style, 0).values()))}%\n"
    output += "\n**已研习丹方**\n" + ("\n".join(f"> {row[0]}：熟练度 {row[1]}" for row in rows) if rows else "> 尚未开始炼丹。")
    return {"type":"markdown","content":output + "\n\n<qqbot-cmd-input text='炼丹菜单' show='前往炼丹' /> | <qqbot-cmd-input text='药性' show='查看药性' />"}

@reg_xz_func
async def pill_property(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT pill_name, use_count FROM user_pill_tolerance WHERE uid = %s ORDER BY use_count DESC LIMIT 8", (uid,))
            rows = await cursor.fetchall()
    output = "##### 💊 药性\n\n同类丹药的耐药值会降低后续永久属性收益；战斗消耗丹不受此项影响。\n\n"
    output += "\n".join(f"> {row[0]}：耐药 {row[1]}，当前效力 {tolerance_multiplier(row[1])}%" for row in rows) if rows else "> 尚未产生耐药记录。"
    return {"type":"markdown","content":output + "\n\n<qqbot-cmd-input text='丹道研习' show='丹道研习' />"}
