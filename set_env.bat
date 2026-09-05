@echo off
REM Hazir ayarlar. run.bat bunu otomatik cagirir; elle calistirmaniza gerek yok.

REM Sabit gizli anahtar (uretildi, gizli tutun)
set JWT_SECRET=-lSTt2GCMcCEt8TszD6okl44pqCpTUXe4ryR5g4ls_Jyj433tUh24--FavbB9D4b

REM Sunucu portu (Caddyfile ile ayni)
set PORT=9000

REM Dinlenecek adres: 127.0.0.1 KALMALI. Disariya yalnizca Caddy (443) bakar;
REM FastAPI'ye dis dunyadan dogrudan erisim OLMAMALI.
set HOST=127.0.0.1

REM Refresh cookie Secure bayragi (HTTPS/Caddy arkasinda true)
set COOKIE_SECURE=true

REM Ana model
set MODEL_NAME=qwen3.6:35b-a3b-q4_K_M

REM Hiz/baglam (16GB VRAM icin dengeli)
set NUM_CTX=8192
set MAX_CHAT_TOKENS=250000

REM Gorsel -> metin hatti: gorseller ayri kucuk VL modeliyle metne dokulur,
REM ana modele SADECE metin gider (cokme olmaz). run.bat caption modelini otomatik indirir.
set IMAGE_TO_TEXT=true
set CAPTION_MODEL=qwen3-vl:8b

REM Kayit acik (3 kullaniciyi ekleyince false yapip kapatabilirsiniz)
set ALLOW_REGISTRATION=true
