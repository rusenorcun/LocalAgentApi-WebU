# Proje İnceleme Raporu — Güvenlik, Mantık, Performans

Tarih: 2026-07-03 · Kapsam: `server/` (FastAPI + Ollama) ve `web/` (React/Vite)

Öncelik etiketleri: 🔴 Kritik · 🟠 Yüksek · 🟡 Orta · 🔵 Düşük/İyileştirme

---

## 1. Güvenlik

### 🔴 G1 — İki paralel kimlik doğrulama sistemi aynı anda açık
`server/main.py`, eski v1 uçlarını hâlâ mount ediyor: `/api/register`, `/api/login`, `/api/me`, `/api/admin/settings`, `/api/admin/users`, `/api/admin/users/{t}/admin`. Bunlar `server/auth.py` + JSON `storage`'ı kullanıyor; v2 ise `auth_v2.py` + SQLite kullanıyor. İki sistemin güvenlik seviyesi çok farklı:

- v1 login: **hesap kilitleme yok** (brute-force serbest), **7 günlük access token**, refresh/iptal yok, **kullanıcı enumerasyonu** var (kullanıcı yoksa hash yapmadan hızlı 401 döner → zamanlama sızıntısı).
- v1 `/api/register` `ALLOW_REGISTRATION=true` iken **yeni bir `users.json` yaratır ve ilk kullanıcıyı admin yapar** — v2 DB'den, Argon2'den, kilitlemeden tamamen bağımsız bir admin dünyası. `migrate_json` eski `users.json`'u silmeyip yalnızca arşive *kopyalıyor*, yani dosya yeniden oluşabiliyor.
- v1 admin uçları `storage.is_admin` (JSON) + `ADMIN_USERS` env'ine bakıyor; v2 admin ise `role` kolonuna. İki ayrı yetki kaynağı = tutarsız yetkilendirme.

**Öneri:** v1 auth ve admin uçlarını tamamen kaldır (veya en azından router'ı mount etme). Tek kaynak v2 olmalı. `main.py`'de sadece SPA fallback + health kalsın.

### 🔴 G2 — Access token `localStorage`'da tutuluyor (XSS'e açık)
`web/src/store/authStore.ts` `accessToken`'ı `persist` ile `localStorage`'a yazıyor. Herhangi bir XSS (ya da kötü niyetli bir bağımlılık) token'ı çalabilir. Refresh token httpOnly cookie'de olması iyi, ama access token bellek dışına çıkmamalı.

**Öneri:** access token'ı yalnızca bellekte (React state / zustand non-persist) tut; sayfa yenilenince `/refresh` ile yeniden al. `partialize`'dan `accessToken`, `username`, `role`'ü çıkar.

### 🟠 G3 — `X-Forwarded-For` körlemesine güveniliyor
`routers/auth.py::_client_ip` XFF başlığının **ilk** değerini alıyor. İstemci bu başlığı kendisi gönderebilir; Caddy arkasında bile saldırgan sahte bir XFF ekleyip audit loglarını zehirleyebilir, hesap kilitleme/rate-limit mantığını atlatabilir (her istekte farklı sahte IP).

**Öneri:** Caddy'nin eklediği gerçek istemci IP'sine güven. Ya `request.client.host`'u kullan (Caddy'den geliyor), ya da yalnızca güvenilen proxy'den gelen XFF'in *son* hop'unu al ve `trusted proxies` doğrula.

### 🟠 G4 — Rate limit anahtarı proxy arkasında çöküyor
`security.py` `limiter = Limiter(key_func=get_remote_address)`. Caddy arkasında tüm istekler `127.0.0.1`'den görünür → **tüm kullanıcılar tek bir rate-limit kovasını paylaşır**. Bir kullanıcı limiti doldurunca herkes 429 alır (DoS), ya da tersine kişi başı limit anlamsızlaşır.

**Öneri:** `key_func`'ı güvenilir XFF/gerçek IP'yi döndürecek şekilde özelleştir (G3 ile birlikte).

### 🟠 G5 — FTS arama gizli/sistem mesajlarını sızdırıyor
`routers/chats.py::search_chats` `messages_fts` üzerinde arıyor ama trigger'lar **tüm** mesajları (hidden `web_context`, `tool_result`, `**Sistem Özeti**`, RAG bağlamı) indeksliyor. Arama sonucu snippet'i bu iç bağlamı kullanıcıya gösterebilir.

