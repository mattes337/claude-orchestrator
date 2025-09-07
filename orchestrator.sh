#!/bin/bash

# Claude Code Orchestrator - Shell Script
# Provides setup, execution, and management functionality for WSL/Git Bash environments

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
CONFIG_FILE="${SCRIPT_DIR}/orchestrator.config.json"
STATE_FILE="${SCRIPT_DIR}/orchestrator_state.json"
LOG_FILE="${SCRIPT_DIR}/orchestrator.log"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements.txt"
PYTHON_SCRIPT="${SCRIPT_DIR}/orchestrator.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a "${LOG_FILE}"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "${LOG_FILE}"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "${LOG_FILE}"
}

log_debug() {
    if [[ "${DEBUG:-}" == "1" ]]; then
        echo -e "${BLUE}[DEBUG]${NC} $1" | tee -a "${LOG_FILE}"
    fi
}

# Utility functions
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "Required command not found: $1"
        return 1
    fi
}

check_dependencies() {
    log_info "Checking dependencies..."
    
    local missing_deps=()
    
    # Check Python
    if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
        missing_deps+=("python3")
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
        missing_deps+=("pip")
    fi
    
    # Check git
    if ! command -v git &> /dev/null; then
        missing_deps+=("git")
    fi
    
    # Check optional dependencies
    if ! command -v claude &> /dev/null; then
        log_warn "Claude Code CLI not found - some features may not work"
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing required dependencies: ${missing_deps[*]}"
        log_error "Please install them before continuing:"
        for dep in "${missing_deps[@]}"; do
            case $dep in
                python3)
                    echo "  - Install Python 3.8+: https://python.org/downloads"
                    ;;
                pip)
                    echo "  - Install pip: python -m ensurepip --upgrade"
                    ;;
                git)
                    echo "  - Install Git: https://git-scm.com/downloads"
                    ;;
            esac
        done
        return 1
    fi
    
    log_info "All required dependencies found"
    return 0
}

get_python_cmd() {
    if command -v python3 &> /dev/null; then
        echo "python3"
    elif command -v python &> /dev/null; then
        echo "python"
    else
        log_error "No Python interpreter found"
        return 1
    fi
}

setup_virtual_environment() {
    log_info "Setting up virtual environment..."
    
    local python_cmd
    python_cmd=$(get_python_cmd) || return 1
    
    if [[ ! -d "${VENV_DIR}" ]]; then
        log_info "Creating virtual environment..."
        ${python_cmd} -m venv "${VENV_DIR}"
    fi
    
    # Activate virtual environment
    source "${VENV_DIR}/bin/activate" || {
        log_error "Failed to activate virtual environment"
        return 1
    }
    
    # Upgrade pip
    log_info "Upgrading pip..."
    pip install --upgrade pip
    
    # Install requirements
    if [[ -f "${REQUIREMENTS_FILE}" ]]; then
        log_info "Installing Python dependencies..."
        pip install -r "${REQUIREMENTS_FILE}"
    else
        log_warn "Requirements file not found: ${REQUIREMENTS_FILE}"
        # Install minimal requirements
        pip install psutil
    fi
    
    log_info "Virtual environment setup complete"
}

create_default_config() {
    if [[ ! -f "${CONFIG_FILE}" ]]; then
        log_info "Creating default configuration..."
        cat > "${CONFIG_FILE}" << 'EOF'
{
  "milestones_dir": "milestones",
  "tasks_file": "TASKS.md",
  "execution": {
    "max_parallel_tasks": 4,
    "task_timeout": 1800,
    "max_retries": 3,
    "retry_delay": 30
  },
  "rate_limit": {
    "requests_per_minute": 50,
    "burst_limit": 10,
    "backoff_multiplier": 2
  },
  "git": {
    "use_worktrees": true,
    "base_branch": "main",
    "worktree_prefix": "milestone-"
  },
  "code_review": {
    "enabled": true,
    "auto_fix": true,
    "quality_threshold": 0.8
  },
  "notifications": {
    "enabled": false,
    "webhook_url": ""
  },
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  }
}
EOF
        log_info "Default configuration created: ${CONFIG_FILE}"
    fi
}

run_orchestrator() {
    local args=("$@")
    
    log_info "Starting Claude Code Orchestrator..."
    
    # Ensure virtual environment is activated
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        source "${VENV_DIR}/bin/activate" || {
            log_error "Failed to activate virtual environment"
            return 1
        }
    fi
    
    # Run the orchestrator
    python "${PYTHON_SCRIPT}" "${args[@]}"
}

resume_execution() {
    log_info "Resuming execution from last checkpoint..."
    run_orchestrator --resume
}

validate_milestones() {
    log_info "Validating milestones..."
    run_orchestrator --validate-only
}

