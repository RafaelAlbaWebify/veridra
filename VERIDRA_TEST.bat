@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-local.ps1" setup
if errorlevel 1 exit /b %ERRORLEVEL%
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade -e "%~dp0.[dev]"
if errorlevel 1 exit /b %ERRORLEVEL%
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-local.ps1" test %*
exit /b %ERRORLEVEL%
