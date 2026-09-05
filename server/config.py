"""Merkezi ayarlar. Ortam degiskenleriyle override edilebilir."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# Veri klasoru (env ile tasinabilir; varsayilan proje/data)
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
USERS_DIR = DATA_DIR / "users"
USERS_FILE = DATA_DIR / "users.json"
WEB_DIR = BASE_DIR / "web"
# React (Vite) build çıktısı. Varsa SPA buradan servis edilir.
WEB_DIST = WEB_DIR / "dist"

# Klasorlerin var oldugundan emin ol
DATA_DIR.mkdir(parents=True, exist_ok=True)
USERS_DIR.mkdir(parents=True, exist_ok=True)

# --- Ollama ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen3.6:35b-a3b-q4_K_M")

# Ozetleme (sohbet ozeti + otomatik kompaktlama) icin model.
# Bos birakilirsa ana model (MODEL_NAME / kullanici tercihi) kullanilir.
# Kucuk/hizli bir model onerilir (orn. qwen2.5:7b-instruct, qwen3:4b).
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "qwen2.5:7b-instruct")

# RAG icin embedding modeli (Ollama tag'i). Proje belge aramasinda kullanilir;
# silinirse RAG sessizce devre disi kalir (panelde "yardimci" olarak gorunur).
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")

# Kod yazma icin model (gelecekteki plan->code delege + katalog).
CODER_MODEL = os.getenv("CODER_MODEL", "qwen3-coder:30b")
# Plan->code delege: ana model plan yapar, kodu CODER_MODEL yazar.
CODER_ENABLED = os.getenv("CODER_ENABLED", "true").lower() == "true"

# Web aramasi (SADE hatti):
#   * Tool destekli model  → arama karari + sorguyu ANA MODEL verir (native
#     function calling; ayrica ara-model cagrisi YOK).
#   * Tool desteksiz model → buton acikken kullanici metniyle DOGRUDAN
#     DuckDuckGo aramasi yapilir, sonuc baglama eklenir. Ara model yok.
# Eski WEBSEARCH_AUTO / WEBSEARCH_SUMMARIZE / WEBSEARCH_INTENT_MODEL
# kaldirildi (her turda kucuk model yuklenmesi = GPU takasi = yavaslik).

# --- Hız / model yerleşimi ---
# Ollama keep_alive: üretim bitince modelin bellekte ne kadar kalacağı.
# Varsayılan (5m) soğuk başlatmalara yol açar. Ana model için uzun tutun.
# "-1" = süresiz. Örn: "30m", "2h".
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "30m")
# Yardımcı modeller (özet/başlık/rerank/intent) için keep_alive.
HELPER_KEEP_ALIVE = os.getenv("HELPER_KEEP_ALIVE", "10m")
# TÜM yardımcı model çağrılarında TEK sabit num_ctx kullanılır. Aynı model
# farklı num_ctx ile çağrılırsa Ollama runner'ı her seferinde yeniden başlatır
# (model reload = saniyeler). Bu değeri değiştirmeyin ya da hepsinde değiştirin.
HELPER_NUM_CTX = int(os.getenv("HELPER_NUM_CTX", "8192"))

# Modele gonderilen aktif baglam penceresi (GPU'ya gore kalibre).
# 16GB VRAM icin varsayilan 16384: 32k, agirliklari zaten tasan MoE modelde
# KV cache'i buyutup surucu taskmasini (shared GPU memory) agirlastiriyordu.
# OLLAMA_FLASH_ATTENTION=1 + OLLAMA_KV_CACHE_TYPE=q8_0 ile (bkz.
# ollama_hiz_ayarlari.bat) 32k tekrar denenebilir.
NUM_CTX = int(os.getenv("NUM_CTX", "16384"))
# Pencerede yanit uretimi icin ayrilan pay (tokens).
CTX_RESERVE = int(os.getenv("CTX_RESERVE", "2048"))

# Multimodal (gorselli) turlarda DAHA KUCUK baglam: vision encoder VRAM yer,
# buyuk KV cache ile birlikte 16GB'i asip runner cokmesine yol acar.
MULTIMODAL_NUM_CTX = int(os.getenv("MULTIMODAL_NUM_CTX", "8192"))
# Her gorsel icin pencerede ayrilan kaba token payi (vision token'lari).
IMAGE_TOKEN_EST = int(os.getenv("IMAGE_TOKEN_EST", "1300"))

# Toplam GPU VRAM (MB) — model bazli otomatik ayar (model_tuner) icin.
# 0 = nvidia-smi ile otomatik tespit denenir; o da yoksa tuning atlanir.
GPU_VRAM_MB = int(os.getenv("GPU_VRAM_MB", "0"))

# GPU'ya yuklenecek katman sayisi (num_gpu). 0 = Ollama otomatik karar versin.
# DUSURMEK = daha fazla katman RAM'e taşar (yavas ama VRAM'de bosluk acar).
NUM_GPU = int(os.getenv("NUM_GPU", "0"))
# Gorselli turlar icin ayri (daha dusuk) deger: vision encoder'a VRAM bosluk acar.
# 0 = NUM_GPU ile ayni. Cokme yasarsaniz buradan dusurun (orn. 20, 12, 8...).
# NOT: bu deger NUM_GPU'dan farkliysa Ollama her geciste modeli yeniden yukler (yavas).
NUM_GPU_MULTIMODAL = int(os.getenv("NUM_GPU_MULTIMODAL", "0"))

# --- Sohbet saklama ---
# Sohbet basina maksimum saklanan token (disk ust siniri).
MAX_CHAT_TOKENS = int(os.getenv("MAX_CHAT_TOKENS", "250000"))

# --- Auth ---
# Uretimde SABIT bir secret ver! Bos birakilirsa her baslatmada degisir
# ve tum oturumlar gecersiz olur.
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
JWT_ALG = "HS256"
JWT_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "168"))  # 7 gun
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

# Refresh cookie'nin Secure bayragi. HTTPS arkasinda (Caddy) true kalsin.
# Yalnizca yerel HTTP testi icin COOKIE_SECURE=false yapilabilir.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

# G9 — Fail-fast: uretimde (COOKIE_SECURE=true) JWT_SECRET env'siz baslatma
# YASAK. Sessiz rastgele fallback her yeniden baslatmada tum oturumlari
# dusurur ve yanlis guven verir. Yerel test icin COOKIE_SECURE=false yeterli.
if COOKIE_SECURE and not os.getenv("JWT_SECRET"):
    raise RuntimeError(
        "JWT_SECRET tanimli degil! set_env.bat icinde sabit bir deger verin "
        "(olusturmak icin: python -c \"import secrets; print(secrets.token_urlsafe(48))\") "
        "veya yalniz yerel HTTP testi icin COOKIE_SECURE=false yapin."
    )

# Yeni kayitlara izin ver (False yaparsan kapali kayit).
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"

# --- Esyamanlilik ---
# Tek GPU: ayni anda 1 uretim. 3 kullanici icin yeterli.
MAX_CONCURRENT_GENERATIONS = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "1"))

# --- Limitler ---
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "32000"))
MAX_CHATS_PER_USER = int(os.getenv("MAX_CHATS_PER_USER", "200"))

# --- Otomatik kompaktlama (ozetleme) ---
# Pencereye sigmayan eski mesajlar modelle ozetlenip "surekli ozet" olarak tutulur.
ENABLE_COMPACTION = os.getenv("ENABLE_COMPACTION", "true").lower() == "true"
# Ozet icin pencerede ayrilan token payi.
SUMMARY_RESERVE = int(os.getenv("SUMMARY_RESERVE", "1500"))
# Ozetlenirken daima ham birakilacak en yeni mesaj sayisi.
COMPACT_KEEP_RECENT = int(os.getenv("COMPACT_KEEP_RECENT", "4"))

# --- Dosya yukleme / cikarma ---
# Yuklenen ham dosyalar kullanici klasorunde saklanir.
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "40"))
# Cikarilan metinden mesaja eklenecek azami karakter (pencereye sigsin diye).
MAX_FILE_TEXT_CHARS = int(os.getenv("MAX_FILE_TEXT_CHARS", "60000"))
# Dosya basina modele gonderilecek azami gorsel sayisi (16GB VRAM icin dusuk).
MAX_IMAGES_PER_FILE = int(os.getenv("MAX_IMAGES_PER_FILE", "10"))
# Gorsel uzun kenar azami piksel (kucultme).
IMAGE_MAX_EDGE = int(os.getenv("IMAGE_MAX_EDGE", "768"))
# Gomulu gorsellerde bu boyuttan kucukleri atla (logo/ikon eler). Slotlar
# gercek sekil/grafiklere gitsin. Dogrudan yuklenen gorsele uygulanmaz.
MIN_IMAGE_EDGE = int(os.getenv("MIN_IMAGE_EDGE", "96"))
# Vision modeli (Tepegöz/Korkut Ata) DOĞRUDAN görsel aldığında daha yüksek çözünürlük
# ve daha çok görsel gönderilir (caption hattındaki küçültmeye gerek yok).
# Mistral Small 3.1: ~1024px kenar, istem başına 10 görsele kadar.
VISION_MAX_EDGE = int(os.getenv("VISION_MAX_EDGE", "1024"))
VISION_MAX_IMAGES = int(os.getenv("VISION_MAX_IMAGES", "10"))
# PDF sayfasini resme cevirirken DPI.
PDF_RENDER_DPI = int(os.getenv("PDF_RENDER_DPI", "150"))
# Sayfa "metinli" sayilmasi icin asgari karakter (altindaysa sayfa resme cevrilir).
PAGE_TEXT_THRESHOLD = int(os.getenv("PAGE_TEXT_THRESHOLD", "40"))
# Gorsel analizi tamamen kapatmak icin false yapin (sadece metin gonderilir).
# VRAM cokmesi yasarsaniz guvenli kacis yolu.
ENABLE_IMAGE_ANALYSIS = os.getenv("ENABLE_IMAGE_ANALYSIS", "true").lower() == "true"

# --- Gorsel -> metin (caption) hatti ---
# AÇIKSA: yukleme aninda her gorsel AYRI bir kucuk VL modeliyle metne dokulur,
# dosya metniyle birlestirilip tek markdown yapilir. Ana modele SADECE metin gider
# (36B'de vision yuku olmaz -> 16GB'da cokme yok). Onerilen yontem.
IMAGE_TO_TEXT = os.getenv("IMAGE_TO_TEXT", "true").lower() == "true"
# Gorselleri aciklayan kucuk, VRAM'e sigan VL modeli. Once: ollama pull qwen3-vl:8b
CAPTION_MODEL = os.getenv("CAPTION_MODEL", "qwen3-vl:8b")
# Caption turu icin baglam (kucuk).
CAPTION_NUM_CTX = int(os.getenv("CAPTION_NUM_CTX", "4096"))
# Caption modeli icin GPU katman (0 = otomatik). VL kucukse sigar.
CAPTION_NUM_GPU = int(os.getenv("CAPTION_NUM_GPU", "0"))
# Gorsel basina caption metni azami karakter.
CAPTION_MAX_CHARS = int(os.getenv("CAPTION_MAX_CHARS", "4000"))
# Caption istemi (modelden ne istedigimiz).
CAPTION_PROMPT = os.getenv("CAPTION_PROMPT",
    "Bu gorseli ayrintili ve tarafsiz acikla. Icindeki metin, tablo, grafik, "
    "sema, sekil ve onemli detaylari yaz. Yorum katma, sadece icerigi aktar.")

# --- Soruya bagli gorsel okuma (query-aware vision) KALDIRILDI ---
# Yeni kural: ana model gorsel yetenekliyse gorseller dogrudan ona gider;
# degilse gorseller tamamen yok sayilir (baska bir VL modelinden ozet uretilmez).

# --- Dusunme modu (Qwen3 vb. 'reasoning' modeller) ---
# Her zaman ACIK: model nihai cevaptan once <think>...</think> ile akil yurutur.
# Bu adimlar gizlenmez — ayri bir "thinking_delta" akisi olarak arayuze gonderilir
# ki kullanici dusunme surecini canli izleyebilsin (bkz. server/chat.py).
ENABLE_THINKING = os.getenv("ENABLE_THINKING", "true").lower() == "true"

# --- Tool Calling (Agentic) ---
# TOOLS_ENABLED + model destegi varsa: ana model native function-calling ile
# arac kullaniyor; dongu run_agent_turn icinde doner (loopback).
TOOLS_ENABLED = os.getenv("TOOLS_ENABLED", "true").lower() == "true"
# Maks. arac dongusu tur sayisi. Son turda araclarsiz kesin yanit verilir.
TOOLS_MAX_ITERS = int(os.getenv("TOOLS_MAX_ITERS", "4"))
TOOL_PYTHON_ENABLED = os.getenv("TOOL_PYTHON_ENABLED", "false").lower() == "true"
# Dongu icerisinde tam metin tutulacak en yeni arac sonucu sayisi; daha eski
# sonuclar kisaltilir (token optimizasyonu — baglama birikmesin).
TOOL_CONTEXT_KEEP_TURNS = int(os.getenv("TOOL_CONTEXT_KEEP_TURNS", "3"))
# Tek bir arac sonucunun baglama girecek azami karakteri (~4 karakter/token).
TOOL_RESULT_MAX_CHARS = int(os.getenv("TOOL_RESULT_MAX_CHARS", "6000"))

# --- Uzak Ollama proxy (api.rorcun.com/ollama) ---
# Caddy bu alt alan adini FastAPI'ye yonlendirir; FastAPI API key dogrulamasi
# yaptiktan sonra gercek Ollama endpoint'ine proxy yapar. Asla dogrudan Ollama
# disari acilmaz.
OLLAMA_PROXY_DOMAIN = os.getenv("OLLAMA_PROXY_DOMAIN", "api.rorcun.com")
OLLAMA_PROXY_PATH = os.getenv("OLLAMA_PROXY_PATH", "/ollama")
# Uzak baglantilar icin proxy uzerinden gitmeyi zorla. False ise baglantinin
# kendi base_url'i kullanilir (yalnizca guvenli ag/VPN senaryolarinda).
OLLAMA_PROXY_FORCE = os.getenv("OLLAMA_PROXY_FORCE", "true").lower() == "true"

# --- Aider / OpenAI uyumlu uclar (api.rorcun.com/v1) ---
# Aider gibi OpenAI-compatible istemciler https://api.rorcun.com/v1 uzerinden
# baglanir. /v1/models, /v1/chat/completions, /v1/completions ucları
# mevcut Ollama baglantilarini OpenAI formatinda sunar.
AIDER_DEFAULT_MODEL = os.getenv("AIDER_DEFAULT_MODEL", "qwen3-coder:30b")
AIDER_REASONING_MODEL = os.getenv("AIDER_REASONING_MODEL", "gpt-oss:120b")

# --- MCP HTTP relay (mcp/ollama_mcp.py) — panel yonetimi ---
# Panel bu adresteki /healthz ve /mcp uclarini izler, sureci baslatir/durdurur.
# NOT: FastAPI ile relay AYNI makinede/container'da calisir, bu yuzden panel
# gosterimi ve ic saglik kontrolu her zaman MCP_HTTP_HOST (varsayilan 127.0.0.1)
# uzerinden yapilir — bu, relay'in DIS DINLEME adresinden (asagida
# MCP_BIND_HOST) bilerek ayri tutulur.
MCP_HTTP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_HTTP_PORT = int(os.getenv("MCP_PORT", "8765"))
# Relay alt surecinin GERCEKTEN dinleyecegi adres. Windows'ta calistirmada
# 127.0.0.1 (varsayilan MCP_HTTP_HOST) yeterlidir; Docker'da ise container'in
# kendi loopback'i disaridan (host'taki Caddy dahil) erisilemez oldugu icin
# 0.0.0.0 gerekir (bkz. docker-compose.yml). Ayri tutulmasinin nedeni: panel
# gosterimi ve ic saglik kontrolu HER ZAMAN 127.0.0.1 kalsin (0.0.0.0'a
# baglanmak bazi ortamlarda beklenmedik davranabilir / kafa karistirir).
MCP_BIND_HOST = os.getenv("MCP_BIND_HOST", MCP_HTTP_HOST)
# Relay dosyalari: token (.mcp_token) mcp_http_baslat.bat ile AYNI dosyayi
# kullanir — iki yoldan baslansa da anahtar degismez.
MCP_DIR = BASE_DIR / "mcp"
MCP_TOKEN_FILE = MCP_DIR / ".mcp_token"
MCP_LOG_FILE = DATA_DIR / "mcp_server.log"

# --- RAG aday havuzu ---
# LLM rerank KALDIRILDI: her RAG sorgusunda kucuk model yuklemesi tek GPU'da
# ana modeli bosaltip yeniden yukletiyordu (cifte takas). Siralama artik tamamen
# yerel/bedava hibrit skor + MMR ile yapilir (bkz. rag_context._mmr).
# Bu deger yalnizca MMR'in secim yapacagi aday havuzu buyuklugudur.
RAG_RERANK_CANDIDATES = int(os.getenv("RAG_RERANK_CANDIDATES", "16"))
