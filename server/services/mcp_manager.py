"""MCP HTTP relay süreç yöneticisi (admin paneli için).

mcp/ollama_mcp.py sunucusunu HTTP modunda ALT SÜREÇ olarak başlatır/durdurur
ve /healthz üzerinden durumunu izler. Tek sorumluluk: süreç yaşam döngüsü.

Notlar:
  * Token: mcp/.mcp_token dosyası mcp_http_baslat.bat ile PAYLAŞILIR — hangi
    yoldan başlatılırsa başlatılsın anahtar aynıdır (istemci config'i bozulmaz).
  * Yönetim kapsamı: yalnızca BU süreçte başlattığımız çocuk yönetilir
    (managed=True). .bat ile elle başlatılan örnek "healthy ama dış" görünür;
    durdurulamaz (penceresini kapatmak gerekir) — bilinçli güvenlik tercihi.
  * Çıktı: data/mcp_server.log dosyasına eklenir (hata teşhisi için).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from .. import config

log = logging.getLogger(__name__)


def _default_ollama_connection_id() -> str | None:
    """data/ollama_connections.json içinden varsayılan uzak bağlantıyı döner."""
    try:
        path = config.DATA_DIR / "ollama_connections.json"
        if not path.is_file():
            return None
        items = json.loads(path.read_text(encoding="utf-8"))
        for item in items:
            if item.get("is_default") and item.get("enabled", True) and not item.get("is_local"):
                return item.get("id")
    except Exception:
        pass
    return None

# Windows'ta arka plan süreci için konsol penceresi açma bayrağı
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_proc: Optional[subprocess.Popen] = None
_log_fh = None
_started_at: Optional[datetime] = None
_lock = asyncio.Lock()


def mask_token(token: str) -> str:
    """UI gösterimi için token'ı maskeler (ilk 6 + son 4 karakter)."""
    if not token:
        return ""
    if len(token) <= 12:
        return token[:2] + "…" + token[-2:]
    return token[:6] + "…" + token[-4:]


def read_or_create_token() -> str:
    """mcp/.mcp_token'ı okur; yoksa üretip yazar (bat ile aynı dosya)."""
    path = Path(config.MCP_TOKEN_FILE)
    if path.is_file():
        tok = path.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tok, encoding="utf-8")
    log.info("MCP token üretildi: %s", path)
    return tok


async def is_healthy(port: Optional[int] = None, timeout: float = 1.5) -> bool:
    """/healthz yanit veriyor mu (token gerekmez)?"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(
                f"http://{config.MCP_HTTP_HOST}:{port or config.MCP_HTTP_PORT}/healthz")
            return r.status_code == 200
    except Exception:
        return False


async def get_status() -> dict:
    """Panel için özet durum. healthy: port ayakta; managed: bizim çocuğumuz."""
    async with _lock:
        alive = _proc is not None and _proc.poll() is None
        healthy = await is_healthy()
        token = ""
        try:
            p = Path(config.MCP_TOKEN_FILE)
            token = p.read_text(encoding="utf-8").strip() if p.is_file() else ""
        except Exception:
            pass
        # Yaşayan ama kaydını tutmadığımız süreç = .bat ile elle başlatılmış
        external = healthy and not alive
        return {
            "running": bool(alive or healthy),
            "healthy": healthy,
            "managed": bool(alive),
            "external": external,
            "pid": _proc.pid if alive else None,
            "started_at": _started_at.isoformat() if (_started_at and alive) else None,
            "host": config.MCP_HTTP_HOST,
            "port": config.MCP_HTTP_PORT,
            "url": f"http://{config.MCP_HTTP_HOST}:{config.MCP_HTTP_PORT}/mcp",
            "token_masked": mask_token(token),
            "token_file": str(config.MCP_TOKEN_FILE),
        }


async def start() -> dict:
    """Relay'i HTTP modunda başlatır. Zaten ayaktaysa dokunmaz."""
    global _proc, _log_fh, _started_at

    async with _lock:
        # Zaten çalışan örnek var mı? (bizim çocuk ya da .bat örneği)
        alive = _proc is not None and _proc.poll() is None
        if alive or await is_healthy():
            return {"ok": True, "already": True,
                    "managed": bool(alive), "pid": _proc.pid if alive else None}

        token = read_or_create_token()

        # Önceki çalıştırmanın log akışını kapat
        if _log_fh is not None:
            try:
                _log_fh.close()
            except Exception:
                pass

        config.MCP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _log_fh = open(config.MCP_LOG_FILE, "ab")

        env = {
            **os.environ,
            "MCP_TRANSPORT": "http",
            # Alt surecin GERCEK dinleme adresi (Docker'da 0.0.0.0 olmali —
            # bkz. config.MCP_BIND_HOST). Panel/healthz her zaman
            # config.MCP_HTTP_HOST (127.0.0.1) uzerinden konusur.
            "MCP_HOST": config.MCP_BIND_HOST,
            "MCP_PORT": str(config.MCP_HTTP_PORT),
            "MCP_TOKEN": token,
            "OLLAMA_HOST": config.OLLAMA_HOST,
            "OLLAMA_PROXY_DOMAIN": config.OLLAMA_PROXY_DOMAIN,
            "OLLAMA_PROXY_PATH": config.OLLAMA_PROXY_PATH,
            "OLLAMA_PROXY_FORCE": "true" if config.OLLAMA_PROXY_FORCE else "false",
            "DATA_DIR": str(config.DATA_DIR),
            "PYTHONIOENCODING": "utf-8",
        }
        conn_id = _default_ollama_connection_id()
        if conn_id:
            env["OLLAMA_CONNECTION_ID"] = conn_id
        cmd = [sys.executable, str(Path(config.MCP_DIR) / "ollama_mcp.py")]
        try:
            _proc = subprocess.Popen(
                cmd, cwd=str(config.BASE_DIR), env=env,
                stdout=_log_fh, stderr=subprocess.STDOUT,
                creationflags=_CREATE_NO_WINDOW,
            )
        except Exception as e:
            log.exception("MCP relay başlatılamadı")
            return {"ok": False, "error": f"Süreç başlatılamadı: {e}"}

        _started_at = datetime.now(timezone.utc)
        log.info("MCP relay başlatıldı pid=%s port=%s", _proc.pid, config.MCP_HTTP_PORT)

        # Sağlık bekleme: uvicorn + SDK kurulumu ~1-3 sn sürer
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            if _proc.poll() is not None:
                tail = ""
                try:
                    _log_fh.flush()
                    tail = Path(config.MCP_LOG_FILE).read_text(
                        encoding="utf-8", errors="replace")[-500:]
                except Exception:
                    pass
                _proc = None
                return {"ok": False, "error": f"Süreç erken kapandı. Log:\n{tail}"}
            if await is_healthy(timeout=0.8):
                return {"ok": True, "already": False,
                        "managed": True, "pid": _proc.pid}
            await asyncio.sleep(0.4)

        return {"ok": True, "already": False, "managed": True, "pid": _proc.pid,
                "warning": "Süreç ayakta ama sağlık yanıtı gecikti"}


