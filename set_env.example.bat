@echo off
REM Bu dosyayi "set_env.bat" olarak kopyalayin ve degerleri doldurun.
REM run.bat'tan ONCE calistirin:  call set_env.bat  &&  run.bat

REM Sabit, gizli bir anahtar (asagidakini DEGISTIRIN). Olusturmak icin:
REM   python -c "import secrets; print(secrets.token_urlsafe(48))"
set JWT_SECRET=BURAYA_UZUN_RASTGELE_ANAHTAR

REM Sunucu portu (8000 doluysa degistirin; Caddyfile ile ayni olmali)
set PORT=9000

REM Ana model (ollama list ciktisindaki tam ad)
set MODEL_NAME=qwen3.6:35b-a3b-q4_K_M

REM --- Hiz / baglam (16GB VRAM) ---
REM Metin baglami. Buyuk = daha cok CPU'ya taşar (yavas). 16GB icin 8192-16384 onerilir.
set NUM_CTX=8192

REM --- Hiz: model bellekte kalma suresi (soguk baslatmayi onler) ---
REM Ana model uretim sonrasi bellekte ne kadar kalsin ("-1" = suresiz).
set KEEP_ALIVE=30m
REM Yardimci modeller (ozet/baslik/rerank) icin.
set HELPER_KEEP_ALIVE=10m

REM --- Hiz: otomatik web arama karari (her mesajda kucuk model = yavas) ---
REM false: yalnizca web butonu / '@web' ile arama yapilir (onerilen).
set WEBSEARCH_AUTO=false
REM Web kaynaklarini ana modele vermeden once kucuk modelle ozetle (yavas).
set WEBSEARCH_SUMMARIZE=false

REM --- Hiz: OLLAMA SUNUCUSU ayarlari ---
REM Buradaki "set" komutlari OLLAMA'yi ETKILEMEZ (Ollama tepsi uygulamasi olarak
REM ayri baslar). Kalici olarak yazmak icin BIR KEZ calistirin:
REM     ollama_hiz_ayarlari.bat
REM (OLLAMA_FLASH_ATTENTION=1, OLLAMA_KV_CACHE_TYPE=q8_0,
REM  OLLAMA_MAX_LOADED_MODELS=2 degerlerini setx ile yazar; ardindan
REM  Ollama'yi kapatip yeniden acin.)

REM Buyuk model VRAM'e sigmayip "paylasilan GPU bellegi"ne tasiyorsa: surucu
REM taskmasi yerine TEMIZ CPU offload icin GPU'ya verilecek katman sayisini
REM sabitleyin (deneyerek ayarlanir; 0 = Ollama otomatik).
REM set NUM_GPU=32

REM Sohbet basina saklama siniri
set MAX_CHAT_TOKENS=250000

REM --- Gorsel -> metin (caption) hatti [ONERILEN] ---
REM ACIK: gorseller ayri kucuk VL modeliyle metne dokulur, ana modele SADECE metin gider.
REM Boylece 36B'de vision yuku olmaz, 16GB'da cokme yasanmaz.
set IMAGE_TO_TEXT=true
REM Gorselleri aciklayan kucuk model. ONCE INDIRIN:  ollama pull qwen3-vl:8b
set CAPTION_MODEL=qwen3-vl:8b

REM --- Gorselleri DOGRUDAN ana modele gondermek isterseniz (riskli, 16GB'da cokebilir) ---
REM IMAGE_TO_TEXT=false yapin, sonra asagidakileri ayarlayin:
REM set ENABLE_IMAGE_ANALYSIS=true
REM set MAX_IMAGES_PER_FILE=3
REM set IMAGE_MAX_EDGE=768
REM set MULTIMODAL_NUM_CTX=8192
REM set NUM_GPU_MULTIMODAL=16

REM Kayit acik mi? (3 kullaniciyi ekledikten sonra false yapip kapatabilirsiniz)
set ALLOW_REGISTRATION=false
