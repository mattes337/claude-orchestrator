# Claude Code Orchestrator

A powerful orchestration system for managing Claude Code development with parallel task execution, iterative code review, automatic git workflow, and comprehensive MCP server integration.

## 🚀 Key Features

### 🔄 **Advanced Code Review & Quality Gates**
- **Iterative Code Review**: After each milestone completion with automatic improvement loops
- **Quality Gates**: Configurable quality thresholds that must pass before progression
- **Auto-Fix Functionality**: Automatically addresses TODOs, quality issues, and failed gates
- **Markdown Reports**: Detailed review reports saved for each milestone and stage
- **Multi-Stage Validation**: Final comprehensive review after stage completion

### 🌳 **Intelligent Git Workflow**
- **Worktree Isolation**: Each milestone runs in isolated git worktrees for true parallelism
- **Automatic Commits**: Each worktree commits changes with detailed task summaries
- **Sequential Merging**: Worktrees merge systematically into root branch with conflict resolution
- **Stage Commits**: Complete stage commits to root branch with comprehensive change summaries
- **Branch Management**: Automated branch creation, merging, and cleanup

### 🔧 **MCP Server Integration**
- **Context7 MCP**: Documentation research, project context consultation, and best practices
- **Playwright MCP**: Browser testing, E2E testing, UI validation, and test automation
- **Aceternity MCP**: Modern UI design patterns, component libraries, and styling guidance
- **Smart Task Routing**: Automatically leverages appropriate MCP servers based on task content

### ⚡ **Parallel Execution & Orchestration**
- **Universal Milestone Format Support**: Automatically processes any milestone format without requiring specific schemas
- **Intelligent Preprocessing**: Detects and normalizes different milestone structures (Task sections, Technical Requirements, Objectives)
- **Parallel Stage Execution**: Run multiple milestone worktrees simultaneously within a stage
- **Sequential Stages**: Ensure proper dependency ordering between stages
- **Auto-Resume**: Automatically retry when rate limits are lifted
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

### Global Installation (Recommended)

Install the orchestrator globally to use it from any project directory:

```bash
# Clone or navigate to the orchestrator directory
cd D:\Test\claude-milestones  # Windows
cd ~/claude-milestones         # macOS/Linux

# Install globally with pip
pip install .

# Or install in development mode (editable)
pip install -e .

# The command 'claude-orchestrator' will now be available globally
claude-orchestrator --help
```

**Note for Windows users**: After installation, you may need to add the Python Scripts directory to your PATH:
- Default location: `%LOCALAPPDATA%\Programs\Python\PythonXX\Scripts\`
- Or user location: `%APPDATA%\Python\PythonXX\Scripts\`

Alternatively, use the provided batch file:
```cmd
# Windows: Use the batch file directly
D:\Test\claude-milestones\claude-orchestrator.bat --help
```

### Local Installation

#### Windows (Command Prompt/PowerShell)

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

#### Windows (WSL/Git Bash)

```bash
# Clone or create your project directory
cd /mnt/d/Test/claude-milestones

# Make the script executable
chmod +x orchestrator.sh

# Run setup
./orchestrator.sh setup
```

#### macOS/Linux

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

### Quick Start with Global Command

If you've installed the orchestrator globally:

```bash
# Navigate to your project directory
cd /path/to/your/project

# Run all milestones
claude-orchestrator

# Run specific stage
claude-orchestrator --stage 2

# Run specific milestone
claude-orchestrator --milestone A1

# Dry run (show what would be executed)
claude-orchestrator --dry-run

# Validate milestone formats without execution
claude-orchestrator --validate-only

# Use custom config
claude-orchestrator --config custom.json

