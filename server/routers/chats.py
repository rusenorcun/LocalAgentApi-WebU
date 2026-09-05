"""API v2 — Sohbet CRUD + SSE streaming + dosya yükleme.

NOT: `from __future__ import annotations` KULLANMA — slowapi sarmalı
endpoint'lerde FastAPI UploadFile tipini çözemiyor (bkz. rag.py notu).
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import chat, config, files
from ..services import pending_files
from ..auth_v2 import current_user
from ..database import Chat, Message, User, get_session
from ..queue_manager import queue
from ..security import limiter
# Router'dan ayiklanan tek-sorumluluklu yardimcilar (okunabilirlik icin):
from ..services.text_utils import sse as _sse, estimate_tokens as _estimate_tokens
from ..services.compaction import apply_compaction_db as _apply_compaction_db
from ..services.rag_context import build_project_rag_context as _build_project_rag_context

router = APIRouter(prefix="/api/v2/chats", tags=["chats"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Şemalar ───────────────────────────────────────────────────────────────────

class NewChat(BaseModel):
    title: str = Field(default="Yeni sohbet", max_length=120)
    model: Optional[str] = Field(default=None, max_length=120)


class ChatPatch(BaseModel):
    title: Optional[str] = Field(default=None, max_length=120)
    model: Optional[str] = Field(default=None, max_length=120)
    pinned: Optional[bool] = None
    system_prompt: Optional[str] = Field(default=None, max_length=8000)


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=32000)
    override_model: Optional[str] = None
    web_search: bool = False
    edit_message_id: Optional[int] = None  # dal: bu mesajin kardesi olarak ekle
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    num_predict: Optional[int] = Field(default=None, ge=64, le=16384)
    num_ctx: Optional[int] = Field(default=None, ge=1024, le=131072)


# ── Yardımcılar ──────────────────────────────────────────────────────────────

def _chat_to_dict(c: Chat, messages: list[Message] | None = None) -> dict:
    """messages None ise yalnız özet döner. ASYNC NOT: c.messages ilişkisine
    dokunma — lazy-load async oturumda MissingGreenlet hatası fırlatır."""
    d = {
        "id": c.id,
        "title": c.title,
        "model": c.model or config.MODEL_NAME,
        "pinned": c.pinned,
        "token_count": c.token_count,
        "summarized_count": c.summarized_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if messages is not None:
        _path = _active_path(messages)
        _ch = _children_map(messages)
        _items = []
        for _m in _path:
            if getattr(_m, "hidden", False):
                continue
            _sibs = _ch.get(_m.parent_id, [])
            _md = _msg_to_dict(_m)
            _md["parent_id"] = _m.parent_id
            _md["branch_index"] = (_sibs.index(_m) + 1) if _m in _sibs else 1
            _md["branch_count"] = len(_sibs)
            _md["siblings"] = [x.id for x in _sibs]
            _items.append(_md)
        d["messages"] = _items
        d["summary"] = c.summary or ""
        d["system_prompt"] = c.system_prompt or ""
        d["max_tokens"] = config.MAX_CHAT_TOKENS
    return d


def _active_path(msgs: list) -> list:
    """Dallanma agacinda aktif yolu (kok->yaprak) yurur.
    active=kardesler arasinda secili; her dugumde aktif cocuga inilir."""
    children: dict = {}
    for m in msgs:
        children.setdefault(m.parent_id, []).append(m)
    for k in children:
        children[k].sort(key=lambda x: x.id)
    def pick(sibs):
        if not sibs:
            return None
        act = [x for x in sibs if x.active]
        return act[-1] if act else sibs[-1]
    path, seen = [], set()
    cur = pick(children.get(None, []))
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        path.append(cur)
        cur = pick(children.get(cur.id, []))
    return path


def _children_map(msgs: list) -> dict:
    ch: dict = {}
    for m in msgs:
        ch.setdefault(m.parent_id, []).append(m)
    for k in ch:
        ch[k].sort(key=lambda x: x.id)
    return ch


def _msg_to_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "tokens": m.tokens,
        "model": m.model,
        "attachments": m.attachments(),
        "sources": (json.loads(m.sources_json) if m.sources_json else []),
        "thinking": m.thinking or None,
        "ts": m.created_at.isoformat() if m.created_at else None,
    }


# NOT: _sse / _estimate_tokens / _apply_compaction_db / _build_project_rag_context
# artik server/services/ altinda; yukarida import-alias ile baglandi.


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("")
async def list_chats(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Chat)
        .where(Chat.user_id == user.id)
        .order_by(Chat.pinned.desc(), Chat.updated_at.desc())
    )
    chats = result.scalars().all()
    return {"chats": [_chat_to_dict(c) for c in chats]}


@router.post("")
async def create_chat(
    body: NewChat,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    count_result = await db.execute(
        select(func.count()).select_from(Chat).where(Chat.user_id == user.id)
    )
    if (count_result.scalar() or 0) >= config.MAX_CHATS_PER_USER:
        raise HTTPException(status_code=400, detail="Maksimum sohbet sayısına ulaşıldı")

    c = Chat(
        id=str(uuid.uuid4()),
        user_id=user.id,
        title=body.title[:120],
        model=body.model or user.default_model or config.MODEL_NAME,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _chat_to_dict(c)


# ÖNEMLİ: /search, /{chat_id}'den ÖNCE tanımlanmalı; yoksa "search"
# bir chat_id olarak eşleşir ve arama ucu asla çalışmaz.
@router.get("/search")
async def search_chats(
    q: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="En az 2 karakter")
    # FTS5 sorgusunu escape et (M3): ham girdideki ", *, AND, ( gibi FTS
    # operatörleri sözdizimi hatası/beklenmedik davranış yaratır. Her kelime
    # çift tırnağa alınır ve önek araması (*) eklenir.
    words = [w.replace('"', '""') for w in q.split() if w.strip()]
    if not words:
        return {"results": []}
    fts_q = " ".join(f'"{w}"*' for w in words)

    # G5: gizli bağlam mesajları (web_context/tool_result/RAG/sistem özeti)
    # FTS'te indeksli — sonuçlardan filtrelenmezse kullanıcıya iç bağlam sızar.
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    try:
        result = await db.execute(
            text("""
                SELECT m.chat_id, m.content, m.created_at
                FROM messages_fts fts
                JOIN messages m ON m.id = fts.rowid
                JOIN chats c ON c.id = m.chat_id
                WHERE c.user_id = :uid
                  AND m.hidden = 0
                  AND m.role IN ('user', 'assistant')
                  AND messages_fts MATCH :q
                ORDER BY rank
                LIMIT 30
            """),
            {"uid": user.id, "q": fts_q},
        )
        rows = result.fetchall()
    except OperationalError:
        # FTS sözdizimi yine de patlarsa 500 yerine boş sonuç
        return {"results": []}
    return {"results": [
        {"chat_id": r[0], "snippet": r[1][:200], "ts": str(r[2])}
        for r in rows
    ]}


@router.get("/{chat_id}/live")
async def chat_live(
    chat_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """Devam eden üretimin canlı anlık görüntüsü (yeniden giriş senaryosu).

    Kullanıcı üretim sürerken sohbetten çıkıp geri döndüğünde frontend bu ucu
    yoklar; dönen {status, text, thinking, tools...} alanları mevcut akış
    arayüzüne sentetik SSE olayları olarak beslenir. Üretim yoksa
    {"active": false} döner.
    """
    result = await db.execute(
        select(Chat.id).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")

    from ..services import live_state
    return live_state.snapshot(chat_id)


@router.get("/{chat_id}")
async def get_chat(
    chat_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
    # Mesajları ayrı sorguyla yükle (ilişkiye atama YOK — async lazy-load patlar)
    msgs_result = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )
    return _chat_to_dict(c, messages=list(msgs_result.scalars().all()))


@router.patch("/{chat_id}")
async def patch_chat(
    chat_id: str,
    body: ChatPatch,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
    if body.title is not None:
        c.title = body.title[:120]
    if body.model is not None:
        c.model = body.model
    if body.pinned is not None:
        c.pinned = body.pinned
    if body.system_prompt is not None:
        c.system_prompt = body.system_prompt.strip() or None
    c.updated_at = _now()
    await db.commit()
    return _chat_to_dict(c)


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
    await db.delete(c)
    await db.commit()
    # Dangling dosya temizligi: bu sohbete yuklenen dosya/gorseller diskten silinir.
    try:
        import os as _os, shutil as _shutil
        _dir = _os.path.join(str(config.USERS_DIR), user.username, "files", chat_id)
        _shutil.rmtree(_dir, ignore_errors=True)
    except Exception:
        pass
    return {"deleted": True}

@router.post("/batch-summarize")
async def batch_summarize(
    chat_ids: list[str] = Body(..., embed=True),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session)
):
    import uuid
    import json
    # NOT: _estimate_tokens chat.py'de YOK; router'ın kendi modül seviyesindeki
    # _estimate_tokens'ı kullanılır. Buradan yalnızca _generate import edilir.
    from ..chat import _generate, OllamaError
    from ..config import MODEL_NAME

    if not chat_ids:
        raise HTTPException(status_code=400, detail="Sohbet ID listesi boş")

    res = await db.execute(select(Chat).where(Chat.id.in_(chat_ids), Chat.user_id == user.id))
    chats = res.scalars().all()
    if len(chats) != len(chat_ids):
        raise HTTPException(status_code=404, detail="Bazı sohbetler bulunamadı")

    # Her sohbetin özetini topla (özet varsa onu, yoksa son mesajları)
    texts = []
    for c in chats:
        t = (c.summary or "").strip()
        if not t:
            m_res = await db.execute(
                select(Message)
                .where(Message.chat_id == c.id, Message.role.in_(["user", "assistant"]))
                .order_by(Message.created_at.desc())
                .limit(8)
            )
            msgs = list(m_res.scalars().all())
            t = "\n".join(f"{m.role}: {m.content[:400]}" for m in reversed(msgs))
        texts.append(f"### Sohbet: {c.title}\n{t}")

    combined = "\n\n---\n\n".join(texts)
    # Aşırı uzun girdiyi kırp (özetleme num_ctx'ine sığsın)
    MAX_COMBINED = 12000
    if len(combined) > MAX_COMBINED:
        combined = combined[:MAX_COMBINED] + "\n\n[... kırpıldı ...]"

    prompt = (
        "Aşağıda bir veya birden fazla sohbetin özetleri ya da son mesajları var. "
        "Bunları kapsayan; ana konuları, alınan kararları ve önemli ayrıntıları "
        "koruyan tek ve tutarlı bir özet yaz. Başlık ekleme, sadece özet metnini ver.\n\n"
        f"SOHBETLER:\n{combined}"
    )

    try:
        model_name = config.SUMMARY_MODEL or user.default_model or MODEL_NAME
        async with queue.slot():
            ai_content = await _generate(
                messages=[{"role": "user", "content": prompt}],
                num_ctx=config.HELPER_NUM_CTX,
                model=model_name,
            )
    except OllamaError as e:
        raise HTTPException(status_code=502, detail=f"Özetleme modeli hatası: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Özetleme hatası: {e}")

    ai_content = (ai_content or "").strip()
    if not ai_content:
        raise HTTPException(status_code=502, detail="Özet üretilemedi (model boş yanıt döndürdü)")

    if len(chats) == 1:
        title = f"{chats[0].title} Özeti"
    else:
        from datetime import datetime
        dt_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        title = f"{dt_str} Özeti"
    
    from ..database import ChatSummarySnapshot
    snap = ChatSummarySnapshot(
        id=str(uuid.uuid4()),
        user_id=user.id,
        title=title,
        source_chat_ids=json.dumps(chat_ids),
        summary_text=ai_content
    )
    db.add(snap)
    await db.commit()
    
    return {
        "id": snap.id,
        "title": snap.title,
        "summary_text": snap.summary_text,
        "source_chat_ids": snap.source_chat_ids,
        "created_at": snap.created_at
    }

@router.post("/{chat_id}/inject-summary")
async def inject_summary(
    chat_id: str,
    summary_id: str = Body(..., embed=True),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session)
):
    from ..database import ChatSummarySnapshot
    # Sohbet
    c_res = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id))
    c = c_res.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
        
    # Özet
    s_res = await db.execute(select(ChatSummarySnapshot).where(ChatSummarySnapshot.id == summary_id, ChatSummarySnapshot.user_id == user.id))
    s = s_res.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Özet bulunamadı")
        
    pending_files.set(user.username, chat_id, {
        "name": s.title + ".txt",
        "text": s.summary_text,
        "num_images": 0,
        "image_paths": []
    })
    
    return {"name": s.title + ".txt", "num_images": 0}

@router.post("/{chat_id}/inject-document")
async def inject_document(
    chat_id: str,
    document_id: int = Body(..., embed=True),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session)
):
    from ..database import Document, Chunk
    from .. import config
    
    # Sohbet
    c_res = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id))
    if not c_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
        
    d_res = await db.execute(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    doc = d_res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Belge bulunamadı")
        
    # Chunk'lardan text'i birleştir
    ch_res = await db.execute(select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.seq))
    chunks = ch_res.scalars().all()
    text = "\n\n".join(c.text for c in chunks)
    
    pending_files.set(user.username, chat_id, {
        "name": doc.name,
        "text": text[:config.MAX_FILE_TEXT_CHARS],
        "num_images": 0,
        "image_paths": []
    })
    
    return {"name": doc.name, "num_images": 0}


# ── Mesaj streaming ───────────────────────────────────────────────────────────

@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    body: MessageIn,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """Kullanıcı mesajını işleyip yanıtı SSE ile token token akıtır.

    Akış (event_stream içinde, sırasıyla):
      1) Kompaktlama  — pencereye sığmayan eski mesajları özete katla (TEMİZ geçmiş üzerinde).
      2) Web araması  — SADE hat: tool destekli modelde arama kararı + sorguyu
                        ana model verir; desteksiz modelde buton açıksa kullanıcı
                        metniyle doğrudan DuckDuckGo araması yapıp bağlama ekler.
                        Ara/küçük model çağrısı YOK (GPU takası yok).
      3) Proje RAG    — sohbet bir projeye bağlıysa ilgili belge kesitlerini bağlama ekle.
      3b) Delege      — kod isteniyorsa ana modele "[CODE]" talimatı eklenir.
      4) Üretim       — seçili model yanıtı üretir; yanıtta [CODE] varsa kodu CODER_MODEL yazar.

    Yayınlanan SSE olayları: start · status · delta · compacted · done · error.
    Web/RAG bağlamı GEÇİCİDİR (DB'ye yazılmaz); yalnız o turun penceresine eklenir.
    """
    # Sohbet sahiplik kontrolü (başkasının sohbetine erişim engellenir).
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Boş mesaj")

    use_web = False
    web_query = ""
    if body.web_search:
        use_web = True
        web_query = content
    elif content.lower().startswith("@web "):
        use_web = True
        web_query = content[5:].strip()

    if c.token_count + _estimate_tokens(content) > config.MAX_CHAT_TOKENS:
        raise HTTPException(status_code=409, detail="Token limiti doldu. Yeni sohbet açın.")

    # Bekleyen ek (eski storage'dan alınıyor — geçiş dönemi)
    msgs_result = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )
    all_messages = list(msgs_result.scalars().all())
    # Ilk gercek tur mu? (otomatik baslik icin)
    is_first_turn = not any(m.role in ("user", "assistant") for m in all_messages)

    model_to_use = body.override_model or c.model or config.MODEL_NAME

    # ── Pending attachment (yukleme aninda birakilan ek) ───────────────────
    pending = None
    attachments = None
    images = None
    try:
        pending = pending_files.get(user.username, chat_id)
    except Exception:
        pass

    if pending:
        attachments = [{
            "name": pending.get("name", "dosya"),
            "text": pending.get("text", ""),
            "num_images": pending.get("num_images", 0),
        }]
        if config.ENABLE_IMAGE_ANALYSIS:
            # Senkron disk I/O + base64 encode event loop'u bloklamasın
            # (bloklarsa o anda akan TÜM SSE stream'leri donar).
            images = await asyncio.to_thread(
                files.load_images_b64, pending.get("image_paths", [])
            )

    # ── Dallanma: yeni kullanıcı mesajının ebeveyni ──
    # Normalde aktif yolun yaprağına bağlanır. edit_message_id verilirse düzenlenen
    # mesajın KARDEŞİ olarak eklenir → eski dal SİLİNMEZ, pasifleşir (veri kaybı yok).
    parent_for_new = None
    if body.edit_message_id is not None:
        edited = next((m for m in all_messages if m.id == body.edit_message_id), None)
        if edited is not None:
            parent_for_new = edited.parent_id
            _cond = (Message.parent_id.is_(None) if parent_for_new is None
                     else Message.parent_id == parent_for_new)
            await db.execute(update(Message).where(Message.chat_id == chat_id, _cond).values(active=False))
    else:
        _ap0 = _active_path(all_messages)
        parent_for_new = _ap0[-1].id if _ap0 else None

    # Kullanıcı mesajını kaydet (dal düğümü)
    user_msg = Message(
        chat_id=chat_id,
        role="user",
        content=content,
        tokens=_estimate_tokens(content),
        attachments_json=json.dumps(attachments) if attachments else None,
        parent_id=parent_for_new,
        active=True,
    )
    db.add(user_msg)
    c.token_count = c.token_count + user_msg.tokens
    if c.title in (None, "", "Yeni sohbet"):
        c.title = (content.strip().splitlines() or ["Yeni sohbet"])[0][:60]
    c.updated_at = _now()
    await db.commit()
    await db.refresh(user_msg)

    if pending:
        try:
            pending_files.clear(user.username, chat_id)
        except Exception:
            pass

    # ── Üretim penceresi = AKTİF YOL (yeni kullanıcı mesajı dahil) ──
    # Dallanma sonrası modele yalnız seçili dal gider; pasif dallar saklı kalır.
    _rq = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.id)
    )
    all_messages = _active_path(list(_rq.scalars().all()))
    chat_dict = {
        "id": c.id,
        "model": model_to_use,
        "title": c.title,
        "token_count": c.token_count,
        "max_tokens": config.MAX_CHAT_TOKENS,
        "summary": c.summary or "",
        "summarized_count": c.summarized_count,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "tokens": m.tokens,
                "attachments": m.attachments(),
            }
            for m in all_messages
        ],
    }

    # Kompaktlama için TEMİZ geçmiş: RAG/web bağlamı OLMADAN, yeni kullanıcı mesajı
    # dahil. Bu listenin index uzayı `all_messages` ile birebir hizalı olduğundan
    # _apply_compaction_db doğru mesajları siler (eski hata: RAG sistem mesajı +
    # kullanıcı mesajı eklenmiş chat_dict üzerinde özetleme → index kayması).
    compaction_history = {
        "summary": c.summary or "",
        "summarized_count": c.summarized_count,
        "messages": [dict(m) for m in chat_dict["messages"]],
    }

    # Üretim parametreleri — background task'a geçilmeden önce toplanır
    gen_options: dict = {}
    if body.temperature is not None:
        gen_options["temperature"] = body.temperature
    if body.top_p is not None:
        gen_options["top_p"] = body.top_p
    if body.num_predict is not None:
        gen_options["num_predict"] = body.num_predict
    if body.num_ctx is not None:
        gen_options["num_ctx"] = body.num_ctx

    async def event_stream():
        """SSE generatörü: background_task'tan gelen olayları istemciye iletir.

        Kullanıcı bağlantıyı keserse (GeneratorExit / CancelledError) generatör
        durur; arka plan görevi DB'ye yazmaya devam eder.
        """
        from ..services.background_task import run_generation

        _eq: asyncio.Queue = asyncio.Queue()

        # Görev event loop'ta bağımsız çalışır — SSE kapanınca iptal EDİLMEZ
        asyncio.create_task(run_generation(
            _eq,
            chat_id=chat_id,
            user_msg_id=user_msg.id,
            model_to_use=model_to_use,
            content=content,
            user_persona=getattr(user, "persona", None),
            use_web=use_web,
            web_query=web_query,
            images=images,
            gen_options=gen_options,
            is_first_turn=is_first_turn,
            compaction_history=compaction_history,
            chat_snapshot=chat_dict,
        ))

        try:
            while True:
                ev = await _eq.get()
                if ev is None:          # sentinel — görev tamamlandı
                    break
                # compacted olayı gelince frontend için ek status da gönder
                if ev.get("type") == "compacted":
                    yield _sse({"type": "status", "status": "summarizing",
                                "message": "Geçmiş özetlendi"})
                yield _sse(ev)
        except (GeneratorExit, asyncio.CancelledError):
            # İstemci bağlantıyı kesti — arka plan görevi çalışmaya devam eder
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{chat_id}/compact")
async def manual_compact(
    chat_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """Manuel özetleme: en yeni birkaç mesaj hariç geçmişi sürekli özete katar."""
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")

    msgs_result = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )
    all_messages = list(msgs_result.scalars().all())

    chat_dict = {
        "id": c.id, "model": c.model or config.MODEL_NAME,
        "summary": c.summary or "", "summarized_count": c.summarized_count,
        "messages": [{"role": m.role, "content": m.content, "tokens": m.tokens}
                     for m in all_messages],
    }

    async with queue.slot():
        try:
            res = await chat.summarize_overflow(chat_dict, force=True)
        except chat.OllamaError as e:
            raise HTTPException(status_code=502, detail=str(e))

    if res is None:
        return {"compacted": False, "summarized_count": c.summarized_count,
                "detail": "Özetlenecek mesaj yok"}

    summary, new_sc = res
    comp_res = await _apply_compaction_db(db, c, all_messages, summary, new_sc)
    await db.commit()
    return {"compacted": True, "summarized_count": comp_res["summarized_count"], "token_count": comp_res["token_count"]}


@router.post("/{chat_id}/truncate")
async def truncate_chat(
    chat_id: str,
    message_id: int = Body(..., embed=True),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """Verilen mesaji ve sonrasini siler (mesaj duzenle -> yeniden uret akisi icin).
    token_count yeniden hesaplanir. Frontend ardindan duzenlenen icerigi yeni
    mesaj olarak gonderir."""
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
    msgs = list((await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )).scalars().all())
    idx = next((i for i, m in enumerate(msgs) if m.id == message_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    for m in msgs[idx:]:
        await db.delete(m)
    c.token_count = sum(m.tokens for m in msgs[:idx])
    c.updated_at = _now()
    await db.commit()
    return {"deleted": len(msgs) - idx}


@router.post("/{chat_id}/select-branch")
async def select_branch(
    chat_id: str,
    message_id: int = Body(..., embed=True),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """Bir mesaji kardesleri arasinda AKTIF dal yapar (dallanma navigasyonu)."""
    result = await db.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
    m = (await db.execute(
        select(Message).where(Message.id == message_id, Message.chat_id == chat_id)
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Mesaj bulunamadı")
    _cond = (Message.parent_id.is_(None) if m.parent_id is None else Message.parent_id == m.parent_id)
    await db.execute(update(Message).where(Message.chat_id == chat_id, _cond).values(active=False))
    m.active = True
    await db.commit()
    return {"ok": True}


@router.post("/{chat_id}/regenerate")
async def regenerate(
    chat_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """Son asistan yanıtını sil ve aynı geçmişle yeniden üret."""
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")

    msgs_result = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )
    all_messages = list(msgs_result.scalars().all())
    if not all_messages:
        raise HTTPException(status_code=400, detail="Yeniden üretilecek mesaj yok")

    # Son asistan mesajını kaldır (varsa)
    if all_messages[-1].role == "assistant":
        last = all_messages.pop()
        c.token_count = max(0, c.token_count - (last.tokens or 0))
        await db.delete(last)
        await db.commit()

    if not all_messages or all_messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="Son mesaj kullanıcıya ait değil")

    chat_dict = {
        "id": c.id,
        "model": c.model or config.MODEL_NAME,
        "title": c.title,
        "token_count": c.token_count,
        "max_tokens": config.MAX_CHAT_TOKENS,
        "summary": c.summary or "",
        "summarized_count": c.summarized_count,
        "messages": [
            {"role": m.role, "content": m.content,
             "tokens": m.tokens, "attachments": m.attachments()}
            for m in all_messages
        ],
    }

    # Model bazlı otomatik ayarlar (katalog: num_ctx/num_gpu)
    regen_options: dict = {}
    try:
        from ..services.model_tuner import model_overrides
        _mc_ctx, _mc_gpu = await model_overrides(db, c.model or config.MODEL_NAME)
        if _mc_ctx:
            regen_options["num_ctx"] = _mc_ctx
        if _mc_gpu:
            regen_options["num_gpu"] = _mc_gpu
    except Exception:
        pass

    async def event_stream():
        from ..services.background_task import cancellable_stream
        cancel_event = queue.register_cancel(chat_id)
        try:
            async with queue.slot():
                yield _sse({"type": "start"})
                done_event = None
                partial_text: list[str] = []
                partial_thinking: list[str] = []
                async for ev in cancellable_stream(
                        chat.stream_chat(chat_dict, gen_options=regen_options or None),
                        cancel_event):
                    if ev is None:
                        # Durduruldu — kismi cikti varsa normal yanit gibi kaydet
                        _pt = "".join(partial_text).strip()
                        if _pt:
                            done_event = {"type": "done", "content": _pt,
                                          "thinking": "".join(partial_thinking),
                                          "completion_tokens": _estimate_tokens(_pt)}
                        break
                    if ev["type"] == "delta":
                        partial_text.append(ev["text"])
                        yield _sse(ev)
                    elif ev["type"] == "thinking_delta":
                        partial_thinking.append(ev["text"])
                        yield _sse(ev)
                    elif ev["type"] in ("status", "tool"):
                        yield _sse(ev)
                    elif ev["type"] == "done":
                        done_event = ev
                if done_event:
                    ai_content = done_event["content"]
                    ai_tokens = done_event.get("completion_tokens", _estimate_tokens(ai_content))
                    db.add(Message(chat_id=chat_id, role="assistant", content=ai_content,
                                   tokens=ai_tokens, model=c.model or config.MODEL_NAME,
                                   thinking=(done_event.get("thinking") or None)))
                    c.token_count = c.token_count + ai_tokens
                    c.updated_at = _now()
                    await db.commit()
                yield _sse({"type": "done", "token_count": c.token_count,
                            "max_tokens": config.MAX_CHAT_TOKENS, "title": c.title})
        except chat.OllamaError as e:
            yield _sse({"type": "error", "message": str(e)})
        except asyncio.CancelledError:
            raise
        except Exception:
            yield _sse({"type": "error", "message": "Sunucu hatası"})
        finally:
            queue.clear_cancel(chat_id, cancel_event)

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{chat_id}/stop")
async def stop_generation(
    chat_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    """Aktif uretimi GERCEKTEN durdurur.

    Iptal isareti konur; arka plan gorevi Ollama akisini kapatir (GPU'daki uretim
    durur), o ana kadar akan kismi cikti normal yanit gibi DB'ye kaydedilir ve
    kuyruk yuvasi birakilir — varsa siradaki istek hemen baslar.
    """
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
    stopped = queue.request_cancel(chat_id)
    return {"stopped": stopped}


# ── Dosya yukleme ─────────────────────────────────────────────────────────────

@router.post("/{chat_id}/upload")
@limiter.limit("20/minute")
async def upload_file(
    chat_id: str,
    request: Request,
    file: UploadFile = File(...),
    direct_vision: bool = False,
    caption_model: str = "",
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Boş dosya")
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Dosya {config.MAX_UPLOAD_MB}MB sınırını aşıyor")

    async def event_stream():
        import asyncio
        q = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def progress_cb(stage, msg, current=0, total=0):
            asyncio.run_coroutine_threadsafe(
                q.put({"type": "progress", "stage": stage, "message": msg, "current": current, "total": total}),
                loop
            )

        yield _sse({"type": "progress", "stage": "start", "message": "İşlem başlatılıyor..."})

        # Vision modeli doğrudan görsel alıyorsa (direct_vision) Mistral/Tepegöz için
        # daha yüksek çözünürlük + daha çok görsel; aksi halde caption hattı varsayılanları.
        _vmax_edge = config.VISION_MAX_EDGE if direct_vision else None
        _vmax_imgs = config.VISION_MAX_IMAGES if direct_vision else None
        task = asyncio.create_task(
            asyncio.to_thread(
                files.process_upload, user.username, chat_id, file.filename or "dosya", raw, progress_cb,
                max_edge=_vmax_edge, max_images=_vmax_imgs,
            )
        )

        while not task.done():
            try:
                ev = await asyncio.wait_for(q.get(), timeout=0.1)
                yield _sse(ev)
            except asyncio.TimeoutError:
                continue

        try:
            res = task.result()
        except Exception:
            yield _sse({"type": "error", "message": "Dosya işlenemedi"})
            return

        text_content = res["text"]
        image_paths = res["image_paths"]
        captioned = 0
        caption_error = None

        # IMAGE_TO_TEXT acikken gorseller yukleme aninda betimlenir (metin
        # dosya icerigine eklenir). Kapaliysa/direct_vision'da yollar saklanir.
        if config.IMAGE_TO_TEXT and image_paths and not direct_vision:
            yield _sse({"type": "progress", "stage": "caption", "message": "Görseller betimleniyor", "current": 0, "total": len(image_paths)})
            b64s = await asyncio.to_thread(files.load_images_b64, image_paths)
            parts = []
            async with queue.slot():
                for i, b in enumerate(b64s, 1):
                    try:
                        desc = await chat.caption_image(b, model=caption_model or None)
                        if desc:
                            parts.append(f"### Görsel {i}\n{desc}")
                            captioned += 1
                        yield _sse({"type": "progress", "stage": "caption", "message": f"Görsel {i} betimlendi", "current": i, "total": len(b64s)})
                    except chat.OllamaError as e:
                        caption_error = str(e)
                        break
            if parts:
                text_content = (text_content + "\n\n## Görsellerin metin dökümü\n\n" + "\n\n".join(parts)).strip()
            image_paths_to_store = []
        else:
            image_paths_to_store = image_paths

        try:
            pending_files.set(user.username, chat_id, {
                "name": res["name"], "text": text_content,
                "num_images": res["num_images"], "image_paths": image_paths_to_store,
            })
        except Exception:
            pass

        yield _sse({
            "type": "done",
            "result": {
                "name": res["name"],
                "num_images": res["num_images"],
                "captioned": captioned,
                "caption_error": caption_error,
                "mode": ("image_to_text" if (config.IMAGE_TO_TEXT and not direct_vision)
                         else "direct"),
                "text_chars": len(text_content),
                "truncated": res["truncated"],
                "has_text": bool(text_content.strip()),
            }
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{chat_id}/upload")
async def clear_upload(
    chat_id: str,
    user: User = Depends(current_user),
):
    try:
        pending_files.clear(user.username, chat_id)
    except Exception:
        pass
    return {"cleared": True}
