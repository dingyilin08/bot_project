"""统一奖励发放服务。

奖励发放必须由 battle_uuid 驱动，并在 reward_ledger 中留下唯一业务键。
该模块不发送 QQ 消息，也不依赖副本展示层。
"""

import copy
import json
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from sql.mysql import connect_mysql


BREAKTHROUGH_LEVELS = {10, 20, 30, 40, 50, 60, 70, 80, 90}
EXP_RANGES = [
    (1, 800, 2000),
    (2, 2000, 12000),
    (3, 4500, 38000),
    (4, 8000, 95000),
    (5, 15000, 200000),
    (6, 28000, 400000),
    (7, 50000, 780000),
    (8, 90000, 1500000),
    (9, 160000, 2800000),
    (10, 280000, 5200000),
]


class RewardError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RewardItem:
    item_id: int
    amount: int
    item_name: Optional[str] = None


@dataclass(frozen=True)
class RewardEquipment:
    equip_id: int
    quality: str = "凡品"
    level: int = 0
    name: Optional[str] = None


@dataclass
class RewardResult:
    battle_id: str
    uid: int
    applied: List[str] = field(default_factory=list)
    duplicates: List[str] = field(default_factory=list)
    level_before: Optional[int] = None
    level_after: Optional[int] = None
    exp_after: Optional[int] = None
    need_breakthrough: bool = False
    add_gongji: int = 0
    add_fangyu: int = 0
    add_qixue: int = 0


def required_exp(level: int) -> int:
    """与现有 Tool.tool_user.up_need_exp 保持同一套升级经验公式。"""
    if level >= 100 or level < 1:
        return 0
    stage = (level - 1) // 10 + 1
    for stage_id, every, start in EXP_RANGES:
        if stage_id == stage:
            return every * (level % 10) + start
    return 0


def calculate_exp_progress(level: int, current_exp: int, add_exp: int) -> Dict:
    """计算经验和等级变化，不读写数据库，便于测试和重放。"""
    if add_exp < 0:
        raise RewardError("INVALID_REWARD", "经验奖励不能为负数")
    new_level = level
    remaining_exp = current_exp + add_exp
    levels_gained = 0
    need_breakthrough = False
    while new_level < 100:
        need = required_exp(new_level)
        if need <= 0 or remaining_exp < need:
            break
        if new_level in BREAKTHROUGH_LEVELS:
            need_breakthrough = True
            break
        remaining_exp -= need
        new_level += 1
        levels_gained += 1
    return {
        "level": new_level,
        "exp": remaining_exp,
        "levels_gained": levels_gained,
        "need_breakthrough": need_breakthrough,
    }


class InMemoryRewardService:
    """不连接数据库的奖励实现，用于幂等和规则测试。"""

    def __init__(self):
        self.ledger = set()
        self.lingshi: Dict[int, int] = {}
        self.roles: Dict[int, Dict] = {}
        self.items: Dict[Tuple[int, int], int] = {}
        self.equipments: List[Dict] = []

    async def grant_battle_rewards(
        self,
        *,
        battle_id: str,
        uid: int,
        exp: int = 0,
        lingshi: int = 0,
        items: Iterable[RewardItem] = (),
        equipments: Iterable[RewardEquipment] = (),
        role_id: Optional[int] = None,
    ) -> RewardResult:
        if exp < 0 or lingshi < 0:
            raise RewardError("INVALID_REWARD", "奖励数量不能为负数")
        result = RewardResult(battle_id=battle_id, uid=uid)

        if exp:
            key = self._key(battle_id, uid, "exp")
            if key in self.ledger:
                result.duplicates.append(key)
            else:
                self.ledger.add(key)
                role = self.roles.setdefault(role_id or uid, {"level": 1, "exp": 0})
                progress = calculate_exp_progress(role["level"], role["exp"], exp)
                result.level_before = role["level"]
                role.update(level=progress["level"], exp=progress["exp"])
                result.level_after = role["level"]
                result.exp_after = role["exp"]
                result.need_breakthrough = progress["need_breakthrough"]
                result.add_gongji = progress.get("add_gongji", 0)
                result.add_fangyu = progress.get("add_fangyu", 0)
                result.add_qixue = progress.get("add_qixue", 0)
                result.applied.append(key)

        if lingshi:
            key = self._key(battle_id, uid, "lingshi")
            if key in self.ledger:
                result.duplicates.append(key)
            else:
                self.ledger.add(key)
                self.lingshi[uid] = self.lingshi.get(uid, 0) + lingshi
                result.applied.append(key)

        item_totals: Dict[int, int] = {}
        for item in items:
            if item.amount < 0:
                raise RewardError("INVALID_REWARD", "物品奖励不能为负数")
            item_totals[item.item_id] = item_totals.get(item.item_id, 0) + item.amount
        for item_id, amount in item_totals.items():
            if not amount:
                continue
            key = self._key(battle_id, uid, f"item:{item_id}")
            if key in self.ledger:
                result.duplicates.append(key)
            else:
                self.ledger.add(key)
                bag_key = (uid, item_id)
                self.items[bag_key] = self.items.get(bag_key, 0) + amount
                result.applied.append(key)

        for index, equipment in enumerate(equipments):
            key = self._key(battle_id, uid, f"equipment:{index}")
            if key in self.ledger:
                result.duplicates.append(key)
            else:
                self.ledger.add(key)
                self.equipments.append({
                    "uid": uid,
                    "equip_id": equipment.equip_id,
                    "quality": equipment.quality,
                    "level": equipment.level,
                })
                result.applied.append(key)
        return result

    @staticmethod
    def _key(battle_id: str, uid: int, reward_type: str) -> str:
        return f"battle:{battle_id}:uid:{uid}:{reward_type}"


