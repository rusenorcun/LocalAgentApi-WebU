"""Aider / OpenAI-compatible Ollama proxy.

Aider ve diger OpenAI uyumlu istemciler, --api-base ile
https://api.rorcun.com/v1 adresini verip --api-key ile baglanti anahtarini
kullanarak yerel/uzak Ollama modellerine erisebilir.

Guvenlik:
  * Bu uclarda da API anahtari ZORUNLUDUR; anahtar olmadan veya yanlissa
    Ollama'ya hic baglanilmaz (401).
  * Her baglanti bir connection_id ile tanimlidir. /v1 yollarinda
    Authorization header'indaki key ile eslesen AKTIF baglanti secilir.
  * Kisisel API key (loc_...) ile gelen isteklerde varsayilan uzak baglanti
    kullanilir; hic uzak baglanti yoksa Yerel Ollama'ya (OLLAMA_HOST) duser.
  * OpenAI tools / tool_calls, cok parcali (list) content ve base64 gorseller
    Ollama formatina cevrilir (Strix, LiteLLM, OpenCode uyumu).
  * Modelin dusunme metni (Ollama "thinking") reasoning_content olarak iletilir.

Aider kullanim ornegi:
    aider --model openai/qwen3-coder:30b \
          --api-base https://api.rorcun.com/v1 \
          --api-key <api_key>
"""
from __future__ import annotations

import json
import secrets
import time
from typing import AsyncGenerator, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config
from ..database import ApiKey, User, get_session
from ..services import model_gate

router = APIRouter(prefix="/api/v2/openai/v1", tags=["openai_proxy"])

# Aider gonderimi: 50MB'a kadar baglam (buyuk kod dosyalari icin).
# read: Ollama'dan gelen iki veri parcasi arasindaki azami bekleme.
# Model RAM'e tasip cok yavas uretse bile istek iptal olmasin diye varsayilan
# SINIRSIZ (API_READ_TIMEOUT=0). Hata olursa (baglanti kopmasi, Ollama hatasi)
# istek yine hemen sonlanir; yalnizca "yavaslik" iptal sebebi degildir.
_READ_TO = float(config.API_READ_TIMEOUT) or None
_OPENAI_TIMEOUT = httpx.Timeout(connect=15.0, read=_READ_TO, write=120.0, pool=None)


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
    """Aktif uzak baglanti listesinden varsayilani veya tek olani secer.

    Uzak baglanti yoksa (veya hicbiri varsayilan degilse ve tek degilse degil),
    kisisel API key ile gelen istekler icin Yerel Ollama'ya (OLLAMA_HOST) duser.
    """
    candidates = [c for c in connections if c.get("enabled", True) and not c.get("is_local")]
    if not candidates:
        local = next((c for c in connections if c.get("is_local")), None)
        if local:
            return local
        raise HTTPException(status_code=400,
                            detail="Kullanılabilir Ollama bağlantısı yok.")
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
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama'ya ulasilamadi ({conn.get('name')} -> {conn.get('base_url')}): {e}",
            )
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


async def _api_options(db: AsyncSession, model: str, req_ctx: int | None,
                       conn: dict | None = None) -> dict:
    """/v1 icin num_ctx/num_gpu.

    num_ctx onceligi: istek > baglantinin num_ctx'i (panel) > global
    API_NUM_CTX > model katalogu. Katalogdaki deger sohbet icin VRAM'e gore
    otomatik hesaplanir; API tarafinda panel ayarini EZMEMELI (eskiden ezdigi
    icin OpenCode/Aider 8192'de kaliyordu).
    num_gpu katalogdan yalnizca secilen baglam katalogla ayniysa alinir;
    farkli baglamda katman sayisini Ollama kendisi hesaplar.
    """
    from .ollama_connections import effective_num_ctx
    opts: dict = {}
    cat_ctx, cat_gpu = None, None
    try:
        from ..services.model_tuner import model_overrides
        cat_ctx, cat_gpu = await model_overrides(db, model)
    except Exception:
        pass
    chosen_ctx = req_ctx or effective_num_ctx(conn) or cat_ctx
    if chosen_ctx and chosen_ctx > 0:
        opts["num_ctx"] = chosen_ctx
    if cat_gpu and chosen_ctx == cat_ctx:
        opts["num_gpu"] = cat_gpu
    return opts



