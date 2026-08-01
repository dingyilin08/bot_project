# -*- coding: utf-8 -*-
"""
游戏菜单系统 - 提供用户友好的功能导航
支持指令：菜单、MENU、主菜单
"""

from sql.mysql import *
from Tool.tool_user import *
from Tool.tool_command import *
from Tool.tool_canwu import canwu_remaining_seconds, ensure_canwu_duration_column
from func.pd_func import *
import time


# ================================
# 菜单配置数据
# ================================

# 主菜单配置
MENU_CONFIG = {
    "role": {
        "name": "角色管理",
        "icon": "👤",
        "description": "查看角色属性、装备背包、角色升级",
        "commands": ["当前角色", "角色背包", "物品背包", "悟道进阶"]
    },
    "cultivation": {
        "name": "修练系统",
        "icon": "🧘",
        "description": "参悟修炼、领取经验、提升境界",
        "commands": ["参悟", "参悟状态", "领取参悟经验"]
    },
    "origin": {
        "name": "本源系统",
        "icon": "💎",
        "description": "查看本源、本源升级",
        "commands": ["查看本源", "本源升级"]
    },
    "dungeon": {
        "name": "副本挑战",
        "icon": "⚔️",
        "description": "挑战副本、战斗记录、查看怪物",
        "commands": ["副本列表", "挑战副本", "查看怪物", "战斗状态", "战斗记录"]
    },
    "skill": {
        "name": "技能系统",
        "icon": "🔮",
        "description": "激活技能、装备技能",
        "commands": ["激活技能", "技能装备", "技能背包"]
    },
    "yaoyuan": {
        "name": "药园炼丹",
        "icon": "🌿",
        "description": "药田种植、丹炉炼丹、服丹增幅",
        "commands": ["药园", "查看丹炉", "丹方列表"]
    },
    "shop": {
        "name": "灵石商城",
        "icon": "🏪",
        "description": "购买体力、药园与炼丹便利道具",
        "commands": ["商城"]
    },
    "spirit_beast": {
        "name": "灵兽园",
        "icon": "🐾",
        "description": "寻访、出战与本源协同",
        "commands": ["灵兽", "灵兽寻访"]
    }
}


# 主菜单只放“xx菜单”级入口。新增功能优先归入已有分区；独立系统需新增子菜单后在此登记。
MAIN_MENU_SECTIONS = (
    (
        "🧍 角色养成",
        "角色培养、修行、本源、技能、装备与专属战斗养成。",
        (("角色菜单", "角色菜单"), ("参悟菜单", "参悟菜单"), ("本源菜单", "本源菜单"),
         ("技能菜单", "技能菜单"), ("装备菜单", "装备菜单"), ("专属养成菜单", "专属养成"),
         ("祈愿菜单", "仙玉祈愿")),
    ),
    (
        "⚔️ 战斗与资源",
        "副本挑战、背包交易、药园炼丹、灵兽与洞府生产。",
        (("副本菜单", "副本菜单"), ("资源菜单", "资源菜单"), ("灵兽菜单", "灵兽菜单"),
         ("洞府菜单", "洞府菜单")),
    ),
    (
        "👥 社交与活动",
        "队伍协作、宗门师徒、世界 Boss、赛季与排行榜。",
        (("队伍菜单", "队伍菜单"), ("宗门菜单", "宗门菜单"), ("活动菜单", "活动菜单"),
         ("战力菜单", "战力菜单")),
    ),
    (
        "📚 指引与记录",
        "新手札记、玩法说明与版本更新记录。",
        (("问道札记", "新手札记"), ("玩法介绍", "玩法介绍"), ("更新日志", "更新日志")),
    ),
)


def _menu_link(command, label):
    return f"<qqbot-cmd-input text='{command}' show='{label}' />"


def _menu_rows(entries, width=3):
    """主菜单每行最多三个入口，避免蓝字文本在窄屏消息中拥挤换行。"""
    return "\n".join(
        " | ".join(_menu_link(command, label) for command, label in entries[index:index + width])
        for index in range(0, len(entries), width)
    )


# ================================
# 菜单辅助函数
# ================================

async def get_player_basic_info(uid):
    """获取玩家基本信息"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT `name`, lingshi, xianyu FROM user_zt WHERE id = %s LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result:
                return {
                    'name': result[0],
                    'lingshi': result[1],
                    'xianyu': result[2]
                }
            return None


async def get_current_role_info(uid):
    """获取当前出战角色信息"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name`, dengji, stage, by_id FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result:
                return {
                    'id': result[0],
                    'name': result[1],
                    'level': result[2],
                    'stage': result[3],
                    'by_id': result[4]
                }
            return None


