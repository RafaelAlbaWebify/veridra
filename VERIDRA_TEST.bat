@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-local.ps1" setup
if errorlevel 1 exit /b %ERRORLEVEL%
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-local.ps1" test %*
exit /b %ERRORLEVEL%
