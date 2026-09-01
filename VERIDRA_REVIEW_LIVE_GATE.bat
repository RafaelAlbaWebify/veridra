@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0"
set "DOWNLOADS=%USERPROFILE%\Downloads"

echo ======================================================
echo VERIDRA - REVIEW INTELLIGENCE LIVE ACCEPTANCE GATE
echo ======================================================
echo.
echo This gate is read-only for prospect evidence and sends no outreach.
echo Google consent, sign-in, or CAPTCHA may require manual interaction.
echo.

call "%ROOT%VERIDRA_REVIEW_INTELLIGENCE.bat" %*
if errorlevel 1 (
  echo.
  echo [FAIL] Review collection did not produce acceptable non-zero evidence.
  exit /b %ERRORLEVEL%
)

call "%ROOT%VERIDRA_REVIEW_ACCEPTANCE.bat"
if errorlevel 1 (
  echo.
  echo [FAIL] Review evidence artifact failed deterministic acceptance.
  exit /b %ERRORLEVEL%
)

call "%ROOT%VERIDRA_AI_EXPORT.bat"
if errorlevel 1 (
  echo.
  echo [FAIL] Review-aware AI evidence export failed.
  exit /b %ERRORLEVEL%
)

set "AI_EXPORT="
for /f "delims=" %%F in ('dir /b /a-d /o-d "%DOWNLOADS%\VERIDRA_AI_EXPORT_*.zip" 2^>nul') do (
  if not defined AI_EXPORT set "AI_EXPORT=%DOWNLOADS%\%%F"
)

if not defined AI_EXPORT (
  echo.
  echo [FAIL] No VERIDRA_AI_EXPORT_*.zip was found in Downloads.
  exit /b 2
)

echo.
echo [Veridra] Final traceability check against:
echo   %AI_EXPORT%
call "%ROOT%VERIDRA_REVIEW_ACCEPTANCE.bat" --ai-export "%AI_EXPORT%"
if errorlevel 1 (
  echo.
  echo [FAIL] Review evidence was not accepted as traceable in the AI export.
  exit /b %ERRORLEVEL%
)

echo.
echo ======================================================
echo [PASS] REVIEW INTELLIGENCE LIVE GATE
echo ======================================================
echo Review evidence is non-zero, bounded, deterministic, indexed,
echo and traceable into the review-aware AI evidence export.
echo No outreach was sent.
exit /b 0
