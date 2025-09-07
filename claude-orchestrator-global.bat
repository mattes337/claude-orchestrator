@echo off
REM Claude Orchestrator Global Launcher
REM This batch file ensures claude-orchestrator works from any directory

REM First try to use the installed console script
claude-orchestrator %* 2>nul
if %ERRORLEVEL% EQU 0 goto :end

REM If that fails, try to run directly with Python
python -m claude_orchestrator %* 2>nul
if %ERRORLEVEL% EQU 0 goto :end

REM If that fails, try to find the development version
set ORCHESTRATOR_DIR=%~dp0
python "%ORCHESTRATOR_DIR%claude-orchestrator-dev.py" %*

:end