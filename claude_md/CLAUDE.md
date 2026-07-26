# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QQ Bot 文字 RPG 游戏，基于《斗破苍穹》《仙逆》《凡人修仙传》《完美世界》《遮天》《沧元图》六部小说世界观。运行在 QQ 机器人平台，通过聊天指令交互。

**官方开发文档:** https://bot.q.qq.com/wiki/develop/api-v2/

**游戏数据源文件** 数据库源文件\bot_project.sql

## Running the Project

```bash
# 两个入口二选一：

# 1. FastAPI HTTP 服务端（接收 QQ 平台回调）
python main.py

# 2. botpy WebSocket 客户端（主动连接 QQ 平台）
python bot_main.py
```

无测试框架，无 lint 配置，无构建步骤。

## Architecture

### 请求处理流程

```
QQ平台 → main.py (FastAPI) 或 bot_main.py (botpy)
       → output_main.py::jiance()  // 指令解析与路由
       → output_main.py::content() // 分发到具体模块
       → Game_main/g*.py           // 业务逻辑
       → sql/mysql.py              // 数据库操作
       → 返回 Markdown 文本响应
```

### 双入口设计

- **main.py** — FastAPI 服务端，处理 QQ 平台 HTTP 回调（含 ed25519 签名验证），支持 sandbox/production 切换（`SANDBOX_MODE` 常量）
- **bot_main.py** — botpy SDK WebSocket 客户端，支持群聊（`on_group_at_message_create`）和私聊（`on_c2c_message_create`）

两个入口都调用 `output_main.py` 的 `jiance()` 做指令解析，最终走同一套游戏逻辑。

### 指令路由 (output_main.py)

所有玩家指令在 `jiance()` 中解析，分为两类：
- **wuhouzhui** — 无后缀指令（如 `菜单`、`装备背包`、`副本列表`）
- **youhouzhui** — 带后缀指令（如 `选择角色 萧炎`、`挑战副本 1`、`穿戴装备 5`）

`content()` 函数根据解析结果分发到 `Game_main/` 下对应模块的异步函数。

### 游戏模块 (Game_main/)

| 文件 | 系统 | 关键功能 |
|------|------|----------|
| g0_menu.py | 菜单导航 | 主菜单、帮助、系统入口 |
| g1_role.py | 角色系统 | 6角色、注册、选择、属性、背包 |
| g2_canwu.py | 参悟系统 | 挂机修炼、经验领取、悟道进阶 |
| g4_benyuan.py | 本源系统 | 角色专属本源升级(1-60阶) |
| g5_skill.py | 技能系统 | 120+技能、激活/装备/融合 |
| g6_dungeon.py | 副本系统 | 60副本(6世界×10)、波次战斗、掉落 |
| g7_equip.py | 装备系统 | 6部位、5品质、强化(0-10)、套装效果 |

### 工具层 (Tool/)

- **combat_system.py** — 回合制战斗引擎，处理技能释放、BUFF 计算、伤害公式、暴击/闪避/命中判定
- **tool_user.py** — 用户查询工具函数（注册判断、前缀获取、属性计算等）
- **tool_command.py** — 快捷指令管理（玩家可绑定数字 1-5 为常用指令）

### 访问控制装饰器 (func/pd_func.py)

- `@pd_reg_func` — 仅要求已注册，注入 `uid` 和 `qz`（前缀）
- `@reg_xz_func` — 要求已注册且已选择初始角色，注入 `uid` 和 `qz`

所有需要登录态的游戏函数必须使用这两个装饰器之一。

### 数据库

- MySQL 5.7，异步访问通过 `aiomysql`
- 连接方式：`async with connect_mysql() as conn`（上下文管理器，在 `sql/mysql.py`）
- `autocommit=False`，需要手动 `await conn.commit()`
- 所有 SQL 使用 `%s` 参数化查询

核心表：
- `user_zt` — 玩家主表（等级、境界、经验、灵石等）
- `user_role` — 玩家角色（6装备槽位为外键关联 user_equip）
- `user_equip` — 装备实例（品质、强化等级、穿戴状态）
- `data_*` 表 — 静态配置数据（角色模板、副本定义、装备模板、技能定义等）

## Response Format Convention

所有模块返回统一格式：
```python
{"type": "markdown", "content": "Markdown文本内容"}
```

交互按钮使用 QQ Bot 专用标签，按指令是否需要玩家输入参数分两种：
```html
<!-- 群聊统一使用参数指令：点击后将 text 插入输入框，玩家确认后发送 -->
<qqbot-cmd-input text="实际发送的指令" show="按钮显示文字" />
```

- 所有指令统一使用 `qqbot-cmd-input`，包括无参数和参数已填完整的指令；群聊不使用 `qqbot-cmd-enter`。
- `text` 必须保留实际可执行指令；`show` 使用面向玩家的简短文案，例如 `show="挑战：青木妖狼"` 对应 `text="挑战怪物 1"`。
- 仍需玩家补充参数时，`text` 以空格结尾，`show` 提供 `*` 或参数示例。

## Admin Commands（管理员功能）

- `关闭图片模式` / `开启图片模式` — 切换纯文字回复模式（不加载图片）/ 恢复图片模式
- 密令：`day10520`（定义在 `config.py::ADMIN_PASSWORD`）
- 两种用法：一步式 `关闭图片模式 day10520`；两步式先发 `关闭图片模式`，再单独发送密令
- 实现要点：
  - 模式开关为 `config.py` 内存态（`_IMAGE_MODE_ENABLED` + `is_image_mode()/set_image_mode()`），**重启后自动恢复图片模式**
  - `output_main.py::apply_image_mode()` 在响应出口统一剥离 `![...](url)` 图片标签（正则），三个 `output_content`（main.py / bot_main.py / output_main.py）均已挂载
  - 两步验证状态 `img_mode_pwd_pending`，校验在限频之前执行（避免密令被 2 秒限频拦截）
  - 新增图片只需在 markdown 中使用 `![...](url)` 语法，纯文字模式自动生效，无需额外处理

## Adding a New Game System

1. 在 `Game_main/` 创建 `g{N}_{name}.py`，参考现有模块风格
2. 函数用 `@pd_reg_func` 或 `@reg_xz_func` 装饰
3. 在 `output_main.py` 的 `wuhouzhui`/`youhouzhui` 添加指令关键词
4. 在 `output_main.py` 的 `content()` 函数中添加分发逻辑
5. 数据表命名：静态数据用 `data_*`，玩家数据用 `user_*`

## Key Design Data (Equipment System)

```python
QUALITY_MULTIPLIER = {'凡品': 1.0, '良品': 1.3, '精品': 1.8, '仙品': 2.5, '神品': 3.5}
ENHANCE_SUCCESS_RATE = {1: 100%, 2: 90%, 3: 80%, ..., 10: 8%}  # 含保底机制
SET_BONUS = {2件: +15%, 4件: +35%, 6件: +60%}
```

