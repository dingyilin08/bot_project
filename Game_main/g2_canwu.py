from sql.mysql import *
from Tool.tool_user import *
from func.pd_func import *
import time
import random
import logging
from Tool.tool_command import *
from Tool.tool_canwu import (
    canwu_remaining_seconds,
    ensure_canwu_duration_column,
    roll_canwu_duration,
)
from Game_main.g14_estate import (
    MIN_CANWU_SECONDS,
    apply_cultivation_duration,
    cultivation_duration_reduction_bp,
    format_basis_points,
    read_estate_levels,
)
from Game_domain.monthly_card_service import (
    MONTHLY_CARD_CULTIVATION_REDUCTION_BP,
    apply_monthly_card_duration,
    has_active_monthly_card,
)


logger = logging.getLogger(__name__)


async def _apply_canwu_experience(cursor, role_id, role_name, level, current_exp, add_exp):
    """在领取事务中发放经验，避免参悟状态与角色经验分开提交。"""
    max_exp = await up_need_exp(level)
    if current_exp + add_exp <= max_exp or level in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        await cursor.execute(
            "UPDATE user_role SET exp = exp + %s WHERE id = %s",
            (add_exp, role_id),
        )
        return {"level_up": False, "need_breakthrough": current_exp + add_exp > max_exp}

    await cursor.execute(
        """
        SELECT gongji, fangyu, qixue, baoji, baoshang,
               mingzhong, shanbi, pofang, xixue
        FROM data_role WHERE `name` = %s LIMIT 1
        """,
        (role_name,),
    )
    base = await cursor.fetchone()
    if not base:
        raise RuntimeError("参悟角色模板不存在")

    add_gongji = int(base[0] * 0.025)
    add_fangyu = int(base[1] * 0.015)
    add_qixue = int(base[2] * 0.015)
    add_pofang = 50 if (level + 1) % 10 == 0 else 0
    add_xixue = 30 if (level + 1) % 10 == 0 else 0
    await cursor.execute(
        """
        UPDATE user_role SET dengji = dengji + 1, exp = %s,
            gongji = gongji + %s, fangyu = fangyu + %s, qixue = qixue + %s,
            baoji = baoji + 15, baoshang = baoshang + 20,
            mingzhong = mingzhong + 25, shanbi = shanbi + 15,
            pofang = pofang + %s, xixue = xixue + %s
        WHERE id = %s
        """,
        (
            current_exp + add_exp - max_exp,
            add_gongji,
            add_fangyu,
            add_qixue,
            add_pofang,
            add_xixue,
            role_id,
        ),
    )
    return {
        "level_up": True,
        "need_breakthrough": False,
        "add_gongji": add_gongji,
        "add_fangyu": add_fangyu,
        "add_qixue": add_qixue,
    }


