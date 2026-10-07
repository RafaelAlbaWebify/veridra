@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)
if /I "%~1"=="prepare" goto run
if /I "%~1"=="verify" goto run
echo Usage: VERIDRA_REBOOT_ACCEPTANCE.bat prepare ^| verify
exit /b 2

:run
".venv\Scripts\python.exe" -u "%~dp0tools\reboot_acceptance.py" %~1
exit /b %ERRORLEVEL%
