@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [Veridra] Local environment is not installed. Run VERIDRA_SETUP.bat first.
  exit /b 1
)
echo [Veridra] Running isolated commercial acceptance...
".venv\Scripts\python.exe" tools\commercial_acceptance.py %*
exit /b %ERRORLEVEL%