**Öneri:** FTS sorgusuna `AND m.hidden = 0 AND m.role IN ('user','assistant')` filtresi ekle; ya da FTS trigger'ında hidden mesajları indeksleme.

### 🟡 G6 — bcrypt 72-bayt sessiz kırpma (v1)
v1 `auth.py::hash_password` bcrypt kullanıyor; 72 bayttan uzun parolalar sessizce kırpılır → aynı 72-bayt önekine sahip farklı parolalar eşdeğer olur. v2 Argon2 bundan etkilenmez. G1 çözülürse bu da kapanır.

### 🟡 G7 — Canlı ayarlarda üst sınır doğrulaması yok
`settings.update` `EDITABLE` anahtarlarını `_coerce` ile dönüştürüyor ama değer aralığı kontrolü yok. Admin `NUM_CTX`/`MULTIMODAL_NUM_CTX`'i uçuk bir değere çekince Ollama runner OOM ile çökebilir, `MAX_CHAT_TOKENS` mantıksız olabilir.

**Öneri:** Her anahtar için `min/max` sınırı tanımla ve `_coerce`'te clamp et.

### 🟡 G8 — Refresh "reuse detection" yorumda var, kodda yok
`auth_v2.refresh_tokens` geçersiz token gelince yalnızca audit atıyor; oysa yorum "çalındı tespiti: tüm oturumları iptal et" diyor. Token ailesi (aynı kullanıcının tüm oturumları) iptal edilmiyor → çalınmış refresh token tespit edilse bile aktif kalabilir.

**Öneri:** Rotasyonda eski token yeniden kullanılırsa o kullanıcının tüm `Session` kayıtlarını `revoked=True` yap.

### 🔵 G9 — `JWT_SECRET` env verilmezse her başlatmada rastgele
`config.py` `JWT_SECRET = os.getenv(...) or secrets.token_urlsafe(48)`. Env unutulursa yeniden başlatmada tüm access token'lar geçersiz olur (refresh ile toparlanır ama gereksiz kesinti). Prod'da mutlaka sabit secret gerekli — belgede var ama sessizce fallback yapması tehlikeli.

**Öneri:** Prod/`COOKIE_SECURE=true` iken `JWT_SECRET` boşsa başlatmayı hata ile durdur (fail-fast).

---

## 2. Mantık Hataları / Doğruluk

### 🟠 M1 — RAG belge işleme başarısızlığı sessiz ve kalıcı takılıyor
`routers/rag.py::_process_document` `asyncio.create_task` ile fire-and-forget çalışıyor. Sunucu işlem sırasında yeniden başlarsa belge sonsuza dek `processing` durumunda kalır (yeniden tetikleyen mekanizma yok). `except Exception` bloğu `status="error"` yapıyor ama **hata metnini saklamıyor** ve `e` kullanılmıyor (F841). Ayrıca `if len(image_paths) >= MAX_IMAGES_PER_FILE` yorumu "embedding'leri ayrı tabloya kaydet" diyor ama aslında sadece durum etiketi koyuyor — yorum yanıltıcı.

**Öneri:** Başlangıçta `processing*` durumundaki belgeleri `error`'a çek (ya da yeniden kuyruğa al). Hata detayını bir kolona yaz. Yanıltıcı yorumu temizle.

### 🟡 M2 — İki ayrı dosya-işleme hattı; biri bozuk
`server/document_processor.py::process_file`, `files.py`'nin private helper'larını çağırıyor ama `_bytes_to_b64`'ü **import etmeden** kullanıyor (`img = _bytes_to_b64(...)`) → çağrılırsa `NameError`. Bu modül hiçbir yerden kullanılmıyor gibi (grep ile referans yok). Ölü ve hatalı kod.

**Öneri:** `document_processor.py`'yi sil veya `files.process_upload`'a yönlendir. Tek hat kalsın.

