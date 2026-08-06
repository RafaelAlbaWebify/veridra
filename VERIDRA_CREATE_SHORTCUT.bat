@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-local.ps1" create-shortcut %*
exit /b %ERRORLEVEL%
