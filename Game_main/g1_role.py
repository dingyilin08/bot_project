from sql.mysql import *
from Tool.tool_user import *
from func.pd_func import *
from config import IMG_BASE_URL
import time
import random
from Tool.tool_command import *
from Game_main.g7_equip import calc_role_equip_bonus


# 注册游戏
async def user_zhuce(openid, player_name):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            line = []
            if await openid_is_zhuce(openid) is True:
                line.append(f"您已注册过本游戏，请勿重复注册！感谢您对本游戏的支持~")
                line.append("<qqbot-cmd-input text='选择角色 ' show='选择角色' /> | <qqbot-cmd-input text='角色介绍 ' show='角色介绍*' />")
                return {"type": "markdown", "content": "\n".join(line)}
            if player_name == "":
                line.append(f"指令错误，正确指令：注册游戏 苍穹")
                line.append("<qqbot-cmd-input text='注册游戏' show='注册游戏' /> | <qqbot-cmd-enter text='主菜单' />")
                return {"type": "markdown", "content": "\n".join(line)}
            if len(player_name) > 8 or len(player_name) < 1:
                line.append(f"注意！！玩家名称长度需要在1-8个字符之间噢~")
                line.append('<qqbot-cmd-input text="注册游戏" show="注册游戏" /> | <qqbot-cmd-enter text="主菜单" />')
                return {"type": "markdown", "content": "\n".join(line)}
            sql = "SELECT COUNT(*) FROM user_zt"
            await cursor.execute(sql)
            result = await cursor.fetchone()
            uid = result[0] + 100000 + 1
            sql = "INSERT INTO user_zt (id, openid, `name`, is_chushi) VALUES (%s, %s, %s, 0)"
            await cursor.execute(sql, (uid, openid, player_name))
            await conn.commit()
            line.append("##### 注册成功！")
            line.append(f"**您的UID：** {uid}")
            line.append(f"**待选角色：**")
            line.append("◇ <qqbot-cmd-enter text='角色介绍 萧炎' />：异火焚天/斗帝传承")
            line.append("◇ <qqbot-cmd-enter text='角色介绍 王林' />：禁制大师/生死轮回")
            line.append("◇ <qqbot-cmd-enter text='角色介绍 韩立' />：掌天瓶主/遁术无双")
            line.append("◇ <qqbot-cmd-enter text='角色介绍 石昊' />：独断万古/至尊骨")
            line.append("◇ <qqbot-cmd-enter text='角色介绍 叶凡' />：圣体无双/九秘传承")
            line.append("◇ <qqbot-cmd-enter text='角色介绍 孟川' />：刀意通神/雷霆灭世")
            line.append("> 点击蓝字可查看详细的角色介绍噢~")
            line.append("")
            line.append("> Tips：角色选择后不可更换，后期可通过碎片合成其他待选角色")
            line.append("***")
            line.append("<qqbot-cmd-input text='选择角色 ' show='选择角色*' /> | <qqbot-cmd-input text='角色介绍 ' show='角色介绍*' />")

            return {"type": "markdown", "content": "\n".join(line)}


