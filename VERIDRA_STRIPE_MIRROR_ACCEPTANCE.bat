@echo off
setlocal
cd /d "%~dp0"
call "%~dp0VERIDRA_OPERATOR_START.bat"
if errorlevel 1 exit /b %ERRORLEVEL%
if not exist ".venv\Scripts\python.exe" (
  echo [Veridra] Python environment is missing.
  exit /b 1
)
set "PHASE=%~1"
if "%PHASE%"=="" set "PHASE=paid"
echo [Veridra] Running Stripe provider mirror phase: %PHASE%
".venv\Scripts\python.exe" -u "%~dp0tools\operator_stripe_mirror_acceptance.py" --phase "%PHASE%"
exit /b %ERRORLEVEL%
