# -*- coding: utf-8 -*-
"""灵石商城：提供不直接出售战力的便利型消耗品。"""

from datetime import date

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


SHOP_PAGE_SIZE = 6
FREE_DAILY_CHALLENGES = 20
DAILY_CHALLENGE_CAP = 40
STAMINA_POTION_ITEM_ID = 209
STAMINA_POTION_RESTORE = 5

# 商品价格以当前副本、药园和炼丹的灵石产出为基准；商品均可由后续运营在
# data_shop_item 表中调整，不在业务逻辑中硬编码价格。
DEFAULT_SHOP_ITEMS = (
    {
        "name": "体力药",
        "item_id": STAMINA_POTION_ITEM_ID,
        "price": 500,
        "category": "历练",
        "daily_limit": 4,
        "description": "使用后恢复5次副本历练次数；当日历练次数最多为40次。",
    },
    {
        "name": "灵草培育液",
        "item_id": 210,
        "price": 250,
        "category": "药园",
        "daily_limit": 8,
        "description": "对已播种且未成熟的药田施用，可立即成熟并采摘。",
    },
    {
        "name": "炼丹加速卡",
        "item_id": 208,
        "price": 300,
        "category": "炼丹",
        "daily_limit": 8,
        "description": "使指定炼制中的丹炉立即完成；不改变炼丹成功率。",
    },
    {
        "name": "悟道天书",
        "item_id": 1,
        "price": 800,
        "category": "修行",
        "daily_limit": 2,
        "description": "悟道进阶时自动消耗，额外提高50%成功率。",
    },
)


def parse_name_num(param):
    """解析“商品名-数量”，数量必须是正整数。"""
    if "-" not in str(param):
        return None, None
    name, num_text = str(param).rsplit("-", 1)
    name = name.strip()
    try:
        num = int(num_text.strip())
    except (TypeError, ValueError):
        return None, None
    if not name or num <= 0:
        return None, None
    return name, num


