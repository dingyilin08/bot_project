# -*- coding: utf-8 -*-
"""P1 丹道研习：公开火候品质权重与分类耐药值。"""
from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql

FIRE_STYLES = {"保守": ("成功稳定，品质上限较低", (70, 23, 6, 1)), "均衡": ("成功与品质兼顾", (55, 30, 12, 3)), "冒险": ("更高品质权重，同时承受更高炸炉风险", (38, 34, 20, 8))}
QUALITIES = ("寻常", "小成", "大成", "圆满")
QUALITY_OUTPUT = {"寻常": 1, "小成": 1, "大成": 2, "圆满": 3}
FIRE_SUCCESS_RATE = {"保守": 95, "均衡": 90, "冒险": 83}

def quality_weights(style, mastery):
    if style not in FIRE_STYLES: return None
    base = list(FIRE_STYLES[style][1]); boost = min(12, int(mastery) // 10)
    base[0] -= boost; base[2] += boost // 2; base[3] += boost - boost // 2
    return dict(zip(QUALITIES, base))

def tolerance_multiplier(count):
    return (100, 85, 70, 55, 40)[min(4, max(0, int(count)))]

def tolerance_factor(start_count, use_count):
    """多次服用的平均永久属性效力，按每一枚丹药分别计算。"""
    use_count = max(0, int(use_count))
    if not use_count:
        return 1.0
    return sum(tolerance_multiplier(int(start_count) + index) for index in range(use_count)) / (100 * use_count)

def roll_alchemy_outcome(style, mastery, roll):
    """用 1-100 掷点生成可展示的成功/品质/产量结果。"""
    style = style if style in FIRE_STYLES else "均衡"
    if int(roll) > FIRE_SUCCESS_RATE[style]:
        return False, None, 0
    cursor = int(roll) * 100 / FIRE_SUCCESS_RATE[style]
    total = 0
    for quality, weight in quality_weights(style, mastery).items():
        total += weight
        if cursor <= total:
            return True, quality, QUALITY_OUTPUT[quality]
    return True, "圆满", QUALITY_OUTPUT["圆满"]

async def get_alchemy_mastery(cursor, uid, recipe_name):
    try:
        await cursor.execute("SELECT mastery FROM user_alchemy_mastery WHERE uid = %s AND recipe_name = %s LIMIT 1", (uid, recipe_name))
        row = await cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0

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
    output = "##### 🧪 丹道研习\n\n火候会影响成功率与品质权重；熟练度每 10 点将部分寻常权重转为高品质权重。\n\n"
    for style, (desc, _) in FIRE_STYLES.items(): output += f"**{style}**：{desc}\n> 寻常/小成/大成/圆满：{'/'.join(map(str, quality_weights(style, 0).values()))}%\n"
    output += "\n**已研习丹方**\n" + ("\n".join(f"> {row[0]}：熟练度 {row[1]}" for row in rows) if rows else "> 尚未开始炼丹。")
    return {"type":"markdown","content":output + "\n\n炼丹时可用：`炼丹 火候-丹方名-炉号`，例如 `炼丹 冒险-九转丹-1`。\n<qqbot-cmd-input text='炼丹菜单' show='前往炼丹' /> | <qqbot-cmd-input text='药性' show='查看药性' />"}

@reg_xz_func
async def pill_property(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT pill_name, use_count FROM user_pill_tolerance WHERE uid = %s ORDER BY use_count DESC LIMIT 8", (uid,))
            rows = await cursor.fetchall()
    output = "##### 💊 药性\n\n同类丹药的耐药值会降低后续永久属性收益；战斗消耗丹不受此项影响。\n\n"
    output += "\n".join(f"> {row[0]}：耐药 {row[1]}，当前效力 {tolerance_multiplier(row[1])}%" for row in rows) if rows else "> 尚未产生耐药记录。"
    return {"type":"markdown","content":output + "\n\n<qqbot-cmd-input text='丹道研习' show='丹道研习' />"}
