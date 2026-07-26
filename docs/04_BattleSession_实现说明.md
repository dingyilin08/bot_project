# Battle Session 实现说明

**实现日期：** 2026-07-25  
**状态：** Battle Session 基础层完成；旧副本奖励链已接入 RewardService

## 已实现

- `Tool/combat_system.py`
  - `CombatManager.initialize()`：只初始化战斗，不自动跑完整场。
  - `CombatManager.resolve_round()`：按一回合推进战斗。
  - `CombatManager.validate_player_action()`：校验普通攻击、技能、防御和自动行动。
  - `CombatEntity/Skill/Buff/CombatManager.to_snapshot()` 与 `from_snapshot()`：快照可 JSON 持久化和恢复。
  - 旧 `start_combat()` 保留，现有自动战斗调用不会因接口移除而失效。
  - 修复 Windows GBK 控制台输出表情时导致战斗中断的问题。

- `Game_domain/battle_models.py`
  - BattleSession、BattleActionRecord、BattleEvent、BattleResult。
  - 统一状态、行动类型和业务错误码。

- `Game_domain/battle_repository.py`
  - `InMemoryBattleRepository`：单元测试和本地规则验证。
  - `MySQLBattleRepository`：生产持久化、行锁、版本号、行动唯一键、事件追加和过期战斗扫描。

- `Game_domain/battle_service.py`
  - 创建战斗。
  - 查询战斗并校验参与者。
  - 提交行动并保证同一行动/同一玩家同一回合不重复。
  - 回合结算、超时自动行动、结束状态和事件生成。
  - 兼容自动战斗的 `run_to_completion()`。
  - `recover_stale_battles()` 恢复超时回合。

- `Game_domain/event_inbox.py`
  - Webhook 与 botpy WebSocket 都按 QQ 事件 ID 去重。
  - 只有 MySQL 唯一键冲突被视为重复事件；连接、权限、未迁移表等错误会继续抛出。

- `数据库源文件/battle_session.sql`
  - 新增 `battle_session`、`battle_action`、`battle_event`、`event_inbox`、`reward_ledger`。

## 使用方式

```python
from Game_domain.battle_repository import MySQLBattleRepository
from Game_domain.battle_service import BattleSessionService

repository = MySQLBattleRepository()
service = BattleSessionService(repository)

session = await service.create_battle(
    uid=uid,
    manager=combat_manager,
    metadata={"participants": [uid], "dungeon_id": dungeon_id},
)

result = await service.submit_action(
    battle_id=session.battle_id,
    uid=uid,
    action_type="NORMAL_ATTACK",
    action_id=request_id,
)
```

## 上线前必须执行

1. 备份生产数据库。
2. 执行 `数据库源文件/battle_session.sql`。
3. 确认 MySQL 版本支持 JSON 字段和 InnoDB 行锁。
4. 用测试账号验证创建、提交、重复提交、超时恢复和重启恢复。
5. 确认日志不打印 QQ Secret、数据库密码或完整战斗快照。

## 当前明确未切换的部分

当前旧副本入口仍使用整场自动战斗，但胜利后的经验、灵石、物品和装备已经统一由 RewardService 发放，并由 reward_ledger 业务键保证幂等。尚未统一的是副本进度、掉落历史和 Battle Session 最终结算状态。

`Game_main/g6_dungeon.py` 仍使用旧的整场自动战斗入口；奖励资产已经统一由 `RewardService + reward_ledger` 事务发放。副本进度、掉落历史和 Battle Session 最终结算仍需后续继续合并。

切换旧副本前必须完成：

- 以 `battle_uuid` 为来源的奖励流水。
- 经验、灵石、物品、装备和进度的一致性事务。
- 重复结算只返回历史结果，不再次修改玩家数据。
- 旧 `combat_log` 与新 `battle_event` 的兼容查询。
- MySQL 集成测试和失败重试测试。

## RewardService 进展

`Game_domain/reward_service.py` 已完成基础实现：

- `battle:{battle_id}:uid:{uid}:{reward_type}` 作为唯一业务键。
- 灵石、经验、物品、装备在同一个 MySQL 事务中写入。
- 经验升级和境界突破临界点使用现有经验公式。
- 物品使用 `user_item` 主键安全 upsert。
- 装备使用 `user_equip` 插入并由奖励流水防止重复生成。
- 内存实现已覆盖重复奖励、物品合并、负数奖励和突破临界测试。

剩余工作是把掉落随机结果、`user_dungeon_progress`、`user_dungeon_drop` 和战斗摘要统一纳入同一个 Battle Session 结算事务。奖励资产的分散写入已经从 `g6_dungeon.py` 删除。
## Implementation Status (2026-07-25)

The legacy dungeon victory path now calls MySQLRewardService. Experience, lingshi, items,
and equipment are committed in one transaction and protected by reward_ledger business keys.
Drop rolls use a stable UUID derived from the dungeon progress instance, so a retry reuses
the same reward plan instead of rolling again. Dungeon progress and display history remain
separate follow-up writes and are the next consistency-hardening step.
