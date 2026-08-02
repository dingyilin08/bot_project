from sql.mysql import *
from Tool.tool_user import *
from func.pd_func import *
from config import IMG_BASE_URL
import time
import random
from Tool.tool_command import *
from Game_main.g7_equip import calc_role_equip_bonus
from Game_domain.role_special_intro import render_role_special_intro
from Game_domain.role_grant_service import RoleGrantError, grant_role


ITEM_TYPE_NAMES = {
    1: "药材",
    2: "材料",
    3: "道具",
    4: "丹药",
    5: "装备材料",
    6: "宝石",
    7: "强化材料",
}
ITEM_TIER_NAMES = {1: "凡品", 2: "良品", 3: "精品", 4: "仙品"}
PILL_CATEGORY_NAMES = {1: "加成类", 2: "专属/突破类", 3: "特殊类"}
PILL_EFFECT_NAMES = {
    "gongji": "攻击",
    "fangyu": "防御",
    "qixue": "气血",
    "fali": "法力",
    "sudu": "速度",
    "baoji": "暴击",
    "baoshang": "暴伤",
    "shanbi": "闪避",
    "mingzhong": "命中",
    "pofang": "破防",
    "xixue": "吸血",
    "exp": "当前等级经验",
    "sell": "灵石",
    "breakthrough": "破境",
}
PILL_RATE_EFFECTS = {"baoji", "baoshang", "shanbi", "mingzhong", "pofang", "xixue"}


def _breakthrough_succeeds(roll, success_rate):
    """1-100 掷点不高于成功率时，判定悟道进阶成功。"""
    return int(roll) <= max(0, min(100, int(success_rate)))


