@echo off
setlocal
set "REPO=%~dp0"
set "PYTHON=%REPO%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  call "%REPO%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)
"%PYTHON%" "%REPO%scripts\browser\discovery_workflow_acceptance.py"
exit /b %ERRORLEVEL%
