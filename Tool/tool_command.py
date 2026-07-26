import asyncio
from sql.mysql import *
from Tool.tool_user import *


# 判断玩家当前快捷指令表中是否有欲输入指令
async def pd_command(openid, input_str):
    """
    指令查询与拼接函数
    参数格式：
    - 普通查询："1"
    - 后缀模式："1-药剂1"（注意中间的短横线）
    返回值：
    - 成功：拼接后的指令字符串（如"使用 药剂1"）
    - 失败：False
    """
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 解析输入参数
            if '-' in input_str:
                parts = input_str.split('-', 1)
                if len(parts) != 2 or not parts[0].isdigit():
                    return False
                comm_id = int(parts[0])
                suffix_content = parts[1].strip()
            else:
                if not input_str.isdigit():
                    return False
                comm_id = int(input_str)
                suffix_content = None

            # 校验指令位有效性
            if not 1 <= comm_id <= 5:
                return False

            # 执行数据库查询
            sql = f"""
                SELECT 
                    command_{comm_id},
                    is_houzhui_{comm_id}
                FROM user_command 
                WHERE openid = %s 
                LIMIT 1
            """
            await cursor.execute(sql, (openid,))
            result = await cursor.fetchone()

            if not result:
                return False

            main_command, is_houzhui = result
            main_command = main_command or ""  # 处理NULL值
            is_houzhui = is_houzhui or 0  # 处理NULL值

            # 空指令处理
            if not main_command.strip():
                return False

            # 后缀模式处理
            if suffix_content:
                if is_houzhui == 1:
                    return f"{main_command} {suffix_content}"
                return False

            # 普通模式返回
            return f"{main_command}" if is_houzhui == 1 else main_command


# 指令写入
async def write_command(openid, uid, comm_id, command):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT openid FROM user_command WHERE uid = %s"
            await cursor.execute(sql, (uid,))
            if await cursor.fetchone() is None:
                sql = "INSERT INTO user_command (openid, uid, command_%s) VALUES (%s, %s, %s)"
                await cursor.execute(sql, (comm_id, openid, uid, command))
                await conn.commit()
            else:
                sql = f"UPDATE user_command SET command_%s = %s WHERE openid = %s AND uid = %s"
                await cursor.execute(sql, (comm_id, command, openid, uid))
                await conn.commit()
            return True


# 多指令写入并输出 - Markdown交互按钮版本
async def all_write_command(uid, command):
    # 旧command消息体：("", "", "", "", "")
    # 新command消息体：[("消息内容", 1), ("消息内容", 0), ("消息内容", 0), ("消息内容", 0), ("消息内容", 0)] # 1表示指令有后缀
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            openid = await uid_to_openid(uid)
            sql = "SELECT openid FROM user_command WHERE uid = %s"
            await cursor.execute(sql, (uid,))
            if await cursor.fetchone() is None:
                columns = ["command_1", "command_2", "command_3", "command_4", "command_5"][:len(command)]
                placeholders = ["%s"] * (2 + len(command))
                sql = f"INSERT INTO user_command (openid, uid, {', '.join(columns)}) VALUES ({', '.join(placeholders)})"
                params = (openid, uid) + tuple(command[:5])
                await cursor.execute(sql, params)
                await conn.commit()
            else:
                valid_columns = ["command_1", "command_2", "command_3", "command_4", "command_5"]
                set_clause = ", ".join([
                    f"{col} = %s"
                    for col, value in zip(valid_columns, command)
                    if value
                ])
                sql = f"UPDATE user_command SET {set_clause} WHERE openid = %s AND uid = %s"
                params = tuple(val for val in command if val)[:5] + (openid, uid)
                await cursor.execute(sql, params)
                await conn.commit()

            # 生成Markdown交互按钮（每行最多3个）
            output = "\n***\n"
            for i in range(0, len(command), 3):
                line_commands = command[i:i+3]
                button_line = " | ".join([f'<qqbot-cmd-enter text="{cmd}" />' for cmd in line_commands])
                output += button_line + "\n"
            return output


# 多指令写入并输出 - Markdown交互按钮版本（支持后缀参数）
async def all_write_cmd(uid, command):
    # 新消息体示例：[("消息1",1), ("消息2",0), ("消息3",1)]
    # flag=1表示指令需要后缀参数，会在按钮显示中用*标记
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            openid = await uid_to_openid(uid)

            # 构建数据库字段映射
            db_fields = []
            params = []
            for idx, (content, flag) in enumerate(command, 1):
                if idx > 5:  # 限制最多5个指令位
                    break
                db_fields.extend([f"command_{idx}", f"is_houzhui_{idx}"])
                params.extend([content, flag])

            # INSERT/UPDATE逻辑
            await cursor.execute("SELECT openid FROM user_command WHERE uid = %s", (uid,))
            if not await cursor.fetchone():
                # 插入新记录（动态生成字段）
                columns = ["openid", "uid"] + db_fields
                placeholders = ["%s"] * (2 + len(command) * 2)  # 每个指令占2个参数
                sql = f"INSERT INTO user_command ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
                await cursor.execute(sql, (openid, uid) + tuple(params))
            else:
                # 更新现有记录（动态生成SET子句）
                set_clauses = [f"{field}=%s" for field in db_fields]
                sql = f"UPDATE user_command SET {', '.join(set_clauses)} WHERE uid=%s"
                await cursor.execute(sql, tuple(params) + (uid,))

            await conn.commit()

            # 生成Markdown交互按钮（每行最多3个）
            output = "\n***\n"
            for i in range(0, len(command), 3):
                line_commands = command[i:i+3]
                button_line = " | ".join([
                    f'<qqbot-cmd-input text="{content}" show="{content}*" />' if flag == 1
                    else f'<qqbot-cmd-enter text="{content}" />'
                    for content, flag in line_commands
                ])
                output += button_line + "\n"
            return output
