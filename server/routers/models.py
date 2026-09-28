"""API v2 — Model kataloğu: listeleme (kullanıcı) + yönetim (admin)."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import chat, config
from ..auth_v2 import current_user, require_admin
from ..database import ModelCatalog, User, get_session
from ..services.text_utils import sse as _sse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/models", tags=["models"])


# ── Şemalar ───────────────────────────────────────────────────────────────────

class ModelUpdate(BaseModel):
    name_tr: str | None = Field(default=None, max_length=60)
    name_en: str | None = Field(default=None, max_length=60)
    desc_tr: str | None = Field(default=None, max_length=300)
    desc_en: str | None = Field(default=None, max_length=300)
    strengths: list[str] | None = None
    speed: int | None = Field(default=None, ge=1, le=5)
    enabled: bool | None = None
    is_default: bool | None = None
    internal: bool | None = None
    is_vision: bool | None = None
    # Model bazlı üretim ayarları: 0 gönderilirse temizlenir (global'e döner).
    # Manuel değer verilirse tune_auto otomatik kapanır.
    num_ctx: int | None = Field(default=None, ge=0, le=131072)
    num_gpu: int | None = Field(default=None, ge=0, le=256)
    tune_auto: bool | None = None


class ModelCreate(BaseModel):
    ollama_name: str = Field(min_length=1, max_length=120)
    name_tr: str = Field(default="", max_length=60)
    name_en: str = Field(default="", max_length=60)
    desc_tr: str = Field(default="", max_length=300)
    desc_en: str = Field(default="", max_length=300)
    strengths: list[str] = Field(default_factory=list)
    speed: int = Field(default=3, ge=1, le=5)
    enabled: bool = True
    internal: bool = False
    is_vision: bool = False
    is_default: bool = False


# ── Yardımcı ─────────────────────────────────────────────────────────────────

def _model_dict(m: ModelCatalog, lang: str = "tr", admin: bool = False) -> dict:
    name_i18n = json.loads(m.name_i18n_json or "{}")
    desc_i18n = json.loads(m.desc_i18n_json or "{}")
    strengths = json.loads(m.strengths_json or "[]")
    d = {
        "id": m.id,
        "display_name": name_i18n.get(lang) or name_i18n.get("tr") or m.ollama_name,
        "description": desc_i18n.get(lang) or desc_i18n.get("tr") or "",
        "strengths": strengths,
        "speed": m.speed,
        "is_default": m.is_default,
        "is_vision": m.is_vision,
        "enabled": m.enabled,
        # Seçim anahtarı olarak gerekli: chat.model bu ham adla saklanır,
        # UI eşleştirme ve model değiştirme bunsuz çalışamaz.
        "ollama_name": m.ollama_name,
    }
    if admin:
        d["internal"] = m.internal
        d["name_i18n"] = name_i18n
        d["desc_i18n"] = desc_i18n
        d["num_ctx"] = m.num_ctx
        d["num_gpu"] = m.num_gpu
        d["tune_auto"] = m.tune_auto
    return d


# ── Kullanıcı uçları ─────────────────────────────────────────────────────────

@router.get("")
async def list_models(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
    include_internal: bool = False,
):
    """Kullanıcıya gösterilen model listesi.
    Varsayılan: enabled=True, internal=False. include_internal=True ise dahili
    modeller de eklenir (caption/görsel seçici için — örn. Görü Mini)."""
    lang = user.lang_pref or "tr"
    conds = [ModelCatalog.enabled == True]  # noqa: E712
    if not include_internal:
        conds.append(ModelCatalog.internal == False)  # noqa: E712
    result = await db.execute(
        select(ModelCatalog)
        .where(*conds)
        .order_by(ModelCatalog.is_default.desc(), ModelCatalog.id)
    )
    catalog = result.scalars().all()

    # Katalogda yoksa Ollama'dan gelen ham modeller (adlandırılmamış olarak)
    if not catalog:
        ollama_models = await chat.list_models()
        return {
            "models": [{"id": None, "display_name": m["name"], "ollama_name": m["name"],
                        "description": "", "strengths": [], "speed": 3,
                        "is_default": m["name"] == config.MODEL_NAME, "enabled": True}
                       for m in ollama_models],
            "default": config.MODEL_NAME,
        }

    default_model = next((m.ollama_name for m in catalog if m.is_default), config.MODEL_NAME)
    return {
        "models": [_model_dict(m, lang) for m in catalog],
        "default": default_model,
    }


# ── Admin uçları ─────────────────────────────────────────────────────────────

@router.get("/admin")
async def admin_list_models(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Admin: tüm modeller (internal dahil) + Ollama keşif listesi."""
    result = await db.execute(select(ModelCatalog).order_by(ModelCatalog.id))
    catalog = result.scalars().all()

    # Ollama'daki mevcut modeller
    ollama_raw = await chat.list_models()
    ollama_names = {m["name"] for m in ollama_raw}
    catalog_names = {m.ollama_name for m in catalog}

    # Sistem tarafindan referanslanan YARDIMCI modeller (ozetleme, caption,
    # coder, embedding...). Katalogda yoklar ama SILINIRSE ozellikler bozulur
    # — panelde ayrica isaretlenir.
    helper_names = {n for n in (
        config.MODEL_NAME, config.SUMMARY_MODEL, config.CODER_MODEL,
        config.CAPTION_MODEL, config.EMBED_MODEL,
    ) if n}
    _sizes = {m["name"]: m.get("size", 0) for m in ollama_raw}

    unnamed = [
        {
            "ollama_name": n,
            "display_name": None,
            "size": _sizes.get(n, 0),
            # Sistem yardimcisi mi? (silinirse ozellik bozulur)
            "helper": n in helper_names,
            # Kullanici sohbetlerinde secilebilir mi? (katalogda yok = hayir)
            "unused": n not in helper_names,
        }
        for n in sorted(ollama_names - catalog_names)
    ]

    return {
        "catalog": [_model_dict(m, "tr", admin=True) for m in catalog],
        "unnamed_ollama_models": unnamed,
    }