# 选择角色
@pd_reg_func
async def select_role(uid, qz, role_name):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            line = []
            sql = "SELECT `name`, gongji, fangyu, qixue, sudu, baoji, baoshang, max_fali, shanbi, mingzhong, pofang, xixue, world FROM data_role WHERE `name` = %s limit 1"
            await cursor.execute(sql, (role_name,))
            result = await cursor.fetchone()
            if result is None:
                line.append(f"你想选择的角色不存在！如果没有自己喜欢的角色，可以私信群主后续可能会一一添加噢~")
                line.append(f"当前可选择的角色有：")
                line.append("◇ <qqbot-cmd-enter text='角色介绍 萧炎' />：异火焚天/斗帝传承")
                line.append("◇ <qqbot-cmd-enter text='角色介绍 王林' />：禁制大师/生死轮回")
                line.append("◇ <qqbot-cmd-enter text='角色介绍 韩立' />：掌天瓶主/遁术无双")
                line.append("◇ <qqbot-cmd-enter text='角色介绍 石昊' />：独断万古/至尊骨")
                line.append("◇ <qqbot-cmd-enter text='角色介绍 叶凡' />：圣体无双/九秘传承")
                line.append("◇ <qqbot-cmd-enter text='角色介绍 孟川' />：刀意通神/雷霆灭世")
                line.append("> 点击蓝字可查看详细的角色介绍噢~")
                line.append("<qqbot-cmd-input text='选择角色 ' show='选择角色' /> | <qqbot-cmd-input text='角色介绍 ' show='角色介绍*' />")
                return {"type": "markdown", "content": "\n".join(line)}
            role_name, gongji, fangyu, qixue, sudu, baoji, baoshang, max_fali, shanbi, mingzhong, pofang, xixue, world = result

            # 判断是否已选择角色
            sql = "SELECT openid, is_chushi FROM user_zt WHERE id = %s limit 1"
            await cursor.execute(sql, (uid,))
            openid, is_chushi = await cursor.fetchone()
            if is_chushi == 1:
                line.append(f"您已选择过角色啦，请勿重复选择！")
                line.append(f"不知道怎么玩？可以尝试发送：<qqbot-cmd-enter text='主菜单' />查看可用指令")
                line.append("<qqbot-cmd-enter text='查看本源' /> | <qqbot-cmd-enter text='副本列表' /> | <qqbot-cmd-enter text='参悟' />")
                return {"type": "markdown", "content": "\n".join(line)}
            # 获取角色本源编号 并插入数据
            sql = "SELECT COUNT(*) FROM user_benyuan"
            await cursor.execute(sql)
            result = await cursor.fetchone()
            by_id = result[0] + 1
            sql = "SELECT `name` FROM data_benyuan WHERE role_name = %s LIMIT 1"
            await cursor.execute(sql, (role_name,))
            by_name = await cursor.fetchone()
            by_name = by_name[0]
            sql = "INSERT INTO user_benyuan (id, uid, `name`, dengji) VALUES (%s, %s, %s, %s)"
            await cursor.execute(sql, (by_id, uid, by_name, 1))
            await conn.commit()
            # 获取角色编号
            sql = "SELECT COUNT(*) FROM user_role"
            await cursor.execute(sql)
            result = await cursor.fetchone()
            role_id = result[0] + 10000 + 1
            # 插入角色数据
            stage = await role_stage(role_name, 1)
            sql = "INSERT INTO user_role (id, uid, `name`, dengji, exp, stage, gongji, fangyu, qixue, sudu, baoji, baoshang, fali, shanbi, mingzhong, pofang, xixue, world, by_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            await cursor.execute(sql, (role_id, uid, role_name, 1, 0, stage, gongji, fangyu, qixue, sudu, baoji, baoshang, max_fali, shanbi, mingzhong, pofang, xixue, world, by_id))
            await conn.commit()

            # 将是否选择初始角色置1
            sql = "UPDATE user_zt SET is_chushi = 1 WHERE id = %s"
            await cursor.execute(sql, (uid,))
            await conn.commit()

            need_exp = await up_need_exp(1)
            output = f"##### 选择成功！\n\n"
            output += f"**角色编号：** {role_id}\n"
            output += f"**名称：** {role_name}\n"
            output += f"**境界：** {stage}\n"
            output += f"**等级：** 1级\n"
            output += f"**经验：** 0/{need_exp}\n\n"
            output += "**基础属性：**\n"
            output += f"> 气血：{qixue} | 攻击：{gongji} | 防御：{fangyu}\n"
            output += f"> 速度：{sudu}\n"
            output += f"> 暴击：{round((baoji / 100), 2)}% | 暴击伤害：{round((baoshang / 100), 2)}%\n"
            output += f"> 闪避：{round((shanbi / 100), 2)}% | 命中：{round((mingzhong / 100), 2)}%\n"
            output += f"> 破防：{round((pofang / 100), 2)}% | 吸血：{round((xixue / 100), 2)}%\n"
            output += f"> 法力上限：{max_fali}\n"
            output += "**技能：** 未装备"

            kj = await all_write_command(uid, (f"出战{role_id}", "角色背包", "查看本源"))

            return {"type": "markdown", "content": output + kj}