### 🟡 M3 — `messages_fts` MATCH ham kullanıcı girdisiyle → FTS sözdizimi hatası
`search_chats` `messages_fts MATCH :q`'ya kullanıcının ham metnini veriyor. İçinde `"`, `*`, `AND`, `(` gibi FTS5 operatörleri olan sorgular ya hata verir ya beklenmedik davranır (500 riski).

**Öneri:** Sorguyu FTS için escape et (kelimeleri `"..."` ile sarıp `*` ekle) veya `try/except`'e al.

### 🟡 M4 — İlk-tur başlık üretimi durdurma davranışını kısmen bozuyor
`background_task` içinde `is_first_turn and not stopped` iyi; ancak `generate_title` ana modelle **ayrı bir eşzamanlı Ollama çağrısı** yapıyor ve bu çağrı kuyruk slotu içinde ama iptal event'ine bağlı değil — kullanıcı durdurduğunda bile (stopped=False iken normal biten turlarda) başlık üretimi turu uzatır. Küçük ama VRAM'de ikinci yükleme yapabilir.

**Öneri:** Başlığı en yeni/en hızlı küçük modelle (SUMMARY_MODEL) üret; ana modelde tutma.

### 🔵 M5 — `_active_path` / branch sıralaması `id`'ye göre
Dallanma "aktif" seçimi `id`'nin en büyüğünü alıyor (`act[-1]`). Kullanıcı eski bir dala geçtikten sonra yeni mesaj eklerse mantık doğru; ama eşzamanlı düzenlemelerde `created_at` yerine `id` kullanımı beklenmedik dal seçebilir. Şu an tek kullanıcı-tek işlem olduğu için düşük risk.

### 🔵 M6 — `estimate_tokens` (~3.5 kr/token) Türkçe'de yanılabilir
Token bütçesi kaba tahmine dayanıyor; Ollama gerçek sayımı `done`'da dönüyor ama pencere kurarken tahmin kullanılıyor. Türkçe/çok-baytlı metinde pencere fazla/az dolabilir. Kabul edilebilir ama biliniyor olsun.

---

## 3. Performans / Optimizasyon

### 🔴 P1 — RAG araması: tüm chunk'lar belleğe, cosine Python'da
`routers/rag.py::query_rag` ve `services/rag_context.py`, kullanıcının/projenin **tüm** chunk'larını çekip her birinin `embedding_json`'unu Python'da parse ediyor ve `_cosine_sim`'i saf Python döngüsüyle hesaplıyor. Belge sayısı arttıkça her sorgu O(n·d) ve yavaş; JSON parse tekrar tekrar yapılıyor.

**Öneri:** `sqlite-vec` (kod yorumlarında zaten hedeflenmiş) veya numpy ile toplu matris çarpımı kullan. En azından embedding'leri numpy `float32` blob olarak sakla, sorgu başında tek `np.dot` yap. Kısa vadede: chunk'ları `numpy` array'e yükleyip vektörize et.

