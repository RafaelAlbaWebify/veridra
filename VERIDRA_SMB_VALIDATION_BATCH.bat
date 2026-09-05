@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "AUDITOR=%ROOT%.venv\Scripts\veridra-prospect-audit-evidence.exe"
set "COHORT=%ROOT%evidence\smb-validation\ie-dental-cohort-v1.csv"
set "OUTDIR=%ROOT%artifacts\smb-validation"
set "INPUTZIP=%OUTDIR%\IE_DENTAL_COHORT_INPUT.zip"

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

if not exist "%OUTDIR%" mkdir "%OUTDIR%"

echo [Veridra] Building no-contact validation input from 25-practice Ireland dental cohort...
"%PYTHON%" "%ROOT%tools\build_smb_validation_input.py" "%COHORT%" "%INPUTZIP%"
if errorlevel 1 exit /b %ERRORLEVEL%

echo [Veridra] Running bounded read-only VERIDRA audits. No outreach or form submission is authorized.
"%AUDITOR%" --input "%INPUTZIP%" --max-targets 25 --output-directory "%OUTDIR%"
set "CODE=%ERRORLEVEL%"

if not "%CODE%"=="0" (
  echo [Veridra] Batch completed with audit failures. Review the generated evidence archive and failures.json.
  exit /b %CODE%
)

echo [Veridra] SMB validation batch completed. Evidence is in:
echo   %OUTDIR%
exit /b 0
