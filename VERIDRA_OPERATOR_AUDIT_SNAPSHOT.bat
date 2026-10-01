@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\veridra-local.ps1" operator-audit-snapshot
exit /b %ERRORLEVEL%
