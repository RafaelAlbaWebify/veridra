@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-commercial-local.ps1" stop %*
exit /b %ERRORLEVEL%
