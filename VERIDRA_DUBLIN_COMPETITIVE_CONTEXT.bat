@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [Veridra] Local environment is missing or outdated. Running setup...
  call "%ROOT%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)

echo [Veridra] Refreshing current Dublin dentist local-profile evidence...
set "DISCOVERY_OK=0"

echo [Veridra] Maps attempt 1/3...
"%PYTHON%" -m veridra.automated_discovery_evidence_cli --query "dentist in Dublin, IE" --country-code IE --locality Dublin --administrative-area Dublin --max-results 50 --max-scrolls 25 --max-seconds 120 --startup-wait-seconds 8 --output-directory "%USERPROFILE%\Downloads"
if not errorlevel 1 set "DISCOVERY_OK=1"

if "%DISCOVERY_OK%"=="0" (
  echo [Veridra] First Maps attempt failed. Waiting before retry...
  timeout /t 5 /nobreak >nul
  echo [Veridra] Maps attempt 2/3...
  "%PYTHON%" -m veridra.automated_discovery_evidence_cli --query "dentist in Dublin, IE" --country-code IE --locality Dublin --administrative-area Dublin --max-results 50 --max-scrolls 25 --max-seconds 120 --startup-wait-seconds 14 --output-directory "%USERPROFILE%\Downloads"
  if not errorlevel 1 set "DISCOVERY_OK=1"
)

if "%DISCOVERY_OK%"=="0" (
  echo [Veridra] Second Maps attempt failed. Waiting before final retry...
  timeout /t 8 /nobreak >nul
  echo [Veridra] Maps attempt 3/3...
  "%PYTHON%" -m veridra.automated_discovery_evidence_cli --query "dentist in Dublin, IE" --country-code IE --locality Dublin --administrative-area Dublin --max-results 50 --max-scrolls 25 --max-seconds 120 --startup-wait-seconds 20 --output-directory "%USERPROFILE%\Downloads"
  if not errorlevel 1 set "DISCOVERY_OK=1"
)

if "%DISCOVERY_OK%"=="0" (
  echo [Veridra] Maps discovery failed after 3 automated attempts.
  exit /b 2
)

echo [Veridra] Building read-only local competitive context...
"%PYTHON%" -m veridra.local_competitive_context_cli --downloads "%USERPROFILE%\Downloads" --output-directory "%USERPROFILE%\Downloads" --label "Dublin-Dentists"
exit /b %ERRORLEVEL%
