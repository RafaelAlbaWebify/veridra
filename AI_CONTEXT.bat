@echo off
setlocal
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "MODE=%~1"

if not "%MODE%"=="" goto run

if defined CI (
  set "MODE=bootstrap"
  goto run
)

echo.
echo ================================================
echo   CHATGPT PROJECT CONTEXT
echo ================================================
echo.
echo What are you doing?
echo.
echo   [1] Starting a NEW ChatGPT chat  ^(recommended/default^)
echo   [2] Moving ACTIVE unfinished work to another chat
echo   [3] Deep repository audit/debugging
echo.
set /p "CHOICE=Choose 1, 2 or 3 [1]: "
if "%CHOICE%"=="2" set "MODE=delta"
if "%CHOICE%"=="3" set "MODE=full"
if "%MODE%"=="" set "MODE=bootstrap"

:run
if /I not "%MODE%"=="bootstrap" if /I not "%MODE%"=="delta" if /I not "%MODE%"=="full" (
  echo Invalid mode: %MODE%
  if not defined CI pause
  exit /b 2
)

pushd "%ROOT%"
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "tools\ai_context_bundle.py" --mode %MODE%
) else (
  python "tools\ai_context_bundle.py" --mode %MODE%
)
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" (
  echo.
  echo Context generation failed.
  if not defined CI pause
  exit /b %RC%
)

set "BUNDLE=%ROOT%\.ai\generated\AI_CONTEXT_BUNDLE.md"
if not exist "%BUNDLE%" (
  echo Context bundle was not created: %BUNDLE%
  if not defined CI pause
  exit /b 3
)

if defined CI (
  echo AI context smoke test passed: %MODE%
  exit /b 0
)

set "PROMPT=Continue this project using the attached AI_CONTEXT_BUNDLE.md as repository context. Treat repository and .ai files as authoritative project memory. Verify current source, tests and runtime evidence before making claims or changes."
powershell -NoProfile -Command "Set-Clipboard -Value $env:PROMPT" >nul 2>nul
explorer /select,"%BUNDLE%"

echo.
echo ================================================
echo   DONE - YOU DO NOT NEED TO REMEMBER ANYTHING ELSE
echo ================================================
echo.
echo 1. Explorer has highlighted AI_CONTEXT_BUNDLE.md
echo 2. Open a new ChatGPT chat and drag that file into it
echo 3. Press Ctrl+V - the starter message is already copied
echo 4. Send
echo.
echo Mode used: %MODE%
echo.
pause
exit /b 0
