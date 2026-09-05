"""Aktif üretimlerin canlı anlık görüntüsü (sohbet bazlı kayıt defteri).

Arka plan görevi (background_task) her SSE olayini buraya AYNALAR; boylece
kullanici uretim surerken sohbetten cikip geri dondugunde devam eden islemin
o anki durumu (durum mesaji + kismi metin/dusunme + arac etkinlikleri)
sorgulanabilir. Uretim bitince kayit "finished" isaretlenir, kisa bir TTL
sonra temizlenir (okuyucunun son durumu gormesi icin hemen silinmez).

NOT: Tum yazimlar tek asyncio dongusu icinde gerceklesir (FastAPI/uvicorn),
bu yuzden kilit gerektirmez; fonksiyonlar await icermeyen duz islemlerdir.
"""
from __future__ import annotations

import time
from typing import Any, Optional

# chat_id -> durum dict'i
_STATES: dict[str, dict[str, Any]] = {}

# Bitmis kaydin okuyucular tarafindan gorulebilmesi icin tutulma suresi (sn)
_FINISHED_TTL = 300.0


def begin(chat_id: str) -> None:
    """Yeni uretim turu basladi — eski kaydi ez."""
    _STATES[chat_id] = {
        "started": time.time(),
        "finished_at": None,
        "status": None,          # {"status": "...", "message": "..."}
        "queued": None,          # kuyruk sirasi (varsa)
        "text_parts": [],        # akan yanit parcalari
        "thinking_parts": [],    # dusunme parcalari
        "tools": [],             # calistirilan arac adlari (sirali)
        "sources": [],           # web/RAG kaynaklari
        "finished": False,
        "error": None,
    }


def push(chat_id: str, ev: dict) -> None:
    """Bir SSE olayini duruma isler (background_task'tan aynalanir)."""
    st = _STATES.get(chat_id)
    if st is None or st["finished"]:
        return
    t = ev.get("type")

    if t == "status":
        st["status"] = {"status": ev.get("status"), "message": ev.get("message")}
    elif t == "queue":
        st["queued"] = ev.get("position")
        st["status"] = {"status": "queue",
                        "message": f"Kuyrukta bekliyor (sıra {ev.get('position')})"}
    elif t == "thinking_delta":
        txt = ev.get("text") or ""
        if txt:
            st["thinking_parts"].append(txt)
            st["status"] = None
    elif t == "delta":
        txt = ev.get("text") or ""
        if txt:
            st["text_parts"].append(txt)
            st["status"] = None
    elif t == "tool":
        name = ev.get("name") or "arac"
        # Ayni aracin ardardik tekrarlarini ekleme
        if not st["tools"] or st["tools"][-1] != name:
            st["tools"].append(name)
    elif t == "sources":
        items = ev.get("items") or []
        if items:
            st["sources"].extend(items)
    elif t == "done":
        st["finished"] = True
        st["finished_at"] = time.time()
        st["status"] = None
    elif t == "error":
        st["error"] = ev.get("message") or "Hata"
        st["finished"] = True
        st["finished_at"] = time.time()
        st["status"] = None


def finish(chat_id: str) -> None:
    """Uretim gorevi sonlandi (herhangi bir yoldan) — okunur isaretle."""
    st = _STATES.get(chat_id)
    if st is not None and not st["finished"]:
        st["finished"] = True
        st["finished_at"] = time.time()
        st["status"] = None


def snapshot(chat_id: str) -> dict:
    """Canlı durumu dondurur. Aktif uretim yoksa {"active": False}."""
    st = _STATES.get(chat_id)

    # Bayatlamis bitmis kayitlari temizle
    now = time.time()
    for cid in [c for c, s in _STATES.items()
                if s["finished"] and s["finished_at"]
                and now - s["finished_at"] > _FINISHED_TTL]:
        _STATES.pop(cid, None)
        if cid == chat_id:
            st = None

    if st is None:
        return {"active": False, "finished": False}

    return {
        "active": not st["finished"],
        "finished": st["finished"],
        "error": st["error"],
        "elapsed": int(now - st["started"]),
        "queued": st["queued"],
        "status": st["status"],
        "text": "".join(st["text_parts"]),
        "thinking": "".join(st["thinking_parts"]),
        "tools": list(st["tools"]),
        "sources_count": len(st["sources"]),
    }


def active_chat_ids() -> list[str]:
    """Su an uretimde olan sohbetler (izleme/tehis icin)."""
    return [c for c, s in _STATES.items() if not s["finished"]]
