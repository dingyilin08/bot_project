# -*- coding: utf-8 -*-
"""玩家坊市：托管挂单、收购单、成交记录与到期返还。"""

import math
import re
import time

from func.pd_func import pd_reg_func, reg_xz_func
from sql.mysql import connect_mysql


MARKET_PAGE_SIZE = 8
MARKET_FEE_BP = 800
MARKET_EXPIRE_HOURS = 72
MARKET_SEARCH_COOLDOWN = 2
MARKET_LISTING_COOLDOWN = 5
MAX_ORDER_QUANTITY = 9999
MAX_ORDER_TOTAL = 1_000_000_000
MARKET_CATEGORIES = ("丹药", "材料", "功法", "神通", "法宝", "坐骑", "消耗品")
BLOCKED_MARKERS = ("绑定", "任务", "轮回专属", "专属")


class MarketError(ValueError):
    pass


def calculate_market_fee(gross):
    """成交手续费按卖方收入的 8% 向下取整，避免灵石小数。"""
    return max(0, int(gross) * MARKET_FEE_BP // 10000)


def category_for_item(item_name, item_type):
    """将当前 data_item 的类型映射为坊市筛选分类。"""
    name = str(item_name or "")
    item_type = int(item_type or 0)
    if item_type == 4:
        return "丹药"
    if "法宝" in name or "飞剑" in name:
        return "法宝"
    if "坐骑" in name:
        return "坐骑"
    if item_type == 3 and ("诀" in name or "功" in name):
        return "功法"
    if item_type == 3 and ("术" in name or "卷轴" in name or "神通" in name):
        return "神通"
    if item_type in (1, 2, 5, 6, 7):
        return "材料"
    return "消耗品"


def parse_item_quantity_price(param, price_first=False):
    """解析物品、数量与单价；收购单可指定“物品名 单价 数量”。"""
    text = str(param or "").strip()
    match = re.fullmatch(r"(.+?)\s+(\d+)\s+(\d+)", text)
    if not match:
        match = re.fullmatch(r"(.+?)-(\d+)-(\d+)", text)
    if not match:
        raise MarketError("指令格式错误，应为：物品名 数量 单价。")
    name, first, second = match.groups()
    name = name.strip()
    if price_first:
        unit_price, quantity = int(first), int(second)
    else:
        quantity, unit_price = int(first), int(second)
    if not name or quantity <= 0 or unit_price <= 0:
        raise MarketError("物品名、数量和单价必须有效且大于 0。")
    if quantity > MAX_ORDER_QUANTITY or quantity * unit_price > MAX_ORDER_TOTAL:
        raise MarketError(f"单笔数量最多 {MAX_ORDER_QUANTITY}，总价最多 {MAX_ORDER_TOTAL} 灵石。")
    return name, quantity, unit_price


def parse_order_quantity(param, command_name):
    text = str(param or "").strip()
    match = re.fullmatch(r"(\d+)\s+(\d+)", text) or re.fullmatch(r"(\d+)-(\d+)", text)
    if not match:
        raise MarketError(f"指令格式错误，应为：{command_name} 摊位号 数量。")
    order_id, quantity = (int(value) for value in match.groups())
    if order_id <= 0 or quantity <= 0:
        raise MarketError("摊位号和数量必须大于 0。")
    return order_id, quantity


def parse_page(param):
    try:
        return max(1, int(str(param or "1").strip() or 1))
    except (TypeError, ValueError):
        return 1


def _buttons(*entries):
    return " | ".join(
        f"<qqbot-cmd-input text='{command}' show='{label}' />" for command, label in entries
    )


def _pagination(command, page, total_pages):
    if total_pages <= 1:
        return ""
    return _buttons(
        (f"{command} {max(1, page - 1)}", "上一页"),
        (f"{command} {min(total_pages, page + 1)}", "下一页"),
    )


async def _ensure_market_schema(cursor):
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_market_order (
            id BIGINT NOT NULL AUTO_INCREMENT,
            owner_uid INT NOT NULL,
            order_type VARCHAR(8) NOT NULL COMMENT 'SELL=出售，BUY=收购',
            item_id INT NOT NULL,
            item_name VARCHAR(255) NOT NULL,
            category VARCHAR(20) NOT NULL,
            initial_quantity INT NOT NULL,
            remaining_quantity INT NOT NULL,
            unit_price BIGINT NOT NULL,
            reserved_lingshi BIGINT NOT NULL DEFAULT 0,
            status VARCHAR(12) NOT NULL DEFAULT 'OPEN',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            closed_at DATETIME NULL,
            PRIMARY KEY (id),
            KEY idx_market_open (status, order_type, created_at),
            KEY idx_market_item (status, item_id, created_at),
            KEY idx_market_owner (owner_uid, status, created_at),
            KEY idx_market_expire (status, expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_坊市挂单与收购单'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_market_trade (
            id BIGINT NOT NULL AUTO_INCREMENT,
            order_id BIGINT NOT NULL,
            buyer_uid INT NOT NULL,
            seller_uid INT NOT NULL,
            item_id INT NOT NULL,
            item_name VARCHAR(255) NOT NULL,
            quantity INT NOT NULL,
            unit_price BIGINT NOT NULL,
            gross_lingshi BIGINT NOT NULL,
            fee_lingshi BIGINT NOT NULL,
            seller_income BIGINT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            KEY idx_trade_item (item_id, created_at),
            KEY idx_trade_buyer (buyer_uid, created_at),
            KEY idx_trade_seller (seller_uid, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_坊市成交记录'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_market_cooldown (
            uid INT NOT NULL,
            action_name VARCHAR(20) NOT NULL,
            last_at BIGINT NOT NULL,
            PRIMARY KEY (uid, action_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_坊市操作冷却'
        """
    )


async def _add_item(cursor, uid, item_id, quantity):
    await cursor.execute(
        """
        INSERT INTO user_item (uid, item_id, item_num) VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE item_num = item_num + VALUES(item_num)
        """,
        (uid, item_id, quantity),
    )


async def _deduct_item(cursor, uid, item_id, quantity):
    await cursor.execute(
        """
        UPDATE user_item SET item_num = item_num - %s
        WHERE uid = %s AND item_id = %s AND item_num >= %s
        """,
        (quantity, uid, item_id, quantity),
    )
    if cursor.rowcount <= 0:
        return False
    await cursor.execute(
        "DELETE FROM user_item WHERE uid = %s AND item_id = %s AND item_num <= 0",
        (uid, item_id),
    )
    return True


async def _expire_orders(cursor):
    """在每次坊市访问前归还过期资产；同一事务内锁定，避免重复返还。"""
    await cursor.execute(
        """
        SELECT id, owner_uid, order_type, item_id, remaining_quantity, reserved_lingshi
        FROM user_market_order
        WHERE status = 'OPEN' AND expires_at <= UTC_TIMESTAMP()
        FOR UPDATE
        """
    )
    expired = await cursor.fetchall()
    for order_id, owner_uid, order_type, item_id, remaining, reserved in expired:
        if order_type == "SELL" and int(remaining) > 0:
            await _add_item(cursor, owner_uid, item_id, int(remaining))
        elif order_type == "BUY" and int(reserved) > 0:
            await cursor.execute(
                "UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s",
                (int(reserved), owner_uid),
            )
        await cursor.execute(
            "UPDATE user_market_order SET status = 'EXPIRED', closed_at = UTC_TIMESTAMP() WHERE id = %s",
            (order_id,),
        )


async def _check_cooldown(cursor, uid, action_name, seconds):
    now = int(time.time())
    await cursor.execute(
        "SELECT last_at FROM user_market_cooldown WHERE uid = %s AND action_name = %s FOR UPDATE",
        (uid, action_name),
    )
    row = await cursor.fetchone()
    if row and now - int(row[0]) < seconds:
        raise MarketError(f"坊市操作过于频繁，请在 {seconds - (now - int(row[0]))} 秒后再试。")
    await cursor.execute(
        """
        INSERT INTO user_market_cooldown (uid, action_name, last_at) VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE last_at = VALUES(last_at)
        """,
        (uid, action_name, now),
    )


async def _get_tradable_item(cursor, item_name):
    await cursor.execute(
        "SELECT id, name, type, `desc`, access FROM data_item WHERE name = %s LIMIT 1",
        (item_name,),
    )
    row = await cursor.fetchone()
    if not row:
        raise MarketError(f"未找到物品【{item_name}】，请从物品背包复制完整名称。")
    item_id, name, item_type, description, access = row
    text = " ".join(str(value or "") for value in (name, description, access))
    if any(marker in text for marker in BLOCKED_MARKERS):
        raise MarketError("绑定物品、任务道具与轮回专属道具不可在坊市交易。")
    if int(item_type or 0) not in (1, 2, 3, 4, 5, 6, 7):
        raise MarketError("该物品不是可堆叠的通用道具，无法在坊市交易。")
    return {
        "id": int(item_id), "name": str(name), "category": category_for_item(name, item_type),
    }


async def _render_orders(cursor, uid, page, keyword=None, category=None, owner_uid=None):
    conditions = ["status = 'OPEN'"]
    params = []
    if keyword:
        conditions.append("item_name LIKE %s")
        params.append(f"%{keyword}%")
    if category:
        conditions.append("category = %s")
        params.append(category)
    if owner_uid is not None:
        conditions.append("owner_uid = %s")
        params.append(owner_uid)
    where = " AND ".join(conditions)
    await cursor.execute(f"SELECT COUNT(*) FROM user_market_order WHERE {where}", tuple(params))
    total = int((await cursor.fetchone())[0] or 0)
    total_pages = max(1, math.ceil(total / MARKET_PAGE_SIZE))
    page = min(max(1, page), total_pages)
    await cursor.execute(
        f"""
        SELECT id, owner_uid, order_type, item_name, category, remaining_quantity,
               unit_price, reserved_lingshi, TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), expires_at)
        FROM user_market_order WHERE {where}
        ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s
        """,
        tuple(params + [MARKET_PAGE_SIZE, (page - 1) * MARKET_PAGE_SIZE]),
    )
    return await cursor.fetchall(), page, total_pages, total


def _render_order_lines(rows, uid, is_owner_view=False):
    lines = []
    for order_id, _owner_uid, order_type, _item_name, category, quantity, unit_price, _reserved, _left_seconds in rows:
        if order_type == "SELL":
            lines.append(f"> 类别：{category}｜数量：{quantity}｜单价：{unit_price} 灵石")
            if is_owner_view:
                lines.append(_buttons((f"撤摊 {order_id}", "下架")))
            else:
                lines.append(_buttons((f"坊市购买 {order_id} 1", "购买 1 件"), (f"坊市购买 {order_id} ", "购买数量*")))
        else:
            lines.append(f"> 类别：{category}｜数量：{quantity}｜单价：{unit_price} 灵石")
            if is_owner_view:
                lines.append(_buttons((f"撤摊 {order_id}", "下架")))
            else:
                lines.append(_buttons((f"坊市出售 {order_id} 1", "交付 1 件"), (f"坊市出售 {order_id} ", "交付数量*")))
        lines.append("")
    return lines


def _market_error(error):
    return {
        "type": "markdown",
        "content": f"##### 坊市操作未完成\n{error}\n***\n" + _buttons(("坊市", "坊市首页"), ("坊市帮助", "坊市规则")),
    }


@reg_xz_func
async def market_home(uid, qz, param=""):
    text = str(param or "").strip()
    if text.startswith("搜"):
        keyword = text[1:].strip()
        if not keyword:
            return _market_error("请输入要搜索的物品名称，例如：坊市 搜 束灵符。")
        return await market_list(uid, qz, keyword=keyword)
    if text.startswith("分类"):
        category = text[2:].strip()
        if category not in MARKET_CATEGORIES:
            return _market_error("分类仅支持：丹药、材料、功法、神通、法宝、坐骑、消耗品。")
        return await market_list(uid, qz, category=category)
    if text:
        return _market_error("可用指令：坊市 搜 物品名，或 坊市 分类 分类名。")

    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_market_schema(cursor)
            await _expire_orders(cursor)
            await cursor.execute("SELECT COUNT(*) FROM user_market_order WHERE status = 'OPEN' AND order_type = 'SELL'")
            sell_count = int((await cursor.fetchone())[0] or 0)
            await cursor.execute("SELECT COUNT(*) FROM user_market_order WHERE status = 'OPEN' AND order_type = 'BUY'")
            buy_count = int((await cursor.fetchone())[0] or 0)
            await conn.commit()
    lines = [
        "##### 🏮 修真坊市",
        "> 全服道友托管交易：出售物品与收购灵石都会先由系统保管，成交后自动结算。",
        f"> 当前在售 **{sell_count}** 单｜收购 **{buy_count}** 单｜订单有效期 **{MARKET_EXPIRE_HOURS} 小时**",
        "***",
        "**浏览坊市**",
        _buttons(("坊市列表", "坊市列表")),
        "> 查看最新出售单和收购单；点击订单下方蓝字即可购买或交付。",
        "",
        "**搜索道具**",
        _buttons(("坊市 搜 ", "坊市 搜 道具名")),
        "> 按物品名称搜索，例如：坊市 搜 束灵符。",
        "",
        "**按分类浏览**",
        _buttons(("坊市 分类 丹药", "丹药"), ("坊市 分类 材料", "材料"), ("坊市 分类 消耗品", "消耗品")),
        "> 还可输入：坊市 分类 功法 / 神通 / 法宝 / 坐骑。",
        "",
        "**出售道具**",
        _buttons(("坊市上架 ", "坊市上架 物品名 数量 单价")),
        "> 从背包托管物品上架；示例：坊市上架 束灵符 10 500000。",
        "",
        "**发布收购**",
        _buttons(("坊市收购 ", "坊市收购 物品名 单价 数量")),
        "> 预存灵石等待道友交付；示例：坊市收购 束灵符 500000 10。",
        "",
        _buttons(("我的摊位", "我的摊位"), ("坊市交易记录", "坊市交易记录"), ("坊市帮助", "坊市帮助")),
    ]
    return {"type": "markdown", "content": "\n".join(lines)}


@reg_xz_func
async def market_help(uid, qz):
    lines = [
        "##### 🏮 坊市帮助",
        "> 蓝色指令可直接点击发送；带“物品名、数量、单价”的指令可点击后继续补全内容。",
        "***",
        "**一、浏览与查询**",
        _buttons(("坊市列表", "坊市列表"), ("坊市 搜 ", "坊市 搜 物品名")),
        "> 浏览最新订单，或按名称搜索在售与收购物品。",
        _buttons(("坊市 分类 丹药", "分类 丹药"), ("坊市 分类 材料", "分类 材料"), ("坊市 分类 消耗品", "分类 消耗品")),
        "> 可用分类：丹药、材料、功法、神通、法宝、坐骑、消耗品。",
        "",
        "**二、出售与购买**",
        _buttons(("坊市上架 ", "坊市上架 物品名 数量 单价")),
        "> 示例：坊市上架 束灵符 10 500000。上架后物品进入系统托管。",
        _buttons(("坊市购买 ", "坊市购买 摊位号 数量")),
        "> 在出售订单下点击“购买”更方便；出售单不能自行购买。",
        "",
        "**三、收购与交付**",
        _buttons(("坊市收购 ", "坊市收购 物品名 单价 数量")),
        "> 示例：坊市收购 束灵符 500000 10。发布时会预存全部灵石。",
        _buttons(("坊市出售 ", "坊市出售 收购单号 数量")),
        "> 向其他道友的收购单交付背包物品；收购单不能自行交付。",
        "",
        "**四、我的订单与价格参考**",
        _buttons(("我的摊位", "我的摊位"), ("撤摊 ", "撤摊 摊位号"), ("坊市交易记录", "坊市交易记录")),
        "> 撤摊会返还未成交的出售余货或收购余款。",
        _buttons(("坊市底价 ", "坊市底价 物品名")),
        "> 查看近 14 日的成交均价、最低价和最高价。",
        "",
        "**五、交易规则**",
        f"> 订单有效期为 **{MARKET_EXPIRE_HOURS} 小时**；到期自动返还余货或余款。成交从卖家收入扣除 **8%** 手续费（向下取整并销毁）。",
        "> 仅可交易背包中的可堆叠通用物品；绑定、任务、轮回专属道具不可上架。搜索和上架设有短暂冷却，防止刷屏。",
        "***",
        _buttons(("坊市", "返回坊市"), ("坊市列表", "浏览订单")),
    ]
    return {"type": "markdown", "content": "\n".join(lines)}


async def market_list(uid, qz, page=1, keyword=None, category=None):
    try:
        page = parse_page(page)
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await _ensure_market_schema(cursor)
                await _check_cooldown(cursor, uid, "BROWSE", MARKET_SEARCH_COOLDOWN)
                await _expire_orders(cursor)
                rows, page, total_pages, total = await _render_orders(cursor, uid, page, keyword, category)
                await conn.commit()
    except MarketError as error:
        return _market_error(error)

    title = "坊市列表"
    if keyword:
        title += f"｜搜索：{keyword}"
    if category:
        title += f"｜分类：{category}"
    lines = [f"##### 🏮 {title}（第{page}/{total_pages}页）", f"> 当前符合条件：{total} 单", "***"]
    if rows:
        lines.extend(_render_order_lines(rows, uid))
    else:
        lines.append("> 暂无符合条件的挂单。")
    lines.extend(("***", _pagination("坊市列表", page, total_pages), _buttons(("坊市", "坊市首页"), ("坊市帮助", "坊市规则"))))
    return {"type": "markdown", "content": "\n".join(line for line in lines if line)}


@reg_xz_func
async def market_list_command(uid, qz, param=""):
    return await market_list(uid, qz, page=parse_page(param))


@reg_xz_func
async def market_create_sell(uid, qz, param):
    try:
        item_name, quantity, unit_price = parse_item_quantity_price(param)
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await _ensure_market_schema(cursor)
                await _check_cooldown(cursor, uid, "LIST", MARKET_LISTING_COOLDOWN)
                await _expire_orders(cursor)
                item = await _get_tradable_item(cursor, item_name)
                if not await _deduct_item(cursor, uid, item["id"], quantity):
                    raise MarketError(f"背包中【{item['name']}】数量不足，无法上架 {quantity} 件。")
                await cursor.execute(
                    """
                    INSERT INTO user_market_order
                    (owner_uid, order_type, item_id, item_name, category, initial_quantity, remaining_quantity, unit_price, expires_at)
                    VALUES (%s, 'SELL', %s, %s, %s, %s, %s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL 72 HOUR))
                    """,
                    (uid, item["id"], item["name"], item["category"], quantity, quantity, unit_price),
                )
                order_id = cursor.lastrowid
                await conn.commit()
    except MarketError as error:
        return _market_error(error)
    return {
        "type": "markdown",
        "content": "\n".join((
            "##### 坊市上架成功", f"摊位：#{order_id}｜{item['name']} x {quantity}",
            f"单价：{unit_price} 灵石｜有效期：{MARKET_EXPIRE_HOURS} 小时", "***",
            _buttons(("我的摊位", "我的摊位"), ("坊市列表", "浏览坊市")),
        )),
    }


@reg_xz_func
async def market_create_buy(uid, qz, param):
    try:
        # 收购格式与出售不同：物品名 单价 数量。
        item_name, quantity, unit_price = parse_item_quantity_price(param, price_first=True)
        total = quantity * unit_price
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await _ensure_market_schema(cursor)
                await _check_cooldown(cursor, uid, "LIST", MARKET_LISTING_COOLDOWN)
                await _expire_orders(cursor)
                item = await _get_tradable_item(cursor, item_name)
                await cursor.execute(
                    "UPDATE user_zt SET lingshi = lingshi - %s WHERE id = %s AND lingshi >= %s",
                    (total, uid, total),
                )
                if cursor.rowcount <= 0:
                    raise MarketError(f"灵石不足，发布该收购单需要预存 {total} 灵石。")
                await cursor.execute(
                    """
                    INSERT INTO user_market_order
                    (owner_uid, order_type, item_id, item_name, category, initial_quantity, remaining_quantity,
                     unit_price, reserved_lingshi, expires_at)
                    VALUES (%s, 'BUY', %s, %s, %s, %s, %s, %s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL 72 HOUR))
                    """,
                    (uid, item["id"], item["name"], item["category"], quantity, quantity, unit_price, total),
                )
                order_id = cursor.lastrowid
                await conn.commit()
    except MarketError as error:
        return _market_error(error)
    return {
        "type": "markdown",
        "content": "\n".join((
            "##### 坊市收购单已发布", f"收购单：#{order_id}｜{item['name']} x {quantity}",
            f"收购价：{unit_price} 灵石/件｜预存：{total} 灵石｜有效期：{MARKET_EXPIRE_HOURS} 小时", "***",
            _buttons(("我的摊位", "我的摊位"), ("坊市列表", "浏览坊市")),
        )),
    }


async def _record_trade(cursor, order_id, buyer_uid, seller_uid, item_id, item_name, quantity, unit_price):
    gross = int(quantity) * int(unit_price)
    fee = calculate_market_fee(gross)
    income = gross - fee
    await cursor.execute(
        "UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s",
        (income, seller_uid),
    )
    await cursor.execute(
        """
        INSERT INTO user_market_trade
        (order_id, buyer_uid, seller_uid, item_id, item_name, quantity, unit_price, gross_lingshi, fee_lingshi, seller_income)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (order_id, buyer_uid, seller_uid, item_id, item_name, quantity, unit_price, gross, fee, income),
    )
    return gross, fee, income


