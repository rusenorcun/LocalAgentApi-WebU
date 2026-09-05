@echo off
REM ============================================================================
REM  Ollama sunucu hiz ayarlarini KALICI olarak yazar (kullanici ortam degiskeni).
REM  Bu degiskenler OLLAMA'yi baslatan ortamda tanimli olmalidir; Ollama genelde
REM  tepsi uygulamasi olarak actigi icin set_env.bat YETMEZ — setx gerekir.
REM
REM  Bir kez calistirin, sonra Ollama'yi TAMAMEN kapatip yeniden acin
REM  (gorev cubugu simgesi -> Quit Ollama -> tekrar baslat).
REM ============================================================================

REM Flash attention: KV cache hesabini hizlandirir, VRAM kullanimini azaltir.
setx OLLAMA_FLASH_ATTENTION 1

REM KV cache nicemleme: ayni VRAM'e ~2x baglam sigar (q8_0'da kalite kaybi ihmal).
setx OLLAMA_KV_CACHE_TYPE q8_0

REM Ayni anda bellekte tutulabilecek model sayisi (ana + kucuk yardimci model).
setx OLLAMA_MAX_LOADED_MODELS 2

echo.
echo [OK] Ayarlar kullanici ortamina yazildi.
echo.
echo SIMDI YAPIN:
echo   1) Ollama'yi tamamen kapatin (gorev cubugu simgesi -^> Quit Ollama)
echo   2) Ollama'yi yeniden baslatin
echo   3) run.bat ile sunucuyu acin
echo.
echo NOT: Buyuk model hala tasiyorsa NUM_GPU ile temiz CPU offload deneyin
echo      (set_env.bat icine: set NUM_GPU=32 gibi) ve NVIDIA panelinden
echo      "CUDA - Sysmem Fallback Policy = Prefer No Sysmem Fallback" secin.
pause
