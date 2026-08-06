@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-local.ps1" restart %*
exit /b %ERRORLEVEL%
