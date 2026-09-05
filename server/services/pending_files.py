"""Bekleyen dosya eki el cakistirmasi (upload -> sonraki mesaj).

Yukleme ucu islenen dosyayi buraya "pending" olarak birakir; kullanici
mesaj gonderdiginde send_message bunu alip mesaja iliştirir ve kaydi siler.

ESKI NOT: v1 JSON deposundaki chat dosyasina gomulu handoff yerine gecti.
Kucuk JSON dosyalariyla kalici (restart'a dayanikli) tutulur — tek dosya,
tek yazici; kilitsiz yeterli (ayni sohbete eszamanli upload zaten UI'da yok).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from .. import config

log = logging.getLogger(__name__)


def _path(username: str, chat_id: str) -> Path:
    safe = quote_plus(f"{username}__{chat_id}")
    return Path(config.DATA_DIR) / "pending" / (safe + ".json")


def set(username: str, chat_id: str, attachment: Optional[dict]) -> None:
    """Eki kaydet; attachment=None ise temizle."""
    p = _path(username, chat_id)
    try:
        if attachment is None:
            p.unlink(missing_ok=True)
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(attachment, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)  # atomik yazim — yarim dosya okunmaz
    except Exception:
        log.exception("pending attachment yazilamadi")


def get(username: str, chat_id: str) -> Optional[dict]:
    """Bekleyen eki dondurur (yoksa None). Dosyayi SILMEZ — send_message okur,
    basarili eklemeden sonra clear() ile temizlenir."""
    try:
        p = _path(username, chat_id)
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        log.exception("pending attachment okunamadi")
        return None


def clear(username: str, chat_id: str) -> None:
    set(username, chat_id, None)
