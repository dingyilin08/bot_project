# -*- coding: utf-8 -*-
"""玩家邀请码：注册绑定、进度追踪与双向奖励领取。"""

import os
import re
import secrets
import string

from func.pd_func import pd_reg_func
from sql.mysql import connect_mysql
from Game_domain.gm_state import get_admin_uids


INVITE_CODE_LENGTH = 8
INVITE_ALPHABET = string.ascii_uppercase
REGISTER_REWARD = {"lingshi": 1600, "xianyu": 500}
ONBOARDING_REWARD = {"lingshi": 0, "xianyu": 1000}
ONBOARDING_TASK_COUNT = 7
REWARD_REGISTER = "REGISTER"
REWARD_ONBOARDING = "ONBOARDING"


class InvitationError(ValueError):
    pass


def generate_invite_code():
    """生成八位大写随机字母；数据库唯一索引负责最终去重。"""
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))


def normalize_invite_code(value):
    code = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{8}", code):
        raise InvitationError("邀请码必须是 8 位英文字母。")
    return code


def parse_registration_input(value):
    """兼容“注册游戏 名称 邀请码”与“注册游戏 名称-邀请码”。"""
    text = str(value or "").strip()
    if not text:
        return "", None
    pieces = text.split()
    if len(pieces) == 2:
        return pieces[0], normalize_invite_code(pieces[1])
    if len(pieces) > 2:
        raise InvitationError("注册格式：注册游戏 玩家名 邀请码。")
    matched = re.fullmatch(r"(.+?)[-－]([A-Za-z]{8})", text)
    if matched:
        return matched.group(1).strip(), normalize_invite_code(matched.group(2))
    return text, None


def _configured_admin_uid(existing_uids):
    configured = os.getenv("INVITATION_ADMIN_UID", "").strip()
    candidates = []
    if configured.isdigit():
        candidates.append(int(configured))
    candidates.extend(get_admin_uids())
    existing = {int(uid) for uid in existing_uids}
    return next((uid for uid in candidates if uid in existing), None)


async def _create_profile(cursor, uid, inviter_uid=None, reward_eligible=False):
    """创建邀请码档案；重复码由唯一索引拦截后重试。"""
    for _ in range(32):
        code = generate_invite_code()
        try:
            await cursor.execute(
                """INSERT INTO user_invitation_profile
                   (uid, invite_code, inviter_uid, reward_eligible)
                   VALUES (%s, %s, %s, %s)""",
                (uid, code, inviter_uid, int(bool(reward_eligible))),
            )
            return code
        except Exception as exc:
            # 只有邀请码唯一冲突可重试；其余数据库故障必须向上抛出。
            if "invite_code" not in str(exc).lower() and "duplicate" not in str(exc).lower():
                raise
    raise RuntimeError("邀请码生成冲突次数过多，请稍后重试。")


async def ensure_legacy_invitation_profiles(cursor):
    """为功能上线前的账号建立无奖励管理员归属与唯一邀请码。"""
    await cursor.execute("SELECT id FROM user_zt ORDER BY id")
    all_uids = [int(row[0]) for row in await cursor.fetchall()]
    if not all_uids:
        return None
    admin_uid = _configured_admin_uid(all_uids)
    await cursor.execute("SELECT uid FROM user_invitation_profile")
    existing = {int(row[0]) for row in await cursor.fetchall()}

    if admin_uid and admin_uid not in existing:
        await _create_profile(cursor, admin_uid)
        existing.add(admin_uid)
    for uid in all_uids:
        if uid in existing:
            continue
        inviter_uid = admin_uid if admin_uid and uid != admin_uid else None
        await _create_profile(cursor, uid, inviter_uid=inviter_uid, reward_eligible=False)
    if admin_uid:
        await cursor.execute(
            """UPDATE user_invitation_profile
               SET inviter_uid = %s, bound_at = CURRENT_TIMESTAMP
               WHERE reward_eligible = 0 AND inviter_uid IS NULL AND uid <> %s""",
            (admin_uid, admin_uid),
        )
    return admin_uid


async def create_new_invitation_profile(cursor, uid):
    return await _create_profile(cursor, uid, reward_eligible=True)


