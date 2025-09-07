# Claude Code Orchestrator

A powerful orchestration system for managing Claude Code development with parallel task execution, automatic resumption, and comprehensive monitoring.

## 🚀 Features

- **Parallel Execution**: Run multiple Claude Code instances for tasks within a stage
- **Sequential Stages**: Ensure proper dependency ordering between stages
- **Git Worktree Isolation**: Each task runs in its own isolated environment
- **Auto-Resume**: Automatically retry when rate limits are lifted
- **Code Review Loop**: Automated review and remediation cycle
- **Progress Tracking**: Real-time updates to TASKS.md
- **Resource Monitoring**: Track system resources to prevent overload
- **Cross-Platform**: Works on Windows, WSL, macOS, and Linux

## 📋 Prerequisites

### Required Software
- Python 3.8 or higher
- Git 2.15 or higher (for worktree support)
- Node.js and npm (for Claude Code)
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)

### System Requirements
- Minimum 8GB RAM (16GB recommended for parallel execution)
- At least 10GB free disk space
- Windows 10/11, macOS 10.15+, or Linux (Ubuntu 20.04+)

## 🔧 Installation

### Windows (Command Prompt/PowerShell)

```cmd
# Clone or create your project directory
cd D:\Test\claude-milestones

# Run the setup script
setup.bat setup

# This will:
# - Check all dependencies
# - Create virtual environment
# - Install Python packages
# - Create necessary directories
```

### Windows (WSL/Git Bash)

```bash
# Clone or create your project directory
cd /mnt/d/Test/claude-milestones

# Make the script executable
chmod +x orchestrator.sh

# Run setup
./orchestrator.sh setup
```

### macOS/Linux

```bash
# Clone or create your project directory
cd ~/projects/claude-milestones

# Make the script executable
chmod +x orchestrator.sh

# Run setup
./orchestrator.sh setup
```

## 📁 Project Structure

```
claude-milestones/
├── orchestrator.py          # Main orchestrator script
├── advanced.py              # Advanced features module
├── orchestrator.sh          # Unix/WSL shell script
├── setup.bat                # Windows batch script
├── orchestrator.config.json # Configuration file
├── requirements.txt         # Python dependencies
├── milestones/             # Milestone definitions
│   ├── 1A.md               # Stage 1, Task A
│   ├── 1B.md               # Stage 1, Task B
│   └── ...
├── .worktree/              # Git worktrees (auto-created)
├── logs/                   # Execution logs (auto-created)
└── TASKS.md                # Progress tracking

```

## 🎯 Usage

### Quick Start

#### Windows Command Prompt
```cmd
# Run all milestones
setup.bat run

# Check status
setup.bat status

# Clean up worktrees
setup.bat clean

# View help
setup.bat help
```

#### WSL/Git Bash/Unix
```bash
# Run all milestones (with auto-resume)
./orchestrator.sh run

# Run single execution (no auto-resume)
./orchestrator.sh single

# Interactive menu
./orchestrator.sh

# Check status
./orchestrator.sh status

# Clean up worktrees
./orchestrator.sh clean
```

### Direct Python Usage
```bash
# Activate virtual environment first
# Windows: venv\Scripts\activate
# Unix: source venv/bin/activate

# Run all milestones
python orchestrator.py

# Run specific stage
python orchestrator.py --stage 1

# Run specific milestone
python orchestrator.py --milestone 1A

# Resume from checkpoint
python orchestrator.py --resume

# Validate only (no execution)
python orchestrator.py --validate-only

# Show help
python orchestrator.py --help
```

### Advanced Usage

#### Custom Configuration
Edit `orchestrator.config.json` to customize:
```json
{
  "max_parallel_tasks": 4,        # Number of parallel tasks
  "claude_rate_limit_wait": 300,  # Wait time when rate limited (seconds)
  "auto_resume": true,            # Enable auto-resume
  "retry_attempts": 10,           # Max retry attempts
  "logging": {
    "level": "INFO",             # Logging level
    "log_dir": "./logs"          # Log directory
  }
}
```

#### Environment Variables
```bash
# Set custom config file
export ORCHESTRATOR_CONFIG=my-config.json

# Set log level
export LOG_LEVEL=DEBUG

# Disable auto-resume
export AUTO_RESUME=false
```

## 📝 Creating Milestones

Milestones follow a specific naming pattern: `{STAGE}{TASK}.md`
- Stage: Single digit (1-9)
- Task: Single uppercase letter (A-Z)

Example milestone structure (`milestones/1A.md`):
```markdown
# Milestone 1A - Initial Setup

## Description
Create the foundational project structure and configuration.

## Entry Requirements
- Git repository initialized
- Node.js and Python installed

## Tasks
1. Create project directory structure
2. Initialize package.json
3. Setup configuration files
4. Create README.md

## Exit Criteria
- All files created and committed
- Tests pass
- Documentation updated

## Dependencies
- None (first milestone)

## Estimated Time
2 hours
```

## 🔄 Execution Flow

1. **Stage Discovery**: Finds the next unimplemented stage
2. **Requirements Check**: Validates prerequisites are met
3. **Parallel Task Execution**: 
   - Creates worktrees for each task in the stage
   - Runs Claude Code with milestone command
   - Commits changes automatically
4. **Code Review**: Performs automated review
5. **Remediation**: Implements fixes if review fails
6. **Merge**: Combines all task branches
7. **Documentation**: Updates TASKS.md
8. **Repeat**: Continues to next stage

## 🛠️ Troubleshooting

### Common Issues

#### Rate Limiting
```bash
# The orchestrator handles rate limiting automatically
# To adjust wait time, edit orchestrator.config.json:
"claude_rate_limit_wait": 600  # Wait 10 minutes instead of 5
```

#### Git Worktree Issues
```bash
# Clean up all worktrees
./orchestrator.sh clean
# or on Windows:
setup.bat clean

# Manual cleanup
git worktree prune
rm -rf .worktree/*
```

#### Python Dependencies
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Update pip
python -m pip install --upgrade pip
```

#### Permission Issues (Unix/WSL)
```bash
# Make scripts executable
chmod +x orchestrator.sh
chmod +x orchestrator.py
chmod +x advanced.py
```

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python orchestrator.py

# Or edit config:
"logging": {
  "level": "DEBUG"
}
```

## 📊 Monitoring

### View Logs
```bash
# Recent logs
ls -la logs/

# View specific log
tail -f logs/orchestrator_20240907_143022.log

# View metrics
cat logs/metrics.json | jq '.'
```

### Check Progress
```bash
# View task status
cat TASKS.md

# Check git status
git status

# List worktrees
git worktree list
```

## 🔐 Security Considerations

- Never commit sensitive data or API keys
- The `.gitignore` file excludes sensitive files
- Use environment variables for credentials
- Review code before automated commits

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request

## 📄 License

This project is provided as-is for use with Claude Code development.

## 🆘 Support

For issues or questions:
1. Check the logs in `./logs/`
2. Verify all dependencies are installed
3. Ensure Claude Code CLI is properly configured
4. Review the troubleshooting section

## 🔮 Advanced Features

### Rate Limit Manager
- Tracks API rate limits
- Implements exponential backoff
- Persists state for resumption

### System Monitor
- Monitors CPU, memory, and disk usage
- Prevents system overload
- Logs performance metrics

### Worktree Manager
- Safe worktree creation
- Automatic cleanup of stale worktrees
- Validation of worktree health

### Milestone Validator
- Validates milestone completion
- Checks test results
- Ensures code quality standards

---

Built for efficient Claude Code development orchestration 🚀