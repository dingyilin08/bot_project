from sql.mysql import *
from Tool.tool_user import *
from func.pd_func import *
import time
import random
import re
from Tool.tool_command import *


# 激活技能
@reg_xz_func
async def jh_skill(uid, qz, skill_name):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, role_name, skill_type, `value`, is_percent, item_id, cooldown, buff_name, buff_desc FROM data_skill WHERE skill_name = %s LIMIT 1"
            await cursor.execute(sql, (skill_name,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "技能不存在，请检查技能名称是否正确。\n示例：激活技能 八极崩\n"}

            skill_id, role_name, skill_type, value, is_percent, item_id, cooldown, buff_name, buff_desc = result
            
            sql = "SELECT id FROM user_skill WHERE uid = %s AND skill_id = %s LIMIT 1"
            await cursor.execute(sql, (uid, skill_id))
            result = await cursor.fetchone()
            if result is not None:
                return {"type": "markdown", "content": qz + "该技能已激活，请勿重复激活。\n"}

            if await cut_bag_item(uid, item_id, 1, cursor=cursor) is False:
                return {"type": "markdown", "content": qz + f"激活失败！缺少技能卷轴[{skill_name}卷轴]，无法激活该技能。\n"}

            sql = "SELECT COALESCE(MAX(id), 0) + 1 FROM user_skill"
            await cursor.execute(sql)
            user_skill_id, = await cursor.fetchone()

            sql = "INSERT INTO user_skill (id, uid, is_data_skill, skill_id, skill_name, skill_type, `value`, is_percent, cooldown) VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s)"
            await cursor.execute(sql, (user_skill_id, uid, skill_id, skill_name, skill_type, value, is_percent, cooldown))
            await conn.commit()
            if skill_type == 1:
                skill_type = "攻击型"
            elif skill_type == 2:
                skill_type = "防御型"
            elif skill_type == 3:
                skill_type = "回复型"
            else:
                skill_type = "穿透型"

            value = f"{value}" if is_percent == 0 else f"{value}%"

            output = f"技能激活成功！请前往技能背包查看\n"
            output += f"技能编号：{user_skill_id}\n"
            output += f"技能名称：{skill_name}\n"
            output += f"可装备角色：{role_name}\n"
            output += f"技能类型：{skill_type}\n"
            output += f"技能数值：{value}\n"
            output += f"技能冷却：{cooldown}回合\n"
            output += f"技能BUFF：{buff_name}\n"
            output += f"BUFF描述：{buff_desc}\n"

            output += "> Tips：基础技能将限制可装备角色，技能融合后可装备给任意角色\n"

            kj = await all_write_cmd(uid, [("技能装备", 1), ("技能背包", 0), ("当前角色", 0)])

            return {"type": "markdown", "content": qz + output + kj}


# 卷轴信息
@reg_xz_func
async def jz_info(uid, qz, jz_name):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            try:
                skill_name = jz_name.split("卷轴")[0]
            except IndexError:
                return {"type": "markdown", "content": qz + "卷轴名称错误，请检查卷轴名称是否正确。\n"}
            sql = "SELECT role_name, skill_type, `value`, is_percent, item_id, cooldown, buff_name, buff_desc FROM data_skill WHERE skill_name = %s LIMIT 1"
            await cursor.execute(sql, (skill_name,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "技能不存在，请检查卷轴名称是否正确。\n"}
            role_name, skill_type, value, is_percent, item_id, cooldown, buff_name, buff_desc = result

            if skill_type == 1:
                skill_type = "攻击型"
            elif skill_type == 2:
                skill_type = "防御型"
            elif skill_type == 3:
                skill_type = "回复型"
            else:
                skill_type = "穿透型"

            value = f"{value}" if is_percent == 0 else f"{value}%"

            output = f"【{jz_name}】卷轴信息如下：\n"
            output += f"技能名称：{skill_name}\n"
            output += f"可装备角色：{role_name}\n"
            output += f"技能类型：{skill_type}\n"
            output += f"技能数值：{value}\n"
            output += f"技能冷却：{cooldown}回合\n"
            output += f"技能BUFF：{buff_name}\n"
            output += f"BUFF描述：{buff_desc}\n"

            output += "> Tips：基础技能将限制可装备角色，技能融合后可装备给任意角色\n"

            kj = await all_write_cmd(uid, [("技能装备", 1), ("技能背包", 0), ("当前角色", 0)])

            return {"type": "markdown", "content": qz + output + kj}


# 技能信息
def parse_skill_info_id(skill_info):
    """解析玩家技能背包编号。"""
    try:
        skill_id = int(str(skill_info or "").strip())
    except (TypeError, ValueError):
        return None
    return skill_id if skill_id > 0 else None


def _display_skill_type(skill_type):
    return {1: "攻击型", 2: "防御型", 3: "回复型", 4: "穿透型"}.get(
        int(skill_type or 0), "未知类型"
    )


def _display_skill_value(value, is_percent):
    return f"{value}%" if int(is_percent or 0) == 1 else str(value)


@reg_xz_func
async def skill_info(uid, qz, skill_info):
    skill_id = parse_skill_info_id(skill_info)
    if skill_id is None:
        return {"type": "markdown", "content": qz + "指令错误，正确指令：技能信息 技能编号\n示例：技能信息 31\n"}
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id, skill_name, skill_type, `value`, is_percent, skill_id, skill_1, skill_2,
                       is_data_skill, cooldown
                FROM user_skill WHERE id = %s AND uid = %s LIMIT 1
                """,
                (skill_id, uid),
            )
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "未找到该技能编号，请从技能背包中复制编号后重试。\n"}
            (_, skill_name, skill_type, value, is_percent, data_skill_id, source_1, source_2,
             is_data_skill, cooldown) = result

            if int(is_data_skill or 0) == 1:
                await cursor.execute(
                    "SELECT role_name, buff_name, buff_desc FROM data_skill WHERE id = %s LIMIT 1",
                    (data_skill_id,),
                )
                data_skill = await cursor.fetchone()
                role_name, buff_name, buff_desc = data_skill or ("未知", "无", "暂无附加效果说明")
                output = f"**基础技能【{skill_name}】信息：**\n"
                output += f"技能编号：{skill_id}\n"
                output += f"可装备角色：{role_name}\n"
                output += f"技能类型：{_display_skill_type(skill_type)}\n"
                output += f"技能数值：{_display_skill_value(value, is_percent)}\n"
                output += f"技能冷却：{cooldown}回合\n"
                output += f"技能BUFF：{buff_name}\n"
                output += f"BUFF描述：{buff_desc}\n"
            else:
                source_ids = [int(source) for source in (source_1, source_2) if source]
                source_names = []
                buff_name, buff_desc = "无", "暂无附加效果说明"
                if source_ids:
                    placeholders = ", ".join("%s" for _ in source_ids)
                    await cursor.execute(
                        f"SELECT id, skill_name, buff_name, buff_desc FROM data_skill WHERE id IN ({placeholders})",
                        tuple(source_ids),
                    )
                    source_rows = {int(row[0]): row[1:] for row in await cursor.fetchall()}
                    for source_id in source_ids:
                        source = source_rows.get(source_id)
                        if source:
                            source_names.append(source[0])
                    first_source = source_rows.get(int(source_1 or 0))
                    if first_source:
                        _, buff_name, buff_desc = first_source
                output = f"**融合技能【{skill_name}】信息：**\n"
                output += f"技能编号：{skill_id}\n"
                output += "可装备角色：任意角色\n"
                output += f"技能类型：{_display_skill_type(skill_type)}\n"
                output += f"技能数值：{_display_skill_value(value, is_percent)}\n"
                output += f"技能冷却：{cooldown}回合\n"
                output += f"融合素材：{' + '.join(source_names) if source_names else '原始素材记录缺失'}\n"
                output += f"继承BUFF：{buff_name}\n"
                output += f"BUFF描述：{buff_desc}\n"

            output += "> Tips：基础技能限制可装备角色；融合技能可由任意角色装备，且继承第一个素材技能的附加效果。\n"
            return {"type": "markdown", "content": qz + output}


# 技能融合
def parse_fusion_skill_ids(skill_info):
    """解析“技能编号A-技能编号B”，避免非法编号进入融合事务。"""
    parts = str(skill_info or "").strip().split("-")
    if len(parts) != 2:
        return None, None
    try:
        skill_1_id, skill_2_id = (int(part.strip()) for part in parts)
    except (TypeError, ValueError):
        return None, None
    if skill_1_id <= 0 or skill_2_id <= 0 or skill_1_id == skill_2_id:
        return None, None
    return skill_1_id, skill_2_id


@reg_xz_func
async def fuse_skills(uid, qz, skill_info):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            skill_1_id, skill_2_id = parse_fusion_skill_ids(skill_info)
            if skill_1_id is None:
                return {"type": "markdown", "content": qz + "技能融合格式错误，请检查技能融合格式是否正确。\n示例：技能融合 欲融合技能1-欲融合技能2"}
            # 检查两个技能是否存在
            sql = "SELECT skill_name, skill_type, `value`, is_percent, is_data_skill, is_zb, skill_id, cooldown FROM user_skill WHERE id = %s AND uid = %s LIMIT 1"
            await cursor.execute(sql, (skill_1_id, uid))
            result1 = await cursor.fetchone()
            if result1 is None:
                return {"type": "markdown", "content": qz + "技能1不存在或未激活，无法融合。\n"}

            skill_name_1, skill_type_1, value_1, is_percent_1, is_data_skill_1, is_zb_1, data_skill_id_1, cooldown_1 = result1

            if is_data_skill_1 != 1:
                return {"type": "markdown", "content": qz + "已融合过的技能无法重复融合！\n"}
            
            if is_zb_1 == 1:
                return {"type": "markdown", "content": qz + f"技能[{skill_name_1}]已装备，请先卸下再融合。\n"}

            await cursor.execute(sql, (skill_2_id, uid))
            result2 = await cursor.fetchone()
            if result2 is None:
                return {"type": "markdown", "content": qz + "技能2不存在或未激活，无法融合。\n"}

            skill_name_2, skill_type_2, value_2, is_percent_2, is_data_skill_2, is_zb_2, data_skill_id_2, cooldown_2 = result2

            if is_data_skill_2 != 1:
                return {"type": "markdown", "content": qz + "已融合过的技能无法重复融合！\n"}
            
            if is_zb_2 == 1:
                return {"type": "markdown", "content": qz + f"技能[{skill_name_2}]已装备，请先卸下再融合。\n"}

            # 检查技能类型是否一致
            if skill_type_1 != skill_type_2:
                return {"type": "markdown", "content": qz + "技能类型不一致，无法融合。\n"}
            if is_percent_1 != is_percent_2:
                return {"type": "markdown", "content": qz + "百分比数值与普通数值类型不一致，无法融合。\n"}

            try:
                value_1 = int(value_1)
                value_2 = int(value_2)
            except (TypeError, ValueError):
                return {"type": "markdown", "content": qz + "技能数值异常，暂时无法融合，请联系管理员处理。\n"}

            if value_1 < value_2:
                new_skill_value = random.randint(int(value_1 * 1.5), int(value_2 * 2))
            elif value_1 > value_2:
                new_skill_value = random.randint(int(value_2 * 1.5), int(value_1 * 2))
            else:
                new_skill_value = random.randint(int(value_1 * 1.5), int(value_1 * 2))

            new_skill_name = "未命名"
            new_skill_type = skill_type_1
            new_skill_cooldown = max(cooldown_1 or 0, cooldown_2 or 0)

            sql = "SELECT COALESCE(MAX(id), 0) + 1 FROM user_skill"
            await cursor.execute(sql)
            result = await cursor.fetchone()
            new_skill_id = result[0]

            skill_type_display = new_skill_type
            if skill_type_display == 1:
                skill_type_display = "攻击型"
            elif skill_type_display == 2:
                skill_type_display = "防御型"
            elif skill_type_display == 3:
                skill_type_display = "回复型"
            elif skill_type_display == 4:
                skill_type_display = "穿透型"

            sql = "INSERT INTO user_skill (id, uid, skill_name, skill_type, `value`, is_percent, skill_1, skill_2, is_data_skill, is_zb, cooldown) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            await cursor.execute(sql, (
            new_skill_id, uid, new_skill_name, new_skill_type, new_skill_value, is_percent_1, data_skill_id_1, data_skill_id_2, 0,
            0, new_skill_cooldown))
            
            sql = "DELETE FROM user_skill WHERE id IN (%s, %s) AND uid = %s"
            await cursor.execute(sql, (skill_1_id, skill_2_id, uid))
            
            await conn.commit()

            output = f"成功将[{skill_name_1}]和[{skill_name_2}]融合\n"
            output += "技能名称：待命名\n"
            output += f"技能编号：{new_skill_id}\n"
            output += f"所属玩家：[{uid}]{await uid_to_name(uid)}\n"
            output += f"技能类型：{skill_type_display}\n"
            output += f"技能数值：{new_skill_value}\n"
            output += f"技能冷却：{new_skill_cooldown}回合\n"
            await cursor.execute(
                "SELECT buff_name, buff_desc FROM data_skill WHERE id = %s LIMIT 1",
                (data_skill_id_1,),
            )
            buff_result = await cursor.fetchone()
            if buff_result:
                output += f"继承BUFF：{buff_result[0]}\n"
                output += f"BUFF描述：{buff_result[1]}\n"
            output += f"<qqbot-cmd-input text='技能命名 {new_skill_id}-' show='为融合技能命名' />\n"
            output += f"<qqbot-cmd-input text='技能信息 {new_skill_id}' show='查看融合技能详情' />\n"

            return {"type": "markdown", "content": qz + output}


# 技能装备
@reg_xz_func
async def equip_skill(uid, qz, skill_info):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            try:
                role_skill_id, skill_id = skill_info.split("-")
            except ValueError:
                return {"type": "markdown", "content": qz + "请输入正确指令：技能装备 角色技能槽-技能编号\n"}
            if role_skill_id is None or skill_id is None:
                return {"type": "markdown", "content": qz + "请输入正确指令：技能装备 角色技能槽-技能编号\n"}
            elif role_skill_id == "" or skill_id == "":
                return {"type": "markdown", "content": qz + "请输入正确指令：技能装备 角色技能槽-技能编号\n"}

            # 检查技能是否存在
            sql = "SELECT skill_name, is_data_skill, skill_id FROM user_skill WHERE id = %s AND uid = %s AND is_zb = 0 LIMIT 1"
            await cursor.execute(sql, (skill_id, uid))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "技能未激活或已装备，装备失败。\n"}

            skill_name, is_data_skill, data_skill_id = result

            # 检查角色是否存在
            sql = "SELECT id, `name`, skill1_id, skill2_id, skill3_id FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid, ))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您当前未出战角色，无法装备技能。\n"}

            role_id, role_name, skill1_id, skill2_id, skill3_id = result

            if int(role_skill_id) not in [1, 2, 3]:
                return {"type": "markdown", "content": qz + "请输入正确指令：技能装备 角色技能槽-技能编号\n示例：技能装备 1-1"}

            if role_skill_id == "1" and skill1_id:
                return {"type": "markdown", "content": qz + f"[{role_id}]{role_name}角色技能槽1已被装备，请更换技能槽重新装备。\n"}
            elif role_skill_id == "2" and skill2_id:
                return {"type": "markdown", "content": qz + f"[{role_id}]{role_name}角色技能槽2已被装备，请更换技能槽重新装备。\n"}
            elif role_skill_id == "3" and skill3_id:
                return {"type": "markdown", "content": qz + f"[{role_id}]{role_name}角色技能槽3已被装备，请更换技能槽重新装备。\n"}

            if is_data_skill == 1:
                sql = "SELECT role_name FROM data_skill WHERE id = %s LIMIT 1"
                await cursor.execute(sql, (data_skill_id, ))
                result = await cursor.fetchone()
                data_role_name = result[0]
                if data_role_name != role_name:
                    return {"type": "markdown", "content": qz + f"[{role_id}]{role_name}角色无法装备{skill_name}，基础技能仅可装备给对应角色。\n"}

            # 装备技能
            sql = f"UPDATE user_role SET `skill{role_skill_id}_id` = %s WHERE id = %s AND uid = %s LIMIT 1"
            await cursor.execute(sql, (skill_id, role_id, uid))

            sql = "UPDATE user_skill SET is_zb = 1 WHERE id = %s LIMIT 1"
            await cursor.execute(sql, (skill_id, ))

            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)
            await conn.commit()

            return {"type": "markdown", "content": qz + f"技能[{skill_name}]已成功装备给角色[{role_name}]。\n"}


# 技能命名
def parse_skill_rename_param(skill_info):
    """解析“技能编号-新名称”，并限制在数据库字段允许的长度内。"""
    try:
        skill_id_text, new_name = str(skill_info or "").split("-", 1)
        skill_id = int(skill_id_text.strip())
    except (TypeError, ValueError):
        return None, None, "请输入正确指令：技能命名 技能编号-新名称\n示例：技能命名 1-烈焰斩"
    new_name = new_name.strip()
    if skill_id <= 0:
        return None, None, "技能编号必须为正整数。"
    if not new_name:
        return None, None, "技能名称不能为空，请重新输入。"
    if len(new_name) > 30:
        return None, None, "技能名称最多30个字符，请缩短后重试。"
    if not re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·【】\[\]-]+", new_name):
        return None, None, "技能名称仅可使用中英文、数字、连接号与书名括号。"
    if new_name == "未命名":
        return None, None, "“未命名”是融合技能占位名，请换一个真正的技能名称。"
    return skill_id, new_name, None


@reg_xz_func
async def rename_skill(uid, qz, skill_info):
    skill_id, new_name, error = parse_skill_rename_param(skill_info)
    if error:
        return {"type": "markdown", "content": qz + error}
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                sql = "SELECT id, skill_name, is_data_skill FROM user_skill WHERE id = %s AND uid = %s LIMIT 1 FOR UPDATE"
                await cursor.execute(sql, (skill_id, uid))
                result = await cursor.fetchone()
                if result is None:
                    return {"type": "markdown", "content": qz + "技能不存在，无法命名。\n"}

                _, old_name, is_data_skill = result
                if is_data_skill == 1:
                    return {"type": "markdown", "content": qz + "基础技能无法重命名，仅融合技能可命名。\n"}

                await cursor.execute(
                    "SELECT 1 FROM user_skill WHERE uid = %s AND skill_name = %s AND id <> %s LIMIT 1",
                    (uid, new_name, skill_id),
                )
                if await cursor.fetchone():
                    return {"type": "markdown", "content": qz + f"你已经拥有名为“{new_name}”的技能，请换一个名称。"}

                sql = "UPDATE user_skill SET skill_name = %s WHERE id = %s AND uid = %s LIMIT 1"
                await cursor.execute(sql, (new_name, skill_id, uid))
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    return {
        "type": "markdown",
        "content": qz + "\n".join((
            "##### ✍️ 融合技能命名成功",
            f"原名称：{old_name}",
            f"新名称：**{new_name}**",
            "***",
            f"<qqbot-cmd-input text='技能装备 1-{skill_id}' show='装备到技能槽1' /> | <qqbot-cmd-input text='技能背包' show='技能背包' />",
        )),
    }


# 技能卸下
@reg_xz_func
async def unload_skill(uid, qz, skill_num):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            try:
                skill_num = int(skill_num)
            except ValueError:
                return {"type": "markdown", "content": qz + "请输入正确的技能槽号。"}
            if skill_num not in [1, 2, 3]:
                return {"type": "markdown", "content": qz + "请输入正确指令：技能卸下 角色技能槽号\n示例：技能卸下 1"}
            sql = f"SELECT id, `name`, skill1_id, skill2_id, skill3_id FROM user_role WHERE uid = %s and is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您还未出战角色，无法卸下技能。\n请发送[出战 角色编号]来选择您要出战的角色！\n"}
            role_id, role_name, skill1_id, skill2_id, skill3_id = result
            if skill_num == 1:
                skill_id = skill1_id
                if skill1_id == 0 or skill1_id is None:
                    return {"type": "markdown", "content": qz + f"您当前出战的角色[{role_id}.{role_name}]技能槽1还未装备技能，无需卸下。\n"}
            elif skill_num == 2:
                skill_id = skill2_id
                if skill2_id == 0 or skill2_id is None:
                    return {"type": "markdown", "content": qz + f"您当前出战的角色[{role_id}.{role_name}]技能槽2还未装备技能，无需卸下。\n"}
            elif skill_num == 3:
                skill_id = skill3_id
                if skill3_id == 0 or skill3_id is None:
                    return {"type": "markdown", "content": qz + f"您当前出战的角色[{role_id}.{role_name}]技能槽3还未装备技能，无需卸下。\n"}

            sql = f"UPDATE user_role SET `skill{skill_num}_id` = NULL WHERE id = %s AND uid = %s LIMIT 1"
            await cursor.execute(sql, (role_id, uid))

            sql = "UPDATE user_skill SET is_zb = 0 WHERE id = %s LIMIT 1"
            await cursor.execute(sql, (skill_id,))

            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)
            await conn.commit()

            return {"type": "markdown", "content": qz + f"成功卸下角色[{role_id}.{role_name}]的技能槽{skill_num}：{await get_skill_name(cursor, skill_id)}。\n"}


# 技能背包
@reg_xz_func
async def skill_bag(uid, qz, page_num=1):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            try:
                page_num = int(page_num)
            except ValueError:
                return {"type": "markdown", "content": qz + "请输入正确的背包页码。\n"}

            if page_num < 1:
                page_num = 1

            page_size = 9

            count_sql = "SELECT COUNT(*) FROM user_skill WHERE uid = %s and is_zb = 0"
            await cursor.execute(count_sql, (uid,))
            a = await cursor.fetchone()
            total_records = a[0]
            if total_records == 0:
                return {"type": "markdown", "content": qz + "你的背包中暂无待装备技能！\n"}
            total_pages = (total_records + page_size - 1) // page_size
            page_num = min(page_num, total_pages)
            offset = (page_num - 1) * page_size

            output = f"##### 技能背包 ({page_num}/{total_pages}页)"

            sql = "SELECT id, is_data_skill, skill_name, skill_type FROM user_skill WHERE uid = %s and is_zb = 0 LIMIT %s OFFSET %s"
            await cursor.execute(sql, (uid, page_size, offset))
            result = await cursor.fetchall()

            for i in result:
                skill_id, is_data_skill, skill_name, skill_type = i
                if is_data_skill == 0:
                    biaoshi = "✧"
                else:
                    biaoshi = ""
                if skill_type == 1 or skill_type == '1':
                    skill_type = "攻击型"
                elif skill_type == 2 or skill_type == '2':
                    skill_type = "防御型"
                elif skill_type == 3 or skill_type == '3':
                    skill_type = "回复型"
                elif skill_type == 4 or skill_type == '4':
                    skill_type = "穿透型"

                skill_bt = f"<qqbot-cmd-input text='技能信息 {skill_id}' show='技能信息 {skill_id}' />"
                output += f"〔{skill_id}〕{skill_bt}『{skill_type}』{biaoshi}\n"

            output += "> 点击蓝字可查看该技能信息噢~\n"

            output += "***\n"

            sql = "SELECT lingshi, xianyu FROM user_zt WHERE id = %s LIMIT 1"
            await cursor.execute(sql, (uid,))
            lingshi, xianyu = await cursor.fetchone()
            output += f"[灵石]：{lingshi} [仙玉]：{xianyu}\n"

            output += "***\n"

            output += pagination_controls("技能背包", page_num, total_pages) + "\n"

            return {"type": "markdown", "content": qz + output}