def _display_number(value):
    """将数据库中的数值转成适合玩家阅读的简洁文本。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or 0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _display_rate_bonus(points):
    """概率属性以万分制存储；100 点等于面板上的 1%。"""
    return f"{_display_number(float(points) / 100)}%"


def _format_pill_effect(effect_types, effect_values, is_percent):
    """格式化 data_pill 中可逗号分隔的一个或多个丹药效果。"""
    type_list = [part.strip() for part in str(effect_types or "").split(",") if part.strip()]
    value_list = [part.strip() for part in str(effect_values or "").split(",") if part.strip()]
    effects = []
    for index, effect_type in enumerate(type_list):
        raw_value = value_list[index] if index < len(value_list) else "?"
        effect_name = PILL_EFFECT_NAMES.get(effect_type, effect_type)
        if raw_value == "?":
            effects.append(f"{effect_name}（数值未配置）")
            continue

        try:
            number = float(raw_value)
        except (TypeError, ValueError):
            effects.append(f"{effect_name} +{raw_value}")
            continue

        if effect_type == "breakthrough":
            effects.append("悟道进阶时自动消耗")
        elif effect_type == "sell":
            effects.append(f"使用后获得 {_display_number(number)} 灵石")
        elif effect_type in PILL_RATE_EFFECTS:
            if is_percent:
                # 兼容 0.001=0.1% 与 0.1=0.1% 两种历史配置。
                display_value = number * 100 if abs(number) <= 0.01 else number
            else:
                display_value = number / 100
            effects.append(f"{effect_name} +{_display_number(display_value)}%")
        elif is_percent:
            effects.append(f"{effect_name} +{_display_number(number)}%")
        else:
            effects.append(f"{effect_name} +{_display_number(number)}")
    return "、".join(effects) if effects else "效果暂未配置"


def _standard_item_record(row):
    if not row:
        return None
    name, item_type, description, access = row
    return {
        "name": name,
        "type_code": item_type,
        "type": ITEM_TYPE_NAMES.get(item_type, f"其他物品（类型{item_type}）"),
        "description": description or "暂无详细描述。",
        "access": access or "暂未配置获取途径。",
        "details": [],
        "commands": [],
    }


def _render_item_info(info):
    lines = [
        "##### 『物品信息』",
        "",
        f"**物品名称：** {info['name']}",
        f"**物品类型：** {info['type']}",
    ]
    for label, value in info.get("details", []):
        lines.append(f"**{label}：** {value}")
    lines.extend([
        "**物品描述：**",
        f"> {info['description']}",
        "**获取途径：**",
        f"> {info['access']}",
    ])
    commands = info.get("commands") or []
    if commands:
        lines.extend(["***", " | ".join(commands)])
    return "\n".join(lines) + "\n"


async def _query_item_info(cursor, item_name):
    """按普通物品、种子、药材、丹药目录统一查询物品详情。"""
    await cursor.execute(
        "SELECT `name`, `type`, `desc`, access FROM data_item WHERE `name` = %s LIMIT 1",
        (item_name,),
    )
    standard = _standard_item_record(await cursor.fetchone())

    # 普通材料、道具等只存在 data_item，命中后无需继续访问药园目录。
    if standard and standard["type_code"] not in (1, 4):
        return standard

    # 兼容尚未启用药园系统的旧数据库；已有的 data_item 物品仍可正常查看。
    await cursor.execute(
        """
        SELECT TABLE_NAME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN ('data_seed', 'data_herb', 'data_pill', 'data_recipe')
        """
    )
    catalog_tables = {row[0] for row in await cursor.fetchall()}

    # 种子不进入 user_item，因此没有 data_item 记录，需直接查询种子目录。
    if standard is None and "data_seed" in catalog_tables:
        await cursor.execute(
            "SELECT name, cl_name, price, tier, world FROM data_seed WHERE name = %s LIMIT 1",
            (item_name,),
        )
        seed = await cursor.fetchone()
        if seed:
            name, herb_name, price, tier, world = seed
            tier_name = ITEM_TIER_NAMES.get(tier, f"品阶{tier}")
            world_name = world or "诸天通用"
            shop_command = (
                f"<qqbot-cmd-input text='种子商店 {world}' show='查看种子商店' />"
                if world else "<qqbot-cmd-input text='种子商店' show='查看种子商店' />"
            )
            return {
                "name": name,
                "type": "种子",
                "description": f"{world_name}的{tier_name}种子，播种后可收获【{herb_name}】。",
                "access": f"前往种子商店购买，单价 {price} 灵石。",
                "details": [("所属世界", world_name), ("品阶", tier_name), ("成熟产物", herb_name)],
                "commands": [
                    f"<qqbot-cmd-input text='购买种子 {name}-1' show='购买×1' />",
                    shop_command,
                ],
            }

    if (standard is None or standard["type_code"] == 1) and "data_herb" in catalog_tables:
        await cursor.execute(
            "SELECT id, name, description, sell_price, tier, world FROM data_herb WHERE name = %s LIMIT 1",
            (item_name,),
        )
        herb = await cursor.fetchone()
        if herb:
            herb_id, name, description, sell_price, tier, world = herb
            seed_row = None
            if "data_seed" in catalog_tables:
                await cursor.execute(
                    "SELECT name FROM data_seed WHERE cl_id = %s OR cl_name = %s "
                    "ORDER BY (cl_id = %s) DESC, id ASC LIMIT 1",
                    (herb_id, name, herb_id),
                )
                seed_row = await cursor.fetchone()
            seed_name = seed_row[0] if seed_row else ""
            tier_name = ITEM_TIER_NAMES.get(tier, f"品阶{tier}")
            world_name = world or "诸天通用"
            if seed_name:
                access = f"在种子商店购买【{seed_name}】，于药园播种，成熟后采摘获得。"
                commands = [
                    f"<qqbot-cmd-input text='购买种子 {seed_name}-1' show='购买对应种子' />",
                    "<qqbot-cmd-input text='药园' show='前往药园' />",
                ]
            else:
                access = standard["access"] if standard else "通过药园种植并采摘获得。"
                commands = ["<qqbot-cmd-input text='药园' show='前往药园' />"]
            return {
                "name": name,
                "type": "药材",
                "description": description or (standard["description"] if standard else "暂无详细描述。"),
                "access": access,
                "details": [("所属世界", world_name), ("品阶", tier_name), ("出售价格", f"{sell_price} 灵石/株")],
                "commands": commands,
            }
        if standard:
            return standard

    if (standard is None or standard["type_code"] == 4) and "data_pill" in catalog_tables:
        await cursor.execute(
            """
            SELECT id, name, description, effect_type, effect_value,
                   is_percent, max_use, category, world
            FROM data_pill
            WHERE name = %s
            LIMIT 1
            """,
            (item_name,),
        )
        pill = await cursor.fetchone()
        if pill:
            pill_id, name, description, effect_type, effect_value, is_percent, max_use, category, world = pill
            recipes = []
            if "data_recipe" in catalog_tables:
                await cursor.execute(
                    """
                    SELECT name, ingredients, need_num, cost, world
                    FROM data_recipe
                    WHERE pill_id = %s
                    ORDER BY CASE WHEN world IS NULL OR world = '' THEN 0 ELSE 1 END, id ASC
                    """,
                    (pill_id,),
                )
                recipes = await cursor.fetchall()
            herb_ids = []
            for _, ingredients, _, _, _ in recipes:
                for raw_id in str(ingredients or "").split("|"):
                    if raw_id.strip().isdigit():
                        herb_ids.append(int(raw_id.strip()))

            herb_names = {}
            if herb_ids and "data_herb" in catalog_tables:
                unique_ids = list(dict.fromkeys(herb_ids))
                placeholders = ", ".join(["%s"] * len(unique_ids))
                await cursor.execute(
                    f"SELECT id, name FROM data_herb WHERE id IN ({placeholders})",
                    tuple(unique_ids),
                )
                herb_names = {int(row[0]): row[1] for row in await cursor.fetchall()}

            recipe_details = []
            for recipe_name, ingredients, need_num, cost, recipe_world in recipes:
                names = []
                for raw_id in str(ingredients or "").split("|"):
                    if raw_id.strip().isdigit():
                        herb_id = int(raw_id.strip())
                        names.append(herb_names.get(herb_id, f"药材#{herb_id}"))
                material_text = " + ".join(names) if names else "原料未配置"
                world_text = recipe_world or "通用"
                recipe_details.append(
                    f"【{recipe_name}】（{world_text}）：{material_text}，每种×{need_num}，消耗 {cost} 灵石"
                )

            if recipe_details:
                access = "在丹炉按对应丹方炼制获得：" + "；".join(recipe_details)
                first_recipe = recipes[0][0]
                commands = [
                    f"<qqbot-cmd-input text='炼丹 {first_recipe}-' show='炼制丹药' />",
                    "<qqbot-cmd-input text='丹方列表' show='查看丹方' />",
                ]
            else:
                access = standard["access"] if standard else "暂未配置可查询的获取途径。"
                commands = ["<qqbot-cmd-input text='丹方列表' show='查看丹方' />"]

            world_name = world or "诸天通用"
            use_limit = f"每名角色最多 {max_use} 枚" if max_use else "不限次数"
            return {
                "name": name,
                "type": "丹药",
                "description": description or (standard["description"] if standard else "暂无详细描述。"),
                "access": access,
                "details": [
                    ("所属世界", world_name),
                    ("丹药类别", PILL_CATEGORY_NAMES.get(category, f"类别{category}")),
                    ("服用效果", _format_pill_effect(effect_type, effect_value, bool(is_percent))),
                    ("服用上限", use_limit),
                ],
                "commands": commands,
            }
        if standard:
            return standard

    return standard


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
                line.append("<qqbot-cmd-input text='注册游戏' show='注册游戏' /> | <qqbot-cmd-input text='主菜单' show='主菜单' />")
                return {"type": "markdown", "content": "\n".join(line)}
            if len(player_name) > 8 or len(player_name) < 1:
                line.append(f"注意！！玩家名称长度需要在1-8个字符之间噢~")
                line.append('<qqbot-cmd-input text="注册游戏" show="注册游戏" /> | <qqbot-cmd-input text="主菜单" show="主菜单" />')
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
            line.append("◇ <qqbot-cmd-input text='角色介绍 萧炎' show='角色介绍 萧炎' />：异火焚天/斗帝传承")
            line.append("◇ <qqbot-cmd-input text='角色介绍 王林' show='角色介绍 王林' />：禁制大师/生死轮回")
            line.append("◇ <qqbot-cmd-input text='角色介绍 韩立' show='角色介绍 韩立' />：掌天瓶主/遁术无双")
            line.append("◇ <qqbot-cmd-input text='角色介绍 石昊' show='角色介绍 石昊' />：独断万古/至尊骨")
            line.append("◇ <qqbot-cmd-input text='角色介绍 叶凡' show='角色介绍 叶凡' />：圣体无双/九秘传承")
            line.append("◇ <qqbot-cmd-input text='角色介绍 孟川' show='角色介绍 孟川' />：刀意通神/雷霆灭世")
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
            sql = "SELECT id, `name`, gongji, fangyu, qixue, sudu, baoji, baoshang, max_fali, shanbi, mingzhong, pofang, xixue, world FROM data_role WHERE `name` = %s limit 1"
            await cursor.execute(sql, (role_name,))
            result = await cursor.fetchone()
            if result is None:
                line.append(f"你想选择的角色不存在！如果没有自己喜欢的角色，可以私信群主后续可能会一一添加噢~")
                line.append(f"当前可选择的角色有：")
                line.append("◇ <qqbot-cmd-input text='角色介绍 萧炎' show='角色介绍 萧炎' />：异火焚天/斗帝传承")
                line.append("◇ <qqbot-cmd-input text='角色介绍 王林' show='角色介绍 王林' />：禁制大师/生死轮回")
                line.append("◇ <qqbot-cmd-input text='角色介绍 韩立' show='角色介绍 韩立' />：掌天瓶主/遁术无双")
                line.append("◇ <qqbot-cmd-input text='角色介绍 石昊' show='角色介绍 石昊' />：独断万古/至尊骨")
                line.append("◇ <qqbot-cmd-input text='角色介绍 叶凡' show='角色介绍 叶凡' />：圣体无双/九秘传承")
                line.append("◇ <qqbot-cmd-input text='角色介绍 孟川' show='角色介绍 孟川' />：刀意通神/雷霆灭世")
                line.append("> 点击蓝字可查看详细的角色介绍噢~")
                line.append("<qqbot-cmd-input text='选择角色 ' show='选择角色' /> | <qqbot-cmd-input text='角色介绍 ' show='角色介绍*' />")
                return {"type": "markdown", "content": "\n".join(line)}
            role_template_id, role_name, gongji, fangyu, qixue, sudu, baoji, baoshang, max_fali, shanbi, mingzhong, pofang, xixue, world = result

            # 判断是否已选择角色
            sql = "SELECT openid, is_chushi FROM user_zt WHERE id = %s limit 1"
            await cursor.execute(sql, (uid,))
            openid, is_chushi = await cursor.fetchone()
            if is_chushi == 1:
                line.append(f"您已选择过角色啦，请勿重复选择！")
                line.append(f"不知道怎么玩？可以尝试发送：<qqbot-cmd-input text='主菜单' show='主菜单' />查看可用指令")
                line.append("<qqbot-cmd-input text='查看本源' show='查看本源' /> | <qqbot-cmd-input text='副本列表' show='副本列表' /> | <qqbot-cmd-input text='参悟' show='参悟' />")
                return {"type": "markdown", "content": "\n".join(line)}
            try:
                granted = await grant_role(cursor, uid=uid, role_template_id=role_template_id)
                role_id = granted["role_id"]
                stage = granted["stage"]
                await cursor.execute(
                    "UPDATE user_zt SET is_chushi = 1 WHERE id = %s AND is_chushi = 0",
                    (uid,),
                )
                if cursor.rowcount != 1:
                    raise RoleGrantError("初始角色状态已经变更，请勿重复选择。")
                await conn.commit()
            except RoleGrantError as exc:
                await conn.rollback()
                return {"type": "markdown", "content": f"##### ⚠️ 选择失败\n\n{exc}"}

            from Game_main.g16_onboarding import record_onboarding_event
            await record_onboarding_event(uid, "ROLE")

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
            special_intro = render_role_special_intro(role_name, include_actions=False)
            if special_intro:
                output += f"\n\n***\n\n{special_intro}"
                output += "\n\n> 先点击下方“出战”让该角色出战，再进入专属养成。"

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
            special_intro = render_role_special_intro(role_name)
            if special_intro:
                output += special_intro + "\n\n"
            output += f"<qqbot-cmd-input text='选择角色 {role_name}' show='选择角色 {role_name}' />\n"

            return {"type": "markdown", "content": output}


# 角色专属玩法介绍
@pd_reg_func
async def role_special_info(uid, qz, role_name):
    output = render_role_special_intro(role_name)
    if output is None:
        return {"type": "markdown", "content": qz + "该角色暂未开放专属战斗养成玩法。\n\n示例：玩法介绍 萧炎"}
    return {"type": "markdown", "content": qz + output}


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
            # 锁定该玩家当前角色和目标角色，避免并发切换产生多个出战角色。
            sql = "SELECT id, `name` FROM user_role WHERE uid = %s and is_chuzhan = 1 FOR UPDATE"
            await cursor.execute(sql, (uid, ))
            result = await cursor.fetchone()
            output = ""
            if result is not None:
                id, name = result
                if id == role_id:
                    return {"type": "markdown", "content": qz + "此角色当前已出战，无需重复出战。"}
                output += f"检测到您已有出战角色[{id}.{name}]，已自动将其收回。\n\n"
            sql = "SELECT id, name, world FROM user_role WHERE uid = %s and id = %s FOR UPDATE"
            await cursor.execute(sql, (uid, role_id))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您没有此角色，请输入正确的角色编号！\n\n示例：出战 10001"}
            role_id, role_name, role_world = result
            await cursor.execute("UPDATE user_role SET is_chuzhan = 0 WHERE uid = %s AND is_chuzhan = 1", (uid,))
            await cursor.execute("UPDATE user_role SET is_chuzhan = 1 WHERE id = %s AND uid = %s", (role_id, uid))

            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)
            await conn.commit()

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
            sql = "SELECT id, `name` FROM user_role WHERE uid = %s and is_chuzhan = 1 FOR UPDATE"
            await cursor.execute(sql, (uid, ))
            result = await cursor.fetchone()
            if result is None:
                return {"type": "markdown", "content": qz + "您没有出战角色，无需收回！"}
            role_id, name = result
            sql = "UPDATE user_role SET is_chuzhan = 0 WHERE id = %s"
            await cursor.execute(sql, (role_id,))
            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)
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

            # 原子扣除破境丹，避免“先检查后扣除”在并发请求下重复消耗。
            if not await cut_bag_item(uid, pojing_dan_id, 1, cursor=cursor):
                old_stage = await role_stage(role_name, dengji)
                output = f"##### 需要破境丹\n\n"
                output += f"您所出战的角色已至 **{dengji}级[{old_stage}]境巅峰**\n\n"
                output += f"欲突破至下一境界，需服用 **【{pojing_dan_name}】** 方可破境成功！\n\n"
                output += "该丹药可通过挑战对应世界副本概率获得。\n"
                return {"type": "markdown", "content": output}

            # 计算剩余经验（破境后经验不断累计，不清空）
            remaining_exp = exp - max_exp  # 计算溢出的经验
            if remaining_exp < 0:
                remaining_exp = 0

            old_stage = await role_stage(role_name, dengji)

            aaa = ""
            base_prob = 100 - (dengji // 10) * 10
            if await cut_bag_item(uid, 1, 1, cursor=cursor):
                base_prob += 50
                aaa = "> 检测到您背包中有[悟道天书]，已自动抵扣，提升悟道概率\n"
            base_prob = min(base_prob, 100)
            r = random.randint(1, 100)

            if not _breakthrough_succeeds(r, base_prob):
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
            from Tool.tool_power import update_role_power
            await update_role_power(conn, uid)
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
            output += f"> 暴击率+{_display_rate_bonus(add_baoji)} | 暴击伤害+{_display_rate_bonus(add_baoshang)}\n\n"
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
            count_sql = "SELECT COUNT(*) FROM user_role WHERE uid = %s and is_chuzhan = 0"
            await cursor.execute(count_sql, (uid,))
            a = await cursor.fetchone()
            total_records = a[0]
            if total_records == 0:
                return {"type": "markdown", "content": qz + "你的背包中暂无空闲角色！"}
            total_pages = (total_records + page_size - 1) // page_size
            page_num = min(page_num, total_pages)
            offset = (page_num - 1) * page_size
            sql = "SELECT id, `name`, dengji FROM user_role WHERE uid = %s and is_chuzhan = 0 LIMIT %s OFFSET %s"
            await cursor.execute(sql, (uid, page_size, offset))
            result = await cursor.fetchall()

            output = f"##### 角色背包({page_num}/{total_pages})\n"
            for i in result:
                role_id, role_name, dengji = i
                stage = await role_stage(role_name, dengji)
                role_button = f"<qqbot-cmd-input text='角色属性 {role_id}' show='角色属性 {role_id}' />"
                output += f"「{role_id}」 {role_button} Lv.{dengji}[{stage}]\n"

            output += f"***\n"

            sql = "SELECT lingshi, xianyu FROM user_zt WHERE id = %s LIMIT 1"
            await cursor.execute(sql, (uid,))
            lingshi, xianyu = await cursor.fetchone()
            output += f"**灵石：** {lingshi}\n**仙玉：** {xianyu}\n"

            output += f"***\n"

            output += pagination_controls("角色背包", page_num, total_pages)

            kj = await all_write_command(uid, (f"出战", "物品背包", "当前角色"))

            return {"type": "markdown", "content": output + kj}


def _item_info_button(item_name):
    return f"<qqbot-cmd-input text='物品信息 {item_name}' show='{item_name}' />"


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
            count_sql = "SELECT COUNT(*) FROM user_item WHERE uid = %s"
            await cursor.execute(count_sql, (uid,))
            a = await cursor.fetchone()
            total_records = a[0]
            if total_records == 0:
                return {"type": "markdown", "content": qz + "你的物品背包中暂无物品！"}
            total_pages = (total_records + page_size - 1) // page_size
            page_num = min(page_num, total_pages)
            offset = (page_num - 1) * page_size
            sql = "SELECT item_id, item_num FROM user_item WHERE uid = %s LIMIT %s OFFSET %s"
            await cursor.execute(sql, (uid, page_size, offset))
            result = await cursor.fetchall()

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
                item_button = _item_info_button(item_name)
                output += f"〔{item_type}〕{item_button}×{item_num}\n"

            output += f"> 点击蓝字可查看物品信息噢~\n"
            output += f"***\n"

            sql = "SELECT lingshi, xianyu FROM user_zt WHERE id = %s LIMIT 1"
            await cursor.execute(sql, (uid,))
            lingshi, xianyu = await cursor.fetchone()
            output += f"**灵石：** {lingshi}\n**仙玉：** {xianyu}\n"

            output += pagination_controls("物品背包", page_num, total_pages)

            kj = await all_write_command(uid, (f"角色背包", f"物品信息 {item_name}"))

            return {"type": "markdown", "content": output + kj}


# 物品信息
@reg_xz_func
async def item_info(uid, qz, item_name):
    item_name = str(item_name).strip()
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            info = await _query_item_info(cursor, item_name)
            if info is None:
                return {
                    "type": "markdown",
                    "content": qz + f"未找到【{item_name}】！请检查名称是否完整，可从物品背包、种子商店或丹方列表点击名称查询。",
                }

            output = _render_item_info(info)
            kj = await all_write_command(uid, ("物品背包", "角色背包", "当前角色"))
            return {"type": "markdown", "content": output + kj}
