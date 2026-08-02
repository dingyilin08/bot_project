# -*- coding: utf-8 -*-
"""角色专属碎片的共享事务资产接口。"""


class RoleSpecialAssetError(Exception):
    pass


async def add_fragments(cursor, *, request_id: str, battle_id, uid: int, role_id: int,
                        collection_id: int, fragment_code: str, amount: int,
                        source: str) -> int:
    await cursor.execute(
        """INSERT INTO user_role_special_collection
           (uid,role_id,collection_id,fragment_amount) VALUES (%s,%s,%s,0)
           ON DUPLICATE KEY UPDATE fragment_amount=fragment_amount""",
        (uid, role_id, collection_id),
    )
    await cursor.execute(
        """SELECT fragment_amount FROM user_role_special_collection
           WHERE uid=%s AND role_id=%s AND collection_id=%s FOR UPDATE""",
        (uid, role_id, collection_id),
    )
    before = int((await cursor.fetchone())[0])
    after = before + int(amount)
    if after < 0:
        raise RoleSpecialAssetError("专属碎片不足。")
    await cursor.execute(
        """UPDATE user_role_special_collection SET fragment_amount=%s
           WHERE uid=%s AND role_id=%s AND collection_id=%s""",
        (after, uid, role_id, collection_id),
    )
    try:
        await cursor.execute(
            """INSERT INTO role_special_material_ledger
               (request_id,battle_id,uid,role_id,material_code,change_amount,
                balance_before,balance_after,source_type)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (request_id, battle_id, uid, role_id, fragment_code, amount, before, after, source),
        )
    except Exception as exc:
        if getattr(exc, "args", [None])[0] == 1062:
            raise RoleSpecialAssetError("该专属碎片请求已经处理。") from exc
        raise
    return after
