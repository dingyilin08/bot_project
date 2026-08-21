# -*- coding: utf-8 -*-
"""QQ 绑定码与 Web 会话服务。

浏览器永远不能用 UID 直接声明身份。QQ 侧先为已解析出的 UID 创建一次性
绑定码，浏览器交换成功后只持有随机会话令牌；数据库中仅保存带服务端密钥
的 HMAC 摘要。
"""

from dataclasses import dataclass
import hashlib
import hmac
import os
import re
import secrets

from Game_domain.gm_state import is_admin
from sql.mysql import connect_mysql


PLAYER_SCOPE = "PLAYER"
ADMIN_SCOPE = "ADMIN"
VALID_SCOPES = {PLAYER_SCOPE, ADMIN_SCOPE}
LINK_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LINK_CODE_LENGTH = 10
LINK_CODE_TTL_SECONDS = 600
PLAYER_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
ADMIN_SESSION_TTL_SECONDS = 8 * 60 * 60


class WebAuthError(Exception):
    """可安全返回给网页或 QQ 玩家的认证错误。"""

    def __init__(self, message: str, code: str = "AUTH_FAILED"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SessionCredentials:
    token: str
    csrf_token: str
    uid: int
    scope: str
    expires_in: int


@dataclass(frozen=True)
class SessionIdentity:
    uid: int
    player_name: str
    scope: str
    csrf_hash: str


def _auth_secret() -> str:
    value = os.getenv("WEB_AUTH_SECRET", "")
    if len(value.encode("utf-8")) < 32:
        raise WebAuthError(
            "服务器尚未配置安全的 WEB_AUTH_SECRET。",
            code="SERVER_NOT_CONFIGURED",
        )
    return value


def digest_secret(value: str, *, secret: str = None) -> str:
    """生成不可逆摘要；显式 secret 参数只用于单元测试。"""

    key = (secret if secret is not None else _auth_secret()).encode("utf-8")
    return hmac.new(key, str(value).encode("utf-8"), hashlib.sha256).hexdigest()


def normalize_link_code(value: str) -> str:
    code = re.sub(r"[\s-]+", "", str(value or "").upper())
    if len(code) != LINK_CODE_LENGTH or any(ch not in LINK_CODE_ALPHABET for ch in code):
        raise WebAuthError("绑定码格式不正确。", code="INVALID_LINK_CODE")
    return code


def _validate_scope(scope: str) -> str:
    normalized = str(scope or "").upper()
    if normalized not in VALID_SCOPES:
        raise WebAuthError("不支持的会话范围。", code="INVALID_SCOPE")
    return normalized


def _metadata_hash(value: str) -> str:
    return digest_secret(str(value or "")[:500]) if value else ""


async def issue_link_code(uid: int, scope: str = PLAYER_SCOPE) -> dict:
    """为 QQ 已确认身份签发一次性绑定码。"""

    uid = int(uid)
    scope = _validate_scope(scope)
    if uid <= 0:
        raise WebAuthError("玩家 UID 无效。", code="INVALID_UID")
    if scope == ADMIN_SCOPE and not is_admin(uid):
        raise WebAuthError("你不是管理员，无法生成管理端绑定码。", code="FORBIDDEN")

    code = "".join(secrets.choice(LINK_CODE_ALPHABET) for _ in range(LINK_CODE_LENGTH))
    code_hash = digest_secret(code)
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT id FROM user_zt WHERE id=%s LIMIT 1",
                    (uid,),
                )
                if not await cursor.fetchone():
                    raise WebAuthError("玩家不存在，请先注册游戏。", code="PLAYER_NOT_FOUND")
                await cursor.execute(
                    """UPDATE web_link_code SET consumed_at=UTC_TIMESTAMP()
                       WHERE uid=%s AND scope=%s AND consumed_at IS NULL""",
                    (uid, scope),
                )
                await cursor.execute(
                    """INSERT INTO web_link_code
                       (uid,scope,code_hash,expires_at)
                       VALUES (%s,%s,%s,DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND))""",
                    (uid, scope, code_hash, LINK_CODE_TTL_SECONDS),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return {
        "uid": uid,
        "scope": scope,
        "code": code,
        "expires_in": LINK_CODE_TTL_SECONDS,
    }


async def exchange_link_code(
    uid: int,
    code: str,
    scope: str,
    *,
    client_ip: str = "",
    user_agent: str = "",
) -> SessionCredentials:
    """原子消费绑定码并创建 Web 会话。"""

    uid = int(uid)
    scope = _validate_scope(scope)
    normalized_code = normalize_link_code(code)
    code_hash = digest_secret(normalized_code)
    if scope == ADMIN_SCOPE and not is_admin(uid):
        raise WebAuthError("管理员权限无效。", code="FORBIDDEN")

    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    session_ttl = (
        ADMIN_SESSION_TTL_SECONDS if scope == ADMIN_SCOPE else PLAYER_SESSION_TTL_SECONDS
    )
    async with connect_mysql() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """SELECT id FROM web_link_code
                       WHERE uid=%s AND scope=%s AND code_hash=%s
                         AND consumed_at IS NULL AND expires_at>UTC_TIMESTAMP()
                       LIMIT 1 FOR UPDATE""",
                    (uid, scope, code_hash),
                )
                row = await cursor.fetchone()
                if not row:
                    raise WebAuthError(
                        "绑定码无效、已使用或已过期，请回到 QQ 重新获取。",
                        code="LINK_CODE_REJECTED",
                    )
                link_id = int(row[0])
                await cursor.execute(
                    """INSERT INTO web_session
                       (session_hash,csrf_hash,uid,scope,expires_at,client_ip_hash,user_agent_hash)
                       VALUES (%s,%s,%s,%s,
                               DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND),%s,%s)""",
                    (
                        digest_secret(token),
                        digest_secret(csrf_token),
                        uid,
                        scope,
                        session_ttl,
                        _metadata_hash(client_ip),
                        _metadata_hash(user_agent),
                    ),
                )
                await cursor.execute(
                    """UPDATE web_link_code SET consumed_at=UTC_TIMESTAMP()
                       WHERE id=%s AND consumed_at IS NULL""",
                    (link_id,),
                )
                if cursor.rowcount != 1:
                    raise WebAuthError("绑定码已经被使用。", code="LINK_CODE_REJECTED")
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    return SessionCredentials(
        token=token,
        csrf_token=csrf_token,
        uid=uid,
        scope=scope,
        expires_in=session_ttl,
    )