# Run in a different project directory
claude-orchestrator --project-dir /path/to/project
```

### Quick Start with Local Scripts

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
Edit `orchestrator.config.json` to customize all features:
```json
{
  "milestones_dir": "milestones",
  "tasks_file": "TASKS.md", 
  "execution": {
    "max_parallel_tasks": 4,        # Number of parallel milestones
    "task_timeout": 1800,           # Task timeout in seconds
    "max_retries": 3,               # Max retry attempts
    "retry_delay": 30               # Delay between retries
  },
  "rate_limit": {
    "requests_per_minute": 50,      # API rate limit
    "burst_limit": 10,              # Burst request limit
    "backoff_multiplier": 2         # Exponential backoff multiplier
  },
  "git": {
    "use_worktrees": true,          # Enable worktree isolation
    "base_branch": "main",          # Base branch for merging
    "worktree_prefix": "milestone-" # Prefix for worktree directories
  },
  "code_review": {
    "enabled": true,                # Enable code review system
    "auto_fix": true,               # Enable automatic issue fixing
    "quality_threshold": 0.8,       # Minimum quality score (0.0-1.0)
    "max_iterations": 3             # Max review/fix iterations
  },
  "mcp_servers": {
    "enabled": true,                # Enable MCP server integration
    "context7": {
      "enabled": true,              # Enable Context7 for documentation
      "use_for": ["documentation", "research", "context"]
    },
    "playwright": {
      "enabled": true,              # Enable Playwright for testing
      "use_for": ["browser_testing", "e2e_testing", "ui_testing"]
    },
    "aceternity": {
      "enabled": true,              # Enable Aceternity for UI design
      "use_for": ["ui_design", "components", "styling"]
    }
  },
  "logging": {
    "level": "INFO",                # Logging level
    "log_dir": "./logs"             # Log directory
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

### Flexible Milestone Formats

The orchestrator now supports **any reasonable milestone format** thanks to intelligent preprocessing! You can use any of these formats:

#### Format 1: Traditional Task Sections
```markdown
# Milestone 1A - Initial Setup

## Description
Create the foundational project structure and configuration.

## Task 1: Create Project Structure
Design and implement the basic project layout with necessary directories.

**Deliverables:**
- Create src/, docs/, tests/ directories
- Setup package.json and configuration files
- Initialize README.md

## Task 2: Setup Build System
Configure build tools and scripts.

**Deliverables:**
- Configure webpack/build tools
- Setup npm scripts
- Create development environment
```

#### Format 2: Technical Requirements
```markdown
# Milestone 1B - Database Integration

## Overview
Implement database connectivity and basic operations.

## Technical Requirements

### 1. Database Connection
- Setup database connection pool
- Configure environment-specific settings
- Implement connection health checks
- Add error handling and retry logic

### 2. Data Models
- Create user data model
- Implement CRUD operations
- Add data validation
- Setup database migrations

### 3. Integration Testing
- Write integration tests
- Setup test database
- Create test fixtures
```

#### Format 3: Simple Objectives
```markdown
# Milestone 1C - Authentication System

## Overview
Add user authentication and authorization.

## Objectives
- Implement user registration functionality
- Add login/logout endpoints  
- Create JWT token management
- Setup role-based access control
- Add password reset functionality
```

#### Format 4: Issues to Fix (Bug Fixes)
```markdown
# Milestone 1C - Slash Menu Bug Fixes

## Overview
This milestone addresses critical bugs in the slash menu functionality that prevent proper item insertion and image integration.

## Issues to Fix

### 1. Slash Menu Arrow Key Navigation Bug
**Problem**: When using the slash menu and navigating with arrow keys (down arrow), pressing Enter inserts a plain newline instead of the selected menu item.

**Expected Behavior**: Pressing Enter after navigating with arrow keys should insert the currently highlighted/selected menu item.

**Current Behavior**: A plain newline character is written to the editor instead of executing the menu item action.

### 2. AI Image Generation Not Working via Slash Menu
**Problem**: AI image generation feature does not open or add images when accessed through the slash menu.

**Expected Behavior**: Selecting AI image generation from the slash menu should open the AI image generation interface and allow users to generate and insert images.

**Current Behavior**: The AI image generation option in the slash menu is non-functional.

### 3. Image Browser Not Working via Slash Menu
**Problem**: Image browser does not open or add images when accessed through the slash menu.

**Expected Behavior**: Selecting the image browser from the slash menu should open the file browser interface and allow users to select and insert existing images.

**Current Behavior**: The image browser option in the slash menu is non-functional.

## Acceptance Criteria
- [ ] Slash menu arrow key navigation works correctly - pressing Enter after using arrow keys inserts the selected item
- [ ] AI image generation opens and functions properly when accessed via slash menu
- [ ] Image browser opens and functions properly when accessed via slash menu
- [ ] All existing slash menu functionality remains intact
- [ ] No regressions introduced to other editor features
```

### Automatic Task Extraction

The preprocessing system automatically:

- **Detects Task Sections**: Finds `## Task N:`, `## Task N -`, or numbered sections
- **Converts Requirements**: Transforms technical requirements into executable tasks
- **Extracts Objectives**: Uses objective lists as fallback tasks  
- **Processes Bug Reports**: Converts "Issues to Fix" sections with Problem/Expected structure into high-priority tasks
- **Normalizes Format**: Ensures consistent structure for the orchestrator
- **Preserves Content**: Maintains all original information and context

### Legacy Format Support

The traditional format is still fully supported:
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

### Best Practices

- **Clear Titles**: Use descriptive milestone and task titles
- **Specific Deliverables**: Define concrete outputs for each task
- **Proper Dependencies**: Document milestone relationships
- **Realistic Estimates**: Provide time estimates when possible
- **Bug Fix Format**: Use "Issues to Fix" with **Problem** and **Expected Behavior** for bug tracking
- **Any Format**: Use whatever markdown structure works best for your team!

## 🔄 Complete Execution Flow

### **Stage-Level Orchestration**
1. **Stage Discovery**: Discovers all milestones for the next unimplemented stage
2. **Worktree Preparation**: Creates isolated git worktrees for each milestone in the stage
3. **Parallel Execution**: Runs all milestones simultaneously within the stage

### **Milestone-Level Processing**  
4. **Requirements Check**: Validates prerequisites and dependencies are met
5. **Task Execution**: 
   - Runs Claude Code with MCP server integration
   - Leverages Context7, Playwright, and Aceternity as appropriate
   - Creates/modifies files with proper project structure
6. **Milestone Code Review**:
   - Comprehensive code review with quality gates
   - Iterative improvement loops with auto-fix
   - Quality score validation and TODO resolution
7. **Worktree Commit**: Commits all milestone changes with detailed summaries

### **Stage-Level Integration**
8. **Sequential Worktree Merging**: 
   - Merges each milestone worktree into root branch systematically
   - Handles merge conflicts and validates integration
   - Maintains clean commit history
9. **Final Stage Code Review**: 
   - Comprehensive review of integrated stage changes
   - Final quality validation and improvement loops
   - Stage-level quality gate verification
10. **Stage Commit**: Commits complete stage with comprehensive change summary
11. **Documentation**: Updates TASKS.md with milestone completion status
12. **Repeat**: Continues to next stage until all stages complete

### **Quality Gates & Review Process**
- **Milestone Quality Gates**: Code builds, tests pass, conventions followed, security validated
- **Iterative Improvement**: Auto-fix cycles continue until quality thresholds met
- **Stage Validation**: Final comprehensive review ensures integration quality
- **MCP Enhancement**: Context7, Playwright, and Aceternity provide specialized guidance

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

### **Code Review System**
- **Iterative Review Process**: Multi-pass code review with improvement cycles
- **Quality Score Calculation**: Numerical quality assessment (0.0 to 1.0)
- **TODO/FIXME Detection**: Automatic identification and tracking of code issues
- **Quality Gate Validation**: Configurable thresholds that must pass before progression
- **Auto-Fix Engine**: Automatically implements fixes for common code review issues
- **Markdown Report Generation**: Detailed review reports for each milestone and stage
- **MCP-Enhanced Review**: Leverages specialized MCP servers for thorough analysis

### **Git Workflow Management**
- **Worktree Orchestration**: Creates and manages isolated development environments
- **Automatic Commit Management**: Commits changes with detailed task summaries
- **Sequential Merge Strategy**: Systematic integration of parallel development streams
- **Branch Lifecycle Management**: Automated branch creation, merging, and cleanup
- **Conflict Resolution Support**: Handles merge conflicts during integration
- **Stage-Level Commits**: Comprehensive commits summarizing entire stage achievements

### **MCP Server Integration**
- **Context7 Integration**: Documentation research, best practices consultation, framework guidance
- **Playwright Integration**: Browser testing automation, E2E test scenarios, UI validation
- **Aceternity Integration**: Modern UI design patterns, component libraries, responsive layouts
- **Smart Task Routing**: Automatically determines which MCP servers to leverage based on task content
- **Enhanced Prompts**: All tasks and reviews include MCP server guidance for superior results

### **Milestone Preprocessor**
- **Universal Format Support**: Automatically detects and normalizes any milestone format
- **Smart Task Extraction**: Converts various structures (Tasks, Requirements, Objectives, Issues) into executable units
- **Pattern Recognition**: Supports multiple task definition patterns (`## Task N:`, `### N.`, `## Issues to Fix`, etc.)
- **Bug Fix Processing**: Specialized handling of "Issues to Fix" format with Problem/Expected Behavior extraction
- **Content Preservation**: Maintains all original milestone information and context
- **Backward Compatibility**: Works seamlessly with existing milestone files
- **Intelligent Prioritization**: Automatically assigns high priority to bug fixes and critical issues

### **System Management**
- **Rate Limit Manager**: Tracks API limits, implements exponential backoff, persists state for resumption
- **System Monitor**: Monitors CPU, memory, and disk usage; prevents system overload; logs performance metrics
- **Worktree Manager**: Safe worktree creation, automatic cleanup of stale worktrees, validation of worktree health
- **Milestone Validator**: Validates milestone completion, checks test results, ensures code quality standards

---

Built for efficient Claude Code development orchestration 🚀