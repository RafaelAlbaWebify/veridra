@echo off
setlocal EnableExtensions
set "MODE=%~1"
set "MODULE=%~2"
pushd "%~dp0"

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
echo   [4] Starting a NEW chat focused on one project module
echo   [5] FINISH current AI session / prepare handoff
echo.
set /p "CHOICE=Choose 1, 2, 3, 4 or 5 [1]: "
if "%CHOICE%"=="2" set "MODE=delta"
if "%CHOICE%"=="3" set "MODE=full"
if "%CHOICE%"=="4" goto choose_module
if "%CHOICE%"=="5" goto finish_session
if "%MODE%"=="" set "MODE=bootstrap"
goto run

:choose_module
echo.
echo Available modules:
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "tools\ai_context_bundle.py" --list-modules
) else (
  python "tools\ai_context_bundle.py" --list-modules
)
echo.
set /p "MODULE=Type the module key exactly as shown: "
if "%MODULE%"=="" (
  echo No module selected.
  pause
  popd
  exit /b 2
)
set "MODE=bootstrap"
goto run

:finish_session
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "tools\finish_ai_session.py"
) else (
  python "tools\finish_ai_session.py"
)
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Session handoff generation failed.
  pause
  popd
  exit /b %RC%
)
echo.
echo ================================================
echo   SESSION HANDOFF READY
echo ================================================
echo.
echo Generated:
echo   .ai\generated\SESSION_HANDOFF.md
echo   .ai\generated\AI_CONTEXT_BUNDLE.md
echo.
echo If project facts/decisions/tests changed, canonical .ai files must still be updated.
explorer /select,"%CD%\.ai\generated\SESSION_HANDOFF.md"
pause
popd
exit /b 0

:run
if /I not "%MODE%"=="bootstrap" if /I not "%MODE%"=="delta" if /I not "%MODE%"=="full" (
  echo Invalid mode: %MODE%
  if not defined CI pause
  popd
  exit /b 2
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  if defined MODULE (
    py -3 "tools\ai_context_bundle.py" --mode %MODE% --module "%MODULE%"
  ) else (
    py -3 "tools\ai_context_bundle.py" --mode %MODE%
  )
) else (
  if defined MODULE (
    python "tools\ai_context_bundle.py" --mode %MODE% --module "%MODULE%"
  ) else (
    python "tools\ai_context_bundle.py" --mode %MODE%
  )
)
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Context generation failed.
  if not defined CI pause
  popd
  exit /b %RC%
)

set "BUNDLE=%CD%\.ai\generated\AI_CONTEXT_BUNDLE.md"
if not exist "%BUNDLE%" (
  echo Context bundle was not created: %BUNDLE%
  if not defined CI pause
  popd
  exit /b 3
)

if defined CI (
  echo AI context smoke test passed: %MODE% %MODULE%
  popd
  exit /b 0
)

set "PROMPT=Continue this project using the attached AI_CONTEXT_BUNDLE.md as repository context. Treat repository and .ai files as authoritative project memory. Pay attention to the bundle freshness status and verify current source, tests and runtime evidence before making claims or changes."
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
if defined MODULE echo Module: %MODULE%
echo.
pause
popd
exit /b 0