# 角色介绍
@pd_reg_func
async def role_info(uid, qz, role_name):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT `name`, gongji, fangyu, qixue, sudu, baoji, baoshang, max_fali, shanbi, mingzhong, pofang, xixue, world FROM data_role WHERE `name` = %s limit 1"
            await cursor.execute(sql, (role_name,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "角色不存在，请重新输入！\n\n示例：角色介绍 萧炎"}
            role_name, gongji, fangyu, qixue, sudu, baoji, baoshang, max_fali, shanbi, mingzhong, pofang, xixue, world = result

            if role_name == '萧炎':
                image = f"![text #204px #117px]({IMG_BASE_URL}/xiaoyan.png)"
            elif role_name == '王林':
                image = f"![text #472px #308px]({IMG_BASE_URL}/wanglin.png)"
            elif role_name == '韩立':
                image = f"![text #384px #216px]({IMG_BASE_URL}/hanli.png)"
            elif role_name == '石昊':
                image = f"![text #113px #66px]({IMG_BASE_URL}/shihao.png)"
            elif role_name == '叶凡':
                image = f"![text #108px #60px]({IMG_BASE_URL}/yefan.png)"
            elif role_name == '孟川':
                image = f"![text #108px #60px]({IMG_BASE_URL}/mengchuan.png)"

            output = f"##### 角色[{role_name}]基础信息\n\n"
            output += f"{image}\n"
            output += f"***\n"
            output += "**属性：**\n"
            output += f"> 气血：{qixue} | 攻击：{gongji} | 防御：{fangyu}\n"
            output += f"> 速度：{sudu}\n"
            output += f"> 暴击：{round((baoji / 100), 1)}% | 暴击伤害：{round((baoshang / 100), 1)}%\n"
            output += f"> 闪避：{round((shanbi / 100), 1)}% | 命中：{round((mingzhong / 100), 1)}%\n"
            output += f"> 破防：{round((pofang / 100), 1)}% | 吸血：{round((xixue / 100), 1)}%\n"
            output += f"> 法力上限：{max_fali}\n\n"
            output += "***\n"
            output += f"<qqbot-cmd-enter text='选择角色 {role_name}' />\n"

            return {"type": "markdown", "content": output}


# 角色属性
@reg_xz_func
async def role_attr(uid, qz, role_id):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name`, stage, dengji, exp, gongji, gongji_jc, fangyu, fangyu_jc, qixue, qixue_jc, fali, sudu, baoji, baoshang, shanbi, mingzhong, pofang, xixue, skill1_id, skill2_id, skill3_id FROM user_role WHERE uid = %s and id = %s"
            await cursor.execute(sql, (uid, role_id))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "角色不存在，请重新输入！\n\n示例：角色属性 角色编号"}
            role_id, role_name, stage, dengji, exp, gongji, gongji_jc, fangyu, fangyu_jc, qixue, qixue_jc, fali, sudu, baoji, baoshang, shanbi, mingzhong, pofang, xixue, skill1_id, skill2_id, skill3_id = result

            skill_1 = await get_skill_name(cursor, skill1_id) if skill1_id is not None else "未装备"
            skill_2 = await get_skill_name(cursor, skill2_id) if skill2_id is not None else "未装备"
            skill_3 = await get_skill_name(cursor, skill3_id) if skill3_id is not None else "未装备"

            max_exp = await up_need_exp(dengji)
            stage = await role_stage(role_name, dengji)

            jc_gongji = int(gongji * (gongji_jc / 100))
            jc_fangyu = int(fangyu * (fangyu_jc / 100))
            jc_qixue = int(qixue * (qixue_jc / 100))

            # 计算装备加成
            equip_bonus = await calc_role_equip_bonus(role_id)

            # 最终属性 = 基础 + 本源加成 + 装备加成
            final_gongji = gongji + jc_gongji + equip_bonus.get('gongji', 0)
            final_fangyu = fangyu + jc_fangyu + equip_bonus.get('fangyu', 0)
            final_qixue = qixue + jc_qixue + equip_bonus.get('qixue', 0)
            final_fali = fali + equip_bonus.get('fali', 0)
            final_sudu = sudu + equip_bonus.get('sudu', 0)
            final_baoji = baoji + equip_bonus.get('baoji', 0)
            final_baoshang = baoshang + equip_bonus.get('baoshang', 0)
            final_shanbi = shanbi + equip_bonus.get('shanbi', 0)
            final_mingzhong = mingzhong + equip_bonus.get('mingzhong', 0)
            final_pofang = pofang + equip_bonus.get('pofang', 0)
            final_xixue = xixue + equip_bonus.get('xixue', 0)

            if role_name == '萧炎':
                image = f"![text #204px #117px]({IMG_BASE_URL}/xiaoyan.png)"
            elif role_name == '王林':
                image = f"![text #472px #308px]({IMG_BASE_URL}/wanglin.png)"
            elif role_name == '韩立':
                image = f"![text #384px #216px]({IMG_BASE_URL}/hanli.png)"
            elif role_name == '石昊':
                image = f"![text #113px #66px]({IMG_BASE_URL}/shihao.png)"
            elif role_name == '叶凡':
                image = f"![text #108px #60px]({IMG_BASE_URL}/yefan.png)"
            elif role_name == '孟川':
                image = f"![text #108px #60px]({IMG_BASE_URL}/mengchuan.png)"

            output = f"##### [{role_id}.{role_name}]属性\n\n"
            output += f"**境界：** {stage} | **等级：** {dengji}\n"
            output += f"**经验：** {exp}/{max_exp}\n\n"
            output += image
            output += "***"
            output += "**角色属性：**\n"
            output += f"> 气血：{final_qixue} | 法力：{final_fali}\n"
            output += f"> 攻击：{final_gongji} | 防御：{final_fangyu}\n"
            output += f"> 速度：{final_sudu}\n"
            output += f"> 暴击：{round((final_baoji / 100), 2)}% | 暴击伤害：{round((final_baoshang / 100), 2)}%\n"
            output += f"> 闪避：{round((final_shanbi / 100), 2)}% | 命中：{round((final_mingzhong / 100), 2)}%\n"
            output += f"> 破防：{round((final_pofang / 100), 2)}% | 吸血：{round((final_xixue / 100), 2)}%\n\n"
            output += "**技能：**\n"
            output += f"> 1.{skill_1}\n"
            output += f"> 2.{skill_2}\n"
            output += f"> 3.{skill_3}\n"

            kj = await all_write_command(uid, (f"出战{role_id}", "参悟", "角色背包", "悟道进阶"))

            return {"type": "markdown", "content": output + kj}


# 当前角色
@reg_xz_func
async def cz_role_attr(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name`, stage, dengji, exp, gongji, gongji_jc, fangyu, fangyu_jc, qixue, qixue_jc, fali, sudu, baoji, baoshang, shanbi, mingzhong, pofang, xixue, skill1_id, skill2_id, skill3_id FROM user_role WHERE uid = %s and is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid, ))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "当前没有出战角色，请先选择角色出战！"}
            role_id, role_name, stage, dengji, exp, gongji, gongji_jc, fangyu, fangyu_jc, qixue, qixue_jc, fali, sudu, baoji, baoshang, shanbi, mingzhong, pofang, xixue, skill1_id, skill2_id, skill3_id = result

            skill_1 = await get_skill_name(cursor, skill1_id) if skill1_id is not None else "未装备"
            skill_2 = await get_skill_name(cursor, skill2_id) if skill2_id is not None else "未装备"
            skill_3 = await get_skill_name(cursor, skill3_id) if skill3_id is not None else "未装备"

            max_exp = await up_need_exp(dengji)
            stage = await role_stage(role_name, dengji)

            jc_gongji = int(gongji * (gongji_jc / 100))
            jc_fangyu = int(fangyu * (fangyu_jc / 100))
            jc_qixue = int(qixue * (qixue_jc / 100))

            # 计算装备加成
            equip_bonus = await calc_role_equip_bonus(role_id)

            # 最终属性 = 基础 + 本源加成 + 装备加成
            final_gongji = gongji + jc_gongji + equip_bonus.get('gongji', 0)
            final_fangyu = fangyu + jc_fangyu + equip_bonus.get('fangyu', 0)
            final_qixue = qixue + jc_qixue + equip_bonus.get('qixue', 0)
            final_fali = fali + equip_bonus.get('fali', 0)
            final_sudu = sudu + equip_bonus.get('sudu', 0)
            final_baoji = baoji + equip_bonus.get('baoji', 0)
            final_baoshang = baoshang + equip_bonus.get('baoshang', 0)
            final_shanbi = shanbi + equip_bonus.get('shanbi', 0)
            final_mingzhong = mingzhong + equip_bonus.get('mingzhong', 0)
            final_pofang = pofang + equip_bonus.get('pofang', 0)
            final_xixue = xixue + equip_bonus.get('xixue', 0)

            if role_name == '萧炎':
                image = f"![text #204px #117px]({IMG_BASE_URL}/xiaoyan.png)"
            elif role_name == '王林':
                image = f"![text #472px #308px]({IMG_BASE_URL}/wanglin.png)"
            elif role_name == '韩立':
                image = f"![text #384px #216px]({IMG_BASE_URL}/hanli.png)"
            elif role_name == '石昊':
                image = f"![text #113px #66px]({IMG_BASE_URL}/shihao.png)"
            elif role_name == '叶凡':
                image = f"![text #108px #60px]({IMG_BASE_URL}/yefan.png)"
            elif role_name == '孟川':
                image = f"![text #108px #60px]({IMG_BASE_URL}/mengchuan.png)"

            output = f"##### [{role_id}.{role_name}]属性\n\n"
            output += f"**境界：** {stage} | **等级：** {dengji}\n"
            output += f"**经验：** {exp}/{max_exp}\n\n"
            output += image
            output += "\n***\n"
            output += "**角色属性：**\n"
            output += f"> 气血：{final_qixue} | 法力：{final_fali}\n"
            output += f"> 攻击：{final_gongji} | 防御：{final_fangyu}\n"
            output += f"> 速度：{final_sudu}\n"
            output += f"> 暴击：{round((final_baoji / 100), 2)}% | 暴击伤害：{round((final_baoshang / 100), 2)}%\n"
            output += f"> 闪避：{round((final_shanbi / 100), 2)}% | 命中：{round((final_mingzhong / 100), 2)}%\n"
            output += f"> 破防：{round((final_pofang / 100), 2)}% | 吸血：{round((final_xixue / 100), 2)}%\n\n"
            output += "**技能：**\n"
            output += f"> 1.{skill_1}\n"
            output += f"> 2.{skill_2}\n"
            output += f"> 3.{skill_3}\n"

            kj = await all_write_command(uid, ("收回", "参悟", "角色背包", "悟道进阶", "查看本源"))

            return {"type": "markdown", "content": output + kj}


