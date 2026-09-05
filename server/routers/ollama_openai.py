"""Aider / OpenAI-compatible Ollama proxy.

Aider ve diger OpenAI uyumlu istemciler, --api-base ile
https://api.rorcun.com/v1 adresini verip --api-key ile baglanti anahtarini
kullanarak yerel/uzak Ollama modellerine erisebilir.

Guvenlik:
  * Bu uclarda da API anahtari ZORUNLUDUR; anahtar olmadan veya yanlissa
    Ollama'ya hic baglanilmaz (401).
  * Her baglanti bir connection_id ile tanimlidir. /v1 yollarinda
    Authorization header'indaki key ile eslesen AKTIF baglanti secilir.
  * Yerel Ollama baglantisinin api_key'i None oldugu icin /v1 uzerinden
    erisilemez; yalnizca uzak/api-key'li baglantilar kullanilabilir.

Aider kullanim ornegi:
    aider --model openai/qwen3-coder:30b \
          --api-base https://api.rorcun.com/v1 \
          --api-key <api_key>
"""
from __future__ import annotations

import json
import secrets
from typing import AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..database import ApiKey, User, get_session

router = APIRouter(prefix="/api/v2/openai/v1", tags=["openai_proxy"])

# Aider gonderimi: 50MB'a kadar baglam (buyuk kod dosyalari icin).
_OPENAI_TIMEOUT = httpx.Timeout(connect=15.0, read=3600.0, write=60.0, pool=10.0)


# --- Ortak dogrulama ---------------------------------------------------------

def _load_connections() -> list[dict]:
    from .ollama_connections import _list_items
    return _list_items()


def _connection_by_direct_key(provided: str | None) -> tuple[dict, str] | None:
    """Key dogrudan bir Ollama baglantisinin api_key'ine eslesiyorsa dondurur."""
    if not provided:
        return None
    candidates = [
        c for c in _load_connections()
        if c.get("enabled", True) and c.get("api_key") and not c.get("is_local")
    ]
    for c in candidates:
        try:
            if secrets.compare_digest(provided, c["api_key"]):
                return c, c["api_key"]
        except Exception:
            pass
    return None


def _select_default_ollama_connection(connections: list[dict]) -> dict:
    """Aktif uzak baglanti listesinden varsayilani veya tek olani secer."""
    candidates = [c for c in connections if c.get("enabled", True) and not c.get("is_local")]
    if not candidates:
        raise HTTPException(status_code=400,
                            detail="Kullanılabilir uzak Ollama bağlantısı yok.")
    default = next((c for c in candidates if c.get("is_default")), None)
    if default:
        return default
    if len(candidates) == 1:
        return candidates[0]
    raise HTTPException(
        status_code=400,
        detail="Birden fazla uzak bağlantı var; varsayılan işaretleyin.",
    )


def _ollama_base_from_connection(conn: dict, use_proxy: bool = False) -> str:
    """Ollama baglantisinin hedef URL'sini dondurur.

    /v1 OpenAI-compatible uclar kendi API key dogrulamasi yapar; bu yuzden
    Ollama'ya dogrudan base_url uzerinden erisir (daha hizli, tek auth).
    Proxy yalnizca harici /ollama/{id}/... cagrilarinda kullanilir.
    """
    if use_proxy and config.OLLAMA_PROXY_FORCE:
        from .ollama_connections import _proxy_url
        return _proxy_url(conn["id"])
    return conn["base_url"].rstrip("/")


# --- /v1/models --------------------------------------------------------------

@router.get("/models")
async def list_openai_models(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """OpenAI /v1/models formatinda mevcut modelleri listele.

    Authorization: Bearer <key>  -> once dogrudan Ollama baglanti key'i,
    sonra kisisel API key olarak dener.
    """
    provided_key = _extract_bearer(request)
    conn = await _resolve_connection(provided_key, db)

    data = []
    for m in conn.get("models", []):
        data.append({
            "id": m,
            "object": "model",
            "created": 0,
            "owned_by": conn["name"],
        })
    if not data:
        try:
            base = _ollama_base_from_connection(conn)
            headers = {}
            if conn.get("api_key"):
                headers["Authorization"] = f"Bearer {conn['api_key']}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{base}/api/tags", headers=headers)
                if r.status_code == 200:
                    for m in r.json().get("models", []):
                        name = m.get("name")
                        if name:
                            data.append({
                                "id": name,
                                "object": "model",
                                "created": 0,
                                "owned_by": conn["name"],
                            })
        except Exception:
            pass
    return {"object": "list", "data": data}


