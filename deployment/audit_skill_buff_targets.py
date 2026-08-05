# -*- coding: utf-8 -*-
"""使用已注册模拟玩家审计全部玩家技能 Buff 的实际落点。"""

import argparse
import asyncio
from pathlib import Path
import sys
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sql.mysql import connect_mysql
from Tool.combat_system import (
    CombatEntity,
    ENEMY_BUFF_TYPES,
    SELF_BUFF_TYPES,
    Skill,
    normalize_skill_buff_type,
)


PLAYABLE_ROLES = ("萧炎", "王林", "韩立", "石昊", "叶凡", "孟川")


def _entity(name, uid, entity_type):
    return CombatEntity(name, {
        "uid": uid,
        "name": name,
        "qixue": 10_000_000,
        "gongji": 1_000,
        "fangyu": 1_000,
        "sudu": 100,
        "baoji": 0,
        "baoshang": 0,
        "shanbi": 0,
        "mingzhong": 100_000,
        "pofang": 0,
        "xixue": 0,
        "max_fali": 100_000,
        "entity_type": entity_type,
    }, [])


def _to_int(value):
    return int(float(value or 0))


def audit_skill_rows(rows, uid, player_name):
    failures = []
    totals = {"player": 0, "enemy": 0}
    for row in rows:
        (
            skill_id, role_name, skill_name, skill_type, value, is_percent,
            cooldown, buff_type, buff_value, buff_duration, buff_target,
            buff_name, description,
        ) = row
        normalized_type = normalize_skill_buff_type(buff_type, skill_name)
        type_key = str(normalized_type or "").strip().lower()
        if type_key in SELF_BUFF_TYPES:
            expected = "player"
        elif type_key in ENEMY_BUFF_TYPES:
            expected = "enemy"
        else:
            failures.append((skill_id, role_name, skill_name, type_key, "未分类"))
            continue

        player = _entity(player_name, uid, "player")
        enemy = _entity("Buff审计木桩", 0, "normal")
        skill = Skill(
            id=_to_int(skill_id),
            name=str(skill_name),
            skill_type=_to_int(skill_type),
            target_type="enemy",
            value=_to_int(value),
            is_percent=_to_int(is_percent),
            cooldown=_to_int(cooldown),
            mana_cost=0,
            buff_type=buff_type,
            buff_value=_to_int(buff_value),
            buff_duration=_to_int(buff_duration),
            buff_target=_to_int(buff_target),
            buff_name=str(buff_name or ""),
            description=str(description or ""),
        )
        with (
            patch("Tool.combat_system.random.random", return_value=0.5),
            patch("Tool.combat_system.random.uniform", return_value=1.0),
        ):
            skill.execute(player, enemy)
        player_has = bool(player.buffs)
        enemy_has = bool(enemy.buffs)
        actual = (
            "player" if player_has and not enemy_has
            else "enemy" if enemy_has and not player_has
            else "无或同时作用"
        )
        if actual != expected:
            failures.append((skill_id, role_name, skill_name, type_key, expected, actual))
        else:
            totals[actual] += 1
    return totals, failures


async def load_audit_context(uid):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT name, is_chushi FROM user_zt WHERE id = %s LIMIT 1",
                (uid,),
            )
            player = await cursor.fetchone()
            if not player or int(player[1] or 0) != 1:
                raise RuntimeError("模拟玩家不存在或尚未选择初始角色")

            placeholders = ",".join(["%s"] * len(PLAYABLE_ROLES))
            await cursor.execute(
                f"""
                SELECT id, role_name, skill_name, skill_type, `value`, is_percent,
                       cooldown, buff_type, buff_value, buff_duration, buff_target,
                       buff_name, buff_desc
                FROM data_skill
                WHERE role_name IN ({placeholders})
                  AND COALESCE(buff_duration, 0) > 0
                ORDER BY id
                """,
                PLAYABLE_ROLES,
            )
            normal_skills = list(await cursor.fetchall())
            await cursor.execute(
                """
                SELECT id, role_name, skill_name, skill_type, `value`, is_percent,
                       cooldown, buff_type, buff_value, buff_duration, buff_target,
                       '', skill_desc
                FROM data_benyuan_skill
                WHERE COALESCE(buff_duration, 0) > 0
                ORDER BY id
                """
            )
            benyuan_skills = list(await cursor.fetchall())
    return str(player[0]), normal_skills, benyuan_skills


async def main(uid):
    player_name, normal_skills, benyuan_skills = await load_audit_context(uid)
    rows = normal_skills + benyuan_skills
    totals, failures = audit_skill_rows(rows, uid, player_name)
    print(f"模拟玩家：{player_name}（UID {uid}）")
    print(f"已测试：基础技能 {len(normal_skills)} 个，本源技能 {len(benyuan_skills)} 个")
    print(f"正确落到玩家：{totals['player']} 个；正确落到敌方：{totals['enemy']} 个")
    print(f"异常：{len(failures)} 个")
    for failure in failures:
        print("异常 | " + " | ".join(str(value) for value in failure))
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uid", type=int, required=True, help="已注册并选择角色的模拟玩家 UID")
    arguments = parser.parse_args()
    raise SystemExit(asyncio.run(main(arguments.uid)))
