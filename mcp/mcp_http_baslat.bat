@echo off
REM Yerel Ollama MCP sunucusunu HTTP modunda baslatir (uzaktan erisim icin).
REM
REM ONERILEN KURULUM (VPN/Tailscale GEREKMEZ):
REM   Caddy (Caddyfile'da zaten hazir) rorcun.com/mcp yolunu bu sunucuya
REM   HTTPS ile proxy'ler. Sen sadece modeminde zaten acik olan 443 portunu
REM   kullanirsin — ekstra port acmana gerek yok. Kimlik dogrulama, asagida
REM   otomatik uretilen MCP_TOKEN ile yapilir (bkz. ollama_mcp.py _BearerGuard).
REM
REM   Genel adres:  https://rorcun.com/mcp
REM
REM MCP_HOST 127.0.0.1'de KALIR — port 8765 hicbir zaman disariya acilmaz,
REM yalnizca ayni makinedeki Caddy ona ulasabilir.
cd /d "%~dp0.."
set MCP_TRANSPORT=http
set MCP_HOST=127.0.0.1
set MCP_PORT=8765

REM --- AUTH ANAHTARI: ilk calistirmada otomatik uretilir ve mcp\.mcp_token
REM     dosyasina kaydedilir, sonraki calistirmalarda ayni anahtar okunur
REM     (Claude/claude.ai config'indeki anahtar boylece degismez). Anahtari
REM     degistirmek icin mcp\.mcp_token dosyasini silip yeniden baslatman yeterli.
set TOKEN_FILE=%~dp0.mcp_token
if not exist "%TOKEN_FILE%" (
    echo Ilk calistirma: MCP_TOKEN uretiliyor...
    ".venv\Scripts\python.exe" -c "import secrets,sys; open(sys.argv[1],'w',encoding='utf-8').write(secrets.token_urlsafe(32))" "%TOKEN_FILE%"
)
set /p MCP_TOKEN=<"%TOKEN_FILE%"

echo.
echo ===============================================================
echo  MCP sunucusu (HTTP) baslatiliyor
echo  Genel adres (Caddy uzerinden): https://rorcun.com/mcp
echo  Yerel adres (yalniz bu makine): http://127.0.0.1:%MCP_PORT%/mcp
echo  Auth anahtari (MCP_TOKEN)     : %MCP_TOKEN%
echo.
echo  Claude Desktop / claude.ai baglanti ornegi:
echo    Header ile   : Authorization: Bearer %MCP_TOKEN%
echo    URL ile (query): https://rorcun.com/mcp?token=%MCP_TOKEN%
echo ===============================================================
echo.

".venv\Scripts\python.exe" mcp\ollama_mcp.py
pause
