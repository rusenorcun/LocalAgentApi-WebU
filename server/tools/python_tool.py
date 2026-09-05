"""run_python araci — izole subprocess'te kisa Python kodu calistirir.

GUVENLIK:
  - Yalnizca config.TOOL_PYTHON_ENABLED=True iken REGISTRY'ye kaydolur (varsayilan KAPALI).
  - Ana surecte ASLA exec/eval yok; kod ayri bir surecte calisir.
  - python -I -S (izole mod, kullanici site/env yok) + gecici cwd + kisitli env + zaman asimi.
  - Ag/dosya izolasyonu best-effort'tur; tam izolasyon icin OS sandbox'i onerilir.
"""
import asyncio
import os
import shutil
import sys
import tempfile

from . import ToolSpec, register_tool
from .. import config

_TIMEOUT = 8.0
_MAX_OUTPUT = 4000


async def _run(args: dict):
    code = (args or {}).get("code", "")
    code = code if isinstance(code, str) else ""
    if not code.strip():
        return "Bos kod."
    workdir = tempfile.mkdtemp(prefix="pytool_")
    src = os.path.join(workdir, "snippet.py")
    try:
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),  # Windows'ta gerekli
        }
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", "-S", src,
            cwd=workdir, env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return f"Zaman asimi ({_TIMEOUT}s) — kod sonlandirildi."
        text = (out or b"").decode("utf-8", "replace")
        if len(text) > _MAX_OUTPUT:
            text = text[:_MAX_OUTPUT] + "\n…(kirpildi)"
        return text or "(cikti yok)"
    except Exception as e:
        return f"Calistirma hatasi: {e}"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if config.TOOL_PYTHON_ENABLED:
    register_tool(ToolSpec(
        name="run_python",
        description=(
            "Kisa, bagimsiz Python kodu calistirir ve stdout ciktisini dondurur. "
            "Hesaplama, veri donusturme, hizli dogrulama icin. Sonucu print() ile yazdir. "
            "Ag/dosya erisimine guvenme."
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Calistirilacak Python kodu; sonucu print() ile yazdir.",
                }
            },
            "required": ["code"],
        },
        run=_run,
    ))
