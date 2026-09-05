@echo off
REM ============================================================
REM  Caddy artik Windows SERVISI olarak calisiyor (servis adi: Caddy).
REM  Bilgisayar her acildiginda giris yapmadan otomatik baslar;
REM  bu dosyayi artik her oturumda calistirmak gerekmez.
REM
REM  Kullanim:
REM    caddy_baslat.bat                 -> servis durumu
REM    caddy_baslat.bat baslat          -> servisi baslatir (UAC onayi ister)
REM    caddy_baslat.bat durdur          -> servisi durdurur (UAC onayi ister)
REM    caddy_baslat.bat yeniden-baslat  -> yeniden baslatir (UAC onayi ister)
REM
REM  Servis tanimi: caddy\caddy-service.exe + caddy-service.xml
REM  Log dosyalari: caddy\logs\
REM ============================================================
setlocal
set "AKS=%~1"
if "%AKS%"=="" set "AKS=durum"

REM Zaten yonetici miyiz? (net session yalnizca yoneticide basarili)
net session >nul 2>&1
if not errorlevel 1 goto :yonetici

if /I "%AKS%"=="durum" goto :durum

REM Yonetici yetkisi gerektiren aksiyon: kendini UAC ile tekrar calistir
echo "%AKS%" icin yonetici izni isteniyor (UAC penceresini onaylayin)...
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%AKS%' -Verb RunAs"
exit /b

:yonetici
if /I "%AKS%"=="baslat"         net start Caddy & goto :sonuc
if /I "%AKS%"=="durdur"         net stop Caddy & goto :sonuc
if /I "%AKS%"=="yeniden-baslat" (net stop Caddy >nul 2>&1 & net start Caddy) & goto :sonuc

:durum
sc query Caddy | findstr /I "SERVICE_NAME STATE DURUM"
exit /b

:sonuc
echo.
sc query Caddy | findstr /I "SERVICE_NAME STATE DURUM"
timeout /t 4 >nul
exit /b
