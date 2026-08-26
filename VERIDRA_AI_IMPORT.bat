@echo off
setlocal
set "ROOT=%~dp0"
python -m veridra.ai_evidence_exchange_cli import %*
exit /b %ERRORLEVEL%
