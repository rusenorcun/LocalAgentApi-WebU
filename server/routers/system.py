"""API v2 — Sistem izleci: kaynak kullanımı ve performans metrikleri.

Ayarlar > Sistem sekmesindeki canlı izleç kartının veri kaynağı.
Yönetim eylemi içermediği için (salt-okunur metrikler) giriş yapmış tüm
kullanıcılara açıktır; model yükleme/boşaltma yine admin uçlarındadır.
"""
from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Depends

from .. import config
from ..auth_v2 import current_user
from ..database import User
from ..services.system_stats import collect
from .models import SystemStats

router = APIRouter(prefix="/api/v2/system", tags=["system"])


@router.get("/stats", response_model=SystemStats)
async def system_stats(user: User = Depends(current_user)):
    """Canlı izleç verisi: CPU / bellek / disk / süreç / çalışma süresi + çalışan model."""
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
