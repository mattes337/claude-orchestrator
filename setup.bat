@echo off
REM Claude Code Orchestrator - Windows Setup and Execution Script
REM Provides setup, execution, and management functionality for Windows environments

setlocal enabledelayedexpansion

REM Configuration
set SCRIPT_DIR=%~dp0
set VENV_DIR=%SCRIPT_DIR%venv
set CONFIG_FILE=%SCRIPT_DIR%orchestrator.config.json
set STATE_FILE=%SCRIPT_DIR%orchestrator_state.json
set LOG_FILE=%SCRIPT_DIR%orchestrator.log
set REQUIREMENTS_FILE=%SCRIPT_DIR%requirements.txt
set PYTHON_SCRIPT=%SCRIPT_DIR%orchestrator.py

REM Initialize log file
echo [%date% %time%] Starting Claude Code Orchestrator Setup >> "%LOG_FILE%"

REM Colors (limited support in Windows)
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

REM Logging functions
call :log_info "Claude Code Orchestrator - Windows Setup"

goto :parse_args

:log_info
echo [INFO] %~1
echo [%date% %time%] [INFO] %~1 >> "%LOG_FILE%"
goto :eof

:log_warn
echo [WARN] %~1
echo [%date% %time%] [WARN] %~1 >> "%LOG_FILE%"
goto :eof

:log_error
echo [ERROR] %~1
echo [%date% %time%] [ERROR] %~1 >> "%LOG_FILE%"
goto :eof

:check_command
where "%~1" >nul 2>&1
if errorlevel 1 (
    call :log_error "Required command not found: %~1"
    exit /b 1
)
goto :eof

:check_dependencies
call :log_info "Checking dependencies..."

set "missing_deps="

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    where python3 >nul 2>&1
    if errorlevel 1 (
        set "missing_deps=!missing_deps! python"
    )
)

REM Check pip
where pip >nul 2>&1
if errorlevel 1 (
    where pip3 >nul 2>&1
    if errorlevel 1 (
        set "missing_deps=!missing_deps! pip"
    )
)

REM Check git
where git >nul 2>&1
if errorlevel 1 (
    set "missing_deps=!missing_deps! git"
)

REM Check Claude CLI (optional)
where claude >nul 2>&1
if errorlevel 1 (
    call :log_warn "Claude Code CLI not found - some features may not work"
)

if not "!missing_deps!"=="" (
    call :log_error "Missing required dependencies: !missing_deps!"
    echo.
    echo Please install the missing dependencies:
    echo - Python 3.8+: https://python.org/downloads
    echo - Git: https://git-scm.com/downloads
    echo - Claude CLI: https://claude.ai/cli
    echo.
    pause
    exit /b 1
)

call :log_info "All required dependencies found"
goto :eof

:get_python_cmd
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :eof
)

where python3 >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python3"
    goto :eof
)

call :log_error "No Python interpreter found"
exit /b 1

:setup_virtual_environment
call :log_info "Setting up virtual environment..."

call :get_python_cmd
if errorlevel 1 exit /b 1

if not exist "%VENV_DIR%" (
    call :log_info "Creating virtual environment..."
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        call :log_error "Failed to create virtual environment"
        exit /b 1
    )
)

REM Activate virtual environment
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
) else (
    call :log_error "Failed to find virtual environment activation script"
    exit /b 1
)

REM Upgrade pip
call :log_info "Upgrading pip..."
pip install --upgrade pip
if errorlevel 1 (
    call :log_warn "Failed to upgrade pip"
)

REM Install requirements
if exist "%REQUIREMENTS_FILE%" (
    call :log_info "Installing Python dependencies..."
    pip install -r "%REQUIREMENTS_FILE%"
    if errorlevel 1 (
        call :log_error "Failed to install requirements"
        exit /b 1
    )
) else (
    call :log_warn "Requirements file not found: %REQUIREMENTS_FILE%"
    REM Install minimal requirements
    pip install psutil
)

call :log_info "Virtual environment setup complete"
goto :eof

