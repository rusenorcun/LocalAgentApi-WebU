"""API v2 — Uzak / yerel Ollama bağlantı yönetimi.

Panelin MCP Server sayfasına eklenecek "Ollama API Bağlantıları" bölümünü
besler. Her bağlantı bir isim, temel URL, ZORUNLU API anahtarı ve notlarla
saklanır. Mevcut yerel Ollama (config.OLLAMA_HOST) editlemez ama liste içinde
görünür.

Güvenlik:
  * API anahtarı ZORUNLUDUR. Anahtar olmadan proxy üzerinden Ollama'ya
    bağlantı hiç başlamaz (FastAPI 401 döner).
  * API anahtarları yalnızca sunucu tarafında saklanır; frontend'e
    maskelenmiş hali (son 4 karakter) gider.
  * Uzak bağlantılar api.rorcun.com/ollama/{id}/... proxy'sinden geçer;
    doğrudan Ollama dışarıya açık değildir.
  * Tüm yazma uçları admin yetkisi gerektirir; listeleme ise giriş yapmış
    kullanıcılara açıktır (tool seçimi için).
"""
from __future__ import annotations

import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from .. import config
from ..auth_v2 import current_user, require_admin
from ..database import User

router = APIRouter(prefix="/api/v2/ollama", tags=["ollama_connections"])

_CONNS_FILE: Path = config.DATA_DIR / "ollama_connections.json"

# --- Şemalar -----------------------------------------------------------------

class ConnectionBase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=500)
    is_default: bool = False
    enabled: bool = True
    notes: Optional[str] = Field(default=None, max_length=300)

    @field_validator("base_url")
    @classmethod
    def _normalize_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL http:// veya https:// ile başlamalı")
        return v


