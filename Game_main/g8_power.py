# -*- coding: utf-8 -*-
"""
战力系统游戏模块
功能：查看战力、战力排行榜
"""
from sql.mysql import connect_mysql
from Tool.tool_power import (
    calculate_total_power, update_role_power, get_user_power_rank, get_power_ranking
)
from Tool.tool_command import all_write_command
from func.pd_func import reg_xz_func


def format_power(power: int) -> str:
    """格式化战力显示"""
    if power >= 100000:
        return f"{power / 10000:.2f}万"
    return str(power)


@reg_xz_func
async def my_power(uid, qz):
    """
    查看我的战力
    指令：我的战力 / 战力
    """
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT power, power_base, power_level, power_equip,
                       power_benyuan, power_skill, power_role_name
                FROM user_zt
                WHERE id = %s
            """, (uid,))
            power_data = await cursor.fetchone()
        
        if not power_data or power_data[0] == 0:
            output = "##### ⚠️ 暂无战力数据\n\n"
            output += "> 您还没有出战角色，或角色数据未初始化\n"
            output += "> 请先选择角色并出战\n"
            output += "***\n"
            output += '<qqbot-cmd-enter text="角色背包" /> | <qqbot-cmd-input text="出战" show="出战角色" />'
            return {"type": "markdown", "content": output}
        
        power, power_base, power_level, power_equip = power_data[0], power_data[1], power_data[2], power_data[3]
        power_benyuan, power_skill, power_role_name = power_data[4], power_data[5], power_data[6]
        
        my_rank, total_players = await get_user_power_rank(conn, uid)
        
        total = power
        percentages = {
            'base': round(power_base / total * 100, 1) if total > 0 else 0,
            'level': round(power_level / total * 100, 1) if total > 0 else 0,
            'equip': round(power_equip / total * 100, 1) if total > 0 else 0,
            'benyuan': round(power_benyuan / total * 100, 1) if total > 0 else 0,
            'skill': round(power_skill / total * 100, 1) if total > 0 else 0,
        }
        
        output = f"##### 🔥 战力详情\n\n"
        output += f"**总战力：** {format_power(power)}\n"
        output += f"**当前角色：** {power_role_name}\n"
        output += f"**全服排名：** 第{my_rank}名 / 共{total_players}人\n"
        output += "***\n"
        output += "**战力构成：**\n"
        output += f"> ⚔️ 基础战力：{format_power(power_base)} ({percentages['base']}%)\n"
        output += f"> 📊 等级战力：{format_power(power_level)} ({percentages['level']}%)\n"
        output += f"> 🛡️ 装备战力：{format_power(power_equip)} ({percentages['equip']}%)\n"
        output += f"> 💎 本源战力：{format_power(power_benyuan)} ({percentages['benyuan']}%)\n"
        output += f"> ⚡ 技能战力：{format_power(power_skill)} ({percentages['skill']}%)\n"
        output += "***\n"
        output += '<qqbot-cmd-enter text="战力排行" /> | <qqbot-cmd-enter text="装备背包" /> | <qqbot-cmd-enter text="查看本源" />'
        
        return {"type": "markdown", "content": output}


@reg_xz_func
async def power_rank(uid, qz):
    """
    查看战力排行榜菜单
    指令：战力排行 / 排行榜
    """
    output = "##### 🏆 战力排行榜\n\n"
    output += "请选择查看的排行榜类型：\n\n"
    output += '<qqbot-cmd-enter text="战力排行 全服" />\n'
    output += '<qqbot-cmd-enter text="战力排行 萧炎" />\n'
    output += '<qqbot-cmd-enter text="战力排行 王林" />\n'
    output += '<qqbot-cmd-enter text="战力排行 韩立" />\n'
    output += '<qqbot-cmd-enter text="战力排行 石昊" />\n'
    output += '<qqbot-cmd-enter text="战力排行 叶凡" />\n'
    output += '<qqbot-cmd-enter text="战力排行 孟川" />\n'
    output += "***\n"
    output += "> 💡 排行榜数据实时更新"
    
    return {"type": "markdown", "content": output}


@reg_xz_func
async def power_rank_detail(uid, qz, rank_type_name):
    """
    查看具体排行榜
    指令：战力排行 全服 / 战力排行 萧炎
    
    Args:
        uid: 玩家ID
        qz: 前缀
        rank_type_name: 排行榜类型（全服/萧炎/王林等）
    """
    async with connect_mysql() as conn:
        ranking = await get_power_ranking(conn, rank_type_name, 20)
        
        if not ranking:
            output = "##### ⚠️ 暂无排行数据\n\n"
            output += f"> 当前没有符合条件的玩家数据\n"
            output += "***\n"
            output += '<qqbot-cmd-enter text="战力排行" />'
            return {"type": "markdown", "content": output}
        
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT power FROM user_zt WHERE id = %s", (uid,))
            my_power_row = await cursor.fetchone()
            my_power = my_power_row[0] if my_power_row else 0
        
        my_rank, total_players = await get_user_power_rank(conn, uid)
        
        title = f"##### 🏆 {rank_type_name}战力排行榜\n\n"
        rank_lines = []
        
        for idx, row in enumerate(ranking, start=1):
            rank_icon = {1: '🥇', 2: '🥈', 3: '🥉'}.get(idx, f'{idx}.')
            highlight = ' ⭐' if row['uid'] == uid else ''
            role_display = f"（{row['role_name']}）" if rank_type_name == '全服' else ''
            rank_lines.append(
                f"{rank_icon} **{row['name']}**{role_display} | 战力：{format_power(row['power'])}{highlight}"
            )
        
        rank_text = '\n'.join(rank_lines)
        
        my_rank_text = ""
        if my_rank and my_rank > 20 and my_power > 0:
            my_rank_text = f"\n\n🔹 你的排名：第{my_rank}名 | 战力：{format_power(my_power)}"
        
        stats = f"\n\n📊 总玩家数：{total_players}人"
        
        buttons = "\n\n***\n"
        buttons += '<qqbot-cmd-enter text="我的战力" /> | <qqbot-cmd-enter text="战力排行" />'
        
        content = title + rank_text + my_rank_text + stats + buttons
        return {"type": "markdown", "content": content}


async def refresh_power(uid: int) -> int:
    """
    刷新玩家战力（供其他模块调用）
    
    Args:
        uid: 玩家ID
    
    Returns:
        更新后的总战力
    """
    async with connect_mysql() as conn:
        return await update_role_power(conn, uid)
