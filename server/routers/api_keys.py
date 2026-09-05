"""API v2 — Kisisel API anahtari yonetimi.

Her kullanici kendi programatik erisim anahtarlarini olusturabilir, listeleyebilir,
askiya alabilir (revoke) veya silebilir. Anahtarlar yalnizca olusturulma aninda
acik metin olarak gosterilir; sonrasi DB'de SHA-256 hash olarak saklanir.

Kapsam (scopes):
  * Bos veya eksik -> tam erisim (mevcut tum /v1 ve /ollama uclari).
  * "read"         -> sadece okuma (orneğin /v1/models, /v1/chat/completions)
  * "write"        -> yazma islemleri (gelecekte eklenecek programatik sohbet uclari)
  * Virgulle ayrilmis liste: "read,write"

Kullanim:
  GET  /api/v2/keys      -> listele
  POST /api/v2/keys      -> olustur (body: name, scopes?)
  PATCH /api/v2/keys/{id} -> guncelle (adi, kapsam, revoked)
  DELETE /api/v2/keys/{id} -> sil
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_v2 import current_user
from ..database import ApiKey, User, get_session

router = APIRouter(prefix="/api/v2/keys", tags=["api_keys"])


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _generate_key() -> str:
    return "loc_" + secrets.token_urlsafe(32)


def _mask_key(key: str) -> str:
    if len(key) <= 12:
        return "***"
    return key[:6] + "..." + key[-4:]


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: Optional[str] = Field(default="", max_length=256)


class KeyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    scopes: Optional[str] = Field(default=None, max_length=256)
    revoked: Optional[bool] = None


class KeyOut(BaseModel):
    id: int
    name: str
    scopes: str
    revoked: bool
    created_at: str
    last_used_at: Optional[str]
    masked_key: Optional[str]


@router.get("", response_model=list[KeyOut])
async def list_keys(user: User = Depends(current_user),
                    db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    return [
        KeyOut(
            id=k.id,
            name=k.name,
            scopes=k.scopes,
            revoked=k.revoked,
            created_at=k.created_at.isoformat() if k.created_at else "",
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            masked_key=None,
        )
        for k in result.scalars().all()
    ]


@router.post("")
async def create_key(
    body: KeyCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    plain = _generate_key()
    key = ApiKey(
        user_id=user.id,
        name=body.name.strip(),
        key_hash=_hash_key(plain),
        scopes=body.scopes.strip() if body.scopes else "",
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return {
        "id": key.id,
        "name": key.name,
        "key": plain,
        "masked_key": _mask_key(plain),
        "scopes": key.scopes,
        "revoked": key.revoked,
        "created_at": key.created_at.isoformat() if key.created_at else "",
    }


@router.patch("/{key_id}")
async def update_key(
    key_id: int,
    body: KeyUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    k = result.scalar_one_or_none()
    if not k:
        raise HTTPException(status_code=404, detail="Anahtar bulunamadi")
    if body.name is not None:
        k.name = body.name.strip()
    if body.scopes is not None:
        k.scopes = body.scopes.strip()
    if body.revoked is not None:
        k.revoked = body.revoked
    if body.revoked is False:
        # Askiya alma kaldirildi; last_used_at'i temizleme gerekmez
        pass
    await db.commit()
    return {
        "id": k.id,
        "name": k.name,
        "scopes": k.scopes,
        "revoked": k.revoked,
        "created_at": k.created_at.isoformat() if k.created_at else "",
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
    }


@router.delete("/{key_id}")
async def delete_key(
    key_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
    )
    k = result.scalar_one_or_none()
    if not k:
        raise HTTPException(status_code=404, detail="Anahtar bulunamadi")
    await db.delete(k)
    await db.commit()
    return {"deleted": True}


# --- Ortak dogrulama (diger router'lar tarafindan kullanilir) ----------------

async def current_user_by_api_key(
    provided: str | None,
    db: AsyncSession,
) -> tuple[User, ApiKey] | None:
    """DB'deki gecerli bir API key ile kullanici dondurur; yoksa None."""
    if not provided:
        return None
    h = _hash_key(provided)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == h, ApiKey.revoked == False)  # noqa: E712
    )
    key = result.scalar_one_or_none()
    if not key:
        return None
    # Kullanici yukle
    user_result = await db.execute(
        select(User).where(User.id == key.user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        return None
    key.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return user, key


def api_key_has_scope(key: ApiKey, scope: str) -> bool:
    if not key.scopes:
        return True
    allowed = {s.strip().lower() for s in key.scopes.split(",")}
    return not scope or scope.lower() in allowed
