# -*- coding: utf-8 -*-
"""灵石商城：提供不直接出售战力的便利型消耗品。"""

from datetime import date, timedelta

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql
from Tool.tool_command import pagination_controls
from Game_domain.dungeon_daily_limit import (
    DAILY_DUNGEON_ATTEMPT_LIMIT,
    MAX_DUNGEON_ATTEMPT_LIMIT,
    ensure_daily_attempt_schema,
    get_daily_attempt_status,
    increase_daily_attempt_limit,
)


SHOP_PAGE_SIZE = 6
FREE_DAILY_CHALLENGES = DAILY_DUNGEON_ATTEMPT_LIMIT
DAILY_CHALLENGE_CAP = MAX_DUNGEON_ATTEMPT_LIMIT
STAMINA_POTION_ITEM_ID = 209
STAMINA_POTION_RESTORE = 5
DUNGEON_SWEEP_TICKET_ITEM_ID = 211
DUNGEON_SWEEP_TICKET_DAILY_LIMIT = 20
DIRECTIONAL_SMELTING_JADE_ITEM_ID = 212

# 商品价格以当前副本、药园和炼丹的灵石产出为基准；商品均可由后续运营在
# data_shop_item 表中调整，不在业务逻辑中硬编码价格。
DEFAULT_SHOP_ITEMS = (
    {
        "name": "体力药",
        "item_id": STAMINA_POTION_ITEM_ID,
        "price": 500,
        "category": "历练",
        "daily_limit": 4,
        "weekly_limit": 0,
        "description": "使用后恢复5次副本历练次数；当日历练次数最多为40次。",
    },
    {
        "name": "扫荡副本券",
        "item_id": DUNGEON_SWEEP_TICKET_ITEM_ID,
        "price": 800,
        "category": "历练",
        "daily_limit": DUNGEON_SWEEP_TICKET_DAILY_LIMIT,
        "weekly_limit": 0,
        "description": "消耗1张可一键扫荡已通关副本，同时消耗1次副本历练次数。",
    },
    {
        "name": "灵草培育液",
        "item_id": 210,
        "price": 250,
        "category": "药园",
        "daily_limit": 8,
        "weekly_limit": 0,
        "description": "对已播种且未成熟的药田施用，可立即成熟并采摘。",
    },
    {
        "name": "炼丹加速卡",
        "item_id": 208,
        "price": 300,
        "category": "炼丹",
        "daily_limit": 8,
        "weekly_limit": 0,
        "description": "使指定炼制中的丹炉立即完成；不改变炼丹成功率。",
    },
    {
        "name": "悟道天书",
        "item_id": 1,
        "price": 800,
        "category": "修行",
        "daily_limit": 2,
        "weekly_limit": 0,
        "description": "悟道进阶时自动消耗，额外提高50%成功率。",
    },
    {
        "name": "定枢玉",
        "item_id": DIRECTIONAL_SMELTING_JADE_ITEM_ID,
        "price": 12000,
        "category": "炼器",
        "daily_limit": 0,
        "weekly_limit": 2,
        "description": "定向熔炼装备时消耗，可指定熔炼产物的装备部位。",
    },
)


