import asyncio
from sql.mysql import *


# 计算角色境界
async def role_stage(name, dengji):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id FROM data_role WHERE `name` = %s limit 1"
            await cursor.execute(sql, (name,))
            result = await cursor.fetchone()
            role_id = result[0]

            stage_id = (dengji - 1) // 10 + 1
            stage_id = f"stage_{stage_id}"
            sql = f"SELECT {stage_id} FROM data_stage WHERE id = %s"
            await cursor.execute(sql, (role_id,))
            result = await cursor.fetchone()
            stage_name = f"{result[0]}境"
            return stage_name


# 计算升级所需经验
async def up_need_exp(dengji):
    stage_lvl = (dengji - 1) // 10 + 1
    exp_ranges = [
        # (阶段, 每级增量, 阶段起始经验, 阶段最大经验)
        (1,  800,    2000,    9200),       # Lv.1~10:  快速成长期
        (2,  2000,   12000,   30000),      # Lv.11~20: 入门期
        (3,  4500,   38000,   78500),      # Lv.21~30: 成长期
        (4,  8000,   95000,   167000),     # Lv.31~40: 发展期
        (5,  15000,  200000,  335000),     # Lv.41~50: 进阶期
        (6,  28000,  400000,  652000),     # Lv.51~60: 强化期
        (7,  50000,  780000,  1230000),    # Lv.61~70: 精英期
        (8,  90000,  1500000, 2310000),    # Lv.71~80: 大师期
        (9,  160000, 2800000, 4240000),    # Lv.81~90: 宗师期
        (10, 280000, 5200000, 7720000),    # Lv.91~100: 巅峰期
    ]

    for lvl, every, start, max_exp in exp_ranges:
        if lvl == stage_lvl:
            mini_stage_lvl = dengji % 10
            if dengji >= 100:
                return 0
            need_exp = every * mini_stage_lvl + start
            return need_exp

    return 0  # 兜底


