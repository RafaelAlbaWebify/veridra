@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [Veridra] Local environment is missing or outdated. Running setup...
  call "%ROOT%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)

set "FAILURES=0"
call :discover "dentist in Dublin, IE"
call :discover "dental clinic in Dublin, IE"
call :discover "cosmetic dentist in Dublin, IE"
call :discover "emergency dentist in Dublin, IE"
call :discover "family dentist in Dublin, IE"

if not "%FAILURES%"=="0" echo [Veridra] Warning: %FAILURES% query variant(s) failed after automated retries; continuing with successful evidence.

echo [Veridra] Building deduped read-only local competitive context...
"%PYTHON%" -m veridra.local_competitive_context_cli ^
  --downloads "%USERPROFILE%\Downloads" ^
  --output-directory "%USERPROFILE%\Downloads" ^
  --label "Dublin-Dentists" ^
  --input-pattern "VERIDRA_DISCOVERY_dentist-in-Dublin-IE_*.zip" ^
  --input-pattern "VERIDRA_DISCOVERY_dental-clinic-in-Dublin-IE_*.zip" ^
  --input-pattern "VERIDRA_DISCOVERY_cosmetic-dentist-in-Dublin-IE_*.zip" ^
  --input-pattern "VERIDRA_DISCOVERY_emergency-dentist-in-Dublin-IE_*.zip" ^
  --input-pattern "VERIDRA_DISCOVERY_family-dentist-in-Dublin-IE_*.zip"
exit /b %ERRORLEVEL%

:discover
set "QUERY=%~1"
echo [Veridra] Refreshing local-profile evidence for: %QUERY%
"%PYTHON%" -m veridra.automated_discovery_evidence_cli --query "%QUERY%" --country-code IE --locality Dublin --administrative-area Dublin --max-results 50 --max-scrolls 25 --max-seconds 120 --startup-wait-seconds 8 --output-directory "%USERPROFILE%\Downloads"
if not errorlevel 1 goto :eof
echo [Veridra] First attempt failed. Retrying: %QUERY%
timeout /t 5 /nobreak >nul
"%PYTHON%" -m veridra.automated_discovery_evidence_cli --query "%QUERY%" --country-code IE --locality Dublin --administrative-area Dublin --max-results 50 --max-scrolls 25 --max-seconds 120 --startup-wait-seconds 16 --output-directory "%USERPROFILE%\Downloads"
if not errorlevel 1 goto :eof
echo [Veridra] Query failed after 2 automated attempts: %QUERY%
set /a FAILURES+=1
goto :eof