show_status() {
    echo -e "\n${BLUE}=== Claude Code Orchestrator Status ===${NC}"
    
    # Check if virtual environment exists
    if [[ -d "${VENV_DIR}" ]]; then
        echo -e "${GREEN}✓${NC} Virtual environment: Ready"
    else
        echo -e "${RED}✗${NC} Virtual environment: Not setup"
    fi
    
    # Check configuration
    if [[ -f "${CONFIG_FILE}" ]]; then
        echo -e "${GREEN}✓${NC} Configuration: Found"
    else
        echo -e "${YELLOW}!${NC} Configuration: Using defaults"
    fi
    
    # Check milestones directory
    if [[ -d "milestones" ]]; then
        local milestone_count=$(find milestones -name "*.md" 2>/dev/null | wc -l)
        echo -e "${GREEN}✓${NC} Milestones: ${milestone_count} found"
    else
        echo -e "${RED}✗${NC} Milestones: Directory not found"
    fi
    
    # Check state file
    if [[ -f "${STATE_FILE}" ]]; then
        echo -e "${BLUE}i${NC} Execution state: Found (can resume)"
        
        # Show last execution info if available
        if command -v jq &> /dev/null; then
            local current_stage
            current_stage=$(jq -r '.current_stage // "N/A"' "${STATE_FILE}" 2>/dev/null)
            local completed_tasks
            completed_tasks=$(jq -r '.completed_tasks | length' "${STATE_FILE}" 2>/dev/null)
            echo -e "  Current stage: ${current_stage}"
            echo -e "  Completed tasks: ${completed_tasks}"
        fi
    else
        echo -e "${BLUE}i${NC} Execution state: Clean start"
    fi
    
    # Check log file
    if [[ -f "${LOG_FILE}" ]]; then
        local log_size=$(stat -c%s "${LOG_FILE}" 2>/dev/null || stat -f%z "${LOG_FILE}" 2>/dev/null || echo "Unknown")
        echo -e "${BLUE}i${NC} Log file: ${log_size} bytes"
    fi
    
    # Git repository status
    if git rev-parse --git-dir &> /dev/null; then
        local current_branch
        current_branch=$(git branch --show-current 2>/dev/null || echo "Unknown")
        echo -e "${GREEN}✓${NC} Git repository: ${current_branch}"
        
        # Check for worktrees
        local worktree_count
        worktree_count=$(git worktree list 2>/dev/null | wc -l)
        if [[ ${worktree_count} -gt 1 ]]; then
            echo -e "${BLUE}i${NC} Active worktrees: $((worktree_count - 1))"
        fi
    else
        echo -e "${YELLOW}!${NC} Git repository: Not initialized"
    fi
    
    echo ""
}

cleanup() {
    log_info "Cleaning up..."
    
    # Remove state file
    if [[ -f "${STATE_FILE}" ]]; then
        rm -f "${STATE_FILE}"
        log_info "Removed state file"
    fi
    
    # Cleanup worktrees
    if git rev-parse --git-dir &> /dev/null; then
        log_info "Cleaning up worktrees..."
        git worktree list --porcelain | grep "^worktree" | cut -d' ' -f2 | while read -r worktree; do
            if [[ "${worktree}" == *"milestone-"* ]]; then
                log_info "Removing worktree: ${worktree}"
                git worktree remove "${worktree}" --force 2>/dev/null || true
            fi
        done
    fi
    
    # Clean Python cache
    find . -name "*.pyc" -delete 2>/dev/null || true
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    
    log_info "Cleanup complete"
}

show_help() {
    cat << EOF
Claude Code Orchestrator - Shell Interface

Usage: $0 [COMMAND] [OPTIONS]

Commands:
  setup           Setup virtual environment and dependencies
  run             Run the orchestrator with default settings
  resume          Resume execution from last checkpoint
  validate        Validate milestone files without execution
  status          Show current system status
  cleanup         Clean up state files and temporary data
  help            Show this help message

Options:
  --config FILE   Use specific configuration file
  --stage N       Execute only stage N
  --milestone ID  Execute only specific milestone
  --dry-run       Show execution plan without running
  --debug         Enable debug output

Examples:
  $0 setup                    # Initial setup
  $0 run                      # Run all milestones
  $0 run --stage 1            # Run only stage 1
  $0 run --milestone 1A       # Run only milestone 1A
  $0 resume                   # Resume from checkpoint
  $0 validate                 # Validate milestones
  $0 status                   # Show status
  $0 cleanup                  # Clean up

Environment Variables:
  DEBUG=1                     Enable debug output
  PYTHON_CMD                  Override Python command
  
EOF
}

interactive_menu() {
    while true; do
        echo -e "\n${BLUE}=== Claude Code Orchestrator ===${NC}"
        echo "1. Show Status"
        echo "2. Setup Environment"
        echo "3. Validate Milestones"
        echo "4. Run All Milestones"
        echo "5. Resume Execution"
        echo "6. Run Specific Stage"
        echo "7. Run Specific Milestone"
        echo "8. Cleanup"
        echo "9. Exit"
        echo -n "Choose an option (1-9): "
        
        read -r choice
        
        case $choice in
            1)
                show_status
                ;;
            2)
                check_dependencies && setup_virtual_environment && create_default_config
                ;;
            3)
                validate_milestones
                ;;
            4)
                run_orchestrator
                ;;
            5)
                resume_execution
                ;;
            6)
                echo -n "Enter stage number: "
                read -r stage_num
                run_orchestrator --stage "${stage_num}"
                ;;
            7)
                echo -n "Enter milestone ID: "
                read -r milestone_id
                run_orchestrator --milestone "${milestone_id}"
                ;;
            8)
                cleanup
                ;;
            9)
                log_info "Goodbye!"
                exit 0
                ;;
            *)
                log_error "Invalid option: ${choice}"
                ;;
        esac
    done
}

# Signal handling
trap 'log_info "Script interrupted"; exit 130' INT TERM

# Main execution
main() {
    # Change to script directory
    cd "${SCRIPT_DIR}"
    
    # Parse command line arguments
    case "${1:-}" in
        setup)
            check_dependencies && setup_virtual_environment && create_default_config
            ;;
        run)
            shift
            run_orchestrator "$@"
            ;;
        resume)
            resume_execution
            ;;
        validate)
            validate_milestones
            ;;
        status)
            show_status
            ;;
        cleanup)
            cleanup
            ;;
        help|--help|-h)
            show_help
            ;;
        "")
            # No arguments - start interactive mode
            interactive_menu
            ;;
        *)
            log_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"