:create_default_config
if not exist "%CONFIG_FILE%" (
    call :log_info "Creating default configuration..."
    (
        echo {
        echo   "milestones_dir": "milestones",
        echo   "tasks_file": "TASKS.md",
        echo   "execution": {
        echo     "max_parallel_tasks": 4,
        echo     "task_timeout": 1800,
        echo     "max_retries": 3,
        echo     "retry_delay": 30
        echo   },
        echo   "rate_limit": {
        echo     "requests_per_minute": 50,
        echo     "burst_limit": 10,
        echo     "backoff_multiplier": 2
        echo   },
        echo   "git": {
        echo     "use_worktrees": true,
        echo     "base_branch": "main",
        echo     "worktree_prefix": "milestone-"
        echo   },
        echo   "code_review": {
        echo     "enabled": true,
        echo     "auto_fix": true,
        echo     "quality_threshold": 0.8
        echo   },
        echo   "notifications": {
        echo     "enabled": false,
        echo     "webhook_url": ""
        echo   },
        echo   "logging": {
        echo     "level": "INFO",
        echo     "format": "%%(asctime^)s - %%(name^)s - %%(levelname^)s - %%(message^)s"
        echo   }
        echo }
    ) > "%CONFIG_FILE%"
    call :log_info "Default configuration created: %CONFIG_FILE%"
)
goto :eof

:run_orchestrator
call :log_info "Starting Claude Code Orchestrator..."

REM Activate virtual environment if not already active
if not defined VIRTUAL_ENV (
    if exist "%VENV_DIR%\Scripts\activate.bat" (
        call "%VENV_DIR%\Scripts\activate.bat"
    ) else (
        call :log_error "Virtual environment not found. Run setup first."
        exit /b 1
    )
)

REM Run the orchestrator with all remaining arguments
set "ARGS="
:build_args
if "%~1"=="" goto :run_python
set "ARGS=%ARGS% %~1"
shift
goto :build_args

:run_python
python "%PYTHON_SCRIPT%" %ARGS%
goto :eof

:resume_execution
call :log_info "Resuming execution from last checkpoint..."
call :run_orchestrator --resume
goto :eof

:validate_milestones
call :log_info "Validating milestones..."
call :run_orchestrator --validate-only
goto :eof

:show_status
echo.
echo === Claude Code Orchestrator Status ===
echo.

REM Check virtual environment
if exist "%VENV_DIR%" (
    echo [OK] Virtual environment: Ready
) else (
    echo [!!] Virtual environment: Not setup
)

REM Check configuration
if exist "%CONFIG_FILE%" (
    echo [OK] Configuration: Found
) else (
    echo [!!] Configuration: Using defaults
)

REM Check milestones directory
if exist "milestones" (
    set "milestone_count=0"
    for %%f in (milestones\*.md) do (
        set /a milestone_count+=1
    )
    echo [OK] Milestones: !milestone_count! found
) else (
    echo [!!] Milestones: Directory not found
)

REM Check state file
if exist "%STATE_FILE%" (
    echo [INFO] Execution state: Found ^(can resume^)
) else (
    echo [INFO] Execution state: Clean start
)

REM Check log file
if exist "%LOG_FILE%" (
    for %%i in ("%LOG_FILE%") do set "log_size=%%~zi"
    echo [INFO] Log file: !log_size! bytes
)

REM Git repository status
git rev-parse --git-dir >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('git branch --show-current 2^>nul') do set "current_branch=%%i"
    if defined current_branch (
        echo [OK] Git repository: !current_branch!
    ) else (
        echo [OK] Git repository: Detected
    )
    
    REM Check for worktrees
    for /f %%i in ('git worktree list 2^>nul ^| find /c /v ""') do set "worktree_count=%%i"
    if !worktree_count! gtr 1 (
        set /a "active_worktrees=!worktree_count!-1"
        echo [INFO] Active worktrees: !active_worktrees!
    )
) else (
    echo [!!] Git repository: Not initialized
)

echo.
goto :eof

:cleanup
call :log_info "Cleaning up..."

REM Remove state file
if exist "%STATE_FILE%" (
    del /f "%STATE_FILE%" 2>nul
    call :log_info "Removed state file"
)

REM Cleanup worktrees
git rev-parse --git-dir >nul 2>&1
if not errorlevel 1 (
    call :log_info "Cleaning up worktrees..."
    for /f "tokens=2" %%i in ('git worktree list --porcelain 2^>nul ^| findstr "^worktree"') do (
        echo %%i | findstr "milestone-" >nul
        if not errorlevel 1 (
            call :log_info "Removing worktree: %%i"
            git worktree remove "%%i" --force >nul 2>&1
        )
    )
)