@reg_xz_func
async def market_buy(uid, qz, param):
    try:
        order_id, quantity = parse_order_quantity(param, "坊市购买")
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await _ensure_market_schema(cursor)
                await _expire_orders(cursor)
                await cursor.execute(
                    """
                    SELECT owner_uid, order_type, item_id, item_name, remaining_quantity, unit_price
                    FROM user_market_order WHERE id = %s AND status = 'OPEN' FOR UPDATE
                    """,
                    (order_id,),
                )
                order = await cursor.fetchone()
                if not order or order[1] != "SELL":
                    raise MarketError("该出售摊位不存在、已结束，或不是出售单。")
                seller_uid, _kind, item_id, item_name, remaining, unit_price = order
                if int(seller_uid) == int(uid):
                    raise MarketError("不能购买自己的出售摊位。")
                if quantity > int(remaining):
                    raise MarketError(f"该摊位仅剩 {remaining} 件。")
                gross = quantity * int(unit_price)
                await cursor.execute(
                    "UPDATE user_zt SET lingshi = lingshi - %s WHERE id = %s AND lingshi >= %s",
                    (gross, uid, gross),
                )
                if cursor.rowcount <= 0:
                    raise MarketError(f"灵石不足，购买需要 {gross} 灵石。")
                await _add_item(cursor, uid, int(item_id), quantity)
                gross, fee, income = await _record_trade(
                    cursor, order_id, uid, int(seller_uid), int(item_id), item_name, quantity, int(unit_price)
                )
                new_remaining = int(remaining) - quantity
                await cursor.execute(
                    """
                    UPDATE user_market_order
                    SET remaining_quantity = %s, status = %s,
                        closed_at = CASE WHEN %s = 'FILLED' THEN UTC_TIMESTAMP() ELSE NULL END
                    WHERE id = %s
                    """,
                    (new_remaining, "FILLED" if new_remaining == 0 else "OPEN", "FILLED" if new_remaining == 0 else "OPEN", order_id),
                )
                await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s", (uid,))
                balance = int((await cursor.fetchone())[0] or 0)
                await conn.commit()
    except MarketError as error:
        return _market_error(error)
    return {
        "type": "markdown",
        "content": "\n".join((
            "##### 坊市购买成功", f"获得：{item_name} x {quantity}",
            f"支付：{gross} 灵石｜卖家实得：{income} 灵石｜手续费销毁：{fee} 灵石", f"剩余灵石：{balance}", "***",
            _buttons(("坊市列表", "继续浏览"), ("物品背包", "查看背包")),
        )),
    }


