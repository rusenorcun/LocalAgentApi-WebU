"""
Auth v2 — Argon2id şifre hash, rotasyonlu refresh token, hesap kilitleme, audit log.

Mimari:
  • Access token  : 15 dk ömürlü JWT, Authorization: Bearer header'da taşınır (bellekte)
  • Refresh token : 7 günlük opak token, httpOnly+Secure+SameSite=Strict cookie'de
                    DB'de SHA-256 hash olarak tutulur; her kullanımda rotate edilir
  • Brute-force   : 5 başarısız giriş → 15 dk hesap kilidi; her denemede audit kaydı
  • Şifre geçişi  : Eski bcrypt hash'leri giriş sırasında sessizce Argon2id'e re-hash'lenir
"""
from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import config
from .database import AuditLog, Session, User, async_session_maker, get_session

# ── Argon2id hasher (OWASP önerisi: t=3, m=65536, p=4) ──────────────────────
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

# ── Sabitler ─────────────────────────────────────────────────────────────────
ACCESS_TTL_SECONDS = 15 * 60          # 15 dakika
REFRESH_TTL_DAYS   = 7
MAX_FAILED         = 5
LOCKOUT_MINUTES    = 15


# ── Yardımcı: şu an ─────────────────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite DateTime tz bilgisini düşürür; karşılaştırma öncesi UTC'ye tamamla."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