async def authenticate_session(token: str, scope: str) -> SessionIdentity:
    scope = _validate_scope(scope)
    if not token:
        raise WebAuthError("请先登录。", code="UNAUTHENTICATED")
    session_hash = digest_secret(token)
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """SELECT ws.uid,uz.`name`,ws.csrf_hash
                   FROM web_session ws
                   JOIN user_zt uz ON uz.id=ws.uid
                   WHERE ws.session_hash=%s AND ws.scope=%s
                     AND ws.revoked_at IS NULL AND ws.expires_at>UTC_TIMESTAMP()
                   LIMIT 1""",
                (session_hash, scope),
            )
            row = await cursor.fetchone()
    if not row:
        raise WebAuthError("登录已失效，请重新绑定。", code="UNAUTHENTICATED")
    uid = int(row[0])
    if scope == ADMIN_SCOPE and not is_admin(uid):
        raise WebAuthError("管理员权限已失效。", code="FORBIDDEN")
    return SessionIdentity(uid=uid, player_name=row[1], scope=scope, csrf_hash=row[2])


def verify_csrf(identity: SessionIdentity, csrf_token: str) -> None:
    supplied = digest_secret(str(csrf_token or ""))
    if not hmac.compare_digest(supplied, identity.csrf_hash):
        raise WebAuthError("页面校验已失效，请刷新后重试。", code="CSRF_REJECTED")


async def revoke_session(token: str, scope: str) -> None:
    scope = _validate_scope(scope)
    if not token:
        return
    async with connect_mysql() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """UPDATE web_session SET revoked_at=UTC_TIMESTAMP()
                   WHERE session_hash=%s AND scope=%s AND revoked_at IS NULL""",
                (digest_secret(token), scope),
            )
        await conn.commit()