# 参悟
@reg_xz_func
async def canwu_role(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            monthly_card_active = await has_active_monthly_card(cursor, uid)
            await ensure_canwu_duration_column(cursor)
            # 建筑行先于用户状态加锁，保证与洞府升级使用同一锁顺序；
            # 最终效果写入 cw_duration，之后升级聚灵阵不会追溯当前任务。
            estate_levels = await read_estate_levels(uid, cursor, for_update=True)
            sql = "SELECT id, `name`, dengji, exp FROM user_role WHERE uid = %s and is_chuzhan = 1 limit 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您当前未出战角色，无法选择使其参悟世界法则。"}
            id, name, dengji, exp = result
            sql = "SELECT is_canwu, cw_role, cw_timestamp, cw_duration, openid FROM user_zt WHERE id = %s FOR UPDATE"
            await cursor.execute(sql, (uid,))
            is_canwu, cw_role, cw_timestamp, cw_duration, openid = await cursor.fetchone()
            if is_canwu != 0:
                current_timestamp = int(time.time())
                needtime = canwu_remaining_seconds(cw_timestamp, cw_duration, current_timestamp)
                sql = "SELECT id, `name` FROM user_role WHERE id = %s limit 1"
                await cursor.execute(sql, (cw_role,))
                result = await cursor.fetchone()
                cw_role, cw_name = result
                if needtime > 0:
                    kj = await all_write_command(uid, ("参悟状态", "领取参悟经验"))

                    output = f"##### 参悟中\n\n"
                    output += f"您当前已有角色[{cw_role}.{cw_name}]正在参悟中\n\n"
                    output += f"**剩余时间：** {needtime}秒\n"

                    return {"type": "markdown", "content": output + kj}
                else:
                    kj = await all_write_command(uid, ("参悟状态", "领取参悟经验"))
                    output = f"##### 参悟已完成\n\n"
                    output += f"您当前参悟中的角色[{cw_role}.{cw_name}]已参悟完毕\n\n"
                    output += "请先**领取参悟经验**后再继续参悟吧。\n"

                    return {"type": "markdown", "content": output + kj}

            max_exp = await up_need_exp(dengji)
            add_exp = int(random.randint(0, max_exp) * 0.25 + max_exp * 0.1)
            base_duration = roll_canwu_duration()
            spirit_array_level = estate_levels["spirit_array"]
            reduction_bp = cultivation_duration_reduction_bp(spirit_array_level)
            duration = apply_cultivation_duration(base_duration, spirit_array_level)
            duration = apply_monthly_card_duration(
                duration,
                monthly_card_active,
                MONTHLY_CARD_CULTIVATION_REDUCTION_BP,
                minimum=MIN_CANWU_SECONDS,
            )

            sql = "UPDATE user_zt SET is_canwu = 1, cw_role = %s, cw_timestamp = %s, cw_duration = %s, cw_exp = %s WHERE id = %s"
            await cursor.execute(sql, (id, int(time.time()), duration, add_exp, uid))
            await conn.commit()
            from Game_main.g16_onboarding import record_onboarding_event
            await record_onboarding_event(uid, "CULTIVATION")
            from Game_main.g25_daily_tasks import record_daily_event
            await record_daily_event(uid, "CULTIVATION")

            output = f"##### 开始参悟\n\n"
            output += f"您已选择角色[{id}.{name}]参悟世界法则\n\n"
            output += f"**剩余参悟时间：** {duration}秒\n"
            output += (
                f"**聚灵阵快照：** Lv.{spirit_array_level}，"
                f"时长-{format_basis_points(reduction_bp)}%（本次已冻结）\n"
            )
            if monthly_card_active:
                output += "**月卡特权：** 悟道静室生效，本次参悟再缩短15%\n"
            output += f"**本次参悟可获得经验：** {add_exp}\n"

            kj = await all_write_command(uid, ("参悟状态", "当前角色", "领取参悟经验"))

            return {"type": "markdown", "content": output + kj}


