"""Proje bazli RAG baglam derleme.

Sohbet bir projeye bagliysa, projenin belgelerinden kullanici sorusuyla en
ilgili kesimleri getirir ve modele verilecek tek bir baglam metni olusturur.
Embedding/benzerlik yardimcilari mevcut `routers.rag`'tan yeniden kullanilir.

NOT: LLM rerank kaldirildi — sorgu basina kucuk model yuklemesi tek GPU'da
ana modeli bosaltiyordu. Siralama tamamen yerel: hibrit skor + MMR.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Kac kesit ve hangi minimum skor baglama eklensin.
TOP_K = 5
MIN_SCORE = 0.05


async def build_project_rag_context(db: AsyncSession, chat_id: str, query: str) -> tuple[Optional[str], list]:
    """Sohbetin projelerindeki belgelerden ilgili kesimleri getirir (hibrit skor + MMR rerank).

    Donus: (baglam_metni, kaynaklar) — kaynaklar = [{n, doc_name, score, snippet}].
    Proje/belge yoksa veya yeterince ilgili kesit yoksa (None, []).
    """
    # Lazy import: dongusel bagimlilik ve agir modulleri yalniz gerektiginde yukle.
    from ..database import ProjectChat, ProjectDocument, Chunk, Document
    from ..routers.rag import (
        _embed as embed, _bulk_cosine,
        _keyword_score, _hybrid_score, _mmr,
    )
    from .. import config
    import json

    # 1) Sohbet hangi proje(ler)e bagli?
    pc_rows = (await db.execute(
        select(ProjectChat).where(ProjectChat.chat_id == chat_id)
    )).scalars().all()
    if not pc_rows:
        return None, []

    # 2) O projelerin belgeleri.
    proj_ids = [pc.project_id for pc in pc_rows]
    pd_rows = (await db.execute(
        select(ProjectDocument).where(ProjectDocument.project_id.in_(proj_ids))
    )).scalars().all()
    doc_ids = [pd.document_id for pd in pd_rows]
    if not doc_ids:
        return None, []

    # 3) Belgelerin (hazir olanlarin) tum chunk'lari.
    chunk_rows = (await db.execute(
        select(Chunk, Document.name)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Document.id.in_(doc_ids),
            Document.status.in_(["ready", "ready_warning_images"]),
        )
    )).all()
    if not chunk_rows:
        return None, []

    # 4) Hibrit skor (anlamsal cosine + sozcuksel keyword) + emb sakla.
    # Cosine TOPLU hesaplanir (numpy varsa tek matris carpimi — P1).
    query_emb = await embed(query)
    embs: list = []
    for chunk, _dn in chunk_rows:
        emb = None
        if query_emb and chunk.embedding_json:
            try:
                emb = json.loads(chunk.embedding_json)
            except Exception:
                emb = None
        embs.append(emb)
    coss = _bulk_cosine(query_emb, embs)

    scored = []
    for (chunk, doc_name), emb, cos in zip(chunk_rows, embs, coss):
        kw = _keyword_score(query, chunk.text)
        scored.append({"text": chunk.text, "doc_name": doc_name, "emb": emb,
                       "score": _hybrid_score(cos, kw)})

    # 5) Over-fetch + MMR rerank (yerel, modelsiz); esik altindaysa baglam ekleme.
    scored.sort(key=lambda x: x["score"], reverse=True)
    if not scored or scored[0]["score"] <= MIN_SCORE:
        return None, []
    prelim = scored[: max(config.RAG_RERANK_CANDIDATES, TOP_K * 4)]
    reranked = _mmr(prelim, TOP_K)

    # 6) Numarali baglam + kaynak listesi.
    ctx_parts, sources = [], []
    for i, c in enumerate(reranked, 1):
        ctx_parts.append(f"[{i}] {c['doc_name']}\n{c['text']}")
        sources.append({
            "n": i,
            "doc_name": c["doc_name"],
            "score": round(c["score"], 3),
            "snippet": (c["text"][:160] + ("…" if len(c["text"]) > 160 else "")),
        })
    ctx = (
        "Proje Belgeleri (ilgili kesimler). Yaniti bunlara dayandir ve "
        "kaynak numaralariyla ([1], [2]) atif yap:\n\n" + "\n\n---\n\n".join(ctx_parts)
    )
    return ctx, sources
