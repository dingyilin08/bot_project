# -*- coding: utf-8 -*-
"""
战力系统游戏模块
功能：查看战力、战力排行榜
"""
import asyncio
import logging

from sql.mysql import connect_mysql
from Tool.tool_power import update_role_power, get_user_power_rank, get_power_ranking
from Tool.tool_command import all_write_command
from Tool.power_card import render_power_card
from func.pd_func import reg_xz_func
from config import IMG_BASE_URL
from Game_domain.power_portrait_service import active_portrait_path


logger = logging.getLogger(__name__)


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
        # 查看时实时刷新，保证刚绑定或更换灵兽后分项战力立即一致。
        await update_role_power(conn, uid)
        await conn.commit()
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT power, power_base, power_level, power_equip,
                       power_benyuan, power_skill, power_beast, power_role_name
                FROM user_zt
                WHERE id = %s
            """, (uid,))
            power_data = await cursor.fetchone()
        
        if not power_data or power_data[0] == 0:
            output = "##### ⚠️ 暂无战力数据\n\n"
            output += "> 您还没有出战角色，或角色数据未初始化\n"
            output += "> 请先选择角色并出战\n"
            output += "***\n"
            output += '<qqbot-cmd-input text="角色背包" show="角色背包" /> | <qqbot-cmd-input text="出战" show="出战角色" />'
            return {"type": "markdown", "content": output}
        
        power, power_base, power_level, power_equip = power_data[0], power_data[1], power_data[2], power_data[3]
        power_benyuan, power_skill, power_beast, power_role_name = power_data[4], power_data[5], power_data[6], power_data[7]
        
        my_rank, total_players = await get_user_power_rank(conn, uid)
        
        total = power
        percentages = {
            'base': round(power_base / total * 100, 1) if total > 0 else 0,
            'level': round(power_level / total * 100, 1) if total > 0 else 0,
            'equip': round(power_equip / total * 100, 1) if total > 0 else 0,
            'benyuan': round(power_benyuan / total * 100, 1) if total > 0 else 0,
            'skill': round(power_skill / total * 100, 1) if total > 0 else 0,
            'beast': round(power_beast / total * 100, 1) if total > 0 else 0,
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
        output += f"> 🐾 灵兽战力：{format_power(power_beast)} ({percentages['beast']}%)\n"
        output += "***\n"
        output += '<qqbot-cmd-input text="战力排行" show="战力排行" /> | <qqbot-cmd-input text="灵兽" show="随行灵兽" /> | <qqbot-cmd-input text="装备背包" show="装备背包" /> | <qqbot-cmd-input text="查看本源" show="查看本源" />'
        
        return {"type": "markdown", "content": output}


def _rate_text(value) -> str:
    try:
        return f"{float(value or 0) / 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


async def _load_power_card_data(conn, uid, power_details):
    """读取刚刚实时结算完成的战力、属性与养成摘要。"""
    async with conn.cursor() as cursor:
        await cursor.execute("""
            SELECT uz.`name`, uz.power, uz.power_base, uz.power_level,
                   uz.power_equip, uz.power_benyuan, uz.power_skill,
                   uz.power_beast,
                   ur.id, ur.`name`, ur.stage, ur.dengji,
                   ur.gongji, ur.gongji_jc, ur.fangyu, ur.fangyu_jc,
                   ur.qixue, ur.qixue_jc, ur.fali, ur.sudu,
                   ur.baoji, ur.baoshang, ur.shanbi, ur.mingzhong,
                   ur.pofang, ur.xixue, ur.by_id,
                   ur.skill1_id, ur.skill2_id, ur.skill3_id
            FROM user_zt uz
            JOIN user_role ur ON ur.uid = uz.id AND ur.is_chuzhan = 1
            WHERE uz.id = %s
            LIMIT 1
        """, (uid,))
        row = await cursor.fetchone()
        if not row or int(row[1] or 0) <= 0:
            return None

        (
            player_name, total_power, power_base, power_level, power_equip,
            power_benyuan, power_skill, power_beast, role_id, role_name,
            stage, level, gongji, gongji_jc, fangyu, fangyu_jc, qixue,
            qixue_jc, fali, sudu, baoji, baoshang, shanbi, mingzhong,
            pofang, xixue, by_id, skill1_id, skill2_id, skill3_id,
        ) = row

        benyuan = "未觉醒"
        if by_id:
            await cursor.execute(
                "SELECT `name`, dengji FROM user_benyuan WHERE id = %s AND uid = %s LIMIT 1",
                (by_id, uid),
            )
            benyuan_row = await cursor.fetchone()
            if benyuan_row:
                benyuan = f"{benyuan_row[0]} Lv.{int(benyuan_row[1] or 0)}"

        skill_ids = [skill_id for skill_id in (skill1_id, skill2_id, skill3_id) if skill_id]
        skill_names = []
        if skill_ids:
            placeholders = ",".join(["%s"] * len(skill_ids))
            await cursor.execute(
                f"SELECT id, skill_name FROM user_skill WHERE id IN ({placeholders})",
                tuple(skill_ids),
            )
            skill_map = {item[0]: item[1] for item in await cursor.fetchall()}
            skill_names = [skill_map[skill_id] for skill_id in skill_ids if skill_id in skill_map]

    set_info = power_details.get("set_info") or {}
    equip_bonus = set_info.get("attr_bonus") or {}
    equip_count = len(set_info.get("equip_details") or [])
    active_set = set_info.get("active_set")
    equipment = active_set or f"已穿戴{equip_count}件"
    beast_info = power_details.get("beast_info") or {}
    beast = beast_info.get("name") if beast_info else "暂无主契灵兽"
    if beast_info and beast_info.get("quality"):
        beast = f"{beast} · {beast_info['quality']}"

    rank, total_players = await get_user_power_rank(conn, uid)
    total_power = int(total_power or 0)
    component_rows = (
        ("基础", power_base), ("等级", power_level), ("装备", power_equip),
        ("本源", power_benyuan), ("技能", power_skill), ("灵兽", power_beast),
    )
    components = [
        {
            "label": label,
            "value": int(value or 0),
            "percent": round(int(value or 0) / total_power * 100, 1) if total_power else 0,
        }
        for label, value in component_rows
    ]

    return {
        "player_name": player_name or "无名道友",
        "role_name": role_name,
        "stage": stage or "未定境",
        "level": int(level or 0),
        "total_power": total_power,
        "rank": int(rank or 0),
        "total_players": int(total_players or 0),
        "stats": {
            "攻击": int(gongji or 0) + int(int(gongji or 0) * float(gongji_jc or 0) / 100) + int(equip_bonus.get("gongji", 0)),
            "防御": int(fangyu or 0) + int(int(fangyu or 0) * float(fangyu_jc or 0) / 100) + int(equip_bonus.get("fangyu", 0)),
            "气血": int(qixue or 0) + int(int(qixue or 0) * float(qixue_jc or 0) / 100) + int(equip_bonus.get("qixue", 0)),
            "法力": int(fali or 0) + int(equip_bonus.get("fali", 0)),
            "速度": int(sudu or 0) + int(equip_bonus.get("sudu", 0)),
            "暴击": _rate_text(int(baoji or 0) + int(equip_bonus.get("baoji", 0))),
        },
        "components": components,
        "benyuan": benyuan,
        "equipment": equipment,
        "skills": " / ".join(skill_names) if skill_names else "未装备技能",
        "beast": beast,
    }


@reg_xz_func
async def power_image(uid, qz):
    """生成当前出战角色的战力图片；该图片是玩法核心输出，不受 GM 关图影响。"""
    async with connect_mysql() as conn:
        _, power_details = await update_role_power(conn, uid, return_details=True)
        await conn.commit()
        card_data = await _load_power_card_data(conn, uid, power_details)

    if card_data is None:
        return {
            "type": "markdown",
            "content": "##### ⚠️ 暂无战力数据\n\n> 请先选择一名角色并设为出战。\n\n<qqbot-cmd-input text='角色背包' show='角色背包' /> | <qqbot-cmd-input text='出战 ' show='出战角色*' />",
        }

    try:
        custom_portrait = await active_portrait_path(uid)
    except Exception:
        # 迁移尚未执行或共享文件临时不可用时，原战力图片仍可使用默认立绘。
        logger.exception("读取玩家 %s 的审核立绘失败，回退角色默认立绘", uid)
        custom_portrait = None
    if custom_portrait:
        card_data["portrait_path"] = str(custom_portrait)

    try:
        image_path = await asyncio.to_thread(render_power_card, card_data)
    except Exception:
        logger.exception("玩家 %s 的战力图片生成失败", uid)
        return {
            "type": "markdown",
            "content": "##### ⚠️ 战力图片生成失败\n\n> 当前战力数据已刷新，请稍后重试；也可先查看文字版。\n\n<qqbot-cmd-input text='我的战力' show='查看文字战力' />",
        }

    image_url = f"{IMG_BASE_URL}/{image_path.name}"
    content = (
        f"![{card_data['role_name']}战力仙鉴 #720px #900px]({image_url})\n\n"
        f"> **{card_data['player_name']}** · {card_data['role_name']} · 战力 {format_power(card_data['total_power'])}\n\n"
        "<qqbot-cmd-input text='战力图片' show='刷新战力图片' /> | "
        "<qqbot-cmd-input text='我的战力' show='查看文字战力' /> | "
        "<qqbot-cmd-input text='当前角色' show='角色详情' />"
    )
    return {"type": "markdown", "content": content, "force_image": True}


@reg_xz_func
async def power_rank(uid, qz):
    """
    查看战力排行榜菜单
    指令：战力排行 / 排行榜
    """
    output = "##### 🏆 战力排行榜\n\n"
    output += "请选择查看的排行榜类型：\n\n"
    output += '<qqbot-cmd-input text="战力排行 全服" show="战力排行 全服" />\n'
    output += '<qqbot-cmd-input text="战力排行 萧炎" show="战力排行 萧炎" />\n'
    output += '<qqbot-cmd-input text="战力排行 王林" show="战力排行 王林" />\n'
    output += '<qqbot-cmd-input text="战力排行 韩立" show="战力排行 韩立" />\n'
    output += '<qqbot-cmd-input text="战力排行 石昊" show="战力排行 石昊" />\n'
    output += '<qqbot-cmd-input text="战力排行 叶凡" show="战力排行 叶凡" />\n'
    output += '<qqbot-cmd-input text="战力排行 孟川" show="战力排行 孟川" />\n'
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
            output += '<qqbot-cmd-input text="战力排行" show="战力排行" />'
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
        buttons += '<qqbot-cmd-input text="我的战力" show="我的战力" /> | <qqbot-cmd-input text="战力排行" show="战力排行" />'
        
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
        power = await update_role_power(conn, uid)
        await conn.commit()
        return power
