@echo off
setlocal
pushd "%~dp0"
echo.
echo Testing enhanced VERIDRA AI workflow...
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "tools\test_ai_workflow.py" --module assessment
) else (
  python "tools\test_ai_workflow.py" --module assessment
)
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo ================================================
  echo   PASS - ENHANCED AI WORKFLOW IS WORKING
  echo ================================================
) else (
  echo ================================================
  echo   FAIL - ENHANCED AI WORKFLOW NEEDS ATTENTION
  echo ================================================
)
echo.
pause
popd
exit /b %RC%
