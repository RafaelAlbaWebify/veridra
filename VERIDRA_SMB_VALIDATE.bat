@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "COMPARISON=%ROOT%artifacts\smb-validation\SMB_VALIDATION_COMPARISON.json"
set "SUMMARY=%ROOT%artifacts\smb-validation\SMB_VALIDATION_SUMMARY.json"

echo [Veridra] One-command SMB validation
echo [Veridra] Safety boundary: public read-only assessment only. No outreach, forms, auth or modification.

git diff --quiet
if errorlevel 1 (
  echo [Veridra] Tracked working-tree changes detected. Commit or revert them before validation.
  exit /b 10
)
git diff --cached --quiet
if errorlevel 1 (
  echo [Veridra] Staged changes detected. Commit or unstage them before validation.
  exit /b 10
)

echo [Veridra] Updating repository with fast-forward only...
git pull --ff-only
if errorlevel 1 exit /b %ERRORLEVEL%

if not exist "%PYTHON%" (
  echo [Veridra] Local environment missing. Running setup...
  call "%ROOT%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)

echo [Veridra] Running focused local validation gate...
"%PYTHON%" -m pytest "%ROOT%tests\test_compare_smb_validation_run.py" "%ROOT%tests\test_business_content_consistency.py" "%ROOT%tests\test_crawl.py" -q
if errorlevel 1 (
  echo [Veridra] Local validation gate failed. Real cohort audit NOT started.
  exit /b %ERRORLEVEL%
)

echo [Veridra] Local gate passed. Running frozen 25-business public-site batch...
call "%ROOT%VERIDRA_SMB_VALIDATION_BATCH.bat"
if errorlevel 1 exit /b %ERRORLEVEL%

if not exist "%COMPARISON%" (
  echo [Veridra] Comparison output missing: %COMPARISON%
  exit /b 11
)

echo [Veridra] Producing compact operator summary...
"%PYTHON%" "%ROOT%tools\summarize_smb_validation.py" --comparison "%COMPARISON%" --output "%SUMMARY%"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo [Veridra] Validation workflow complete.
echo [Veridra] Paste only the summary block above, or upload:
echo   %SUMMARY%
exit /b 0