# --- /v1/chat/completions ----------------------------------------------------

class OpenAIMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool|developer)$")
    content: str | list | None = ""
    name: Optional[str] = None
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None


def _to_ollama_message(m: "OpenAIMessage") -> dict:
    """OpenAI mesajini Ollama /api/chat mesajina cevirir (metin parcalari,
    base64 gorseller ve tool call'lar dahil)."""
    role = "system" if m.role == "developer" else m.role
    text_parts: list[str] = []
    images: list[str] = []
    if isinstance(m.content, list):
        for part in m.content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                if url.startswith("data:") and "," in url:
                    images.append(url.split(",", 1)[1])
    elif m.content:
        text_parts.append(m.content)
    out: dict = {"role": role, "content": "\n".join(text_parts)}
    if images:
        out["images"] = images
    if m.tool_calls:
        calls = []
        for tc in m.tool_calls:
            fn = (tc or {}).get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args else {}
                except Exception:
                    args = {"_raw": args}
            calls.append({"function": {"name": fn.get("name", ""), "arguments": args or {}}})
        out["tool_calls"] = calls
    if m.tool_call_id:
        out["tool_call_id"] = m.tool_call_id
    return out


def _to_openai_tool_calls(calls: list | None) -> list | None:
    if not calls:
        return None
    out = []
    for i, tc in enumerate(calls):
        fn = (tc or {}).get("function") or {}
        out.append({
            "id": f"call_{i}_{secrets.token_hex(4)}",
            "type": "function",
            "function": {
                "name": fn.get("name", ""),
                "arguments": json.dumps(fn.get("arguments") or {}, ensure_ascii=False),
            },
        })
    return out


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
    tools: Optional[list] = None
    tool_choice: Optional[str | dict] = None
    # Ollama'ya ozel
    num_ctx: Optional[int] = Field(default=None, ge=1, le=200000)
    keep_alive: Optional[str] = None  # API tavanina kirpilir (config.API_KEEP_ALIVE)


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
    had_tools = False
    role_sent = False

    def _chunk(delta_dict: dict) -> str:
        """Tek bir OpenAI delta parcasi; role yalnizca ilk parcada gider."""
        nonlocal idx, role_sent
        if not role_sent:
            delta_dict = {"role": "assistant", **delta_dict}
            role_sent = True
        out = {
            "id": f"chatcmpl-{conn['id']}-{idx}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": ollama_payload["model"],
            "choices": [{"index": 0, "delta": delta_dict, "finish_reason": None}],
        }
        idx += 1
        return f"data: {json.dumps(out, ensure_ascii=False)}\n\n"

    try:
        async with model_gate.api_use(ollama_payload["model"]), \
                client.stream("POST", f"{base}/api/chat",
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
                # Dusunme metni (gpt-oss, qwen3...) reasoning_content olarak gider:
                # OpenCode/AI SDK bunu "dusunuyor" bolumunde gosterir ve uzun
                # akil yurutme sirasinda da istemciye veri (ve basliklar) akar.
                thinking = msg.get("thinking", "")
                if thinking:
                    yield _chunk({"reasoning_content": thinking})
                tcs = _to_openai_tool_calls(msg.get("tool_calls"))
                if tcs:
                    for j, tc in enumerate(tcs):
                        tc["index"] = j
                    yield _chunk({"tool_calls": tcs})
                    had_tools = True
                delta = msg.get("content", "")
                if delta:
                    yield _chunk({"content": delta})
                if chunk.get("done"):
                    # Son parca: finish_reason + usage. OpenCode/AI SDK gibi
                    # istemciler baglam/token gostergesini buradan okur.
                    pt = chunk.get("prompt_eval_count", 0) or 0
                    ct = chunk.get("eval_count", 0) or 0
                    fin = {
                        "id": f"chatcmpl-{conn['id']}-{idx}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": ollama_payload["model"],
                        "choices": [{"index": 0, "delta": {},
                                     "finish_reason": "tool_calls" if had_tools else "stop"}],
                        "usage": {"prompt_tokens": pt, "completion_tokens": ct,
                                  "total_tokens": pt + ct},
                    }
                    yield f"data: {json.dumps(fin)}\n\n"
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
    async with model_gate.api_use(ollama_payload["model"]), \
            httpx.AsyncClient(timeout=_OPENAI_TIMEOUT) as client:
        r = await client.post(f"{base}/api/chat", json=ollama_payload, headers=headers)
        if r.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"Ollama hatasi {r.status_code}: {r.text[:500]}")
        data = r.json()
        msg = data.get("message") or {}
        content = msg.get("content", "")
        tool_calls = _to_openai_tool_calls(msg.get("tool_calls"))
        out_msg: dict = {"role": "assistant", "content": content}
        if msg.get("thinking"):
            out_msg["reasoning_content"] = msg["thinking"]
        if tool_calls:
            out_msg["tool_calls"] = tool_calls
        return {
            "id": f"chatcmpl-{conn['id']}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": ollama_payload["model"],
            "choices": [{
                "index": 0,
                "message": out_msg,
                "finish_reason": "tool_calls" if tool_calls else "stop",
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
    if request.method == "OPTIONS":
        from fastapi import Response
        return Response(status_code=200)
    if request.method == "GET":
        return {"status": "ok"}

    body_bytes = await request.body()
    try:
        req = OpenAIChatRequest.model_validate_json(body_bytes)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Gecersiz istek: {e}")

    provided_key = _extract_bearer(request)
    conn = await _resolve_connection(provided_key, db)

    # Ollama /api/chat payload'i olustur
    messages = [_to_ollama_message(m) for m in req.messages]

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
        "keep_alive": model_gate.api_keep_alive(req.keep_alive),
    }
    if options:
        ollama_payload["options"] = options
    ollama_payload["options"] = ollama_payload.get("options", {}) | \
        await _api_options(db, req.model, req.num_ctx, conn)
    if req.stop:
        stops = [req.stop] if isinstance(req.stop, str) else req.stop
        ollama_payload["options"] = ollama_payload.get("options", {}) | {"stop": stops}
    if req.tools and req.tool_choice != "none":
        ollama_payload["tools"] = req.tools

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
    keep_alive: Optional[str] = None  # API tavanina kirpilir (config.API_KEEP_ALIVE)


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
        "keep_alive": model_gate.api_keep_alive(req.keep_alive),
    }
    ollama_payload["options"] = options | await _api_options(db, req.model, None, conn)

    base = _ollama_base_from_connection(conn)
    headers = {}
    if conn.get("api_key"):
        headers["Authorization"] = f"Bearer {conn['api_key']}"

    if req.stream:
        async def gen():
            client = httpx.AsyncClient(timeout=_OPENAI_TIMEOUT)
            idx = 0
            try:
                async with model_gate.api_use(req.model), \
                        client.stream("POST", f"{base}/api/generate",
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
                            "created": int(time.time()),
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

    async with model_gate.api_use(req.model), \
            httpx.AsyncClient(timeout=_OPENAI_TIMEOUT) as client:
        r = await client.post(f"{base}/api/generate", json=ollama_payload, headers=headers)
        if r.status_code != 200:
            raise HTTPException(status_code=502,
                                detail=f"Ollama hatasi {r.status_code}: {r.text[:500]}")
        data = r.json()
        return {
            "id": f"cmpl-{conn['id']}",
            "object": "text_completion",
            "created": int(time.time()),
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
