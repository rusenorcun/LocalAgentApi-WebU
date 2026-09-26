"""Buyuk model sirasi (tek GPU + sistem RAM'i tasmasin).

Kurallar (dahili cagrilar: web uretimi, coder delegesi, ozet, gorsel, embedding):
  * KUCUK modeller (boyut < BIG_MODEL_MIN_GB; orn. bge-m3, 7B yardimcilar)
    eskisi gibi calisir: sira beklemez, bosaltilmaz, keep_alive korunur.
  * BUYUK modeller birbirini bekler: ayni anda tek buyuk model islemi calisir.
    Farkli bir buyuk model gerekiyorsa bellekteki BOSTAKI diger buyuk modeller
    bosaltilir (keep_alive=0) ve /api/ps'ten dustukleri gorulene kadar beklenir.
    Ayni model art arda kullaniliyorsa bosaltma yapilmaz (sicak kalir).
  * Yardimci (companion) cagri — orn. plan->code delegesinde coder: cagiran
    orkestrator model bellekte KALIR, coder yanina yuklenir ve is biter bitmez
    (SUB_MODEL_KEEP_ALIVE, vars. 0) bellekten cikar.

Istisna — API baglantisi (/v1 OpenAI uyumlu uclar, Ollama proxy, MCP relay):
orkestrator/agentic istemciler ayni anda farkli model cagirabilsin diye sirayi
BEKLEMEZ. Karsiliginda keep_alive en fazla config.API_KEEP_ALIVE (vars. 2m)
olur. Aktif bir API isteginin kullandigi model dahili taraftan bosaltilmaz.
"""
import asyncio
import logging
import re
import time
from collections import Counter
from contextlib import asynccontextmanager

import httpx

from .. import config

log = logging.getLogger(__name__)

_lock = asyncio.Lock()               # yalniz buyuk model islemleri
_api_active: Counter = Counter()     # API'de aktif modeller (normalize ad -> istek sayisi)

_sizes: dict[str, int] = {}          # /api/tags boyut onbellegi (normalize ad -> bayt)
_sizes_at = 0.0
_SIZES_TTL = 300.0


def _norm(name: str | None) -> str:
    """Etiketsiz adlari Ollama'nin /api/ps bicimine getirir (bge-m3 -> bge-m3:latest)."""
    name = (name or "").strip()
    if name and ":" not in name.rsplit("/", 1)[-1]:
        name += ":latest"
    return name


# ── API istisnasi ─────────────────────────────────────────────────────────────

class ApiLease:
    """Bir API isteginin model kullanim kaydi. release() tekrar cagrilabilir."""

    __slots__ = ("_key", "_open")

    def __init__(self, model: str | None):
        self._key = _norm(model)
        self._open = bool(self._key)
        if self._open:
            _api_active[self._key] += 1

    def release(self) -> None:
        if not self._open:
            return
        self._open = False
        _api_active[self._key] -= 1
        if _api_active[self._key] <= 0:
            del _api_active[self._key]


@asynccontextmanager
async def api_use(model: str | None):
    lease = ApiLease(model)
    try:
        yield
    finally:
        lease.release()


_DUR_PART = re.compile(r"(-?\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h)")
_DUR_UNIT = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}


