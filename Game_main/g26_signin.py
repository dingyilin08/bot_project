# -*- coding: utf-8 -*-
"""滚动三十日签到：每日防重领取，七日节点与三十日大奖同事务发放。"""

import json

from func.pd_func import pd_reg_func
from sql.mysql import connect_mysql


CYCLE_DAYS = 30
ITEM_NAMES = {
    1: "悟道天书",
    208: "炼丹加速卡",
    209: "体力药",
    210: "灵草培育液",
}


def _reward(*, lingshi=0, xianyu=0, items=()):
    return {
        "lingshi": int(lingshi),
        "xianyu": int(xianyu),
        "items": tuple(
            {"item_id": int(item_id), "name": ITEM_NAMES[int(item_id)], "amount": int(amount)}
            for item_id, amount in items
        ),
    }


# 三十日基础奖励控制在当前便利商城与日常任务产出的中低档水平；高价值道具放在后段。
DAILY_REWARDS = (
    _reward(lingshi=100),
    _reward(items=((210, 1),)),
    _reward(lingshi=120),
    _reward(items=((208, 1),)),
    _reward(xianyu=50),
    _reward(items=((209, 1),)),
    _reward(lingshi=180),
    _reward(lingshi=120),
    _reward(items=((210, 1),)),
    _reward(xianyu=50),
    _reward(items=((208, 1),)),
    _reward(lingshi=160),
    _reward(items=((209, 1),)),
    _reward(lingshi=200),
    _reward(xianyu=50),
    _reward(items=((210, 2),)),
    _reward(lingshi=180),
    _reward(items=((208, 1),)),
    _reward(items=((209, 1),)),
    _reward(xianyu=50),
    _reward(lingshi=220),
    _reward(items=((210, 2),)),
    _reward(lingshi=200),
    _reward(items=((208, 2),)),
    _reward(xianyu=50),
    _reward(items=((209, 2),)),
    _reward(lingshi=250),
    _reward(lingshi=300),
    _reward(items=((1, 1),)),
    _reward(xianyu=50),
)


MILESTONE_REWARDS = {
    7: {
        "kind": "WEEKLY",
        "title": "七日累签礼·初境",
        "reward": _reward(lingshi=300, xianyu=100, items=((210, 1),)),
    },
    14: {
        "kind": "WEEKLY",
        "title": "七日累签礼·凝华",
        "reward": _reward(lingshi=400, xianyu=100, items=((208, 1),)),
    },
    21: {
        "kind": "WEEKLY",
        "title": "七日累签礼·破关",
        "reward": _reward(lingshi=500, xianyu=100, items=((209, 1),)),
    },
    28: {
        "kind": "WEEKLY",
        "title": "七日累签礼·悟道",
        "reward": _reward(lingshi=600, xianyu=100, items=((1, 1),)),
    },
    30: {
        "kind": "MONTHLY",
        "title": "三十日圆满礼",
        "reward": _reward(
            lingshi=1200,
            xianyu=800,
            items=((1, 2), (208, 2), (209, 2), (210, 2)),
        ),
    },
}


def reward_for_day(day):
    """返回指定周期日的基础奖励。"""
    day = int(day)
    if day < 1 or day > CYCLE_DAYS:
        raise ValueError("签到周期日必须在1到30之间。")
    return DAILY_REWARDS[day - 1]


def milestone_for_day(day):
    """返回指定周期日的七日或三十日里程碑。"""
    day = int(day)
    if day < 1 or day > CYCLE_DAYS:
        raise ValueError("签到周期日必须在1到30之间。")
    return MILESTONE_REWARDS.get(day)


def next_cycle_position(cycle_no, cycle_day):
    """三十日圆满后，下一次签到进入新的滚动周期。"""
    cycle_no = int(cycle_no)
    cycle_day = int(cycle_day)
    if cycle_no < 1 or cycle_day < 0 or cycle_day > CYCLE_DAYS:
        raise ValueError("签到周期状态无效。")
    if cycle_day == CYCLE_DAYS:
        return cycle_no + 1, 1
    return cycle_no, cycle_day + 1


def combine_rewards(*rewards):
    """合并基础与里程碑奖励，便于事务内一次发放。"""
    lingshi = 0
    xianyu = 0
    items = {}
    for reward in rewards:
        if not reward:
            continue
        lingshi += int(reward.get("lingshi", 0))
        xianyu += int(reward.get("xianyu", 0))
        for item in reward.get("items", ()):
            item_id = int(item["item_id"])
            items[item_id] = items.get(item_id, 0) + int(item["amount"])
    return _reward(
        lingshi=lingshi,
        xianyu=xianyu,
        items=tuple((item_id, amount) for item_id, amount in sorted(items.items())),
    )


def cycle_reward_total():
    """公开完整周期投放总量，供测试和后续平衡调整使用。"""
    rewards = list(DAILY_REWARDS)
    rewards.extend(entry["reward"] for entry in MILESTONE_REWARDS.values())
    return combine_rewards(*rewards)


