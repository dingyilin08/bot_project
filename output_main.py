# -*- coding: utf-8 -*-
import asyncio
import os
import time
import re
from datetime import datetime

from Tool.tool_user import *
from config import is_image_mode, set_image_mode, ADMIN_PASSWORD

from Game_main.g1_role import *          # 角色
from Game_main.g2_canwu import *         # 参悟
from Game_main.g4_benyuan import *       # 本源
from Game_main.g5_skill import *         # 技能
from Game_main.g6_dungeon import *       # 副本
from Game_main.g7_equip import *         # 装备
from Game_main.g8_power import *         # 战力
from Game_main.g9_yaoyuan import *       # 药园炼丹
from Game_main.g10_shop import *         # 灵石商城
from Game_main.g11_battle import *       # 回合战斗
from Game_main.g0_menu import *          # 菜单系统

wuhouzhui = '收回|当前角色|参悟|参悟状态|领取参悟经验|悟道进阶|查看本源|本源升级|本源技能|战斗记录|战斗状态|查看怪物|怪物列表|放弃副本|药园|查看药田|种子背包|一键采摘|查看丹炉|一键收丹|添火次数|商城|菜单|MENU|主菜单|帮助|HELP|角色菜单|参悟菜单|装备菜单|本源菜单|技能菜单|副本菜单|药园菜单|炼丹菜单|装备菜单|战力菜单|玩法介绍|当前装备|我的战力|战力|新手攻略|游戏指南'
youhouzhui = '注册游戏|选择角色|角色介绍|角色属性|出战|角色背包|物品背包|物品信息|副本信息|副本列表|挑战副本|挑战怪物|战斗行动|激活技能|卷轴信息|技能信息|技能融合|技能装备|技能卸下|穿戴装备|卸下装备|强化装备|装备详情|出售装备|技能背包|装备背包|战力排行|排行榜|商城|购买商品|使用体力药|种子商店|购买种子|播种|一键播种|采摘|解锁药田|施肥|出售药材|丹方列表|炼丹|收丹|服丹|解锁丹炉|加速炼丹|添火|关闭图片模式|开启图片模式'

user_last_call_time = {}

async def jiance(message):
    # 定义要保留的字符范围的正则表达式模式
    message = message.upper()
    message = message.strip()
    pattern = re.compile(r'[^\u4E00-\u9FFF\da-zA-Z·-]', re.UNICODE)
    # 进行替换操作
    message = pattern.sub('', message)
    zz = ''
    hz = ''

    w_arr = wuhouzhui.split('|')
    for w_item in w_arr:
        if w_item == message:
            zz = w_item
            break
    if zz == '':
        y_arr = youhouzhui.split('|')
        for y_item in y_arr:
            if message.startswith(y_item):
                zz = y_item
                hz = message.replace(zz, '')
                break
    return zz, hz


async def is_txt_exist(file_name):
    """判断是否有txt文件，参数为txt文件名"""
    file_name = file_name.replace(" ", "")
    if os.path.exists(f"./menu/{file_name}.txt"):
        # 读取txt文件内容
        with open(f"./menu/{file_name}.txt", "r") as f:
            content = f.read()
        return content
    else:
        return False


# ==================== 图片模式（管理员功能） ====================

# 图片模式密令两步验证的待确认状态：{user_openid: 'close' | 'open'}
img_mode_pwd_pending = {}


def check_img_mode_pending(user_content, user_openid):
    """图片模式密令两步验证：若该用户处于待输入密令状态，校验其本条消息。
    返回处理结果文本；不在待验证状态则返回 None。
    需在限频与指令解析之前调用。"""
    action = img_mode_pwd_pending.pop(user_openid, None)
    if action is None:
        return None
    if user_content.upper() == ADMIN_PASSWORD.upper():
        if action == 'close':
            set_image_mode(False)
            return "✅ 密令正确，已切换为【纯文字回复模式】\n后续回复将不再加载图片。\n恢复图片模式请发送：开启图片模式"
        set_image_mode(True)
        return "✅ 密令正确，已恢复【图片回复模式】。"
    return "❌ 密令错误，已取消本次切换操作。"