# 出战
@reg_xz_func
async def cz_role(uid, qz, role_id):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name` FROM user_role WHERE uid = %s and is_chuzhan = 1"
            await cursor.execute(sql, (uid, ))
            result = await cursor.fetchone()
            output = ""
            if result is not None:
                id, name = result
                if id == role_id:
                    return {"type": "markdown", "content": qz + "此角色当前已出战，无需重复出战。"}
                sql = "UPDATE user_role SET is_chuzhan = 0 WHERE id = %s"
                await cursor.execute(sql, (id,))
                await conn.commit()
                output += f"检测到您已有出战角色[{id}.{name}]，已自动将其收回。\n\n"
            sql = "SELECT id, name, world FROM user_role WHERE uid = %s and id = %s"
            await cursor.execute(sql, (uid, role_id))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您没有此角色，请输入正确的角色编号！\n\n示例：出战 10001"}
            role_id, role_name, role_world = result
            sql = "UPDATE user_role SET is_chuzhan = 1 WHERE id = %s"
            await cursor.execute(sql, (role_id,))
            await conn.commit()

            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)

            output += f"##### 出战成功\n"
            output += f"[{role_id}.{role_name}]已出战！\n"
            output += f"**克制世界：** 《{role_world}》"

            kj = await all_write_command(uid, ("收回", "参悟", "悟道进阶", "查看本源"))

            return {"type": "markdown", "content": output + kj}


# 收回
@reg_xz_func
async def sh_role(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name` FROM user_role WHERE uid = %s and is_chuzhan = 1"
            await cursor.execute(sql, (uid, ))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您没有出战角色，无需收回！"}
            role_id, name = result
            sql = "UPDATE user_role SET is_chuzhan = 0 WHERE id = %s"
            await cursor.execute(sql, (role_id,))
            await conn.commit()
            output = f"##### 收回成功\n\n[{role_id}.{name}]已收回！"

            kj = await all_write_command(uid, (f"出战 {role_id}", f"角色属性 {role_id}", "角色背包"))

            return {"type": "markdown", "content": output + kj}


