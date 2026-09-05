"""Ollama streaming chat entegrasyonu + kayan pencere (canli <think> ayristirma dahil)."""
import json
import re
import time
from typing import AsyncGenerator

import httpx

from . import config
from .services import windowing
from .services.text_utils import estimate_tokens


class OllamaError(Exception):
    pass


def _strip_thinking(text: str) -> str:
    """qwen3 gibi 'dusunme' modellerinin <think>...</think> blogunu nihai yanittan ayiklar.
    Bu blok arayuzde bos/karisik gorunume yol acabiliyor; sadece nihai cevap saklanir."""
    if "<think>" in text:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # kapali bloklar
        text = re.sub(r"<think>.*$", "", text, flags=re.S)          # kapanmamis (yarim) blok
    return text.strip()


# Hangi modellerin Ollama "think" alanini destekledigi onbelleklenir. Desteklemeyen
# modele think alani gonderilirse Ollama 400 doner (orn. qwen3-coder:30b).
# P5: TTL'li — model guncellenirse/degistirilirse bilgi bayatlamasin.
_THINK_SUPPORT_CACHE: dict[str, tuple[bool, float]] = {}
_THINK_CACHE_TTL = 600.0  # saniye


def invalidate_think_cache(model: str | None = None) -> None:
    """Model silme/guncelleme sonrasi onbellegi temizle (None = hepsi)."""
    if model is None:
        _THINK_SUPPORT_CACHE.clear()
    else:
        _THINK_SUPPORT_CACHE.pop(model, None)


async def _model_supports_thinking(model: str) -> bool:
    now = time.monotonic()
    hit = _THINK_SUPPORT_CACHE.get(model)
    if hit is not None and (now - hit[1]) < _THINK_CACHE_TTL:
        return hit[0]
    supported = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # "model" yeni, "name" eski Ollama surumlerinin bekledigi anahtar —
            # ikisini birden gonder ki surumden bagimsiz calissin.
            r = await client.post(f"{config.OLLAMA_HOST}/api/show",
                                  json={"model": model, "name": model})
            if r.status_code == 200:
                caps = r.json().get("capabilities", []) or []
                supported = "thinking" in caps
    except Exception:
        supported = False
    _THINK_SUPPORT_CACHE[model] = (supported, now)
    return supported


# Tool (function-calling) destegi de ayni sekilde onbelleklenir. Katalogda
# kaydi olmayan yeni indirilen modeller icin canli sorgu tek guvenilir kaynak.
_TOOLS_SUPPORT_CACHE: dict[str, tuple[bool, float]] = {}


async def model_supports_tools(model: str) -> bool:
    """Modelin Ollama'da tools (function calling) destegini dondurur (TTL onbellek).

    /api/show 'capabilities' listesinde 'tools' varsa ya da chat sablonunda
    {{.Tools}} blogu varsa destekli sayilir. Ollama erisilemezse False doner
    (cagiran taraf katalog bilgisini oncelikli kullanir).
    """
    now = time.monotonic()
    hit = _TOOLS_SUPPORT_CACHE.get(model)
    if hit is not None and (now - hit[1]) < _THINK_CACHE_TTL:
        return hit[0]
    supported = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{config.OLLAMA_HOST}/api/show",
                                  json={"model": model, "name": model})
            if r.status_code == 200:
                data = r.json()
                caps = data.get("capabilities", []) or []
                tmpl = data.get("template", "") or ""
                supported = ("tools" in caps) or ("{{.Tools}}" in tmpl) \
                    or ("{{ .Tools }}" in tmpl) or ("{{- .Tools" in tmpl)
    except Exception:
        supported = False
    _TOOLS_SUPPORT_CACHE[model] = (supported, now)
    return supported


