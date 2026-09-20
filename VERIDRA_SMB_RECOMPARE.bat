@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "OUTDIR=%ROOT%artifacts\smb-validation"
set "EXPECTATIONS=%ROOT%evidence\smb-validation\ie-dental-seed-expectations-v1.json"
set "ADJUDICATIONS=%ROOT%evidence\smb-validation\ie-dental-seed-adjudications-v1.json"
set "COMPARISON=%OUTDIR%\SMB_VALIDATION_COMPARISON.json"
set "SUMMARY=%OUTDIR%\SMB_VALIDATION_SUMMARY.json"

if not exist "%PYTHON%" (
  echo [Veridra] Local environment missing. Run VERIDRA_SETUP.bat first.
  exit /b 2
)

echo [Veridra] Running focused comparator regression...
"%PYTHON%" -m pytest "%ROOT%tests\test_compare_smb_validation_run.py" -q
if errorlevel 1 (
  echo [Veridra] Comparator regression failed. Existing real-site evidence was NOT rescored.
  exit /b %ERRORLEVEL%
)

set "AUDITZIP="
for /f "delims=" %%F in ('dir /b /a-d /o-d "%OUTDIR%\VERIDRA_PROSPECT_AUDITS_*.zip" 2^>nul') do if not defined AUDITZIP set "AUDITZIP=%OUTDIR%\%%F"

if not defined AUDITZIP (
  echo [Veridra] No existing SMB audit archive found in %OUTDIR%.
  exit /b 3
)

echo [Veridra] Re-comparing existing real-SMB evidence only.
echo [Veridra] No websites will be crawled.
echo [Veridra] Audit archive:
echo   %AUDITZIP%

"%PYTHON%" "%ROOT%tools\compare_smb_validation_run.py" --audit-zip "%AUDITZIP%" --expectations "%EXPECTATIONS%" --adjudications "%ADJUDICATIONS%" --output "%COMPARISON%"
if errorlevel 1 exit /b %ERRORLEVEL%

"%PYTHON%" "%ROOT%tools\summarize_smb_validation.py" --comparison "%COMPARISON%" --output "%SUMMARY%"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo [Veridra] Recomparison complete. No real-site audit was repeated.
exit /b 0
