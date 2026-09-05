"""Yerel Ollama MCP sunucusu — Claude'dan yerel/uzak modellere delegasyon.

Claude Desktop / Cowork'e stdio MCP olarak eklenir (bkz. mcp/README.md).
Araclar:
  * genel_sohbet    → MCP_CHAT_MODEL (vars. qwen3.6:35b-a3b-q4_K_M) — genel konular
  * derin_analiz    → MCP_REASONER_MODEL (vars. gpt-oss:120b) — YAVAS ama guclu
  * kod_yaz         → MCP_CODER_MODEL (vars. qwen3-coder:30b) — kodlama
  * web_ara         → DuckDuckGo ile guncel web aramasi
  * yerel_sohbet    → istenen herhangi bir yerel modelle tek atimlik sohbet
  * modelleri_listele → diskteki + bellekte yuklu modeller
  * uzaktan_sohbet  → kaydedilmis uzak Ollama baglantisindan model calistirma
  * uzaktan_modelleri_listele → kaydedilmis uzak Ollama baglantisinin modelleri

Ortam degiskenleri:
  OLLAMA_HOST          (vars. http://127.0.0.1:11434)
  MCP_CHAT_MODEL       (vars. qwen3.6:35b-a3b-q4_K_M)
  MCP_REASONER_MODEL   (vars. gpt-oss:120b)
  MCP_CODER_MODEL      (vars. qwen3-coder:30b)
  OLLAMA_CONNECTION_ID (opsiyonel) → data/ollama_connections.json'daki baglanti

Kurulum: .venv icine `pip install "mcp[cli]"` (requirements.txt icinde).

DIKKAT: Bu modulde `from __future__ import annotations` KULLANMA —
mcp SDK (<=1.x) FastMCP tool kaydinda annotation'lari dogrudan sinif olarak
sorgular (issubclass(param.annotation, Context)); string annotation'lar
TypeError ile tum arac kaydini cokertir.
"""
import asyncio
import json
import os
import re
import secrets
import urllib.parse
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
CHAT_MODEL = os.getenv("MCP_CHAT_MODEL", "qwen3.6:35b-a3b-q4_K_M")
REASONER_MODEL = os.getenv("MCP_REASONER_MODEL", "gpt-oss:120b")
CODER_MODEL = os.getenv("MCP_CODER_MODEL", "qwen3-coder:30b")

# Uzak baglanti env'si: "__local_default__" veya bos ise yerel Ollama kullanilir.
OLLAMA_CONNECTION_ID = os.getenv("OLLAMA_CONNECTION_ID", "").strip()
OLLAMA_PROXY_DOMAIN = os.getenv("OLLAMA_PROXY_DOMAIN", "api.rorcun.com")
OLLAMA_PROXY_PATH = os.getenv("OLLAMA_PROXY_PATH", "/ollama")
OLLAMA_PROXY_FORCE = os.getenv("OLLAMA_PROXY_FORCE", "true").lower() == "true"


def _data_dir() -> Path:
    # Panel DATA_DIR'i ile ayni konum; env yoksa proje/data.
    base = Path(__file__).resolve().parent.parent
    return Path(os.getenv("DATA_DIR", str(base / "data")))


def _default_host() -> str:
    return OLLAMA_HOST.rstrip("/")


def _proxy_url(connection_id: str) -> str:
    return f"https://{OLLAMA_PROXY_DOMAIN}{OLLAMA_PROXY_PATH}/{connection_id}"


def _resolve_connection() -> tuple[str, str | None]:
    """Aktif baglanti (base_url/proxy_url, api_key) dondurur.

    Yerel default disindaki baglantilar icin api.rorcun.com/ollama uzerinden
    guvenli proxy kullanilir; gercek Ollama endpoint'i hicbir zaman disari
    acilmaz. API key olmadan proxy 401 doner ve Ollama'ya baglanti baslamaz.
    """
    if not OLLAMA_CONNECTION_ID or OLLAMA_CONNECTION_ID == "__local_default__":
        return _default_host(), None
    conns_file = _data_dir() / "ollama_connections.json"
    try:
        items = json.loads(conns_file.read_text(encoding="utf-8"))
        for item in items:
            if item.get("id") == OLLAMA_CONNECTION_ID:
                api_key = item.get("api_key") or None
                if OLLAMA_PROXY_FORCE and not item.get("is_local"):
                    return _proxy_url(item["id"]), api_key
                return item.get("base_url", _default_host()).rstrip("/"), api_key
    except Exception:
        pass
    return _default_host(), None