# 参悟状态
@reg_xz_func
async def canwu_zt(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_canwu_duration_column(cursor)
            sql = "SELECT openid, is_canwu, cw_role, cw_timestamp, cw_duration, cw_exp FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            openid, is_canwu, cw_role, cw_timestamp, cw_duration, cw_exp = await cursor.fetchone()
            if is_canwu == 0:
                kj = await all_write_command(uid, ("参悟", "当前角色"))
                return {"type": "markdown", "content": qz + "您当前没有参悟中的角色。\n\n" + kj}

            current_timestamp = int(time.time())
            need_time = canwu_remaining_seconds(cw_timestamp, cw_duration, current_timestamp)
            cw_role_name = await role_id_to_name(cw_role)
            if need_time <= 0:
                output = f"##### 参悟完成\n\n"
                output += f"**参悟角色：** {cw_role}.{cw_role_name}\n"
                output += f"**本次参悟经验：** {cw_exp}\n\n"

                kj = await all_write_command(uid, ("参悟", "领取参悟经验"))

                return {"type": "markdown", "content": output + kj}
            output = "##### 参悟状态\n\n"
            output += f"**参悟角色：** {cw_role}.{cw_role_name}\n"
            output += f"**本次参悟可得经验：** {cw_exp}\n"
            output += f"**本次参悟剩余时间：** {need_time}秒\n"

            kj = await all_write_command(uid, ("参悟", "领取参悟经验", "当前角色"))

            return {"type": "markdown", "content": output + kj}


# 领取参悟经验
@reg_xz_func
async def canwu_lq_exp(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_canwu_duration_column(cursor)
            sql = "SELECT openid, is_canwu, cw_role, cw_timestamp, cw_duration, cw_exp FROM user_zt WHERE id = %s FOR UPDATE"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "##### 查询失败\n\n查询用户信息失败。"}

            openid, is_canwu, cw_role, cw_timestamp, cw_duration, cw_exp = result

            if is_canwu == 0:
                kj = await all_write_command(uid, (f"参悟", "当前角色"))
                return {"type": "markdown", "content": qz + "##### 无参悟角色\n\n您当前没有参悟中的角色。\n" + kj}

            current_timestamp = int(time.time())
            need_time = canwu_remaining_seconds(cw_timestamp, cw_duration, current_timestamp)

            sql = "SELECT `name`, dengji, exp FROM user_role WHERE id = %s FOR UPDATE"
            await cursor.execute(sql, (cw_role,))
            role_result = await cursor.fetchone()
            if role_result is None:
                return {"type": "markdown", "content": qz + "##### 角色数据异常\n\n参悟角色数据异常，可能角色已不存在。"}
            role_name, dengji, exp = role_result

            if need_time > 0:
                output = "##### 参悟未完成\n\n"
                output += "您当前角色未参悟完毕，无法领取参悟经验\n\n"
                output += f"**参悟角色：** {cw_role}.{role_name}\n"
                output += f"**本次参悟可得经验：** {cw_exp}\n"
                output += f"**本次参悟剩余时间：** {need_time}秒\n"

                kj = await all_write_command(uid, (f"角色属性 {cw_role}", "角色背包", "参悟状态"))

                return {"type": "markdown", "content": output + kj}

            max_exp = await up_need_exp(dengji)
            exp_result = await _apply_canwu_experience(
                cursor, cw_role, role_name, dengji, exp, cw_exp
            )
            await cursor.execute(
                """
                UPDATE user_zt
                SET is_canwu = 0, cw_role = 0, cw_timestamp = 0,
                    cw_duration = 0, cw_exp = 0
                WHERE id = %s AND is_canwu = 1 AND cw_role = %s
                """,
                (uid, cw_role),
            )
            if cursor.rowcount != 1:
                await conn.rollback()
                return {"type": "markdown", "content": "##### 操作失败\n\n参悟状态已变化，本次未扣除或发放任何奖励。"}
            if exp_result["level_up"]:
                from Tool.tool_power import update_role_power
                await update_role_power(conn, uid)

            # 经验、参悟状态与战力快照一起提交。
            await conn.commit()

            if exp_result["need_breakthrough"]:
                output = "##### 境界巅峰\n\n"
                output += "您当前参悟的角色已修至本阶至强，需进阶。\n\n"
                output += f"**本次参悟所获经验：** {cw_exp}\n"
                kj = await all_write_command(uid, (f"角色属性 {cw_role}", "悟道进阶"))
                return {"type": "markdown", "content": output + kj}

            if exp_result["level_up"]:
                output = "##### 升级成功\n\n"
                output += f"您当前参悟的角色已升级，当前等级：{dengji + 1}\n\n"
                output += f"**本次参悟所获经验：** {cw_exp}\n\n"
                output += "**升级所提升属性：**\n"
                output += f"> 攻击+{exp_result['add_gongji']}\n"
                output += f"> 防御+{exp_result['add_fangyu']}\n"
                output += f"> 气血+{exp_result['add_qixue']}\n"
                kj = await all_write_command(uid, (f"角色属性 {cw_role}", "参悟"))
                return {"type": "markdown", "content": output + kj}

            remaining_exp = max(0, max_exp - (exp + cw_exp))
            output = "##### 参悟完成\n\n"
            output += "当前角色已参悟完成\n\n"
            output += f"**本次参悟获得经验：** {cw_exp}\n"
            output += f"**距离升级所需经验：** {remaining_exp}\n\n"
            output += "**Tips：** 每日参悟次数不限，每次仅可参悟一名角色。\n"
            kj = await all_write_command(uid, (f"角色属性 {cw_role}", "参悟"))
            return {"type": "markdown", "content": output + kj}


