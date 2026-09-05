"""Güvenlik: rate limiting + güvenlik başlıkları + CSP nonce + güvenilir IP."""
import base64
import os as _os

from slowapi import Limiter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Guvenilir reverse proxy'ler (Caddy ayni makinede calisir). Yalniz bu
# adreslerden gelen isteklerde X-Forwarded-For'a guvenilir; istemcinin kendi
# gonderdigi sahte XFF yok sayilir (audit zehirleme / rate-limit atlatma önlemi).
TRUSTED_PROXIES = {
    p.strip() for p in _os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if p.strip()
}


def client_ip(request: Request) -> str:
    """Gerçek istemci IP'si.

    - Bağlantı güvenilir proxy'den geliyorsa: XFF'in SON değeri alınır
      (proxy'nin kendisinin EKLEDİĞİ değer; istemcinin öne koyduğu sahte
      girişler solda kalır ve yok sayılır).
    - Aksi halde doğrudan soket adresi kullanılır.
    """
    peer = request.client.host if request.client else "unknown"
    if peer in TRUSTED_PROXIES:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            last = xff.split(",")[-1].strip()
            if last:
                return last
    return peer


# Rate limit anahtarı: proxy arkasında tüm istekler 127.0.0.1 görünmesin —
# gerçek istemci IP'sine göre kova ayrılır (kişi başı limit anlamlı kalır).
limiter = Limiter(key_func=client_ip, default_limits=["240/minute"])


def _nonce() -> str:
    return base64.b64encode(_os.urandom(16)).decode()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        nonce = _nonce()
        request.state.csp_nonce = nonce

        resp = await call_next(request)

        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        resp.headers["X-XSS-Protection"] = "1; mode=block"

        # SSE / stream yanıtlarda CSP nonce'u atla (header injection sorunu olmaz)
        ct = resp.headers.get("content-type", "")
        if "text/event-stream" not in ct:
            # API yollari nonce'lu siki CSP; web yollari React (Vite) SPA'sina
            # gore: harici script yok, yalnizca Google Fonts'a izin verilir
            # (index.css @import ile Space Grotesk / JetBrains Mono yukluyor).
            if request.url.path.startswith("/api"):
                resp.headers["Content-Security-Policy"] = (
                    f"default-src 'self'; "
                    f"script-src 'self' 'nonce-{nonce}'; "
                    f"style-src 'self' 'unsafe-inline'; "
                    f"img-src 'self' data: blob:; "
                    f"connect-src 'self' ws: wss:; "
                    f"font-src 'self' data:; "
                    f"base-uri 'self'; "
                    f"frame-ancestors 'none'"
                )
            else:
                resp.headers["Content-Security-Policy"] = (
                    "default-src 'self'; "
                    "script-src 'self'; "
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                    "img-src 'self' data: blob:; "
                    "connect-src 'self' ws: wss:; "
                    "font-src 'self' data: https://fonts.gstatic.com; "
                    "base-uri 'self'; "
                    "frame-ancestors 'none'"
                )
        return resp
