"""Canli ayar katmani.

Duzenlenebilir ayarlar data/settings.json'da tutulur ve calisirken `config`
modulune uygulanir (setattr). Boylece tum kod config.X'i okumaya devam eder,
degisiklikler yeniden baslatmadan etki eder.

PORT / JWT_SECRET / OLLAMA_HOST gibi degerler buraya DAHIL DEGIL (restart gerektirir).
"""
import json
import threading

from . import config

_LOCK = threading.Lock()
_FILE = config.DATA_DIR / "settings.json"

# Duzenlenebilir anahtar -> tip
EDITABLE: dict[str, type] = {
    "MODEL_NAME": str,
    "NUM_CTX": int,
    "MAX_CHAT_TOKENS": int,
    "ENABLE_COMPACTION": bool,
    "ENABLE_THINKING": bool,
    "ALLOW_REGISTRATION": bool,
    # Dosya / gorsel
    "IMAGE_TO_TEXT": bool,
    "CAPTION_MODEL": str,
    "ENABLE_IMAGE_ANALYSIS": bool,
    "MAX_IMAGES_PER_FILE": int,
    "IMAGE_MAX_EDGE": int,
    "MIN_IMAGE_EDGE": int,
    "MULTIMODAL_NUM_CTX": int,
    "NUM_GPU": int,
    "NUM_GPU_MULTIMODAL": int,
}


# G7: Sayısal anahtarlar için güvenli aralıklar — admin uçuk bir değer girince
# (örn. NUM_CTX=10 milyon) Ollama runner'ı OOM ile çökertmesin diye clamp edilir.
LIMITS: dict[str, tuple[int, int]] = {
    "NUM_CTX": (1024, 131072),
    "MAX_CHAT_TOKENS": (10_000, 2_000_000),
    "MAX_IMAGES_PER_FILE": (1, 50),
    "IMAGE_MAX_EDGE": (128, 4096),
    "MIN_IMAGE_EDGE": (0, 1024),
    "MULTIMODAL_NUM_CTX": (1024, 65536),
    "NUM_GPU": (0, 256),
    "NUM_GPU_MULTIMODAL": (0, 256),
}


def _coerce(t: type, v, key: str | None = None):
    if t is bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("1", "true", "yes", "on", "evet")
    if t is int:
        iv = int(v)
        if key in LIMITS:
            lo, hi = LIMITS[key]
            iv = max(lo, min(hi, iv))
        return iv
    return str(v)


def init() -> None:
    """Baslangicta settings.json'u config'e uygula."""
    if not _FILE.exists():
        return
    try:
        with open(_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    for k, v in data.items():
        if k in EDITABLE:
            try:
                setattr(config, k, _coerce(EDITABLE[k], v, key=k))
            except Exception:
                pass


def current() -> dict:
    """Su anki duzenlenebilir ayar degerleri."""
    return {k: getattr(config, k) for k in EDITABLE}


def update(changes: dict) -> dict:
    """Ayarlari canli uygula + settings.json'a yaz. Uygulanan degerleri dondurur."""
    applied = {}
    with _LOCK:
        data = {}
        if _FILE.exists():
            try:
                with open(_FILE, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        for k, v in changes.items():
            if k not in EDITABLE:
                continue
            try:
                val = _coerce(EDITABLE[k], v, key=k)
            except (ValueError, TypeError):
                continue
            setattr(config, k, val)
            data[k] = val
            applied[k] = val
        tmp = _FILE.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(_FILE)
    return applied
