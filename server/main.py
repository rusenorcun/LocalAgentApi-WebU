"""FastAPI uygulamasi — yalniz v2 API + SPA servis.

GUVENLIK (G1): Eski v1 auth/admin uclari (/api/register, /api/login, /api/me,
/api/admin/*) KALDIRILDI. Bunlar JSON tabanli ayri bir kimlik dunyasi kuruyordu
(kilitleme yok, refresh yok, ayri admin kaynagi). Tek kimlik kaynagi v2'dir
(auth_v2 + SQLite). Eski JSON verisi migrate_json ile tasinir.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import config, files, settings
from .database import init_db
from .queue_manager import queue
from .routers import admin as admin_router
from .routers import rag as rag_router
from .routers import auth as auth_router
from .routers import chats as chats_router
from .routers import mcp as mcp_router
from .routers import models as models_router
from .routers import api_keys as api_keys_router
from .routers import ollama_connections as ollama_router
from .routers import ollama_openai as ollama_openai_router
from .routers import ollama_proxy as ollama_proxy_router
from .routers import summaries as summaries_router
from .routers import projects as projects_router
from .security import SecurityHeadersMiddleware, limiter


@asynccontextmanager
async def lifespan(app):
    settings.init()
    await init_db()
    yield


app = FastAPI(
    title="Yerel Ollama Sohbet Sunucusu",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router.router)
app.include_router(api_keys_router.router)
app.include_router(chats_router.router)
app.include_router(models_router.router)
app.include_router(admin_router.router)
app.include_router(rag_router.router)
app.include_router(summaries_router.router, prefix="/api/v2/summaries", tags=["summaries"])
app.include_router(projects_router.router)
app.include_router(ollama_router.router)
app.include_router(ollama_proxy_router.router)
app.include_router(mcp_router.router)
app.include_router(ollama_openai_router.router, prefix="")


@app.get("/api/v2/health")
async def health_v2():
    return {"status": "ok", "model": config.MODEL_NAME, "queue": queue.stats}


@app.get("/api/health")
async def health():
    """Eski izleme betikleri icin korunan basit saglik ucu."""
    return {"status": "ok", "model": config.MODEL_NAME, "queue": queue.stats,
            "extractors": files.available()}


# ── SPA servis ────────────────────────────────────────────────────────────────
# React (Vite) build çıktısı web/dist'ten servis edilir. Build yoksa anlamlı
# bir hata sayfası döner (eski vanilla arayüz artık kullanılmıyor).
_INDEX = config.WEB_DIST / "index.html"

if (config.WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(config.WEB_DIST / "assets")), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    """SPA fallback: /login, /chat/:id, /admin gibi istemci rotaları index.html'e düşer."""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Bulunamadı")
    # dist içindeki gerçek dosyalar (favicon, manifest...) doğrudan verilir
    if full_path:
        candidate = (config.WEB_DIST / full_path).resolve()
        try:
            candidate.relative_to(config.WEB_DIST.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="Bulunamadı")
        if candidate.is_file():
            return FileResponse(candidate)
    if _INDEX.is_file():
        return FileResponse(_INDEX)
    raise HTTPException(
        status_code=503,
        detail="Arayuz build edilmemis.",
    )