class ConnectionCreate(ConnectionBase):
    @field_validator("api_key")
    @classmethod
    def _key_required(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.strip():
            raise ValueError("Uzak Ollama bağlantıları için API anahtarı zorunludur.")
        return v.strip()


class ConnectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    base_url: Optional[str] = Field(default=None, max_length=500)
    api_key: Optional[str] = Field(default=None, max_length=500)
    is_default: Optional[bool] = None
    enabled: Optional[bool] = None
    notes: Optional[str] = Field(default=None, max_length=300)

    @field_validator("api_key")
    @classmethod
    def _key_nonempty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("API anahtarı boş bırakılamaz; silmek için bağlantıyı silin.")
        return v.strip()


class ConnectionOut(BaseModel):
    id: str
    name: str
    base_url: str
    proxy_url: str
    api_key_masked: Optional[str]
    is_default: bool
    enabled: bool
    is_local: bool
    is_https: bool
    notes: Optional[str]
    last_seen_ok: Optional[str]
    models: list[str]


def _proxy_url(connection_id: str) -> str:
    return f"https://{config.OLLAMA_PROXY_DOMAIN}{config.OLLAMA_PROXY_PATH}/{connection_id}"


# --- Depo --------------------------------------------------------------------

def _mask_key(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    if len(key) <= 8:
        return "***"
    return "***" + key[-4:]


def _load_raw() -> list[dict]:
    if not _CONNS_FILE.is_file():
        return []
    try:
        data = json.loads(_CONNS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save_raw(items: list[dict]) -> None:
    _CONNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONNS_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _ensure_local_default(items: list[dict]) -> list[dict]:
    """Listede yerel Ollama bağlantısı yoksa ekle."""
    local_id = "__local_default__"
    if not any(i.get("id") == local_id for i in items):
        items.insert(0, {
            "id": local_id,
            "name": "Yerel Ollama",
            "base_url": config.OLLAMA_HOST.rstrip("/"),
            "api_key": None,
            "is_default": not any(i.get("is_default") for i in items),
            "enabled": True,
            "is_local": True,
            "notes": "Ortam değişkeni OLLAMA_HOST tarafından belirlenir.",
            "last_seen_ok": None,
            "models": [],
        })
    else:
        for i in items:
            if i.get("id") == local_id:
                i["base_url"] = config.OLLAMA_HOST.rstrip("/")
                i["is_local"] = True
    return items


def _list_items() -> list[dict]:
    items = _load_raw()
    items = _ensure_local_default(items)
    return items


def _get_item(item_id: str) -> Optional[dict]:
    return next((i for i in _list_items() if i.get("id") == item_id), None)


def _persist(items: list[dict]) -> None:
    # Yerel default dışarıya yazılmaz (env'den gelir).
    _save_raw([i for i in items if not i.get("is_local")])


# --- Ollama istemcisi --------------------------------------------------------

async def _ollama_get(base_url: str, path: str, api_key: Optional[str] = None,
                      timeout: float = 10.0):
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await client.get(f"{base_url}{path}", headers=headers)


async def _test_connection(item: dict) -> tuple[bool, list[str], Optional[str]]:
    """(ok, model_adlari, hata_mesaji) döner. Yerel bağlantıya doğrudan,
    uzak bağlantıya proxy üzerinden (api.rorcun.com/ollama/{id}/...) test atar."""
    if item.get("is_local"):
        base_url = item["base_url"]
        api_key = item.get("api_key")
        path_prefix = ""
    else:
        if config.OLLAMA_PROXY_FORCE:
            base_url = f"https://{config.OLLAMA_PROXY_DOMAIN}"
            api_key = item.get("api_key")
            path_prefix = f"{config.OLLAMA_PROXY_PATH}/{item['id']}"
        else:
            base_url = item["base_url"]
            api_key = item.get("api_key")
            path_prefix = ""
    try:
        r = await _ollama_get(base_url, f"{path_prefix}/api/tags", api_key=api_key, timeout=12.0)
        if r.status_code == 401:
            return False, [], "Yetkilendirme hatası (401) — API anahtarını kontrol edin."
        if r.status_code != 200:
            return False, [], f"Ollama hatası {r.status_code}: {r.text[:200]}"
        data = r.json()
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return True, models, None
    except httpx.ConnectError as e:
        return False, [], f"Bağlanılamadı: {e}"
    except httpx.TimeoutException:
        return False, [], "Zaman aşımı — bağlantı çok yavaş veya erişilemiyor."
    except Exception as e:
        return False, [], f"Hata: {e}"


def _to_out(item: dict) -> ConnectionOut:
    return ConnectionOut(
        id=item["id"],
        name=item["name"],
        base_url=item["base_url"],
        proxy_url=_proxy_url(item["id"]),
        api_key_masked=_mask_key(item.get("api_key")),
        is_default=bool(item.get("is_default")),
        enabled=bool(item.get("enabled", True)),
        is_local=bool(item.get("is_local")),
        is_https=item["base_url"].startswith("https://"),
        notes=item.get("notes"),
        last_seen_ok=item.get("last_seen_ok"),
        models=item.get("models", []),
    )


# --- Uçlar -------------------------------------------------------------------

@router.get("/connections", response_model=list[ConnectionOut])
async def list_connections(_user: User = Depends(current_user)):
    """Tüm Ollama bağlantılarını listele (giriş yapmış kullanıcı)."""
    return [_to_out(i) for i in _list_items()]


@router.get("/connections/{connection_id}", response_model=ConnectionOut)
async def get_connection(connection_id: str, _user: User = Depends(current_user)):
    item = _get_item(connection_id)
    if not item:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")
    return _to_out(item)


@router.post("/connections", response_model=ConnectionOut)
async def create_connection(body: ConnectionCreate, _admin: User = Depends(require_admin)):
    items = _list_items()
    new_id = str(uuid.uuid4())
    new_item = {
        "id": new_id,
        "name": body.name.strip(),
        "base_url": body.base_url,
        "api_key": body.api_key.strip() if body.api_key else None,
        "is_default": bool(body.is_default),
        "enabled": bool(body.enabled),
        "is_local": False,
        "notes": body.notes,
        "last_seen_ok": None,
        "models": [],
    }
    if body.is_default:
        for i in items:
            if not i.get("is_local"):
                i["is_default"] = False
    elif not any(i.get("is_default") for i in items if not i.get("is_local")):
        new_item["is_default"] = True
    items.append(new_item)
    _persist(items)
    return _to_out(new_item)


@router.patch("/connections/{connection_id}", response_model=ConnectionOut)
async def update_connection(connection_id: str, body: ConnectionUpdate,
                            _admin: User = Depends(require_admin)):
    items = _list_items()
    item = next((i for i in items if i.get("id") == connection_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")
    if item.get("is_local"):
        # Yerel default yalnızca is_default/abled güncellenebilir.
        if body.name is not None or body.base_url is not None or body.api_key is not None or body.notes is not None:
            raise HTTPException(status_code=403, detail="Yerel varsayılan bağlantısı düzenlenemez")

    if body.name is not None:
        item["name"] = body.name.strip()
    if body.base_url is not None:
        item["base_url"] = body.base_url
    if body.api_key is not None:
        item["api_key"] = body.api_key.strip() if body.api_key else None
    if body.enabled is not None:
        item["enabled"] = bool(body.enabled)
    if body.notes is not None:
        item["notes"] = body.notes
    if body.is_default is True:
        for i in items:
            if i.get("id") != connection_id and not i.get("is_local"):
                i["is_default"] = False
        item["is_default"] = True
    elif body.is_default is False and not item.get("is_local"):
        item["is_default"] = False

    _persist(items)
    return _to_out(item)


@router.delete("/connections/{connection_id}")
async def delete_connection(connection_id: str, _admin: User = Depends(require_admin)):
    items = _list_items()
    item = next((i for i in items if i.get("id") == connection_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")
    if item.get("is_local"):
        raise HTTPException(status_code=403, detail="Yerel varsayılan bağlantısı silinemez")
    items = [i for i in items if i.get("id") != connection_id]
    _persist(items)
    return {"deleted": True}


@router.post("/connections/{connection_id}/test")
async def test_connection(connection_id: str, _admin: User = Depends(require_admin)):
    """Bağlantıyı test et ve model listesini önbelleğe al."""
    item = _get_item(connection_id)
    if not item:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")
    ok, models, err = await _test_connection(item)
    if ok:
        item["last_seen_ok"] = datetime.now(timezone.utc).isoformat()
        item["models"] = models
        items = _list_items()
        for idx, i in enumerate(items):
            if i.get("id") == connection_id:
                items[idx] = item
                break
        _persist(items)
        return {"ok": True, "models": models, "count": len(models)}
    return {"ok": False, "error": err, "models": [], "count": 0}


@router.get("/connections/{connection_id}/models")
async def connection_models(connection_id: str, _user: User = Depends(current_user)):
    """Verilen bağlantıdaki mevcut modelleri canlı olarak listele."""
    item = _get_item(connection_id)
    if not item:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")
    if not item.get("enabled", True):
        raise HTTPException(status_code=400, detail="Bağlantı devre dışı")
    ok, models, err = await _test_connection(item)
    if not ok:
        raise HTTPException(status_code=502, detail=err or "Bağlantı hatası")
    return {"models": models}


@router.post("/connections/{connection_id}/proxy/{path:path}")
async def proxy_to_connection(connection_id: str, path: str,
                              _admin: User = Depends(require_admin)):
    raise HTTPException(status_code=410, detail="Kullanımdan kaldırıldı — MCP relay araçlarını kullanın.")
