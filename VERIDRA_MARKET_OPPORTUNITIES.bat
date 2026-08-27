@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
  echo [Veridra] Missing project virtual environment: %VENV_PYTHON%
  exit /b 2
)
echo [Veridra] Ranking the latest fully enriched market evidence...
"%VENV_PYTHON%" -m veridra.market_opportunity_cli --downloads "%USERPROFILE%\Downloads" --output-directory "%USERPROFILE%\Downloads"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" echo [Veridra] Market opportunity ranking failed with exit code %EXITCODE%.
exit /b %EXITCODE%
