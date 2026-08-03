# -*- coding: utf-8 -*-
"""八周赛季：可追赶进度、可佩戴外观与有边界的临时 PVE 天象。"""

from datetime import date, datetime, time, timedelta

import aiomysql

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql


EVENT_XP = {"DUNGEON": 8, "SECT": 5, "WORLD_BOSS": 10}

# threshold, display name, cosmetic type, stable suffix
REWARDS = (
    (20, "流云纹头像框", "FRAME", "cloud_frame"),
    (60, "诸天行者", "TITLE", "heaven_walker"),
    (120, "五行流光", "AURA", "five_elements_aura"),
)

COSMETIC_TYPE_NAMES = {"FRAME": "头像框", "TITLE": "称号", "AURA": "外观特效"}

# 只有这里列出的机器码可以进入战斗；数据库里的自由文本不能直接变成数值。
SEASON_EFFECT_SPECS = {
    "PVE_ATTACK_UP": {
        "stat": "attack_bp",
        "max_bp": 500,
        "default_name": "五行轮转·锐金",
        "default_text": "本赛季所有 PVE 开战时攻击提高 3%；世界 Boss 中折算为贡献效率，赛季结束后失效。",
    },
    "PVE_DEFENSE_UP": {
        "stat": "defense_bp",
        "max_bp": 500,
        "default_name": "五行轮转·厚土",
        "default_text": "本赛季所有 PVE 开战时防御提高 3%；世界 Boss 中折算为贡献效率，赛季结束后失效。",
    },
    "PVE_SPEED_UP": {
        "stat": "speed_bp",
        "max_bp": 500,
        "default_name": "五行轮转·疾风",
        "default_text": "本赛季所有 PVE 开战时速度提高 3%；世界 Boss 中折算为贡献效率，赛季结束后失效。",
    },
}

DEFAULT_RULE_VALUE_BP = 300
SEASON_RULE_VERSION = 1
SEASON_EPOCH = date(2026, 1, 1)
DEFAULT_RULE_ROTATION = ("PVE_ATTACK_UP", "PVE_DEFENSE_UP", "PVE_SPEED_UP")


def season_period(today=None):
    """返回稳定且连续的 56 天区间；跨年时沿用开始年份的赛季编号。"""
    today = today or date.today()
    if isinstance(today, datetime):
        today = today.date()
    block_index = (today - SEASON_EPOCH).days // 56
    starts_on = SEASON_EPOCH + timedelta(days=block_index * 56)
    ends_on = starts_on + timedelta(days=55)
    first_block_of_start_year = -(
        -((date(starts_on.year, 1, 1) - SEASON_EPOCH).days) // 56
    )
    index_in_year = block_index - first_block_of_start_year + 1
    return {
        "key": f"{starts_on.year}-S{index_in_year}",
        "index": index_in_year,
        "starts_on": starts_on,
        "ends_on": ends_on,
    }


def season_key(today=None):
    return season_period(today)["key"]


def season_days_left(today=None):
    today = today or date.today()
    if isinstance(today, datetime):
        today = today.date()
    return max(0, (season_period(today)["ends_on"] - today).days)


def reward_for_xp(xp):
    return [item for item in REWARDS if int(xp) >= item[0]]


def season_cosmetic_code(key, suffix):
    # 仅使用全局指令解析器会保留的字符，确保按钮回填后代码不会被改写。
    return f"{key}-{str(suffix).replace('_', '-')}".upper()


def cosmetic_catalog(key):
    return tuple(
        {
            "threshold": threshold,
            "name": name,
            "cosmetic_type": cosmetic_type,
            "code": season_cosmetic_code(key, suffix),
            "description": f"{key} 赛季限定{COSMETIC_TYPE_NAMES[cosmetic_type]}，仅改变展示。",
        }
        for threshold, name, cosmetic_type, suffix in REWARDS
    )


def cosmetic_identity(equipped):
    """生成角色页的纯展示标识；不会返回或修改任何战斗属性。"""
    equipped = equipped or {}
    title = equipped.get("TITLE", {}).get("name")
    frame = equipped.get("FRAME", {}).get("name")
    aura = equipped.get("AURA", {}).get("name")
    prefix = f"「{title}」" if title else ""
    prefix += f"〔{frame}〕" if frame else ""
    return prefix, aura


