# -*- coding: utf-8 -*-
"""在同一事务中发放角色与本源，供初始选角和碎片合成共用。"""


class RoleGrantError(Exception):
    pass


async def grant_role(cursor, *, uid: int, role_template_id: int) -> dict:
    await cursor.execute(
        """SELECT id, `name`, gongji, fangyu, qixue, sudu, baoji, baoshang,
                  max_fali, shanbi, mingzhong, pofang, xixue, world
           FROM data_role WHERE id=%s LIMIT 1""",
        (role_template_id,),
    )
    template = await cursor.fetchone()
    if not template:
        raise RoleGrantError("角色模板不存在。")
    role_name = template[1]
    await cursor.execute(
        "SELECT id FROM user_role WHERE uid=%s AND `name`=%s LIMIT 1 FOR UPDATE",
        (uid, role_name),
    )
    if await cursor.fetchone():
        raise RoleGrantError(f"你已经拥有角色{role_name}。")

    # 旧表的主键不是自增。数据库级命名锁把两张旧表的编号分配串行化。
    await cursor.execute("SELECT GET_LOCK('bot_project:role_grant_id', 10)")
    locked = await cursor.fetchone()
    if not locked or int(locked[0]) != 1:
        raise RoleGrantError("角色发放繁忙，请稍后重试。")
    try:
        await cursor.execute("SELECT `name` FROM data_benyuan WHERE role_name=%s LIMIT 1", (role_name,))
        benyuan = await cursor.fetchone()
        if not benyuan:
            raise RoleGrantError(f"角色{role_name}缺少本源配置。")
        await cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM user_benyuan")
        by_id = int((await cursor.fetchone())[0])
        await cursor.execute(
            "INSERT INTO user_benyuan (id,uid,`name`,dengji) VALUES (%s,%s,%s,1)",
            (by_id, uid, benyuan[0]),
        )
        await cursor.execute("SELECT COALESCE(MAX(id), 10000) + 1 FROM user_role")
        role_id = int((await cursor.fetchone())[0])
        await cursor.execute("SELECT stage_1 FROM data_stage WHERE id=%s", (role_template_id,))
        stage = await cursor.fetchone()
        if not stage:
            raise RoleGrantError(f"角色{role_name}缺少境界配置。")
        stage_name = f"{stage[0]}境"
        await cursor.execute(
            """INSERT INTO user_role
               (id,uid,`name`,dengji,exp,stage,gongji,fangyu,qixue,sudu,baoji,
                baoshang,fali,shanbi,mingzhong,pofang,xixue,world,by_id,is_chuzhan)
               VALUES (%s,%s,%s,1,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)""",
            (role_id, uid, role_name, stage_name, *template[2:], by_id),
        )
        return {
            "role_id": role_id,
            "role_template_id": int(template[0]),
            "role_name": role_name,
            "stage": stage_name,
            "by_id": by_id,
        }
    finally:
        await cursor.execute("SELECT RELEASE_LOCK('bot_project:role_grant_id')")