async def _ensure_shop_schema(cursor):
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS data_shop_item (
            id INT NOT NULL AUTO_INCREMENT,
            name VARCHAR(50) NOT NULL,
            item_id INT NOT NULL,
            price INT NOT NULL,
            category VARCHAR(20) NOT NULL,
            description VARCHAR(255) NOT NULL,
            daily_limit INT NOT NULL DEFAULT 0,
            enabled TINYINT NOT NULL DEFAULT 1,
            PRIMARY KEY (id),
            UNIQUE KEY uk_name (name),
            UNIQUE KEY uk_item_id (item_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_灵石商城商品'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_shop_daily (
            uid INT NOT NULL,
            item_id INT NOT NULL,
            stat_date DATE NOT NULL,
            bought_num INT NOT NULL DEFAULT 0,
            PRIMARY KEY (uid, item_id, stat_date),
            KEY idx_stat_date (stat_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_商城每日购买记录'
        """
    )

    item_definitions = (
        (1, "悟道天书", "可提升悟道进阶概率。", "副本掉落、灵石商城"),
        (208, "炼丹加速卡", "使指定丹炉立即完成炼制。", "药园炼丹、灵石商城"),
        (209, "体力药", "恢复副本历练次数，每次恢复5次。", "灵石商城"),
        (210, "灵草培育液", "使已播种药田立即成熟。", "灵石商城"),
    )
    for item_id, name, description, access in item_definitions:
        await cursor.execute(
            """
            INSERT INTO data_item (id, name, type, `desc`, access)
            VALUES (%s, %s, 3, %s, %s)
            ON DUPLICATE KEY UPDATE name = VALUES(name), `desc` = VALUES(`desc`), access = VALUES(access)
            """,
            (item_id, name, description, access),
        )

    for item in DEFAULT_SHOP_ITEMS:
        await cursor.execute(
            """
            INSERT INTO data_shop_item (name, item_id, price, category, description, daily_limit, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE item_id = VALUES(item_id), price = VALUES(price),
                category = VALUES(category), description = VALUES(description),
                daily_limit = VALUES(daily_limit), enabled = 1
            """,
            (
                item["name"], item["item_id"], item["price"], item["category"],
                item["description"], item["daily_limit"],
            ),
        )


async def _get_shop_item(cursor, item_name):
    await cursor.execute(
        """
        SELECT id, name, item_id, price, category, description, daily_limit
        FROM data_shop_item WHERE name = %s AND enabled = 1 LIMIT 1
        """,
        (item_name,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": int(row[0]), "name": row[1], "item_id": int(row[2]), "price": int(row[3]),
        "category": row[4], "description": row[5], "daily_limit": int(row[6]),
    }


async def _add_user_item(cursor, uid, item_id, count):
    await cursor.execute(
        """
        INSERT INTO user_item (uid, item_id, item_num) VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE item_num = item_num + VALUES(item_num)
        """,
        (uid, item_id, count),
    )


async def _deduct_user_item(cursor, uid, item_id, count):
    await cursor.execute(
        """
        UPDATE user_item SET item_num = item_num - %s
        WHERE uid = %s AND item_id = %s AND item_num >= %s
        """,
        (count, uid, item_id, count),
    )
    if cursor.rowcount <= 0:
        return False
    await cursor.execute(
        "DELETE FROM user_item WHERE uid = %s AND item_id = %s AND item_num <= 0",
        (uid, item_id),
    )
    return True


@reg_xz_func
async def show_shop(uid, qz, page=1):
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_shop_schema(cursor)
            today = date.today()
            await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s LIMIT 1", (uid,))
            balance_row = await cursor.fetchone()
            lingshi = int((balance_row or [0])[0] or 0)
            await cursor.execute("SELECT COUNT(*) FROM data_shop_item WHERE enabled = 1")
            total = int((await cursor.fetchone())[0] or 0)
            total_pages = max(1, (total + SHOP_PAGE_SIZE - 1) // SHOP_PAGE_SIZE)
            page = min(page, total_pages)
            offset = (page - 1) * SHOP_PAGE_SIZE
            await cursor.execute(
                """
                SELECT d.name, d.price, d.category, d.description, d.daily_limit,
                       COALESCE(u.bought_num, 0)
                FROM data_shop_item d
                LEFT JOIN user_shop_daily u
                    ON u.uid = %s AND u.item_id = d.item_id AND u.stat_date = %s
                WHERE d.enabled = 1
                ORDER BY d.category, d.id
                LIMIT %s OFFSET %s
                """,
                (uid, today, SHOP_PAGE_SIZE, offset),
            )
            rows = await cursor.fetchall()
            await conn.commit()

    lines = [f"##### 🏪 灵石商城（{page}/{total_pages}页）", f"> 当前灵石：{lingshi}", "***"]
    for name, price, category, description, daily_limit, bought_num in rows:
        limit_text = "不限购" if int(daily_limit) <= 0 else f"今日 {int(bought_num)}/{int(daily_limit)}"
        lines.append(f"**{name}**｜{category}｜{price}灵石｜{limit_text}")
        lines.append(f"> {description}")
        lines.append(f"<qqbot-cmd-input text='购买商品 {name}-' show='购买{name}*' />")
    lines.extend([
        "***",
        "便捷道具只缩短等待或补充可玩次数，不直接出售装备、技能与副本稀有材料。",
        f"<qqbot-cmd-enter text='商城 {max(1, page - 1)}' /> | <qqbot-cmd-enter text='商城 {min(total_pages, page + 1)}' />",
        "<qqbot-cmd-input text='购买商品 ' show='购买商品 名称-数量' /> | <qqbot-cmd-input text='使用体力药 ' show='使用体力药 数量' />",
    ])
    return {"type": "markdown", "content": "\n".join(lines)}


@reg_xz_func
async def buy_shop_item(uid, qz, param):
    item_name, count = parse_name_num(param)
    if not item_name:
        return {"type": "markdown", "content": "指令错误，正确指令：购买商品 商品名-数量\n示例：购买商品 体力药-1"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_shop_schema(cursor)
            item = await _get_shop_item(cursor, item_name)
            if not item:
                await conn.rollback()
                return {"type": "markdown", "content": f"商城没有出售：{item_name}。可发送“商城”查看商品。"}

            today = date.today()
            await cursor.execute(
                """
                INSERT INTO user_shop_daily (uid, item_id, stat_date, bought_num)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE bought_num = bought_num
                """,
                (uid, item["item_id"], today),
            )
            await cursor.execute(
                """
                SELECT bought_num FROM user_shop_daily
                WHERE uid = %s AND item_id = %s AND stat_date = %s FOR UPDATE
                """,
                (uid, item["item_id"], today),
            )
            bought_num = int((await cursor.fetchone())[0] or 0)
            if item["daily_limit"] > 0 and bought_num + count > item["daily_limit"]:
                await conn.rollback()
                remain = max(0, item["daily_limit"] - bought_num)
                return {"type": "markdown", "content": f"{item['name']}今日限购{item['daily_limit']}个，已购买{bought_num}个，还可购买{remain}个。"}

            total_price = item["price"] * count
            await cursor.execute(
                "UPDATE user_zt SET lingshi = lingshi - %s WHERE id = %s AND lingshi >= %s",
                (total_price, uid, total_price),
            )
            if cursor.rowcount <= 0:
                await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s LIMIT 1", (uid,))
                balance = int((await cursor.fetchone() or [0])[0] or 0)
                await conn.rollback()
                return {"type": "markdown", "content": f"灵石不足，购买需要{total_price}灵石，当前仅有{balance}灵石。"}

            await _add_user_item(cursor, uid, item["item_id"], count)
            await cursor.execute(
                """
                UPDATE user_shop_daily SET bought_num = bought_num + %s
                WHERE uid = %s AND item_id = %s AND stat_date = %s
                """,
                (count, uid, item["item_id"], today),
            )
            await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s LIMIT 1", (uid,))
            balance = int((await cursor.fetchone())[0] or 0)
            await conn.commit()

    return {
        "type": "markdown",
        "content": "\n".join((
            "##### 购买成功", f"获得：{item['name']} x {count}", f"消耗灵石：{total_price}",
            f"剩余灵石：{balance}", "***",
            "<qqbot-cmd-enter text='商城' /> | <qqbot-cmd-enter text='物品背包' />",
        )),
    }


@reg_xz_func
async def use_stamina_potion(uid, qz, param):
    try:
        count = int(str(param).strip())
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return {"type": "markdown", "content": "指令错误，正确指令：使用体力药 数量\n示例：使用体力药 1"}

    today = date.today()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_shop_schema(cursor)
            await cursor.execute(
                "SELECT dungeon_num, daily_dungeon_reset_time FROM user_zt WHERE id = %s FOR UPDATE",
                (uid,),
            )
            row = await cursor.fetchone()
            if not row:
                await conn.rollback()
                return {"type": "markdown", "content": "未找到玩家数据，请重新注册后再试。"}
            remaining = int(row[0] if row[0] is not None else FREE_DAILY_CHALLENGES)
            if row[1] != today:
                remaining = FREE_DAILY_CHALLENGES
                await cursor.execute(
                    "UPDATE user_zt SET dungeon_num = %s, daily_dungeon_reset_time = %s WHERE id = %s",
                    (remaining, today, uid),
                )

            restore = count * STAMINA_POTION_RESTORE
            if remaining + restore > DAILY_CHALLENGE_CAP:
                await conn.rollback()
                return {"type": "markdown", "content": f"当前历练次数为{remaining}，使用后不能超过每日上限{DAILY_CHALLENGE_CAP}次。请减少使用数量。"}
            if not await _deduct_user_item(cursor, uid, STAMINA_POTION_ITEM_ID, count):
                await conn.rollback()
                return {"type": "markdown", "content": f"体力药不足，需要{count}个。"}

            new_remaining = remaining + restore
            await cursor.execute(
                "UPDATE user_zt SET dungeon_num = %s, daily_dungeon_reset_time = %s WHERE id = %s",
                (new_remaining, today, uid),
            )
            await conn.commit()

    return {
        "type": "markdown",
        "content": "\n".join((
            "##### 体力恢复成功", f"使用体力药：x {count}", f"恢复历练次数：+{restore}",
            f"当前副本历练次数：{new_remaining}/{DAILY_CHALLENGE_CAP}", "***",
            "<qqbot-cmd-enter text='副本菜单' /> | <qqbot-cmd-enter text='副本列表' />",
        )),
    }