def _load_remote_connection(baglanti_id: str) -> tuple[str, str | None] | None:
    """Uzak baglanti icin (url, api_key) dondurur. Yerel id verilirse None."""
    conns_file = _data_dir() / "ollama_connections.json"
    try:
        items = json.loads(conns_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    item = next((i for i in items if i.get("id") == baglanti_id), None)
    if not item or item.get("is_local"):
        return None
    api_key = item.get("api_key") or None
    if OLLAMA_PROXY_FORCE:
        return _proxy_url(item["id"]), api_key
    return item.get("base_url", _default_host()).rstrip("/"), api_key


# 120B buyuk olcude CPU'da calisir — uzun okuma zaman asimi sart.
_TIMEOUT = httpx.Timeout(connect=10.0, read=3600.0, write=60.0, pool=10.0)

mcp = FastMCP("yerel-ollama")


def _strip_thinking(text: str) -> str:
    """Reasoning modellerin <think>...</think> bloklarini ayikla."""
    if "<think>" in text:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
        text = re.sub(r"<think>.*$", "", text, flags=re.S)
    return text.strip()


async def _chat(model: str, prompt: str, system: str = "",
                num_ctx: int = 16384, keep_alive: str = "5m",
                base_url: str | None = None, api_key: str | None = None) -> str:
    host = (base_url or _default_host()).rstrip("/")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": num_ctx},
        "keep_alive": keep_alive,
    }
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(f"{host}/api/chat", json=payload, headers=headers)
        if r.status_code != 200:
            return f"[Ollama hatasi {r.status_code}] {r.text[:300]}"
        data = r.json()
        msg = data.get("message") or {}
        # Ollama, thinking'i ayri alanda dondurebilir — nihai icerigi tercih et
        content = (msg.get("content") or "").strip()
        return _strip_thinking(content) or "[Bos yanit]"


async def _list_remote_models(base_url: str, api_key: str | None) -> tuple[list[str], str | None]:
    """Uzak/ya da yerel Ollama'dan model listesi çeker; (names, error)."""
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base_url.rstrip('/')}/api/tags", headers=headers)
            if r.status_code == 401:
                return [], "Yetkilendirme hatasi (401) — API anahtarini kontrol edin."
            if r.status_code != 200:
                return [], f"Ollama hatasi {r.status_code}: {r.text[:200]}"
            return [m.get("name") for m in r.json().get("models", []) if m.get("name")], None
    except Exception as e:
        return [], f"Ollama'ya erisilemedi ({base_url}): {e}"


@mcp.tool()
async def genel_sohbet(istem: str, baglam: str = "", sistem: str = "") -> str:
    """Ortak varsayılan Ollama bağlantısı üzerinden genel amaçlı modelle sohbet.

    Günlük sorular, açıklama, özet, çeviri, yazı taslağı gibi GENEL görevler
    için varsayılan araç budur. Kod için kod_yaz, ağır analiz için derin_analiz,
    farklı bir uzak bağlantıdan model çalıştırmak için uzaktan_sohbet kullan.

    Args:
        istem: Kullanıcının sorusu/görevi.
        baglam: (opsiyonel) İlgili arka plan bilgisi veya metin.
        sistem: (opsiyonel) Sistem talimatı.
    """
    prompt = istem if not baglam else f"BAGLAM:\n{baglam}\n\nISTEK:\n{istem}"
    host, key = _resolve_connection()
    return await _chat(CHAT_MODEL, prompt, system=sistem,
                       num_ctx=16384, keep_alive="30m",
                       base_url=host, api_key=key)