def _seconds(value) -> float | None:
    """Ollama keep_alive degerini saniyeye cevirir ("2m", "1h30m", 300, "-1")."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(" ", "")
    try:
        return float(s)
    except ValueError:
        pass
    parts = _DUR_PART.findall(s)
    if not parts or "".join(a + b for a, b in parts) != s:
        return None
    return sum(float(a) * _DUR_UNIT[b] for a, b in parts)


def api_keep_alive(requested=None):
    """API istekleri icin keep_alive: istemci daha KISA istediyse o, degilse tavan.

    Suresiz ("-1"), tavandan uzun veya okunamayan degerler tavana cekilir.
    """
    cap = _seconds(config.API_KEEP_ALIVE)
    req = _seconds(requested)
    if cap is not None and req is not None and 0 <= req <= cap:
        return requested
    return config.API_KEEP_ALIVE


# ── Dahili buyuk model sirasi ─────────────────────────────────────────────────

async def _model_size(client: httpx.AsyncClient, name: str) -> int | None:
    global _sizes_at
    key = _norm(name)
    if key not in _sizes or time.monotonic() - _sizes_at > _SIZES_TTL:
        try:
            r = await client.get(f"{config.OLLAMA_HOST}/api/tags")
            r.raise_for_status()
            fresh = {}
            for m in r.json().get("models", []):
                n = m.get("name") or m.get("model")
                if n:
                    fresh[_norm(n)] = int(m.get("size") or 0)
            _sizes.clear()
            _sizes.update(fresh)
            _sizes_at = time.monotonic()
        except Exception:
            pass
    return _sizes.get(key)


def _is_big(size: int | None) -> bool:
    # Boyutu bilinmeyen model guvenli tarafta kalsin: buyuk say.
    return size is None or size >= config.BIG_MODEL_MIN_GB * 1e9


async def _loaded_models(client: httpx.AsyncClient) -> list[str] | None:
    try:
        r = await client.get(f"{config.OLLAMA_HOST}/api/ps")
        r.raise_for_status()
        return [n for m in r.json().get("models", []) if (n := m.get("name") or m.get("model"))]
    except Exception:
        return None


async def _unload(client: httpx.AsyncClient, name: str) -> None:
    body = {"model": name, "keep_alive": 0}
    try:
        r = await client.post(f"{config.OLLAMA_HOST}/api/generate", json=body)
        if r.status_code != 200:
            # Yalniz-embedding modelleri generate'i reddedebilir
            await client.post(f"{config.OLLAMA_HOST}/api/embed", json={**body, "input": []})
    except Exception:
        log.warning("Model bosaltilamadi: %s", name, exc_info=True)


async def _evict_other_big(client: httpx.AsyncClient, model: str, keep: str | None) -> None:
    spare = {_norm(model), _norm(keep)}
    loaded = await _loaded_models(client)
    if not loaded:
        return
    victims = {}
    for n in loaded:
        k = _norm(n)
        if k in spare or k in _api_active:
            continue
        if _is_big(await _model_size(client, n)):
            victims[k] = n
    if not victims:
        return
    log.info("Buyuk model sirasi: %s oncesi bosaltiliyor: %s", _norm(model), list(victims.values()))
    for name in victims.values():
        await _unload(client, name)

    deadline = time.monotonic() + config.MODEL_UNLOAD_TIMEOUT
    remaining = list(victims.values())
    while time.monotonic() < deadline:
        await asyncio.sleep(0.5)
        loaded = await _loaded_models(client)
        if loaded is None:
            return
        remaining = [n for n in loaded if _norm(n) in victims and _norm(n) not in _api_active]
        if not remaining:
            return
    # Ollama, istegi suren modeli istek bitene kadar bosaltmaz (orn. MCP
    # relay'in dogrudan cagrisi). Sonsuza dek beklemek yerine devam et.
    log.warning("Buyuk model sirasi: %s %.0f sn icinde bosalmadi; devam ediliyor",
                remaining, config.MODEL_UNLOAD_TIMEOUT)


@asynccontextmanager
async def internal(model: str | None, keep: str | None = None):
    """Dahili Ollama islemi. Buyuk modelse sirayi bekler ve bostaki diger buyuk
    modelleri bosaltir; kucuk modelse dogrudan calisir.

    keep: bosaltilmayacak orkestrator model (companion cagrilar icin).
    """
    if not config.SEQUENTIAL_MODEL_LOADING:
        yield
        return
    model = model or config.MODEL_NAME
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            big = _is_big(await _model_size(client, model))
    except Exception:
        big = True
    if not big:
        yield
        return
    async with _lock:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await _evict_other_big(client, model, keep)
        except Exception:
            log.warning("Buyuk model sirasi kontrolu basarisiz", exc_info=True)
        yield


def stats() -> dict:
    return {"busy": _lock.locked(), "api_models": dict(_api_active)}