class ThinkSplitter:
    """Content akisindaki <think>...</think> bloklarini CANLI olarak ayirir.

    Bazi modeller / Ollama surumleri "thinking" alanini desteklemez ve dusunme
    metnini dogrudan content icine <think> etiketiyle gomer. Bu sinif, chunk
    sinirlarina bolunmus etiketleri de dogru yakalayarak akisi (dusunme, icerik)
    ciftlerine ayirir; boylece UI dusunme surecini ayri panelde canli gosterebilir.
    """

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self):
        self._buf = ""
        self.in_think = False

    @staticmethod
    def _partial_tail(s: str, tag: str) -> int:
        """s'nin sonunda tag'in kac karakterlik on-eki var? (yarim etiket bekletme)"""
        for k in range(min(len(s), len(tag) - 1), 0, -1):
            if s.endswith(tag[:k]):
                return k
        return 0

    def feed(self, text: str) -> tuple[str, str]:
        """Yeni chunk'i isler; (thinking_metni, icerik_metni) dondurur."""
        self._buf += text
        think_out: list[str] = []
        content_out: list[str] = []
        while self._buf:
            tag = self.CLOSE if self.in_think else self.OPEN
            out = think_out if self.in_think else content_out
            idx = self._buf.find(tag)
            if idx != -1:
                out.append(self._buf[:idx])
                self._buf = self._buf[idx + len(tag):]
                self.in_think = not self.in_think
            else:
                keep = self._partial_tail(self._buf, tag)
                emit_len = len(self._buf) - keep
                out.append(self._buf[:emit_len])
                self._buf = self._buf[emit_len:]
                break
        return "".join(think_out), "".join(content_out)

    def flush(self) -> tuple[str, str]:
        """Akis bitti — bekletilen kuyrugu bosalt (yarim etiket metin sayilir)."""
        rem, self._buf = self._buf, ""
        if not rem:
            return "", ""
        return (rem, "") if self.in_think else ("", rem)