def parse_name_num(param):
    """解析“商品名-数量”；省略数量或以“-”结尾时默认购买一件。"""
    text = str(param or "").strip()
    if "-" not in text:
        return (text, 1) if text else (None, None)
    name, num_text = text.rsplit("-", 1)
    name = name.strip()
    if not num_text.strip():
        return (name, 1) if name else (None, None)
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
            weekly_limit INT NOT NULL DEFAULT 0,
            enabled TINYINT NOT NULL DEFAULT 1,
            PRIMARY KEY (id),
            UNIQUE KEY uk_name (name),
            UNIQUE KEY uk_item_id (item_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='基础_灵石商城商品'
        """
    )
    # 兼容已上线的商城表：早期版本没有周限购字段。
    await cursor.execute("SHOW COLUMNS FROM data_shop_item LIKE 'weekly_limit'")
    if not await cursor.fetchone():
        await cursor.execute(
            "ALTER TABLE data_shop_item ADD COLUMN weekly_limit INT NOT NULL DEFAULT 0 AFTER daily_limit"
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
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_shop_weekly (
            uid INT NOT NULL,
            item_id INT NOT NULL,
            week_start DATE NOT NULL,
            bought_num INT NOT NULL DEFAULT 0,
            PRIMARY KEY (uid, item_id, week_start),
            KEY idx_week_start (week_start)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_商城每周购买记录'
        """
    )

    item_definitions = (
        (1, "悟道天书", "可提升悟道进阶概率。", "副本掉落、灵石商城"),
        (208, "炼丹加速卡", "使指定丹炉立即完成炼制。", "药园炼丹、灵石商城"),
        (209, "体力药", "恢复副本历练次数，每次恢复5次。", "灵石商城"),
        (210, "灵草培育液", "使已播种药田立即成熟。", "灵石商城"),
        (211, "扫荡副本券", "可一键扫荡已通关副本。", "灵石商城"),
        (DIRECTIONAL_SMELTING_JADE_ITEM_ID, "定枢玉", "定向熔炼装备时消耗，可指定产物部位。", "灵石商城（每周限购）"),
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
            INSERT INTO data_shop_item (name, item_id, price, category, description, daily_limit, weekly_limit, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE item_id = VALUES(item_id), price = VALUES(price),
                category = VALUES(category), description = VALUES(description),
                daily_limit = VALUES(daily_limit), weekly_limit = VALUES(weekly_limit), enabled = 1
            """,
            (
                item["name"], item["item_id"], item["price"], item["category"],
                item["description"], item["daily_limit"], item["weekly_limit"],
            ),
        )
    # 体力药保持正常供给；每日4瓶，每瓶扩充5次，当日总额度最多40次。
    await cursor.execute(
        "UPDATE data_shop_item SET enabled=1,daily_limit=4 WHERE item_id=%s",
        (STAMINA_POTION_ITEM_ID,),
    )


async def _get_shop_item(cursor, item_name):
    await cursor.execute(
        """
        SELECT id, name, item_id, price, category, description, daily_limit, weekly_limit
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
        "weekly_limit": int(row[7]),
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
            week_start = today - timedelta(days=today.weekday())
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
                SELECT d.name, d.price, d.category, d.description, d.daily_limit, d.weekly_limit,
                       COALESCE(u.bought_num, 0), COALESCE(w.bought_num, 0)
                FROM data_shop_item d
                LEFT JOIN user_shop_daily u
                    ON u.uid = %s AND u.item_id = d.item_id AND u.stat_date = %s
                LEFT JOIN user_shop_weekly w
                    ON w.uid = %s AND w.item_id = d.item_id AND w.week_start = %s
                WHERE d.enabled = 1
                ORDER BY d.category, d.id
                LIMIT %s OFFSET %s
                """,
                (uid, today, uid, week_start, SHOP_PAGE_SIZE, offset),
            )
            rows = await cursor.fetchall()
            await conn.commit()

    lines = [f"##### 🏪 灵石商城（第{page}/{total_pages}页）", f"> 当前灵石：**{lingshi}**", "***"]
    for name, price, category, description, daily_limit, weekly_limit, bought_num, weekly_bought_num in rows:
        limits = []
        if int(daily_limit) > 0:
            limits.append(f"今日 {int(bought_num)}/{int(daily_limit)}")
        if int(weekly_limit) > 0:
            limits.append(f"本周 {int(weekly_bought_num)}/{int(weekly_limit)}")
        limit_text = "｜".join(limits) if limits else "不限购"
        lines.append(f"**【{category}】{name}**")
        lines.append(f"> {description}")
        lines.append(f"> 价格：**{price} 灵石** ｜ 限购：{limit_text}")
        lines.append(f"<qqbot-cmd-input text='购买商品 {name}' show='购买1件' /> | <qqbot-cmd-input text='购买商品 {name}-5' show='购买5件' />")
        lines.append("")
    lines.extend([
        "***",
        "便捷道具只缩短等待或补充可玩次数，不直接出售装备、技能与副本稀有材料。",
        pagination_controls("商城", page, total_pages),
        "<qqbot-cmd-input text='购买商品 ' show='购买商品 名称[-数量]' /> | <qqbot-cmd-input text='使用体力药' show='使用1瓶体力药' /> | <qqbot-cmd-input text='副本菜单' show='副本菜单' />",
    ])
    return {"type": "markdown", "content": "\n".join(lines)}


@reg_xz_func
async def buy_shop_item(uid, qz, param):
    item_name, count = parse_name_num(param)
    if not item_name:
        return {"type": "markdown", "content": "指令错误，正确指令：购买商品 商品名[-数量]\n示例：购买商品 体力药 或 购买商品 体力药-5"}

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_shop_schema(cursor)
            item = await _get_shop_item(cursor, item_name)
            if not item:
                await conn.rollback()
                return {"type": "markdown", "content": f"商城没有出售：{item_name}。可发送“商城”查看商品。"}

            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            bought_num = 0
            weekly_bought_num = 0
            if item["daily_limit"] > 0:
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
                if bought_num + count > item["daily_limit"]:
                    await conn.rollback()
                    remain = max(0, item["daily_limit"] - bought_num)
                    return {"type": "markdown", "content": f"{item['name']}今日限购{item['daily_limit']}个，已购买{bought_num}个，还可购买{remain}个。"}
            if item["weekly_limit"] > 0:
                await cursor.execute(
                    """
                    INSERT INTO user_shop_weekly (uid, item_id, week_start, bought_num)
                    VALUES (%s, %s, %s, 0)
                    ON DUPLICATE KEY UPDATE bought_num = bought_num
                    """,
                    (uid, item["item_id"], week_start),
                )
                await cursor.execute(
                    """
                    SELECT bought_num FROM user_shop_weekly
                    WHERE uid = %s AND item_id = %s AND week_start = %s FOR UPDATE
                    """,
                    (uid, item["item_id"], week_start),
                )
                weekly_bought_num = int((await cursor.fetchone())[0] or 0)
                if weekly_bought_num + count > item["weekly_limit"]:
                    await conn.rollback()
                    remain = max(0, item["weekly_limit"] - weekly_bought_num)
                    return {"type": "markdown", "content": f"{item['name']}本周限购{item['weekly_limit']}个，已购买{weekly_bought_num}个，还可购买{remain}个。"}

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
            if item["daily_limit"] > 0:
                await cursor.execute(
                    """
                    UPDATE user_shop_daily SET bought_num = bought_num + %s
                    WHERE uid = %s AND item_id = %s AND stat_date = %s
                    """,
                    (count, uid, item["item_id"], today),
                )
            if item["weekly_limit"] > 0:
                await cursor.execute(
                    """
                    UPDATE user_shop_weekly SET bought_num = bought_num + %s
                    WHERE uid = %s AND item_id = %s AND week_start = %s
                    """,
                    (count, uid, item["item_id"], week_start),
                )
            await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s LIMIT 1", (uid,))
            balance = int((await cursor.fetchone())[0] or 0)
            await conn.commit()
    from Game_main.g16_onboarding import record_onboarding_event
    await record_onboarding_event(uid, "SHOP")
    from Game_main.g25_daily_tasks import record_daily_event
    await record_daily_event(uid, "SHOP")

    return {
        "type": "markdown",
        "content": "\n".join((
            "##### 购买成功", f"获得：{item['name']} x {count}", f"消耗灵石：{total_price}",
            f"剩余灵石：{balance}", "***",
            "<qqbot-cmd-input text='商城' show='商城' /> | <qqbot-cmd-input text='物品背包' show='物品背包' />",
        )),
    }


@reg_xz_func
async def use_stamina_potion(uid, qz, param):
    if not str(param or "").strip():
        param = 1
    try:
        count = int(str(param).strip())
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return {
            "type": "markdown",
            "content": "指令错误，正确指令：使用体力药 数量\n示例：使用体力药 1",
        }

    restore = count * STAMINA_POTION_RESTORE
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_shop_schema(cursor)
            await ensure_daily_attempt_schema(cursor)
            status = await get_daily_attempt_status(cursor, uid, lock=True)
            if not status:
                await conn.rollback()
                return {
                    "type": "markdown",
                    "content": "未找到玩家数据，请重新注册后再试。",
                }
            if status["limit"] + restore > DAILY_CHALLENGE_CAP:
                await conn.rollback()
                usable = max(
                    0,
                    (DAILY_CHALLENGE_CAP - status["limit"])
                    // STAMINA_POTION_RESTORE,
                )
                return {
                    "type": "markdown",
                    "content": (
                        f"今日历练额度为{status['limit']}次，使用后不能超过"
                        f"{DAILY_CHALLENGE_CAP}次。当前最多还能使用{usable}瓶体力药。"
                    ),
                }
            if not await _deduct_user_item(
                cursor, uid, STAMINA_POTION_ITEM_ID, count
            ):
                await conn.rollback()
                return {
                    "type": "markdown",
                    "content": f"体力药不足，需要{count}瓶。",
                }
            result = await increase_daily_attempt_limit(cursor, uid, restore)
            if not result:
                await conn.rollback()
                return {
                    "type": "markdown",
                    "content": "今日历练额度已达上限，体力药未消耗。",
                }
            await conn.commit()

    return {
        "type": "markdown",
        "content": "\n".join((
            "##### 体力恢复成功",
            f"使用体力药：**x {count}**",
            f"今日历练额度：**+{result['added']}**",
            f"剩余历练次数：**{result['remaining']}**｜当日额度：**{result['limit']}/{DAILY_CHALLENGE_CAP}**",
            "***",
            "<qqbot-cmd-input text='副本菜单' show='副本菜单' /> | <qqbot-cmd-input text='副本列表' show='副本列表' />",
        )),
    }
