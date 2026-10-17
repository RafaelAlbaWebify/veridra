@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [Veridra] Missing .venv. Run VERIDRA_SETUP.bat first.
  exit /b 2
)
".venv\Scripts\python.exe" -u "tools\webify_engagement_review.py" %*
exit /b %ERRORLEVEL%
