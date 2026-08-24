@echo off
setlocal
set "ROOT=%~dp0"
set "RUNNER=%ROOT%.venv\Scripts\veridra-dublin-acquisition-batch.exe"
if not exist "%RUNNER%" (
  echo [Veridra] Local environment is missing or outdated. Running setup...
  call "%ROOT%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)
"%RUNNER%" %*
exit /b %ERRORLEVEL%