async def bind_invitation_code(cursor, invitee_uid, invite_code):
    code = normalize_invite_code(invite_code)
    await cursor.execute(
        "SELECT uid FROM user_invitation_profile WHERE invite_code = %s FOR UPDATE",
        (code,),
    )
    row = await cursor.fetchone()
    if not row:
        raise InvitationError("邀请码不存在，请向邀请人确认后重新注册。")
    inviter_uid = int(row[0])
    if inviter_uid == int(invitee_uid):
        raise InvitationError("不可填写自己的邀请码。")
    await cursor.execute(
        "SELECT inviter_uid FROM user_invitation_profile WHERE uid = %s FOR UPDATE",
        (invitee_uid,),
    )
    profile = await cursor.fetchone()
    if not profile:
        raise InvitationError("邀请码档案初始化失败，请稍后重试。")
    if profile[0] is not None:
        raise InvitationError("当前账号已绑定邀请码，不能重复填写。")
    await cursor.execute(
        """UPDATE user_invitation_profile
           SET inviter_uid = %s, reward_eligible = 1, bound_at = CURRENT_TIMESTAMP
           WHERE uid = %s AND inviter_uid IS NULL""",
        (inviter_uid, invitee_uid),
    )
    reward_rows = (
        (inviter_uid, inviter_uid, invitee_uid, REWARD_REGISTER, REGISTER_REWARD, True),
        (invitee_uid, inviter_uid, invitee_uid, REWARD_REGISTER, REGISTER_REWARD, True),
        (inviter_uid, inviter_uid, invitee_uid, REWARD_ONBOARDING, ONBOARDING_REWARD, False),
        (invitee_uid, inviter_uid, invitee_uid, REWARD_ONBOARDING, ONBOARDING_REWARD, False),
    )
    for receiver_uid, owner_uid, new_uid, reward_code, reward, available in reward_rows:
        await cursor.execute(
            """INSERT IGNORE INTO user_invitation_reward
               (uid, inviter_uid, invitee_uid, reward_code, lingshi, xianyu, available_at)
               VALUES (%s, %s, %s, %s, %s, %s,
                       CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END)""",
            (receiver_uid, owner_uid, new_uid, reward_code, reward["lingshi"], reward["xianyu"], int(available)),
        )
    return inviter_uid


async def activate_onboarding_invitation_rewards(cursor, invitee_uid):
    """新玩家完成七项札记后，解锁双方的第二档邀请奖励。"""
    await cursor.execute(
        """SELECT inviter_uid, reward_eligible FROM user_invitation_profile
           WHERE uid = %s FOR UPDATE""",
        (invitee_uid,),
    )
    profile = await cursor.fetchone()
    if not profile or profile[0] is None or not profile[1]:
        return False
    await cursor.execute(
        """SELECT COUNT(*) FROM user_onboarding_progress
           WHERE uid = %s AND completed_at IS NOT NULL""",
        (invitee_uid,),
    )
    if int((await cursor.fetchone())[0]) < ONBOARDING_TASK_COUNT:
        return False
    await cursor.execute(
        """UPDATE user_invitation_reward
           SET available_at = COALESCE(available_at, CURRENT_TIMESTAMP)
           WHERE invitee_uid = %s AND reward_code = %s AND available_at IS NULL""",
        (invitee_uid, REWARD_ONBOARDING),
    )
    return cursor.rowcount > 0


async def sync_onboarding_invitation_rewards(uid):
    """札记事件提交后异步同步邀请奖励，失败不影响原引导玩法。"""
    try:
        async with connect_mysql() as conn:
            async with conn.cursor() as cursor:
                await activate_onboarding_invitation_rewards(cursor, uid)
                await conn.commit()
    except Exception:
        return False
    return True


def _buttons(*entries):
    return " | ".join(f"<qqbot-cmd-input text='{command}' show='{label}' />" for command, label in entries)


async def _ensure_profiles_and_commit(cursor, conn):
    await ensure_legacy_invitation_profiles(cursor)
    await conn.commit()


