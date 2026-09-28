"""Model başına üretim ayarı (num_ctx / num_gpu) politikası.

Politika: VRAM'e sığmayan modelde BAĞLAMDAN DEĞİL HIZDAN ödün verilir.
Agentic işler (OpenCode, Aider, orkestratör/coder) uzun bağlam ister; bağlamı
küçültmek aracın dosyaları/geçmişi kaybetmesine yol açar. Sığmayan kısım
Ollama tarafından RAM'e/CPU'ya taşınır — yavaşlar ama bağlam korunur.

Bu yüzden otomatik modda (tune_auto=True) katalogda HİÇBİR override tutulmaz:
  * num_ctx → None: global ayar geçerli (sohbette NUM_CTX, /v1'de bağlantının
    num_ctx'i veya API_NUM_CTX).
  * num_gpu → None: GPU katman dağılımını Ollama yapar. Elle sabitlenen katman
    sayısı MoE modellerde uzmanların CPU'ya dağıtımını bozuyor ve gpt-oss:120b'de
    (num_gpu=6) llama-server'ı CUDA hatasıyla çökertiyordu; Ollama'nın kendi
    dağılımı ölçümlerde %25-75 daha hızlı çıktı.

Admin PATCH ile manuel değer verirse tune_auto=False olur ve o değer korunur
(tek bir modele özel bağlam gerekiyorsa panelden verilebilir).
"""
from __future__ import annotations

import logging
import shutil
import subprocess

from sqlalchemy import select

from .. import config
from ..database import ModelCatalog, async_session_maker

log = logging.getLogger(__name__)


def detect_vram_mb() -> int:
    """Toplam GPU VRAM (MB). Önce env, sonra nvidia-smi; bulunamazsa 0.
    (Yalnız sistem izleme ekranında gösterim için.)"""
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


async def auto_tune_models() -> int:
    """tune_auto modellerin katalog override'larını temizler (bkz. modül notu).

    Döndürür: temizlenen model sayısı.
    """
    cleared = 0
    async with async_session_maker() as db:
        rows = (await db.execute(select(ModelCatalog))).scalars().all()
        for m in rows:
            if not m.tune_auto:
                continue  # admin manuel ayarlamış — dokunma
            if m.num_ctx is not None or m.num_gpu is not None:
                log.info("Model auto-tune: %s → num_ctx=%s num_gpu=%s override'ı "
                         "kaldırıldı (global ayar + Ollama otomatiği)",
                         m.ollama_name, m.num_ctx, m.num_gpu)
                m.num_ctx = None
                m.num_gpu = None
                cleared += 1
        await db.commit()
    return cleared


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
