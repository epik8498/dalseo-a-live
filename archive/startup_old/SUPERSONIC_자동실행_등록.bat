@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SUPERSONIC_자동실행_등록.ps1"
echo.
pause
