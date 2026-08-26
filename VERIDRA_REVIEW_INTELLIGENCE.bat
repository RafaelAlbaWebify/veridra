@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [Veridra] Local environment is missing or outdated. Running setup...
  call "%ROOT%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)

echo [Veridra] Building hardened bounded read-only review intelligence...
"%PYTHON%" -m veridra.review_intelligence_hardened_cli --downloads "%USERPROFILE%\Downloads" --output-directory "%USERPROFILE%\Downloads" %*
exit /b %ERRORLEVEL%