@mcp.tool()
async def derin_analiz(soru: str, baglam: str = "") -> str:
    """Ortak varsayılan Ollama bağlantısı üzerinden güçlü modelle derin analiz.

    Karmaşık analiz, çok adımlı planlama, zor matematik/mantık soruları için.
    UYARI: Model büyük ölçüde CPU'da çalışabilir — yanıt DAKİKALAR sürebilir.
    Basit sorular için bunu KULLANMA.

    Args:
        soru: Analiz edilecek soru/görev.
        baglam: (opsiyonel) İlgili arka plan bilgisi, veri veya kod.
    """
    prompt = soru if not baglam else f"BAGLAM:\n{baglam}\n\nSORU/GOREV:\n{soru}"
    host, key = _resolve_connection()
    return await _chat(REASONER_MODEL, prompt, num_ctx=16384, keep_alive="5m",
                       base_url=host, api_key=key)


@mcp.tool()
async def kod_yaz(gorev: str, kod_baglami: str = "", dil: str = "") -> str:
    """Ortak varsayılan Ollama bağlantısı üzerinden kod üretir/duzeltir/refactor eder.

    Args:
        gorev: Ne yapılacağı (özellik, hata düzeltme, refactor tarifi).
        kod_baglami: (opsiyonel) Mevcut kod, dosya içerikleri, hata çıktısı.
        dil: (opsiyonel) Hedef dil/çerçeve (örn. "python", "react+ts").
    """
    system = ("Sen uzman bir yazilimcisin. Eksiksiz, calisir ve temiz kod yaz. "
              "Kod bloklarini dil etiketiyle bicimlendir; kisa kurulum/kullanim notu ekle.")
    parts = []
    if dil:
        parts.append(f"HEDEF DIL/CERCEVE: {dil}")
    if kod_baglami:
        parts.append(f"MEVCUT KOD/BAGLAM:\n{kod_baglami}")
    parts.append(f"GOREV:\n{gorev}")
    host, key = _resolve_connection()
    return await _chat(CODER_MODEL, "\n\n".join(parts), system=system,
                       num_ctx=16384, keep_alive="30m",
                       base_url=host, api_key=key)


@mcp.tool()
async def web_ara(sorgu: str, sonuc_sayisi: int = 5) -> str:
    """DuckDuckGo ile internette guncel arama yapar (sonuc + URL listesi).

    Guncel olaylar, fiyatlar, haberler, surum bilgileri, tarihler gibi
    egitim verisinde olmayabilecek konularda KULLAN. Yanitinda bilgiyi
    verdigin URL'lere atif yaparak aktar.

    Args:
        sorgu: Aranacak ifade (kisa ve odakli; kullanici dilinde).
        sonuc_sayisi: Donderilecek sonuc sayisi (varsayilan 5, en fazla 10).
    """
    n = max(1, min(int(sonuc_sayisi or 5), 10))
    q = (sorgu or "").strip()
    if not q:
        return "Bos arama sorgusu."

    def _sync():
        DDGS = None
        try:
            from ddgs import DDGS as _D
            DDGS = _D
        except Exception:
            try:
                from duckduckgo_search import DDGS as _D2
                DDGS = _D2
            except Exception:
                return None
        items = []
        try:
            # timeout: DNS/ag takilursa istek sonsuza kadar askida kalmasin
            with DDGS(timeout=10) as d:
                for r in d.text(q, region="tr-tr", safesearch="moderate", max_results=n):
                    url = r.get("href") or r.get("url") or ""
                    if url:
                        items.append((r.get("title", ""), url, r.get("body", "")))
        except Exception as e:
            return f"[Arama hatasi] {e}"
        return items

    try:
        res = await asyncio.wait_for(asyncio.to_thread(_sync), timeout=30.0)
    except asyncio.TimeoutError:
        return "[Arama hatasi] Zaman asimi (30 sn) — ag cok yavas olabilir."
    if res is None:
        return ("Arama paketi kurulu degil (ddgs). Kurulum: "
                '.venv\\Scripts\\pip install "ddgs>=9.0.0"')
    if isinstance(res, str):
        return res
    if not res:
        return f"'{q}' icin web sonucu bulunamadi."
    lines = [f"'{q}' icin web sonuclari:"]
    for i, (title, url, body) in enumerate(res, 1):
        lines.append(f"\n[{i}] {title}\nURL: {url}\n{(body or '')[:300]}")
    lines.append("\n(Yanitinda bu kaynaklari numarayla atif yap; kaynaksiz bilgi verme.)")
    return "\n".join(lines)


