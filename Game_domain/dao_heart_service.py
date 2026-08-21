# -*- coding: utf-8 -*-
"""道心问境：可复现的每日事件、事务化抉择与短效参悟增益。"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from uuid import uuid4

from sql.mysql import connect_mysql


EVENT_VERSION = 1
BUFF_EXPERIENCE = "CULTIVATION_EXP_BONUS_BP"
BUFF_DURATION = "CULTIVATION_DURATION_REDUCTION_BP"
TENDENCY_LABELS = {
    "clarity": "清明",
    "courage": "勇毅",
    "compassion": "仁心",
}

CHOICE_RULES = {
    "clarity": {
        "label": "守心观照",
        "tendency": "clarity",
        "tendency_delta": 2,
        "lingshi": 60,
        "buff_code": BUFF_DURATION,
        "buff_value": 1000,
        "buff_text": "今日新开始的参悟时长缩短 10%",
    },
    "courage": {
        "label": "迎难问锋",
        "tendency": "courage",
        "tendency_delta": 2,
        "lingshi": 80,
        "buff_code": BUFF_EXPERIENCE,
        "buff_value": 1200,
        "buff_text": "今日新开始的参悟经验提高 12%",
    },
    "compassion": {
        "label": "济人渡厄",
        "tendency": "compassion",
        "tendency_delta": 2,
        "lingshi": 100,
        "buff_code": BUFF_EXPERIENCE,
        "buff_value": 800,
        "buff_text": "今日新开始的参悟经验提高 8%",
    },
}

EVENTS = (
    {
        "key": "rain_pavilion",
        "title": "雨亭论道",
        "description": "山雨将至，一位负剑散修与受伤药童同时在亭外求助，亭中残碑又显出片刻道纹。",
        "choice_text": {
            "clarity": "闭目观碑，先辨明道纹真伪。",
            "courage": "冒雨迎向山道，探清前方异动。",
            "compassion": "扶药童入亭，为其稳住伤势。",
        },
        "result_text": {
            "clarity": "雨声洗去杂念，你从残碑中辨出一缕清静真意。",
            "courage": "你踏雨而行，剑鸣与雷声相和，道心更见锋芒。",
            "compassion": "药香在亭中散开，一念善意化作温润灵机。",
        },
    },
    {
        "key": "broken_bridge",
        "title": "断桥迷雾",
        "description": "古桥被雾海截断，对岸传来求救声，桥下却浮现一条只有静心者才能看见的旧路。",
        "choice_text": {
            "clarity": "驻足推演雾气流向，寻找旧路。",
            "courage": "以灵力护体，直渡断桥。",
            "compassion": "循着呼声先救被困行旅。",
        },
        "result_text": {
            "clarity": "你看破雾阵虚实，心湖澄澈如镜。",
            "courage": "断桥在脚下崩落，你却借势跃上彼岸。",
            "compassion": "被困行旅平安脱险，众人的谢意汇成一缕愿力。",
        },
    },
    {
        "key": "sword_mound",
        "title": "荒冢剑鸣",
        "description": "无名剑冢忽然长鸣，三道残念分别诉说克制、进取与守护之道。",
        "choice_text": {
            "clarity": "按剑不动，听完三道残念。",
            "courage": "拔出最沉寂的一柄残剑。",
            "compassion": "为剑冢立碑，安抚无主残念。",
        },
        "result_text": {
            "clarity": "万剑渐息，你在寂静中听见自己的本心。",
            "courage": "残剑虽锈，仍在你掌中发出清越剑鸣。",
            "compassion": "残念归于安宁，一点柔光落入你的识海。",
        },
    },
    {
        "key": "star_well",
        "title": "星井照心",
        "description": "洞府旧井倒映漫天星河，井沿留有三句前人问语，只容你答其中一问。",
        "choice_text": {
            "clarity": "答“万象纷纭，何者为真”。",
            "courage": "答“前路无门，何以为进”。",
            "compassion": "答“众生有苦，何以自处”。",
        },
        "result_text": {
            "clarity": "星影收束成一点，你的神思不再为外物所扰。",
            "courage": "井中星河逆流而上，为你照出一条未走之路。",
            "compassion": "星光落向人间，你愿在求道时仍为他人留一盏灯。",
        },
    },
)


class DaoHeartError(Exception):
    pass


def _date_text(value) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def deterministic_event(uid: int, event_date, version: int = EVENT_VERSION) -> dict:
    """同一玩家、日期与版本总是得到同一事件，便于重放和审计。"""

    date_text = _date_text(event_date)
    digest = hashlib.sha256(
        f"dao-heart:v{int(version)}:{int(uid)}:{date_text}".encode("utf-8")
    ).hexdigest()
    event = EVENTS[int(digest[:16], 16) % len(EVENTS)]
    return {**event, "version": int(version), "seed": digest[:16], "date": date_text}


def apply_basis_points(value: int, basis_points: int, *, increase: bool, minimum: int = 0) -> int:
    """按基点应用增益或减免，整数向下取整并保留业务最小值。"""

    value = max(0, int(value))
    basis_points = max(0, min(5000, int(basis_points)))
    multiplier = 10000 + basis_points if increase else 10000 - basis_points
    return max(int(minimum), value * multiplier // 10000)


def _loads(value):
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


def _choice_dto(event: dict, key: str) -> dict:
    rule = CHOICE_RULES[key]
    return {
        "key": key,
        "label": rule["label"],
        "description": event["choice_text"][key],
        "tendency": TENDENCY_LABELS[rule["tendency"]],
        "tendency_delta": rule["tendency_delta"],
        "reward": {"lingshi": rule["lingshi"]},
        "buff": rule["buff_text"],
    }


def _state_dto(uid: int, today, profile, daily) -> dict:
    event = deterministic_event(uid, today)
    chosen_key = None
    result = None
    if daily:
        stored_key, stored_version, stored_seed, chosen_key, result_json = daily
        matching = next((entry for entry in EVENTS if entry["key"] == stored_key), None)
        if matching:
            event = {
                **matching,
                "version": int(stored_version),
                "seed": stored_seed,
                "date": _date_text(today),
            }
        result = _loads(result_json) if chosen_key else None
    clarity, courage, compassion, buff_code, buff_value, buff_expires = profile or (0, 0, 0, None, 0, None)
    return {
        "date": _date_text(today),
        "event": {
            "key": event["key"],
            "title": event["title"],
            "description": event["description"],
            "version": event["version"],
            "seed": event["seed"],
            "choices": [_choice_dto(event, key) for key in CHOICE_RULES],
        },
        "chosen": bool(chosen_key),
        "choice_key": chosen_key,
        "result": result,
        "tendencies": {
            "clarity": int(clarity or 0),
            "courage": int(courage or 0),
            "compassion": int(compassion or 0),
        },
        "active_buff": {
            "code": buff_code,
            "value": int(buff_value or 0),
            "expires_at": str(buff_expires) if buff_expires else None,
        } if buff_code else None,
    }


async def get_daily_state(uid: int) -> dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT CURDATE()")
            today = (await cursor.fetchone())[0]
            await cursor.execute("SELECT id FROM user_zt WHERE id=%s LIMIT 1", (uid,))
            if not await cursor.fetchone():
                raise DaoHeartError("玩家不存在，请先注册游戏。")
            await cursor.execute(
                """SELECT clarity,courage,compassion,active_buff_code,
                          active_buff_value,active_buff_expires_at
                   FROM dao_heart_profile WHERE uid=%s LIMIT 1""",
                (uid,),
            )
            profile = await cursor.fetchone()
            await cursor.execute(
                """SELECT event_key,event_version,event_seed,choice_key,result_json
                   FROM dao_heart_daily WHERE uid=%s AND event_date=%s LIMIT 1""",
                (uid, today),
            )
            daily = await cursor.fetchone()
    return _state_dto(uid, today, profile, daily)


async def choose_daily_path(uid: int, choice_key: str, *, request_id: str | None = None) -> dict:
    choice_key = str(choice_key or "").strip().lower()
    if choice_key not in CHOICE_RULES:
        raise DaoHeartError("请选择清明、勇毅或仁心之道。")
    request_id = str(request_id or f"dao-heart:{uuid4().hex}")[:80]

    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT CURDATE()")
                today = (await cursor.fetchone())[0]
                await cursor.execute(
                    "SELECT `name`,lingshi FROM user_zt WHERE id=%s FOR UPDATE",
                    (uid,),
                )
                player = await cursor.fetchone()
                if not player:
                    raise DaoHeartError("玩家不存在，请先注册游戏。")

                await cursor.execute("INSERT IGNORE INTO dao_heart_profile (uid) VALUES (%s)", (uid,))
                await cursor.execute(
                    """SELECT clarity,courage,compassion,active_buff_code,
                              active_buff_value,active_buff_expires_at
                       FROM dao_heart_profile WHERE uid=%s FOR UPDATE""",
                    (uid,),
                )
                profile = await cursor.fetchone()
                await cursor.execute(
                    """SELECT event_key,event_version,event_seed,choice_key,result_json
                       FROM dao_heart_daily WHERE uid=%s AND event_date=%s FOR UPDATE""",
                    (uid, today),
                )
                daily = await cursor.fetchone()
                if daily and daily[3]:
                    replay = _loads(daily[4])
                    replay["replayed"] = True
                    await conn.rollback()
                    return replay

                event = deterministic_event(uid, today)
                if not daily:
                    await cursor.execute(
                        """INSERT INTO dao_heart_daily
                               (uid,event_date,event_key,event_version,event_seed)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (uid, today, event["key"], event["version"], event["seed"]),
                    )
                else:
                    stored = next((entry for entry in EVENTS if entry["key"] == daily[0]), None)
                    if stored:
                        event = {
                            **stored,
                            "version": int(daily[1]),
                            "seed": daily[2],
                            "date": _date_text(today),
                        }

                rule = CHOICE_RULES[choice_key]
                tendency_column = rule["tendency"]
                reward_lingshi = int(rule["lingshi"])
                balance_before = int(player[1] or 0)
                balance_after = balance_before + reward_lingshi
                await cursor.execute(
                    "UPDATE user_zt SET lingshi=lingshi+%s WHERE id=%s",
                    (reward_lingshi, uid),
                )
                tendency_increments = {
                    "clarity": int(rule["tendency_delta"]) if tendency_column == "clarity" else 0,
                    "courage": int(rule["tendency_delta"]) if tendency_column == "courage" else 0,
                    "compassion": int(rule["tendency_delta"]) if tendency_column == "compassion" else 0,
                }
                await cursor.execute(
                    """UPDATE dao_heart_profile
                        SET clarity=clarity+%s,courage=courage+%s,
                            compassion=compassion+%s,active_buff_code=%s,
                            active_buff_value=%s,
                            active_buff_expires_at=DATE_ADD(%s, INTERVAL 1 DAY),
                            last_choice_date=%s
                        WHERE uid=%s""",
                    (
                        tendency_increments["clarity"],
                        tendency_increments["courage"],
                        tendency_increments["compassion"],
                        rule["buff_code"], rule["buff_value"], today, today, uid,
                    ),
                )

                tendencies = {
                    "clarity": int(profile[0] or 0),
                    "courage": int(profile[1] or 0),
                    "compassion": int(profile[2] or 0),
                }
                tendencies[tendency_column] += int(rule["tendency_delta"])
                result = {
                    "date": _date_text(today),
                    "event_key": event["key"],
                    "event_title": event["title"],
                    "choice_key": choice_key,
                    "choice_label": rule["label"],
                    "result_text": event["result_text"][choice_key],
                    "reward": {"lingshi": reward_lingshi},
                    "buff": {
                        "code": rule["buff_code"],
                        "value": rule["buff_value"],
                        "text": rule["buff_text"],
                    },
                    "tendencies": tendencies,
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                    "replayed": False,
                }
                payload = json.dumps(result, ensure_ascii=False)
                await cursor.execute(
                    """UPDATE dao_heart_daily
                       SET choice_key=%s,tendency_key=%s,tendency_delta=%s,
                           reward_json=%s,result_json=%s,request_id=%s,chosen_at=NOW()
                       WHERE uid=%s AND event_date=%s AND choice_key IS NULL""",
                    (
                        choice_key, tendency_column, rule["tendency_delta"],
                        json.dumps({"lingshi": reward_lingshi}, ensure_ascii=False),
                        payload, request_id, uid, today,
                    ),
                )
                if cursor.rowcount != 1:
                    raise DaoHeartError("今日问境状态已变化，请重新查看。")
                await cursor.execute(
                    """INSERT IGNORE INTO reward_ledger
                           (business_key,uid,reward_type,amount,source_type,source_id,status,payload_json)
                       VALUES (%s,%s,'LINGSHI',%s,'DAO_HEART',%s,'GRANTED',%s)""",
                    (
                        f"dao-heart:{uid}:{_date_text(today)}:lingshi",
                        uid,
                        reward_lingshi,
                        f"{uid}:{_date_text(today)}",
                        payload,
                    ),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return result


async def get_active_cultivation_effects(cursor, uid: int) -> dict:
    """读取尚未过期的道心参悟 Buff；迁移未部署时安全退回无增益。"""

    try:
        await cursor.execute(
            """SELECT active_buff_code,active_buff_value
               FROM dao_heart_profile
               WHERE uid=%s AND active_buff_expires_at>NOW() LIMIT 1""",
            (uid,),
        )
        row = await cursor.fetchone()
    except Exception:
        return {"experience_bonus_bp": 0, "duration_reduction_bp": 0}
    effects = {"experience_bonus_bp": 0, "duration_reduction_bp": 0}
    if not row:
        return effects
    if row[0] == BUFF_EXPERIENCE:
        effects["experience_bonus_bp"] = int(row[1] or 0)
    elif row[0] == BUFF_DURATION:
        effects["duration_reduction_bp"] = int(row[1] or 0)
    return effects
