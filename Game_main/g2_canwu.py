from sql.mysql import *
from Tool.tool_user import *
from func.pd_func import *
import time
import random
from Tool.tool_command import *


# 参悟
@reg_xz_func
async def canwu_role(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name`, dengji, exp FROM user_role WHERE uid = %s and is_chuzhan = 1 limit 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您当前未出战角色，无法选择使其参悟世界法则。"}
            id, name, dengji, exp = result
            sql = "SELECT is_canwu, cw_role, cw_timestamp, openid FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            is_canwu, cw_role, cw_timestamp, openid = await cursor.fetchone()
            if is_canwu != 0:
                current_timestamp = int(time.time())
                ts = current_timestamp - cw_timestamp
                sql = "SELECT id, `name` FROM user_role WHERE id = %s limit 1"
                await cursor.execute(sql, (cw_role,))
                result = await cursor.fetchone()
                cw_role, cw_name = result
                if ts < 1200:
                    needtime = 1200 - ts

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

            sql = "UPDATE user_zt SET is_canwu = 1, cw_role = %s, cw_timestamp = %s, cw_exp = %s WHERE id = %s"
            await cursor.execute(sql, (id, int(time.time()), add_exp, uid))
            await conn.commit()

            output = f"##### 开始参悟\n\n"
            output += f"您已选择角色[{id}.{name}]参悟世界法则\n\n"
            output += f"**剩余参悟时间：** 1200秒\n"
            output += f"**本次参悟可获得经验：** {add_exp}\n"

            kj = await all_write_command(uid, ("参悟状态", "当前角色", "领取参悟经验"))

            return {"type": "markdown", "content": output + kj}


# 参悟状态
@reg_xz_func
async def canwu_zt(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT openid, is_canwu, cw_role, cw_timestamp, cw_exp FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            openid, is_canwu, cw_role, cw_timestamp, cw_exp = await cursor.fetchone()
            if is_canwu == 0:
                kj = await all_write_command(uid, ("参悟", "当前角色"))
                return {"type": "markdown", "content": qz + "您当前没有参悟中的角色。\n\n" + kj}

            current_timestamp = int(time.time())
            ts = current_timestamp - cw_timestamp
            cw_role_name = await role_id_to_name(cw_role)
            if (1200 - ts) <= 0:
                output = f"##### 参悟完成\n\n"
                output += f"**参悟角色：** {cw_role}.{cw_role_name}\n"
                output += f"**本次参悟经验：** {cw_exp}\n\n"

                kj = await all_write_command(uid, ("参悟", "领取参悟经验"))

                return {"type": "markdown", "content": output + kj}
            need_time = 1200 - ts
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
            sql = "SELECT openid, is_canwu, cw_role, cw_timestamp, cw_exp FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "##### 查询失败\n\n查询用户信息失败。"}
                
            openid, is_canwu, cw_role, cw_timestamp, cw_exp = result
            
            if is_canwu == 0:
                kj = await all_write_command(uid, (f"参悟", "当前角色"))
                return {"type": "markdown", "content": qz + "##### 无参悟角色\n\n您当前没有参悟中的角色。\n" + kj}

            current_timestamp = int(time.time())
            ts = current_timestamp - cw_timestamp

            sql = "SELECT `name`, dengji, exp FROM user_role WHERE id = %s"
            await cursor.execute(sql, (cw_role,))
            role_result = await cursor.fetchone()
            if role_result is None:
                 return {"type": "markdown", "content": qz + "##### 角色数据异常\n\n参悟角色数据异常，可能角色已不存在。"}
            role_name, dengji, exp = role_result

            if (1200 - ts) > 0:
                need_time = 1200 - ts
                if need_time < 0:
                    need_time = 0
                output = "##### 参悟未完成\n\n"
                output += "您当前角色未参悟完毕，无法领取参悟经验\n\n"
                output += f"**参悟角色：** {cw_role}.{role_name}\n"
                output += f"**本次参悟可得经验：** {cw_exp}\n"
                output += f"**本次参悟剩余时间：** {need_time}秒\n"

                kj = await all_write_command(uid, (f"角色属性 {cw_role}", "角色背包", "参悟状态"))

                return {"type": "markdown", "content": output + kj}

            # === 并发控制核心修改 ===
            # 使用原子操作尝试更新状态，充当乐观锁
            # 只有成功将 is_canwu 从 1 更新为 0 的请求，才有资格发放奖励
            sql_lock = "UPDATE user_zt SET is_canwu = 0, cw_role = 0, cw_timestamp = 0 WHERE id = %s AND is_canwu = 1"
            await cursor.execute(sql_lock, (uid,))
            
            if cursor.rowcount == 0:
                # 抢锁失败，说明已经被并发请求领取过，或者状态已变更
                return {"type": "markdown", "content": "##### 操作失败\n\n操作失败：奖励可能已被领取或参悟状态已失效。"}
            
            await conn.commit()
            # ========================

            max_exp = await up_need_exp(dengji)
            if exp + cw_exp > max_exp:
                if dengji in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
                    sql = "UPDATE user_role SET exp = exp + %s WHERE id = %s"
                    await cursor.execute(sql, (cw_exp, cw_role))
                    await conn.commit()

                    output = f"##### 境界巅峰\n\n"
                    output += f"您当前参悟的角色已修至本阶至强，需进阶。\n\n"
                    output += f"**本次参悟所获经验：** {cw_exp}\n"

                    kj = await all_write_command(uid, (f"角色属性 {cw_role}", "悟道进阶"))
                    return {"type": "markdown", "content": output + kj}
                else:
                    add_gongji, add_fangyu, add_qixue = await up_lvl(cw_role, cw_exp)
                    output = f"##### 升级成功\n\n"
                    output += f"您当前参悟的角色已升级，当前等级：{dengji + 1}\n\n"
                    output += f"**本次参悟所获经验：** {cw_exp}\n\n"
                    output += "**升级所提升属性：**\n"
                    output += f"> 攻击+{add_gongji}\n"
                    output += f"> 防御+{add_fangyu}\n"
                    output += f"> 气血+{add_qixue}\n"

                    kj = await all_write_command(uid, (f"角色属性 {cw_role}", "参悟"))

                    return {"type": "markdown", "content": output + kj}
            else:
                sql = "UPDATE user_role SET exp = exp + %s WHERE id = %s LIMIT 1"
                await cursor.execute(sql, (cw_exp, cw_role))
                await conn.commit()

                remaining_exp = max_exp - (exp + cw_exp)
                output = f"##### 参悟完成\n\n"
                output += f"当前角色已参悟完成\n\n"
                output += f"**本次参悟获得经验：** {cw_exp}\n"
                output += f"**距离升级所需经验：** {remaining_exp}\n\n"
                output += "**Tips：** 每日参悟次数不限，每次仅可参悟一名角色。\n"

                kj = await all_write_command(uid, (f"角色属性 {cw_role}", "参悟"))

                return {"type": "markdown", "content": output + kj}