REM Clean Python cache
if exist "__pycache__" rmdir /s /q "__pycache__" 2>nul
for /r . %%d in (__pycache__) do if exist "%%d" rmdir /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul

call :log_info "Cleanup complete"
goto :eof

:show_help
echo Claude Code Orchestrator - Windows Interface
echo.
echo Usage: %~nx0 [COMMAND] [OPTIONS]
echo.
echo Commands:
echo   setup           Setup virtual environment and dependencies
echo   run             Run the orchestrator with default settings
echo   resume          Resume execution from last checkpoint
echo   validate        Validate milestone files without execution
echo   status          Show current system status
echo   cleanup         Clean up state files and temporary data
echo   help            Show this help message
echo.
echo Options:
echo   --config FILE   Use specific configuration file
echo   --stage N       Execute only stage N
echo   --milestone ID  Execute only specific milestone
echo   --dry-run       Show execution plan without running
echo.
echo Examples:
echo   %~nx0 setup                    # Initial setup
echo   %~nx0 run                      # Run all milestones
echo   %~nx0 run --stage 1            # Run only stage 1
echo   %~nx0 run --milestone 1A       # Run only milestone 1A
echo   %~nx0 resume                   # Resume from checkpoint
echo   %~nx0 validate                 # Validate milestones
echo   %~nx0 status                   # Show status
echo   %~nx0 cleanup                  # Clean up
echo.
goto :eof

:interactive_menu
:menu_loop
echo.
echo === Claude Code Orchestrator ===
echo 1. Show Status
echo 2. Setup Environment
echo 3. Validate Milestones
echo 4. Run All Milestones
echo 5. Resume Execution
echo 6. Run Specific Stage
echo 7. Run Specific Milestone
echo 8. Cleanup
echo 9. Exit
echo.
set /p "choice=Choose an option (1-9): "

if "%choice%"=="1" (
    call :show_status
    goto :menu_loop
)
if "%choice%"=="2" (
    call :check_dependencies && call :setup_virtual_environment && call :create_default_config
    goto :menu_loop
)
if "%choice%"=="3" (
    call :validate_milestones
    goto :menu_loop
)
if "%choice%"=="4" (
    call :run_orchestrator
    goto :menu_loop
)
if "%choice%"=="5" (
    call :resume_execution
    goto :menu_loop
)
if "%choice%"=="6" (
    set /p "stage_num=Enter stage number: "
    call :run_orchestrator --stage !stage_num!
    goto :menu_loop
)
if "%choice%"=="7" (
    set /p "milestone_id=Enter milestone ID: "
    call :run_orchestrator --milestone !milestone_id!
    goto :menu_loop
)
if "%choice%"=="8" (
    call :cleanup
    goto :menu_loop
)
if "%choice%"=="9" (
    call :log_info "Goodbye!"
    goto :eof
)

call :log_error "Invalid option: %choice%"
goto :menu_loop

:parse_args
REM Change to script directory
cd /d "%SCRIPT_DIR%"

REM Parse command line arguments
if "%~1"=="" (
    REM No arguments - start interactive mode
    call :interactive_menu
    goto :eof
)

if /i "%~1"=="setup" (
    call :check_dependencies && call :setup_virtual_environment && call :create_default_config
    goto :eof
)

if /i "%~1"=="run" (
    shift
    call :run_orchestrator %*
    goto :eof
)

if /i "%~1"=="resume" (
    call :resume_execution
    goto :eof
)

if /i "%~1"=="validate" (
    call :validate_milestones
    goto :eof
)

if /i "%~1"=="status" (
    call :show_status
    goto :eof
)

if /i "%~1"=="cleanup" (
    call :cleanup
    goto :eof
)

if /i "%~1"=="help" (
    call :show_help
    goto :eof
)

if /i "%~1"=="--help" (
    call :show_help
    goto :eof
)

if /i "%~1"=="-h" (
    call :show_help
    goto :eof
)

call :log_error "Unknown command: %~1"
call :show_help
exit /b 1