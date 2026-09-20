@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "REVIEWDIR=%ROOT%artifacts\smb-validation\human-validation"

if not exist "%PYTHON%" (
  echo [Veridra] Local environment missing. Run VERIDRA_SETUP.bat first.
  exit /b 2
)

if /I "%~1"=="summary" goto :summary
if /I "%~1"=="generate" goto :generate
if "%~1"=="" goto :generate

echo Usage:
echo   VERIDRA_SMB_HUMAN_VALIDATION.bat generate
echo   VERIDRA_SMB_HUMAN_VALIDATION.bat summary
exit /b 2

:generate
echo [Veridra] Building 12-business Phase C human-validation pack from latest audit evidence...
"%PYTHON%" -m py_compile ^
  "%ROOT%tools\build_smb_human_validation_pack.py" ^
  "%ROOT%tools\summarize_smb_human_validation.py"
if errorlevel 1 exit /b %ERRORLEVEL%

"%PYTHON%" "%ROOT%tools\build_smb_human_validation_pack.py" ^
  --count 12 ^
  --output-directory "%REVIEWDIR%"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo [Veridra] Human-validation pack ready:
echo   %REVIEWDIR%\business_review.csv
echo   %REVIEWDIR%\finding_review.csv
echo   %REVIEWDIR%\README.md
echo.
echo [Veridra] No websites were contacted by this command.
exit /b 0

:summary
echo [Veridra] Calculating Phase C metrics from completed review files...
"%PYTHON%" "%ROOT%tools\summarize_smb_human_validation.py" ^
  --review-directory "%REVIEWDIR%"
exit /b %ERRORLEVEL%
