# -*- coding: utf-8 -*-
"""玩家网页与隔离管理端的 FastAPI 路由。"""

import hmac
import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from Game_domain.gm_service import GMError, grant_item, grant_xianyu
from Game_domain.dao_heart_service import (
    DaoHeartError,
    choose_daily_path,
    get_daily_state,
)
from Game_domain.web_auth_service import (
    ADMIN_SCOPE,
    PLAYER_SCOPE,
    WebAuthError,
    authenticate_session,
    exchange_link_code,
    revoke_session,
    verify_csrf,
)
from Game_web.portal_service import (
    get_dashboard,
    list_admin_audit,
    list_player_dungeons,
    list_player_inventory,
    list_player_roles,
    search_items,
    search_players,
    write_admin_audit,
)
from Game_web.presentation import dispatch_web_command


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = PROJECT_ROOT / "web_static"
FONT_ROOT = PROJECT_ROOT / "assets" / "fonts"
PLAYER_SESSION_COOKIE = "wenda_player_session"
PLAYER_CSRF_COOKIE = "wenda_player_csrf"
ADMIN_SESSION_COOKIE = "wenda_admin_session"
ADMIN_CSRF_COOKIE = "wenda_admin_csrf"

router = APIRouter()


class LinkLoginRequest(BaseModel):
    uid: int = Field(gt=0)
    code: str = Field(min_length=8, max_length=20)


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=120)
    request_id: str | None = Field(default=None, max_length=80)


class DaoHeartChoiceRequest(BaseModel):
    choice: str = Field(min_length=1, max_length=24)
    request_id: str | None = Field(default=None, max_length=80)


class ItemGrantRequest(BaseModel):
    target_uid: int = Field(gt=0)
    item_key: str = Field(min_length=1, max_length=255)
    amount: int = Field(gt=0, le=1_000_000_000)
    request_id: str | None = Field(default=None, max_length=80)


class XianyuGrantRequest(BaseModel):
    target_uid: int = Field(gt=0)
    amount: int = Field(gt=0, le=1_000_000_000)
    request_id: str | None = Field(default=None, max_length=80)


def _cookie_secure(request: Request) -> bool:
    configured = os.getenv("WEB_COOKIE_SECURE")
    if configured is not None:
        return configured.lower() not in {"0", "false", "no"}
    return request.url.scheme == "https"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else ""


def _require_same_origin(request: Request) -> None:
    """拒绝带有错误 Origin 的浏览器写请求。无 Origin 的同源表单/测试仍走 CSRF。"""

    origin = request.headers.get("origin")
    if not origin:
        return
    public_origin = os.getenv("WEB_PUBLIC_ORIGIN", "").rstrip("/")
    expected = public_origin or f"{request.url.scheme}://{request.url.netloc}"
    if not hmac.compare_digest(origin.rstrip("/"), expected):
        raise HTTPException(status_code=403, detail="请求来源校验失败。")


def _raise_auth_error(exc: WebAuthError):
    status = 500 if exc.code == "SERVER_NOT_CONFIGURED" else 401
    if exc.code in {"FORBIDDEN", "CSRF_REJECTED"}:
        status = 403
    raise HTTPException(status_code=status, detail=str(exc)) from exc


async def _identity(request: Request, scope: str, *, write: bool = False):
    cookie_name = ADMIN_SESSION_COOKIE if scope == ADMIN_SCOPE else PLAYER_SESSION_COOKIE
    csrf_cookie_name = ADMIN_CSRF_COOKIE if scope == ADMIN_SCOPE else PLAYER_CSRF_COOKIE
    try:
        identity = await authenticate_session(request.cookies.get(cookie_name, ""), scope)
        if write:
            _require_same_origin(request)
            csrf_header = request.headers.get("x-csrf-token", "")
            csrf_cookie = request.cookies.get(csrf_cookie_name, "")
            if not csrf_header or not csrf_cookie or not hmac.compare_digest(csrf_header, csrf_cookie):
                raise WebAuthError("页面校验已失效，请刷新后重试。", code="CSRF_REJECTED")
            verify_csrf(identity, csrf_header)
        return identity
    except WebAuthError as exc:
        _raise_auth_error(exc)


