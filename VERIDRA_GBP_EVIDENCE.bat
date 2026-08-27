@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
echo [Veridra] Collecting bounded public Google Business Profile evidence...
python -m veridra.gbp_profile_evidence_cli --downloads "%USERPROFILE%\Downloads" --output-directory "%USERPROFILE%\Downloads"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo [Veridra] GBP evidence collection failed with exit code %EXITCODE%.
)
exit /b %EXITCODE%
