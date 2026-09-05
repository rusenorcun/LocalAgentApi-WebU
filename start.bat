@echo off
REM Tek giris noktasi run.bat'tir. Bu dosya geriye uyumluluk icin durur.
REM Frontend'i her seferinde yeniden derleyerek baslatir.
set BUILD=1
call "%~dp0run.bat"