def season_effect_snapshot(rule_code, value_bp, **metadata):
    """把数据库规则转成有白名单与硬上限的战斗快照。"""
    snapshot = {
        "rule_version": SEASON_RULE_VERSION,
        "rule_code": str(rule_code or ""),
        "value_bp": 0,
        "attack_bp": 0,
        "defense_bp": 0,
        "speed_bp": 0,
        "active": False,
    }
    spec = SEASON_EFFECT_SPECS.get(snapshot["rule_code"])
    if not spec:
        snapshot.update(metadata)
        return snapshot
    try:
        bounded = min(max(int(value_bp), 0), int(spec["max_bp"]))
    except (TypeError, ValueError):
        bounded = 0
    snapshot["value_bp"] = bounded
    snapshot[spec["stat"]] = bounded
    snapshot["active"] = bounded > 0
    snapshot.update(metadata)
    return snapshot


def default_season_rule(key):
    """按赛季序号稳定轮转天象，重启或补迁移都不会改变结果。"""
    try:
        ordinal = max(1, int(str(key).rsplit("S", 1)[1]))
    except (IndexError, TypeError, ValueError):
        ordinal = 1
    code = DEFAULT_RULE_ROTATION[(ordinal - 1) % len(DEFAULT_RULE_ROTATION)]
    spec = SEASON_EFFECT_SPECS[code]
    return code, spec["default_name"], spec["default_text"], DEFAULT_RULE_VALUE_BP


async def _ensure_default_rule(cursor, season):
    rule_code, rule_name, rule_text, rule_value_bp = default_season_rule(season[1])
    await cursor.execute(
        """
        INSERT INTO season_effect_rule
            (season_id, rule_code, rule_name, rule_text, effect_value_bp, rule_version, enabled)
        SELECT %s, %s, %s, %s, %s, %s, 1
        WHERE NOT EXISTS (
            SELECT 1 FROM season_effect_rule WHERE season_id = %s AND enabled = 1
        )
        ON DUPLICATE KEY UPDATE rule_code = VALUES(rule_code)
        """,
        (
            season[0],
            rule_code,
            rule_name,
            rule_text,
            rule_value_bp,
            SEASON_RULE_VERSION,
            season[0],
        ),
    )


async def _ensure_cosmetic_catalog(cursor, season):
    for item in cosmetic_catalog(season[1]):
        await cursor.execute(
            """
            INSERT INTO cosmetic_catalog
                (cosmetic_code, season_id, reward_tier, cosmetic_type, cosmetic_name, description)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                cosmetic_name = VALUES(cosmetic_name), description = VALUES(description)
            """,
            (
                item["code"],
                season[0],
                item["threshold"],
                item["cosmetic_type"],
                item["name"],
                item["description"],
            ),
        )


async def _current_season(cursor, today=None):
    period = season_period(today)
    await cursor.execute(
        """
        INSERT INTO season (season_key, name, starts_on, ends_on)
        VALUES (%s, '五行天象', %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name), starts_on = VALUES(starts_on), ends_on = VALUES(ends_on)
        """,
        (period["key"], period["starts_on"], period["ends_on"]),
    )
    await cursor.execute(
        "SELECT id, season_key, name, ends_on, starts_on FROM season WHERE season_key = %s",
        (period["key"],),
    )
    season = await cursor.fetchone()
    await _ensure_default_rule(cursor, season)
    await _ensure_cosmetic_catalog(cursor, season)
    return season


async def _load_active_effect(cursor, season, today=None):
    if today is None:
        moment = datetime.now()
    elif isinstance(today, datetime):
        moment = today
    else:
        moment = datetime.combine(today, time.min)
    await cursor.execute(
        """
        SELECT rule_code, effect_value_bp, rule_name, rule_text, rule_version
        FROM season_effect_rule
        WHERE season_id = %s AND enabled = 1
          AND (starts_at IS NULL OR starts_at <= %s)
          AND (ends_at IS NULL OR ends_at > %s)
        ORDER BY id LIMIT 1
        """,
        (season[0], moment, moment),
    )
    row = await cursor.fetchone()
    if not row:
        return season_effect_snapshot("", 0, season_id=season[0], season_key=season[1])
    code, value_bp, name, text, stored_version = row
    snapshot = season_effect_snapshot(
        code,
        value_bp,
        season_id=season[0],
        season_key=season[1],
        name=name,
        text=text,
        stored_rule_version=int(stored_version or 1),
        starts_on=str(season[4]),
        ends_on=str(season[3]),
    )
    # 未知机器码仍可被管理端记录，但绝不会进入战斗。
    if not snapshot["active"]:
        snapshot["text"] = "当前天象规则未启用战斗数值。"
    return snapshot


