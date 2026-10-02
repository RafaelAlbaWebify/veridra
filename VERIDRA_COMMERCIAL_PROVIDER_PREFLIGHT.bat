@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-hosted-provider-preflight.ps1" %*
exit /b %ERRORLEVEL%
