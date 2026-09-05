# Madde 15 — Native Tool-Calling (Hibrit) + Araç Bağlamının Kalıcılığı

**Durum: 🔵 Planlandı.** İki sorunu tek mimaride çözer:
1. Web aramasının "yapılsın mı?" kararı bugün ayrı bir küçük niyet-modeli (`decide_web_search`) ile veriliyor. Ollama native **tools (function calling)** ile bu kararı esas modelin kendisi verir (arama, hesap, kod vb.).
2. Arama sonuçları yalnız o anlık istek için RAM'de `gen_messages[-1]` içine ekleniyor; **DB'ye yazılmıyor** (`routers/chats.py:615-619`). Sonraki turda model o bilgiyi göremediği için halüsinasyon riski var.

## Temel Karar — Hibrit Mimari
- **Tool esas araçtır.** Model `tools` listesini görür, ne zaman hangi aracı çağıracağına kendi karar verir.
- **Küçük niyet-modeli fallback'tir.** Seçili model tool desteklemiyorsa (`/api/show` yeteneği yok) eski `decide_web_search` yolu devreye girer. Hiçbir model bozulmaz.
- **Her durumda kalıcılık.** Tool çağrısı + sonucu DB'ye `hidden` mesaj olarak yazılır; sonraki turlarda bağlama dahil edilir, UI'da gösterilmez. Fallback yolunda da web bağlamı `hidden`/`kind="web_context"` mesajı olarak yazılır.

> Çünkü tool-calling'in standart mesaj biçimi (`assistant.tool_calls` → `role:"tool"` sonuç) zaten kalıcılığın ta kendisidir. Tek mimari her iki problemi kapatır.

---

## Mevcut Durum (doğrulanmış)
- `server/chat.py`: `decide_web_search` (küçük model niyet), `summarize_search_results`, `stream_chat(chat, images, gen_options)`, `_generate`.
- `server/routers/chats.py` → `send_message` event_stream: kompaktlama → persona → **web araması (RAM, kalıcı değil)** → RAG → delege → üretim → `sources_json` kaydı.
- `turn_sources` zaten `Message.sources_json`'a yazılıyor ama bu sadece UI "Kaynaklar" butonu için metadata; **modele beslenen bağlam değil.**
- `web_search.py`: `ddg_search`, `fetch_pages`, `build_context` hazır — araç çalıştırıcısı olarak yeniden kullanılır.

---

## Aşama 0 — Şema + Yetenek Temeli
**Amaç:** kalıcılık ve tool yeteneği için altyapı.

### 0.1 `Message` şeması (`server/database.py`)
- `hidden: bool` (default `False`) — UI'da gösterilmez, bağlamda kalır.
- `tool_calls_json: Text | None` — asistanın ürettiği araç çağrıları (JSON).
- `kind: str | None` — `"web_context"`, `"tool_result"`, `null` (normal). UI/temizlik için ayrım.

