#!/usr/bin/env python3
"""
Advanced Features Module for Claude Code Orchestrator
Contains specialized components for rate limiting, system monitoring, 
git worktree management, and Claude Code integration.
"""

import os
import sys
import time
import json
import logging
import subprocess
import threading
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import tempfile
import shutil
import re
import uuid

# Import shared types to avoid circular imports
from types_shared import ValidationResult, CodeReviewResult, TaskResult

class RateLimitManager:
    """Manages API rate limiting with intelligent backoff"""
    
    def __init__(self, requests_per_minute: int = 50, burst_limit: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.request_times = []
        self.burst_count = 0
        self.last_reset = time.time()
        self.lock = threading.Lock()
        
        # Dynamic adjustment
        self.consecutive_429s = 0
        self.adjustment_factor = 1.0
        
        logging.info(f"Rate limiter initialized: {requests_per_minute} req/min, burst: {burst_limit}")
    
    def wait_if_needed(self) -> float:
        """Wait if rate limit would be exceeded, returns wait time"""
        with self.lock:
            now = time.time()
            
            # Reset burst counter every minute
            if now - self.last_reset > 60:
                self.burst_count = 0
                self.last_reset = now
            
            # Clean old request times (keep only last minute)
            cutoff = now - 60
            self.request_times = [t for t in self.request_times if t > cutoff]
            
            # Check if we need to wait
            wait_time = 0
            
            # Check burst limit
            if self.burst_count >= self.burst_limit:
                wait_time = max(wait_time, 60 - (now - self.last_reset))
            
            # Check per-minute limit
            effective_limit = int(self.requests_per_minute * self.adjustment_factor)
            if len(self.request_times) >= effective_limit:
                oldest_request = min(self.request_times)
                wait_time = max(wait_time, 60 - (now - oldest_request))
            
            if wait_time > 0:
                logging.info(f"Rate limit waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                now = time.time()
            
            # Record this request
            self.request_times.append(now)
            self.burst_count += 1
            
            return wait_time
    
    def handle_rate_limit_response(self, status_code: int, headers: Dict[str, str]):
        """Handle rate limit response from API"""
        if status_code == 429:
            self.consecutive_429s += 1
            # Reduce rate by 20% for each consecutive 429
            self.adjustment_factor = max(0.1, self.adjustment_factor * 0.8)
            
            # Extract retry-after if available
            retry_after = headers.get('retry-after')
            if retry_after:
                wait_time = int(retry_after)
                logging.warning(f"Rate limited, waiting {wait_time}s (consecutive: {self.consecutive_429s})")
                time.sleep(wait_time)
        else:
            # Gradually restore rate if successful
            if self.consecutive_429s > 0:
                self.consecutive_429s = max(0, self.consecutive_429s - 1)
                self.adjustment_factor = min(1.0, self.adjustment_factor * 1.1)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current rate limiting statistics"""
        with self.lock:
            now = time.time()
            recent_requests = len([t for t in self.request_times if now - t < 60])
            
            return {
                "requests_last_minute": recent_requests,
                "burst_count": self.burst_count,
                "adjustment_factor": self.adjustment_factor,
                "consecutive_429s": self.consecutive_429s,
                "effective_rate": int(self.requests_per_minute * self.adjustment_factor)
            }

class SystemMonitor:
    """Monitors system resources and performance"""
    
    def __init__(self, cpu_threshold: float = 90.0, memory_threshold: float = 85.0, 
                 disk_threshold: float = 90.0):
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.disk_threshold = disk_threshold
        
        self.monitoring = False
        self.stats = {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "disk_percent": 0.0,
            "network_io": {"bytes_sent": 0, "bytes_recv": 0},
            "last_update": time.time()
        }
        
        # Start monitoring thread
        self.start_monitoring()
    
    def start_monitoring(self):
        """Start background monitoring thread"""
        def monitor_loop():
            while self.monitoring:
                try:
                    self.update_stats()
                    time.sleep(10)  # Update every 10 seconds
                except Exception as e:
                    logging.error(f"System monitoring error: {e}")
                    time.sleep(30)
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        logging.info("System monitoring started")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join(timeout=5)
    
    def update_stats(self):
        """Update system statistics"""
        try:
            # CPU usage
            self.stats["cpu_percent"] = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.stats["memory_percent"] = memory.percent
            
            # Disk usage (current directory)
            disk = psutil.disk_usage('.')
            self.stats["disk_percent"] = (disk.used / disk.total) * 100
            
            # Network I/O
            net_io = psutil.net_io_counters()
            if net_io:
                self.stats["network_io"] = {
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv
                }
            
            self.stats["last_update"] = time.time()
            
        except Exception as e:
            logging.error(f"Failed to update system stats: {e}")
    
    def check_resources(self) -> bool:
        """Check if system resources are within acceptable limits"""
        try:
            # Ensure we have recent stats
            if time.time() - self.stats["last_update"] > 30:
                self.update_stats()
            
            # Check thresholds
            if self.stats["cpu_percent"] > self.cpu_threshold:
                logging.warning(f"High CPU usage: {self.stats['cpu_percent']:.1f}%")
                return False
            
            if self.stats["memory_percent"] > self.memory_threshold:
                logging.warning(f"High memory usage: {self.stats['memory_percent']:.1f}%")
                return False
            
            if self.stats["disk_percent"] > self.disk_threshold:
                logging.warning(f"High disk usage: {self.stats['disk_percent']:.1f}%")
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"Resource check failed: {e}")
            return True  # Assume OK if check fails
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current system statistics"""
        return self.stats.copy()
    
    def wait_for_resources(self, max_wait: int = 300) -> bool:
        """Wait for system resources to become available"""
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if self.check_resources():
                return True
            
            logging.info("Waiting for system resources to become available...")
            time.sleep(30)
        
        logging.warning("Timeout waiting for system resources")
        return False

class WorktreeManager:
    """Manages git worktrees for parallel development"""
    
    def __init__(self, base_dir: str = ".worktrees"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.active_worktrees = {}
        
        # Verify git repository
        self.is_git_repo = self._check_git_repo()
        if not self.is_git_repo:
            logging.warning("Not in a git repository, worktree features disabled")
    
    def _check_git_repo(self) -> bool:
        """Check if current directory is a git repository"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True, text=True, check=True,
                encoding='utf-8', errors='replace',
                cwd=os.getcwd()
            )
            return True
        except subprocess.CalledProcessError:
            return False
    
    def create_worktree(self, name: str, base_branch: str = "main", 
                       prefix: str = "milestone-") -> str:
        """Create a new git worktree"""
        if not self.is_git_repo:
            raise RuntimeError("Not in a git repository")
        
        worktree_name = f"{prefix}{name}"
        worktree_path = self.base_dir / worktree_name
        
        # Remove existing worktree if it exists
        if worktree_path.exists():
            self.cleanup_worktree(str(worktree_path))
        
        try:
            # Create new branch
            branch_name = f"milestone/{name}"
            
            # Delete existing branch if it exists
            try:
                subprocess.run(
                    ["git", "branch", "-D", branch_name],
                    capture_output=True, encoding='utf-8', errors='replace',
                    cwd=os.getcwd()
                )
                logging.info(f"Deleted existing branch: {branch_name}")
            except subprocess.CalledProcessError:
                # Branch doesn't exist, which is fine
                pass
            
            subprocess.run(
                ["git", "checkout", base_branch],
                check=True, capture_output=True,
                encoding='utf-8', errors='replace',
                cwd=os.getcwd()
            )
            
            # Create worktree using correct syntax: git worktree add -b "branch" path
            subprocess.run([
                "git", "worktree", "add", "-b", branch_name, str(worktree_path)
            ], check=True, capture_output=True, encoding='utf-8', errors='replace',
               cwd=os.getcwd())
            
            self.active_worktrees[name] = {
                "path": str(worktree_path),
                "branch": branch_name,
                "created": datetime.now().isoformat()
            }
            
            logging.info(f"Created worktree: {worktree_path} ({branch_name})")
            return str(worktree_path)
            
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to create worktree {worktree_name}: {e}")
            raise
    
    def cleanup_worktree(self, worktree_path: str):
        """Remove a git worktree"""
        if not self.is_git_repo:
            return
        
        try:
            path = Path(worktree_path)
            
            # Remove worktree
            subprocess.run([
                "git", "worktree", "remove", str(path), "--force"
            ], check=True, capture_output=True, encoding='utf-8', errors='replace',
               cwd=os.getcwd())
            
            # Remove from active tracking
            for name, info in list(self.active_worktrees.items()):
                if info["path"] == str(path):
                    del self.active_worktrees[name]
                    break
            
            logging.debug(f"Cleaned up worktree: {worktree_path}")
            
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to cleanup worktree {worktree_path}: {e}")
            # Try manual cleanup
            if path.exists():
                try:
                    shutil.rmtree(path)
                except Exception as e2:
                    logging.error(f"Manual cleanup also failed: {e2}")
    
    def cleanup_all(self):
        """Cleanup all active worktrees"""
        for name, info in list(self.active_worktrees.items()):
            self.cleanup_worktree(info["path"])
    
    def get_worktree_info(self, name: str) -> Optional[Dict[str, str]]:
        """Get information about a worktree"""
        return self.active_worktrees.get(name)
    
    def list_worktrees(self) -> List[Dict[str, str]]:
        """List all active worktrees"""
        return list(self.active_worktrees.values())

class ClaudeCodeWrapper:
    """Wrapper for Claude Code CLI interactions"""
    
    def __init__(self, claude_path: str = "claude"):
        # Try to find the full path to claude command
        import shutil
        if claude_path == "claude":
            # Try to find claude in PATH
            found_path = shutil.which("claude")
            if found_path:
                self.claude_path = found_path
            else:
                # Try common Windows locations
                possible_paths = [
                    "C:/Users/MatthiasHelling/AppData/Roaming/npm/claude.cmd",
                    "C:/Users/MatthiasHelling/AppData/Roaming/npm/claude",
                    "claude.cmd",
                    "claude"
                ]
                self.claude_path = claude_path
                for path in possible_paths:
                    if shutil.which(path):
                        self.claude_path = path
                        break
        else:
            self.claude_path = claude_path
            
        self.session_id = None
        self.default_timeout = 300
        
        # Verify Claude Code is available
        self.is_available = self._check_claude_availability()
        if not self.is_available:
            logging.warning(f"Claude Code CLI not available at path: {self.claude_path}")
    
    def _check_claude_availability(self) -> bool:
        """Check if Claude Code CLI is available"""
        try:
            # On Windows, we might need shell=True
            import platform
            use_shell = platform.system() == "Windows"
            
            result = subprocess.run([self.claude_path, "--version"], 
                                  capture_output=True, text=True, timeout=10,
                                  shell=use_shell, encoding='utf-8', errors='replace')
            return result.returncode == 0
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logging.debug(f"Claude availability check failed: {e}")
            return False
    
    def execute_task(self, task: Dict[str, Any], worktree_path: Optional[str] = None, 
                    timeout: int = 300) -> 'TaskResult':
        """Execute a task using Claude Code"""
        # TaskResult is now imported from types_shared
        
        if not self.is_available:
            error_msg = f"Claude Code CLI not available at path: {self.claude_path}"
            logging.error(error_msg)
            return TaskResult(
                task["id"], False, 
                error=error_msg
            )
        
        task_id = task["id"]
        start_time = time.time()
        
        try:
            # Prepare task prompt
            prompt = self._prepare_task_prompt(task)
            
            # Change to worktree directory if provided
            original_cwd = os.getcwd()
            if worktree_path and os.path.exists(worktree_path):
                os.chdir(worktree_path)
                logging.debug(f"Changed to worktree: {worktree_path}")
            
            try:
                # Execute Claude Code command
                result = self._execute_claude_command(prompt, timeout)
                
                # Analyze result
                success = self._analyze_result(result, task)
                
                duration = time.time() - start_time
                
                if success:
                    return TaskResult(
                        task_id, True, 
                        output=result.get("output", ""),
                        duration=duration
                    )
                else:
                    return TaskResult(
                        task_id, False,
                        output=result.get("output", ""),
                        error=result.get("error", "Task execution failed"),
                        duration=duration
                    )
            
            finally:
                # Restore original directory
                if worktree_path:
                    os.chdir(original_cwd)
        
        except Exception as e:
            duration = time.time() - start_time
            return TaskResult(
                task_id, False,
                error=str(e),
                duration=duration
            )
    
    def _prepare_task_prompt(self, task: Dict[str, Any]) -> str:
        """Prepare Claude Code prompt for task"""
        task_title = task['title']
        requirements = task.get('requirements', 'No specific requirements provided')
        acceptance_criteria = task.get('acceptance_criteria', 'No specific criteria provided')
        task_id = task.get('id', 'unknown')
        milestone_id = task.get('milestone_id', 'unknown')
        
        # Generate specific, actionable prompt that instructs Claude CLI to create files
        prompt = f"""You must implement: {task_title}

TASK ID: {task_id}
MILESTONE: {milestone_id}

REQUIREMENTS:
{requirements}

ACCEPTANCE CRITERIA:
{acceptance_criteria}

CRITICAL INSTRUCTIONS:
1. You MUST create actual files using Write, Edit, or MultiEdit tools
2. You MUST NOT just provide code examples or explanations
3. File creation is REQUIRED for this task to be considered complete
4. Use appropriate file paths based on the project structure

SPECIFIC ACTIONS REQUIRED:
- If this is a component task, create the component file in the appropriate directory (e.g., src/components/)
- If this involves configuration, create or modify configuration files
- If this involves tests, create test files in the appropriate test directory
- If this involves documentation, create or update relevant documentation files

MCP SERVERS AVAILABLE:
Use the following MCP servers when appropriate for enhanced capabilities:

🔍 CONTEXT7 MCP - For documentation and research:
- Use when you need to consult documentation or research best practices
- Helpful for understanding project context and standards
- Use for gathering information about frameworks, libraries, and patterns

🎭 PLAYWRIGHT MCP - For browser testing and E2E testing:
- Use when implementing testing functionality
- Essential for UI testing, browser automation, and end-to-end tests
- Use for creating test scenarios and validating user interactions

🎨 ACETERNITY MCP - For UI design and components:
- Use when creating UI components or styling
- Provides modern design patterns and component libraries
- Use for implementing responsive layouts and beautiful interfaces

IMPLEMENTATION STEPS:
1. Analyze the current project structure using available tools
2. Determine which MCP servers would be most helpful for this task
3. Use relevant MCP servers for research, testing, or design guidance
4. Determine the exact file paths needed for implementation
5. Create or modify files using Write/Edit/MultiEdit tools
6. Ensure all created files follow the project's conventions and structure
7. If implementing UI components, leverage Aceternity MCP for modern designs
8. If implementing testing, use Playwright MCP for comprehensive test coverage
9. Use Context7 MCP for documentation consultation when needed
10. Verify that your implementation meets all requirements and acceptance criteria

IMPORTANT: This task will ONLY be marked as successful if you actually create or modify files. Simply acknowledging the task or providing code snippets without creating files will result in task failure.

Begin implementation now using the appropriate file creation tools and MCP servers."""
        
        return prompt
    
    def _execute_claude_command(self, prompt: str, timeout: int) -> Dict[str, Any]:
        """Execute Claude Code command with prompt"""
        try:
            # Write prompt to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(prompt)
                prompt_file = f.name
            
            try:
                # Execute claude command with correct syntax
                # Read the prompt from file and pass it directly
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_content = f.read()
                
                cmd = [self.claude_path, "--print", prompt_content]
                import platform
                use_shell = platform.system() == "Windows"
                
                logging.debug(f"Executing Claude command: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                    shell=use_shell,
                    encoding='utf-8',
                    errors='replace'  # Replace invalid characters instead of failing
                )
                
                logging.debug(f"Command completed with return code: {result.returncode}")
                if result.stderr:
                    logging.debug(f"Command stderr: {result.stderr[:200]}")
                
                return {
                    "returncode": result.returncode,
                    "output": result.stdout,
                    "error": result.stderr
                }
            
            finally:
                # Cleanup prompt file
                try:
                    os.unlink(prompt_file)
                except Exception:
                    pass
        
        except subprocess.TimeoutExpired:
            return {
                "returncode": 124,
                "output": "",
                "error": f"Command timed out after {timeout}s"
            }
        except Exception as e:
            return {
                "returncode": 1,
                "output": "",
                "error": str(e)
            }
    
    def _analyze_result(self, result: Dict[str, Any], task: Dict[str, Any]) -> bool:
        """Analyze Claude Code execution result"""
        if result["returncode"] != 0:
            return False
        
        output = result.get("output", "")
        
        # Check for common success indicators
        success_indicators = [
            "Task completed successfully",
            "Implementation complete",
            "All tests passing",
            "[SUCCESS]",
            "Success"
        ]
        
        # Check for error indicators
        error_indicators = [
            "Error:",
            "Failed:",
            "Exception:",
            "[ERROR]",
            "FAILED"
        ]
        
        # Simple heuristic analysis
        has_success = any(indicator in output for indicator in success_indicators)
        has_errors = any(indicator in output for indicator in error_indicators)
        
        # If we have explicit success indicators and no errors, consider successful
        if has_success and not has_errors:
            return True
        
        # If we have errors but no success, consider failed
        if has_errors and not has_success:
            return False
        
        # Otherwise, assume success if the command completed without error
        return len(output.strip()) > 0
    
    def execute_milestone_directly(self, milestone_content: str, milestone_id: str, timeout: int = 300) -> 'TaskResult':
        """Execute a milestone directly by sending the full milestone content to Claude"""
        from types_shared import TaskResult
        
        if not self.is_available:
            error_msg = f"Claude Code CLI not available at path: {self.claude_path}"
            logging.error(error_msg)
            return TaskResult(
                milestone_id, False, 
                error=error_msg
            )
        
        start_time = time.time()
        
        try:
            # Prepare milestone prompt for Claude
            prompt = f"""
You are tasked with implementing the following milestone for the travelflow-backend project. 
Please analyze the milestone requirements and implement all necessary changes.

MILESTONE CONTENT:
{milestone_content}

Please:
1. Read and understand the milestone requirements
2. Implement all necessary code, configuration, and setup
3. Follow the acceptance criteria specified in the milestone
4. Create any required files and directories
5. Ensure all dependencies are properly configured
6. Test that the implementation works as expected

Work within the current directory and implement the milestone completely.
"""
            
            try:
                # Execute Claude Code command with the milestone prompt
                result = self._execute_claude_command(prompt, timeout)
                
                # Analyze result - for milestone execution, we assume success if Claude completed
                success = result.returncode == 0 and len(result.stdout.strip()) > 0
                
                execution_time = time.time() - start_time
                logging.info(f"Milestone {milestone_id} executed in {execution_time:.2f}s")
                
                if success:
                    return TaskResult(
                        milestone_id, True,
                        output=result.stdout,
                        execution_time=execution_time
                    )
                else:
                    return TaskResult(
                        milestone_id, False,
                        error=result.stderr or "Unknown error during milestone execution",
                        output=result.stdout,
                        execution_time=execution_time
                    )
                    
            except subprocess.TimeoutExpired:
                error_msg = f"Milestone {milestone_id} execution timed out after {timeout} seconds"
                logging.error(error_msg)
                return TaskResult(
                    milestone_id, False,
                    error=error_msg,
                    execution_time=timeout
                )
                
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Error executing milestone {milestone_id}: {str(e)}"
            logging.error(error_msg)
            return TaskResult(
                milestone_id, False,
                error=error_msg,
                execution_time=execution_time
            )

class MilestoneValidator:
    """Validates milestone structure and completion"""
    
    def __init__(self):
        self.validation_rules = {
            "required_fields": ["id", "title", "tasks"],
            "task_required_fields": ["id", "title"],
            "valid_priorities": ["high", "medium", "low"],
            "max_tasks_per_milestone": 20,
            "min_description_length": 10
        }
    
    def validate_milestone_structure(self, milestone: Dict[str, Any]) -> ValidationResult:
        """Validate milestone structure and content"""
        result = ValidationResult(True, [], [])
        
        # Check required fields
        for field in self.validation_rules["required_fields"]:
            if field not in milestone or not milestone[field]:
                result.add_error(f"Missing required field: {field}")
        
        # Validate milestone ID format (more flexible)
        milestone_id = milestone.get("id", "")
        if not re.match(r'^[a-zA-Z0-9-_]+$', milestone_id):
            result.add_error(f"Invalid milestone ID format: {milestone_id}")
        
        # Check description length
        description = milestone.get("description", "")
        if len(description) < self.validation_rules["min_description_length"]:
            result.add_warning("Description is too short")
        
        # Validate tasks
        tasks = milestone.get("tasks", [])
        if not tasks:
            result.add_error("No tasks defined")
        elif len(tasks) > self.validation_rules["max_tasks_per_milestone"]:
            result.add_warning(f"Too many tasks ({len(tasks)}), consider splitting milestone")
        
        # Validate each task
        for i, task in enumerate(tasks):
            task_result = self.validate_task_structure(task, i)
            result.errors.extend(task_result.errors)
            result.warnings.extend(task_result.warnings)
            if not task_result.valid:
                result.valid = False
        
        # Calculate quality score
        result.score = self._calculate_quality_score(milestone, result)
        
        return result
    
    def validate_task_structure(self, task: Dict[str, Any], index: int) -> ValidationResult:
        """Validate individual task structure"""
        result = ValidationResult(True, [], [])
        
        # Check required fields
        for field in self.validation_rules["task_required_fields"]:
            if field not in task or not task[field]:
                result.add_error(f"Task {index}: Missing required field: {field}")
        
        # Validate task ID format (more flexible)
        task_id = task.get("id", "")
        if not re.match(r'^[a-zA-Z0-9-_]+-T\d+$', task_id):
            result.add_error(f"Task {index}: Invalid task ID format: {task_id}")
        
        # Validate priority
        priority = task.get("priority", "medium").lower()
        if priority not in self.validation_rules["valid_priorities"]:
            result.add_warning(f"Task {index}: Invalid priority: {priority}")
        
        # Check for requirements and acceptance criteria
        if not task.get("requirements"):
            result.add_warning(f"Task {index}: No requirements specified")
        
        if not task.get("acceptance_criteria"):
            result.add_warning(f"Task {index}: No acceptance criteria specified")
        
        return result
    
    def validate_milestone(self, milestone: Dict[str, Any], 
                          task_results: List['TaskResult']) -> ValidationResult:
        """Validate milestone completion against results"""
        # TaskResult is now imported from types_shared
        
        result = ValidationResult(True, [], [])
        
        # Check if all tasks have results
        milestone_tasks = {task["id"] for task in milestone.get("tasks", [])}
        result_tasks = {tr.task_id for tr in task_results}
        
        missing_results = milestone_tasks - result_tasks
        if missing_results:
            for task_id in missing_results:
                result.add_error(f"No result found for task: {task_id}")
        
        # Check success rate
        if task_results:
            successful_tasks = sum(1 for tr in task_results if tr.success)
            success_rate = successful_tasks / len(task_results)
            
            if success_rate < 0.8:
                result.add_error(f"Low success rate: {success_rate:.1%}")
            elif success_rate < 0.9:
                result.add_warning(f"Moderate success rate: {success_rate:.1%}")
            
            result.score = success_rate
        
        return result
    
    def _calculate_quality_score(self, milestone: Dict[str, Any], 
                                validation_result: ValidationResult) -> float:
        """Calculate milestone quality score"""
        base_score = 1.0
        
        # Deduct for errors
        error_penalty = len(validation_result.errors) * 0.2
        warning_penalty = len(validation_result.warnings) * 0.05
        
        # Bonus for good practices
        bonus = 0.0
        if milestone.get("description") and len(milestone["description"]) > 50:
            bonus += 0.1
        
        if milestone.get("dependencies"):
            bonus += 0.05
        
        tasks = milestone.get("tasks", [])
        if tasks:
            well_defined_tasks = sum(1 for task in tasks 
                                   if task.get("requirements") and task.get("acceptance_criteria"))
            if well_defined_tasks == len(tasks):
                bonus += 0.1
        
        score = max(0.0, min(1.0, base_score - error_penalty - warning_penalty + bonus))
        return score

class CodeReviewManager:
    """Manages code review processes with iterative improvement"""
    
    def __init__(self, claude_wrapper: ClaudeCodeWrapper, config: Dict = None):
        self.claude_wrapper = claude_wrapper
        self.config = config or {}
        self.max_iterations = self.config.get("code_review", {}).get("max_iterations", 3)
        self.quality_threshold = self.config.get("code_review", {}).get("quality_threshold", 0.8)
        self.auto_fix = self.config.get("code_review", {}).get("auto_fix", True)
        
    def conduct_code_review(self, milestone_id: str, worktree_path: Optional[str] = None, 
                          review_type: str = "milestone") -> CodeReviewResult:
        """Conduct comprehensive code review with iterative improvement"""
        logging.info(f"Starting code review for {review_type}: {milestone_id}")
        
        # Generate unique review ID
        review_id = f"{milestone_id}-{review_type}-{uuid.uuid4().hex[:8]}"
        report_file = f"code_review_{review_id}.md"
        
        iterations_completed = 0
        final_result = None
        
        for iteration in range(self.max_iterations):
            iterations_completed = iteration + 1
            
            logging.info(f"Code review iteration {iteration + 1}/{self.max_iterations}")
            
            # Perform code review
            review_result = self._perform_single_review(
                milestone_id, worktree_path, report_file, iteration + 1, review_type
            )
            
            if not review_result.success:
                return review_result
                
            # Check if quality threshold is met and no issues remain
            if not review_result.has_quality_issues:
                logging.info(f"Code review completed successfully after {iteration + 1} iteration(s)")
                final_result = review_result
                break
                
            # If auto-fix is enabled and there are issues, try to fix them
            if self.auto_fix and review_result.has_quality_issues:
                logging.info(f"Quality issues found, attempting auto-fix (iteration {iteration + 1})")
                fix_success = self._attempt_auto_fix(review_result, worktree_path)
                if not fix_success:
                    logging.warning("Auto-fix failed, manual intervention required")
                    final_result = review_result
                    break
            else:
                final_result = review_result
                break
        
        if final_result is None:
            final_result = CodeReviewResult(
                success=False,
                quality_score=0.0,
                todos_found=["Review process failed"],
                quality_gates_failed=["Maximum iterations exceeded"],
                recommendations=["Manual review required"],
                report_file=report_file,
                iterations_completed=iterations_completed
            )
        
        final_result.iterations_completed = iterations_completed
        logging.info(f"Code review completed with {iterations_completed} iteration(s), final score: {final_result.quality_score:.2f}")
        
        return final_result
    
    def _perform_single_review(self, milestone_id: str, worktree_path: Optional[str], 
                              report_file: str, iteration: int, review_type: str) -> CodeReviewResult:
        """Perform a single code review iteration"""
        
        # Prepare code review task
        review_task = {
            "id": f"code-review-{milestone_id}-{iteration}",
            "title": f"Code Review - {milestone_id} (Iteration {iteration})",
            "requirements": self._prepare_code_review_requirements(milestone_id, review_type),
            "acceptance_criteria": self._prepare_code_review_acceptance_criteria(),
            "milestone_id": milestone_id
        }
        
        try:
            # Execute code review
            result = self.claude_wrapper.execute_task(review_task, worktree_path)
            
            if not result.success:
                return CodeReviewResult(
                    success=False,
                    quality_score=0.0,
                    todos_found=[],
                    quality_gates_failed=[f"Code review execution failed: {result.error}"],
                    recommendations=["Fix execution issues and retry"],
                    report_file=report_file
                )
            
            # Parse review results
            return self._parse_review_results(result.output, report_file)
            
        except Exception as e:
            logging.error(f"Code review failed: {e}")
            return CodeReviewResult(
                success=False,
                quality_score=0.0,
                todos_found=[],
                quality_gates_failed=[f"Exception during review: {str(e)}"],
                recommendations=["Debug and fix review process"],
                report_file=report_file
            )
    
    def _prepare_code_review_requirements(self, milestone_id: str, review_type: str) -> str:
        """Prepare requirements for code review task"""
        return f"""
Conduct a comprehensive code review for {review_type}: {milestone_id}

REVIEW SCOPE:
- Analyze all files changed/created for this {review_type}
- Check code quality, architecture, and best practices
- Identify TODOs, FIXMEs, and incomplete implementations
- Verify quality gates are met
- Assess overall implementation quality

QUALITY GATES TO CHECK:
1. Code builds without errors
2. All tests pass (if tests exist)
3. Code follows project conventions
4. No security vulnerabilities
5. Performance considerations addressed
6. Documentation is adequate
7. Error handling is proper
8. Code is maintainable and readable

MCP SERVERS FOR ENHANCED REVIEW:
Use these MCP servers to provide more thorough code review:

🔍 CONTEXT7 MCP - For documentation and standards review:
- Consult documentation for best practices and standards
- Research framework-specific patterns and conventions
- Verify adherence to project architectural guidelines

🎭 PLAYWRIGHT MCP - For testing review:
- If tests are present, validate test coverage and quality
- Suggest additional test scenarios for better coverage
- Review browser testing implementations

🎨 ACETERNITY MCP - For UI/UX review:
- If UI components are present, review design patterns
- Check for modern UI best practices and accessibility
- Validate responsive design and user experience

OUTPUT REQUIREMENTS:
- Generate a markdown report file: code_review_{milestone_id}_{review_type}.md
- Include a quality score (0.0 to 1.0)
- List all TODOs and FIXMEs found
- Document failed quality gates
- Provide specific recommendations for improvement
- Include file-by-file analysis if applicable
- Use MCP servers to enhance review quality where applicable

CRITICAL: This review must result in the creation of a detailed markdown report file with comprehensive analysis.
"""
    
    def _prepare_code_review_acceptance_criteria(self) -> str:
        """Prepare acceptance criteria for code review"""
        return f"""
ACCEPTANCE CRITERIA:
1. A comprehensive markdown report file is created
2. Quality score is calculated and documented
3. All TODOs and FIXMEs are identified and listed
4. Failed quality gates are clearly documented
5. Specific, actionable recommendations are provided
6. Overall assessment includes pass/fail decision based on quality threshold ({self.quality_threshold})

SUCCESS CRITERIA:
- Report file is generated and readable
- Quality analysis is thorough and accurate
- Recommendations are specific and implementable
"""
    
    def _parse_review_results(self, output: str, report_file: str) -> CodeReviewResult:
        """Parse code review results from Claude output"""
        
        # Extract quality score
        quality_score = 0.8  # Default
        quality_match = re.search(r'[Qq]uality [Ss]core:?\s*([\d.]+)', output)
        if quality_match:
            try:
                quality_score = float(quality_match.group(1))
            except ValueError:
                pass
        
        # Extract TODOs
        todos_found = []
        todo_pattern = r'(?:TODO|FIXME|XXX)(?:\([^)]*\))?:?\s*(.+)'
        todos_found.extend(re.findall(todo_pattern, output, re.IGNORECASE | re.MULTILINE))
        
        # Extract failed quality gates
        quality_gates_failed = []
        gates_pattern = r'(?:FAILED|FAIL|❌)(?:\s*:)?\s*(.+?)(?:\n|$)'
        quality_gates_failed.extend(re.findall(gates_pattern, output, re.MULTILINE))
        
        # Extract recommendations
        recommendations = []
        rec_pattern = r'(?:RECOMMENDATION|RECOMMEND|➤)(?:\s*:)?\s*(.+?)(?:\n|$)'
        recommendations.extend(re.findall(rec_pattern, output, re.MULTILINE))
        
        # If no specific recommendations found, look for bullet points in recommendation sections
        if not recommendations:
            rec_section = re.search(r'[Rr]ecommendation[s]?:?\s*(.*?)(?:\n\n|\n[A-Z]|$)', output, re.DOTALL | re.MULTILINE)
            if rec_section:
                bullet_recs = re.findall(r'^[-*•]\s*(.+?)$', rec_section.group(1), re.MULTILINE)
                recommendations.extend(bullet_recs)
        
        success = quality_score >= self.quality_threshold and not quality_gates_failed
        
        return CodeReviewResult(
            success=success,
            quality_score=quality_score,
            todos_found=todos_found,
            quality_gates_failed=quality_gates_failed,
            recommendations=recommendations,
            report_file=report_file
        )
    
    def _attempt_auto_fix(self, review_result: CodeReviewResult, worktree_path: Optional[str]) -> bool:
        """Attempt to automatically fix issues found in code review"""
        if not self.auto_fix or not review_result.has_quality_issues:
            return True
        
        logging.info("Attempting auto-fix of code review issues")
        
        # Prepare auto-fix task based on review results
        fix_recommendations = review_result.recommendations[:5]  # Limit to top 5
        fix_todos = review_result.todos_found[:10]  # Limit to top 10
        
        fix_task = {
            "id": f"auto-fix-{uuid.uuid4().hex[:8]}",
            "title": "Auto-fix Code Review Issues",
            "requirements": self._prepare_auto_fix_requirements(fix_recommendations, fix_todos, review_result.quality_gates_failed),
            "acceptance_criteria": self._prepare_auto_fix_acceptance_criteria(),
            "milestone_id": "auto-fix"
        }
        
        try:
            result = self.claude_wrapper.execute_task(fix_task, worktree_path)
            if result.success:
                logging.info("Auto-fix completed successfully")
                return True
            else:
                logging.warning(f"Auto-fix failed: {result.error}")
                return False
        except Exception as e:
            logging.error(f"Auto-fix exception: {e}")
            return False
    
    def _prepare_auto_fix_requirements(self, recommendations: List[str], todos: List[str], failed_gates: List[str]) -> str:
        """Prepare requirements for auto-fix task"""
        req = "Fix the following code review issues:\n\n"
        
        if recommendations:
            req += "RECOMMENDATIONS TO IMPLEMENT:\n"
            for i, rec in enumerate(recommendations, 1):
                req += f"{i}. {rec}\n"
            req += "\n"
        
        if todos:
            req += "TODOs TO ADDRESS:\n"
            for i, todo in enumerate(todos, 1):
                req += f"{i}. {todo}\n"
            req += "\n"
        
        if failed_gates:
            req += "QUALITY GATES TO FIX:\n"
            for i, gate in enumerate(failed_gates, 1):
                req += f"{i}. {gate}\n"
            req += "\n"
        
        req += """
MCP SERVERS FOR ENHANCED FIXES:
Use these MCP servers to implement better solutions:

🔍 CONTEXT7 MCP - For research and documentation:
- Research best practices for the issues being fixed
- Consult documentation for proper implementation patterns

🎭 PLAYWRIGHT MCP - For testing improvements:
- When fixing testing-related issues
- Implement comprehensive test coverage for fixes

🎨 ACETERNITY MCP - For UI/UX fixes:
- When fixing UI components or styling issues
- Implement modern design patterns and accessibility improvements

CRITICAL INSTRUCTIONS:
1. Address as many issues as possible while maintaining code functionality
2. Make minimal, focused changes that resolve the specific issues
3. Ensure all changes follow project conventions
4. Test that your changes don't break existing functionality
5. Use Write, Edit, or MultiEdit tools to make actual file changes
6. Leverage appropriate MCP servers for enhanced solutions
"""
        
        return req
    
    def _prepare_auto_fix_acceptance_criteria(self) -> str:
        """Prepare acceptance criteria for auto-fix"""
        return """
ACCEPTANCE CRITERIA:
1. Code review issues are resolved without breaking functionality
2. Changes follow project coding conventions
3. All file modifications are completed using appropriate tools
4. No new issues are introduced during the fix process
5. Code still builds and runs correctly after fixes
"""

# Utility functions
def setup_logging_for_module():
    """Setup logging configuration for this module"""
    logger = logging.getLogger(__name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

# Initialize logging when module is imported
setup_logging_for_module()