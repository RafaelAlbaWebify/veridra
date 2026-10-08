@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [Veridra] Existing .venv is required for a non-disruptive inspection.
  echo [Veridra] No setup or service changes will be attempted.
  exit /b 2
)
".venv\Scripts\python.exe" -u "%~dp0tools\workstation_readonly_inspection.py"
exit /b %ERRORLEVEL%