### 0.2 Migrasyon (`alembic/versions/`)
- Yeni revizyon (head'in üstüne), **idempotent** (inspector guard — mevcut desen).
- `messages` tablosuna 3 kolon ekle.

### 0.3 Model yeteneği
- `_MANAGED_CATALOG` modellerine `supports_tools: bool`.
- `init_db` içinde `/api/show` ile `capabilities` okunup backfill (vision flag deseni gibi). `/api/show` erişilemezse güvenli varsayılan (`False`).

### 0.4 Config (`server/config.py`)
- `TOOLS_ENABLED: bool = True`
- `TOOLS_MAX_ITERS: int = 4` (sonsuz döngü koruması)
- `TOOL_PYTHON_ENABLED: bool = False` (kod aracı varsayılan kapalı — güvenlik)
- `TOOL_CONTEXT_KEEP_TURNS: int = 3` (ham tool sonucu kaç tur ham kalsın)

### Doğrulama
- `alembic upgrade head` temiz; `messages.hidden / tool_calls_json / kind` mevcut.
- `import server.main` OK; fresh DATA_DIR init_db OK.

---

## Aşama 1 — Genel Araç Çerçevesi (Tool Registry)
**Amaç:** tek araç değil, genişleyebilir bir kayıt defteri. İleride araç eklemek pipeline'ı değiştirmesin.

### 1.1 `server/tools/__init__.py` (yeni paket)
- `ToolSpec`: `name`, `description`, `parameters` (JSON Schema), `run(args) -> str` (async).
- `REGISTRY: dict[str, ToolSpec]`.
- `ollama_tools_payload()` → Ollama `/api/chat` `tools=[...]` formatı üretir.

### 1.2 İlk araç: `web_search`
- `server/tools/web_search_tool.py`: `args={query}` → `ddg_search` + `fetch_pages` + `build_context`. Sonuç metni döner. Kaynak listesini (`turn_sources`) yan kanaldan toplar.

### 1.3 (Sonraki aşamada) `calculator`, `run_python` aynı arayüze takılır.

### Doğrulama
- `REGISTRY` birim testi; `ollama_tools_payload()` şema doğrulaması.

---

## Aşama 2 — Ajan Döngüsü (chat.py)
**Amaç:** tool destekleyen modelde kararı modele bırak; döngüyle araçları çalıştır.

### 2.1 `run_agent_turn(...)` (stream_chat'i saran katman)
1. `supports_tools` ise mesajlar + `tools` ile **stream'siz** ilk çağrı (karar turu).
2. Yanıt `tool_calls` içeriyorsa: her çağrıyı `REGISTRY[name].run(args)` ile çalıştır → SSE `{"type":"tool","name":...,"status":"running/done"}` → sonucu mesaj listesine `role:"tool"` olarak ekle.
3. `TOOLS_MAX_ITERS`'e kadar tekrar.
4. Model araç istemiyorsa **stream ederek** son yanıtı üret (mevcut `stream_chat`).
- `supports_tools` değilse → mevcut `decide_web_search` fallback yolu (değişmeden).

### 2.2 Toggle anlamı
- Web butonu AÇIK → `web_search` aracını listeye koy (zorla teşvik).
- KAPALI + `WEBSEARCH_AUTO` → aracı yine listeye koy, kararı modele bırak.
- Tamamen araçsız mod gerekirse boş `tools`.

### Doğrulama
- Tek araç çağrılı senaryo testi (mock Ollama). Maks-iter koruması testi. Fallback testi.

---

## Aşama 3 — Kalıcılık (her iki problem burada kapanır)
**Amaç:** tool/web bağlamı DB'ye gizli yazılsın, sonraki turlarda kullanılsın, UI'da görünmesin.

### 3.1 Yazma
- Tool yolunda: asistanın `tool_calls`'lu mesajı (`tool_calls_json`, `hidden=True`) + her `role:"tool"` sonuç mesajı (`kind="tool_result"`, `hidden=True`) DB'ye yazılır.
- Fallback yolunda: web bağlamı tek `hidden=True`, `kind="web_context"` mesajı olarak yazılır (bugünkü RAM-enjeksiyon yerine).
- `sources_json` (tıklanabilir linkler) **aynen korunur** — tamamlayıcı.

### 3.2 Okuma / üretim
- Üretim penceresi (`gen_messages`) DB sırasından kurulduğu için gizli mesajlar **otomatik dahil**.
- `_msg_to_dict` ve `GET /messages`: `hidden=True` olanları **eler** (UI temiz).

### 3.3 Kenar durumlar
- **Kompaktlama:** gizli mesajlar token bütçesine sayılır; eskidiğinde özete iner. `TOOL_CONTEXT_KEEP_TURNS` sonrası ham sonuç özetlenebilir.
- **Edit→truncate:** bir mesajdan yeniden üretirken o noktadan sonraki gizli tool mesajları da silinir (zaman/id ile kesim zaten kapsar — doğrula).
- **Ollama sıra kuralı:** `role:"tool"` mesajı, `tool_calls` içeren asistan mesajından hemen sonra gelmeli; sıralama korunmalı.

### Doğrulama
- **Çok turlu senaryo (kritik):** Tur 1 web araması → Tur 2 "o haberdeki kişinin yaşı?" → model gizli bağlamdan doğru yanıt (halüsinasyon yok).
- UI'da gizli mesajlar görünmez; "Kaynaklar" butonu çalışır.

---

## Aşama 4 — Araç Genişletme
- `calculator` aracı (güvenli ifade değerlendirme — `eval` değil).
- `run_python` aracı: **`TOOL_PYTHON_ENABLED` bayrağı arkasında**, ağsız + zaman aşımlı + geçici dizinde **izole subprocess**. Asla ana süreçte `exec`. İlk sürümde KAPALI.

### Doğrulama
- calculator birim testi. python aracı: timeout/ağ-yok/sandbox kaçış testleri; bayrak kapalıyken çağrılamaz.

---

## Aşama 5 — UI
- Araç etkinliği rozetleri: `{"type":"tool",...}` SSE → MessageList'te "🔧 web_search • hesaplandı" gibi katlanabilir gösterim (mevcut `status` altyapısı).
- "Kaynaklar" butonu korunur. Gizli mesajlar listelenmez.

### Doğrulama
- `npx tsc -b` 0. Araç çağrısında rozet görünür; normal yanıtta görünmez.

---

## Aşama 6 — Son Doğrulama (testler geçse bile)
- `py_compile` + `import server.main` + fresh init_db.
- `alembic upgrade head`; yeni kolonlar mevcut.
- Tool-model + fallback-model iki yol da çalışıyor.
- Çok turlu hafıza senaryosu yeşil.
- `npx tsc -b` 0.
- Geriye dönük: eski sohbetler (gizli mesaj yokken) bozulmadan açılıyor.

---

## Riskler / Notlar
- **Tool desteği değişkenliği:** modele göre kalite farkı → yetenek-kapılı hibrit zorunlu.
- **Stream + tools:** karar turu stream'siz, son yanıt stream'li — en sağlam yol.
- **Token şişmesi:** ham arama metni büyük; saklama politikası (KEEP_TURNS + kompaktlama) şart.
- **Güvenlik:** `run_python` keyfi kod = risk; sandbox + bayrak + varsayılan kapalı.

## Uygulama Sırası (öneri)
Aşama 0 → 1 → 2 → 3 (buraya kadar iki sorun da çözülür) → 4 → 5 → 6. 3. aşama sonunda ana hedefe ulaşılır; 4-5 ilerleyiş.