async def get_active_season_effect(cursor, today=None):
    """供副本、组队与世界 Boss 在开战时读取赛季 PVE 快照。"""
    try:
        season = await _current_season(cursor, today)
        return await _load_active_effect(cursor, season, today)
    except (aiomysql.OperationalError, aiomysql.ProgrammingError) as error:
        if error.args and error.args[0] in (1054, 1146):
            return season_effect_snapshot(
                "",
                0,
                migration_pending=True,
                text="赛季运行时迁移尚未部署，本场不应用天象数值。",
            )
        raise


async def get_equipped_cosmetics(uid, cursor):
    try:
        await cursor.execute(
            """
            SELECT e.cosmetic_type, e.cosmetic_code, c.cosmetic_name
            FROM user_cosmetic_equipped e
            JOIN user_cosmetic u ON u.uid = e.uid AND u.cosmetic_code = e.cosmetic_code
            JOIN cosmetic_catalog c ON c.cosmetic_code = e.cosmetic_code
            WHERE e.uid = %s
            ORDER BY e.cosmetic_type
            """,
            (uid,),
        )
    except (aiomysql.OperationalError, aiomysql.ProgrammingError) as error:
        if error.args and error.args[0] in (1054, 1146):
            return {}
        raise
    return {
        cosmetic_type: {"code": code, "name": name}
        for cosmetic_type, code, name in await cursor.fetchall()
    }


async def record_season_event(uid, source):
    """由真实玩法调用；同一来源每天仅计一次，异常不影响原玩法。"""
    xp = EVENT_XP.get(source)
    if not xp:
        return False
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                season = await _current_season(cursor)
                await cursor.execute(
                    """
                    INSERT IGNORE INTO season_task_log
                        (season_id, uid, source, task_date, xp)
                    VALUES (%s, %s, %s, CURDATE(), %s)
                    """,
                    (season[0], uid, source, xp),
                )
                recorded = bool(cursor.rowcount)
                if recorded:
                    await cursor.execute(
                        """
                        INSERT INTO user_season_progress (season_id, uid, xp)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE xp = xp + VALUES(xp)
                        """,
                        (season[0], uid, xp),
                    )
                await conn.commit()
                return recorded
    except Exception:
        return False


