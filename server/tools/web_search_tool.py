"""web_search araci — DuckDuckGo uzerinden guncel bilgi getirir.

ddg_search -> fetch_pages -> build_context hattini kullanir (server/web_search.py).
Model-facing metin (kaynak numarali baglam) + UI icin kaynak listesi dondurur.

TOKEN NOTU: Agentic dongude bu arac birkac kez cagrilabilir; her sonuc baglama
girer. Bu yuzden sayfa okuma sayisi (PAGE_FETCH_K) ve sayfa basina metin
(PAGE_CONTENT_MAX) bilinçli olarak kisitlidir — kalite/token dengesi.
"""
from . import ToolSpec, register_tool
from .. import web_search

PAGE_FETCH_K = 2        # tam metni okunacak ilk sonuc sayisi
PAGE_CONTENT_MAX = 1800  # sayfa basina modele giden azami karakter


async def _run(args: dict):
    query = (args or {}).get("query", "")
    query = query.strip() if isinstance(query, str) else ""
    if not query:
        return {"text": "Bos arama sorgusu.", "sources": []}
    try:
        items = await web_search.ddg_search(query)
    except Exception:
        items = []
    if not items:
        return {"text": f"'{query}' icin web sonucu bulunamadi.", "sources": []}
    items = await web_search.fetch_pages(items, k=PAGE_FETCH_K)
    # Sayfa metinlerini kirp (build_context'e girmeden once).
    items = [
        {**it, "content": (it.get("content") or "")[:PAGE_CONTENT_MAX]}
        for it in items
    ]
    text = web_search.build_context(query, items)
    sources = [
        {
            "title": it.get("title") or it.get("url") or "",
            "url": it.get("url", ""),
            "snippet": (it.get("body") or "")[:160],
        }
        for it in items
    ]
    return {"text": text, "sources": sources}


register_tool(
    ToolSpec(
        name="web_search",
        description=(
            "Guncel, degisken veya bilmedigin bilgileri internette arar. "
            "Haberler, fiyatlar, kisiler, tarihler, son olaylar, surum bilgileri "
            "gibi egitim verinde olmayabilecek seyler icin kullan."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Arama sorgusu (kullanicinin dilinde, kisa ve odakli).",
                }
            },
            "required": ["query"],
        },
        run=_run,
    )
)