@reg_xz_func
async def market_sell_to_buy_order(uid, qz, param):
    try:
        order_id, quantity = parse_order_quantity(param, "坊市出售")
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await _ensure_market_schema(cursor)
                await _expire_orders(cursor)
                await cursor.execute(
                    """
                    SELECT owner_uid, order_type, item_id, item_name, remaining_quantity, unit_price, reserved_lingshi
                    FROM user_market_order WHERE id = %s AND status = 'OPEN' FOR UPDATE
                    """,
                    (order_id,),
                )
                order = await cursor.fetchone()
                if not order or order[1] != "BUY":
                    raise MarketError("该收购单不存在、已结束，或不是收购单。")
                buyer_uid, _kind, item_id, item_name, remaining, unit_price, reserved = order
                if int(buyer_uid) == int(uid):
                    raise MarketError("不能向自己的收购单交付物品。")
                if quantity > int(remaining):
                    raise MarketError(f"该收购单仅需 {remaining} 件。")
                if not await _deduct_item(cursor, uid, int(item_id), quantity):
                    raise MarketError(f"背包中【{item_name}】数量不足，无法交付。")
                gross, fee, income = await _record_trade(
                    cursor, order_id, int(buyer_uid), uid, int(item_id), item_name, quantity, int(unit_price)
                )
                new_remaining = int(remaining) - quantity
                new_reserved = int(reserved) - gross
                await cursor.execute(
                    """
                    UPDATE user_market_order
                    SET remaining_quantity = %s, reserved_lingshi = %s, status = %s,
                        closed_at = CASE WHEN %s = 'FILLED' THEN UTC_TIMESTAMP() ELSE NULL END
                    WHERE id = %s
                    """,
                    (new_remaining, new_reserved, "FILLED" if new_remaining == 0 else "OPEN", "FILLED" if new_remaining == 0 else "OPEN", order_id),
                )
                await _add_item(cursor, int(buyer_uid), int(item_id), quantity)
                await cursor.execute("SELECT lingshi FROM user_zt WHERE id = %s", (uid,))
                balance = int((await cursor.fetchone())[0] or 0)
                await conn.commit()
    except MarketError as error:
        return _market_error(error)
    return {
        "type": "markdown",
        "content": "\n".join((
            "##### 收购单交付成功", f"交付：{item_name} x {quantity}",
            f"成交额：{gross} 灵石｜实得：{income} 灵石｜手续费销毁：{fee} 灵石", f"当前灵石：{balance}", "***",
            _buttons(("坊市列表", "继续浏览"), ("我的摊位", "我的摊位")),
        )),
    }


