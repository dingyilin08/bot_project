# -*- coding: utf-8 -*-
"""玩家仪表盘与管理端只读查询。"""

import json

from sql.mysql import connect_mysql


def _limit(value, maximum=100):
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return 20


async def get_dashboard(uid: int) -> dict:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """SELECT id,`name`,is_chushi,is_canwu,cw_timestamp,cw_exp,
                          lingshi,xianyu,dungeon_num,power,power_role_name
                   FROM user_zt WHERE id=%s LIMIT 1""",
                (int(uid),),
            )
            player = await cursor.fetchone()
            if not player:
                raise ValueError("玩家不存在。")
            await cursor.execute(
                """SELECT id,`name`,dengji,exp,stage,world,gongji,fangyu,qixue,fali,sudu
                   FROM user_role
                   WHERE uid=%s AND is_chuzhan=1 LIMIT 1""",
                (int(uid),),
            )
            role = await cursor.fetchone()

    dashboard = {
        "player": {
            "uid": int(player[0]),
            "name": player[1],
            "initialized": bool(player[2]),
            "cultivating": bool(player[3]),
            "cultivation_started_at": int(player[4] or 0),
            "cultivation_exp": int(player[5] or 0),
            "lingshi": int(player[6] or 0),
            "xianyu": int(player[7] or 0),
            "dungeon_attempts": int(player[8] or 0),
            "power": int(player[9] or 0),
            "power_role_name": player[10] or "",
        },
        "role": None,
    }
    if role:
        dashboard["role"] = {
            "id": int(role[0]),
            "name": role[1],
            "level": int(role[2]),
            "exp": int(role[3] or 0),
            "stage": role[4] or "未入境",
            "world": role[5] or "诸天",
            "attack": int(role[6] or 0),
            "defense": int(role[7] or 0),
            "health": int(role[8] or 0),
            "mana": int(role[9] or 0),
            "speed": int(role[10] or 0),
        }
    return dashboard


async def list_player_roles(uid: int) -> list:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """SELECT id,`name`,dengji,exp,stage,world,is_chuzhan,
                          gongji,fangyu,qixue,fali,sudu
                   FROM user_role WHERE uid=%s
                   ORDER BY is_chuzhan DESC,id ASC""",
                (int(uid),),
            )
            rows = await cursor.fetchall()
    return [
        {
            "id": int(row[0]),
            "name": row[1],
            "level": int(row[2] or 0),
            "exp": int(row[3] or 0),
            "stage": row[4] or "未入境",
            "world": row[5] or "诸天",
            "active": bool(row[6]),
            "attack": int(row[7] or 0),
            "defense": int(row[8] or 0),
            "health": int(row[9] or 0),
            "mana": int(row[10] or 0),
            "speed": int(row[11] or 0),
        }
        for row in rows
    ]


async def list_player_inventory(uid: int, page: int = 1, page_size: int = 40) -> dict:
    page = max(1, int(page or 1))
    page_size = _limit(page_size, 60)
    offset = (page - 1) * page_size
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT COUNT(*) FROM user_item WHERE uid=%s AND item_num>0",
                (int(uid),),
            )
            total = int((await cursor.fetchone())[0])
            await cursor.execute(
                """SELECT ui.item_id,di.`name`,di.`type`,di.`desc`,di.`access`,ui.item_num
                   FROM user_item ui
                   JOIN data_item di ON di.id=ui.item_id
                   WHERE ui.uid=%s AND ui.item_num>0
                   ORDER BY di.`type`,ui.item_id
                   LIMIT %s OFFSET %s""",
                (int(uid), page_size, offset),
            )
            rows = await cursor.fetchall()
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "id": int(row[0]),
                "name": row[1],
                "type": int(row[2] or 0),
                "description": row[3] or "",
                "access": row[4] or "",
                "amount": int(row[5] or 0),
            }
            for row in rows
        ],
    }


async def search_players(query: str = "", limit: int = 20) -> list:
    term = str(query or "").strip()[:32]
    limit = _limit(limit, 50)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            if term:
                if term.isdigit():
                    await cursor.execute(
                        """SELECT id,`name`,lingshi,xianyu,power,power_role_name
                           FROM user_zt WHERE id=%s OR `name` LIKE %s
                           ORDER BY id LIMIT %s""",
                        (int(term), f"%{term}%", limit),
                    )
                else:
                    await cursor.execute(
                        """SELECT id,`name`,lingshi,xianyu,power,power_role_name
                           FROM user_zt WHERE `name` LIKE %s ORDER BY id LIMIT %s""",
                        (f"%{term}%", limit),
                    )
            else:
                await cursor.execute(
                    """SELECT id,`name`,lingshi,xianyu,power,power_role_name
                       FROM user_zt ORDER BY id DESC LIMIT %s""",
                    (limit,),
                )
            rows = await cursor.fetchall()
    return [
        {
            "uid": int(row[0]),
            "name": row[1],
            "lingshi": int(row[2] or 0),
            "xianyu": int(row[3] or 0),
            "power": int(row[4] or 0),
            "role_name": row[5] or "",
        }
        for row in rows
    ]


async def search_items(query: str = "", limit: int = 30) -> list:
    term = str(query or "").strip()[:50]
    limit = _limit(limit, 100)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            if term:
                if term.isdigit():
                    await cursor.execute(
                        """SELECT id,`name`,`type`,`desc` FROM data_item
                           WHERE id=%s OR `name` LIKE %s ORDER BY id LIMIT %s""",
                        (int(term), f"%{term}%", limit),
                    )
                else:
                    await cursor.execute(
                        """SELECT id,`name`,`type`,`desc` FROM data_item
                           WHERE `name` LIKE %s ORDER BY id LIMIT %s""",
                        (f"%{term}%", limit),
                    )
            else:
                await cursor.execute(
                    "SELECT id,`name`,`type`,`desc` FROM data_item ORDER BY id LIMIT %s",
                    (limit,),
                )
            rows = await cursor.fetchall()
    return [
        {"id": int(row[0]), "name": row[1], "type": int(row[2]), "description": row[3] or ""}
        for row in rows
    ]


async def write_admin_audit(
    *,
    request_id: str,
    operator_uid: int,
    action: str,
    status: str,
    detail: dict,
    target_uid: int = None,
) -> None:
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """INSERT INTO web_admin_audit
                   (request_id,operator_uid,target_uid,action,status,detail_json)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE status=VALUES(status),detail_json=VALUES(detail_json)""",
                (
                    str(request_id)[:80],
                    int(operator_uid),
                    int(target_uid) if target_uid is not None else None,
                    str(action)[:32],
                    str(status)[:16],
                    json.dumps(detail, ensure_ascii=False),
                ),
            )
        await conn.commit()


async def list_admin_audit(limit: int = 50) -> list:
    limit = _limit(limit, 100)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """SELECT request_id,operator_uid,target_uid,action,status,detail_json,created_at
                   FROM web_admin_audit ORDER BY id DESC LIMIT %s""",
                (limit,),
            )
            rows = await cursor.fetchall()
    result = []
    for row in rows:
        try:
            detail = row[5] if isinstance(row[5], dict) else json.loads(row[5] or "{}")
        except (TypeError, ValueError):
            detail = {}
        result.append(
            {
                "request_id": row[0],
                "operator_uid": int(row[1]),
                "target_uid": int(row[2]) if row[2] is not None else None,
                "action": row[3],
                "status": row[4],
                "detail": detail,
                "created_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
            }
        )
    return result
