# -*- coding: utf-8 -*-
"""角色轮回规则与事务服务。"""

from sql.mysql import connect_mysql


MIN_REINCARNATION = 1
MAX_REINCARNATION = 9
REINCARNATION_LEVEL = 100
INHERIT_PERCENT = 10

ROLE_ATTRIBUTE_COLUMNS = (
    "gongji",
    "fangyu",
    "qixue",
    "fali",
    "sudu",
    "baoji",
    "baoshang",
    "shanbi",
    "mingzhong",
    "pofang",
    "xixue",
)

ROLE_ATTRIBUTE_NAMES = {
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
}

_schema_ready = False


class ReincarnationError(Exception):
    """可直接展示给玩家的轮回失败原因。"""


async def ensure_reincarnation_schema(cursor):
    """为旧服惰性补齐世数字段；每个进程只检查一次。"""
    global _schema_ready
    if _schema_ready:
        return
    await cursor.execute(
        """
        SELECT COUNT(1)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'user_role'
          AND COLUMN_NAME = 'reincarnation_count'
        """
    )
    if int((await cursor.fetchone())[0]) == 0:
        try:
            await cursor.execute(
                """
                ALTER TABLE user_role
                ADD COLUMN reincarnation_count TINYINT UNSIGNED NOT NULL DEFAULT 1
                COMMENT '角色当前世数，1至9'
                """
            )
        except Exception as exc:
            # 多进程首次请求可能同时补列；1060 表示另一进程已经完成迁移。
            error_code = exc.args[0] if getattr(exc, "args", ()) else None
            if str(error_code) != "1060":
                raise
    _schema_ready = True


def calculate_reincarnation_attributes(current_attributes, template_attributes):
    """以1级模板为底，叠加上一世裸属性的10%遗泽。"""
    inherited = {}
    reborn = {}
    for column in ROLE_ATTRIBUTE_COLUMNS:
        current_value = max(0, int(current_attributes.get(column, 0) or 0))
        template_value = max(0, int(template_attributes.get(column, 0) or 0))
        inherited[column] = current_value * INHERIT_PERCENT // 100
        reborn[column] = template_value + inherited[column]
    return reborn, inherited


def _row_to_dict(row, columns):
    return {column: row[index] for index, column in enumerate(columns)}


async def _load_active_role(cursor, uid, *, for_update=False):
    lock = " FOR UPDATE" if for_update else ""
    columns = (
        "id",
        "name",
        "dengji",
        "exp",
        "reincarnation_count",
        *ROLE_ATTRIBUTE_COLUMNS,
    )
    await cursor.execute(
        f"SELECT {','.join(f'`{column}`' for column in columns)} "
        f"FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1{lock}",
        (uid,),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row, columns) if row else None


async def _load_role_template(cursor, role_name):
    columns = (*ROLE_ATTRIBUTE_COLUMNS, "id")
    # data_role 中法力字段名为 max_fali，其他字段与 user_role 一致。
    select_columns = ["max_fali" if column == "fali" else column for column in ROLE_ATTRIBUTE_COLUMNS]
    await cursor.execute(
        f"SELECT {','.join(f'`{column}`' for column in select_columns)}, id "
        "FROM data_role WHERE `name` = %s LIMIT 1",
        (role_name,),
    )
    row = await cursor.fetchone()
    if not row:
        raise ReincarnationError("角色模板数据不存在，请联系管理员。")
    values = _row_to_dict(row, columns)
    await cursor.execute("SELECT stage_1 FROM data_stage WHERE id = %s LIMIT 1", (values["id"],))
    stage_row = await cursor.fetchone()
    if not stage_row or not stage_row[0]:
        raise ReincarnationError("角色初始境界数据不存在，请联系管理员。")
    values["stage"] = f"{stage_row[0]}境"
    return values


def _build_preview(role, template):
    current = {column: role[column] for column in ROLE_ATTRIBUTE_COLUMNS}
    base = {column: template[column] for column in ROLE_ATTRIBUTE_COLUMNS}
    reborn, inherited = calculate_reincarnation_attributes(current, base)
    return {
        **role,
        "next_reincarnation": int(role["reincarnation_count"]) + 1,
        "stage": template["stage"],
        "reborn_attributes": reborn,
        "inherited_attributes": inherited,
    }


def validate_reincarnation(role):
    if int(role["dengji"]) < REINCARNATION_LEVEL:
        raise ReincarnationError(
            f"当前角色仅{int(role['dengji'])}级，达到{REINCARNATION_LEVEL}级后方可轮回。"
        )
    current_life = int(role["reincarnation_count"] or MIN_REINCARNATION)
    if current_life >= MAX_REINCARNATION:
        raise ReincarnationError("当前角色已至第9世，无法再次轮回。")


async def get_reincarnation_preview(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await ensure_reincarnation_schema(cursor)
            role = await _load_active_role(cursor, uid)
            if not role:
                raise ReincarnationError("当前没有出战角色，请先选择角色出战。")
            validate_reincarnation(role)
            template = await _load_role_template(cursor, role["name"])
            return _build_preview(role, template)


async def reincarnate_active_role(uid):
    """锁定用户与出战角色，原子完成等级、境界、属性及战力更新。"""
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            try:
                await ensure_reincarnation_schema(cursor)
                from Game_domain.abyss_service import is_role_locked_by_abyss

                if await is_role_locked_by_abyss(uid, cursor):
                    raise ReincarnationError("角色正处于深渊冻结状态，请先完成或结算当前挑战。")

                # 与参悟领取保持 user_zt -> user_role 的加锁顺序，避免交叉死锁。
                await cursor.execute(
                    "SELECT is_canwu, cw_role FROM user_zt WHERE id = %s LIMIT 1 FOR UPDATE",
                    (uid,),
                )
                user_state = await cursor.fetchone()
                if not user_state:
                    raise ReincarnationError("玩家数据不存在，请重新注册或联系管理员。")

                role = await _load_active_role(cursor, uid, for_update=True)
                if not role:
                    raise ReincarnationError("当前没有出战角色，请先选择角色出战。")
                if int(user_state[0] or 0) != 0 and int(user_state[1] or 0) == int(role["id"]):
                    raise ReincarnationError("当前角色尚在参悟，请先领取参悟经验后再轮回。")

                validate_reincarnation(role)
                template = await _load_role_template(cursor, role["name"])
                preview = _build_preview(role, template)
                assignments = [
                    "dengji = 1",
                    "exp = 0",
                    "stage = %s",
                    "reincarnation_count = reincarnation_count + 1",
                ]
                values = [preview["stage"]]
                for column in ROLE_ATTRIBUTE_COLUMNS:
                    assignments.append(f"`{column}` = %s")
                    values.append(preview["reborn_attributes"][column])
                values.extend((role["id"], uid, REINCARNATION_LEVEL, MAX_REINCARNATION))
                await cursor.execute(
                    f"UPDATE user_role SET {', '.join(assignments)} "
                    "WHERE id = %s AND uid = %s AND dengji >= %s "
                    "AND reincarnation_count < %s",
                    tuple(values),
                )
                if cursor.rowcount != 1:
                    raise ReincarnationError("轮回状态已发生变化，请刷新角色信息后重试。")

                from Tool.tool_power import update_role_power

                await update_role_power(conn, uid)
                await conn.commit()
                return preview
            except ReincarnationError:
                await conn.rollback()
                raise
            except Exception:
                await conn.rollback()
                raise
