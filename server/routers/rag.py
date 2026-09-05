"""RAG — belge yükleme, chunking, embedding, retrieval.

NOT: `from __future__ import annotations` KULLANMA — tip ipuçları string'e
dönünce FastAPI, slowapi'nin sardığı endpoint'lerde UploadFile'ı çözemiyor
(Python 3.12: "Invalid args for response field ... ForwardRef('UploadFile')").
"""
import asyncio
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import AsyncIterator

import httpx

try:  # Vektörize benzerlik için numpy (varsa); yoksa saf Python'a düşülür.
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import chat, config, files
from ..auth_v2 import current_user
from ..database import Chunk, Document, User, get_session
from ..queue_manager import queue
from ..security import limiter

router = APIRouter(prefix="/api/v2/rag", tags=["rag"])

CHUNK_SIZE = 512        # token yaklaşımı: karakter / 4
CHUNK_OVERLAP = 64
TOP_K = 5
# Embedding modeli config.EMBED_MODEL'ten okunur (bkz. config.py).


# ── Yardımcılar ──────────────────────────────────────────────────────────────

def _split_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Yapı-farkında chunking: paragraflari korur, kucukleri birlestirir, uzunlari
    kelime penceresiyle (ortusmeli) boler. Daha tutarli, anlamli parcalar -> daha
    isabetli retrieval. (size/overlap kelime cinsinden yaklasik token.)"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        paras = [text.strip()] if text.strip() else []
    chunks: list[str] = []
    cur: list[str] = []
    for p in paras:
        pw = p.split()
        if len(pw) > size:
            # Uzun paragraf: once birikeni kapat, sonra pencereyle bol
            if cur:
                chunks.append(" ".join(cur)); cur = []
            step = max(1, size - overlap)
            for i in range(0, len(pw), step):
                piece = pw[i: i + size]
                if piece:
                    chunks.append(" ".join(piece))
        elif len(cur) + len(pw) > size:
            chunks.append(" ".join(cur))
            tail = cur[-overlap:] if overlap and len(cur) > overlap else cur[:]
            cur = tail + pw
        else:
            cur.extend(pw)
    if cur:
        chunks.append(" ".join(cur))
    return [c for c in chunks if c.strip()]


# ── Rerank: hibrit (anlamsal + sozcuksel) skor + MMR cesitlilik ───────────────

def _keyword_score(query: str, text: str) -> float:
    """Sorgu sozcuklerinin chunk'ta gecme orani (0..1) — sozcuksel sinyal."""
    qw = set(re.findall(r"\w+", query.lower()))
    if not qw:
        return 0.0
    tw = set(re.findall(r"\w+", text.lower()))
    return len(qw & tw) / len(qw)


def _hybrid_score(cosine: float, keyword: float, alpha: float = 0.75) -> float:
    """Anlamsal (cosine) + sozcuksel (keyword) birlesik skor."""
    return alpha * cosine + (1.0 - alpha) * keyword


def _mmr(candidates: list[dict], top_k: int, lambda_: float = 0.7) -> list[dict]:
    """Maximal Marginal Relevance: alaka yuksek ama birbirine benzemeyen (cesitli)
    parcalari secer; tekrar/yakin-kopya chunk'lari eler. candidates: {'score','emb',...}."""
    pool = candidates[:]
    selected: list[dict] = []
    while pool and len(selected) < top_k:
        best, best_val = None, -1e18
        for c in pool:
            div = 0.0
            if c.get("emb") and any(s.get("emb") for s in selected):
                div = max(_cosine_sim(c["emb"], s["emb"]) for s in selected if s.get("emb"))
            val = lambda_ * c["score"] - (1.0 - lambda_) * div
            if val > best_val:
                best_val, best = val, c
        selected.append(best)
        pool.remove(best)
    return selected


