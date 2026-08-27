@echo off
setlocal
cd /d "%~dp0"
echo [Veridra] Enumerating the Dublin dental market across bounded Google Maps queries...
if not exist ".venv\Scripts\python.exe" (
  echo [Veridra] Missing .venv. Create the VERIDRA virtual environment first.
  exit /b 1
)
".venv\Scripts\python.exe" -m veridra.market_enumeration_cli --plan dublin-dentists --output-directory "%USERPROFILE%\Downloads"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo [Veridra] Market enumeration failed with exit code %EXITCODE%.
)
exit /b %EXITCODE%