async def get_benyuan_info(uid):
    """获取当前出战角色本源信息"""
    role_info = await get_current_role_info(uid)
    if role_info is None or role_info.get('by_id') is None:
        return None
    
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT `name`, dengji FROM user_benyuan WHERE id = %s AND uid = %s LIMIT 1"
            await cursor.execute(sql, (role_info['by_id'], uid))
            result = await cursor.fetchone()
            if result:
                if 20 <= result[1] < 40:
                    stage = "五转·"
                elif 40 <= result[1] < 60:
                    stage = "天启·"
                elif result[1] >= 60:
                    stage = "终焉·"
                else:
                    stage = ""

                return {
                    'id': role_info['by_id'],
                    'name': result[0],
                    'level': result[1],
                    'stage': stage
                }
            return None


async def get_cultivation_status(uid):
    """获取参悟状态信息"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_canwu_duration_column(cursor)
            sql = "SELECT is_canwu, cw_role, cw_timestamp, cw_duration, cw_exp FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result:
                is_canwu, cw_role, cw_timestamp, cw_duration, cw_exp = result

                if is_canwu == 0:
                    return {
                        'is_cultivating': False,
                        'role_id': None,
                        'remaining_time': 0,
                        'exp': 0
                    }

                current_time = int(time.time())
                remaining_time = canwu_remaining_seconds(cw_timestamp, cw_duration, current_time)

                role_name = await role_id_to_name(cw_role)

                return {
                    'is_cultivating': True,
                    'role_id': cw_role,
                    'role_name': role_name,
                    'remaining_time': remaining_time,
                    'exp': cw_exp
                }
            return None


# ================================
# 主菜单功能
# ================================

@pd_reg_func
async def show_main_menu(uid, qz):
    """
    显示主菜单
    指令：菜单 / MENU / 主菜单

    视觉设计：
    - 顶部显示玩家信息和资产
    - 按系统分组显示功能
    - 每行最多3个按钮
    - 使用emoji增强视觉效果
    """
    player_info = await get_player_basic_info(uid)
    if player_info is None:
        return {"type": "markdown", "content": "##### ⚠️ 未注册游戏\n\n欢迎来到问道诸天文游！\n\n请先注册游戏开始你的修仙之旅：\n\n***\n\n<qqbot-cmd-input text='注册游戏 ' show='✏️ 注册游戏*' />\n\n**Tips：** 点击按钮后输入你的玩家名称（2-8个字符）"}

    role_info = await get_current_role_info(uid)

    if role_info:
        role_display = f"{role_info['name']} Lv.{role_info['level']} [{role_info['stage']}]"
    else:
        role_display = "未出战角色"

    output = "##### 🏮 问道诸天｜主菜单\n\n"
    output += f"**玩家：** {player_info['name']}\n"
    output += f"**当前角色：** {role_display}\n"
    output += f"**灵石：** {player_info['lingshi']} | **仙玉：** {player_info['xianyu']}\n\n"
    output += "> 首页仅保留系统入口；进入对应「xx菜单」查看具体操作。\n\n"

    for title, description, entries in MAIN_MENU_SECTIONS:
        output += f"***\n\n**{title}**\n> {description}\n"
        output += _menu_rows(entries) + "\n\n"

    return {"type": "markdown", "content": output}


# ================================
# 子菜单功能
# ================================

@reg_xz_func
async def show_spirit_beast_menu(uid, qz):
    """灵兽相关指令统一入口，避免主菜单出现操作级按钮。"""
    output = "##### 🐾 灵兽菜单\n\n"
    output += "寻访灵兽、查看图鉴与设置出战灵兽都集中在此处；灵兽只从玩法中获得，不在商城出售。\n\n"
    output += "<qqbot-cmd-input text='灵兽' show='我的灵兽' /> | <qqbot-cmd-input text='灵兽图鉴' show='灵兽图鉴' />\n\n"
    output += "<qqbot-cmd-input text='灵兽寻访' show='每日寻访' /> | <qqbot-cmd-input text='灵兽出战 ' show='灵兽出战 编号*' />\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_estate_menu(uid, qz):
    """洞府建设与收取入口。洞府详情仍由原有“洞府”指令展示。"""
    output = "##### 🏡 洞府菜单\n\n"
    output += "洞府提供离线灵气。每日可选一次稳健收取或冒险共鸣；建筑升级只消耗灵石。\n\n"
    output += "<qqbot-cmd-input text='洞府' show='查看洞府' /> | <qqbot-cmd-input text='洞府收取 稳健' show='稳健收取' />\n\n"
    output += "<qqbot-cmd-input text='洞府收取 冒险' show='冒险共鸣' /> | <qqbot-cmd-input text='洞府升级 ' show='升级建筑*' />\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_party_menu(uid, qz):
    """群协作系统入口：队伍、阵法与三千道途。"""
    output = "##### 👥 队伍菜单\n\n"
    output += "队伍与三千道途仅限群聊使用。先创建或加入队伍，再布阵并让全员准备。\n\n"
    output += "<qqbot-cmd-input text='队伍' show='查看队伍' /> | <qqbot-cmd-input text='队伍创建' show='创建队伍' />\n\n"
    output += "<qqbot-cmd-input text='队伍加入 ' show='加入队伍 队伍码*' /> | <qqbot-cmd-input text='队伍准备' show='确认准备' />\n\n"
    output += "<qqbot-cmd-input text='布阵 ' show='布阵 阵法-位置*' /> | <qqbot-cmd-input text='队伍离开' show='离开队伍' />\n\n"
    output += "<qqbot-cmd-input text='道途' show='三千道途' /> | <qqbot-cmd-input text='道途开启' show='队长开启道途' />\n\n"
    output += "<qqbot-cmd-input text='队伍战斗' show='开启队伍战斗' /> | <qqbot-cmd-input text='队伍战斗状态' show='队伍战斗状态' />\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_sect_menu(uid, qz):
    """宗门与师徒的聚合入口。"""
    output = "##### 🏯 宗门菜单\n\n"
    output += "完成每日委托获得贡献，投票决定下周 PVE 便利研究；师徒之间不转移任何装备或货币。\n\n"
    output += "<qqbot-cmd-input text='宗门' show='我的宗门' /> | <qqbot-cmd-input text='宗门列表' show='宗门列表' />\n\n"
    output += "<qqbot-cmd-input text='宗门创建 ' show='创建宗门*' /> | <qqbot-cmd-input text='宗门委托' show='宗门委托' />\n\n"
    output += "<qqbot-cmd-input text='师徒进度' show='师徒进度' /> | <qqbot-cmd-input text='师徒修行' show='师徒修行' />\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_role_special_menu(uid, qz):
    """角色专属战斗养成入口；具体内容随当前出战角色切换。"""
    output = "##### ⚔️ 专属养成菜单\n\n"
    output += "当前出战角色的专属材料、图鉴、进阶、组合与排行均在此处；先在副本或世界 Boss 中获得对应养成资源。\n\n"
    output += "<qqbot-cmd-input text='角色养成' show='当前角色养成' /> | <qqbot-cmd-input text='专属图鉴' show='专属图鉴' />\n\n"
    output += "<qqbot-cmd-input text='专属进阶' show='专属进阶' /> | <qqbot-cmd-input text='专属排行榜' show='专属排行榜' />\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_wish_menu(uid, qz):
    """仙玉祈愿、角色碎片与记录入口。"""
    output = "##### ✨ 仙玉祈愿菜单\n\n"
    output += "消耗仙玉获取角色碎片、当前出战角色专属养成碎片，并固定获得经验与本源材料。\n\n"
    output += "<qqbot-cmd-input text='仙玉祈愿' show='祈愿首页' /> | <qqbot-cmd-input text='仙玉祈愿 1次' show='祈愿1次' />\n\n"
    output += "<qqbot-cmd-input text='仙玉祈愿 10次' show='祈愿10次' /> | <qqbot-cmd-input text='祈愿定向 ' show='设置定向角色*' />\n\n"
    output += "<qqbot-cmd-input text='角色碎片' show='角色碎片' /> | <qqbot-cmd-input text='祈愿记录' show='祈愿记录' />\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"
    return {"type": "markdown", "content": output, "keyboard_commands": (
        ("仙玉祈愿", "祈愿首页"), ("仙玉祈愿 1次", "祈愿1次"),
        ("仙玉祈愿 10次", "祈愿10次"), ("角色碎片", "角色碎片"),
        ("祈愿记录", "祈愿记录"), ("主菜单", "主菜单"),
    )}


@pd_reg_func
async def show_resource_menu(uid, qz):
    """资源、背包、药园和炼丹的聚合入口。"""
    output = "##### 📦 资源菜单\n\n"
    output += "管理物品与货币，进入药园与炼丹子菜单处理长期资源生产。\n\n"
    output += "<qqbot-cmd-input text='物品背包' show='物品背包' /> | <qqbot-cmd-input text='商城' show='灵石商城' />\n\n"
    output += "<qqbot-cmd-input text='药园菜单' show='药园菜单' /> | <qqbot-cmd-input text='炼丹菜单' show='炼丹菜单' />\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"
    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_activity_menu(uid, qz):
    """周期性挑战与长期目标的聚合入口。"""
    output = "##### 🌌 活动菜单\n\n"
    output += "参与世界 Boss 获取贡献与专属感悟；赛季记录长期目标与外观、称号资格。\n\n"
    output += "<qqbot-cmd-input text='世界BOSS' show='世界Boss' /> | <qqbot-cmd-input text='赛季' show='赛季主页' />\n\n"
    output += "<qqbot-cmd-input text='世界排行' show='世界排行' /> | <qqbot-cmd-input text='赛季任务' show='赛季任务' />\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"
    return {"type": "markdown", "content": output}

@reg_xz_func
async def show_role_menu(uid, qz):
    """
    显示角色子菜单
    指令：角色菜单
    """
    role_info = await get_current_role_info(uid)

    if role_info:
        role_display = f"当前出战角色：{role_info['name']} Lv.{role_info['level']} 『{role_info['stage']}』"
    else:
        role_display = "当前没有出战角色\n> 请先在角色背包中选择角色出战"

    output = "##### 角色菜单\n\n"
    output += f"{role_display}\n\n"
    output += "***\n\n"

    output += "<qqbot-cmd-input text='选择角色' show='选择角色 角色名称' />\n"
    output += "> 点击蓝字后输入想选择的角色名称，如：选择角色 王林\n\n"
    output += "<qqbot-cmd-input text='角色介绍' show='角色介绍 角色名称' />\n"
    output += "> 点击蓝字后输入想了解的角色名称，如：角色介绍 韩立\n\n"
    output += "<qqbot-cmd-input text='玩法介绍' show='玩法介绍 角色名称' />\n"
    output += "> 查看角色专属战斗养成路线，如：玩法介绍 萧炎\n\n"
    output += "<qqbot-cmd-input text='祈愿菜单' show='仙玉祈愿' />\n"
    output += "> 定向获取角色碎片，集齐10个可合成新角色\n\n"
    output += "<qqbot-cmd-input text='角色背包' show='角色背包 页码' />\n"
    output += "> 点击蓝字后输入页码可查看角色背包的第X页，如：角色背包1\n\n"
    output += "<qqbot-cmd-input text='角色属性' show='角色属性' />\n"
    output += "> 点击蓝字后输入角色编号可查看背包角色的具体属性，如：角色属性 10001\n\n"
    output += "<qqbot-cmd-input text='当前角色' show='当前角色' />\n"
    output += "> 点击蓝字后发送可查看当前出战角色属性，示例：当前角色\n\n"
    output += "<qqbot-cmd-input text='悟道进阶' show='悟道进阶' />\n"
    output += "> 当前角色等级达到境界巅峰时，可发送'悟道进阶'，突破下个境界\n\n"
    output += "<qqbot-cmd-input text='出战' show='出战 角色编号' />\n"
    output += "> 点击蓝字后输入角色编号可出战该角色，示例：出战 10001\n\n"
    output += "<qqbot-cmd-input text='收回' show='收回' />\n"
    output += "> 点击蓝字后发送可收回已出战角色，示例：收回\n\n"
    output += "<qqbot-cmd-input text='物品背包' show='物品背包 页码' />\n"
    output += "> 点击蓝字后输入页码可查看物品背包的第X页，如：物品背包1\n\n"
    output += "<qqbot-cmd-input text='物品信息' show='物品信息 物品名称' />\n"
    output += "> 点击蓝字后输入物品名称可查看物品详细信息，如：物品信息 星辰砂\n\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"

    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_cultivation_menu(uid, qz):
    """
    显示参悟系统子菜单
    指令：参悟菜单
    """

    cultivation_status = await get_cultivation_status(uid)

    if cultivation_status is None or not cultivation_status['is_cultivating']:
        status_info = "当前没有角色在参悟\n> 请先选择角色出战，然后开始参悟"
    else:
        status_info = f"> 当前参悟角色：{cultivation_status['role_name']}\n"
        status_info += f"> 参悟剩余时间：{cultivation_status['remaining_time']}秒\n"
        status_info += f"> 预计获得经验：{cultivation_status['exp']}"

    output = "##### 🧘 修炼系统\n\n"
    output += f"{status_info}\n\n"
    output += "***\n\n"

    output += "<qqbot-cmd-input text='参悟' show='参悟' />\n\n"
    output += "> 点击后发送可开始挂机参悟，攒经验\n"
    output += "<qqbot-cmd-input text='参悟状态' show='参悟状态' />\n\n"
    output += "> 点击后发送可查看当前角色参悟状态\n"
    output += "<qqbot-cmd-input text='领取参悟经验' show='领取参悟经验' />\n\n"
    output += "> 点击后发送可领取当前角色参悟所得经验\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"

    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_benyuan_menu(uid, qz):
    """
    显示本源系统子菜单
    指令：本源菜单
    """

    benyuan_info = await get_benyuan_info(uid)

    if benyuan_info is None:
        status_info = "> 当前没有出战角色本源\n> 请先选择角色并创建本源"
    else:
        status_info = f"> 出战角色本源：『{benyuan_info['id']}』{benyuan_info['name']}\n"
        status_info += f"> 角色本源等级：{benyuan_info['level']}级\n"
        status_info += f"> 角色本源阶段：{benyuan_info['stage']}"

    output = "##### 本源菜单\n\n"
    output += f"{status_info}\n\n"
    output += "***\n\n"

    output += "<qqbot-cmd-input text='查看本源' show='查看本源' />\n\n"
    output += "> 点击后发送可查看当前本源加成以及本源等级、阶段等信息\n\n"
    output += "<qqbot-cmd-input text='本源升级' show='本源升级' />\n\n"
    output += "> 点击后发送可升级当前本源等级，记得先查看升级所需材料噢~\n\n"
    output += "<qqbot-cmd-input text='本源技能' show='本源技能' />\n\n"
    output += "> 点击后发送可查看当前本源技能、解锁等级与技能特性\n\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"

    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_skill_menu(uid, qz):
    """
    显示技能系统子菜单
    指令：技能菜单
    """

    role_info = await get_current_role_info(uid)

    if role_info:
        role_display = f"> 当前出战角色：{role_info['name']} Lv.{role_info['level']} [{role_info['stage']}]"
    else:
        role_display = "> 当前没有出战角色\n> 请先在角色背包中选择角色出战"

    output = "##### 技能菜单\n\n"
    output += f"{role_display}\n\n"
    output += "***\n\n"

    output += "<qqbot-cmd-input text='激活技能 ' show='激活技能 技能名称' />\n\n"
    output += "> 点击后输入技能名称可激活该技能到你的技能背包中，示例：激活技能 吸掌\n"
    output += "<qqbot-cmd-input text='技能背包 ' show='技能背包' />\n\n"
    output += "> 点击后发送可查看技能背包内容，输入页码可查看指定页，如：技能背包 页码\n"
    output += "<qqbot-cmd-input text='技能信息 ' show='技能信息 技能名称' />\n\n"
    output += "> 点击后输入技能名称可查看技能详细信息，示例：技能信息 吸掌\n"
    output += "<qqbot-cmd-input text='卷轴信息 ' show='卷轴信息 卷轴名称' />\n\n"
    output += "> 点击后输入技能名称可查看技能卷轴详细信息，示例：卷轴信息 吸掌卷轴\n"
    output += "<qqbot-cmd-input text='技能装备 ' show='技能装备 技能槽编号-技能编号' />\n\n"
    output += "> 如：技能装备 1-10001，则是将技能编号10001装备到当前角色的技能槽1\n"
    output += "<qqbot-cmd-input text='技能卸下 ' show='技能卸下 技能槽编号' />\n\n"
    output += "> 如：技能卸下 1，则是将当前角色的技能槽1中所装备的技能卸下\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"

    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_equipment_menu(uid, qz):
    """
    显示装备系统子菜单
    指令：装备菜单
    """
    player_info = await get_player_basic_info(uid)

    output = "##### 🎒 装备系统\n\n"
    output += f"**灵石：** {player_info['lingshi']} | **仙玉：** {player_info['xianyu']}\n\n"
    output += "***\n\n"

    output += "<qqbot-cmd-input text='装备背包 ' show='装备背包 页码' />\n\n"
    output += "> 点击后发送可查看装备背包内容，输入页码可查看指定页，如：装备背包 2\n"
    output += "<qqbot-cmd-input text='当前装备' show='当前装备' />\n\n"
    output += "> 点击后发送可查看当前装备信息，查看装备套装加成等\n"
    output += "<qqbot-cmd-input text='穿戴装备 ' show='穿戴装备 装备编号' />\n\n"
    output += "> 点击后输入欲穿戴的装备编号，可将该装备穿戴到相应的部位，如：穿戴装备 10001\n"
    output += "<qqbot-cmd-input text='卸下装备 ' show='卸下装备 部位名' />\n\n"
    output += "> 点击后输入欲卸下装备的部位名称，可将该部位的装备卸下，如：卸下装备 铠甲\n"
    output += "<qqbot-cmd-input text='强化装备 ' show='强化装备 装备编号' />\n\n"
    output += "> 点击后输入欲强化的装备编号，可强化该装备，如：强化装备 10001\n"
    output += "<qqbot-cmd-input text='装备详情 ' show='装备详情 装备编号' />\n\n"
    output += "> 点击后输入欲查看的装备编号，可查看该装备详细信息，如：装备详情 10001\n"
    output += "<qqbot-cmd-input text='出售装备 ' show='出售装备 装备编号' />\n\n"
    output += "> 点击后输入欲出售的装备编号，可出售该装备为灵石，如：出售装备 10001\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"

    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_dungeon_menu(uid, qz):
    """
    显示副本挑战子菜单
    指令：副本菜单
    """
    from Game_main.g6_dungeon import get_daily_remaining_count

    role_info = await get_current_role_info(uid)
    remaining_count = await get_daily_remaining_count(uid)

    if role_info:
        role_display = f"{role_info['name']} Lv.{role_info['level']} [{role_info['stage']}]"
    else:
        role_display = "未出战角色"

    output = "##### 副本菜单\n\n"
    output += f"**当前角色：** {role_display}\n"
    output += f"**剩余挑战次数：** {remaining_count}/20\n\n"
    output += "***\n\n"

    output += "<qqbot-cmd-input text='副本列表' show='副本列表' />\n"
    output += "> 点击后发送可查看当前可挑战的副本列表\n\n"
    output += "<qqbot-cmd-input text='副本信息 ' show='副本信息 副本编号' />\n"
    output += "> 点击后输入副本编号，可查看该副本的详细信息，如：副本信息 1\n\n"
    output += "<qqbot-cmd-input text='挑战副本 ' show='挑战副本 副本编号' />\n"
    output += "> 点击后输入副本编号，可进入副本进行挑战。如：挑战副本 1\n\n"
    output += "<qqbot-cmd-input text='怪物列表' show='怪物列表' />\n"
    output += "> 点击后发送可查看当前副本中可挑战的怪物。\n\n"
    output += "<qqbot-cmd-input text='挑战怪物 ' show='挑战怪物 怪物编号' />\n"
    output += "> 点击后输入怪物编号，可指定挑战此怪物。如：挑战怪物 1\n\n"
    output += "<qqbot-cmd-input text='战斗状态' show='战斗状态' />\n"
    output += "> 查看进行中的回合战斗；每回合可选择普攻、防御、调息、御器或已装备技能。\n\n"
    output += "<qqbot-cmd-input text='放弃副本' show='放弃副本' />\n"
    output += "> 三十六计跑为上策，保命逃跑，放弃挑战。\n\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"

    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_yaoyuan_menu(uid, qz):
    """
    显示药园炼丹子菜单
    指令：药园菜单
    """
    player_info = await get_player_basic_info(uid)
    role_info = await get_current_role_info(uid)

    if role_info:
        role_display = f"{role_info['name']} Lv.{role_info['level']} [{role_info['stage']}]"
    else:
        role_display = "未出战角色"

    output = "##### 🌿 药园菜单\n\n"
    output += f"**当前角色：** {role_display}\n"
    output += f"**灵石：** {player_info['lingshi']} | **仙玉：** {player_info['xianyu']}\n\n"
    output += "***\n\n"

    output += "<qqbot-cmd-input text='药园' show='药园' />\n\n"
    output += "> 查看药田状态、成熟进度、解锁情况\n\n"
    output += "<qqbot-cmd-input text='种子商店' show='种子商店' />\n\n"
    output += "> 购买种子，指令示例：购买种子 冰灵焰草种子-5\n\n"
    output += "<qqbot-cmd-input text='购买种子 ' show='购买种子 种子名-数量' />\n\n"
    output += "> 指令示例：购买种子 冰灵焰草种子-5\n\n"
    output += "<qqbot-cmd-input text='种子背包' show='种子背包' />\n\n"
    output += "> 查看您当前持有的种子数量\n\n"
    output += "<qqbot-cmd-input text='播种 ' show='播种 种子名-田号' />\n\n"
    output += "> 指令示例：播种 冰灵焰草种子-1\n\n"
    output += "<qqbot-cmd-input text='一键播种 ' show='一键播种 种子名' />\n\n"
    output += "> 指令示例：一键播种 冰灵焰草种子\n\n"
    output += "<qqbot-cmd-input text='采摘 ' show='采摘 田号' />\n\n"
    output += "> 指令示例：采摘 1\n\n"
    output += "<qqbot-cmd-input text='一键采摘' show='一键采摘' />\n\n"
    output += "> 一键采摘您当前的所有药田的药材\n\n"
    output += "<qqbot-cmd-input text='施肥 ' show='施肥 田号' />\n\n"
    output += "> 消耗『灵草培育液』（或旧版植物肥料）使药材立即成熟；可在商城购买，示例：施肥 1\n\n"
    output += "<qqbot-cmd-input text='商城' show='商城' />\n\n"
    output += "> 商城出售体力药、灵草培育液与炼丹加速卡等便利道具\n\n"
    output += "<qqbot-cmd-input text='解锁药田 ' show='解锁药田 田号' />\n\n"
    output += "> 消耗仙玉解锁药田，指令示例：解锁药田 1\n\n"
    output += "<qqbot-cmd-input text='出售药材 ' show='出售药材 药材名-数量' />\n\n"
    output += "> 指令示例：出售药材 冰灵焰草-10\n\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"

    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_liandan_menu(uid, qz):
    """
    显示炼丹子菜单
    指令：炼丹菜单
    """
    player_info = await get_player_basic_info(uid)
    role_info = await get_current_role_info(uid)

    if role_info:
        role_display = f"{role_info['name']} Lv.{role_info['level']} [{role_info['stage']}]"
    else:
        role_display = "未出战角色"

    output = "##### 🌿 炼丹菜单\n\n"
    output += f"**当前角色：** {role_display}\n"
    output += f"**灵石：** {player_info['lingshi']} | **仙玉：** {player_info['xianyu']}\n\n"
    output += "***\n\n"

    output += "<qqbot-cmd-input text='查看丹炉' show='查看丹炉' />\n\n"
    output += "> 查看丹炉状态、解锁条件、炼制进度\n\n"
    output += "<qqbot-cmd-input text='丹方列表' show='丹方列表' />\n\n"
    output += "> 查看可炼制丹方（通用 + 当前世界专属）\n\n"
    output += "<qqbot-cmd-input text='炼丹 ' show='炼丹 丹方名-炉号' />\n\n"
    output += "> 指令示例：炼丹 九转丹-1（也支持丹药名）\n\n"
    output += "<qqbot-cmd-input text='收丹 ' show='收丹 炉号' />\n\n"
    output += "> 指令示例：收丹 1\n\n"
    output += "<qqbot-cmd-input text='一键收丹' show='一键收丹' />\n\n"
    output += "> 一键收取您丹炉中炼制好的丹药。\n\n"
    output += "<qqbot-cmd-input text='服丹 ' show='服丹 丹药名-数量' />\n\n"
    output += "> 指令示例：服丹 九转丹-10\n\n"
    output += "<qqbot-cmd-input text='解锁丹炉 ' show='解锁丹炉 炉号' />\n\n"
    output += "> 消耗仙玉解锁丹炉，指令示例：解锁丹炉 4\n\n"
    output += "<qqbot-cmd-input text='加速炼丹 ' show='加速炼丹 炉号' />\n\n"
    output += "> 消耗物品『炼丹加速卡』用于加速丹药炼制速度，可在商城购买，示例：加速炼丹 1\n\n"
    output += "<qqbot-cmd-input text='商城' show='商城' />\n\n"
    output += "> 商城出售炼丹与突破所需的便利道具\n\n"
    output += "<qqbot-cmd-input text='添火次数' show='添火次数' />\n\n"
    output += "> 查看你今日主动添火/被添火次数。\n\n"
    output += "<qqbot-cmd-input text='添火 ' show='添火 目标UID(可选-炉号)' />\n\n"
    output += "> 可用“添火 目标UID”自动选炉，或“添火 目标UID-炉号”指定丹炉；每次减少30分钟\n\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"

    return {"type": "markdown", "content": output}


@reg_xz_func
async def show_power_menu(uid, qz):
    """
    显示排行榜子菜单
    指令：排行菜单
    """
    player_info = await get_player_basic_info(uid)
    role_info = await get_current_role_info(uid)

    output = "##### 战力菜单\n\n"
    output += f"**玩家：** {player_info['name']}\n"
    output += f"**UID：** {uid}\n"

    if role_info:
        output += f"**当前角色：** {role_info['name']} Lv.{role_info['level']}\n"

    output += f"**灵石：** {player_info['lingshi']}\n"
    output += f"**仙玉：** {player_info['xianyu']}\n\n"
    output += "***\n\n"

    output += "<qqbot-cmd-input text='我的战力' show='我的战力' />\n"
    output += "> 点击后发送可查看当前您出战角色的战力组成\n\n"
    output += "<qqbot-cmd-input text='战力排行' show='战力排行' />\n"
    output += "> 点击后发送可选择当前全服/各个角色的战力排行榜\n\n"
    output += "<qqbot-cmd-input text='战力排行 全服' show='战力排行 全服' />\n"
    output += "> 点击后发送可查看当前全服战力排行榜\n\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' />"

    return {"type": "markdown", "content": output}


# ================================
# 帮助功能
# ================================

async def show_help(uid):
    """
    显示游戏帮助信息
    指令：帮助 / HELP
    """
    return await show_game_guide(uid)


async def show_update_log(uid):
    """显示当前线上版本的玩家可见更新内容。"""
    output = "##### 📜 更新日志｜v1.22\n\n"
    output += "**⚔️ 角色专属战斗养成开放**\n> 萧炎、王林、韩立、石昊、叶凡、孟川均拥有独立成长路线、专属能力与组合玩法。发送“玩法介绍 角色名”可查看详细说明。\n\n"
    output += "**🗂️ 主菜单焕新**\n> 首页已按角色养成、战斗与资源、社交与活动、指引与记录分区；先进入对应“xx菜单”，再选择具体操作。\n\n"
    output += "**⚔️ 战斗与炼丹体验优化**\n> 队伍战斗中暂未行动的队友会自动防御；炼丹可选择保守、均衡或冒险火候，并受品质、产量与耐药效果影响。\n\n"
    output += "**🐾 灵兽园开放**\n> 完成副本后每日可寻访灵兽；可设置出战灵兽并获得透明的战斗灵契加成。灵兽不在商城出售。\n\n"
    output += "**🧭 三千道途开放**\n> 2~4 名已准备的同群道友可挑战 6 节异步秘境；每节投票一次，超时沿用上次偏好，节点奖励与因果印记均可追溯。\n\n"
    output += "**🏯 宗门与师徒开放**\n> 可创建或加入宗门、完成每日委托、参与周研究投票；师徒契约支持申请、收徒与共同修行，且没有资产转移。\n\n"
    output += "**🌌 世界Boss与赛季开放**\n> 世界 Boss 提供挑战、辅助、净化三类贡献；副本、宗门委托和世界 Boss 均会累积赛季经验，可获取外观与称号资格。\n\n"
    output += "**✨ 操作体验改进**\n> 常用操作会以正文蓝字或底部按钮呈现：导航与列表保持贴近说明，战斗和世界 Boss 的关键操作可直接点击。\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' /> | <qqbot-cmd-input text='玩法介绍' show='玩法介绍' />"
    return {"type": "markdown", "content": output}


async def show_game_guide(uid):
    """
    显示游戏玩法介绍
    指令：玩法介绍 / 新手攻略 / 游戏指南
    """
    output = "##### 📚 玩法介绍\n\n"

    output += "**🎯 游戏目标：**\n"
    output += "> 收集六大主角，挑战副本，提升战力，成为巅峰强者！\n\n"

    output += "**📖 基础入门：**\n\n"
    output += "**第一步：注册角色**\n"
    output += "> 发送 `注册游戏 你的名字` 创建游戏账号\n\n"
    output += "**第二步：选择主角**\n"
    output += "> 发送 `选择角色 萧炎` 选择你的第一位主角\n"
    output += "> 可选主角：萧炎、王林、韩立、石昊、叶凡、孟川\n\n"
    output += "**第三步：开始修炼**\n"
    output += "> 发送 `参悟` 开始挂机修炼，获得经验和灵石\n"
    output += "> 发送 `参悟状态` 查看修炼进度\n"
    output += "> 修炼完成后发送 `领取参悟经验` 获得奖励\n\n"

    output += "***\n\n"

    output += "**⚔️ 副本系统：**\n\n"
    output += "> `副本列表` - 查看所有可挑战副本\n"
    output += "> `挑战副本 X` - 挑战第X个副本\n"
    output += "> 每个副本有多波怪物，击败所有波次通关\n"
    output += "> 通关副本可获得灵石、装备和材料\n\n"

    output += "**⚙️ 装备系统：**\n\n"
    output += "> `装备背包` - 查看背包中的装备\n"
    output += "> `穿戴装备 X` - 穿戴ID为X的装备\n"
    output += "> 装备分为白、绿、蓝、紫、橙五种品质\n"
    output += "> 装备可强化提升属性，套装效果激活更强战力\n\n"

    output += "**🌿 药园炼丹：**\n\n"
    output += "> `药园` - 查看药田状态，播种/采摘灵草\n"
    output += "> `种子商店` - 购买种子，发展药园产出\n"
    output += "> `查看丹炉` - 管理丹炉炼制进度\n"
    output += "> `丹方列表` - 查看可炼制丹药\n"
    output += "> `服丹 X-数量` - 服用丹药永久提升属性\n\n"

    output += "**🔮 技能系统：**\n\n"
    output += "> `技能背包` - 查看已拥有的技能\n"
    output += "> `激活技能 X` - 激活ID为X的技能\n"
    output += "> `技能装备 X` - 装备技能到技能槽位\n"
    output += "> 每个主角有专属技能，技能可融合升级\n\n"

    output += "***\n\n"

    output += "**💎 本源系统：**\n\n"
    output += "> `查看本源` - 查看角色本源等级\n"
    output += "> `本源升级` - 消耗灵石提升本源\n"
    output += "> 本源提升大幅增加角色属性\n\n"

    output += "**📊 战力系统：**\n\n"
    output += "> `我的战力` - 查看当前战力详情\n"
    output += "> `战力排行` - 查看全服战力排行榜\n"
    output += "> 战力由基础、等级、装备、本源、技能构成\n\n"

    output += "**🏆 修练系统：**\n\n"
    output += "> `悟道进阶` - 提升角色境界\n"
    output += "> 境界越高，角色属性加成越多\n\n"

    output += "***\n\n"

    output += "**💡 实用技巧：**\n\n"
    output += "> 1. 每天记得领取参悟经验，经验会累积\n"
    output += "> 2. 优先强化武器和防具，提升输出和生存\n"
    output += "> 3. 注意技能搭配，不同技能有不同效果\n"
    output += "> 4. 套装装备有额外属性激活，多收集套装\n"
    output += "> 5. 挑战副本失败不扣除次数，可重复尝试\n\n"

    output += "**🔗 常用指令：**\n\n"
    output += "> `主菜单` - 打开游戏主菜单\n"
    output += "> `当前角色` - 查看角色属性\n"
    output += "> `角色背包` - 查看物品背包\n"
    output += "> `我的战力` - 查看战力详情\n\n"

    output += "***\n\n"
    output += "<qqbot-cmd-input text='主菜单' show='主菜单' /> | <qqbot-cmd-input text='更新日志' show='更新日志 v1.22' />"

    return {"type": "markdown", "content": output}