def strip_image_tags(text):
    """移除文本中的 markdown 图片标签（![...](url)），并压缩因此产生的多余空行"""
    if not isinstance(text, str):
        return text
    cleaned = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned


def apply_image_mode(send_content):
    """根据图片模式处理回复内容：纯文字模式下去除所有图片标签（兼容str与dict返回值）"""
    if is_image_mode():
        return send_content
    if isinstance(send_content, dict):
        result = dict(send_content)
        if isinstance(result.get('content'), str):
            result['content'] = strip_image_tags(result['content'])
        return result
    if isinstance(send_content, str):
        return strip_image_tags(send_content)
    return send_content



async def content(con_arr0, con_arr1, openid):
    uid = await openid_to_uid(openid)
    if con_arr0 == '收回':
        return await sh_role(uid)
    elif con_arr0 == '当前角色':
        return await cz_role_attr(uid)
    elif con_arr0 == '参悟':
        return await canwu_role(uid)
    elif con_arr0 == '参悟状态':
        return await canwu_zt(uid)
    elif con_arr0 == '领取参悟经验':
        return await canwu_lq_exp(uid)
    elif con_arr0 == '悟道进阶':
        return await jinjie_role(uid)
    elif con_arr0 == '查看本源':
        return await ck_benyuan(uid)
    elif con_arr0 == '本源升级':
        return await up_benyuan(uid)
    elif con_arr0 == '本源技能':
        return await by_skill(uid)

    # ######################### ============== 分割线 ============= ################################### #

    elif con_arr0 == '注册游戏':
        if con_arr1 == "":
            return "指令错误，正确指令：注册游戏 玩家名称"
        return await user_zhuce(openid, con_arr1)
    elif con_arr0 == '选择角色':
        if con_arr1 == "":
            return "指令错误，正确指令：选择角色 角色名称"
        return await select_role(uid, con_arr1)
    elif con_arr0 == '角色介绍':
        if con_arr1 == "":
            return "指令错误，正确指令：角色介绍 角色名称"
        return await role_info(uid, con_arr1)
    elif con_arr0 == '角色属性':
        if con_arr1 == "":
            return "指令错误，正确指令：角色属性 角色编号"
        return await role_attr(uid, con_arr1)
    elif con_arr0 == '出战':
        if con_arr1 == "":
            return "指令错误，正确指令：出战 角色编号"
        return await cz_role(uid, con_arr1)
    elif con_arr0 == '物品信息':
        if con_arr1 == "":
            return "指令错误，正确指令：物品信息 物品名称"
        return await item_info(uid, con_arr1)
    elif con_arr0 == '物品背包':
        if con_arr1 == "":
            return await item_bag(uid, 1)
        return await item_bag(uid, con_arr1)
    elif con_arr0 == '商城':
        return await show_shop(uid, con_arr1 or 1)
    elif con_arr0 == '购买商品':
        if con_arr1 == "":
            return "指令错误，正确指令：购买商品 商品名-数量\n示例：购买商品 体力药-1"
        return await buy_shop_item(uid, con_arr1)
    elif con_arr0 == '使用体力药':
        if con_arr1 == "":
            return "指令错误，正确指令：使用体力药 数量\n示例：使用体力药 1"
        return await use_stamina_potion(uid, con_arr1)
    elif con_arr0 == '角色背包':
        if con_arr1 == "":
            return await role_bag(uid, 1)
        return await role_bag(uid, con_arr1)

    # ==================== 副本系统命令 ==================== #

    elif con_arr0 == '副本列表':
        if con_arr1 == "":
            return await dungeon_list(uid, 1)
        return await dungeon_list(uid, con_arr1)
    elif con_arr0 == '战斗记录':
        if con_arr1 == "":
            return await combat_history(uid, 10)
        return await combat_history(uid, con_arr1)
    elif con_arr0 == '战斗状态':
        return await battle_status(uid)
    elif con_arr0 == '副本信息':
        if con_arr1 == "":
            return "指令错误，正确指令：副本信息 副本ID\n示例：副本信息 1"
        return await dungeon_info(uid, con_arr1)
    elif con_arr0 == '挑战副本':
        if con_arr1 == "":
            return await challenge_dungeon(uid)
        return await start_challenge_dungeon(uid, con_arr1)
    elif con_arr0 == '查看怪物' or con_arr0 == '怪物列表':
        return await show_monster_list(uid)
    elif con_arr0 == '挑战怪物':
        if con_arr1 == "":
            return "指令错误，正确指令：挑战怪物 编号\n示例：挑战怪物 1"
        return await fight_monster(uid, con_arr1)
    elif con_arr0 == '战斗行动':
        if con_arr1 == "":
            return "指令错误，正确指令：战斗行动 普攻/防御/调息/御器/技能-编号"
        return await battle_action(uid, con_arr1)
    elif con_arr0 == '放弃副本':
        return await abandon_dungeon_cmd(uid)

    # ==================== 技能系统命令 ==================== #

    elif con_arr0 == '技能背包':
        if con_arr1 == "":
            return await skill_bag(uid, 1)
        return await skill_bag(uid, con_arr1)
    elif con_arr0 == '激活技能':
        if con_arr1 == "":
            return "指令错误，正确指令：激活技能 技能名称\n示例：激活技能 八极崩"
        return await jh_skill(uid, con_arr1)
    elif con_arr0 == '卷轴信息':
        if con_arr1 == "":
            return "指令错误，正确指令：卷轴信息 卷轴名称\n示例：卷轴信息 八极崩卷轴"
        return await jz_info(uid, con_arr1)
    elif con_arr0 == '技能信息':
        if con_arr1 == "":
            return "指令错误，正确指令：技能信息 技能名称\n示例：技能信息 八极崩"
        return await skill_info(uid, con_arr1)
    elif con_arr0 == '技能融合':
        if con_arr1 == "":
            return "指令错误，正确指令：技能融合 技能1-技能2\n示例：技能融合 1-2"
        return await fuse_skills(uid, con_arr1)
    elif con_arr0 == '技能装备':
        if con_arr1 == "":
            return "指令错误，正确指令：技能装备 技能槽-技能编号\n示例：技能装备 1-1"
        return await equip_skill(uid, con_arr1)
    elif con_arr0 == '技能卸下':
        if con_arr1 == "":
            return "指令错误，正确指令：技能卸下 技能槽号\n示例：技能卸下 1"
        return await unload_skill(uid, con_arr1)

    # ==================== 装备系统命令 ==================== #

    elif con_arr0 == '装备背包':
        if con_arr1 == "":
            return await equip_bag(uid, 1)
        return await equip_bag(uid, con_arr1)
    elif con_arr0 == '当前装备':
        return await current_equip(uid)
    elif con_arr0 == '穿戴装备':
        if con_arr1 == "":
            return "指令错误，正确指令：穿戴装备 装备编号\n示例：穿戴装备 1"
        return await wear_equip(uid, con_arr1)
    elif con_arr0 == '卸下装备':
        if con_arr1 == "":
            return "指令错误，正确指令：卸下装备 部位\n示例：卸下装备 武器"
        return await remove_equip(uid, con_arr1)
    elif con_arr0 == '强化装备':
        if con_arr1 == "":
            return "指令错误，正确指令：强化装备 装备编号\n示例：强化装备 1"
        return await enhance_equip(uid, con_arr1)
    elif con_arr0 == '装备详情':
        if con_arr1 == "":
            return "指令错误，正确指令：装备详情 装备编号\n示例：装备详情 1"
        return await equip_detail(uid, con_arr1)
    elif con_arr0 == '出售装备':
        if con_arr1 == "":
            return "指令错误，正确指令：出售装备 装备编号\n示例：出售装备 1"
        return await sell_equip(uid, con_arr1)

    # ==================== 药园炼丹系统命令 ==================== #

    elif con_arr0 == '药园' or con_arr0 == '查看药田':
        return await ck_yaotian(uid)
    elif con_arr0 == '种子背包':
        return await zz_beibao(uid)
    elif con_arr0 == '一键采摘':
        return await yj_caizhai(uid)
    elif con_arr0 == '种子商店':
        if con_arr1 == "":
            return await zz_shangdian(uid, 1)
        return await zz_shangdian(uid, con_arr1)
    elif con_arr0 == '购买种子':
        if con_arr1 == "":
            return "指令错误，正确指令：购买种子 种子名-数量\n示例：购买种子 冰灵焰草种子-5"
        return await gm_zhongzi(uid, con_arr1)
    elif con_arr0 == '播种':
        if con_arr1 == "":
            return "指令错误，正确指令：播种 种子名-田号\n示例：播种 冰灵焰草种子-1"
        return await bo_zhong(uid, con_arr1)
    elif con_arr0 == '一键播种':
        if con_arr1 == "":
            return "指令错误，正确指令：一键播种 种子名\n示例：一键播种 冰灵焰草种子"
        return await yj_bozhong(uid, con_arr1)
    elif con_arr0 == '采摘':
        if con_arr1 == "":
            return "指令错误，正确指令：采摘 田号\n示例：采摘 1"
        return await cai_zhai(uid, con_arr1)
    elif con_arr0 == '解锁药田':
        if con_arr1 == "":
            return "指令错误，正确指令：解锁药田 田号\n示例：解锁药田 6"
        return await js_yaotian(uid, con_arr1)
    elif con_arr0 == '施肥':
        if con_arr1 == "":
            return "指令错误，正确指令：施肥 田号\n示例：施肥 1"
        return await shi_fei(uid, con_arr1)
    elif con_arr0 == '出售药材':
        if con_arr1 == "":
            return "指令错误，正确指令：出售药材 药材名-数量\n示例：出售药材 冰灵焰草-10"
        return await sell_herb(uid, con_arr1)
    elif con_arr0 == '查看丹炉':
        return await ck_danlu(uid)
    elif con_arr0 == '一键收丹':
        return await yj_shoudan(uid)
    elif con_arr0 == '丹方列表':
        if con_arr1 == "":
            return await df_liebiao(uid, 1)
        return await df_liebiao(uid, con_arr1)
    elif con_arr0 == '炼丹':
        if con_arr1 == "":
            return "指令错误，正确指令：炼丹 丹方名-炉号（也支持丹药名）\n示例：炼丹 九转丹-1"
        return await lian_dan(uid, con_arr1)
    elif con_arr0 == '收丹':
        if con_arr1 == "":
            return "指令错误，正确指令：收丹 炉号\n示例：收丹 1"
        return await shou_dan(uid, con_arr1)
    elif con_arr0 == '服丹':
        if con_arr1 == "":
            return "指令错误，正确指令：服丹 丹药名-数量\n示例：服丹 九转丹-10"
        return await fu_dan(uid, con_arr1)
    elif con_arr0 == '解锁丹炉':
        if con_arr1 == "":
            return "指令错误，正确指令：解锁丹炉 炉号\n示例：解锁丹炉 4"
        return await js_danlu(uid, con_arr1)
    elif con_arr0 == '加速炼丹':
        if con_arr1 == "":
            return "指令错误，正确指令：加速炼丹 炉号\n示例：加速炼丹 1"
        return await js_liandan(uid, con_arr1)
    elif con_arr0 == '添火':
        if con_arr1 == "":
            return "指令错误，正确指令：添火 目标UID 或 添火 目标UID-炉号\n示例：添火 10086 或 添火 10086-1"
        return await th_liandan(uid, con_arr1)
    elif con_arr0 == '添火次数':
        return await ck_tianhuo_times(uid)

    # ==================== 管理员命令 ====================

    elif con_arr0 == '关闭图片模式':
        if con_arr1 == "":
            # 两步验证：先登记待确认状态，等待玩家下一条消息发送密令
            img_mode_pwd_pending[openid] = 'close'
            return "🔒 已进入密令验证，请直接发送管理员密令："
        if con_arr1.upper() == ADMIN_PASSWORD.upper():
            if not is_image_mode():
                return "当前已是纯文字回复模式，无需重复切换。"
            set_image_mode(False)
            return "✅ 密令正确，已切换为【纯文字回复模式】\n后续回复将不再加载图片。\n恢复图片模式请发送：开启图片模式"
        return "❌ 密令错误，切换失败！"
    elif con_arr0 == '开启图片模式':
        if con_arr1 == "":
            img_mode_pwd_pending[openid] = 'open'
            return "🔒 已进入密令验证，请直接发送管理员密令："
        if con_arr1.upper() == ADMIN_PASSWORD.upper():
            if is_image_mode():
                return "当前已是图片回复模式，无需重复切换。"
            set_image_mode(True)
            return "✅ 密令正确，已恢复【图片回复模式】。"
        return "❌ 密令错误，切换失败！"

    # ==================== 菜单系统命令 ==================== #

    elif con_arr0 == '菜单' or con_arr0 == 'MENU' or con_arr0 == '主菜单':
        return await show_main_menu(uid)
    elif con_arr0 == '帮助' or con_arr0 == 'HELP':
        return await show_help(uid)
    elif con_arr0 == '玩法介绍' or con_arr0 == '新手攻略' or con_arr0 == '游戏指南':
        return await show_game_guide(uid)
    elif con_arr0 == '角色菜单':
        return await show_role_menu(uid)
    elif con_arr0 == '参悟菜单':
        return await show_cultivation_menu(uid)
    elif con_arr0 == '装备菜单':
        return await show_equipment_menu(uid)
    elif con_arr0 == '副本菜单':
        return await show_dungeon_menu(uid)
    elif con_arr0 == '药园菜单':
        return await show_yaoyuan_menu(uid)
    elif con_arr0 == '炼丹菜单':
        return await show_liandan_menu(uid)
    elif con_arr0 == '本源菜单':
        return await show_benyuan_menu(uid)
    elif con_arr0 == '技能菜单':
        return await show_skill_menu(uid)
    elif con_arr0 == '战力菜单':
        return await show_power_menu(uid)

    # ==================== 战力系统命令 ==================== #

    elif con_arr0 == '我的战力' or con_arr0 == '战力':
        return await my_power(uid)
    elif con_arr0 == '战力排行' or con_arr0 == '排行榜':
        if con_arr1 == "":
            return await power_rank(uid)
        else:
            return await power_rank_detail(uid, con_arr1)

    else:
        return "指令错误，请检查指令后重试！"