# ── Şifre işlemleri ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Argon2id ile hash üret."""
    return _ph.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Argon2id veya bcrypt hash doğrula.
    Argon2id ise doğrudan; bcrypt ise python-bcrypt ile.
    """
    if stored_hash.startswith("$argon2"):
        try:
            return _ph.verify(stored_hash, password)
        except (VerifyMismatchError, VerificationError):
            return False
        except Exception:
            return False
    elif stored_hash.startswith("$2"):
        # Eski bcrypt — python-bcrypt ile doğrula
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
        except Exception:
            return False
    return False


def needs_rehash(stored_hash: str) -> bool:
    """Argon2id değilse veya parametre eskiyse True döner."""
    if not stored_hash.startswith("$argon2"):
        return True
    try:
        return _ph.check_needs_rehash(stored_hash)
    except Exception:
        return False


# ── Token üretimi ─────────────────────────────────────────────────────────────

def create_access_token(username: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + ACCESS_TTL_SECONDS,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALG)


def decode_access_token(token: str) -> dict:
    """Token çöz; geçersizse HTTPException fırlat."""
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Oturum süresi doldu")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Geçersiz token")


def _hash_token(token: str) -> str:
    """Refresh token'ı SHA-256 ile hash'le (DB'de plain token saklanmaz)."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_refresh_token() -> str:
    """32 byte rastgele URL-safe token."""
    return secrets.token_urlsafe(32)


# ── Audit log ────────────────────────────────────────────────────────────────

async def audit(action: str, user_id: int | None = None,
                username: str | None = None, ip: str | None = None,
                detail: str | None = None) -> None:
    async with async_session_maker() as session:
        session.add(AuditLog(
            user_id=user_id, username=username,
            ip=ip, action=action, detail=detail,
        ))
        await session.commit()


# ── Login akışı ──────────────────────────────────────────────────────────────

async def login(
    username: str,
    password: str,
    ip: str,
    user_agent: str,
    db: AsyncSession,
) -> tuple[str, str]:
    """
    Kullanıcı doğrula; access token + refresh token döndür.
    Başarısızlıkta kilitleme sayacını artır, başarıda sıfırla.
    """
    result = await db.execute(select(User).where(User.username == username))
    user: User | None = result.scalar_one_or_none()

    # Zamanlama saldırısı önlemi: kullanıcı yoksa da hash işlemi yap
    dummy_hash = "$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy"
    target_hash = user.pass_hash if user else dummy_hash

    # Hesap kilitli mi? (SQLite naive datetime döndürür — _aware ile normalize et)
    locked_until = _aware(user.locked_until) if user else None
    if user and locked_until and locked_until > _utcnow():
        remaining = int((locked_until - _utcnow()).total_seconds() / 60) + 1
        await audit("login_blocked", user_id=user.id, username=username,
                    ip=ip, detail=f"Hesap kilitli, {remaining} dk kaldı")
        raise HTTPException(
            status_code=429,
            detail=f"Çok fazla başarısız giriş. {remaining} dakika bekleyin."
        )

    ok = verify_password(password, target_hash)

    if not ok or user is None:
        if user:
            new_count = user.failed_attempts + 1
            lock_until = None
            if new_count >= MAX_FAILED:
                lock_until = _utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            await db.execute(
                update(User)
                .where(User.id == user.id)
                .values(failed_attempts=new_count, locked_until=lock_until)
            )
            await db.commit()
            await audit("login_failed", user_id=user.id, username=username,
                        ip=ip, detail=f"Deneme {new_count}/{MAX_FAILED}")
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı")

    # Başarılı giriş
    # Şeffaf Argon2id re-hash
    if needs_rehash(user.pass_hash):
        user.pass_hash = hash_password(password)

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = _utcnow()
    await db.flush()

    # Refresh token oluştur ve kaydet
    refresh_raw = generate_refresh_token()
    refresh_hash = _hash_token(refresh_raw)
    expires_at = _utcnow() + timedelta(days=REFRESH_TTL_DAYS)
    db.add(Session(
        user_id=user.id,
        refresh_hash=refresh_hash,
        user_agent=user_agent[:256] if user_agent else None,
        ip=ip,
        expires_at=expires_at,
    ))
    await db.commit()

    access = create_access_token(user.username, user.role)
    await audit("login_ok", user_id=user.id, username=username, ip=ip)
    return access, refresh_raw


async def refresh_tokens(
    refresh_raw: str,
    ip: str,
    user_agent: str,
    db: AsyncSession,
) -> tuple[str, str]:
    """Refresh token'ı doğrula, eski oturumu iptal et, yeni çift üret."""
    token_hash = _hash_token(refresh_raw)
    result = await db.execute(
        select(Session).where(
            Session.refresh_hash == token_hash,
            Session.revoked == False,      # noqa: E712
            Session.expires_at > _utcnow(),
        )
    )
    sess: Session | None = result.scalar_one_or_none()

    if not sess:
        # G8 — Reuse detection: token hash'i DB'de VAR ama revoked/expired ise
        # bu, rotate edilmiş (eski) bir refresh token'ın yeniden kullanımıdır →
        # büyük olasılıkla çalıntı. O kullanıcının TÜM oturumları iptal edilir.
        reused_result = await db.execute(
            select(Session).where(Session.refresh_hash == token_hash)
        )
        reused: Session | None = reused_result.scalar_one_or_none()
        if reused:
            await db.execute(
                update(Session)
                .where(Session.user_id == reused.user_id)
                .values(revoked=True)
            )
            await db.commit()
            u_res = await db.execute(select(User).where(User.id == reused.user_id))
            u = u_res.scalar_one_or_none()
            await audit(
                "refresh_reuse_detected",
                user_id=reused.user_id,
                username=(u.username if u else None),
                ip=ip,
                detail="Rotate edilmiş refresh token yeniden kullanıldı — tüm oturumlar iptal edildi",
            )
        else:
            await audit("refresh_invalid", ip=ip, detail="Geçersiz refresh token")
        raise HTTPException(status_code=401, detail="Oturum geçersiz")

    # Kullanıcıyı yükle
    user_result = await db.execute(select(User).where(User.id == sess.user_id))
    user: User | None = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")

    # Eski oturumu iptal et (token rotation)
    sess.revoked = True
    await db.flush()

    # Yeni refresh token
    new_refresh_raw = generate_refresh_token()
    new_refresh_hash = _hash_token(new_refresh_raw)
    expires_at = _utcnow() + timedelta(days=REFRESH_TTL_DAYS)
    db.add(Session(
        user_id=user.id,
        refresh_hash=new_refresh_hash,
        user_agent=user_agent[:256] if user_agent else None,
        ip=ip,
        expires_at=expires_at,
    ))
    await db.commit()

    new_access = create_access_token(user.username, user.role)
    await audit("token_refreshed", user_id=user.id, username=user.username, ip=ip)
    return new_access, new_refresh_raw


async def logout(refresh_raw: str, db: AsyncSession, ip: str = "", username: str = "") -> None:
    """Refresh token'ı iptal et."""
    token_hash = _hash_token(refresh_raw)
    result = await db.execute(
        select(Session).where(Session.refresh_hash == token_hash)
    )
    sess = result.scalar_one_or_none()
    if sess:
        sess.revoked = True
        await db.commit()
    await audit("logout", username=username, ip=ip)


# ── FastAPI Depends yardımcıları ──────────────────────────────────────────────

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402

_bearer = HTTPBearer(auto_error=False)


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_session),
) -> User:
    """Geçerli access token'dan User döner."""
    if creds is None:
        raise HTTPException(status_code=401, detail="Yetkilendirme gerekli")
    payload = decode_access_token(creds.credentials)
    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    return user


# ── Cookie yardımcıları ───────────────────────────────────────────────────────

REFRESH_COOKIE = "refresh_token"
COOKIE_KWARGS = dict(
    httponly=True,
    secure=config.COOKIE_SECURE,   # HTTPS arkasinda true; yerel HTTP testi icin env ile kapatilabilir
    samesite="strict",
    path="/api/v2/auth",
    max_age=REFRESH_TTL_DAYS * 86400,
)


def set_refresh_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(REFRESH_COOKIE, token, **COOKIE_KWARGS)


def clear_refresh_cookie(response: JSONResponse) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v2/auth")


def get_refresh_cookie(refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)) -> str | None:
    return refresh_token
