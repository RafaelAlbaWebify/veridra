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
"%PYTHON%" -m veridra.automated_discovery_evidence_cli --query "dentist in Dublin, IE" --country-code IE --locality Dublin --administrative-area Dublin --max-results 50 --max-scrolls 25 --max-seconds 120 --startup-wait-seconds 8 --output-directory "%USERPROFILE%\Downloads"
if errorlevel 1 exit /b %ERRORLEVEL%
echo [Veridra] Building read-only local competitive context...
"%PYTHON%" -m veridra.local_competitive_context_cli --downloads "%USERPROFILE%\Downloads" --output-directory "%USERPROFILE%\Downloads" --label "Dublin-Dentists"
exit /b %ERRORLEVEL%
