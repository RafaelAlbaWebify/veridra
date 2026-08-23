@echo off
setlocal
set "ROOT=%~dp0"
set "CHECK=%ROOT%.venv\Scripts\veridra-assisted-discovery-check.exe"
if not exist "%CHECK%" (
  echo [Veridra] Local environment is missing or outdated. Running setup...
  call "%ROOT%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)
"%CHECK%" %*
exit /b %ERRORLEVEL%