@mcp.tool()
async def yerel_sohbet(istem: str, model: str = "", sistem: str = "") -> str:
    """Ortak varsayılan Ollama bağlantısı üzerinden herhangi bir modelle üretim.

    Args:
        istem: Kullanıcı istemi.
        model: Ollama model adı — ZORUNLU. Bilmiyorsan once modelleri_listele
               cagir ve listedeki adlardan birini aynen kullan.
        sistem: (opsiyonel) Sistem talimatı.
    """
    if not model:
        return ("Model adi gerekli — once modelleri_listele aracini cagirip "
                "listedeki bir adla tekrar dene.")
    host, key = _resolve_connection()
    names, err = await _list_remote_models(host, key)
    if err:
        return err
    base = model.split(":")[0]
    if model not in names and not any(n and n.startswith(base + ":") for n in names):
        avail = ", ".join(n for n in names if n)[:300]
        return (f"Model bulunamadi: '{model}'. Kurulu modeller: {avail}. "
                "Tam adla (etiket dahil) tekrar dene.")
    return await _chat(model, istem, system=sistem, num_ctx=8192, keep_alive="10m",
                       base_url=host, api_key=key)


@mcp.tool()
async def uzaktan_sohbet(baglanti_id: str, istem: str, model: str = "", sistem: str = "") -> str:
    """Kaydedilmis uzak Ollama baglantisindan herhangi bir modelle tek atimlik uretim.

    Args:
        baglanti_id: data/ollama_connections.json icindeki baglanti kimligi.
        istem: Kullanici istemi.
        model: Ollama model adi — ZORUNLU. Bilmiyorsan once
               uzaktan_modelleri_listele aracini cagir.
        sistem: (opsiyonel) Sistem talimati.
    """
    if not baglanti_id or not model:
        return "baglanti_id ve model adi zorunlu."
    resolved = _load_remote_connection(baglanti_id)
    if resolved is None:
        info_path = f"{_proxy_url(baglanti_id)}/api/tags"
        try:
            import urllib.request
            urllib.request.urlopen(info_path, timeout=3)
        except Exception:
            pass
        return f"Baglanti bulunamadi veya yerel baglanti: '{baglanti_id}'."
    host, key = resolved
    names, err = await _list_remote_models(host, key)
    if err:
        return err
    base = model.split(":")[0]
    if model not in names and not any(n and n.startswith(base + ":") for n in names):
        avail = ", ".join(n for n in names if n)[:300]
        return (f"Model bulunamadi: '{model}'. Kurulu modeller: {avail}.")
    return await _chat(model, istem, system=sistem, num_ctx=8192, keep_alive="10m",
                       base_url=host, api_key=key)


@mcp.tool()
async def uzaktan_modelleri_listele(baglanti_id: str) -> str:
    """Kaydedilmis uzak Ollama baglantisindaki modelleri listeler.

    Args:
        baglanti_id: data/ollama_connections.json icindeki baglanti kimligi.
    """
    if not baglanti_id:
        return "baglanti_id zorunlu."
    resolved = _load_remote_connection(baglanti_id)
    if resolved is None:
        return f"Baglanti bulunamadi veya yerel baglanti: '{baglanti_id}'."
    host, key = resolved
    names, err = await _list_remote_models(host, key)
    if err:
        return err
    return f"Uzak baglanti ({host}) modelleri:\n" + "\n".join(f"  - {n}" for n in names)


@mcp.tool()
async def modelleri_listele() -> str:
    """Ortak varsayılan Ollama bağlantısındaki diskteki ve bellekteki modelleri listeler."""
    out = []
    host, key = _resolve_connection()
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{host}/api/tags", headers=headers)
            r.raise_for_status()
            out.append("DISKTE:")
            for m in r.json().get("models", []):
                size_gb = (m.get("size", 0) or 0) / 1e9
                out.append(f"  - {m.get('name')} ({size_gb:.1f} GB)")
            r2 = await client.get(f"{host}/api/ps", headers=headers)
            if r2.status_code == 200:
                running = r2.json().get("models", [])
                out.append("BELLEKTE:" if running else "BELLEKTE: (yok)")
                for m in running:
                    vram_gb = (m.get("size_vram", 0) or 0) / 1e9
                    out.append(f"  - {m.get('name')} (VRAM: {vram_gb:.1f} GB)")
    except Exception as e:
        return f"Ollama'ya erisilemedi ({host}): {e}"
    return "\n".join(out)