def reward_text(reward):
    parts = []
    if int(reward.get("lingshi", 0)):
        parts.append(f"灵石 ×{int(reward['lingshi'])}")
    if int(reward.get("xianyu", 0)):
        parts.append(f"仙玉 ×{int(reward['xianyu'])}")
    parts.extend(f"{item['name']} ×{int(item['amount'])}" for item in reward.get("items", ()))
    return "、".join(parts) or "无"


def _reward_json(reward):
    return json.dumps(
        {
            "lingshi": int(reward.get("lingshi", 0)),
            "xianyu": int(reward.get("xianyu", 0)),
            "items": [dict(item) for item in reward.get("items", ())],
        },
        ensure_ascii=False,
    )


async def ensure_signin_schema(cursor):
    """运行时兼容建表；正式部署同时提供独立 SQL 迁移。"""
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_signin_progress (
            uid INT NOT NULL,
            cycle_no INT NOT NULL DEFAULT 1,
            cycle_day TINYINT NOT NULL DEFAULT 0,
            total_signins INT NOT NULL DEFAULT 0,
            last_signin_date DATE NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (uid),
            KEY idx_signin_last_date (last_signin_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_三十日签到进度'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_signin_log (
            id BIGINT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            cycle_no INT NOT NULL,
            cycle_day TINYINT NOT NULL,
            sign_date DATE NOT NULL,
            daily_reward_json JSON NOT NULL,
            milestone_reward_json JSON NULL,
            total_reward_json JSON NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_signin_date (uid, sign_date),
            UNIQUE KEY uk_signin_cycle_day (uid, cycle_no, cycle_day),
            KEY idx_signin_log_uid_time (uid, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_签到领奖流水'
        """
    )


async def _ensure_progress(cursor, uid):
    await cursor.execute(
        "INSERT IGNORE INTO user_signin_progress (uid) VALUES (%s)",
        (uid,),
    )


async def _grant_reward(cursor, uid, reward):
    await cursor.execute(
        "UPDATE user_zt SET lingshi=lingshi+%s,xianyu=xianyu+%s WHERE id=%s",
        (int(reward["lingshi"]), int(reward["xianyu"]), uid),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("玩家资产不存在，签到奖励未发放。")
    for item in reward["items"]:
        await cursor.execute(
            """
            INSERT INTO user_item (uid,item_id,item_num) VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE item_num=item_num+VALUES(item_num)
            """,
            (uid, int(item["item_id"]), int(item["amount"])),
        )


def _button(command, label):
    return f"<qqbot-cmd-input text='{command}' show='{label}' />"


@pd_reg_func
async def signin_claim(uid, qz):
    """领取今日签到，资产、进度与审计流水在同一事务内提交。"""
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_signin_schema(cursor)
                await cursor.execute("SELECT id FROM user_zt WHERE id=%s FOR UPDATE", (uid,))
                if not await cursor.fetchone():
                    await conn.rollback()
                    return {"type": "markdown", "content": "请先注册游戏。"}
                await _ensure_progress(cursor, uid)
                await cursor.execute(
                    """
                    SELECT cycle_no,cycle_day,total_signins,last_signin_date,CURDATE()
                    FROM user_signin_progress WHERE uid=%s FOR UPDATE
                    """,
                    (uid,),
                )
                cycle_no, cycle_day, total_signins, last_date, today = await cursor.fetchone()
                if last_date == today:
                    await conn.rollback()
                    return {
                        "type": "markdown",
                        "content": "\n".join((
                            "##### ☀️ 今日已经签到",
                            "",
                            f"> 当前为第 **{int(cycle_no)}期 · {int(cycle_day)}/30日**，奖励已入账。",
                            "",
                            f"{_button('签到记录', '查看签到记录')} | {_button('签到奖励', '查看奖励总览')}",
                        )),
                    }

                new_cycle_no, new_cycle_day = next_cycle_position(cycle_no, cycle_day)
                daily_reward = reward_for_day(new_cycle_day)
                milestone = milestone_for_day(new_cycle_day)
                milestone_reward = milestone["reward"] if milestone else None
                total_reward = combine_rewards(daily_reward, milestone_reward)

                await cursor.execute(
                    """
                    INSERT INTO user_signin_log
                        (uid,cycle_no,cycle_day,sign_date,daily_reward_json,
                         milestone_reward_json,total_reward_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        uid,
                        new_cycle_no,
                        new_cycle_day,
                        today,
                        _reward_json(daily_reward),
                        _reward_json(milestone_reward) if milestone_reward else None,
                        _reward_json(total_reward),
                    ),
                )
                await _grant_reward(cursor, uid, total_reward)
                await cursor.execute(
                    """
                    UPDATE user_signin_progress
                    SET cycle_no=%s,cycle_day=%s,total_signins=total_signins+1,last_signin_date=%s
                    WHERE uid=%s
                    """,
                    (new_cycle_no, new_cycle_day, today, uid),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("签到进度更新失败，奖励未发放。")
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    lines = [
        "##### ☀️ 签到成功",
        "",
        f"> 第 **{new_cycle_no}期 · {new_cycle_day}/30日**｜总签到 **{int(total_signins) + 1}次**",
        f"今日奖励：**{reward_text(daily_reward)}**",
    ]
    if milestone:
        lines.extend(("", f"##### 🎊 {milestone['title']}", f"> 额外获得：**{reward_text(milestone_reward)}**"))
    if new_cycle_day == CYCLE_DAYS:
        lines.extend(("", "> 三十日道途圆满！下一次签到将开启全新一期。"))
    else:
        _, next_day = next_cycle_position(new_cycle_no, new_cycle_day)
        lines.extend(("", f"> 下一签到：第 {next_day} 日｜{reward_text(reward_for_day(next_day))}"))
    lines.extend(("", f"{_button('签到记录', '签到记录')} | {_button('签到奖励', '奖励总览')} | {_button('主菜单', '主菜单')}"))
    return {"type": "markdown", "content": "\n".join(lines)}


@pd_reg_func
async def signin_home(uid, qz):
    """查看当前签到周期、今日状态和近期流水。"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_signin_schema(cursor)
            await _ensure_progress(cursor, uid)
            await cursor.execute(
                """
                SELECT cycle_no,cycle_day,total_signins,last_signin_date,CURDATE()
                FROM user_signin_progress WHERE uid=%s
                """,
                (uid,),
            )
            cycle_no, cycle_day, total_signins, last_date, today = await cursor.fetchone()
            await cursor.execute(
                """
                SELECT sign_date,cycle_no,cycle_day FROM user_signin_log
                WHERE uid=%s ORDER BY id DESC LIMIT 5
                """,
                (uid,),
            )
            recent = await cursor.fetchall()
            await conn.commit()

    claimed_today = last_date == today
    if claimed_today:
        next_cycle_no, next_day = next_cycle_position(cycle_no, cycle_day)
    else:
        next_cycle_no, next_day = next_cycle_position(cycle_no, cycle_day)
    next_milestone_day = next(
        (day for day in sorted(MILESTONE_REWARDS) if day >= next_day),
        CYCLE_DAYS,
    )
    milestone = MILESTONE_REWARDS[next_milestone_day]
    lines = [
        "##### 📅 三十日签到",
        "",
        f"> 当前进度：第 **{int(cycle_no)}期 · {int(cycle_day)}/30日**｜累计 **{int(total_signins)}次**",
        f"> 今日状态：{'✅ 已签到' if claimed_today else '🎁 可签到'}",
        "> 每个自然日限领一次；漏签不清零、不补领，完成第30日后开启新一期。",
        "",
        f"**下一签到：** 第 {next_cycle_no}期 · 第{next_day}日",
        f"> 基础奖励：{reward_text(reward_for_day(next_day))}",
        f"**下一里程碑：** 第{next_milestone_day}日 · {milestone['title']}",
        f"> 额外奖励：{reward_text(milestone['reward'])}",
    ]
    if recent:
        lines.extend(("", "**近期签到**"))
        lines.extend(f"> {row[0]}｜第{int(row[1])}期·第{int(row[2])}日" for row in recent)
    lines.extend(("", f"{_button('签到', '立即签到')} | {_button('签到奖励', '奖励总览')} | {_button('活动菜单', '活动菜单')}"))
    return {"type": "markdown", "content": "\n".join(lines)}


@pd_reg_func
async def signin_reward_preview(uid, qz):
    """展示完整三十日奖励，避免稀有道具投放成为黑箱。"""
    lines = [
        "##### 🎁 三十日签到奖励",
        "",
        "> 每日奖励按签到次数推进；第7/14/21/28日追加七日礼，第30日追加圆满礼。",
        "",
    ]
    for day in range(1, CYCLE_DAYS + 1):
        milestone = milestone_for_day(day)
        suffix = f" ＋ {milestone['title']}" if milestone else ""
        lines.append(f"> **第{day}日**｜{reward_text(reward_for_day(day))}{suffix}")
    lines.extend(("", "**里程碑额外奖励**"))
    for day, milestone in MILESTONE_REWARDS.items():
        lines.append(f"> 第{day}日·{milestone['title']}：{reward_text(milestone['reward'])}")
    total = cycle_reward_total()
    lines.extend((
        "",
        f"> 三十日总计：**{reward_text(total)}**",
        "",
        f"{_button('签到', '立即签到')} | {_button('签到记录', '签到记录')} | {_button('活动菜单', '活动菜单')}",
    ))
    return {"type": "markdown", "content": "\n".join(lines)}
