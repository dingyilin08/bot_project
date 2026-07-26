from functools import wraps
from Tool.tool_user import *


# 注册判断装饰器
def pd_reg_func(func):
    @wraps(func)
    async def wrapper(uid, *args, **kwargs):
        if await uid_is_zhuce(uid):
            qz = await qianzhui(uid)
            return await func(uid, qz, *args, **kwargs)
        else:
            return {"type": "markdown", "content": "您还未注册本游戏，请先注册！\n\n可用指令：[注册游戏]"}
    return wrapper


# 注册+选择初始角色——判断装饰器
def reg_xz_func(func):
    @wraps(func)
    async def wrapper(uid, *args, **kwargs):
        if await uid_is_zhuce(uid):
            qz = await qianzhui(uid)
            async with connect_mysql() as conn:
                async with conn.cursor() as cursor:
                    sql = "SELECT is_chushi FROM user_zt WHERE id = %s limit 1"
                    await cursor.execute(sql, (uid,))
                    result = await cursor.fetchone()
                    if result[0] == 1:
                        return await func(uid, qz, *args, **kwargs)
                    else:
                        output = "##### 未选择初始角色\n\n"
                        output += "您还未选择您的初始角色！\n请发送**选择角色**来选择您的初始角色！\n\n"
                        output += "**待选角色：**\n"
                        output += "> ◇<qqbot-cmd-input text='角色介绍 萧炎' show='角色介绍 萧炎' />：异火焚天/斗帝传承\n"
                        output += "> ◇<qqbot-cmd-input text='角色介绍 王林' show='角色介绍 王林' />：禁制大师/生死轮回\n"
                        output += "> ◇<qqbot-cmd-input text='角色介绍 韩立' show='角色介绍 韩立' />：掌天瓶主/遁术无双\n"
                        output += "> ◇<qqbot-cmd-input text='角色介绍 石昊' show='角色介绍 石昊' />：独断万古/至尊骨\n"
                        output += "> ◇<qqbot-cmd-input text='角色介绍 叶凡' show='角色介绍 叶凡' />：圣体无双/九秘传承\n"
                        output += "> ◇<qqbot-cmd-input text='角色介绍 孟川' show='角色介绍 孟川' />：刀意通神/雷霆灭世\n\n"
                        output += "**Tips：** 角色选择后不可更换，后期可通过碎片合成其他角色\n"
                        output += "***\n"
                        output += '<qqbot-cmd-input text="选择角色 " show="选择角色* " /> | <qqbot-cmd-input text="角色介绍 " show="角色介绍* " />\n'
                        return {"type": "markdown", "content": output}
        else:
            return {"type": "markdown", "content": "您还未注册本游戏，请先注册！\n\n可用指令：[注册游戏]"}
    return wrapper
