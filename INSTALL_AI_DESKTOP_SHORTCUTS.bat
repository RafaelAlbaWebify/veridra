@echo off
setlocal
set "ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%tools\install_ai_desktop_shortcuts.ps1"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo Desktop shortcut installation completed successfully.
) else (
  echo Desktop shortcut installation FAILED. See messages above.
)
echo.
pause
exit /b %RC%