async def stop(force: bool = False) -> dict:
    """Bizim başlattığımız çocuğu düzgünce sonlandırır.

    force=True: dış örnek (.bat) olsa bile PID'sini taskkill ile düşürmeye
    çalışır (yalnız aynı makinede ve admin yetkisiyle çağrılır).
    """
    global _proc, _log_fh, _started_at

    async with _lock:
        stopped_pid = None
        if _proc is not None and _proc.poll() is None:
            stopped_pid = _proc.pid
            _proc.terminate()
            try:
                await asyncio.to_thread(_proc.wait, 6)
            except Exception:
                try:
                    _proc.kill()
                except Exception:
                    pass
        elif force:
            # Dış örnek: Windows'ta portu dinleyen PID'i nettle tespit etmek
            # psutil gerektirmez — taskkill'e PID veremeyiz; bunun yerine
            # netstat ile dinleyen PID'i bulmayı deneriz (best-effort).
            pid = await _find_listener_pid(config.MCP_HTTP_PORT)
            if pid:
                stopped_pid = pid
                try:
                    await asyncio.to_thread(
                        subprocess.run,
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True, creationflags=_CREATE_NO_WINDOW)
                except Exception as e:
                    return {"ok": False, "error": f"Dış süreç sonlandırılamadı: {e}"}
            else:
                return {"ok": False,
                        "error": "Çalışan bir MCP relay bulunamadı"}
        else:
            if await is_healthy():
                return {"ok": False,
                        "error": ("Relay .bat ile elle başlatılmış görünüyor; "
                                  "panel 'Zorla Durdur' kullanabilir")}
            return {"ok": True, "stopped": None}

        if _log_fh is not None:
            try:
                _log_fh.close()
            except Exception:
                pass
            _log_fh = None
        _proc = None
        _started_at = None

        # Kapanışı doğrula (kısa bekleme)
        for _ in range(6):
            if not await is_healthy(timeout=0.6):
                break
            await asyncio.sleep(0.3)

        return {"ok": True, "stopped": stopped_pid}


async def _find_listener_pid(port: int) -> Optional[int]:
    """netstat ile verilen portu dinleyen PID'i bulur (Windows, best-effort)."""
    try:
        out = await asyncio.to_thread(
            subprocess.run,
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW)
        for line in (out.stdout or "").splitlines():
            parts = line.split()
            # TCP    127.0.0.1:8765   0.0.0.0:0    LISTENING    12345
            if len(parts) >= 5 and parts[3].upper() == "LISTENING" \
                    and parts[1].endswith(f":{port}"):
                return int(parts[4])
    except Exception:
        pass
    return None


def tail_log(n_chars: int = 2000) -> str:
    """Son n karakterlik relay log'u (hata teşhisi için)."""
    try:
        return Path(config.MCP_LOG_FILE).read_text(
            encoding="utf-8", errors="replace")[-n_chars:]
    except Exception:
        return ""