async def stream_chat(chat: dict, images: list[str] | None = None, gen_options: dict | None = None) -> AsyncGenerator[dict, None]:
    """
    Ollama'dan token token yanit akitir.
    images verilirse (base64 listesi) penceredeki son kullanici mesajina iliştirilir
    (multimodal goruntu analizi).
    Yield edilen olaylar:
      {"type": "delta", "text": "..."}
      {"type": "done", "content": "...", "prompt_tokens": N, "completion_tokens": M}
    Hata olursa OllamaError firlatir.
    """
    # P3: ctx ONCE belirlenir, pencere TEK SEFER kurulur (eskiden num_ctx
    # override'inda build_window iki kez cagriliyordu — ilk hesap boşaydı).
    if gen_options and gen_options.get("num_ctx"):
        ctx = gen_options["num_ctx"]
    elif images:
        # Multimodal turlarda daha kucuk baglam (VRAM) + gorsel token payi ayir
        ctx = config.MULTIMODAL_NUM_CTX
    else:
        ctx = config.NUM_CTX
    if images:
        budget = ctx - config.CTX_RESERVE - len(images) * config.IMAGE_TOKEN_EST
    else:
        budget = ctx - config.CTX_RESERVE
    budget = max(1024, budget)

    messages = windowing.build_window(chat, budget=budget)
    if images:
        for m in reversed(messages):
            if m["role"] == "user":
                m["images"] = images
                break

    options = {"num_ctx": ctx}
    # GPU katman sayisi (num_gpu): dusuk = daha cok RAM'e taşar, VRAM bosalir.
    # Oncelik: gen_options (model katalogu / model bazli otomatik ayar) > config.
    num_gpu = (config.NUM_GPU_MULTIMODAL or config.NUM_GPU) if images else config.NUM_GPU
    if gen_options and gen_options.get("num_gpu"):
        num_gpu = gen_options["num_gpu"]
    if num_gpu > 0:
        options["num_gpu"] = num_gpu

    # Kullanici parametreleri — sadece None olmayanlari uygula
    if gen_options:
        for k in ("temperature", "top_p", "num_predict"):
            if gen_options.get(k) is not None:
                options[k] = gen_options[k]

    model_name = chat.get("model", config.MODEL_NAME)
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "options": options,
        # Ana model bellekte kalsın — varsayılan 5dk sonra boşalır ve her
        # yeni mesaj soğuk başlar (35B için onlarca saniye).
        "keep_alive": config.KEEP_ALIVE,
    }
    if await _model_supports_thinking(model_name):
        payload["think"] = config.ENABLE_THINKING

    full_text = []
    full_thinking = []
    prompt_tokens = 0
    completion_tokens = 0
    splitter = ThinkSplitter()  # content icine gomulu <think> bloklarini canli ayir

    url = f"{config.OLLAMA_HOST}/api/chat"
    timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "replace")
                    raise OllamaError(f"Ollama {resp.status_code}: {body[:200]}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "error" in chunk:
                        raise OllamaError(str(chunk["error"]))
                    msg = chunk.get("message") or {}
                    # Ollama, think:true ile "thinking" alanini content'ten AYRI gonderir
                    # (yeni surumler/uyumlu modeller). Bunu canli, ayri bir olay olarak akit.
                    thinking_delta = msg.get("thinking", "")
                    if thinking_delta:
                        full_thinking.append(thinking_delta)
                        yield {"type": "thinking_delta", "text": thinking_delta}
                    delta = msg.get("content", "")
                    if delta:
                        # Ayri "thinking" alani gelmeyen modellerde dusunme, content
                        # icinde <think>...</think> olarak akar — canli olarak ayristir.
                        tk, ct = splitter.feed(delta)
                        if tk:
                            full_thinking.append(tk)
                            yield {"type": "thinking_delta", "text": tk}
                        if ct:
                            full_text.append(ct)
                            yield {"type": "delta", "text": ct}
                    if chunk.get("done"):
                        prompt_tokens = chunk.get("prompt_eval_count", 0)
                        completion_tokens = chunk.get("eval_count", 0)
                        break
    except httpx.ConnectError:
        raise OllamaError("Ollama'ya baglanilamadi (127.0.0.1:11434 calisiyor mu?)")
    except httpx.ReadTimeout:
        raise OllamaError("Ollama yanit zaman asimina ugradi")

    # Yarim etiket kuyrugu kaldiysa bosalt
    _tk, _ct = splitter.flush()
    if _tk:
        full_thinking.append(_tk)
    if _ct:
        full_text.append(_ct)
        yield {"type": "delta", "text": _ct}

    # Bazi model sablonlari "thinking" alanini desteklemeyip <think> etiketini
    # dogrudan content icine gomebiliyor — guvenlik agi olarak burada da ayikla.
    content = _strip_thinking("".join(full_text))
    yield {
        "type": "done",
        "content": content,
        "thinking": "".join(full_thinking),
        "prompt_tokens": prompt_tokens,
        # eval_count gelmezse tahmine dus
        "completion_tokens": completion_tokens or estimate_tokens(content),
    }


async def run_agent_turn(chat: dict, images: list[str] | None = None,
                         gen_options: dict | None = None,
                         tools: list[dict] | None = None,
                         supports_tools: bool = False,
                         web_hint: str | None = None) -> AsyncGenerator[dict, None]:
    """Hibrit ajan turu (native tool-calling + stream) — token-optimize loopback.

    supports_tools + tools varsa: stream:true + tools ile uretir. Model tool_calls
    isterse REGISTRY uzerinden calistirir, sonuclari role:"tool" mesajlari olarak
    baglama ekler ve donguyu surdurur (en cok TOOLS_MAX_ITERS). Arac istenmezse akan
    yaniti dogrudan dondurur (tek uretim, stream korunur). Son turda araclar kapatilir
    ki model kesin bir yanit uretsin (sonsuz dongu korumasi).

    Token optimizasyonlari:
      * Ayni isim+argumanla tekrar edilen arac cagrilari YENIDEN CALISTIRILMAZ;
        modele kisa "onceki sonucu kullan" notu doner (bos dongu/token israfi onlenir).
      * Her arac sonucu baglama girmeden TOOL_RESULT_MAX_CHARS ile kirpilir.
      * Dongu ilerledikce eski role:"tool" ciktilarindan yalniz en yeni
        TOOL_CONTEXT_KEEP_TURNS adedi tam metin kalir; daha eskileri kisaltilir.
      * web_hint verildiyse son kullanici mesajina kisa bir not eklenir: kullanici
        web aramasini acti -> model ONCE arar; sorguyu model kendisi secer.

    Tutarlilik: ara turlarda ekrana akan metin kaybolmaz — done olayinin
    icerigi TUM turlarin gorunen metinlerinin birlesimidir (gorunen = kalici).

    Tool desteklenmiyorsa dogrudan stream_chat'e duser (eski davranis; web
    butonu aciksa background_task dogrudan DuckDuckGo aramasi yapar).

    Yield: stream_chat ile ayni ('delta','done') + ek olaylar:
      {"type":"tool_call","name","arguments","result","sources"}  (DB kaliciligi + UI)
      {"type":"status",...}
    """
    if not (supports_tools and tools and config.TOOLS_ENABLED):
        async for ev in stream_chat(chat, images=images, gen_options=gen_options):
            yield ev
        return

    from .tools import REGISTRY

    ctx = (gen_options or {}).get("num_ctx") or config.NUM_CTX
    budget = max(1024, ctx - config.CTX_RESERVE)
    convo = windowing.build_window(chat, budget=budget)  # [{role, content}]
    if images:
        for m in reversed(convo):
            if m["role"] == "user":
                m["images"] = images
                break

    # Web arama modu (🌐): ipucu SON kullanici mesajina eklenir. build_window
    # yeni dict'ler urettigi icin bu degisiklik kalici degildir.
    if web_hint:
        for m in reversed(convo):
            if m["role"] == "user":
                m["content"] = m["content"] + "\n\n" + web_hint
                break

    options = {"num_ctx": ctx}
    _num_gpu = config.NUM_GPU
    if gen_options and gen_options.get("num_gpu"):
        _num_gpu = gen_options["num_gpu"]  # model bazli katalog ayari
    if _num_gpu > 0:
        options["num_gpu"] = _num_gpu
    if gen_options:
        for k in ("temperature", "top_p", "num_predict"):
            if gen_options.get(k) is not None:
                options[k] = gen_options[k]

    url = f"{config.OLLAMA_HOST}/api/chat"
    timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
    model = chat.get("model", config.MODEL_NAME)
    max_iters = max(2, config.TOOLS_MAX_ITERS)
    think_supported = await _model_supports_thinking(model)
    seen_calls: set[str] = set()  # dedupe: calistirilan (arac+arguman) imzalari
    # Tum turlarda UI'a akitilan gorunur metin. Nihai kayit BUNLARDIR — aksi
    # halde arac turunda ekranda gorunen ara metin, refetch sonrasi kaybolurdu
    # (gorunen != kalici tutarsizligi).
    turn_texts: list[str] = []

    def _accumulated_content() -> str:
        return _strip_thinking("\n\n".join(t for t in turn_texts if t.strip()))

    for _round in range(max_iters):
        last_round = _round == max_iters - 1
        payload = {"model": model, "messages": convo, "stream": True, "options": options,
                   "keep_alive": config.KEEP_ALIVE}
        if think_supported:
            payload["think"] = config.ENABLE_THINKING
        if not last_round:
            payload["tools"] = tools  # son turda arac sunma -> kesin yanit

        full_text: list[str] = []
        full_thinking: list[str] = []
        tool_calls_acc: list[dict] = []
        prompt_tokens = completion_tokens = 0
        splitter = ThinkSplitter()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        raise OllamaError(f"Ollama {resp.status_code}: {body[:200]}")
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if "error" in chunk:
                            raise OllamaError(str(chunk["error"]))
                        msg = chunk.get("message") or {}
                        tcs = msg.get("tool_calls")
                        if tcs:
                            tool_calls_acc.extend(tcs)
                        thinking_delta = msg.get("thinking", "")
                        if thinking_delta:
                            full_thinking.append(thinking_delta)
                            yield {"type": "thinking_delta", "text": thinking_delta}
                        delta = msg.get("content", "")
                        # NOT: bazi modeller content ile tool_calls'u AYNI
                        # chunk'ta gonderir — `not tcs` kosulu o metni tamamen
                        # dusuruyordu. Content bos degilse her kosulda akit.
                        if delta:
                            # <think> etiketi gomulu gelirse canli ayristir
                            tk, ct = splitter.feed(delta)
                            if tk:
                                full_thinking.append(tk)
                                yield {"type": "thinking_delta", "text": tk}
                            if ct:
                                full_text.append(ct)
                                yield {"type": "delta", "text": ct}
                        if chunk.get("done"):
                            prompt_tokens = chunk.get("prompt_eval_count", 0)
                            completion_tokens = chunk.get("eval_count", 0)
                            break
        except httpx.ConnectError:
            raise OllamaError("Ollama'ya baglanilamadi (127.0.0.1:11434 calisiyor mu?)")
        except httpx.ReadTimeout:
            raise OllamaError("Ollama yanit zaman asimina ugradi")

        _tk, _ct = splitter.flush()
        if _tk:
            full_thinking.append(_tk)
        if _ct:
            full_text.append(_ct)
            yield {"type": "delta", "text": _ct}

        # Bu turun gorunen metnini turna yaz — done icerigi bunlardan kurulur
        if full_text:
            turn_texts.append("".join(full_text))

        if not tool_calls_acc:
            content = _accumulated_content()
            yield {"type": "done", "content": content,
                   "thinking": "".join(full_thinking),
                   "prompt_tokens": prompt_tokens,
                   "completion_tokens": completion_tokens or estimate_tokens(content)}
            return

        # Arac cagrilari -> calistir, baglama ekle, donguyu surdur
        convo.append({"role": "assistant", "content": "".join(full_text),
                      "tool_calls": tool_calls_acc})
        for tc in tool_calls_acc:
            fn = tc.get("function") or {}
            name = fn.get("name")
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            args = args or {}
            # Ozet/duyuru metni: web_search'te sorguyu goster (kullanici ne
            # arandigini canli gorsun), digerlerinde arac adini.
            if name == "web_search":
                _q = str(args.get("query", "")).strip()
                _label = "Web'de aranıyor: " + (_q[:60] or "?")
            else:
                _label = f"Araç çalıştırılıyor: {name}"
            yield {"type": "status", "status": "searching", "message": _label}

            # Dedupe: ayni arac + ayni arguman tekrar geldiyse yeniden
            # calistirma — onceki sonuc zaten baglamda. (Token optimizasyonu;
            # modelin ayni sorguda takilip donguye girmesini keser.)
            key = (name or "") + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)
            sources: list = []
            if key in seen_calls:
                text = ("Bu arac bu oturumda ayni argumanlarla cagrildi; sonucu "
                        "baglamda mevcut. Lutfen onceki sonucu kullan ya da "
                        "farkli bir sorgu/arac dene.")
            else:
                seen_calls.add(key)
                spec = REGISTRY.get(name)
                if spec:
                    try:
                        res = await spec.run(args)
                    except Exception as e:
                        res = f"Arac hatasi: {e}"
                else:
                    res = f"Bilinmeyen arac: {name}"
                if isinstance(res, dict):
                    text = res.get("text", "")
                    sources = res.get("sources", []) or []
                else:
                    text = str(res)
                # Arac ciktisini tavanla — baglam sismezi onler (~token payi).
                _cap = config.TOOL_RESULT_MAX_CHARS
                if len(text) > _cap:
                    text = text[:_cap] + "\n…(araç çıktısı uzun olduğu için kırpıldı)"
            convo.append({"role": "tool", "content": text, "name": name})
            yield {"type": "tool_call", "name": name, "arguments": args,
                   "result": text, "sources": sources}

        # Dongu boyunca biriken ESKI arac ciktilarini kirp: yalniz en yeni
        # TOOL_CONTEXT_KEEP_TURNS sonuc tam metin kalir. KV/prompt buyumesi
        # dogrusal yerine sinirli kalir.
        _tidx = [i for i, m in enumerate(convo) if m.get("role") == "tool"]
        _keep = max(1, config.TOOL_CONTEXT_KEEP_TURNS)
        for i in _tidx[:-_keep]:
            _c = convo[i].get("content") or ""
            if len(_c) > 240:
                convo[i]["content"] = _c[:240] + "\n…(eski araç çıktısı özetlendi)"

    # Buraya normalde gelinmez (son tur araçsiz kesin yanit verir); guvenlik agi:
    # K4 — bos content yerine o ana kadarki TUM gorunen metni dondur; bos yanit
    # background_task'te "Model yanit uretemedi" hatasina donusuyordu.
    _partial = _accumulated_content()
    yield {"type": "done", "content": _partial,
           "thinking": "".join(full_thinking),
           "prompt_tokens": prompt_tokens,
           "completion_tokens": completion_tokens or estimate_tokens(_partial)}



