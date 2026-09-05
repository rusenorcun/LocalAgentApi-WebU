"""Web arama hatti (DuckDuckGo).

Strateji:
 1) `ddgs` paketi (eski adi duckduckgo-search) ile sonuc listesi al. Yoksa
    html.duckduckgo.com kazimasina dus.
 2) En iyi K sonucun sayfa metnini eszamanli cek + temizle (daha derin baglam).
 3) Modele verilecek tek bir baglam metni derle (kaynak numarali, alintilanabilir).

ddgs senkron oldugundan thread'e devredilir (asyncio.to_thread).
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

PAGE_TEXT_MAX = 2500
SNIPPET_MAX = 400


def _ddgs_search_sync(query, max_results, region):
    """ddgs paketiyle senkron arama (thread'de calistirilir)."""
    DDGS = None
    try:
        from ddgs import DDGS as _D
        DDGS = _D
    except Exception:
        try:
            from duckduckgo_search import DDGS as _D2
            DDGS = _D2
        except Exception:
            return []

    out = []
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, region=region, safesearch="moderate", max_results=max_results)
            for r in results:
                url = r.get("href") or r.get("url") or ""
                title = r.get("title") or ""
                body = r.get("body") or ""
                if url:
                    out.append({"title": title.strip(), "url": url.strip(), "body": body.strip()})
    except Exception as e:
        logger.warning("ddgs arama hatasi: %s", e)
    return out


async def _html_scrape_fallback(query, max_results):
    """ddgs yoksa/basarisizsa html.duckduckgo.com kazimasi."""
    if BeautifulSoup is None:
        return []
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": _UA}) as client:
            r = await client.get(url)
            if r.status_code != 200:
                logger.warning("DDG HTML fallback %s", r.status_code)
                return []
            soup = BeautifulSoup(r.text, "html.parser")
            out = []
            for item in soup.find_all("div", class_="result__body"):
                if len(out) >= max_results:
                    break
                te = item.find("a", class_="result__a")
                se = item.find("a", class_="result__snippet")
                if te:
                    out.append({
                        "title": te.get_text(strip=True),
                        "url": te.get("href", ""),
                        "body": se.get_text(strip=True) if se else "",
                    })
            return out
    except Exception as e:
        logger.error("DDG HTML fallback hatasi: %s", e)
        return []


async def ddg_search(query, max_results=6, region="tr-tr"):
    """Web arama sonuclarini dondurur: [{title, url, body}]. Bir kez retry'lar."""
    query = (query or "").strip()
    if not query:
        return []
    items = await asyncio.to_thread(_ddgs_search_sync, query, max_results, region)
    if not items:
        await asyncio.sleep(1.5)
        items = await asyncio.to_thread(_ddgs_search_sync, query, max_results, region)
    if not items:
        items = await _html_scrape_fallback(query, max_results)
    return items[:max_results]


def _extract_readable(html):
    """HTML'den okunabilir duz metin cikarir (script/style/nav atilir)."""
    if BeautifulSoup is None:
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "form", "svg"]):
            tag.decompose()
        main = soup.find("article") or soup.find("main") or soup.body or soup
        text = main.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""


async def _fetch_one(client, item, per_timeout):
    url = item.get("url", "")
    if not url.startswith("http"):
        return item
    try:
        r = await asyncio.wait_for(client.get(url), timeout=per_timeout)
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and "text/html" in ctype:
            txt = _extract_readable(r.text)
            if txt:
                item = {**item, "content": txt[:PAGE_TEXT_MAX]}
    except Exception:
        pass
    return item


async def fetch_pages(items, k=3, per_timeout=6.0):
    """Ilk k sonucun sayfa metnini eszamanli ceker; 'content' alani ekler."""
    if not items:
        return items
    head, tail = items[:k], items[k:]
    try:
        async with httpx.AsyncClient(
            timeout=per_timeout + 2, follow_redirects=True, headers={"User-Agent": _UA},
        ) as client:
            fetched = await asyncio.gather(*[_fetch_one(client, it, per_timeout) for it in head])
        return list(fetched) + tail
    except Exception as e:
        logger.warning("fetch_pages hatasi: %s", e)
        return items


def build_context(query, items):
    """Modele verilecek baglam metnini derler (kaynak numarali + alinti talimati)."""
    if not items:
        return ""
    blocks = []
    for i, it in enumerate(items, 1):
        title = it.get("title") or it.get("url") or ("Kaynak " + str(i))
        url = it.get("url", "")
        body = (it.get("body") or "")[:SNIPPET_MAX]
        content = it.get("content", "")
        block = "[" + str(i) + "] " + title + "\nURL: " + url + "\nOzet: " + body
        if content:
            block += "\nIcerik: " + content
        blocks.append(block)
    joined = "\n\n".join(blocks)
    return (
        "[WEB ARAMA SONUCLARI]\n"
        "Asagidaki guncel web kaynaklari '" + query + "' sorgusu icin getirildi. "
        "Yanitini bu kaynaklara dayandir, kaynak numaralariyla ([1], [2]) atif yap "
        "ve kaynaklarda olmayan bilgi uydurma.\n\n" + joined
    )


async def search_duckduckgo(query, max_results=5):
    """Eski API: tek metin dondurur (v1 uclari icin)."""
    items = await ddg_search(query, max_results=max_results)
    if not items:
        return ""
    return build_context(query, items)
