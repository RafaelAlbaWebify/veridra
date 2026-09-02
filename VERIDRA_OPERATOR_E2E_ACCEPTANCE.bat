@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)
echo [Veridra] Running true Playwright first-customer operator + visual acceptance...
".venv\Scripts\python.exe" -u "%~dp0tools\operator_visual_acceptance_entry.py"
exit /b %ERRORLEVEL%
