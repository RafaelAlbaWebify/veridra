@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\veridra-human-acceptance.ps1"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo.
  echo [VERIDRA] Human acceptance session setup failed with exit code %EXITCODE%.
)
exit /b %EXITCODE%
