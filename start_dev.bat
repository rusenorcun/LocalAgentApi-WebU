@echo off
cd /d "%~dp0"
echo === Gelistirme Modu ===

if exist "set_env.bat" call set_env.bat
if "%PORT%"=="" set PORT=9000

echo [1/2] FastAPI sunucusu baslatiliyor (port %PORT%)...
start cmd /k "call .venv\Scripts\activate.bat && python -m uvicorn server.main:app --host 127.0.0.1 --port %PORT% --reload"

echo [2/2] Vite gelistirme sunucusu baslatiliyor (port 5173)...
cd web
call npm install --silent
call npm run dev
