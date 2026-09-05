@echo off
REM Yerel Ollama Sohbet Sunucusu - tek tikla baslatma
cd /d "%~dp0"

REM Ayarlari yukle (tam yol: bazi ortamlarda gorece "call set_env.bat" bulunamiyor)
if exist "%~dp0set_env.bat" call "%~dp0set_env.bat"

REM Sanal ortam yoksa olustur
if not exist ".venv\Scripts\python.exe" (
  echo [kurulum] sanal ortam olusturuluyor...
  python -m venv .venv
)
call .venv\Scripts\activate.bat

REM Bagimliliklari dogrula; eksikse kur
python -c "import fastapi, uvicorn, httpx, bcrypt, jwt, slowapi, fitz, PIL, markitdown, sqlalchemy, aiosqlite, argon2" 2>nul
if errorlevel 1 (
  echo [kurulum] python bagimliliklari yukleniyor...
  python -m pip install --upgrade pip --quiet
  python -m pip install -r requirements.txt --quiet
)

REM Caption modeli (gorsel -> metin) eksikse otomatik indir
if /I not "%IMAGE_TO_TEXT%"=="true" goto :migrate
if "%CAPTION_MODEL%"=="" set CAPTION_MODEL=qwen3-vl:8b
where ollama >nul 2>nul
if errorlevel 1 goto :migrate
ollama list | findstr /I "%CAPTION_MODEL%" >nul 2>nul
if not errorlevel 1 goto :migrate
echo [kurulum] caption modeli indiriliyor: %CAPTION_MODEL%
ollama pull %CAPTION_MODEL%

:migrate
REM Stale WAL journal dosyalarini temizle
if exist "data\chat.db-journal" del /f "data\chat.db-journal" 2>nul
if exist "data\chat.db-shm"     del /f "data\chat.db-shm" 2>nul
if exist "data\test.db"         del /f "data\test.db" 2>nul
if exist "data\test.db-journal" del /f "data\test.db-journal" 2>nul

REM Mevcut JSON verisi varsa SQLite'a tasI (idempotent)
if exist "data\users.json" (
  echo [migrate] JSON verisi SQLite DB'ye tasiniyor...
  python -m server.migrate_json
)

REM React arayuzu derle:
REM  - web\dist yoksa her zaman
REM  - BUILD=1 verilmisse zorla (frontend kaynaklari degistiyse: set BUILD=1 && run.bat)
if "%BUILD%"=="1" goto :dobuild
if not exist "web\dist\index.html" goto :dobuild
goto :afterbuild
:dobuild
echo [kurulum] web arayuzu derleniyor...
cd web
call npm install --no-audit --no-fund
call npm run build
cd ..
:afterbuild

:runserver
if "%PORT%"=="" set PORT=9000
if "%HOST%"=="" set HOST=127.0.0.1
echo.
echo Sunucu baslatiliyor: http://%HOST%:%PORT%
echo.
python -m uvicorn server.main:app --host %HOST% --port %PORT%
