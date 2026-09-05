"""API v2 — Güvenli Ollama proxy (api.rorcun.com/ollama/...).

Bu router, uzak istemcilerin api.rorcun.com üzerinden yerel/uzak Ollama
endpoint'lerine erişmesini sağlar. Asla doğrudan Ollama'ya açık proxy
değildir; her istek:

  1. JWT admin yetkisiyle FastAPI'ye gelir,
  2. İstekteki Authorization: Bearer <key> ile kayıtlı bağlantının api_key
     sabit-zamanlı (secrets.compare_digest) karşılaştırılır,
  3. Anahtar uyuşmazsa 401 döner — Ollama'ya bağlantı HIÇ başlamaz,
  4. Uyuşursa istek ilgili Ollama base_url'e iletilir; yanıt/stream aynen
     istemciye aktarılır.

Desteklenen yöntemler: GET/POST (Ollama'nın /api/tags, /api/chat,
/api/generate, /api/ps, /api/show, /api/pull, /api/embed vb. uçları).
"""
from __future__ import annotations

import json
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from httpx import Timeout

from .. import config
from ..auth_v2 import require_admin
from ..database import User

# Ollama proxy için timeout: uzun üretimler/streaming göz önünde bulunduruldu.
_PROXY_TIMEOUT = Timeout(connect=10.0, read=3600.0, write=60.0, pool=10.0)

router = APIRouter(prefix="/api/v2/ollama/proxy", tags=["ollama_proxy"])


def _load_connections() -> list[dict]:
    from .ollama_connections import _list_items
    return _list_items()


def _get_connection(connection_id: str) -> Optional[dict]:
    return next((c for c in _load_connections() if c.get("id") == connection_id), None)


def _verify_api_key(conn: dict, provided: str | None) -> bool:
    expected = conn.get("api_key")
    if not expected:
        # Yönetici proxy'yi kullanmak istiyorsa bağlantıya mutlaka key tanımlanmalı.
        return False
    if not provided:
        return False
    try:
        import secrets as _secrets
        return _secrets.compare_digest(provided, expected)
    except Exception:
        return False


async def _read_request_body(request: Request) -> tuple[bytes, str]:
    """Raw body + Content-Type döndürür."""
    body = await request.body()
    ct = request.headers.get("content-type", "")
    return body, ct


@router.api_route("/{connection_id}/{path:path}", methods=["GET", "POST", "DELETE"])
async def ollama_proxy(
    connection_id: str,
    path: str,
    request: Request,
    _admin: User = Depends(require_admin),
):
    """Kayıtlı bağlantıya API key doğrulaması yaparak güvenli proxy."""
    conn = _get_connection(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")
    if not conn.get("enabled", True):
        raise HTTPException(status_code=400, detail="Bağlantı devre dışı")

    # API key zorunlu — olmadan Ollama'ya bağlantı başlamaz.
    auth_header = request.headers.get("authorization", "")
    provided_key = ""
    if auth_header.lower().startswith("bearer "):
        provided_key = auth_header[7:].strip()
    if not _verify_api_key(conn, provided_key):
        raise HTTPException(
            status_code=401,
            detail="Geçersiz veya eksik Ollama API anahtarı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    base_url = conn["base_url"].rstrip("/")
    target_url = f"{base_url}/{path}"

    # İstek header'larını aktar; host/by/atıf header'ları Ollama'ya gitmesin.
    forward_headers = {}
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in ("host", "authorization", "cookie", "connection", "content-length"):
            continue
        forward_headers[k] = v

    method = request.method
    body, ct = await _read_request_body(request)

    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT, follow_redirects=False) as client:
            req = client.build_request(
                method=method,
                url=target_url,
                headers=forward_headers,
                content=body if body else None,
            )
            r = await client.send(req, stream=True)

            async def stream_response():
                async for chunk in r.aiter_raw():
                    yield chunk
                await r.aclose()

            return StreamingResponse(
                stream_response(),
                status_code=r.status_code,
                headers=dict(r.headers),
                media_type=r.headers.get("content-type"),
            )
    except httpx.ConnectError as e:
        raise HTTPException(status_code=502, detail=f"Ollama'ya bağlanılamadı: {e}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Ollama yanıt vermedi (zaman aşımı).")