### 🟠 P2 — Embedding'ler seri üretiliyor ve kuyruk slotu dışında
`_embed_batch = [await _embed(t) for t in texts]` → her chunk tek tek, ardışık. Büyük belgede onlarca sıralı Ollama çağrısı. Üstelik embedding üretimi **kuyruk slotu dışında** (`_process_document` yalnızca captioning'i slot içine alıyor) → tek GPU'da sohbet üretimiyle çekişir, ikisini de yavaşlatır.

**Öneri:** Ollama `/api/embed` girdi listesini destekliyor — tek çağrıda toplu embed. Embedding aşamasını da `queue.slot()` içine al (ya da ayrı düşük öncelikli kuyruk).

### 🟠 P3 — `stream_chat` num_ctx override'ında pencere iki kez kuruluyor
`chat.py::stream_chat`, `gen_options.num_ctx` verildiğinde `storage.build_window`'u **iki kez** çağırıyor (önce default budget, sonra override budget). İlk hesap boşa gidiyor. Her mesajda gereksiz iş.

**Öneri:** Budget'i baştan hesapla, `build_window`'u bir kez çağır.

### 🟡 P4 — Admin `list_users` N+1 sorgu
`routers/admin.py::list_users` her kullanıcı için ayrı `COUNT(sessions)` sorgusu atıyor. Kullanıcı sayısı arttıkça N+1.

**Öneri:** Tek `GROUP BY user_id` sorgusuyla aktif oturum sayılarını topla, dict'ten eşle.

### 🟡 P5 — `_model_supports_thinking` / tool-capability önbelleği hiç tazelenmiyor
`_THINK_SUPPORT_CACHE` süresiz. Model güncellenir/değişirse yanlış kalır. Küçük ama admin model kataloğu değişince sürtüşme yaratır.

**Öneri:** TTL'li önbellek veya model sil/güncelle işleminde cache temizliği.

### 🟡 P6 — RAG upload'da dosya tamamen belleğe okunuyor + iki kez saklama
`upload_document` `raw = await file.read()` ile 40MB'a kadar tümünü belleğe alıyor, hem diske yazıyor hem `_process_document`'a `raw`'ı da geçiriyor (ikinci kez `files.process_upload` içinde tekrar diske yazılıyor). Eşzamanlı yüklemede bellek baskısı.

**Öneri:** Streaming okuma veya tek sefer diske yazıp yalnızca path geçir.

### 🔵 P7 — `_mmr` O(n²·k) ve `_cosine_sim` saf Python
Küçük aday setlerinde sorun değil ama `RAG_RERANK_CANDIDATES=16` + MMR ile her seçimde tüm seçilenlerle karşılaştırma. numpy ile ivmelenebilir.

### 🔵 P8 — Frontend: `MessageList` her stream delta'sında tüm listeyi yeniden render
`stream.content` her token'da state güncelliyor ve `AnimatePresence` altındaki tüm mesajlar yeniden değerlendiriliyor. Uzun sohbette akış sırasında CPU artışı. `MessageBubble`'ı `React.memo`'ya alıp streaming balonu ayrı bir bileşene taşımak yardımcı olur.

### 🔵 P9 — `bufferedMarkdown` + rehype-highlight her delta'da tüm içeriği yeniden parse ediyor
Streaming sırasında her token'da tüm markdown yeniden ayrıştırılıp yeniden vurgulanıyor. Uzun kod bloklu yanıtlarda maliyetli. Throttle (örn. 50–80ms) veya son bloğu ayrı render etmek düşünülebilir.

---

## 4. Kod Kalitesi / Bakım

- 🔵 K1 — `document_processor.py` ölü + bozuk (M2). Kaldırılmalı.
- 🔵 K2 — v1 şemaları `main.py`'de (`Credentials`, `NewChat`, `MessageIn`, `ChatPatch`) ve v2 router'larında ayrı ayrı tanımlı; çoğu kullanılmıyor. Temizlenmeli.
- 🔵 K3 — `routers/rag.py::_process_document` `except Exception as e:` içinde `e` kullanılmıyor; hata yutuluyor (loglama yok). En azından `logger.exception`.
- 🔵 K4 — `chat.py::run_agent_turn` son "güvenlik ağı" `yield done content=""` — boş içerik `background_task`'te "Model yanıt üretemedi" hatasına dönüşebilir; nadir ama tool döngüsü tükenince kullanıcı hata görür. Kısmi metni döndürmek daha iyi.
- 🔵 K5 — `settings.EDITABLE`'da `MODEL_NAME` var ama gerçek varsayılan model seçimi büyük ölçüde DB kataloğundan (`is_default`) geliyor; iki kaynak kafa karıştırıcı.
- 🔵 K6 — CSP `style-src 'unsafe-inline'` içeriyor (Tailwind/inline style zorunluluğu). Kabul edilebilir ama not düşülsün; katı CSP hedefleniyorsa nonce'lu stil gerekir.

---

## Özet — Önce Ne Yapılmalı

1. **G1** v1 auth/admin uçlarını kaldır (tek kimlik sistemi).
2. **G2** access token'ı localStorage'dan çıkar.
3. **P1/P2** RAG embedding'i toplu + slot içinde yap, benzerliği vektörize et.
4. **G3/G4** proxy arkasında gerçek IP'ye göre rate-limit ve audit.
5. **G5** FTS aramasında gizli mesajları filtrele.
6. **M1/M2** RAG işleme hatasını görünür kıl; ölü `document_processor.py`'yi sil.

Bu altı madde güvenlik yüzeyini ve en belirgin yavaşlık kaynaklarını büyük ölçüde kapatır.