@router.post("/admin")
async def admin_create_model(
    body: ModelCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    existing = await db.execute(
        select(ModelCatalog).where(ModelCatalog.ollama_name == body.ollama_name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Model zaten katalogda")

    if body.is_default:
        from sqlalchemy import update as sqla_update
        await db.execute(sqla_update(ModelCatalog).values(is_default=False))
        from .. import settings
        settings.update({"MODEL_NAME": body.ollama_name})

    m = ModelCatalog(
        ollama_name=body.ollama_name,
        name_i18n_json=json.dumps({"tr": body.name_tr, "en": body.name_en}),
        desc_i18n_json=json.dumps({"tr": body.desc_tr, "en": body.desc_en}),
        strengths_json=json.dumps(body.strengths),
        speed=body.speed,
        is_vision=body.is_vision,
        enabled=body.enabled,
        internal=body.internal,
        is_default=body.is_default,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _model_dict(m, "tr", admin=True)


@router.patch("/admin/{model_id}")
async def admin_update_model(
    model_id: int,
    body: ModelUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(ModelCatalog).where(ModelCatalog.id == model_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Model bulunamadı")

    name_i18n = json.loads(m.name_i18n_json or "{}")
    desc_i18n = json.loads(m.desc_i18n_json or "{}")

    if body.name_tr is not None:
        name_i18n["tr"] = body.name_tr
    if body.name_en is not None:
        name_i18n["en"] = body.name_en
    if body.desc_tr is not None:
        desc_i18n["tr"] = body.desc_tr
    if body.desc_en is not None:
        desc_i18n["en"] = body.desc_en

    m.name_i18n_json = json.dumps(name_i18n)
    m.desc_i18n_json = json.dumps(desc_i18n)

    if body.strengths is not None:
        m.strengths_json = json.dumps(body.strengths)
    if body.speed is not None:
        m.speed = body.speed
    if body.enabled is not None:
        m.enabled = body.enabled
    if body.internal is not None:
        m.internal = body.internal
    if body.is_vision is not None:
        m.is_vision = body.is_vision

    # Model bazlı üretim ayarları (0 = temizle → global config'e dön)
    if body.num_ctx is not None:
        m.num_ctx = body.num_ctx or None
        m.tune_auto = False  # manuel müdahale — otomatik hesap dokunmasın
    if body.num_gpu is not None:
        m.num_gpu = body.num_gpu or None
        m.tune_auto = False
    if body.tune_auto is not None:
        m.tune_auto = body.tune_auto

    # Varsayılan değişikliği: diğerlerini sıfırla ve settings'e kaydet
    if body.is_default is True:
        from sqlalchemy import update as sqla_update
        await db.execute(
            sqla_update(ModelCatalog).values(is_default=False)
        )
        m.is_default = True
        from .. import settings
        settings.update({"MODEL_NAME": m.ollama_name})
    elif body.is_default is False and m.is_default:
        m.is_default = False

    await db.commit()
    return _model_dict(m, "tr", admin=True)


@router.delete("/admin/{model_id}")
async def admin_delete_model(
    model_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(ModelCatalog).where(ModelCatalog.id == model_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Model bulunamadı")
    was_default = m.is_default
    await db.delete(m)
    await db.commit()
    if was_default:
        next_default = (await db.execute(
            select(ModelCatalog).where(ModelCatalog.enabled == True).order_by(ModelCatalog.id)
        )).scalars().first()
        if next_default:
            next_default.is_default = True
            await db.commit()
            from .. import settings
            settings.update({"MODEL_NAME": next_default.ollama_name})
    return {"deleted": True}



@router.post("/admin/retune")
async def admin_retune(admin: User = Depends(require_admin)):
    """Otomatik moddaki (tune_auto=True) modellerin katalog override'larını
    temizler: bağlam global ayardan gelir, GPU dağılımını Ollama yapar.
    Manuel ayarlanmış modellere dokunulmaz (bkz. services/model_tuner.py)."""
    from ..services.model_tuner import auto_tune_models
    cleared = await auto_tune_models()
    return {"retuned": True, "cleared": cleared}


# ── Ollama sistem yönetimi (admin) ────────────────────────────────────────────

@router.get("/admin/status")
async def admin_ollama_status(admin: User = Depends(require_admin)):
    """Çalışan (VRAM'de yüklü) + diskte yüklü modeller — sağlık/VRAM paneli için."""
    running = await chat.running_models()
    installed = await chat.list_models()  # [{name, size}]
    return {"running": running, "installed": installed}


@router.post("/admin/uninstall")
async def admin_uninstall(name: str = Body(..., embed=True), admin: User = Depends(require_admin)):
    """Modeli Ollama'dan (diskten) kaldır. NOT: /admin/{id} (int) ile çakışmasın diye POST."""
    if not await chat.delete_model(name):
        raise HTTPException(status_code=502, detail="Model silinemedi (Ollama erişilemiyor olabilir)")
    return {"deleted": True}


@router.post("/admin/pull")
async def admin_pull(name: str = Body(..., embed=True), admin: User = Depends(require_admin)):
    """Modeli indir — ilerleme SSE ile akar."""
    async def gen():
        try:
            async for ev in chat.pull_model_stream(name):
                yield _sse(ev)
            # İndirme bitti — otomatik moddaki modellerde override kalmasın
            try:
                from ..services.model_tuner import auto_tune_models
                await auto_tune_models()
            except Exception:
                pass
        except chat.OllamaError as e:
            yield _sse({"status": "error", "error": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Sistem monitörü ve model yönetimi ───────────────────────────────────────────

class SystemStats(BaseModel):
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    active_processes: int
    running_model: str | None = None
    # İzleç ek alanları (services/system_stats.collect)
    cpu_count: int | None = None
    memory_used_gb: float | None = None
    memory_total_gb: float | None = None
    disk_used_gb: float | None = None
    disk_total_gb: float | None = None
    uptime_seconds: int | None = None
    load_avg: list[float] | None = None
    platform: str | None = None


class SystemUnloadRequest(BaseModel):
    model: str


class SystemReloadRequest(BaseModel):
    model: str


class SystemActionResponse(BaseModel):
    ok: bool
    note: str | None = None


@router.get("/admin/system/stats", response_model=SystemStats)
async def admin_system_stats(admin: User = Depends(require_admin)):
    """Sistem kaynak kullanım istatistikleri (CPU, Memory, Disk)."""
    import asyncio
    import httpx

    from ..services.system_stats import collect

    # Metrikleri thread havuzunda topla (psutil/proc okumaları senkron)
    data = await asyncio.to_thread(collect)

    # Çalışan model (Ollama üzerinden kontrol)
    running_model = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{config.OLLAMA_HOST}/api/ps")
            if r.status_code == 200:
                running_models = r.json().get("models", [])
                running_model = running_models[0].get("name") if running_models else None
    except Exception:
        pass

    return {**data, "running_model": running_model}


@router.get("/admin/system/models")
async def admin_system_models(admin: User = Depends(require_admin)):
    """Ollama yüklü modeller ve VRAM kullanım durumları."""
    try:
        installed = await chat.list_models()
    except Exception:
        installed = []

    try:
        running = await chat.running_models()
    except Exception:
        running = []

    running_map = {}
    for r in running:
        name = r.get("name")
        if name:
            running_map[name] = r
            if ":" in name:
                running_map[name.split(":")[0]] = r
            else:
                running_map[f"{name}:latest"] = r

    vram_total_mb = 0
    try:
        from ..services.model_tuner import detect_vram_mb
        vram_total_mb = detect_vram_mb() or 0
    except Exception:
        pass
    vram_total_bytes = int(vram_total_mb * 1024 * 1024)

    out = []
    for m in installed:
        name = m.get("name", "")
        run_info = running_map.get(name) or running_map.get(f"{name}:latest") or running_map.get(name.split(":")[0])
        vram_used = run_info.get("size_vram", 0) if run_info else 0
        out.append({
            "name": name,
            "size": m.get("size", 0),
            "vram_used": vram_used,
            "vram_total": vram_total_bytes,
            "is_loading": False,
        })
    return out


@router.post("/admin/system/unload", response_model=SystemActionResponse)
async def admin_system_unload(body: SystemUnloadRequest, admin: User = Depends(require_admin)):
    """Modeli bellekten boşalt (keep_alive=0) ve /api/ps'ten düşmesini bekle."""
    import asyncio
    import httpx
    from ..services import model_gate
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await model_gate._unload(client, body.model)
            # Ollama boşaltmayı arka planda yapar; panel yenilendiğinde model
            # hâlâ listede görünmesin diye düşene kadar kısa süre bekle.
            target = model_gate._norm(body.model)
            for _ in range(20):
                loaded = await model_gate._loaded_models(client)
                if loaded is None or target not in {model_gate._norm(n) for n in loaded}:
                    return {"ok": True}
                await asyncio.sleep(0.5)
        busy = model_gate._norm(body.model) in model_gate.stats()["api_models"]
        return {"ok": False, "note": "Model şu an bir istek tarafından kullanılıyor; istek bitince boşalacak."
                if busy else "Model 10 sn içinde bellekten düşmedi; biraz sonra tekrar deneyin."}
    except Exception as e:
        log.warning("Model boşaltılamadı: %s - %s", body.model, e)
        return {"ok": False, "note": str(e)}


class BenchmarkRequest(BaseModel):
    model: str = Field(min_length=1)
    num_predict: int = Field(default=256, ge=32, le=2048)
    unload_after: bool = True


_BENCH_PROMPT = (
    "Explain step by step how a hash map works internally: hashing, buckets, "
    "collision handling (chaining vs open addressing), load factor and resizing. "
    "Then write a minimal Python implementation with get/put/delete."
)


@router.post("/admin/benchmark")
async def admin_benchmark(body: BenchmarkRequest, admin: User = Depends(require_admin),
                          db: AsyncSession = Depends(get_session)):
    """Modelin gerçek token/s hızını ölç (Ollama'nın kendi sayaçlarıyla).

    Sohbetteki gerçek ayarlar kullanılır (katalog num_ctx/num_gpu, yoksa NUM_CTX).
    Büyük model sırasına (model_gate) girer; bittiğinde istenirse model boşaltılır.
    """
    import time
    import httpx
    from ..services import model_gate
    from ..services.model_tuner import model_overrides

    host = config.OLLAMA_HOST
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, read=900.0)) as client:
        # Embedding modelleri metin üretemez — atla.
        try:
            r = await client.post(f"{host}/api/show", json={"model": body.model})
            caps = (r.json().get("capabilities") or []) if r.status_code == 200 else []
        except Exception:
            caps = []
        if caps and "completion" not in caps:
            return {"model": body.model, "ok": False, "skipped": True,
                    "note": "Metin üretmeyen model (embedding) — test edilmedi."}

        ctx, gpu = await model_overrides(db, body.model)
        options = {"num_ctx": ctx or config.NUM_CTX, "num_predict": body.num_predict,
                   "temperature": 0, "seed": 42}
        if gpu:
            options["num_gpu"] = gpu
        payload = {"model": body.model, "stream": False, "options": options,
                   "keep_alive": "5m",
                   "messages": [{"role": "user", "content": _BENCH_PROMPT}]}

        async with model_gate.internal(body.model):
            t0 = time.perf_counter()
            try:
                r = await client.post(f"{host}/api/chat", json=payload)
            except httpx.TimeoutException:
                return {"model": body.model, "ok": False, "note": "Zaman aşımı (15 dk)."}
            wall = time.perf_counter() - t0
            if r.status_code != 200:
                return {"model": body.model, "ok": False,
                        "note": f"Ollama hatası {r.status_code}: {r.text[:200]}"}
            d = r.json()
            # Yükleme sonrası GPU/CPU dağılımı (keep_alive=0 olsa da yanıt anında listede)
            size = size_vram = 0
            try:
                ps = (await client.get(f"{host}/api/ps")).json().get("models", [])
                row = next((m for m in ps if model_gate._norm(m.get("name")) == model_gate._norm(body.model)), None)
                if row:
                    size, size_vram = row.get("size", 0), row.get("size_vram", 0)
            except Exception:
                pass
            if body.unload_after:
                await model_gate._unload(client, body.model)

    ns = 1e9
    ev_n, ev_d = d.get("eval_count", 0), d.get("eval_duration", 0)
    pe_n, pe_d = d.get("prompt_eval_count", 0), d.get("prompt_eval_duration", 0)
    return {
        "model": body.model,
        "ok": True,
        "gen_tps": round(ev_n / (ev_d / ns), 1) if ev_d else None,        # üretim hızı
        "prompt_tps": round(pe_n / (pe_d / ns), 1) if pe_d else None,     # prompt işleme hızı
        "eval_count": ev_n,
        "prompt_eval_count": pe_n,
        "load_s": round(d.get("load_duration", 0) / ns, 2),
        "total_s": round(wall, 2),
        "num_ctx": options["num_ctx"],
        "num_gpu": options.get("num_gpu"),
        "gpu_pct": round(size_vram / size * 100) if size else None,
    }


@router.post("/admin/system/reload", response_model=SystemActionResponse)
async def admin_system_reload(body: SystemReloadRequest, admin: User = Depends(require_admin)):
    """Modeli yeniden yükle / belleğe getir."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Modelin varlığını kontrol et
            r = await client.get(f"{config.OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                models = [m.get("name") for m in r.json().get("models", []) if m.get("name")]
                if body.model not in models and f"{body.model}:latest" not in models:
                    return {"ok": False, "note": "Model bulunamadı"}
            # Modeli yuklemeye çalış (keep_alive ile)
            r = await client.post(
                f"{config.OLLAMA_HOST}/api/generate",
                json={"model": body.model, "keep_alive": "2m"}
            )
            return {"ok": r.status_code == 200}
    except Exception as e:
        log.warning("Model yeniden yükleme hatası: %s - %s", body.model, e)
        return {"ok": False, "note": str(e)}
