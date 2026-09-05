"""API v2 — Auth router: login, refresh, logout, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import auth_v2, config
from ..services.text_utils import valid_username
from ..auth_v2 import (
    COOKIE_KWARGS, REFRESH_COOKIE, clear_refresh_cookie,
    current_user, get_refresh_cookie, set_refresh_cookie,
)
from ..database import User, get_session

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Gerçek istemci IP'si — XFF'e yalnız güvenilir proxy'den gelirse güvenilir
    (bkz. security.client_ip). İstemcinin sahte XFF'i audit/kilitlemeyi zehirleyemez."""
    from ..security import client_ip
    return client_ip(request)


# ── Şemalar ───────────────────────────────────────────────────────────────────

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=256)


class RegisterBody(Credentials):
    pass


class PreferencesPatch(BaseModel):
    theme: str | None = Field(default=None, pattern="^(light|dark|system)$")
    lang: str | None = Field(default=None, pattern="^(tr|en)$")
    default_model: str | None = Field(default=None, max_length=120)
    persona: str | None = Field(default=None, max_length=8000)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


# ── Endpointler ───────────────────────────────────────────────────────────────

@router.post("/register")
async def register(
    request: Request,
    body: RegisterBody,
    db: AsyncSession = Depends(get_session),
):
    if not config.ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="Kayıt kapalı")
    if not valid_username(body.username):
        raise HTTPException(status_code=400, detail="Geçersiz kullanıcı adı (3-32, harf/rakam/._-)")
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Kullanıcı adı alınmış")

    # İlk kullanıcı otomatik admin
    from sqlalchemy import func
    count_result = await db.execute(select(func.count()).select_from(User))
    is_first = (count_result.scalar() or 0) == 0

    user = User(
        username=body.username,
        pass_hash=auth_v2.hash_password(body.password),
        role="admin" if is_first else "user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    ip = _client_ip(request)
    access = auth_v2.create_access_token(user.username, user.role)
    refresh_raw = auth_v2.generate_refresh_token()
    from ..database import Session as DbSession
    from datetime import timezone, timedelta
    from datetime import datetime
    db.add(DbSession(
        user_id=user.id,
        refresh_hash=auth_v2._hash_token(refresh_raw),
        ip=ip,
        user_agent=request.headers.get("User-Agent", ""),
        expires_at=datetime.now(timezone.utc) + timedelta(days=auth_v2.REFRESH_TTL_DAYS),
    ))
    await db.commit()
    await auth_v2.audit("register", user_id=user.id, username=user.username, ip=ip)

    resp = JSONResponse({"access_token": access, "username": user.username, "role": user.role})
    set_refresh_cookie(resp, refresh_raw)
    return resp


@router.post("/login")
async def login(
    request: Request,
    body: Credentials,
    db: AsyncSession = Depends(get_session),
):
    ip = _client_ip(request)
    ua = request.headers.get("User-Agent", "")
    access, refresh_raw = await auth_v2.login(body.username, body.password, ip, ua, db)

    # Kullanıcı bilgilerini al
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one()

    resp = JSONResponse({
        "access_token": access,
        "username": user.username,
        "role": user.role,
        "theme": user.theme_pref,
        "lang": user.lang_pref or "tr",
    })
    set_refresh_cookie(resp, refresh_raw)
    return resp


@router.post("/refresh")
async def refresh(
    request: Request,
    refresh_token: str | None = Depends(get_refresh_cookie),
    db: AsyncSession = Depends(get_session),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token yok")
    ip = _client_ip(request)
    ua = request.headers.get("User-Agent", "")
    access, new_refresh = await auth_v2.refresh_tokens(refresh_token, ip, ua, db)

    # Kullanıcı bilgilerini al
    payload = auth_v2.decode_access_token(access)
    result = await db.execute(select(User).where(User.username == payload["sub"]))
    user = result.scalar_one()

    resp = JSONResponse({
        "access_token": access,
        "username": user.username,
        "role": user.role,
    })
    set_refresh_cookie(resp, new_refresh)
    return resp


@router.post("/logout")
async def logout(
    request: Request,
    refresh_token: str | None = Depends(get_refresh_cookie),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    if refresh_token:
        await auth_v2.logout(refresh_token, db, _client_ip(request), user.username)
    resp = JSONResponse({"logged_out": True})
    clear_refresh_cookie(resp)
    return resp


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {
        "username": user.username,
        "role": user.role,
        "theme": user.theme_pref,
        "lang": user.lang_pref or "tr",
        "default_model": user.default_model,
        "persona": user.persona or "",
    }


@router.patch("/me/password")
async def change_password(
    body: PasswordChange,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    if not auth_v2.verify_password(body.current_password, user.pass_hash):
        raise HTTPException(status_code=403, detail="Mevcut şifre hatalı")
    user.pass_hash = auth_v2.hash_password(body.new_password)
    await db.commit()
    return {"success": True}


@router.patch("/me/preferences")
async def update_preferences(
    body: PreferencesPatch,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    if body.theme is not None:
        user.theme_pref = body.theme
    if body.lang is not None:
        user.lang_pref = body.lang
    if body.default_model is not None:
        user.default_model = body.default_model
    if body.persona is not None:
        user.persona = body.persona.strip() or None
    await db.commit()
    return {"theme": user.theme_pref, "lang": user.lang_pref, "default_model": user.default_model}
