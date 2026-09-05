"""Model başına otomatik üretim ayarı (num_ctx / num_gpu).

Her katalog modeli için Ollama'dan boyut + mimari bilgisi alınır ve GPU
VRAM'iyle karşılaştırılır:

  1. Model + KV cache VRAM'e sığıyorsa      → override YOK (None; Ollama otomatiği)
  2. Ağırlıklar sığıyor, KV sığmıyorsa       → num_ctx düşürülür (16k → 8k → 4k)
  3. Ağırlıklar tek başına sığmıyorsa        → num_ctx=8192 + GPU'ya sığan katman
     sayısı (num_gpu) hesaplanır → sürücünün "paylaşılan GPU belleği" taşması
     yerine TEMİZ CPU offload (çok daha hızlı).

Sonuçlar `models` tablosuna yazılır (yalnız tune_auto=True satırlar). Admin
PATCH ile manuel değer verirse tune_auto=False olur ve bir daha dokunulmaz.

VRAM tespiti: GPU_VRAM_MB env > nvidia-smi > (bulunamazsa tuning atlanır).
"""
from __future__ import annotations

import logging
import shutil
import subprocess

import httpx
from sqlalchemy import select

from .. import config
from ..database import ModelCatalog, async_session_maker

log = logging.getLogger(__name__)

_RUNNER_OVERHEAD_GB = 1.2   # Ollama runner + ara tamponlar + vision projektörü payı
_VRAM_SAFETY = 0.92         # VRAM'in tamamını hedefleme (sürücü/kompozitör payı)
_CTX_CANDIDATES = (16384, 8192, 4096)


def detect_vram_mb() -> int:
    """Toplam GPU VRAM (MB). Önce env, sonra nvidia-smi; bulunamazsa 0."""
    if getattr(config, "GPU_VRAM_MB", 0) > 0:
        return config.GPU_VRAM_MB
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            out = subprocess.run(
                [exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            vals = [int(x.strip()) for x in out.stdout.splitlines() if x.strip().isdigit()]
            if vals:
                return max(vals)
        except Exception:
            pass
    return 0


def _find(info: dict, suffix: str):
    """model_info anahtarları '<arch>.block_count' biçimindedir — sonekle bul."""
    for k, v in info.items():
        if k.endswith(suffix):
            return v
    return None


def _kv_gb(info: dict, n_ctx: int) -> float:
    """KV cache tahmini (GB), f16 varsayımıyla (q8_0 açıksa gerçek ~yarısı —
    güvenli tarafta kalınır)."""
    block = _find(info, ".block_count")
    emb = _find(info, ".embedding_length")
    heads = _find(info, ".attention.head_count")
    kv_heads = _find(info, ".attention.head_count_kv") or heads
    if not (block and emb and heads):
        return 2.0 * (n_ctx / 16384)  # mimari bilinmiyorsa kaba tahmin
    head_dim = emb / heads
    return (2 * block * n_ctx * head_dim * kv_heads * 2) / 1e9  # K+V, 2 bayt


async def auto_tune_models() -> None:
    """Katalogdaki tune_auto modeller için num_ctx/num_gpu hesapla ve kaydet."""
    vram_mb = detect_vram_mb()
    if vram_mb <= 0:
        log.info("VRAM belirlenemedi (GPU_VRAM_MB env verin) — model tuning atlandı")
        return
    usable_gb = (vram_mb / 1024.0) * _VRAM_SAFETY - _RUNNER_OVERHEAD_GB
    if usable_gb <= 1.0:
        return

    # Diskteki model boyutları
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{config.OLLAMA_HOST}/api/tags")
            r.raise_for_status()
            sizes = {m["name"]: m.get("size", 0) for m in r.json().get("models", [])}
    except Exception:
        return  # Ollama kapalı — mevcut değerlere dokunma

    async with async_session_maker() as db:
        rows = (await db.execute(select(ModelCatalog))).scalars().all()
        async with httpx.AsyncClient(timeout=8.0) as client:
            for m in rows:
                if not m.tune_auto:
                    continue  # admin manuel ayarlamış — dokunma
                size = sizes.get(m.ollama_name)
                if not size:
                    continue  # diskte yok
                # Ağırlıkların bellek maliyeti ≈ dosya boyutu (+%5 tampon)
                size_gb = (size / 1e9) * 1.05

                info: dict = {}
                try:
                    rr = await client.post(f"{config.OLLAMA_HOST}/api/show",
                                           json={"model": m.ollama_name, "name": m.ollama_name})
                    if rr.status_code == 200:
                        info = rr.json().get("model_info") or {}
                except Exception:
                    info = {}

                new_ctx: int | None = None
                new_gpu: int | None = None
                base_ctx = config.NUM_CTX

                if size_gb + _kv_gb(info, base_ctx) <= usable_gb:
                    # 1) Tamamen sığıyor — override gereksiz, Ollama otomatiği en iyisi
                    pass
                elif size_gb <= usable_gb:
                    # 2) Ağırlıklar sığıyor, KV sığmıyor — bağlamı küçült
                    for cand in _CTX_CANDIDATES:
                        if cand < base_ctx and size_gb + _kv_gb(info, cand) <= usable_gb:
                            new_ctx = cand
                            break
                    if new_ctx is None:
                        new_ctx = _CTX_CANDIDATES[-1]
                else:
                    # 3) Ağırlıklar sığmıyor — küçük bağlam + temiz katman offload'u
                    new_ctx = min(base_ctx, 8192)
                    block = _find(info, ".block_count")
                    if block:
                        frac = (usable_gb - _kv_gb(info, new_ctx)) / size_gb
                        frac = max(0.05, min(1.0, frac))
                        new_gpu = max(1, min(int(block), int(block * frac)))

                if (m.num_ctx, m.num_gpu) != (new_ctx, new_gpu):
                    m.num_ctx = new_ctx
                    m.num_gpu = new_gpu
                    log.info("Model auto-tune: %s → num_ctx=%s num_gpu=%s "
                             "(boyut=%.1fGB, kullanılabilir VRAM=%.1fGB)",
                             m.ollama_name, new_ctx, new_gpu, size_gb, usable_gb)
        await db.commit()


async def model_overrides(db, model_name: str) -> tuple[int | None, int | None]:
    """Bir modelin katalogdaki (num_ctx, num_gpu) override'ları; yoksa (None, None)."""
    try:
        row = (await db.execute(
            select(ModelCatalog.num_ctx, ModelCatalog.num_gpu)
            .where(ModelCatalog.ollama_name == model_name)
        )).first()
        if row:
            return row[0], row[1]
    except Exception:
        pass
    return None, None
