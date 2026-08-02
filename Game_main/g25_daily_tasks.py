# -*- coding: utf-8 -*-
"""日常任务：由真实玩法完成事件驱动，奖励领取全程在同一事务内完成。"""

import json

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


DAILY_XIANYU_PER_TASK = 60
DAILY_ALL_XIANYU = 300
DAILY_BONUS_CODE = "DAILY_ALL_REWARD"

# code, title, description, action command
DAILY_TASKS = (
    ("CULTIVATION", "静心参悟", "成功开始一次参悟。", "参悟菜单"),
    ("DUNGEON", "斩妖历练", "在副本战斗中获胜一次。", "副本菜单"),
    ("SHOP", "补给整备", "在灵石商城成功购买一次道具。", "商城"),
    ("FARM", "灵田耕作", "成功播种一格药田。", "药园菜单"),
    ("ALCHEMY", "丹炉开火", "成功开始炼制一炉丹药。", "炼丹菜单"),
)
TASK_BY_CODE = {task[0]: task for task in DAILY_TASKS}


def task_by_key(value):
    """支持用编号或任务代码领取日常奖励。"""
    text = str(value or "").strip().upper()
    if text.isdigit() and 1 <= int(text) <= len(DAILY_TASKS):
        return DAILY_TASKS[int(text) - 1]
    return TASK_BY_CODE.get(text)


