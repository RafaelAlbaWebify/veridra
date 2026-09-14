@echo off
setlocal
set "ROOT=%~dp0"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=bootstrap"
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%ROOT%tools\ai_context_bundle.py" --root "%ROOT%" --mode %MODE%
) else (
  python "%ROOT%tools\ai_context_bundle.py" --root "%ROOT%" --mode %MODE%
)
exit /b %ERRORLEVEL%