# 通过UID判断玩家是否注册
async def uid_is_zhuce(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT `name` FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is not None:
                return True
            else:
                return False


# 通过openid判断玩家是否注册
async def openid_is_zhuce(openid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT `name` FROM user_zt WHERE openid = %s"
            await cursor.execute(sql, (openid,))
            result = await cursor.fetchone()
            if result is not None:
                return True
            else:
                return False


# openid 转 玩家UID
async def openid_to_uid(openid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id FROM user_zt WHERE openid = %s"
            await cursor.execute(sql, (openid,))
            result = await cursor.fetchone()
            if result is not None:
                return result[0]
            else:
                return None


# UID 转 openid
async def uid_to_openid(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT openid FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is not None:
                return result[0]
            else:
                return None


# UID 转 玩家名称
async def uid_to_name(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT `name` FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is not None:
                return result[0]
            else:
                return None


# 角色编号查询角色名称
async def role_id_to_name(role_id):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT `name` FROM user_role WHERE id = %s"
            await cursor.execute(sql, (role_id, ))
            result = await cursor.fetchone()
            if result is not None:
                return result[0]
            else:
                return False


# 前缀
async def qianzhui(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT id, `name` FROM user_zt WHERE id = %s"
            await cursor.execute(sql, (uid,))
            result = await cursor.fetchone()
            if result is not None:
                id = result[0]
                name = result[1]
                return f"To[{id}]{name}：\n"
            else:
                return "未注册"


# 技能名称查询
async def get_skill_name(cursor, skill_id):
    """统一的技能名称查询函数
    user_role.skill1_id 存储的是 user_skill.id，需要先查 user_skill 表
    """
    if skill_id is None:
        return None
    await cursor.execute(
        "SELECT skill_name FROM user_skill WHERE id = %s",
        (skill_id,)
    )
    result = await cursor.fetchone()
    return result[0] if result else None


# 升级
async def up_lvl(role_id, add_exp):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT `name`, uid, dengji, exp FROM user_role WHERE id = %s"
            await cursor.execute(sql, (role_id,))
            result = await cursor.fetchone()
            name, uid, dengji, exp = result[0], result[1], result[2], result[3]
            max_exp = await up_need_exp(dengji)
            now_exp = add_exp + exp - max_exp
            if now_exp < 0:
                now_exp = 0

            sql = """SELECT gongji, fangyu, qixue, baoji, baoshang,
                            mingzhong, shanbi, pofang, xixue
                     FROM data_role WHERE `name` = %s LIMIT 1"""
            await cursor.execute(sql, (name,))
            base = await cursor.fetchone()
            gongji, fangyu, qixue = base[0], base[1], base[2]
            baoji, baoshang = base[3], base[4]
            mingzhong, shanbi = base[5], base[6]
            pofang, xixue = base[7], base[8]

            add_gongji = int(gongji * 0.025)
            add_fangyu = int(fangyu * 0.015)
            add_qixue = int(qixue * 0.015)

            add_baoji = 15
            add_baoshang = 20
            add_mingzhong = 25
            add_shanbi = 15

            add_pofang = 0
            add_xixue = 0
            if (dengji + 1) % 10 == 0:
                add_pofang = 50
                add_xixue = 30

            sql = """UPDATE user_role SET
                        dengji = dengji + 1,
                        exp = %s,
                        gongji = gongji + %s,
                        fangyu = fangyu + %s,
                        qixue = qixue + %s,
                        baoji = baoji + %s,
                        baoshang = baoshang + %s,
                        mingzhong = mingzhong + %s,
                        shanbi = shanbi + %s,
                        pofang = pofang + %s,
                        xixue = xixue + %s
                     WHERE id = %s"""
            await cursor.execute(sql, (
                now_exp, add_gongji, add_fangyu, add_qixue,
                add_baoji, add_baoshang, add_mingzhong, add_shanbi,
                add_pofang, add_xixue, role_id
            ))
            await conn.commit()

        from Tool.tool_power import update_role_power
        await update_role_power(conn, uid)

        return add_gongji, add_fangyu, add_qixue


# 扣除物品
async def cut_bag_item(uid, item_id, num):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            # 使用原子更新操作，确保并发安全
            # 只有当物品数量充足时才执行扣除
            sql = "UPDATE user_item SET `item_num` = `item_num` - %s WHERE uid = %s and item_id = %s and `item_num` >= %s"
            await cursor.execute(sql, (num, uid, item_id, num))
            
            # 检查是否有行被更新
            if cursor.rowcount > 0:
                # 扣除成功
                await conn.commit()
                
                # 清理数量为0的记录（可选，保持与原逻辑一致）
                # 这一步不需要原子性，因为物品已经扣除成功
                sql_clean = "DELETE FROM user_item WHERE uid = %s and item_id = %s and `item_num` = 0"
                await cursor.execute(sql_clean, (uid, item_id))
                await conn.commit()
                
                return True
            else:
                # 扣除失败（数量不足或物品不存在）
                return False


# 添加物品
async def add_bag_item(uid, item_id, add_num):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            sql1 = "SELECT `item_num` FROM user_item WHERE uid = %s and item_id = %s"
            await cursor.execute(sql1, (uid, item_id))
            a = await cursor.fetchone()
            if a is None:
                sql2 = "INSERT INTO user_item (uid, item_id, item_num) VALUES (%s, %s, %s)"
                await cursor.execute(sql2, (uid, item_id, add_num))
                await conn.commit()
            else:
                sql = "UPDATE user_item SET `item_num` = `item_num` + %s WHERE uid = %s and item_id = %s"
                await cursor.execute(sql, (add_num, uid, item_id))
                await conn.commit()
            return True


# 判断背包中物品数量
async def pd_bag_num(uid, item_id, num):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            s = "SELECT item_num FROM user_item WHERE uid = %s and item_id = %s"
            await cursor.execute(s, (uid, item_id))
            result = await cursor.fetchone()
            if result is None:
                return False
            item_num = result[0]
            if item_num < num:
                return False
            return True


# 查询物品名称
async def get_item_name(cursor, item_id):
    """统一的物品名称查询函数"""
    await cursor.execute("SELECT `name` FROM data_item WHERE id = %s", (item_id,))
    result = await cursor.fetchone()
    return result[0] if result else None

