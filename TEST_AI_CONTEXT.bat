@echo off
setlocal
set "ROOT=%~dp0"
set "CI=1"

echo Testing bootstrap...
call "%ROOT%AI_CONTEXT.bat" bootstrap
if errorlevel 1 goto fail

echo Testing delta...
call "%ROOT%AI_CONTEXT.bat" delta
if errorlevel 1 goto fail

echo Testing full...
call "%ROOT%AI_CONTEXT.bat" full
if errorlevel 1 goto fail

if not exist "%ROOT%.ai\generated\AI_CONTEXT_BUNDLE.md" goto fail
if not exist "%ROOT%.ai\generated\AI_CONTEXT_MANIFEST.json" goto fail

powershell -NoProfile -Command "$m=Get-Content '%ROOT%.ai\generated\AI_CONTEXT_MANIFEST.json' -Raw | ConvertFrom-Json; if($m.mode -ne 'full'){exit 2}; if([string]::IsNullOrWhiteSpace($m.commit) -or $m.commit -eq 'unknown'){exit 3}; $b=Get-Item '%ROOT%.ai\generated\AI_CONTEXT_BUNDLE.md'; if($b.Length -lt 500){exit 4}"
if errorlevel 1 goto fail

echo.
echo ================================================
echo   PASS - AI CONTEXT WORKFLOW IS WORKING
echo ================================================
echo.
pause
exit /b 0

:fail
echo.
echo ================================================
echo   FAIL - AI CONTEXT WORKFLOW NEEDS ATTENTION
echo ================================================
echo.
pause
exit /b 1