class MySQLRewardService:
    """生产奖励实现：所有奖励类型共用一个数据库事务。"""

    async def grant_battle_rewards(
        self,
        *,
        battle_id: str,
        uid: int,
        exp: int = 0,
        lingshi: int = 0,
        items: Iterable[RewardItem] = (),
        equipments: Iterable[RewardEquipment] = (),
        role_id: Optional[int] = None,
    ) -> RewardResult:
        if exp < 0 or lingshi < 0:
            raise RewardError("INVALID_REWARD", "奖励数量不能为负数")
        items = list(items)
        equipments = list(equipments)
        if any(item.amount < 0 for item in items):
            raise RewardError("INVALID_REWARD", "物品奖励不能为负数")

        result = RewardResult(battle_id=battle_id, uid=uid)
        role_level_changed = False
        async with connect_mysql() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT id FROM user_zt WHERE id = %s FOR UPDATE", (uid,))
                    if not await cursor.fetchone():
                        raise RewardError("PLAYER_NOT_FOUND", "玩家不存在")

                    current_role = None
                    if exp:
                        if role_id is None:
                            await cursor.execute(
                                """
                                SELECT id, `name`, dengji, exp, gongji, fangyu, qixue,
                                       baoji, baoshang, mingzhong, shanbi, pofang, xixue
                                FROM user_role WHERE uid = %s AND is_chuzhan = 1 LIMIT 1 FOR UPDATE
                                """,
                                (uid,),
                            )
                        else:
                            await cursor.execute(
                                """
                                SELECT id, `name`, dengji, exp, gongji, fangyu, qixue,
                                       baoji, baoshang, mingzhong, shanbi, pofang, xixue
                                FROM user_role WHERE id = %s AND uid = %s LIMIT 1 FOR UPDATE
                                """,
                                (role_id, uid),
                            )
                        current_role = await cursor.fetchone()
                        if not current_role:
                            raise RewardError("ROLE_NOT_FOUND", "出战角色不存在")

                    if exp:
                        key = self._key(battle_id, uid, "exp")
                        if await self._claim(cursor, key, uid, "EXP", exp, battle_id, {"role_id": current_role[0]}):
                            progress = await self._apply_experience(cursor, current_role, exp)
                            result.level_before = current_role[2]
                            result.level_after = progress["level"]
                            result.exp_after = progress["exp"]
                            result.need_breakthrough = progress["need_breakthrough"]
                            result.add_gongji = progress.get("add_gongji", 0)
                            result.add_fangyu = progress.get("add_fangyu", 0)
                            result.add_qixue = progress.get("add_qixue", 0)
                            role_level_changed = progress["level"] != current_role[2]
                            result.applied.append(key)
                        else:
                            result.duplicates.append(key)

                    if lingshi:
                        key = self._key(battle_id, uid, "lingshi")
                        if await self._claim(cursor, key, uid, "LINGSHI", lingshi, battle_id):
                            await cursor.execute(
                                "UPDATE user_zt SET lingshi = lingshi + %s WHERE id = %s",
                                (lingshi, uid),
                            )
                            result.applied.append(key)
                        else:
                            result.duplicates.append(key)

                    item_totals: Dict[int, int] = {}
                    for item in items:
                        item_totals[item.item_id] = item_totals.get(item.item_id, 0) + item.amount
                    for item_id, amount in item_totals.items():
                        if not amount:
                            continue
                        key = self._key(battle_id, uid, f"item:{item_id}")
                        if await self._claim(cursor, key, uid, "ITEM", amount, battle_id, {"item_id": item_id}):
                            await cursor.execute(
                                """
                                INSERT INTO user_item (uid, item_id, item_num)
                                VALUES (%s, %s, %s)
                                ON DUPLICATE KEY UPDATE item_num = item_num + VALUES(item_num)
                                """,
                                (uid, item_id, amount),
                            )
                            result.applied.append(key)
                        else:
                            result.duplicates.append(key)

                    for index, equipment in enumerate(equipments):
                        key = self._key(battle_id, uid, f"equipment:{index}")
                        payload = {
                            "equip_id": equipment.equip_id,
                            "quality": equipment.quality,
                            "level": equipment.level,
                        }
                        if await self._claim(cursor, key, uid, "EQUIPMENT", 1, battle_id, payload):
                            await cursor.execute(
                                """
                                INSERT INTO user_equip (uid, equip_id, level, quality, is_equipped)
                                VALUES (%s, %s, %s, %s, 0)
                                """,
                                (uid, equipment.equip_id, equipment.level, equipment.quality),
                            )
                            result.applied.append(key)
                        else:
                            result.duplicates.append(key)
                    if role_level_changed:
                        # 奖励经验、等级属性和战力快照使用同一事务提交。
                        from Tool.tool_power import update_role_power
                        await update_role_power(conn, uid)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return result

    async def _apply_experience(self, cursor, role, add_exp: int) -> Dict:
        role_id, role_name, level, current_exp = role[0], role[1], role[2], role[3]
        progress = calculate_exp_progress(level, current_exp, add_exp)
        levels_gained = progress["levels_gained"]
        add_gongji = add_fangyu = add_qixue = 0
        add_baoji = add_baoshang = add_mingzhong = add_shanbi = 0
        add_pofang = add_xixue = 0
        if levels_gained:
            await cursor.execute(
                """
                SELECT gongji, fangyu, qixue, baoji, baoshang,
                       mingzhong, shanbi, pofang, xixue
                FROM data_role WHERE `name` = %s LIMIT 1
                """,
                (role_name,),
            )
            base = await cursor.fetchone()
            if not base:
                raise RewardError("ROLE_TEMPLATE_NOT_FOUND", "角色模板不存在")
            add_gongji = int(base[0] * 0.025) * levels_gained
            add_fangyu = int(base[1] * 0.015) * levels_gained
            add_qixue = int(base[2] * 0.015) * levels_gained
            add_baoji = 15 * levels_gained
            add_baoshang = 20 * levels_gained
            add_mingzhong = 25 * levels_gained
            add_shanbi = 15 * levels_gained
            for gained_level in range(level + 1, progress["level"] + 1):
                if gained_level % 10 == 0:
                    add_pofang += 50
                    add_xixue += 30

        await cursor.execute(
            """
            UPDATE user_role SET dengji = %s, exp = %s,
                gongji = gongji + %s, fangyu = fangyu + %s,
                qixue = qixue + %s, baoji = baoji + %s,
                baoshang = baoshang + %s, mingzhong = mingzhong + %s,
                shanbi = shanbi + %s, pofang = pofang + %s,
                xixue = xixue + %s
            WHERE id = %s
            """,
            (
                progress["level"], progress["exp"], add_gongji, add_fangyu,
                add_qixue, add_baoji, add_baoshang, add_mingzhong,
                add_shanbi, add_pofang, add_xixue, role_id,
            ),
        )
        progress.update({
            "add_gongji": add_gongji,
            "add_fangyu": add_fangyu,
            "add_qixue": add_qixue,
        })
        return progress

    async def _claim(
        self,
        cursor,
        business_key: str,
        uid: int,
        reward_type: str,
        amount: int,
        battle_id: str,
        payload: Optional[Dict] = None,
    ) -> bool:
        await cursor.execute(
            """
            INSERT INTO reward_ledger
                (business_key, uid, reward_type, amount, source_type, source_id, status, payload_json)
            VALUES (%s, %s, %s, %s, 'BATTLE', %s, 'GRANTED', %s)
            ON DUPLICATE KEY UPDATE business_key = business_key
            """,
            (
                business_key, uid, reward_type, amount, battle_id,
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        return cursor.rowcount == 1

    @staticmethod
    def _key(battle_id: str, uid: int, reward_type: str) -> str:
        return f"battle:{battle_id}:uid:{uid}:{reward_type}"