# --- Ortak yardimcilar -------------------------------------------------------

def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def _resolve_connection(provided_key: str | None, db: AsyncSession) -> dict:
    """Once dogrudan Ollama baglanti key'i, sonra kisisel API key dener."""
    if not provided_key:
        raise HTTPException(status_code=401, detail="API anahtari gerekli.",
                            headers={"WWW-Authenticate": "Bearer"})

    direct = _connection_by_direct_key(provided_key)
    if direct:
        return direct[0]

    # Kisisel API key kontrolu
    from .api_keys import current_user_by_api_key
    result = await current_user_by_api_key(provided_key, db)
    if result:
        user, key = result
        # Kisisel key -> varsayilan uzak baglantiyi kullan
        return _select_default_ollama_connection(_load_connections())

    raise HTTPException(status_code=401, detail="Geçersiz API anahtari.",
                        headers={"WWW-Authenticate": "Bearer"})


# --- /v1/chat/completions ----------------------------------------------------

class OpenAIMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str | None = ""
    name: Optional[str] = None


class OpenAIChatRequest(BaseModel):
    model: str = Field(..., min_length=1)
    messages: list[OpenAIMessage]
    stream: bool = False
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[str | list[str]] = None
    # Ollama'ya ozel
    num_ctx: Optional[int] = Field(default=None, ge=1, le=200000)
    keep_alive: Optional[str] = "5m"


async def _openai_chat_stream(
    conn: dict,
    ollama_payload: dict,
) -> AsyncGenerator[str, None]:
    """Ollama /api/chat streaming yapisini OpenAI SSE formatina cevirir."""
    base = _ollama_base_from_connection(conn)
    headers = {}
    if conn.get("api_key"):
        headers["Authorization"] = f"Bearer {conn['api_key']}"
    client = httpx.AsyncClient(timeout=_OPENAI_TIMEOUT)
    idx = 0

    try:
        async with client.stream("POST", f"{base}/api/chat",
                                 json=ollama_payload, headers=headers) as resp:
            if resp.status_code != 200:
                text = await resp.aread()
                yield f"data: {json.dumps({'error': {'message': text.decode('utf-8', 'replace')[:500], 'type': 'ollama_error'}})}\n\n"
                yield "data: [DONE]\n\n"
                return

            async for line in resp.aiter_lines():
                if not line or not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue
                msg = chunk.get("message") or {}
                delta = msg.get("content", "")
                if chunk.get("done") and not delta:
                    break
                if not delta and not chunk.get("done"):
                    continue
                out = {
                    "id": f"chatcmpl-{conn['id']}-{idx}",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": ollama_payload["model"],
                    "choices": [{
                        "index": 0,
                        "delta": {"content": delta},
                        "finish_reason": "stop" if chunk.get("done") else None,
                    }],
                }
                yield f"data: {json.dumps(out, ensure_ascii=False)}\n\n"
                idx += 1
                if chunk.get("done"):
                    break
            yield "data: [DONE]\n\n"
    finally:
        await client.aclose()


async def _openai_chat_nonstream(
    conn: dict,
    ollama_payload: dict,
) -> dict:
    """Ollama /api/chat non-streaming yapisini OpenAI formatina cevirir."""
    base = _ollama_base_from_connection(conn)
    headers = {}
    if conn.get("api_key"):
        headers["Authorization"] = f"Bearer {conn['api_key']}"
    async with httpx.AsyncClient(timeout=_OPENAI_TIMEOUT) as client:
        r = await client.post(f"{base}/api/chat", json=ollama_payload, headers=headers)
        if r.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"Ollama hatasi {r.status_code}: {r.text[:500]}")
        data = r.json()
        msg = data.get("message") or {}
        content = msg.get("content", "")
        return {
            "id": f"chatcmpl-{conn['id']}",
            "object": "chat.completion",
            "created": 0,
            "model": ollama_payload["model"],
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": (data.get("prompt_eval_count", 0) + data.get("eval_count", 0)),
            },
        }