_SUMMARY_SYS = (
    "Sen bir konusma ozetleyicisin. Verilen onceki ozet ve yeni mesajlari, "
    "ileride sohbete devam etmek icin gereken TUM onemli bilgileri (kararlar, "
    "olgular, isimler, tercihler, devam eden gorevler) koruyarak tek, kisa ve "
    "tutarli bir ozette birlestir. Ozeti konusmanin dilinde yaz. Sadece ozeti dondur."
)


async def _generate(messages: list[dict], num_ctx: int, model: str | None = None,
                    num_gpu: int = 0, temperature: float = 0.3) -> str:
    """Streaming olmayan tek seferlik uretim (ozetleme + caption icin).

    HIZ NOTU: Ayni yardimci model DAIMA ayni num_ctx ile cagrilmali
    (config.HELPER_NUM_CTX); options degisirse Ollama runner'i yeniden yukler.
    """
    options = {"num_ctx": num_ctx, "temperature": temperature}
    if num_gpu > 0:
        options["num_gpu"] = num_gpu
    payload = {
        "model": model or config.MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": options,
        "keep_alive": config.HELPER_KEEP_ALIVE,
    }
    url = f"{config.OLLAMA_HOST}/api/chat"
    timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload)
            if r.status_code != 200:
                raise OllamaError(f"Ollama {r.status_code}: {r.text[:200]}")
            data = r.json()
            return (data.get("message") or {}).get("content", "").strip()
    except httpx.ConnectError:
        raise OllamaError("Ollama'ya baglanilamadi")
    except httpx.ReadTimeout:
        raise OllamaError("Uretim zaman asimina ugradi")


