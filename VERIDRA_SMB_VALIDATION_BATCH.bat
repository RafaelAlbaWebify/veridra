@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "AUDITOR=%ROOT%.venv\Scripts\veridra-prospect-audit-evidence.exe"
set "COHORT=%ROOT%evidence\smb-validation\ie-dental-cohort-v1.csv"
set "EXPECTATIONS=%ROOT%evidence\smb-validation\ie-dental-seed-expectations-v1.json"
set "ADJUDICATIONS=%ROOT%evidence\smb-validation\ie-dental-seed-adjudications-v1.json"
set "OUTDIR=%ROOT%artifacts\smb-validation"
set "INPUTZIP=%OUTDIR%\IE_DENTAL_COHORT_INPUT.zip"
set "COMPARISON=%OUTDIR%\SMB_VALIDATION_COMPARISON.json"

if not exist "%PYTHON%" (
  echo [Veridra] Local environment is missing or outdated. Running setup...
  call "%ROOT%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)

if not exist "%AUDITOR%" (
  echo [Veridra] Audit CLI is missing. Refreshing setup...
  call "%ROOT%VERIDRA_SETUP.bat"
  if errorlevel 1 exit /b %ERRORLEVEL%
)

if not exist "%COHORT%" (
  echo [Veridra] SMB validation cohort is missing: %COHORT%
  exit /b 2
)

if not exist "%EXPECTATIONS%" (
  echo [Veridra] SMB validation expectations are missing: %EXPECTATIONS%
  exit /b 2
)

if not exist "%ADJUDICATIONS%" (
  echo [Veridra] SMB validation adjudications are missing: %ADJUDICATIONS%
  exit /b 2
)

if not exist "%OUTDIR%" mkdir "%OUTDIR%"

echo [Veridra] Building no-contact validation input from 25-practice Ireland dental cohort...
"%PYTHON%" "%ROOT%tools\build_smb_validation_input.py" "%COHORT%" "%INPUTZIP%"
if errorlevel 1 exit /b %ERRORLEVEL%

echo [Veridra] Running bounded read-only VERIDRA audits. No outreach or form submission is authorized.
"%AUDITOR%" --input "%INPUTZIP%" --max-targets 25 --output-directory "%OUTDIR%"
set "CODE=%ERRORLEVEL%"

if not "%CODE%"=="0" (
  echo [Veridra] Batch completed without a successful assessment. Review the generated evidence and failures.
  exit /b %CODE%
)

set "AUDITZIP="
for /f "delims=" %%F in ('dir /b /a-d /o-d "%OUTDIR%\VERIDRA_PROSPECT_AUDITS_*.zip" 2^>nul') do if not defined AUDITZIP set "AUDITZIP=%OUTDIR%\%%F"

if not defined AUDITZIP (
  echo [Veridra] Audit archive was not found after the batch run.
  exit /b 3
)

if not exist "%AUDITZIP%" (
  echo [Veridra] Selected audit archive does not exist: %AUDITZIP%
  exit /b 3
)

echo [Veridra] Comparing real-SMB evidence against the frozen manual seed and current adjudications...
"%PYTHON%" "%ROOT%tools\compare_smb_validation_run.py" --audit-zip "%AUDITZIP%" --expectations "%EXPECTATIONS%" --adjudications "%ADJUDICATIONS%" --output "%COMPARISON%"
if errorlevel 1 exit /b %ERRORLEVEL%

echo [Veridra] SMB validation batch completed.
echo [Veridra] Audit evidence:
echo   %AUDITZIP%
echo [Veridra] Frozen-seed plus adjudicated comparison:
echo   %COMPARISON%
exit /b 0
