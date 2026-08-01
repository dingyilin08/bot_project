# -*- coding: utf-8 -*-
"""事务内角色经验结算。"""

from Game_domain.reward_service import RewardError, calculate_exp_progress


async def apply_role_experience(cursor, *, uid: int, role_id: int, add_exp: int) -> dict:
    await cursor.execute(
        """SELECT id,`name`,dengji,exp FROM user_role
           WHERE id=%s AND uid=%s LIMIT 1 FOR UPDATE""",
        (role_id, uid),
    )
    role = await cursor.fetchone()
    if not role:
        raise RewardError("ROLE_NOT_FOUND", "出战角色不存在")
    level, current_exp = int(role[2]), int(role[3])
    progress = calculate_exp_progress(level, current_exp, int(add_exp))
    gained = int(progress["levels_gained"])
    additions = [0] * 9
    if gained:
        await cursor.execute(
            """SELECT gongji,fangyu,qixue,baoji,baoshang,mingzhong,shanbi,pofang,xixue
               FROM data_role WHERE `name`=%s LIMIT 1""",
            (role[1],),
        )
        base = await cursor.fetchone()
        if not base:
            raise RewardError("ROLE_TEMPLATE_NOT_FOUND", "角色模板不存在")
        additions[0] = int(base[0] * 0.025) * gained
        additions[1] = int(base[1] * 0.015) * gained
        additions[2] = int(base[2] * 0.015) * gained
        additions[3] = 15 * gained
        additions[4] = 20 * gained
        additions[5] = 25 * gained
        additions[6] = 15 * gained
        for gained_level in range(level + 1, int(progress["level"]) + 1):
            if gained_level % 10 == 0:
                additions[7] += 50
                additions[8] += 30
    await cursor.execute(
        """UPDATE user_role SET dengji=%s,exp=%s,gongji=gongji+%s,
           fangyu=fangyu+%s,qixue=qixue+%s,baoji=baoji+%s,
           baoshang=baoshang+%s,mingzhong=mingzhong+%s,shanbi=shanbi+%s,
           pofang=pofang+%s,xixue=xixue+%s WHERE id=%s AND uid=%s""",
        (progress["level"], progress["exp"], *additions, role_id, uid),
    )
    progress.update({"level_before": level, "add_gongji": additions[0],
                     "add_fangyu": additions[1], "add_qixue": additions[2]})
    return progress