async def caption_image(image_b64: str, model: str | None = None) -> str:
    """Tek gorseli ayri kucuk VL modeliyle metne dokar (dusuk VRAM).
    model verilmezse config.CAPTION_MODEL kullanilir (kullanici secebilir)."""
    messages = [{"role": "user", "content": config.CAPTION_PROMPT, "images": [image_b64]}]
    txt = await _generate(messages, config.CAPTION_NUM_CTX,
                          model=model or config.CAPTION_MODEL, num_gpu=config.CAPTION_NUM_GPU)
    return txt[:config.CAPTION_MAX_CHARS]


async def summarize_overflow(chat: dict, force: bool = False) -> tuple[str, int] | None:
    """
    Pencereye sigmayan eski mesajlar icin ozet uretir; depoya YAZMAZ.
    Donus: (ozet, yeni_summarized_count) veya None (gerek yok / uretilemedi).
    force=True: pencere tasmasa bile, en yeni COMPACT_KEEP_RECENT mesaj
    haric tum ozetlenmemis mesajlari ozetler (manuel buton).
    """
    new_sc, to_summarize = windowing.overflow_messages(chat)

    if not to_summarize and force:
        msgs = chat.get("messages", [])
        sc = chat.get("summarized_count", 0)
        start = sc
        if msgs and msgs[0]["role"] == "system" and sc == 0:
            start = 1
        end = max(start, len(msgs) - config.COMPACT_KEEP_RECENT)
        to_summarize = msgs[start:end]
        new_sc = end

    if not to_summarize:
        return None

    prev = chat.get("summary", "")
    lines = []
    if prev:
        lines.append("MEVCUT OZET:\n" + prev + "\n")
    lines.append("YENI MESAJLAR:")
    for m in to_summarize:
        who = {"user": "Kullanici", "assistant": "Asistan", "system": "Sistem"}.get(m["role"], m["role"])
        lines.append(f"{who}: {m['content']}")
    user_prompt = "\n".join(lines)

    # HELPER_NUM_CTX'e sigacak sekilde kirp (~3 karakter/token guvenli pay).
    # Eskiden NUM_CTX (32k) ile cagriliyordu: 7B ozetleyici icin 32k KV cache
    # tahsisi + farkli num_ctx yuzunden her cagrida runner yeniden basliyordu.
    _max_chars = max(4000, (config.HELPER_NUM_CTX - 1024) * 3)
    if len(user_prompt) > _max_chars:
        user_prompt = user_prompt[-_max_chars:]

    summary = await _generate(
        [{"role": "system", "content": _SUMMARY_SYS},
         {"role": "user", "content": user_prompt}],
        num_ctx=config.HELPER_NUM_CTX,
        model=config.SUMMARY_MODEL or None,
    )
    if not summary:
        return None
    return summary, new_sc


