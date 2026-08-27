@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [Veridra] Local environment is missing or outdated. Running setup...
  call "%ROOT%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)

echo [Veridra] Building read-only AI evidence export with Review Intelligence...
"%PYTHON%" -m veridra.ai_evidence_exchange_review_cli export ^
  --downloads "%USERPROFILE%\Downloads" ^
  --output-directory "%USERPROFILE%\Downloads" %*
exit /b %ERRORLEVEL%