async def output_content(user_content, user_openid, qun_openid=None):
    user_content = user_content.upper()

    # 图片模式密令两步验证（优先于限频与指令解析）
    pending_reply = check_img_mode_pending(user_content, user_openid)
    if pending_reply is not None:
        return pending_reply

    if await is_txt_exist(user_content):
        return await is_txt_exist(user_content)

    c_time = datetime.now().timestamp()

    if user_openid in user_last_call_time:
        time_diff = c_time - user_last_call_time[user_openid]
        if time_diff < 2:
            return "严重警告！你输入的指令过快！"
    user_last_call_time[user_openid] = c_time

    if user_content in ["1", "2", "3", "4", "5"] or re.match(r'^[1-5]-', user_content):
        user_content = await pd_command(user_openid, user_content)
        print(user_content)
        if user_content is False:
            return "该快捷指令不存在！"

    con_arr0, con_arr1 = await jiance(user_content)
    send_content = await content(con_arr0, con_arr1, user_openid)
    send_content = apply_image_mode(send_content)

    # 兼容dict返回值（Markdown格式）
    if isinstance(send_content, dict):
        return send_content
    else:
        send_content += "\n点击快捷指令按钮可自动执行此命令，如带有*则需输入相应后缀"
        return send_content

if __name__ == "__main__":
    while True:
        content1 = str(input("请输入命令调试："))
        print("------------------------------")

        send_content = asyncio.run((output_content(content1, "AC5EF3D2A47723672DB287CD216931A7")))

        print(send_content)