# ── Ollama liste sorgulari: kisa TTL onbellek ────────────────────────────────
# Admin paneli /admin/status'u 5 sn'de bir yoklar; her yoklama Ollama'ya 2 istek
# atiyordu. 3 sn'lik onbellek panel icin fark edilmez, yuku yariya indirir.
_MODELS_TTL = 3.0
_models_cache: tuple[float, list[dict]] | None = None
_running_cache: tuple[float, list[dict]] | None = None


async def list_models() -> list[dict]:
    """Ollama'da yuklu modelleri dondurur: [{name, size}] (3sn TTL onbellekli)."""
    global _models_cache
    now = time.monotonic()
    if _models_cache is not None and now - _models_cache[0] < _MODELS_TTL:
        return _models_cache[1]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{config.OLLAMA_HOST}/api/tags")
            r.raise_for_status()
            out = []
            for m in r.json().get("models", []):
                if m.get("name"):
                    out.append({"name": m["name"], "size": m.get("size", 0)})
            out.sort(key=lambda x: x["name"])
            _models_cache = (now, out)
            return out
    except Exception:
        # Ollama erisilemezse UI'yi dusurme — bos liste don
        return []


async def check_model() -> bool:
    """Modelin Ollama'da yuklu olup olmadigini kontrol et (list_models onbellegi)."""
    names = {m["name"] for m in await list_models()}
    return config.MODEL_NAME in names


