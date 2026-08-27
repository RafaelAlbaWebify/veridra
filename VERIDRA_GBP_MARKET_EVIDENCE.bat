@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [Veridra] Missing .venv. Create the VERIDRA environment before running GBP market enrichment.
  exit /b 2
)
echo [Veridra] Enriching the latest market enumeration with public GBP evidence...
"%PYTHON%" -m veridra.gbp_market_evidence_cli --downloads "%USERPROFILE%\Downloads" --output-directory "%USERPROFILE%\Downloads"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo [Veridra] GBP market enrichment failed with exit code %EXITCODE%.
)
exit /b %EXITCODE%
