@echo off
setlocal
cd /d "%~dp0"
echo [Veridra] Starting H-500 local-commercial human acceptance...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\windows\veridra-commercial-h500-acceptance.ps1"
exit /b %ERRORLEVEL%
