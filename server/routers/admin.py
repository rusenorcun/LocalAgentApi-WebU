"""API v2 — Admin router: kullanıcı yönetimi, istatistik, audit log, ayarlar."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config, settings
from ..auth_v2 import require_admin, audit
from ..database import AuditLog, Chat, Message, Session, User, get_session

router = APIRouter(prefix="/api/v2/admin", tags=["admin"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Kullanıcılar ─────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()

    # P4: N+1 yerine tek GROUP BY sorgusuyla aktif oturum sayıları
    sess_rows = await db.execute(
        select(Session.user_id, func.count())
        .where(
            Session.revoked == False,       # noqa: E712
            Session.expires_at > _utcnow(),
        )
        .group_by(Session.user_id)
    )
    active_map = {uid: cnt for uid, cnt in sess_rows.all()}

    out = []
    for u in users:
        active_sessions = active_map.get(u.id, 0)
        out.append({
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "locked_until": u.locked_until.isoformat() if u.locked_until else None,
            "failed_attempts": u.failed_attempts,
            "active_sessions": active_sessions,
        })
    return {"users": out}


class RolePatch(BaseModel):
    role: str  # "user" | "admin"


@router.patch("/users/{user_id}/role")
async def set_role(
    user_id: int,
    body: RolePatch,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    if body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Geçersiz rol")
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    if target.id == admin.id and body.role != "admin":
        raise HTTPException(status_code=400, detail="Kendi adminliğinizi kaldıramazsınız")
    target.role = body.role
    await db.commit()
    await audit("admin_set_role", user_id=admin.id, username=admin.username,
                detail=f"{target.username} → {body.role}")
    return {"username": target.username, "role": target.role}


@router.post("/users/{user_id}/unlock")
async def unlock_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    target.failed_attempts = 0
    target.locked_until = None
    await db.commit()
    await audit("admin_unlock", user_id=admin.id, username=admin.username,
                detail=target.username)
    return {"unlocked": True}


@router.delete("/users/{user_id}/sessions")
async def revoke_sessions(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Kullanıcının tüm aktif oturumlarını iptal et."""
    await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked == False)  # noqa: E712
        .values(revoked=True)
    )
    await db.commit()
    await audit("admin_revoke_sessions", user_id=admin.id, username=admin.username,
                detail=f"user_id={user_id}")
    return {"revoked": True}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz")
    await db.delete(target)
    await db.commit()
    await audit("admin_delete_user", user_id=admin.id, username=admin.username,
                detail=target.username)
    return {"deleted": True}


# ── İstatistik panosu ─────────────────────────────────────────────────────────

@router.get("/stats")
async def stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    now = _utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    total_chats = (await db.execute(select(func.count()).select_from(Chat))).scalar() or 0
    total_messages = (await db.execute(select(func.count()).select_from(Message))).scalar() or 0

    messages_24h = (await db.execute(
        select(func.count()).select_from(Message).where(Message.created_at >= day_ago)
    )).scalar() or 0

    messages_7d = (await db.execute(
        select(func.count()).select_from(Message).where(Message.created_at >= week_ago)
    )).scalar() or 0

    active_sessions = (await db.execute(
        select(func.count()).select_from(Session).where(
            Session.revoked == False,       # noqa: E712
            Session.expires_at > now,
        )
    )).scalar() or 0

    from ..queue_manager import queue
    from .. import chat as chat_mod

    ollama_ok = await chat_mod.check_model()

    return {
        "totals": {
            "users": total_users,
            "chats": total_chats,
            "messages": total_messages,
        },
        "activity": {
            "messages_24h": messages_24h,
            "messages_7d": messages_7d,
            "active_sessions": active_sessions,
        },
        "queue": queue.stats,
        "ollama": {"status": "ok" if ollama_ok else "error"},
    }


# ── Audit log ────────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit(
    action: str | None = None,
    username: str | None = None,
    limit: int = 100,
    offset: int = 0,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    q = select(AuditLog).order_by(AuditLog.ts.desc())
    if action:
        q = q.where(AuditLog.action == action)
    if username:
        q = q.where(AuditLog.username == username)
    q = q.offset(offset).limit(min(limit, 500))
    result = await db.execute(q)
    rows = result.scalars().all()
    return {
        "logs": [
            {
                "id": r.id,
                "ts": r.ts.isoformat() if r.ts else None,
                "username": r.username,
                "ip": r.ip,
                "action": r.action,
                "detail": r.detail,
            }
            for r in rows
        ]
    }


# ── Sistem ayarları ───────────────────────────────────────────────────────────

class SettingsPatch(BaseModel):
    changes: dict


@router.get("/settings")
async def get_settings(admin: User = Depends(require_admin)):
    return {
        "settings": settings.current(),
        "types": {k: t.__name__ for k, t in settings.EDITABLE.items()},
        "restart_only": ["PORT", "JWT_SECRET", "OLLAMA_HOST"],
    }


@router.put("/settings")
async def update_settings(
    body: SettingsPatch,
    admin: User = Depends(require_admin),
):
    applied = settings.update(body.changes or {})
    await audit("admin_settings_update", user_id=admin.id, username=admin.username,
                detail=str(list(applied.keys())))
    return {"applied": applied, "settings": settings.current()}
