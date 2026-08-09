# -*- coding: utf-8 -*-
"""副本扫荡：消耗扫荡券与历练次数，结算一轮已通关副本的标准奖励。"""

import hashlib
import json
import logging
import random
from datetime import date
from uuid import uuid4

from func.pd_func import reg_xz_func
from sql.mysql import connect_mysql
from Game_domain.dungeon_daily_limit import (
    consume_daily_attempt,
    ensure_daily_attempt_schema,
    get_daily_attempt_status,
)
from Game_domain.reward_service import MySQLRewardService
from Game_main.g6_dungeon import (
    EXP_MULTIPLIER,
    KILL_STREAK_REWARDS,
    LINGSHI_MULTIPLIER,
    ensure_dungeon_clear_schema,
)
from Game_main.g7_equip import QUALITY_DROP_RATE
from Game_main.g10_shop import (
    DUNGEON_SWEEP_TICKET_DAILY_LIMIT,
    DUNGEON_SWEEP_TICKET_ITEM_ID,
)


LOGGER = logging.getLogger(__name__)
SWEEP_TICKET_NAME = "扫荡副本券"


class DungeonSweepError(Exception):
    """可直接展示给玩家的扫荡失败原因。"""


def parse_dungeon_id(value):
    """解析正整数副本编号。"""
    try:
        dungeon_id = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return dungeon_id if dungeon_id > 0 else None


def _split_item_ids(value):
    return list(dict.fromkeys(
        int(part) for part in str(value or "").split("|") if part.strip().isdigit()
    ))


def calculate_full_clear_currency(reward_exp, reward_lingshi):
    """按实际副本15场战斗（12小怪、3首领、连胜加成）汇总经验与灵石。"""
    base_exp = int(reward_exp or 0) // 15 * EXP_MULTIPLIER
    base_lingshi = int(reward_lingshi or 0) // 15 * LINGSHI_MULTIPLIER
    total_exp = 0
    total_lingshi = 0
    for kill_streak in range(1, 16):
        monster_bonus = 2.0 if kill_streak % 5 == 0 else 1.0
        streak_bonus = 1.0
        for threshold, bonus in KILL_STREAK_REWARDS.items():
            if kill_streak >= threshold:
                streak_bonus = max(streak_bonus, bonus)
        total_exp += int(int(base_exp * monster_bonus) * streak_bonus)
        total_lingshi += int(int(base_lingshi * monster_bonus) * streak_bonus)
    return total_exp, total_lingshi


def build_sweep_reward_plan(dungeon, equip_templates=(), seed=None):
    """生成与完整普通通关一致的随机奖励计划，不含实战专属与破解额外掉落。"""
    rng = random.Random(str(seed or uuid4()))
    total_exp, total_lingshi = calculate_full_clear_currency(
        dungeon.get("reward_exp"), dungeon.get("reward_lingshi")
    )
    item_totals = {}

    def add_item(item_id, amount=1):
        if item_id and amount > 0:
            item_id = int(item_id)
            item_totals[item_id] = item_totals.get(item_id, 0) + int(amount)

    skill_ids = _split_item_ids(dungeon.get("reward_skill"))
    boss_materials = _split_item_ids(dungeon.get("reward_cl_boss"))
    normal_materials = _split_item_ids(dungeon.get("reward_cl_normal")) or boss_materials

    for battle_index in range(1, 16):
        is_boss = battle_index % 5 == 0
        if is_boss:
            if (
                dungeon.get("reward_benyuan")
                and rng.randint(1, 100) <= int(dungeon.get("rate_benyuan") or 0)
            ):
                add_item(dungeon["reward_benyuan"])
            for skill_id in skill_ids:
                if rng.randint(1, 100) <= int(dungeon.get("rate_skill") or 0):
                    add_item(skill_id)

        material_pool = boss_materials if is_boss else normal_materials
        if material_pool:
            draw_count = min(2 if is_boss else 1, len(material_pool))
            for material_id in rng.sample(material_pool, draw_count):
                add_item(material_id, rng.randint(1, 3))

    equipment = None
    if equip_templates:
        selected = rng.choice(list(equip_templates))
        quality_roll = rng.uniform(0, 100)
        quality = "凡品"
        for threshold, candidate in QUALITY_DROP_RATE:
            if quality_roll <= threshold:
                quality = candidate
                break
        equipment = {
            "equip_id": int(selected["id"]),
            "name": selected["name"],
            "quality": quality,
        }

    if (
        dungeon.get("reward_pojing_dan")
        and rng.randint(1, 100) <= int(dungeon.get("rate_pojing_dan") or 0)
    ):
        add_item(dungeon["reward_pojing_dan"])

    return {
        "exp": total_exp,
        "lingshi": total_lingshi,
        "item_totals": item_totals,
        "equipment": equipment,
    }


