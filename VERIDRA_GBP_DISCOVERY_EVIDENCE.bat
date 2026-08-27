@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
if exist "%CD%\.venv\Scripts\python.exe" (
  set "VERIDRA_PYTHON=%CD%\.venv\Scripts\python.exe"
) else (
  set "VERIDRA_PYTHON=python"
)
echo [Veridra] Enriching latest broad discovery pack with public GBP evidence...
"%VERIDRA_PYTHON%" -m veridra.gbp_discovery_evidence_cli --downloads "%USERPROFILE%\Downloads" --output-directory "%USERPROFILE%\Downloads"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo [Veridra] Discovery GBP evidence collection failed with exit code %EXITCODE%.
)
exit /b %EXITCODE%
