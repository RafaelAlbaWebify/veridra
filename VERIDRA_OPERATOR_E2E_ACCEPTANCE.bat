@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)
echo [Veridra] Running full business lifecycle Playwright acceptance...
".venv\Scripts\python.exe" -u "%~dp0tools\full_business_lifecycle_acceptance_entry.py"
exit /b %ERRORLEVEL%