@reg_xz_func
async def market_my_orders(uid, qz, param=""):
    try:
        page = parse_page(param)
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await _ensure_market_schema(cursor)
                await _expire_orders(cursor)
                rows, page, total_pages, total = await _render_orders(cursor, uid, page, owner_uid=uid)
                await conn.commit()
    except MarketError as error:
        return _market_error(error)
    lines = [f"##### 🏮 我的摊位（第{page}/{total_pages}页）", f"> 上架中：{total} 单", "***"]
    if rows:
        lines.extend(_render_order_lines(rows, uid, is_owner_view=True))
        lines.append("> 撤摊会返还出售余货或收购余款；已成交部分不可撤回。")
    else:
        lines.append("> 你当前没有上架中的出售单或收购单。")
    lines.extend(("***", _pagination("我的摊位", page, total_pages), _buttons(("坊市", "坊市首页"), ("坊市上架 ", "上架物品*"))))
    return {"type": "markdown", "content": "\n".join(line for line in lines if line)}


@reg_xz_func
async def market_cancel(uid, qz, param):
    try:
        order_id = int(str(param or "").strip())
        if order_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _market_error("指令格式错误，应为：撤摊 摊位号。")
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await _ensure_market_schema(cursor)
                await _expire_orders(cursor)
                await cursor.execute(
                    """
                    SELECT order_type, item_id, item_name, remaining_quantity, reserved_lingshi
                    FROM user_market_order WHERE id = %s AND owner_uid = %s AND status = 'OPEN' FOR UPDATE
                    """,
                    (order_id, uid),
                )
                order = await cursor.fetchone()
                if not order:
                    raise MarketError("未找到你的进行中摊位；已成交、已撤回或已到期的订单不能再次撤摊。")
                order_type, item_id, item_name, remaining, reserved = order
                if order_type == "SELL":
                    await _add_item(cursor, uid, int(item_id), int(remaining))
                    returned = f"返还物品：{item_name} x {remaining}"
                else:
                    await cursor.execute("UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s", (int(reserved), uid))
                    returned = f"返还预存灵石：{reserved}"
                await cursor.execute(
                    "UPDATE user_market_order SET status = 'CANCELLED', closed_at = UTC_TIMESTAMP() WHERE id = %s",
                    (order_id,),
                )
                await conn.commit()
    except MarketError as error:
        return _market_error(error)
    return {
        "type": "markdown",
        "content": f"##### 撤摊成功\n摊位：#{order_id}\n{returned}\n***\n" + _buttons(("我的摊位", "我的摊位"), ("坊市", "坊市首页")),
    }


