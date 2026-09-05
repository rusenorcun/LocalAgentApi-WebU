"""Arka plan mesaj üretimi.

SSE bağlantısı kesilse (kullanıcı sekmeyi kapasa) bile üretimi tamamlar ve
sonucu veritabanına kaydeder.  Üretim süreci bir asyncio.Queue üzerinden
event_stream() generatörüne SSE olayları gönderir; generatör kapanınca
queue dinlenmez ama görev kendi DB oturumunu kullanmaya devam eder.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from .. import chat, config
from ..database import Chat, Message, ModelCatalog, async_session_maker
from ..queue_manager import queue
from ..services.text_utils import estimate_tokens as _estimate_tokens
from ..services.text_utils import derive_title as _derive_title
from ..services.compaction import apply_compaction_db as _apply_compaction_db
from ..services.rag_context import build_project_rag_context as _build_project_rag_context
from ..services import live_state
from sqlalchemy import select

log = logging.getLogger(__name__)


class _LiveTee:
    """event_q'yu SSE tuketicisine aktarirken ayni olaylari live_state'e yansitir.

    Boylece SSE baglantisi kopssa bile (baska sekme/refresh) uretimin canli
    durumu GET /chats/{id}/live ucuyla okunabilir kalir.
    """

    __slots__ = ("_q", "_cid")

    def __init__(self, q: asyncio.Queue, chat_id: str):
        self._q = q
        self._cid = chat_id

    async def put(self, item):
        if isinstance(item, dict):
            try:
                live_state.push(self._cid, item)
            except Exception:  # izleme asla uretimi bozmasin
                log.exception("live_state push hatasi")
        await self._q.put(item)

    def __getattr__(self, name):  # task_done/join vb. yok — ilet
        return getattr(self._q, name)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


_TOOL_CTX_MARKS = ("[Araç ", "[WEB ARAMA SONUÇLARI", "[GÖRSEL OKUMA")


def _prune_stale_tool_context(gen_messages: list[dict]) -> None:
    """Onceki turlardan kalma gizli arac/web baglamlarini kirpar (token optimizasyonu).

    Pencerede 'system' rolunde tasinan [Araç ...] / [WEB ARAMA SONUÇLARI...] /
    [GÖRSEL OKUMA...] bloklarindan yalniz en yeni TOOL_CONTEXT_KEEP_TURNS adedi
    tam metin kalir; daha eskiler kisaltilir. Mesaj SILINMEZ, yalnizca icerigi
    kisaltilir -> pencere/kompaktlama index hizasi bozulmaz, DB dokunulmaz.
    """
    keep = max(1, config.TOOL_CONTEXT_KEEP_TURNS)
    idxs = [
        i for i, m in enumerate(gen_messages)
        if m.get("role") == "system"
        and str(m.get("content") or "").startswith(_TOOL_CTX_MARKS)
    ]
    for i in idxs[:-keep]:
        c = str(gen_messages[i].get("content") or "")
        if len(c) > 400:
            gen_messages[i]["content"] = c[:400] + "\n…(eski araç/web bağlamı özetlendi)"


async def cancellable_stream(gen, cancel_event: asyncio.Event):
    """Bir async generatoru, iptal olayina KARSI yarisarak tuketir.

    Olaylari aynen yield eder; cancel_event set olursa None yield edip biter.
    None goruldugunde uretim durdurulmus demektir. finally icinde gen.aclose()
    cagrilir — boylece Ollama'ya acik HTTP stream'i kapanir ve GPU'daki uretim
    GERCEKTEN durur (yalniz UI degil). Token akmayan uzun asamalarda (prompt
    eval, model yukleme) bile iptal aninda tetiklenir.
    """
    cwait = asyncio.ensure_future(cancel_event.wait())
    try:
        while True:
            nxt = asyncio.ensure_future(gen.__anext__())
            done, _ = await asyncio.wait({nxt, cwait}, return_when=asyncio.FIRST_COMPLETED)
            if cwait in done and not nxt.done():
                nxt.cancel()
                try:
                    await nxt
                except BaseException:
                    pass
                yield None
                return
            try:
                ev = nxt.result()
            except StopAsyncIteration:
                return
            yield ev
            if cancel_event.is_set():
                yield None
                return
    finally:
        cwait.cancel()
        try:
            await gen.aclose()
        except BaseException:
            pass


async def run_generation(
    event_q: asyncio.Queue,
    *,
    chat_id: str,
    user_msg_id: int,
    model_to_use: str,
    content: str,
    user_persona: Optional[str],
    use_web: bool,
    web_query: str,
    images: Optional[list],
    gen_options: dict,
    is_first_turn: bool,
    compaction_history: dict,
    chat_snapshot: dict,      # chat_dict: mesaj penceresi (kompaktlama öncesi)
) -> None:
    """Arka planda AI yanıtı üret ve DB'ye kaydet.

    event_q'ya SSE olay dict'leri gönderilir; None sentinel ile tamamlandığını bildirir.
    Kullanıcı bağlantısı kesilse dahi bu coroutine çalışmaya devam eder.
    """
    _slot_acquired = False
    _error_in_slot = False
    # "Durdur" butonu icin iptal olayini kaydet (uretim BASLAMADAN once —
    # kuyrukta beklerken de durdurulabilsin)
    cancel_event = queue.register_cancel(chat_id)
    # Canli durum kaydini ac; tum SSE olaylari buraya da aynalanacak
    live_state.begin(chat_id)
    event_q = _LiveTee(event_q, chat_id)

    try:
        # ── Kuyruk bekleme — pozisyon bildirimiyle ────────────────────────────
        async with queue._lock:
            queue.waiting += 1

        # İlk bildirim: kuyrukta bekleyen varsa hemen haber ver
        if queue.active >= config.MAX_CONCURRENT_GENERATIONS or queue.waiting > 1:
            await event_q.put({"type": "queue", "position": queue.waiting})

        # Semaforu alma görevi ayrı bir task'ta; böylece biz arada position
        # güncellemesi gönderebiliriz.
        _acquire_task = asyncio.ensure_future(queue._sem.acquire())
        try:
            while not _acquire_task.done():
                if cancel_event.is_set():
                    # Kuyrukta beklerken durduruldu — yuva alinmadan cik
                    _acquire_task.cancel()
                    try:
                        await _acquire_task
                    except BaseException:
                        pass
                    if not _acquire_task.cancelled() and _acquire_task.exception() is None:
                        # Yaris: iptalden hemen once yuva alinmisti — geri birak
                        queue._sem.release()
                    await event_q.put({"type": "done"})
                    return
                try:
                    await asyncio.wait_for(asyncio.shield(_acquire_task), timeout=1.0)
                except asyncio.TimeoutError:
                    # Hâlâ bekliyoruz — güncel pozisyonu bildir
                    await event_q.put({"type": "queue", "position": queue.waiting})
        except asyncio.CancelledError:
            _acquire_task.cancel()
            async with queue._lock:
                queue.waiting -= 1
            raise

        # Slot alındı
        async with queue._lock:
            queue.waiting -= 1
            queue.active += 1
        _slot_acquired = True

        # ── Üretim ───────────────────────────────────────────────────────────
        await event_q.put({"type": "start"})

        # Bağımsız DB oturumu — request scope'lu değil
        async with async_session_maker() as db:
            # Chat'i taze yükle
            c_res = await db.execute(select(Chat).where(Chat.id == chat_id))
            c = c_res.scalar_one_or_none()
            if not c:
                await event_q.put({"type": "error", "message": "Sohbet bulunamadı"})
                return

            # Mesajları yükle (aktif yol)
            from ..routers.chats import _active_path as _ap
            all_msgs_res = await db.execute(
                select(Message).where(Message.chat_id == chat_id).order_by(Message.id)
            )
            all_messages = _ap(list(all_msgs_res.scalars().all()))

            gen_messages = list(chat_snapshot["messages"])
            # Onceki turlarin buyuk arac/web ciktilari pencereyi sisirmesin:
            # yalniz en yeni birkaç tanesi tam metin kalir.
            _prune_stale_tool_context(gen_messages)

            # ── 0) Model bazlı otomatik ayarlar (katalog: num_ctx/num_gpu) ──
            # Kullanıcının mesaj bazlı seçimi her zaman önceliklidir.
            try:
                from .model_tuner import model_overrides
                _mc_ctx, _mc_gpu = await model_overrides(db, model_to_use)
                if _mc_ctx and not gen_options.get("num_ctx"):
                    gen_options["num_ctx"] = _mc_ctx
                if _mc_gpu and not gen_options.get("num_gpu"):
                    gen_options["num_gpu"] = _mc_gpu
            except Exception:
                pass

            # ── 1) Kompaktlama — ARTIK YANIT SONRASINA ERTELENIR ────────────
            # Eski davranış: yanıttan ÖNCE küçük modelle özetleme yapılıyordu.
            # Tek GPU'da bu, ana modelin boşaltılıp yeniden yüklenmesi demekti
            # (her turda saniyeler). build_window pencereye sığmayan mesajları
            # zaten dışarıda bıraktığı için üretim özetsiz de doğru çalışır;
            # özet yanıt tamamlandıktan sonra (aşağıda) üretilir.
            from ..services import windowing as _windowing
            _needs_compaction = False
            if config.ENABLE_COMPACTION:
                _, _to_sum = _windowing.overflow_messages(compaction_history)
                _needs_compaction = bool(_to_sum)

            # ── 1b) Sistem promptları ───────────────────────────────────────
            if c.system_prompt and c.system_prompt.strip():
                gen_messages = [
                    {"role": "system", "content": c.system_prompt.strip(),
                     "tokens": 0, "attachments": []},
                ] + gen_messages
            if user_persona and user_persona.strip():
                gen_messages = [
                    {"role": "system", "content": user_persona.strip(),
                     "tokens": 0, "attachments": []},
                ] + gen_messages

            turn_sources: list = []

            # ── Tool desteği ────────────────────────────────────────────────
            # Once model kataloguna bak; kayit yoksa (yeni indirilen model)
            # Ollama /api/show ile CANLI yetenek sorgula (TTL onbellekli).
            supports_tools = False
            try:
                _row = (
                    await db.execute(
                        select(ModelCatalog.supports_tools)
                        .where(ModelCatalog.ollama_name == model_to_use)
                    )
                ).first()
                if _row is not None:
                    supports_tools = bool(_row[0])
                else:
                    supports_tools = await chat.model_supports_tools(model_to_use)
            except Exception:
                pass
            tool_mode = bool(config.TOOLS_ENABLED and supports_tools)
            fallback_web_ctx: Optional[str] = None

            # ── 2) Web araması — SADE ve KESİN ──────────────────────────────
            # İki net kural, ara model YOK (GPU takası yok):
            #   * Tool modu AÇIK   → aramayı ANA MODEL karar verir (native
            #     function calling). Buton açıksa yalnız web_search sunulur +
            #     "önce ara" ipucu; sorguyu ana model kendisi üretir.
            #   * Tool modu KAPALI → buton açıksa kullanıcı metniyle DOĞRUDAN
            #     DuckDuckGo araması yapılıp bağlam son kullanıcı mesajına eklenir.
            from .. import web_search as _web_search
            fallback_web_ctx: Optional[str] = None
            web_hint: Optional[str] = None
            if tool_mode and use_web:
                web_hint = (
                    "[WEB ARAMA TALİMATI] Kullanıcı bu turda web aramasını AÇTI: "
                    "yanıtı vermeden ÖNCE web_search aracını kullanarak güncel "
                    "kaynak topla. Aranacak konuyu/sorguyu kendin belirle "
                    "(kullanıcının dilinde, kısa ve odaklı); tek arama yeterli "
                    "olmazsa farklı bir sorguyla en fazla bir kez daha ara. "
                    "Sonrasında kaynaklara dayalı yanıt ver."
                )
            elif not tool_mode and use_web:
                _query = (web_query or content).strip()[:200]
                await event_q.put({
                    "type": "status", "status": "searching",
                    "message": f"Web'de aranıyor: {_query[:50]}",
                })
                try:
                    _items = await _web_search.ddg_search(_query)
                except Exception:
                    _items = []
                if _items:
                    await event_q.put({
                        "type": "status", "status": "searching",
                        "message": f"{len(_items)} sonuç bulundu, sayfalar okunuyor",
                    })
                    _items = await _web_search.fetch_pages(_items, k=3)
                    turn_sources += [
                        {
                            "title": it.get("title") or it.get("url") or "",
                            "url": it.get("url", ""),
                            "snippet": (it.get("body") or "")[:160],
                        }
                        for it in _items
                    ]
                    final_ctx = (
                        "[WEB ARAMA SONUÇLARI — aşağıdaki güncel bilgiyi kullanarak "
                        "kullanıcının sorusunu kaynak numaralarıyla ([1],[2]) yanıtla]\n"
                        + _web_search.build_context(_query, _items)
                    )
                    if gen_messages and gen_messages[-1]["role"] == "user":
                        gen_messages[-1] = {
                            **gen_messages[-1],
                            "content": gen_messages[-1]["content"] + "\n\n" + final_ctx,
                        }
                    fallback_web_ctx = final_ctx
                    await event_q.put({
                        "type": "status", "status": "success",
                        "message": f"{len(_items)} web kaynağı derlendi",
                    })
                else:
                    await event_q.put({
                        "type": "status", "status": "error",
                        "message": "Web sonucu bulunamadı",
                    })

            # ── 3) Proje RAG bağlamı ────────────────────────────────────────
            try:
                rag_ctx, rag_sources = await _build_project_rag_context(
                    db, chat_id, content
                )
            except Exception:
                rag_ctx, rag_sources = None, []

            if rag_ctx:
                _docs = ", ".join(dict.fromkeys(s["doc_name"] for s in rag_sources))
                await event_q.put({
                    "type": "status", "status": "processing",
                    "message": f"Proje belgeleri tarandı: {_docs}",
                })
                await event_q.put({"type": "sources", "items": rag_sources})
                turn_sources += [
                    {"title": s["doc_name"], "snippet": s.get("snippet", "")}
                    for s in rag_sources
                ]
                # HIZ: RAG bağlamı listenin BAŞINA eklenirse prompt öneki her
                # turda değişir ve Ollama'nın KV/prompt cache'i boşa gider
                # (32k'lık geçmiş her turda yeniden değerlendirilir). Web
                # bağlamı gibi SON kullanıcı mesajına eklenir.
                if gen_messages and gen_messages[-1]["role"] == "user":
                    gen_messages[-1] = {
                        **gen_messages[-1],
                        "content": gen_messages[-1]["content"] + "\n\n" + rag_ctx,
                    }
                else:
                    gen_messages = gen_messages + [
                        {"role": "system", "content": rag_ctx, "tokens": 0, "attachments": []},
                    ]

            # ── 3c) Görseller — TEK KURAL ───────────────────────────────────
            # Seçili model görsel yetenekliyse görseller DOĞRUDAN ona gider.
            # Yetenekli DEĞİLSE görseller TAMAMEN yok sayılır — başka bir
            # görü modelinden özet/okuma üretilip bağlama EKLENMEZ (eski
            # query-read hattı kaldırıldı: sade, net, sürprizsiz).
            if images:
                _model_is_vision = False
                try:
                    _vrow = (
                        await db.execute(
                            select(ModelCatalog.is_vision)
                            .where(ModelCatalog.ollama_name == model_to_use)
                        )
                    ).first()
                    _model_is_vision = bool(_vrow and _vrow[0])
                except Exception:
                    pass
                if not _model_is_vision:
                    images = None  # 400 riski + istenmeyen davranış: hiç gönderme
                    await event_q.put({
                        "type": "status", "status": "error",
                        "message": "Seçili model görsel desteklemiyor — ekli görseller yok sayıldı",
                    })

            # ── 3b) Plan→Code delege ────────────────────────────────────────
            if config.CODER_ENABLED and model_to_use != config.CODER_MODEL:
                gen_messages = [
                    {"role": "system", "content": chat.DELEGATE_SYS,
                     "tokens": 0, "attachments": []},
                ] + gen_messages

            # ── 4) Üretim ───────────────────────────────────────────────────
            if images:
                await event_q.put({
                    "type": "status", "status": "processing",
                    "message": "Görsel(ler) modele iletiliyor",
                })

            # Uzun üretim boyunca DB transaction'ı AÇIK tutma: tüm okumalar
            # bitti — commit ile okuma transaction'ını kapat. (expire_on_commit
            # = False olduğu için `c` nesnesi kullanılabilir kalır; yazımlar
            # akış sonrası yeni kısa bir transaction'da olur.) WAL büyümesi ve
            # dakikalarca açık oturum riski böylece ortadan kalkar.
            await db.commit()

            gen_chat = {
                "id": c.id, "model": model_to_use, "title": c.title,
                "summary": c.summary or "", "summarized_count": c.summarized_count,
                "messages": gen_messages,
            }

            tool_payloads = None
            if tool_mode:
                from ..tools import ollama_tools_payload
                if use_web:
                    # 🌟 Buton acik: yalniz web_search sunulur (odakli, ucuz
                    # arac seti) + "once ara" ipucu. Sorguyu model secer.
                    tool_payloads = ollama_tools_payload(["web_search"])
                    if not tool_payloads:
                        tool_payloads = ollama_tools_payload()
                else:
                    tool_payloads = ollama_tools_payload()

            _gen = (
                chat.run_agent_turn(
                    gen_chat, images=images, gen_options=gen_options or None,
                    tools=tool_payloads, supports_tools=True,
                    web_hint=web_hint,
                )
                if tool_mode
                else chat.stream_chat(gen_chat, images=images, gen_options=gen_options or None)
            )

            done_event = None
            tool_events: list = []
            stopped = False
            # Kismi cikti tamponlari — durdurulursa o ana kadarki metin kaydedilir
            partial_text: list[str] = []
            partial_thinking: list[str] = []
            async for ev in cancellable_stream(_gen, cancel_event):
                if ev is None:          # kullanici durdurdu — Ollama akisi kapatildi
                    stopped = True
                    break
                et = ev["type"]
                if et == "delta":
                    partial_text.append(ev["text"])
                    await event_q.put(ev)
                elif et == "thinking_delta":
                    partial_thinking.append(ev["text"])
                    await event_q.put(ev)
                elif et == "status":
                    await event_q.put(ev)
                elif et == "tool_call":
                    tool_events.append(ev)
                    await event_q.put({"type": "tool", "name": ev.get("name")})
                    _srcs = ev.get("sources") or []
                    turn_sources += [
                        {
                            "title": x.get("title", ""), "url": x.get("url", ""),
                            "snippet": x.get("snippet", ""),
                        }
                        for x in _srcs
                    ]
                    if _srcs:
                        await event_q.put({"type": "sources", "items": _srcs})
                elif et == "done":
                    done_event = ev

            if stopped and not done_event:
                # Durduruldu: o ana kadar akan kismi cikti varsa NORMAL yanit gibi
                # kaydedilsin (baglanti kopmasi dayanikliligiyla ayni davranis).
                _pt = "".join(partial_text).strip()
                _pth = "".join(partial_thinking)
                if not _pt:
                    # Gorunur icerik uretilmemisti — kaydedilecek bir sey yok
                    await event_q.put({
                        "type": "done",
                        "token_count": c.token_count,
                        "max_tokens": config.MAX_CHAT_TOKENS,
                        "title": c.title,
                    })
                    return
                done_event = {
                    "type": "done",
                    "content": _pt,
                    "thinking": _pth,
                    "completion_tokens": _estimate_tokens(_pt),
                }

            if not done_event:
                await event_q.put({
                    "type": "error",
                    "message": "Model yanıt üretemedi.",
                })
                return

            ai_content: str = done_event["content"]
            ai_tokens: int = done_event.get(
                "completion_tokens", _estimate_tokens(ai_content)
            )
            coder_used = model_to_use

            # ── Plan→Code delege: [CODE] varsa koder modeli devreye girer ──
            # (kullanici durdurduysa yeni bir uretim BASLATMA)
            if config.CODER_ENABLED and model_to_use != config.CODER_MODEL and not stopped:
                cr = chat.extract_code_request(ai_content)
                if cr:
                    plan, spec = cr
                    await event_q.put({
                        "type": "status", "status": "processing",
                        "message": "Kod uzmanı (coder) çağrılıyor",
                    })
                    sep = "\n\n---\n\n"
                    await event_q.put({"type": "delta", "text": sep})
                    coder_chat = {
                        "id": c.id, "model": config.CODER_MODEL, "title": c.title,
                        "summary": "", "summarized_count": 0,
                        "messages": [
                            {"role": "system", "content": chat.CODER_SYS},
                            {
                                "role": "user",
                                "content": (
                                    f"Kullanıcı isteği:\n{content}\n\n"
                                    f"Plan:\n{plan}\n\nYazılacak:\n{spec}"
                                ),
                            },
                        ],
                    }
                    coder_text = ""
                    # Koder modeline de katalog ayarlarini uygula (num_ctx/num_gpu)
                    coder_opts: dict = {}
                    try:
                        from .model_tuner import model_overrides as _coder_mo
                        _cc_ctx, _cc_gpu = await _coder_mo(db, config.CODER_MODEL)
                        if _cc_ctx:
                            coder_opts["num_ctx"] = _cc_ctx
                        if _cc_gpu:
                            coder_opts["num_gpu"] = _cc_gpu
                    except Exception:
                        pass
                    try:
                        async for cev in cancellable_stream(
                                chat.stream_chat(coder_chat, gen_options=coder_opts or None),
                                cancel_event):
                            if cev is None:      # koder uretimi sirasinda durduruldu
                                stopped = True
                                break
                            if cev["type"] == "delta":
                                coder_text += cev["text"]
                                await event_q.put(cev)
                            elif cev["type"] == "thinking_delta":
                                await event_q.put(cev)
                    except chat.OllamaError as e:
                        err = f"\n[Kod modeli hatası: {e}]"
                        coder_text += err
                        await event_q.put({"type": "delta", "text": err})
                    plan_clean = (
                        plan or ai_content.split(chat.CODE_MARKER)[0].strip()
                    )
                    ai_content = (plan_clean + sep + coder_text).strip()
                    ai_tokens = _estimate_tokens(ai_content)
                    coder_used = config.CODER_MODEL

            # Boş yanıt koruması
            if not (ai_content or "").strip():
                await event_q.put({
                    "type": "error",
                    "message": (
                        "Model boş yanıt döndürdü. "
                        "Bağlam çok büyük olabilir; tekrar deneyin."
                    ),
                })
                return

            # Otomatik başlık — MODELSIZ: asistan yanıtının ilk anlamlı
            # satırından türetilir (eski hali kucuk model cagirip ana modeli
            # bosaltiyordu). Anlamlı satır cıkmazsa mevcut baslik korunur.
            if is_first_turn:
                _nt = _derive_title(ai_content)
                if _nt:
                    c.title = _nt

            # ── Web/araç bağlamını gizli mesaj olarak kalıcılaştır ───────────
            _last_id = user_msg_id
            if fallback_web_ctx:
                _wm = Message(
                    chat_id=chat_id, role="system", content=fallback_web_ctx,
                    tokens=_estimate_tokens(fallback_web_ctx),
                    hidden=True, kind="web_context",
                    parent_id=_last_id, active=True,
                )
                db.add(_wm)
                await db.flush()
                _last_id = _wm.id

            for _tev in tool_events:
                _res = str(_tev.get("result", ""))
                _tm = Message(
                    chat_id=chat_id, role="system",
                    content=f"[Araç {_tev.get('name')} sonucu]\n{_res}",
                    tokens=_estimate_tokens(_res),
                    tool_calls_json=json.dumps(
                        [
                            {
                                "function": {
                                    "name": _tev.get("name"),
                                    "arguments": _tev.get("arguments", {}),
                                }
                            }
                        ],
                        ensure_ascii=False,
                    ),
                    hidden=True, kind="tool_result",
                    parent_id=_last_id, active=True,
                )
                db.add(_tm)
                await db.flush()
                _last_id = _tm.id

            # ── Asistan mesajını kaydet ──────────────────────────────────────
            ai_msg = Message(
                chat_id=chat_id, role="assistant",
                content=ai_content, tokens=ai_tokens, model=coder_used,
                sources_json=(
                    json.dumps(turn_sources, ensure_ascii=False) if turn_sources else None
                ),
                thinking=(done_event.get("thinking") or None),
                parent_id=_last_id, active=True,
            )
            db.add(ai_msg)
            c.token_count = c.token_count + ai_tokens
            c.updated_at = _now()
            await db.commit()

            await event_q.put({
                "type": "done",
                "token_count": c.token_count,
                "max_tokens": config.MAX_CHAT_TOKENS,
                "title": c.title,
            })

            # ── 5) Ertelenmiş kompaktlama — kullanıcı yanıtını ALDIKTAN sonra ──
            # Özet üretimi (küçük model) artık turun kritik yolunda değil.
            # compaction_history'nin index uzayı, üretim sırasında eklenen
            # mesajlar SONA geldiği için taze aktif yolun öneki ile hizalıdır.
            if _needs_compaction and not stopped:
                try:
                    result = await chat.summarize_overflow(compaction_history)
                    if result is not None:
                        summary, new_sc = result
                        rq2 = await db.execute(
                            select(Message)
                            .where(Message.chat_id == chat_id)
                            .order_by(Message.id)
                        )
                        fresh_path = _ap(list(rq2.scalars().all()))
                        await _apply_compaction_db(db, c, fresh_path, summary, new_sc)
                        await db.commit()
                except Exception:
                    log.warning("Ertelenmiş kompaktlama başarısız", exc_info=True)

    except chat.OllamaError as e:
        _error_in_slot = True
        await event_q.put({"type": "error", "message": str(e)})
    except asyncio.CancelledError:
        # Bu görev iptal edilmemeli — ama olursa sessizce bitir
        pass
    except Exception as e:
        _error_in_slot = True
        log.exception("Arka plan üretim hatası: %s", e)
        await event_q.put({"type": "error", "message": "Sunucu hatası"})
    finally:
        # Canli kaydi kapat — okuyucu "finished" gorup mesajlari tazeleyecek
        live_state.finish(chat_id)
        # Iptal kaydini temizle — sonraki uretim yeni event kaydeder
        queue.clear_cancel(chat_id, cancel_event)
        if _slot_acquired:
            async with queue._lock:
                queue.active -= 1
                if _error_in_slot:
                    queue.errors += 1
                else:
                    queue.completed += 1
            queue._sem.release()
        elif queue.waiting > 0:
            # Slot alınamadan çıkıldıysa waiting sayacını düzelt
            async with queue._lock:
                queue.waiting = max(0, queue.waiting - 1)
        # Sentinel — SSE generatörüne "bitti" sinyali
        await event_q.put(None)