@router.api_route("/chat/completions", methods=["GET", "POST", "OPTIONS"])
async def openai_chat_completions(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """OpenAI /v1/chat/completions ucunu Ollama /api/chat'e cevir."""
    body_bytes = await request.body()
    try:
        req = OpenAIChatRequest.model_validate_json(body_bytes)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Gecersiz istek: {e}")

    provided_key = _extract_bearer(request)
    conn = await _resolve_connection(provided_key, db)

    # Ollama /api/chat payload'i olustur
    messages = []
    for m in req.messages:
        messages.append({"role": m.role, "content": m.content or ""})

    options: dict = {}
    if req.temperature is not None:
        options["temperature"] = req.temperature
    if req.top_p is not None:
        options["top_p"] = req.top_p
    if req.max_tokens is not None:
        options["num_predict"] = req.max_tokens

    ollama_payload = {
        "model": req.model,
        "messages": messages,
        "stream": req.stream,
        "keep_alive": req.keep_alive or "5m",
    }
    if options:
        ollama_payload["options"] = options
    if req.num_ctx:
        ollama_payload["options"] = ollama_payload.get("options", {}) | {"num_ctx": req.num_ctx}

    if req.stream:
        return StreamingResponse(
            _openai_chat_stream(conn, ollama_payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await _openai_chat_nonstream(conn, ollama_payload)


# --- /v1/completions (eskitamamlama) -----------------------------------------

class OpenAICompletionRequest(BaseModel):
    model: str = Field(..., min_length=1)
    prompt: str | list[str] = Field(..., min_length=1)
    stream: bool = False
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    keep_alive: Optional[str] = "5m"


@router.post("/completions")
async def openai_completions(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """OpenAI /v1/completions ucunu Ollama /api/generate'e cevir (string prompt)."""
    body_bytes = await request.body()
    try:
        req = OpenAICompletionRequest.model_validate_json(body_bytes)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Gecersiz istek: {e}")

    provided_key = _extract_bearer(request)
    conn = await _resolve_connection(provided_key, db)

    prompt = req.prompt[0] if isinstance(req.prompt, list) else req.prompt
    options: dict = {}
    if req.temperature is not None:
        options["temperature"] = req.temperature
    if req.max_tokens is not None:
        options["num_predict"] = req.max_tokens

    ollama_payload = {
        "model": req.model,
        "prompt": prompt,
        "stream": req.stream,
        "keep_alive": req.keep_alive or "5m",
    }
    if options:
        ollama_payload["options"] = options

    base = _ollama_base_from_connection(conn)
    headers = {}
    if conn.get("api_key"):
        headers["Authorization"] = f"Bearer {conn['api_key']}"

    if req.stream:
        async def gen():
            client = httpx.AsyncClient(timeout=_OPENAI_TIMEOUT)
            idx = 0
            try:
                async with client.stream("POST", f"{base}/api/generate",
                                         json=ollama_payload, headers=headers) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except Exception:
                            continue
                        delta = chunk.get("response", "")
                        if chunk.get("done") and not delta:
                            break
                        out = {
                            "id": f"cmpl-{conn['id']}-{idx}",
                            "object": "text_completion.chunk",
                            "created": 0,
                            "model": req.model,
                            "choices": [{
                                "index": 0,
                                "text": delta,
                                "finish_reason": "stop" if chunk.get("done") else None,
                            }],
                        }
                        yield f"data: {json.dumps(out, ensure_ascii=False)}\n\n"
                        idx += 1
                        if chunk.get("done"):
                            break
                    yield "data: [DONE]\n\n"
            finally:
                await client.aclose()
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async with httpx.AsyncClient(timeout=_OPENAI_TIMEOUT) as client:
        r = await client.post(f"{base}/api/generate", json=ollama_payload, headers=headers)
        if r.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"Ollama hatasi {r.status_code}: {r.text[:500]}")
        data = r.json()
        return {
            "id": f"cmpl-{conn['id']}",
            "object": "text_completion",
            "created": 0,
            "model": req.model,
            "choices": [{
                "index": 0,
                "text": data.get("response", ""),
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": (data.get("prompt_eval_count", 0) + data.get("eval_count", 0)),
            },
        }