def _set_session_cookies(
    response: Response,
    request: Request,
    *,
    token: str,
    csrf_token: str,
    scope: str,
    max_age: int,
) -> None:
    is_admin = scope == ADMIN_SCOPE
    session_name = ADMIN_SESSION_COOKIE if is_admin else PLAYER_SESSION_COOKIE
    csrf_name = ADMIN_CSRF_COOKIE if is_admin else PLAYER_CSRF_COOKIE
    path = "/api/admin" if is_admin else "/"
    common = {
        "max_age": max_age,
        "secure": _cookie_secure(request),
        "samesite": "strict",
        "path": path,
    }
    response.set_cookie(session_name, token, httponly=True, **common)
    response.set_cookie(csrf_name, csrf_token, httponly=False, **common)


def _clear_session_cookies(response: Response, scope: str) -> None:
    is_admin = scope == ADMIN_SCOPE
    path = "/api/admin" if is_admin else "/"
    response.delete_cookie(ADMIN_SESSION_COOKIE if is_admin else PLAYER_SESSION_COOKIE, path=path)
    response.delete_cookie(ADMIN_CSRF_COOKIE if is_admin else PLAYER_CSRF_COOKIE, path=path)


@router.get("/play", include_in_schema=False)
async def player_page():
    return FileResponse(STATIC_ROOT / "play.html", media_type="text/html")


@router.get("/admin", include_in_schema=False)
async def admin_page():
    return FileResponse(STATIC_ROOT / "admin.html", media_type="text/html")