async def _embed(text: str) -> list[float] | None:
    """Ollama embed API ile vektör üret."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{config.OLLAMA_HOST}/api/embed",
                # keep_alive: embedding modeli her sorguda yeniden YÜKLENMESİN
                # (bge-m3 küçüktür ama 5 dk sonra boşalırsa RAG soğuk başlar).
                json={"model": config.EMBED_MODEL, "input": text,
                      "keep_alive": config.HELPER_KEEP_ALIVE},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings") or data.get("embedding")
            if isinstance(embeddings, list) and embeddings:
                e = embeddings[0] if isinstance(embeddings[0], list) else embeddings
                return [float(x) for x in e]
    except Exception:
        pass
    return None


async def _embed_batch(texts: list[str]) -> list[list[float] | None]:
    """Toplu embedding — TEK /api/embed çağrısı (P2).

    Ollama embed API'si liste girdi destekler; chunk başına ayrı HTTP çağrısı
    (eski davranış) büyük belgelerde onlarca sıralı istek demekti. Toplu çağrı
    başarısız olursa tek tek üretime düşülür.
    """
    if not texts:
        return []
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{config.OLLAMA_HOST}/api/embed",
                json={"model": config.EMBED_MODEL, "input": texts,
                      "keep_alive": config.HELPER_KEEP_ALIVE},
            )
            resp.raise_for_status()
            embs = resp.json().get("embeddings")
            if isinstance(embs, list) and len(embs) == len(texts):
                return [
                    [float(x) for x in e] if isinstance(e, list) and e else None
                    for e in embs
                ]
    except Exception:
        logger.warning("Toplu embedding başarısız; tek tek üretime düşülüyor", exc_info=True)
    return [await _embed(t) for t in texts]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if _np is not None:
        va = _np.asarray(a, dtype=_np.float32)
        vb = _np.asarray(b, dtype=_np.float32)
        na = float(_np.linalg.norm(va))
        nb = float(_np.linalg.norm(vb))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(va @ vb) / (na * nb)
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _bulk_cosine(query_emb: list[float] | None,
                 embs: list[list[float] | None]) -> list[float]:
    """Sorgu vektörü ile N chunk embedding'inin benzerliği — tek matris çarpımı (P1).

    numpy varsa O(n·d) saf Python döngüsü yerine vektörize hesap; yoksa
    _cosine_sim ile aynı sonucu döndürür.
    """
    n = len(embs)
    if not query_emb or n == 0:
        return [0.0] * n
    if _np is not None:
        out = [0.0] * n
        idx = [i for i, e in enumerate(embs) if e]
        if idx:
            m = _np.asarray([embs[i] for i in idx], dtype=_np.float32)
            qv = _np.asarray(query_emb, dtype=_np.float32)
            qn = float(_np.linalg.norm(qv))
            if qn > 0.0:
                norms = _np.linalg.norm(m, axis=1)
                norms[norms == 0.0] = 1.0
                sims = (m @ qv) / (norms * qn)
                for j, i in enumerate(idx):
                    out[i] = float(sims[j])
        return out
    return [(_cosine_sim(query_emb, e) if e else 0.0) for e in embs]


# ── Uç noktalar ───────────────────────────────────────────────────────────────

@router.get("/documents")
async def list_documents(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return {
        "documents": [
            {
                "id": d.id,
                "name": d.name,
                "size": d.size,
                "status": d.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }


@router.post("/documents")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Boş dosya")
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Dosya {config.MAX_UPLOAD_MB}MB sınırını aşıyor")

    # Dosyayı geçici dizine kaydet
    upload_dir = Path(config.DATA_DIR) / "rag_uploads" / str(user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-\.]+", "_", file.filename or "document")
    fpath = upload_dir / safe_name
    fpath.write_bytes(raw)

    doc = Document(
        user_id=user.id,
        name=file.filename or "document",
        size=len(raw),
        path=str(fpath),
        status="processing",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Arka planda işle
    asyncio.create_task(_process_document(doc.id, str(fpath), file.filename or "", raw, user.id))

    return {"id": doc.id, "name": doc.name, "status": "processing"}


async def _process_document(doc_id: int, fpath: str, filename: str, raw: bytes, user_id: int):
    """Metni çıkar → chunklara böl → embed et → DB'ye kaydet."""
    from ..database import engine
    from sqlalchemy.ext.asyncio import AsyncSession as ASession

    async with ASession(engine) as db:
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return

        try:
            doc.status = "processing_text"
            await db.commit()

            # Metin çıkar
            extracted = await asyncio.to_thread(
                files.process_upload, f"rag_user_{user_id}", str(doc_id), filename, raw
            )
            text = extracted.get("text", "")
            # Görselleri metne dök (varsa ve IMAGE_TO_TEXT açıksa)
            image_paths = extracted.get("image_paths", [])
            if config.IMAGE_TO_TEXT and image_paths:
                doc.status = "processing_images"
                await db.commit()
                
                b64s = await asyncio.to_thread(files.load_images_b64, image_paths)
                parts = []
                # Queue slot is needed to prevent concurrent vision model overloading
                async with queue.slot():
                    for i, b in enumerate(b64s, 1):
                        try:
                            desc = await chat.caption_image(b)
                            if desc:
                                parts.append(f"### Görsel {i}\n{desc}")
                        except Exception:
                            continue
                
                if parts:
                    text = (text + "\n\n## Görsellerin metin dökümü\n\n" + "\n\n".join(parts)).strip()

            if not text.strip():
                doc.status = "error"
                await db.commit()
                return

            doc.status = "processing_embeddings"
            await db.commit()

            # Chunk'lara böl
            chunks_text = _split_chunks(text)

            # Embed et — kuyruk slotu İÇİNDE (P2): embedding modeli de GPU
            # kullanır; slot dışında sohbet üretimiyle çekişip ikisini de
            # yavaşlatıyordu. Toplu tek çağrı (bkz. _embed_batch).
            async with queue.slot():
                embeddings = await _embed_batch(chunks_text)

            # Kaydet (embedding JSON olarak kolonda — sqlite-vec'siz fallback)
            for seq, (chunk_text, emb) in enumerate(zip(chunks_text, embeddings)):
                chunk = Chunk(
                    document_id=doc_id,
                    seq=seq,
                    text=chunk_text,
                )
                if emb:
                    chunk.embedding_json = json.dumps(emb)
                db.add(chunk)

            # Görsel limiti aşıldıysa durumu uyarı etiketiyle işaretle
            if len(image_paths) >= config.MAX_IMAGES_PER_FILE:
                doc.status = "ready_warning_images"
            else:
                doc.status = "ready"
            await db.commit()

        except Exception:
            # K3: hata yutulmasın — sebep loglansın (belge adıyla)
            logger.exception("RAG belge işleme hatası (doc_id=%s, name=%s)", doc_id, filename)
            doc.status = "error"
            await db.commit()


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Document).where(Document.id == doc_id, Document.user_id == user.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Belge bulunamadı")
    await db.delete(doc)
    await db.commit()
    return {"deleted": True}


class QueryBody(BaseModel):
    q: str
    doc_ids: list[int] | None = None
    top_k: int = TOP_K


@router.post("/query")
async def query_rag(
    body: QueryBody,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """Sorgu vektörünü oluştur, en yakın chunk'ları döndür."""
    query_emb = await _embed(body.q)

    # Kullanıcının chunk'larını çek
    stmt = (
        select(Chunk, Document.name)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.user_id == user.id, Document.status.in_(["ready", "ready_warning_images"]))
    )
    if body.doc_ids:
        stmt = stmt.where(Document.id.in_(body.doc_ids))
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return {"chunks": []}

    # Skorla: hibrit (anlamsal cosine + sozcuksel keyword) — cosine TOPLU (P1)
    embs: list = []
    for chunk, _dn in rows:
        emb = None
        if query_emb and chunk.embedding_json:
            try:
                emb = json.loads(chunk.embedding_json)
            except Exception:
                emb = None
        embs.append(emb)
    coss = _bulk_cosine(query_emb, embs)

    scored = []
    for (chunk, doc_name), emb, cos in zip(rows, embs, coss):
        kw = _keyword_score(body.q, chunk.text)
        scored.append({
            "text": chunk.text, "doc_name": doc_name,
            "score": _hybrid_score(cos, kw), "cosine": round(cos, 4), "keyword": round(kw, 4),
            "chunk_id": chunk.id, "emb": emb,
        })

    # Over-fetch (top_k*4) sonra MMR ile cesitlilik/rerank.
    # NOT: LLM rerank kaldirildi — kucuk model yuklemesi tek GPU'da ana modeli
    # bosaltiyordu; siralama tamamen yerel hibrit skor + MMR ile yapilir.
    scored.sort(key=lambda x: x["score"], reverse=True)
    prelim = scored[: max(config.RAG_RERANK_CANDIDATES, body.top_k * 4)]
    reranked = _mmr(prelim, body.top_k)
    # emb alanini yanittan cikar (buyuk + gereksiz)
    out = [{k: round(v, 4) if isinstance(v, float) else v
            for k, v in c.items() if k != "emb"} for c in reranked]
    return {"chunks": out}