@pd_reg_func
async def my_invitation_code(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_profiles_and_commit(cursor, conn)
            await cursor.execute("SELECT invite_code FROM user_invitation_profile WHERE uid = %s", (uid,))
            row = await cursor.fetchone()
    code = row[0] if row else "生成中"
    content = (
        "##### ✉️ 我的邀请码\n\n"
        f"**邀请码：{code}**\n"
        "> 邀请新道友注册时填写：`注册游戏 玩家名 邀请码`。\n"
        "> 双方可各领取 500 仙玉 + 1600 灵石；新道友完成全部问道札记后，双方再各得 1000 仙玉。\n\n"
        + _buttons(("邀请列表", "邀请列表"), ("领取邀请奖励", "领取奖励"), ("主菜单", "主菜单"))
    )
    return {"type": "markdown", "content": content}


@pd_reg_func
async def invitation_list(uid, qz):
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await _ensure_profiles_and_commit(cursor, conn)
            await cursor.execute(
                """SELECT u.id, u.name,
                          (SELECT COUNT(*) FROM user_onboarding_progress op
                           WHERE op.uid = u.id AND op.completed_at IS NOT NULL),
                          r.name, r.dengji
                   FROM user_invitation_profile p
                   JOIN user_zt u ON u.id = p.uid
                   LEFT JOIN user_role r ON r.uid = u.id AND r.is_chuzhan = 1
                   WHERE p.inviter_uid = %s AND p.reward_eligible = 1
                   ORDER BY p.bound_at DESC, u.id DESC""",
                (uid,),
            )
            rows = await cursor.fetchall()
    lines = ["##### 👥 邀请列表", "> 仅显示通过你邀请码注册的新道友。", "***"]
    if not rows:
        lines.append("> 暂无有效邀请。发送“我的邀请码”分享你的八位邀请码。")
    else:
        for invited_uid, name, progress, role_name, level in rows:
            role = f"{role_name} Lv.{level}" if role_name else "尚未选择角色"
            lines.append(f"**{name}（{invited_uid}）**")
            lines.append(f"> 新手札记：{int(progress)}/{ONBOARDING_TASK_COUNT}｜当前角色：{role}")
    lines.extend(("***", _buttons(("领取邀请奖励", "领取奖励"), ("我的邀请码", "我的邀请码"), ("主菜单", "主菜单"))))
    return {"type": "markdown", "content": "\n".join(lines)}


@pd_reg_func
async def claim_invitation_rewards(uid, qz):
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await _ensure_profiles_and_commit(cursor, conn)
                await cursor.execute(
                    """SELECT DISTINCT invitee_uid FROM user_invitation_reward
                       WHERE uid = %s AND reward_code = %s AND available_at IS NULL""",
                    (uid, REWARD_ONBOARDING),
                )
                for (invitee_uid,) in await cursor.fetchall():
                    await activate_onboarding_invitation_rewards(cursor, int(invitee_uid))
                await cursor.execute(
                    """SELECT id, reward_code, lingshi, xianyu FROM user_invitation_reward
                       WHERE uid = %s AND available_at IS NOT NULL AND claimed_at IS NULL
                       ORDER BY id FOR UPDATE""",
                    (uid,),
                )
                rewards = await cursor.fetchall()
                if not rewards:
                    await conn.commit()
                    return {"type": "markdown", "content": "##### 🎁 邀请奖励\n\n当前暂无可领取奖励。邀请新道友完成注册，或等待已邀请道友完成全部新手札记后再来领取。\n\n" + _buttons(("邀请列表", "邀请列表"), ("我的邀请码", "我的邀请码"))}
                total_lingshi = sum(int(row[2]) for row in rewards)
                total_xianyu = sum(int(row[3]) for row in rewards)
                for reward_id, *_ in rewards:
                    await cursor.execute(
                        "UPDATE user_invitation_reward SET claimed_at = CURRENT_TIMESTAMP WHERE id = %s AND claimed_at IS NULL",
                        (reward_id,),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("邀请奖励状态已变化，请重新领取。")
                await cursor.execute(
                    "UPDATE user_zt SET lingshi = lingshi + %s, xianyu = xianyu + %s WHERE id = %s",
                    (total_lingshi, total_xianyu, uid),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("玩家资产不存在，邀请奖励未发放。")
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    kinds = "、".join("注册邀请礼" if row[1] == REWARD_REGISTER else "札记圆满礼" for row in rewards)
    return {"type": "markdown", "content": f"##### 🎁 邀请奖励已领取\n\n来源：{kinds}\n获得：**{total_xianyu} 仙玉 + {total_lingshi} 灵石**\n\n" + _buttons(("邀请列表", "邀请列表"), ("我的邀请码", "我的邀请码"), ("主菜单", "主菜单"))}