@reg_xz_func
async def market_price_floor(uid, qz, param):
    item_name = str(param or "").strip()
    if not item_name:
        return _market_error("指令格式错误，应为：坊市底价 物品名。")
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_market_schema(cursor)
            await _expire_orders(cursor)
            await cursor.execute(
                """
                SELECT COUNT(*), AVG(unit_price), MIN(unit_price), MAX(unit_price)
                FROM user_market_trade
                WHERE item_name = %s AND created_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 14 DAY)
                """,
                (item_name,),
            )
            count, average, minimum, maximum = await cursor.fetchone()
            await conn.commit()
    if not count:
        text = "> 近 14 日暂无成交记录，暂时无法提供价格参考。"
    else:
        text = f"> 近 14 日成交 {count} 笔｜均价：**{int(average)}** 灵石｜最低：{minimum}｜最高：{maximum}"
    return {
        "type": "markdown",
        "content": f"##### 坊市价格看板｜{item_name}\n{text}\n***\n" + _buttons(("坊市列表", "浏览坊市"), ("坊市", "坊市首页")),
    }


@reg_xz_func
async def market_trade_history(uid, qz, param=""):
    page = parse_page(param)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_market_schema(cursor)
            await _expire_orders(cursor)
            await cursor.execute(
                "SELECT COUNT(*) FROM user_market_trade WHERE buyer_uid = %s OR seller_uid = %s", (uid, uid))
            total = int((await cursor.fetchone())[0] or 0)
            total_pages = max(1, math.ceil(total / MARKET_PAGE_SIZE))
            page = min(page, total_pages)
            await cursor.execute(
                """
                SELECT order_id, buyer_uid, seller_uid, item_name, quantity, unit_price, fee_lingshi, seller_income, created_at
                FROM user_market_trade WHERE buyer_uid = %s OR seller_uid = %s
                ORDER BY id DESC LIMIT %s OFFSET %s
                """,
                (uid, uid, MARKET_PAGE_SIZE, (page - 1) * MARKET_PAGE_SIZE),
            )
            rows = await cursor.fetchall()
            await conn.commit()
    lines = [f"##### 📜 坊市交易记录（第{page}/{total_pages}页）", "***"]
    if not rows:
        lines.append("> 尚无买入或卖出记录。")
    for order_id, buyer_uid, seller_uid, item_name, quantity, unit_price, fee, income, created_at in rows:
        if int(buyer_uid) == int(uid):
            lines.append(f"**买入｜#{order_id}｜{item_name} x {quantity}**")
            lines.append(f"> 单价：{unit_price} 灵石｜时间：{created_at}")
        else:
            lines.append(f"**卖出｜#{order_id}｜{item_name} x {quantity}**")
            lines.append(f"> 单价：{unit_price}｜实得：{income}｜手续费：{fee} 灵石｜时间：{created_at}")
    lines.extend(("***", _pagination("坊市交易记录", page, total_pages), _buttons(("坊市", "坊市首页"), ("我的摊位", "我的摊位"))))
    return {"type": "markdown", "content": "\n".join(line for line in lines if line)}