async def _ensure_sweep_schema(cursor):
    await ensure_dungeon_clear_schema(cursor)
    await cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_dungeon_sweep_log (
            id BIGINT NOT NULL AUTO_INCREMENT,
            request_key CHAR(64) NOT NULL,
            uid INT NOT NULL,
            dungeon_id INT NOT NULL,
            role_id INT NOT NULL,
            reward_json LONGTEXT NOT NULL,
            remaining_challenges INT NOT NULL,
            remaining_tickets INT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_request_key (request_key),
            KEY idx_uid_created (uid, created_at),
            KEY idx_uid_dungeon (uid, dungeon_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家_副本扫荡记录'
        """
    )
    # 兼容上线前已经完成的副本进度，将现存通关状态迁入永久记录。
    await cursor.execute(
        """
        INSERT IGNORE INTO user_dungeon_clear (uid, dungeon_id, clear_count, first_clear_at, last_clear_at)
        SELECT uid, dungeon_id, 1, COALESCE(start_time, CURRENT_TIMESTAMP),
               COALESCE(last_update, CURRENT_TIMESTAMP)
        FROM user_dungeon_progress WHERE status = 'completed'
        """
    )


def _dungeon_from_row(row):
    keys = (
        "id", "name", "world", "min_level", "min_stage", "description",
        "reward_exp", "reward_lingshi", "reward_benyuan", "rate_benyuan",
        "reward_skill", "rate_skill", "reward_pojing_dan", "rate_pojing_dan",
        "reward_cl_boss", "reward_cl_boss_count", "reward_cl_normal",
        "reward_cl_normal_count",
    )
    return dict(zip(keys, row))


async def _load_dungeon(cursor, dungeon_id):
    await cursor.execute(
        """
        SELECT id, name, world, min_level, min_stage, description,
               reward_exp, reward_lingshi, reward_benyuan, rate_benyuan,
               reward_skill, rate_skill, reward_pojing_dan, rate_pojing_dan,
               reward_cl_boss, reward_cl_boss_count, reward_cl_normal, reward_cl_normal_count
        FROM data_dungeon WHERE id = %s LIMIT 1
        """,
        (dungeon_id,),
    )
    row = await cursor.fetchone()
    return _dungeon_from_row(row) if row else None


async def _load_item_names(cursor, item_ids):
    item_ids = list(dict.fromkeys(int(item_id) for item_id in item_ids if int(item_id) > 0))
    if not item_ids:
        return {}
    placeholders = ",".join(["%s"] * len(item_ids))
    await cursor.execute(
        f"SELECT id, name FROM data_item WHERE id IN ({placeholders})",
        tuple(item_ids),
    )
    return {int(row[0]): row[1] for row in await cursor.fetchall()}


def _render_sweep_result(reward, duplicate=False):
    title = "##### ✅ 扫荡完成"
    if duplicate:
        title = "##### ✅ 本次扫荡已结算"
    lines = [
        title,
        f"> **{reward['dungeon_name']}** 的旧日强敌已被道友弹指镇压。",
        "***",
        f"**基础收获**：经验 +{reward['exp']} ｜ 灵石 +{reward['lingshi']}",
    ]
    if reward.get("items"):
        lines.append("**战利品**")
        for item in reward["items"]:
            lines.append(f"> {item['name']} x{item['count']}")
    equipment = reward.get("equipment")
    if equipment:
        lines.append(f"**装备掉落**：{equipment['quality']}·{equipment['name']}")
    if reward.get("level_after", 0) > reward.get("level_before", 0):
        lines.append(f"**境界精进**：Lv.{reward['level_before']} → Lv.{reward['level_after']}")
    elif reward.get("need_breakthrough"):
        lines.append(f"> 经验已积蓄至突破关隘，请先完成 Lv.{reward['level_after']} 的悟道进阶。")
    lines.extend([
        "***",
        f"消耗：{SWEEP_TICKET_NAME} x1、历练次数 x1",
        f"剩余：扫荡券 **{reward['remaining_tickets']}** ｜ 历练次数 **{reward['remaining_challenges']}**",
        "<qqbot-cmd-input text='扫荡副本' show='继续扫荡' /> | <qqbot-cmd-input text='物品背包' show='查看背包' /> | <qqbot-cmd-input text='商城' show='购买扫荡券' />",
        "> 扫荡结算普通完整通关奖励；角色专属战斗掉落与首领破解额外奖励仍需亲自迎战。",
    ])
    return {"type": "markdown", "content": "\n".join(lines)}


@reg_xz_func
async def dungeon_sweep_list(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_sweep_schema(cursor)
            await ensure_daily_attempt_schema(cursor)
            await conn.commit()
            attempt_status = await get_daily_attempt_status(cursor, uid, lock=True)
            if not attempt_status:
                return {"type": "markdown", "content": "未找到玩家数据，请重新注册后再试。"}
            remaining = attempt_status["remaining"]
            await cursor.execute(
                "SELECT id, name, dengji FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1",
                (uid,),
            )
            role = await cursor.fetchone()
            if not role:
                await conn.commit()
                return {
                    "type": "markdown",
                    "content": "当前没有出战角色，请先选择出战角色。\n<qqbot-cmd-input text='角色背包' show='角色背包' />",
                }
            await cursor.execute(
                "SELECT item_num FROM user_item WHERE uid = %s AND item_id = %s LIMIT 1",
                (uid, DUNGEON_SWEEP_TICKET_ITEM_ID),
            )
            ticket_row = await cursor.fetchone()
            tickets = int((ticket_row or [0])[0] or 0)
            await cursor.execute(
                """
                SELECT d.id, d.name, d.world, d.min_level, c.clear_count
                FROM user_dungeon_clear c
                JOIN data_dungeon d ON d.id = c.dungeon_id
                WHERE c.uid = %s AND d.min_level <= %s
                ORDER BY d.min_level, d.id
                """,
                (uid, int(role[2])),
            )
            dungeons = await cursor.fetchall()
            await conn.commit()

    lines = [
        "##### ⚡ 副本扫荡",
        f"> 出战：**{role[1]} Lv.{role[2]}**",
        f"> 扫荡券：**{tickets}** ｜ 剩余历练次数：**{remaining}**",
        "***",
    ]
    if not dungeons:
        lines.extend([
            "尚无可扫荡副本。亲手完成一次副本后，即可永久解锁该副本扫荡。",
            "<qqbot-cmd-input text='副本列表' show='前往挑战' />",
        ])
    else:
        for dungeon_id, name, world, min_level, clear_count in dungeons:
            lines.append(f"**{dungeon_id}. {name}**｜{world}｜Lv.{min_level}+")
            lines.append(f"> 已通关 {clear_count} 次")
            lines.append(f"<qqbot-cmd-input text='扫荡副本 {dungeon_id}' show='一键扫荡 {name}' />")
            lines.append("")
        lines.extend([
            "***",
            "每次扫荡消耗1张扫荡副本券与1次历练次数，获得一轮普通完整通关奖励。",
        ])
    lines.append("<qqbot-cmd-input text='商城' show='购买扫荡券' /> | <qqbot-cmd-input text='副本菜单' show='副本菜单' />")
    return {"type": "markdown", "content": "\n".join(lines)}


@reg_xz_func
async def sweep_dungeon(uid, qz, dungeon_id, request_id=None):
    dungeon_id = parse_dungeon_id(dungeon_id)
    if dungeon_id is None:
        return {
            "type": "markdown",
            "content": "指令错误，正确指令：扫荡副本 副本编号\n示例：扫荡副本 1\n<qqbot-cmd-input text='扫荡副本' show='可扫荡副本' />",
        }

    request_source = str(request_id or uuid4())
    request_key = hashlib.sha256(f"{uid}:{request_source}".encode("utf-8")).hexdigest()
    today = date.today()
    try:
        async with connect_mysql() as conn:
            try:
                async with conn.cursor() as cursor:
                    await _ensure_sweep_schema(cursor)
                    await ensure_daily_attempt_schema(cursor)
                    await conn.commit()
                    attempt_status = await get_daily_attempt_status(
                        cursor, uid, lock=True, stat_date=today
                    )
                    if not attempt_status:
                        raise DungeonSweepError("未找到玩家数据，请重新注册后再试。")

                    await cursor.execute(
                        "SELECT reward_json FROM user_dungeon_sweep_log WHERE request_key = %s LIMIT 1",
                        (request_key,),
                    )
                    duplicate = await cursor.fetchone()
                    if duplicate:
                        await conn.rollback()
                        reward = json.loads(duplicate[0])
                        return _render_sweep_result(reward, duplicate=True)

                    remaining = attempt_status["remaining"]
                    if remaining <= 0:
                        raise DungeonSweepError(
                            f"今日副本挑战与扫荡额度已用完（{attempt_status['used']}/{attempt_status['limit']}）。"
                            "可使用体力药补充额度，或明日再来。"
                        )

                    await cursor.execute(
                        """
                        SELECT id, `name`, dengji, exp, gongji, fangyu, qixue,
                               baoji, baoshang, mingzhong, shanbi, pofang, xixue
                        FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1 FOR UPDATE
                        """,
                        (uid,),
                    )
                    role = await cursor.fetchone()
                    if not role:
                        raise DungeonSweepError("当前没有出战角色，请先选择出战角色。")

                    await cursor.execute(
                        "SELECT dungeon_id FROM user_dungeon_progress WHERE uid = %s AND status = 'fighting' LIMIT 1",
                        (uid,),
                    )
                    active_progress = await cursor.fetchone()
                    if active_progress:
                        raise DungeonSweepError("你还有进行中的副本，请先完成或放弃当前副本后再扫荡。")

                    await cursor.execute(
                        "SELECT 1 FROM user_dungeon_clear WHERE uid = %s AND dungeon_id = %s LIMIT 1",
                        (uid, dungeon_id),
                    )
                    if not await cursor.fetchone():
                        raise DungeonSweepError("该副本尚未挑战成功。亲手通关一次后即可永久解锁扫荡。")

                    dungeon = await _load_dungeon(cursor, dungeon_id)
                    if not dungeon:
                        raise DungeonSweepError("副本不存在，请发送“扫荡副本”查看可扫荡列表。")
                    if int(role[2]) < int(dungeon["min_level"]):
                        raise DungeonSweepError(
                            f"当前出战角色等级不足，{dungeon['name']}需要 Lv.{dungeon['min_level']}。"
                        )

                    await cursor.execute(
                        "SELECT item_num FROM user_item WHERE uid = %s AND item_id = %s FOR UPDATE",
                        (uid, DUNGEON_SWEEP_TICKET_ITEM_ID),
                    )
                    ticket_row = await cursor.fetchone()
                    tickets = int((ticket_row or [0])[0] or 0)
                    if tickets <= 0:
                        raise DungeonSweepError(
                            f"扫荡副本券不足。商城售价800灵石，每日限购{DUNGEON_SWEEP_TICKET_DAILY_LIMIT}张。\n"
                            "<qqbot-cmd-input text='购买商品 扫荡副本券' show='购买扫荡副本券' />"
                        )

                    await cursor.execute(
                        "SELECT id, name FROM data_equip WHERE dungeon_id = %s ORDER BY id",
                        (dungeon_id,),
                    )
                    equip_templates = [
                        {"id": int(row[0]), "name": row[1]} for row in await cursor.fetchall()
                    ]
                    plan = build_sweep_reward_plan(dungeon, equip_templates, request_key)
                    item_names = await _load_item_names(cursor, plan["item_totals"].keys())

                    await cursor.execute(
                        """
                        UPDATE user_item SET item_num = item_num - 1
                        WHERE uid = %s AND item_id = %s AND item_num >= 1
                        """,
                        (uid, DUNGEON_SWEEP_TICKET_ITEM_ID),
                    )
                    if cursor.rowcount <= 0:
                        raise DungeonSweepError("扫荡副本券不足，请前往商城购买。")
                    await cursor.execute(
                        "DELETE FROM user_item WHERE uid = %s AND item_id = %s AND item_num <= 0",
                        (uid, DUNGEON_SWEEP_TICKET_ITEM_ID),
                    )
                    attempt_result = await consume_daily_attempt(
                        cursor, uid, stat_date=today
                    )
                    if not attempt_result:
                        raise DungeonSweepError("副本历练次数扣除失败，请稍后重试。")

                    progress = await MySQLRewardService().apply_experience(cursor, role, plan["exp"])
                    await cursor.execute(
                        "UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s",
                        (plan["lingshi"], uid),
                    )
                    for item_id, amount in plan["item_totals"].items():
                        await cursor.execute(
                            """
                            INSERT INTO user_item (uid, item_id, item_num) VALUES (%s, %s, %s)
                            ON DUPLICATE KEY UPDATE item_num = item_num + VALUES(item_num)
                            """,
                            (uid, item_id, amount),
                        )
                    if plan["equipment"]:
                        await cursor.execute(
                            """
                            INSERT INTO user_equip (uid, equip_id, level, quality, is_equipped)
                            VALUES (%s, %s, 0, %s, 0)
                            """,
                            (uid, plan["equipment"]["equip_id"], plan["equipment"]["quality"]),
                        )
                    if progress["level"] != int(role[2]):
                        from Tool.tool_power import update_role_power
                        await update_role_power(conn, uid)

                    remaining_tickets = tickets - 1
                    remaining_challenges = attempt_result["remaining"]
                    reward = {
                        "dungeon_id": dungeon_id,
                        "dungeon_name": dungeon["name"],
                        "exp": plan["exp"],
                        "lingshi": plan["lingshi"],
                        "items": [
                            {
                                "id": item_id,
                                "name": item_names.get(item_id, f"物品#{item_id}"),
                                "count": amount,
                            }
                            for item_id, amount in sorted(plan["item_totals"].items())
                        ],
                        "equipment": plan["equipment"],
                        "level_before": int(role[2]),
                        "level_after": int(progress["level"]),
                        "need_breakthrough": bool(progress["need_breakthrough"]),
                        "remaining_tickets": remaining_tickets,
                        "remaining_challenges": remaining_challenges,
                    }
                    await cursor.execute(
                        """
                        INSERT INTO user_dungeon_sweep_log
                            (request_key, uid, dungeon_id, role_id, reward_json,
                             remaining_challenges, remaining_tickets)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            request_key, uid, dungeon_id, int(role[0]),
                            json.dumps(reward, ensure_ascii=False),
                            remaining_challenges, remaining_tickets,
                        ),
                    )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
    except DungeonSweepError as error:
        return {
            "type": "markdown",
            "content": f"##### 扫荡未成\n{error}\n***\n<qqbot-cmd-input text='扫荡副本' show='可扫荡副本' /> | <qqbot-cmd-input text='商城' show='商城' />",
        }
    except Exception:
        LOGGER.exception("副本扫荡结算失败 uid=%s dungeon_id=%s", uid, dungeon_id)
        return {
            "type": "markdown",
            "content": "扫荡结算遇到异常，本次不会消耗扫荡券或历练次数，请稍后重试。",
        }

    from Game_main.g33_spirit_beast_v2 import record_spirit_beast_pve
    beast_reward = await record_spirit_beast_pve(
        uid, int(role[0]), completed=False, swept=True, source="SWEEP"
    )
    response = _render_sweep_result(reward)
    response["content"] += (
        f"\n\n> 🐾 扫荡基础兽材×{beast_reward['beast_material']}｜"
        f"御兽灵息×{beast_reward['spirit_essence']}；"
        "扫荡不结算羁绊与传记事件。"
    )
    return response