@reg_xz_func
async def season_home(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            season = await _current_season(cursor)
            await cursor.execute(
                "SELECT xp FROM user_season_progress WHERE season_id = %s AND uid = %s",
                (season[0], uid),
            )
            row = await cursor.fetchone()
            xp = int(row[0]) if row else 0
            effect = await _load_active_effect(cursor, season)
            equipped = await get_equipped_cosmetics(uid, cursor)
            await conn.commit()
    output = f"##### ✨ 赛季｜{season[2]}\n\n赛季编号：{season[1]}｜剩余 {season_days_left()} 天\n"
    output += f"赛季经验：{xp}｜当前天象：{effect.get('name', '天象休整')}\n"
    output += f"> {effect.get('text', '当前没有生效中的 PVE 天象。')}\n"
    if equipped:
        output += "> 已佩戴：" + "｜".join(
            f"{COSMETIC_TYPE_NAMES.get(kind, kind)}·{item['name']}"
            for kind, item in equipped.items()
        ) + "\n"
    output += "\n进度来源：每日首次副本通关 +8、宗门委托 +5、世界 Boss +10。\n"
    output += "奖励均为可佩戴外观，不提供永久数值。\n\n"
    output += "<qqbot-cmd-input text='赛季任务' show='赛季任务' /> | <qqbot-cmd-input text='赛季奖励' show='领取奖励' /> | <qqbot-cmd-input text='赛季装扮' show='我的装扮' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def season_tasks(uid, qz):
    return {
        "type": "markdown",
        "content": "##### ✨ 赛季任务\n\n> 每日首次完整副本通关：+8 赛季经验\n> 每日首次宗门委托：+5 赛季经验\n> 每日首次世界 Boss 贡献：+10 赛季经验\n\n完成对应真实玩法后自动计入，无需额外领取。\n\n<qqbot-cmd-input text='赛季' show='赛季主页' />",
    }


@reg_xz_func
async def season_rewards(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            season = await _current_season(cursor)
            await cursor.execute(
                "SELECT xp FROM user_season_progress WHERE season_id = %s AND uid = %s",
                (season[0], uid),
            )
            row = await cursor.fetchone()
            xp = int(row[0]) if row else 0
            eligible = reward_for_xp(xp)
            catalog_by_tier = {item["threshold"]: item for item in cosmetic_catalog(season[1])}
            granted = []
            for threshold, name, _, _ in eligible:
                item = catalog_by_tier[threshold]
                await cursor.execute(
                    """
                    INSERT IGNORE INTO season_reward_log
                        (season_id, uid, reward_tier, reward_name)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (season[0], uid, threshold, name),
                )
                # 即使旧版本只写过奖励日志，也会在这里补发真实外观资产。
                await cursor.execute(
                    """
                    INSERT IGNORE INTO user_cosmetic (uid, cosmetic_code, source_season_id)
                    VALUES (%s, %s, %s)
                    """,
                    (uid, item["code"], season[0]),
                )
                if cursor.rowcount:
                    granted.append(name)
            await conn.commit()
    if granted:
        return {
            "type": "markdown",
            "content": "赛季装扮已入库：" + "、".join(granted) + "。\n\n<qqbot-cmd-input text='赛季装扮' show='立即佩戴' />",
        }
    if eligible:
        return {
            "type": "markdown",
            "content": f"当前经验 {xp}，已达成的赛季装扮均已领取。\n\n<qqbot-cmd-input text='赛季装扮' show='查看装扮' />",
        }
    next_item = next((item for item in REWARDS if xp < item[0]), None)
    return {
        "type": "markdown",
        "content": f"暂无可领取的赛季奖励。当前经验 {xp}；下一档：{next_item[0] if next_item else '已全部领取'}。",
    }


@reg_xz_func
async def season_cosmetics(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT c.cosmetic_code, c.cosmetic_type, c.cosmetic_name, c.description,
                       CASE WHEN e.cosmetic_code IS NULL THEN 0 ELSE 1 END AS equipped
                FROM user_cosmetic u
                JOIN cosmetic_catalog c ON c.cosmetic_code = u.cosmetic_code
                LEFT JOIN user_cosmetic_equipped e
                  ON e.uid = u.uid AND e.cosmetic_type = c.cosmetic_type
                 AND e.cosmetic_code = c.cosmetic_code
                WHERE u.uid = %s
                ORDER BY u.acquired_at, c.reward_tier
                """,
                (uid,),
            )
            rows = await cursor.fetchall()
    output = "##### 👘 赛季装扮\n\n"
    if not rows:
        output += "尚未拥有赛季装扮。完成赛季任务后发送“赛季奖励”领取。\n\n"
    for code, cosmetic_type, name, description, equipped in rows:
        state = "已佩戴" if equipped else f"<qqbot-cmd-input text='赛季佩戴 {code}' show='佩戴' />"
        output += f"> **{name}**｜{COSMETIC_TYPE_NAMES.get(cosmetic_type, cosmetic_type)}｜{state}\n> {description}\n\n"
    output += "装扮只改变玩家展示，不提供战斗属性。\n\n<qqbot-cmd-input text='赛季' show='返回赛季主页' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def season_equip_cosmetic(uid, qz, cosmetic_code):
    cosmetic_code = str(cosmetic_code or "").strip().upper()
    if not cosmetic_code or len(cosmetic_code) > 96:
        return {"type": "markdown", "content": "请从“赛季装扮”中选择一件已拥有的装扮佩戴。"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT c.cosmetic_type, c.cosmetic_name
                FROM user_cosmetic u
                JOIN cosmetic_catalog c ON c.cosmetic_code = u.cosmetic_code
                WHERE u.uid = %s AND u.cosmetic_code = %s
                LIMIT 1 FOR UPDATE
                """,
                (uid, cosmetic_code),
            )
            row = await cursor.fetchone()
            if not row:
                return {"type": "markdown", "content": "未找到这件已拥有的赛季装扮，请先发送“赛季装扮”查看。"}
            cosmetic_type, name = row
            await cursor.execute(
                """
                INSERT INTO user_cosmetic_equipped (uid, cosmetic_type, cosmetic_code)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    cosmetic_code = VALUES(cosmetic_code), equipped_at = CURRENT_TIMESTAMP
                """,
                (uid, cosmetic_type, cosmetic_code),
            )
            await conn.commit()
    return {
        "type": "markdown",
        "content": f"已佩戴{COSMETIC_TYPE_NAMES.get(cosmetic_type, cosmetic_type)}「{name}」。\n\n<qqbot-cmd-input text='赛季装扮' show='返回装扮列表' />",
    }
