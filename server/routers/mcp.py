"""API v2 — MCP HTTP relay yönetimi (yalnızca admin).

Panelin "MCP Server" sayfasını besleyen uçlar:
  GET  /status  → süreç durumu + sağlık + maskeli token
  POST /start   → relay'i HTTP modunda alt süreç olarak başlatır
  POST /stop    → durdurur (?force=true: dış örnek dahil)
  GET  /token   → TAM token (Claude Desktop / claude.ai config'i için)
  GET  /tools   → sohbet-içi araçlar (REGISTRY) + relay'in CANLI araç listesi

Süreç yaşam döngüsü server/services/mcp_manager.py'dedir; bu dosya yalnızca
HTTP arayüzüdür.
"""
import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import config
from ..auth_v2 import require_admin
from ..services import mcp_manager

router = APIRouter(prefix="/api/v2/mcp", tags=["mcp"])


class McpActionOut(BaseModel):
    ok: bool
    error: str | None = None


class McpStartOut(BaseModel):
    ok: bool
    already: bool = False
    managed: bool = False
    pid: int | None = None
    warning: str | None = None


class McpStopOut(BaseModel):
    ok: bool
    stopped: int | None = None


# ── Durum ─────────────────────────────────────────────────────────────────────

@router.get("/status")
async def mcp_status(_: object = Depends(require_admin)):
    return await mcp_manager.get_status()


@router.get("/token")
async def mcp_token(_: object = Depends(require_admin)):
    """TAM MCP_TOKEN — istemci tarafı config için. Yalnızca admin."""
    tok = mcp_manager.read_or_create_token()
    st = await mcp_manager.get_status()
    return {"token": tok, "masked": st["token_masked"], "url": st["url"],
            "public_hint": "https://rorcun.com/mcp  (Caddy aktifse)"}


@router.post("/start", response_model=McpStartOut)
async def mcp_start(_: object = Depends(require_admin)):
    res = await mcp_manager.start()
    if not res.get("ok"):
        raise HTTPException(status_code=502, detail=res.get("error") or "Başlatılamadı")
    return {"ok": True, "already": bool(res.get("already")),
            "managed": bool(res.get("managed")), "pid": res.get("pid"),
            "warning": res.get("warning")}


@router.post("/stop", response_model=McpStopOut)
async def mcp_stop(force: bool = False, _: object = Depends(require_admin)):
    """force=True: .bat ile başlatılmış DIŞ örneği de düşürmeye çalışır."""
    res = await mcp_manager.stop(force=force)
    if not res.get("ok"):
        raise HTTPException(status_code=409, detail=res.get("error") or "Durdurulamadı")
    return {"ok": True, "stopped": res.get("stopped")}


# ── Araç listeleri ────────────────────────────────────────────────────────────

def _chat_tools_payload() -> list[dict]:
    """Sohbet-içi araçlar: REGISTRY gerçek kayıtlarından üretilir.
    TOOL_PYTHON_ENABLED kapalıyken run_python kayıtlı DEĞİLDİR ama panelde
    'devre dışı' görünür ki kullanıcı farkında olsun."""
    from ..tools import REGISTRY

    items = [
        {"name": s.name, "description": s.description, "enabled": True}
        for s in REGISTRY.values()
    ]
    if not config.TOOL_PYTHON_ENABLED:
        items.append({
            "name": "run_python",
            "description": ("Kısa, bağımsız Python kodu çalıştırır (subprocess, "
                            "izole). Kapalı — TOOL_PYTHON_ENABLED=true ile açılır."),
            "enabled": False,
        })
    return sorted(items, key=lambda x: x["name"])


async def _relay_live_tools(token: str) -> list[dict] | None:
    """Relay ayaktaysa JSON-RPC tools/list ile GERÇEK araç şemasını çeker;
    erişilemezse None döner (frontend statik liste gösterir)."""
    base = f"http://{config.MCP_HTTP_HOST}:{config.MCP_HTTP_PORT}/mcp"
    accept = {"Accept": "application/json, text/event-stream",
              "Authorization": f"Bearer {token}"}

    def _rpc(resp):
        ct = resp.headers.get("content-type", "")
        if "text/event-stream" in ct:
            for ln in resp.text.splitlines():
                if ln.startswith("data:"):
                    p = ln[5:].strip()
                    if p and p != "[DONE]":
                        return json.loads(p)
            return None
        try:
            return resp.json()
        except Exception:
            return None

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r1 = await client.post(base, headers=accept, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "panel", "version": "1"}}})
            msg = _rpc(r1)
            if not msg or "result" not in msg:
                return None
            sid = r1.headers.get("mcp-session-id")
            hdrs = dict(accept)
            if sid:
                hdrs["mcp-session-id"] = sid
                await client.post(base, headers=hdrs, json={
                    "jsonrpc": "2.0", "method": "notifications/initialized"})
            r2 = await client.post(base, headers=hdrs, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            msg = _rpc(r2)
            if not msg or "result" not in msg:
                return None
            return [
                {"name": t["name"], "description": t.get("description", "")}
                for t in msg["result"].get("tools", [])
            ]
    except Exception:
        return None


@router.get("/tools")
async def mcp_tools(_: object = Depends(require_admin)):
    """Chat araçları (REGISTRY) + relay canlı araç listesi (ayaktaysa)."""
    st = await mcp_manager.get_status()
    relay = None
    if st["healthy"]:
        relay = await _relay_live_tools(mcp_manager.read_or_create_token())
    return {
        "chat_tools": _chat_tools_payload(),
        "relay_tools": relay,
        "relay_healthy": st["healthy"],
    }


@router.get("/log")
async def mcp_log(n: int = 2000, _: object = Depends(require_admin)):
    """Son n karakterlik relay log'u (hata teşhisi için)."""
    return {"log": mcp_manager.tail_log(max(200, min(int(n), 20000)))}