@pd_reg_func
async def show_market_menu(uid, qz):
    """主菜单的坊市子菜单；无需访问数据库。"""
    lines = [
        "##### 🏮 坊市菜单",
        "> 玩家之间的全服托管交易。点击蓝色指令即可直接发送或补全指令。",
        "> 出售余货与收购余款会在 72 小时到期后自动返还；卖家成交收入扣除 8% 手续费。",
        "***",
        "**查看坊市**",
        _buttons(("坊市", "坊市首页"), ("坊市列表", "坊市列表")),
        "> 首页展示当前订单数量；列表可查看最新出售和收购订单。",
        "",
        "**查找道具**",
        _buttons(("坊市 搜 ", "坊市 搜 道具名"), ("坊市 分类 丹药", "分类 丹药"), ("坊市 分类 材料", "分类 材料")),
        "",
        "**发布订单**",
        _buttons(("坊市上架 ", "坊市上架 物品名 数量 单价")),
        "> 出售格式：物品名、数量、单价。",
        _buttons(("坊市收购 ", "坊市收购 物品名 单价 数量")),
        "> 收购格式：物品名、单价、数量；发布时预存灵石。",
        "",
        "**成交操作**",
        _buttons(("坊市购买 ", "坊市购买 摊位号 数量"), ("坊市出售 ", "坊市出售 收购单号 数量")),
        "> 建议在订单列表中直接点击购买或交付；也可手动输入对应订单号。",
        "",
        "**管理与规则**",
        _buttons(("我的摊位", "我的摊位"), ("坊市交易记录", "坊市交易记录"), ("坊市帮助", "坊市帮助")),
        "",
        _buttons(("主菜单", "返回主菜单")),
    ]
    return {"type": "markdown", "content": "\n".join(lines)}
