@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-commercial-local.ps1" h6-phase6 %*
exit /b %ERRORLEVEL%