class _BearerGuard:
    """HTTP modunda tek anahtarli kimlik dogrulama (ASGI sarmalayici).

    Kabul edilen iki bicim:
      * Authorization: Bearer <MCP_TOKEN>   (header destekleyen istemciler)
      * ...?token=<MCP_TOKEN>               (yalniz URL girilebilen istemciler,
                                             orn. claude.ai custom connector)
    /healthz yolu MUAF tutulur (panel/Caddy saglik kontrolleri anahtarsiz
    calisir; yanit hassas bilgi icermez).

    Kullanici kaydi/oturum yonetimi YOKTUR ve gerekmez — sunucunun tek sahibi
    var; anahtar, HTTPS/VPN uzerinden tasindigi surece yeterlidir.
    """

    HEALTH_PATH = "/healthz"

    def __init__(self, app, token: str):
        self._app = app
        self._token = token

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path != self.HEALTH_PATH:
                ok = False
                expected = "Bearer " + self._token
                for k, v in scope.get("headers") or []:
                    if k == b"authorization":
                        try:
                            ok = secrets.compare_digest(v.decode("utf-8"), expected)
                        except Exception:
                            ok = False
                        break
                if not ok:
                    qs = urllib.parse.parse_qs(
                        (scope.get("query_string") or b"").decode("utf-8", "replace"))
                    tok = (qs.get("token") or [""])[0]
                    ok = bool(tok) and secrets.compare_digest(tok, self._token)
                if not ok:
                    await send({"type": "http.response.start", "status": 401,
                                "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                                            (b"www-authenticate", b"Bearer")]})
                    await send({"type": "http.response.body",
                                "body": b"Unauthorized: MCP_TOKEN gerekli"})
                    return
        await self._app(scope, receive, send)


if __name__ == "__main__":
    # Taşıma modu:
    #   stdio (varsayilan) — Claude Desktop dosyayi kendisi baslatir, port yok.
    #   http              — Streamable HTTP sunucusu (uzaktan erisim icin).
    #                       MCP_HOST/MCP_PORT ile dinleme adresi secilir,
    #                       MCP_TOKEN ile tek anahtarli auth uygulanir.
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport in ("http", "streamable-http"):
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_PORT", "8765"))
        token = os.getenv("MCP_TOKEN", "").strip()
        if not token and host not in ("127.0.0.1", "localhost", "::1"):
            raise SystemExit(
                "HATA: MCP_TOKEN tanimlamadan 127.0.0.1 disina acilamaz.\n"
                "Anahtar uretmek icin: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        mcp.settings.host = host
        mcp.settings.port = port
        app = mcp.streamable_http_app()

        # Saglik ucu: panel/Caddy izleme icin token'siz GET /healthz.
        # Ollama erisilebilirligini de raporlar (bagimlilik durumu tek bakista).
        # NOT: Route, guard sarmalamasindan ONCE eklenir (guard'in router'i yok).
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def _healthz(request):
            ollama_ok = False
            active_host = _default_host()
            try:
                host, key = _resolve_connection()
                active_host = host
                headers = {"Authorization": f"Bearer {key}"} if key else {}
                async with httpx.AsyncClient(timeout=3.0) as client:
                    rr = await client.get(f"{host}/api/tags", headers=headers)
                    ollama_ok = (rr.status_code == 200)
            except Exception:
                pass
            return JSONResponse({"status": "ok", "service": "yerel-ollama-mcp",
                                 "ollama": ollama_ok, "host": active_host,
                                 "tools": 8})

        app.router.routes.append(Route("/healthz", _healthz, methods=["GET"]))

        if token:
            app = _BearerGuard(app, token)

        import uvicorn
        print(f"MCP HTTP: http://{host}:{port}/mcp  (auth: {'ACIK' if token else 'KAPALI — yalniz localhost'})")
        print(f"Saglik:   http://{host}:{port}/healthz")
        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        mcp.run()
