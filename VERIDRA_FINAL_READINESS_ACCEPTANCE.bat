@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)
echo [Veridra] Running final technical readiness acceptance...
".venv\Scripts\python.exe" -u "%~dp0tools\final_readiness_acceptance.py"
exit /b %ERRORLEVEL%