@router.post("/api/web/auth/link")
async def player_login(payload: LinkLoginRequest, request: Request, response: Response):
    _require_same_origin(request)
    try:
        credentials = await exchange_link_code(
            payload.uid,
            payload.code,
            PLAYER_SCOPE,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
    except WebAuthError as exc:
        _raise_auth_error(exc)
    _set_session_cookies(
        response,
        request,
        token=credentials.token,
        csrf_token=credentials.csrf_token,
        scope=PLAYER_SCOPE,
        max_age=credentials.expires_in,
    )
    return {"ok": True, "uid": credentials.uid, "csrf_token": credentials.csrf_token}


@router.get("/api/web/session")
async def player_session(request: Request):
    identity = await _identity(request, PLAYER_SCOPE)
    return {
        "authenticated": True,
        "uid": identity.uid,
        "player_name": identity.player_name,
        "csrf_token": request.cookies.get(PLAYER_CSRF_COOKIE, ""),
    }


@router.delete("/api/web/session")
async def player_logout(request: Request, response: Response):
    await _identity(request, PLAYER_SCOPE, write=True)
    await revoke_session(request.cookies.get(PLAYER_SESSION_COOKIE, ""), PLAYER_SCOPE)
    _clear_session_cookies(response, PLAYER_SCOPE)
    return {"ok": True}


@router.get("/api/web/dashboard")
async def player_dashboard(request: Request):
    identity = await _identity(request, PLAYER_SCOPE)
    return await get_dashboard(identity.uid)


@router.get("/api/web/roles")
async def player_roles(request: Request):
    identity = await _identity(request, PLAYER_SCOPE)
    return {"roles": await list_player_roles(identity.uid)}


@router.get("/api/web/inventory")
async def player_inventory(request: Request, page: int = 1, page_size: int = 40):
    identity = await _identity(request, PLAYER_SCOPE)
    return await list_player_inventory(identity.uid, page, page_size)


@router.get("/api/web/dungeons")
async def player_dungeons(request: Request, page: int = 1, page_size: int = 12):
    identity = await _identity(request, PLAYER_SCOPE)
    try:
        return await list_player_dungeons(identity.uid, page, page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/web/command")
async def player_command(payload: CommandRequest, request: Request):
    identity = await _identity(request, PLAYER_SCOPE, write=True)
    try:
        return await dispatch_web_command(
            identity.uid,
            payload.command,
            request_id=payload.request_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/web/dao-heart")
async def player_dao_heart(request: Request):
    identity = await _identity(request, PLAYER_SCOPE)
    try:
        return await get_daily_state(identity.uid)
    except DaoHeartError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/web/dao-heart/choice")
async def player_dao_heart_choice(payload: DaoHeartChoiceRequest, request: Request):
    identity = await _identity(request, PLAYER_SCOPE, write=True)
    try:
        return await choose_daily_path(
            identity.uid,
            payload.choice,
            request_id=payload.request_id,
        )
    except DaoHeartError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/auth/link")
async def admin_login(payload: LinkLoginRequest, request: Request, response: Response):
    _require_same_origin(request)
    try:
        credentials = await exchange_link_code(
            payload.uid,
            payload.code,
            ADMIN_SCOPE,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
    except WebAuthError as exc:
        _raise_auth_error(exc)
    _set_session_cookies(
        response,
        request,
        token=credentials.token,
        csrf_token=credentials.csrf_token,
        scope=ADMIN_SCOPE,
        max_age=credentials.expires_in,
    )
    return {"ok": True, "uid": credentials.uid, "csrf_token": credentials.csrf_token}


@router.get("/api/admin/session")
async def admin_session(request: Request):
    identity = await _identity(request, ADMIN_SCOPE)
    return {
        "authenticated": True,
        "uid": identity.uid,
        "player_name": identity.player_name,
        "csrf_token": request.cookies.get(ADMIN_CSRF_COOKIE, ""),
    }


@router.delete("/api/admin/session")
async def admin_logout(request: Request, response: Response):
    await _identity(request, ADMIN_SCOPE, write=True)
    await revoke_session(request.cookies.get(ADMIN_SESSION_COOKIE, ""), ADMIN_SCOPE)
    _clear_session_cookies(response, ADMIN_SCOPE)
    return {"ok": True}


@router.get("/api/admin/players")
async def admin_players(request: Request, q: str = "", limit: int = 20):
    await _identity(request, ADMIN_SCOPE)
    return {"players": await search_players(q, limit)}


@router.get("/api/admin/items")
async def admin_items(request: Request, q: str = "", limit: int = 30):
    await _identity(request, ADMIN_SCOPE)
    return {"items": await search_items(q, limit)}


async def _audit_safely(**kwargs):
    try:
        await write_admin_audit(**kwargs)
    except Exception:
        # gm_service 自身的 gm_operation_log 与 reward_ledger 仍是发放权威审计。
        LOGGER.exception("记录网页管理审计失败: %s", kwargs.get("request_id"))


@router.post("/api/admin/grants/item")
async def admin_grant_item(payload: ItemGrantRequest, request: Request):
    identity = await _identity(request, ADMIN_SCOPE, write=True)
    request_id = payload.request_id or f"web-admin:{uuid4().hex}"
    try:
        result = await grant_item(
            operator_uid=identity.uid,
            target_uid=payload.target_uid,
            item_key=payload.item_key.strip(),
            amount=payload.amount,
            request_id=request_id,
        )
    except GMError as exc:
        await _audit_safely(
            request_id=request_id,
            operator_uid=identity.uid,
            target_uid=payload.target_uid,
            action="GRANT_ITEM",
            status="FAILED",
            detail={"error": str(exc), "item_key": payload.item_key, "amount": payload.amount},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _audit_safely(
        request_id=request_id,
        operator_uid=identity.uid,
        target_uid=payload.target_uid,
        action="GRANT_ITEM",
        status="SUCCESS",
        detail=result,
    )
    return {"ok": True, "request_id": request_id, "result": result}


@router.post("/api/admin/grants/xianyu")
async def admin_grant_xianyu(payload: XianyuGrantRequest, request: Request):
    identity = await _identity(request, ADMIN_SCOPE, write=True)
    request_id = payload.request_id or f"web-admin:{uuid4().hex}"
    try:
        result = await grant_xianyu(
            operator_uid=identity.uid,
            target_uid=payload.target_uid,
            amount=payload.amount,
            request_id=request_id,
        )
    except GMError as exc:
        await _audit_safely(
            request_id=request_id,
            operator_uid=identity.uid,
            target_uid=payload.target_uid,
            action="GRANT_XIANYU",
            status="FAILED",
            detail={"error": str(exc), "amount": payload.amount},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _audit_safely(
        request_id=request_id,
        operator_uid=identity.uid,
        target_uid=payload.target_uid,
        action="GRANT_XIANYU",
        status="SUCCESS",
        detail=result,
    )
    return {"ok": True, "request_id": request_id, "result": result}


@router.get("/api/admin/audit")
async def admin_audit(request: Request, limit: int = 50):
    await _identity(request, ADMIN_SCOPE)
    return {"records": await list_admin_audit(limit)}


def install_web_routes(app: FastAPI) -> None:
    app.include_router(router)
    app.mount("/web/static", StaticFiles(directory=STATIC_ROOT), name="web-static")
    app.mount("/web/fonts", StaticFiles(directory=FONT_ROOT), name="web-fonts")
