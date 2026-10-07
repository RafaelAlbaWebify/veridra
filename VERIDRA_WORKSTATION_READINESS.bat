@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)
if "%~1"=="" (
  echo Usage: VERIDRA_WORKSTATION_READINESS.bat ^<SECOND_COPY_DIRECTORY^>
  echo Example: VERIDRA_WORKSTATION_READINESS.bat E:\Webify\VeridraBackups
  exit /b 2
)
echo [Veridra] Running #296 workstation readiness acceptance...
".venv\Scripts\python.exe" -u "%~dp0tools\workstation_readiness_acceptance.py" --second-copy-dir "%~1"
exit /b %ERRORLEVEL%