# ── Plan -> Code delege ───────────────────────────────────────────────────────

CODE_MARKER = "[CODE]"

DELEGATE_SYS = (
    "Kod yazma yetenegin var ama ASIL kodu uzman bir kod modeli yazacak. "
    "Kullanici onemli ya da uzun bir kod isterse soyle yap: once kisa bir plan / "
    "aciklama yaz, sonra YENI SATIRDA tam olarak '[CODE]' yaz ve ardindan ne "
    "yazilacagini net ve eksiksiz tarif et (diller, dosyalar, gereksinimler, "
    "arayuzler). Kodu KENDIN YAZMA, sadece tarifle. Kucuk/onemsiz kod parcaciklari "
    "veya kod disindaki sorular icin '[CODE]' kullanma; normal yanit ver."
)

CODER_SYS = (
    "Sen uzman bir yazilimcisin. Verilen plan ve talebe gore eksiksiz, calisir ve "
    "temiz kod yaz. Gerekli tum dosyalari, kisa bir kullanim/kurulum notuyla birlikte "
    "ver. Kod bloklarini uygun dil etiketleriyle bicimlendir. Gereksiz aciklamadan kacin."
)


def extract_code_request(text: str):
    """Ana model yanitinda '[CODE]' isaretini arar. (plan, spec) veya None doner."""
    idx = text.find(CODE_MARKER)
    if idx == -1:
        return None
    plan = text[:idx].strip()
    spec = text[idx + len(CODE_MARKER):].strip()
    if not spec:
        return None
    return plan, spec


# ── Ollama model yönetimi (admin: durum / indir / sil) ───────────────────────

async def running_models() -> list[dict]:
    """Ollama /api/ps - su an bellekte yuklu modeller (VRAM/size) — TTL onbellekli."""
    global _running_cache
    now = time.monotonic()
    if _running_cache is not None and now - _running_cache[0] < _MODELS_TTL:
        return _running_cache[1]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{config.OLLAMA_HOST}/api/ps")
            r.raise_for_status()
            out = []
            for m in r.json().get("models", []):
                out.append({
                    "name": m.get("name") or m.get("model"),
                    "size": m.get("size", 0),
                    "size_vram": m.get("size_vram", 0),
                    "expires_at": m.get("expires_at"),
                })
            _running_cache = (now, out)
            return out
    except Exception:
        return []


async def delete_model(name: str) -> bool:
    """Ollama /api/delete — yuklu modeli diskten kaldirir."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.request("DELETE", f"{config.OLLAMA_HOST}/api/delete",
                                     json={"model": name})
            if r.status_code == 200:
                invalidate_think_cache(name)  # P5: bayat yetenek bilgisi kalmasin
                return True
            return False
    except Exception:
        return False


async def pull_model_stream(name: str):
    """Ollama /api/pull — indirme ilerlemesini olay olay yield eder."""
    invalidate_think_cache(name)  # P5: guncellenen modelin yetenekleri yeniden sorgulansin
    url = f"{config.OLLAMA_HOST}/api/pull"
    timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json={"model": name, "stream": True}) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise OllamaError(f"pull {resp.status_code}: {body[:200]}")
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