async def ensure_daily_task_schema(cursor):
    """保留运行时建表兼容，正式部署同时提供独立迁移文件。"""
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_daily_task_progress (
            id BIGINT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            task_date DATE NOT NULL,
            task_code VARCHAR(32) NOT NULL,
            completed_at DATETIME NULL,
            claimed_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_daily_task (uid, task_date, task_code),
            KEY idx_daily_task_uid_date (uid, task_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_日常任务进度'
        """
    )
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_daily_task_bonus (
            id BIGINT NOT NULL AUTO_INCREMENT,
            uid INT NOT NULL,
            task_date DATE NOT NULL,
            bonus_code VARCHAR(32) NOT NULL,
            reward_json JSON NOT NULL,
            claimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_daily_task_bonus (uid, task_date, bonus_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_日常任务全勤奖励'
        """
    )


async def record_daily_event(uid, code):
    """在原玩法成功提交后调用；同任务每日只完成一次，异常不影响原玩法。"""
    if code not in TASK_BY_CODE:
        return False
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await ensure_daily_task_schema(cursor)
                await cursor.execute(
                    """
                    INSERT INTO user_daily_task_progress (uid, task_date, task_code, completed_at)
                    VALUES (%s, CURDATE(), %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
                    """,
                    (uid, code),
                )
            await conn.commit()
        return True
    except Exception:
        return False


async def _ensure_today_tasks(uid, cursor):
    for code, *_ in DAILY_TASKS:
        await cursor.execute(
            """
            INSERT IGNORE INTO user_daily_task_progress (uid, task_date, task_code)
            VALUES (%s, CURDATE(), %s)
            """,
            (uid, code),
        )


async def _daily_progress(uid, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        """
        SELECT task_code, completed_at, claimed_at
        FROM user_daily_task_progress
        WHERE uid=%s AND task_date=CURDATE()
        """ + suffix,
        (uid,),
    )
    return {row[0]: (row[1], row[2]) for row in await cursor.fetchall()}


async def _bonus_claimed(uid, cursor, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    await cursor.execute(
        """
        SELECT id FROM user_daily_task_bonus
        WHERE uid=%s AND task_date=CURDATE() AND bonus_code=%s
        """ + suffix,
        (uid, DAILY_BONUS_CODE),
    )
    return bool(await cursor.fetchone())


def _button(command, label):
    return f"<qqbot-cmd-input text='{command}' show='{label}' />"


@reg_xz_func
async def daily_task_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_daily_task_schema(cursor)
            await _ensure_today_tasks(uid, cursor)
            progress = await _daily_progress(uid, cursor)
            bonus_claimed = await _bonus_claimed(uid, cursor)
            await conn.commit()

    completed = sum(1 for code, *_ in DAILY_TASKS if progress.get(code, (None, None))[0])
    unclaimed = sum(1 for code, *_ in DAILY_TASKS if progress.get(code, (None, None))[0] and not progress.get(code, (None, None))[1])
    lines = ["##### 📅 日常任务", "", f"> 今日进度：**{completed}/{len(DAILY_TASKS)}**｜每项奖励 **{DAILY_XIANYU_PER_TASK}仙玉**｜全部完成共 **{DAILY_ALL_XIANYU}仙玉**。", "> 完成玩法后会自动计入；奖励需手动领取，次日零点刷新。", ""]
    for index, (code, title, description, command) in enumerate(DAILY_TASKS, 1):
        done_at, claimed_at = progress.get(code, (None, None))
        state = "✅ 已领取" if claimed_at else ("🎁 可领取" if done_at else "⬜ 未完成")
        lines.append(f"**{index}. {title}**　{state}")
        lines.append(f"> {description}｜奖励：**{DAILY_XIANYU_PER_TASK}仙玉**")
        if done_at and not claimed_at:
            lines.append(f"> {_button(f'日常领取 {index}', '领取60仙玉')}")
        elif not done_at:
            lines.append(f"> {_button(command, '前往完成')}")

    lines.extend(["", "***"])
    if completed == len(DAILY_TASKS):
        if bonus_claimed:
            lines.append("> ✅ 今日全勤礼包已领取：药材、种子、装备、丹药已发放。")
        else:
            lines.append("> 🎊 五项任务已完成！可一键领取未领仙玉，并领取药材、种子、装备、丹药全勤礼包。")
            lines.append(_button("日常领取 全部", f"领取全勤礼包（{unclaimed * DAILY_XIANYU_PER_TASK}仙玉）"))
    else:
        lines.append(f"> 完成全部任务后可领取药材、种子、装备、丹药全勤礼包（还差 {len(DAILY_TASKS) - completed} 项）。")
    lines.append("")
    lines.append(f"{_button('主菜单', '主菜单')} | {_button('物品背包', '物品背包')} | {_button('仙玉祈愿', '仙玉祈愿')}")
    return {"type": "markdown", "content": "\n".join(lines)}


@reg_xz_func
async def daily_task_claim(uid, qz, task_key):
    text = str(task_key or "").strip().upper()
    if text in ("全部", "ALL"):
        return await _claim_daily_all(uid)
    task = task_by_key(task_key)
    if not task:
        return {"type": "markdown", "content": "任务编号错误，请发送“日常任务”查看可领取奖励。"}
    code, title, _, _ = task
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_daily_task_schema(cursor)
                await cursor.execute("SELECT id FROM user_zt WHERE id=%s FOR UPDATE", (uid,))
                if not await cursor.fetchone():
                    await conn.rollback()
                    return {"type": "markdown", "content": "请先注册游戏。"}
                await _ensure_today_tasks(uid, cursor)
                progress = await _daily_progress(uid, cursor, lock=True)
                completed_at, claimed_at = progress.get(code, (None, None))
                if not completed_at:
                    await conn.rollback()
                    return {"type": "markdown", "content": f"「{title}」尚未完成，请先发送“日常任务”查看目标。"}
                if claimed_at:
                    await conn.rollback()
                    return {"type": "markdown", "content": f"「{title}」奖励已领取，请继续完成其他日常任务。"}
                await cursor.execute(
                    """
                    UPDATE user_daily_task_progress SET claimed_at=CURRENT_TIMESTAMP
                    WHERE uid=%s AND task_date=CURDATE() AND task_code=%s AND claimed_at IS NULL
                    """,
                    (uid, code),
                )
                if cursor.rowcount != 1:
                    await conn.rollback()
                    return {"type": "markdown", "content": "奖励状态已更新，请重新查看日常任务。"}
                await cursor.execute("UPDATE user_zt SET xianyu=xianyu+%s WHERE id=%s", (DAILY_XIANYU_PER_TASK, uid))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return {"type": "markdown", "content": f"##### 🎁 日常奖励\n\n完成：**{title}**\n获得：**{DAILY_XIANYU_PER_TASK}仙玉**\n\n{_button('日常任务', '继续日常任务')} | {_button('仙玉祈愿', '仙玉祈愿')}"}


async def _pick_daily_bonus(cursor, uid):
    """按当前出战角色所在世界选择一组可用奖励；无出战角色时安全回退全表首项。"""
    await cursor.execute("SELECT world FROM user_role WHERE uid=%s AND is_chuzhan=1 LIMIT 1", (uid,))
    role = await cursor.fetchone()
    world = role[0] if role else None

    async def pick(sql, fallback_sql):
        if world:
            await cursor.execute(sql, (world,))
            row = await cursor.fetchone()
            if row:
                return row
        await cursor.execute(fallback_sql)
        return await cursor.fetchone()

    herb = await pick(
        "SELECT item_id,name FROM data_herb WHERE world=%s AND item_id IS NOT NULL ORDER BY tier,id LIMIT 1",
        "SELECT item_id,name FROM data_herb WHERE item_id IS NOT NULL ORDER BY tier,id LIMIT 1",
    )
    seed = await pick(
        "SELECT id,name FROM data_seed WHERE world=%s ORDER BY tier,id LIMIT 1",
        "SELECT id,name FROM data_seed ORDER BY tier,id LIMIT 1",
    )
    pill = await pick(
        "SELECT item_id,name FROM data_pill WHERE world=%s AND item_id IS NOT NULL ORDER BY category,id LIMIT 1",
        "SELECT item_id,name FROM data_pill WHERE item_id IS NOT NULL ORDER BY category,id LIMIT 1",
    )
    equip = await pick(
        "SELECT id,name FROM data_equip WHERE world=%s ORDER BY min_level,id LIMIT 1",
        "SELECT id,name FROM data_equip ORDER BY min_level,id LIMIT 1",
    )
    if not all((herb, seed, pill, equip)):
        raise RuntimeError("日常全勤奖励配置不完整，请先导入药园与装备基础数据。")
    return {
        "herb": {"item_id": int(herb[0]), "name": herb[1], "amount": 3},
        "seed": {"seed_id": int(seed[0]), "name": seed[1], "amount": 2},
        "pill": {"item_id": int(pill[0]), "name": pill[1], "amount": 1},
        "equipment": {"equip_id": int(equip[0]), "name": equip[1], "quality": "良品"},
    }


async def _grant_daily_bonus(cursor, uid, reward):
    for item in (reward["herb"], reward["pill"]):
        await cursor.execute(
            """
            INSERT INTO user_item (uid,item_id,item_num) VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE item_num=item_num+VALUES(item_num)
            """,
            (uid, item["item_id"], item["amount"]),
        )
    seed = reward["seed"]
    await cursor.execute(
        """
        INSERT INTO user_seed_bag (uid,zz_id,zz_num) VALUES (%s,%s,%s)
        ON DUPLICATE KEY UPDATE zz_num=zz_num+VALUES(zz_num)
        """,
        (uid, seed["seed_id"], seed["amount"]),
    )
    equip = reward["equipment"]
    await cursor.execute(
        """
        INSERT INTO user_equip (uid,equip_id,level,quality,is_equipped)
        VALUES (%s,%s,0,%s,0)
        """,
        (uid, equip["equip_id"], equip["quality"]),
    )


async def _claim_daily_all(uid):
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await ensure_daily_task_schema(cursor)
                await cursor.execute("SELECT id FROM user_zt WHERE id=%s FOR UPDATE", (uid,))
                if not await cursor.fetchone():
                    await conn.rollback()
                    return {"type": "markdown", "content": "请先注册游戏。"}
                await _ensure_today_tasks(uid, cursor)
                progress = await _daily_progress(uid, cursor, lock=True)
                completed = [code for code, *_ in DAILY_TASKS if progress.get(code, (None, None))[0]]
                if len(completed) != len(DAILY_TASKS):
                    await conn.rollback()
                    return {"type": "markdown", "content": f"尚未完成全部日常任务（{len(completed)}/{len(DAILY_TASKS)}），暂不能领取全勤礼包。"}
                if await _bonus_claimed(uid, cursor, lock=True):
                    await conn.rollback()
                    return {"type": "markdown", "content": "今日全勤礼包已经领取，请明日再来。"}

                unclaimed = [code for code in completed if not progress[code][1]]
                xianyu = DAILY_XIANYU_PER_TASK * len(unclaimed)
                reward = await _pick_daily_bonus(cursor, uid)
                reward_json = json.dumps({"xianyu": xianyu, **reward}, ensure_ascii=False)
                await cursor.execute(
                    """
                    INSERT INTO user_daily_task_bonus (uid,task_date,bonus_code,reward_json)
                    VALUES (%s,CURDATE(),%s,%s)
                    """,
                    (uid, DAILY_BONUS_CODE, reward_json),
                )
                if unclaimed:
                    await cursor.execute(
                        """
                        UPDATE user_daily_task_progress SET claimed_at=CURRENT_TIMESTAMP
                        WHERE uid=%s AND task_date=CURDATE() AND claimed_at IS NULL
                        """,
                        (uid,),
                    )
                    await cursor.execute("UPDATE user_zt SET xianyu=xianyu+%s WHERE id=%s", (xianyu, uid))
                await _grant_daily_bonus(cursor, uid, reward)
            await conn.commit()
        except RuntimeError as error:
            await conn.rollback()
            return {"type": "markdown", "content": f"全勤礼包暂不可发放：{error}"}
        except Exception:
            await conn.rollback()
            raise
    lines = ["##### 🎊 日常全勤礼包", "", f"仙玉：**+{xianyu}**（五项日常合计 {DAILY_ALL_XIANYU} 仙玉）", f"药材：**{reward['herb']['name']} ×{reward['herb']['amount']}**", f"种子：**{reward['seed']['name']} ×{reward['seed']['amount']}**", f"丹药：**{reward['pill']['name']} ×{reward['pill']['amount']}**", f"装备：**{reward['equipment']['name']}（{reward['equipment']['quality']}）**", "", f"{_button('物品背包', '查看物品背包')} | {_button('装备背包', '查看装备背包')} | {_button('日常任务', '返回日常任务')}"]
    return {"type": "markdown", "content": "\n".join(lines)}