# 悟道进阶
@reg_xz_func
async def jinjie_role(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name`, dengji, exp FROM user_role WHERE uid = %s and is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid, ))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您当前没有出战角色，无法悟道！\n\n请先选择角色出战。"}
            role_id, role_name, dengji, exp = result
            max_exp = await up_need_exp(dengji)
            if dengji not in [10, 20, 30, 40, 50, 60, 70, 80, 90]:
                return {"type": "markdown", "content": qz + "您所出战的角色暂未到达需悟道等级，请继续参悟这世界法则吧~"}
            elif exp < max_exp:
                return {"type": "markdown", "content": qz + "您所出战的角色经验未至经验值上限，无需悟道进阶。"}

            # 破境系统：检查是否需要破境丹
            stage_num = dengji // 10  # 当前境界编号（1-9）
            next_stage_num = stage_num + 1  # 下一境界编号

            # 获取角色信息和世界简称
            sql = "SELECT id, world FROM data_role WHERE `name` = %s LIMIT 1"
            await cursor.execute(sql, (role_name,))
            role_data = await cursor.fetchone()
            if role_data is None:
                return {"type": "markdown", "content": qz + "角色数据异常，请联系管理员。"}

            role_db_id, world = role_data

            # 根据世界确定简称
            world_abbr_map = {
                '斗破苍穹': '穹',
                '仙逆': '逆',
                '凡人修仙传': '凡',
                '完美世界': '界',
                '遮天': '天',
                '沧元图': '沧'
            }
            world_abbr = world_abbr_map.get(world, '')

            # 获取下一境界名称
            next_stage_id = f"stage_{next_stage_num}"
            sql = f"SELECT {next_stage_id} FROM data_stage WHERE id = %s"
            await cursor.execute(sql, (role_db_id,))
            stage_result = await cursor.fetchone()
            if stage_result is None or stage_result[0] is None:
                return {"type": "markdown", "content": qz + "境界数据异常，请联系管理员。"}
            next_stage_name = stage_result[0]

            # 构建破境丹名称
            pojing_dan_name = f"[{world_abbr}]{next_stage_name}破境丹"

            # 查询破境丹物品ID
            sql = "SELECT id FROM data_item WHERE `name` = %s LIMIT 1"
            await cursor.execute(sql, (pojing_dan_name,))
            pojing_dan_result = await cursor.fetchone()

            if pojing_dan_result is None:
                return {"type": "markdown", "content": qz + f"破境丹数据异常（{pojing_dan_name}），请联系管理员。"}

            pojing_dan_id = pojing_dan_result[0]

            # 检查玩家是否有破境丹
            has_pojing_dan = await pd_bag_num(uid, pojing_dan_id, 1)

            if not has_pojing_dan:
                old_stage = await role_stage(role_name, dengji)
                output = f"##### 需要破境丹\n\n"
                output += f"您所出战的角色已至 **{dengji}级[{old_stage}]境巅峰**\n\n"
                output += f"欲突破至下一境界，需服用 **【{pojing_dan_name}】** 方可破境成功！\n\n"
                output += "该丹药可通过挑战对应世界副本概率获得。\n"
                return {"type": "markdown", "content": output}

            # 扣除破境丹
            await cut_bag_item(uid, pojing_dan_id, 1)

            # 计算剩余经验（破境后经验不断累计，不清空）
            remaining_exp = exp - max_exp  # 计算溢出的经验
            if remaining_exp < 0:
                remaining_exp = 0

            old_stage = await role_stage(role_name, dengji)

            aaa = ""
            base_prob = 100 - (dengji // 10) * 10
            if await pd_bag_num(uid, 1, 1):
                await cut_bag_item(uid, 1, 1)
                base_prob += 50
                aaa = "> 检测到您背包中有[悟道天书]，已自动抵扣，提升悟道概率\n"
            base_prob = min(base_prob, 100)
            r = random.randint(1, 100)

            if r <= base_prob:
                output = "##### 悟道失败\n\n"
                output += "一阵雷云环绕周身，只见你孱弱的身影浮现，本次悟道失败\n\n"
                output += aaa
                output += f"> 已使用【{pojing_dan_name}】，但悟道失败，破境丹已消耗。\n"
                output += f"> 本次悟道成功概率：{base_prob}%\n"
                output += f"> 角色当前等级境界：{dengji}级 [{old_stage}]\n\n"
                output += "**Tips：** 悟道概率随等级提升而变化。[悟道天书]可助你提升悟道概率！\n"
                # 失败时保留当前经验（不清空）
                sql = "UPDATE user_role SET exp = %s WHERE uid = %s and id = %s LIMIT 1"
                await cursor.execute(sql, (exp, uid, role_id))
                await conn.commit()
                return {"type": "markdown", "content": output}

            sql = "SELECT `name`, gongji, fangyu, qixue, sudu, baoji, baoshang FROM data_role WHERE `name` = %s LIMIT 1"
            await cursor.execute(sql, (role_name, ))
            name, gongji, fangyu, qixue, sudu, baoji, baoshang = await cursor.fetchone()
            add_gongji = int(gongji * 0.03)
            add_fangyu = int(fangyu * 0.02)
            add_qixue = int(qixue * 0.02)
            add_baoji = 20
            add_baoshang = 20
            # 破境成功：经验累计到下一境界（不清空）
            sql = "UPDATE user_role SET dengji = dengji + 1, exp = %s, gongji = gongji + %s, fangyu = fangyu + %s, qixue = qixue + %s, baoji = baoji + %s, baoshang = baoshang + %s WHERE uid = %s and id = %s"
            await cursor.execute(sql, (remaining_exp, add_gongji, add_fangyu, add_qixue, add_baoji, add_baoshang, uid, role_id))
            await conn.commit()
            stage = await role_stage(role_name, dengji + 1)
            output = "##### 破境成功！\n\n"
            output += "只见其周身泛起赤金光芒，三百六十处窍穴齐鸣，破境成功！\n\n"
            output += aaa
            output += f"> 已使用【{pojing_dan_name}】成功突破境界\n"
            output += f"> 本次悟道成功概率：{base_prob}%\n"
            output += f"> 角色境界提升：{old_stage} -> {stage}\n"
            output += f"> 破境后累计经验：{remaining_exp}\n\n"
            output += "**属性提升：**\n"
            output += f"> 攻击+{add_gongji} | 防御+{add_fangyu}\n"
            output += f"> 气血+{add_qixue}\n"
            output += f"> 暴击率+{add_baoji}% | 暴击伤害+{add_baoshang}%\n\n"
            output += "**Tips：** 悟道概率随等级提升而变化。[悟道天书]可助你提升悟道概率！"

            kj = await all_write_command(uid, ("当前角色", "角色背包", "行囊"))

            return {"type": "markdown", "content": output + kj}


# 角色背包
@reg_xz_func
async def role_bag(uid, qz, page_num=1):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            try:
                page_num = int(page_num)
            except ValueError:
                return {"type": "markdown", "content": qz + "请输入正确的背包页码。"}

            if page_num < 1:
                page_num = 1

            page_size = 9
            offset = (page_num - 1) * page_size
            sql = "SELECT id, `name`, dengji FROM user_role WHERE uid = %s and is_chuzhan = 0 LIMIT %s OFFSET %s"
            await cursor.execute(sql, (uid, page_size, offset))
            result = await cursor.fetchall()
            if result == ():
                return {"type": "markdown", "content": qz + "你的背包中暂无空闲角色！"}

            count_sql = "SELECT COUNT(*) FROM user_role WHERE uid = %s"
            await cursor.execute(count_sql, (uid,))
            a = await cursor.fetchone()
            total_records = a[0]
            total_pages = (total_records + page_size - 1) // page_size

            output = f"##### 角色背包({page_num}/{total_pages})\n"
            for i in result:
                role_id, role_name, dengji = i
                stage = await role_stage(role_name, dengji)
                role_button = f"<qqbot-cmd-enter text='角色属性 {role_id}' />"
                output += f"「{role_id}」 {role_button} Lv.{dengji}[{stage}]\n"

            output += f"***\n"

            sql = "SELECT lingshi, xianyu FROM user_zt WHERE id = %s LIMIT 1"
            await cursor.execute(sql, (uid,))
            lingshi, xianyu = await cursor.fetchone()
            output += f"**灵石：** {lingshi}\n**仙玉：** {xianyu}\n"

            output += f"***\n"

            output += f"<qqbot-cmd-enter text='角色背包 {page_num - 1}' /> | <qqbot-cmd-input text='角色背包 ' show='跳转【页数】' /> |<qqbot-cmd-enter text='角色背包 {page_num + 1}' />"

            kj = await all_write_command(uid, (f"出战", "物品背包", "当前角色"))

            return {"type": "markdown", "content": output + kj}


# 物品背包
@reg_xz_func
async def item_bag(uid, qz, page_num=1):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            try:
                page_num = int(page_num)
            except ValueError:
                return {"type": "markdown", "content": qz + "请输入正确的背包页码。"}

            if page_num < 1:
                page_num = 1

            page_size = 9
            offset = (page_num - 1) * page_size
            sql = "SELECT item_id, item_num FROM user_item WHERE uid = %s LIMIT %s OFFSET %s"
            await cursor.execute(sql, (uid, page_size, offset))
            result = await cursor.fetchall()
            if result == ():
                return {"type": "markdown", "content": qz + "你的物品背包中暂无物品！"}

            count_sql = "SELECT COUNT(*) FROM user_item WHERE uid = %s"
            await cursor.execute(count_sql, (uid,))
            a = await cursor.fetchone()
            total_records = a[0]
            total_pages = (total_records + page_size - 1) // page_size

            output = f"##### 物品背包({page_num}/{total_pages}页)\n\n"

            for i in result:
                item_id, item_num = i
                # 1=药材2=材料3=道具4=丹药
                sql = "SELECT `name`, `type` FROM data_item WHERE id = %s LIMIT 1"
                await cursor.execute(sql, (item_id,))
                item_name, item_type = await cursor.fetchone()
                if item_type == 1:
                    item_type = "药材"
                elif item_type == 2:
                    item_type = "材料"
                elif item_type == 3:
                    item_type = "道具"
                elif item_type == 4:
                    item_type = "丹药"
                item_button = f"<qqbot-cmd-enter text='物品信息 {item_name}' />"
                output += f"〔{item_type}〕{item_button}×{item_num}\n"

            output += f"> 点击蓝字可查看物品信息噢~\n"
            output += f"***\n"

            sql = "SELECT lingshi, xianyu FROM user_zt WHERE id = %s LIMIT 1"
            await cursor.execute(sql, (uid,))
            lingshi, xianyu = await cursor.fetchone()
            output += f"**灵石：** {lingshi}\n**仙玉：** {xianyu}\n"

            output += f"<qqbot-cmd-enter text='物品背包 {page_num - 1}' /> | <qqbot-cmd-input text='物品背包 ' show='跳转【页数】' /> |<qqbot-cmd-enter text='物品背包 {page_num + 1}' />"

            kj = await all_write_command(uid, (f"角色背包", f"物品信息 {item_name}"))

            return {"type": "markdown", "content": output + kj}


# 物品信息
@reg_xz_func
async def item_info(uid, qz, item_name):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT `name`, `type`, `desc`, access FROM data_item WHERE `name` = %s LIMIT 1"
            await cursor.execute(sql, (item_name,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "未找到该物品！"}
            item_name, item_type, desc, access = result
            if item_type == 1:
                item_type = "药材"
            elif item_type == 2:
                item_type = "材料"
            elif item_type == 3:
                item_type = "道具"
            elif item_type == 4:
                item_type = "丹药"

            output = f"##### 『物品信息』\n\n"
            output += f"**物品名称：** {item_name}\n"
            output += f"**物品类型：** {item_type}\n"
            output += f"**物品描述：**\n"
            output += f"> {desc}\n"
            output += f"**获取途径：**\n"
            output += f"> {access}\n"

            kj = await all_write_command(uid, ("物品背包", "角色背包", "当前角色"))
            return {"type": "markdown", "content": output + kj}
