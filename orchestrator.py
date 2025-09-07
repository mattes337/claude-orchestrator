#!/usr/bin/env python3
"""
Claude Code Orchestrator - Main Application
Advanced milestone execution orchestrator with parallel processing, git worktree management,
and comprehensive error handling.
"""

import os
import sys
import json
import time
import asyncio
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import subprocess
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import signal

# Import advanced modules
from advanced import (
    RateLimitManager,
    SystemMonitor,
    WorktreeManager,
    ClaudeCodeWrapper,
    MilestoneValidator
)

class OrchestratorState:
    """Manages orchestrator state and persistence"""
    
    def __init__(self, state_file: str = "orchestrator_state.json"):
        self.state_file = state_file
        self.state = {
            "current_stage": 0,
            "completed_tasks": set(),
            "failed_tasks": set(),
            "skipped_tasks": set(),
            "stage_results": {},
            "last_checkpoint": None,
            "total_start_time": None,
            "rate_limit_resets": {},
            "worktree_paths": {},
            "execution_log": []
        }
        self.load_state()
    
    def load_state(self):
        """Load state from file"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    # Convert sets from lists
                    for key in ["completed_tasks", "failed_tasks", "skipped_tasks"]:
                        if key in data:
                            data[key] = set(data[key])
                    self.state.update(data)
            except Exception as e:
                logging.error(f"Failed to load state: {e}")
    
    def save_state(self):
        """Save state to file"""
        try:
            data = self.state.copy()
            # Convert sets to lists for JSON serialization
            for key in ["completed_tasks", "failed_tasks", "skipped_tasks"]:
                if key in data:
                    data[key] = list(data[key])
            
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"Failed to save state: {e}")
    
    def add_log_entry(self, entry: str):
        """Add entry to execution log"""
        timestamp = datetime.now().isoformat()
        self.state["execution_log"].append(f"[{timestamp}] {entry}")
    
    def reset_state(self):
        """Reset state to initial values"""
        self.state = {
            "current_stage": 0,
            "completed_tasks": set(),
            "failed_tasks": set(),
            "skipped_tasks": set(),
            "stage_results": {},
            "last_checkpoint": None,
            "total_start_time": None,
            "rate_limit_resets": {},
            "worktree_paths": {},
            "execution_log": []
        }
        # Remove state file if it exists
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
        logging.info("Orchestrator state has been reset")

class TaskResult:
    """Represents the result of a task execution"""
    
    def __init__(self, task_id: str, success: bool, output: str = "", 
                 error: str = "", duration: float = 0.0, retry_count: int = 0):
        self.task_id = task_id
        self.success = success
        self.output = output
        self.error = error
        self.duration = duration
        self.retry_count = retry_count
        self.timestamp = datetime.now().isoformat()

class MilestoneOrchestrator:
    """Main orchestrator class for milestone execution"""
    
    def __init__(self, config_path: str = "orchestrator.config.json"):
        self.config = self.load_config(config_path)
        
        # Override base_branch with current branch
        current_branch = self.get_current_branch()
        self.config["git"]["base_branch"] = current_branch
        logging.info(f"Using current branch as base: {current_branch}")
        
        self.state = OrchestratorState()
        
        # Initialize components
        self.rate_limiter = RateLimitManager(
            requests_per_minute=self.config.get("rate_limit", {}).get("requests_per_minute", 50),
            burst_limit=self.config.get("rate_limit", {}).get("burst_limit", 10)
        )
        self.system_monitor = SystemMonitor()
        self.worktree_manager = WorktreeManager()
        self.claude_wrapper = ClaudeCodeWrapper()
        self.validator = MilestoneValidator()
        
        # Setup logging
        self.setup_logging()
        
        # Shutdown handling
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Task execution
        self.max_workers = self.config.get("execution", {}).get("max_parallel_tasks", 4)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # Output control
        self.verbose = False
        
        logging.info("Orchestrator initialized successfully")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logging.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
        self.state.add_log_entry(f"Shutdown signal received: {signum}")
        
        # Shutdown the thread pool executor to cancel running tasks
        if hasattr(self, 'executor') and self.executor:
            logging.info("Shutting down thread pool executor...")
            self.executor.shutdown(wait=False, cancel_futures=True)
            
        # Force exit after a short delay if graceful shutdown doesn't work
        import threading
        def force_exit():
            import time
            time.sleep(2)  # Give graceful shutdown a chance
            if self.shutdown_requested:
                logging.warning("Forcing exit due to shutdown timeout")
                os._exit(130)  # Exit code for SIGINT
        
        force_exit_thread = threading.Thread(target=force_exit, daemon=True)
        force_exit_thread.start()
    
    def get_current_branch(self) -> str:
        """Get the current git branch"""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            logging.warning("Failed to get current branch, falling back to 'main'")
            return "main"
        except Exception as e:
            logging.warning(f"Error getting current branch: {e}, falling back to 'main'")
            return "main"
    
    def load_config(self, config_path: str) -> Dict:
        """Load configuration from file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.warning(f"Config file {config_path} not found, using defaults")
            return self.get_default_config()
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON in config file: {e}")
            return self.get_default_config()
    
    def get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
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
                "use_worktrees": True,
                "base_branch": "main",
                "worktree_prefix": "milestone-"
            },
            "code_review": {
                "enabled": True,
                "auto_fix": True,
                "quality_threshold": 0.8
            },
            "notifications": {
                "enabled": False,
                "webhook_url": ""
            }
        }
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_level = getattr(logging, self.config.get("logging", {}).get("level", "INFO").upper())
        log_format = self.config.get("logging", {}).get("format", 
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        
        # File handler
        file_handler = logging.FileHandler("orchestrator.log")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format))
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter(log_format))
        
        # Root logger
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[file_handler, console_handler]
        )
    
    def discover_milestones(self) -> List[Dict]:
        """Discover and parse milestone files"""
        milestones_dir = Path(self.config["milestones_dir"])
        if not milestones_dir.exists():
            raise FileNotFoundError(f"Milestones directory not found: {milestones_dir}")
        
        milestones = []
        for milestone_file in milestones_dir.glob("*.md"):
            try:
                milestone = self.parse_milestone_file(milestone_file)
                if milestone:
                    milestones.append(milestone)
            except Exception as e:
                logging.error(f"Failed to parse milestone {milestone_file}: {e}")
        
        # Sort by milestone ID
        milestones.sort(key=lambda x: x["id"])
        logging.info(f"Discovered {len(milestones)} milestones")
        return milestones
    
    def parse_milestone_file(self, filepath: Path) -> Optional[Dict]:
        """Parse a milestone file and extract tasks"""
        try:
            content = filepath.read_text(encoding='utf-8')
            
            # Extract milestone metadata
            milestone_id = filepath.stem
            title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            title = title_match.group(1) if title_match else milestone_id
            
            # Extract description
            desc_match = re.search(r'^#\s+.+\n\n(.+?)(?=\n##|\n```|\Z)', content, re.MULTILINE | re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ""
            
            # Extract tasks
            tasks = self.extract_tasks_from_content(content, milestone_id)
            
            # Extract dependencies
            deps_match = re.search(r'## Dependencies\n(.+?)(?=\n##|\Z)', content, re.MULTILINE | re.DOTALL)
            dependencies = []
            if deps_match:
                deps_text = deps_match.group(1)
                dependencies = re.findall(r'- (.+)', deps_text)
            
            # Extract stage information
            stage_match = re.search(r'Stage:\s*(\d+)', content, re.IGNORECASE)
            stage = int(stage_match.group(1)) if stage_match else 1
            
            return {
                "id": milestone_id,
                "title": title,
                "description": description,
                "stage": stage,
                "tasks": tasks,
                "dependencies": dependencies,
                "filepath": str(filepath)
            }
            
        except Exception as e:
            logging.error(f"Error parsing milestone file {filepath}: {e}")
            return None
    
    def extract_tasks_from_content(self, content: str, milestone_id: str) -> List[Dict]:
        """Extract tasks from milestone content"""
        tasks = []
        
        # Find task sections
        task_sections = re.findall(r'## Task (\d+): (.+?)\n(.+?)(?=\n## |\Z)', 
                                 content, re.MULTILINE | re.DOTALL)
        
        for task_num, task_title, task_content in task_sections:
            task_id = f"{milestone_id}-T{task_num}"
            
            # Extract requirements
            req_match = re.search(r'### Requirements\n(.+?)(?=\n###|\Z)', 
                                task_content, re.MULTILINE | re.DOTALL)
            requirements = req_match.group(1).strip() if req_match else ""
            
            # Extract acceptance criteria
            ac_match = re.search(r'### Acceptance Criteria\n(.+?)(?=\n###|\Z)', 
                               task_content, re.MULTILINE | re.DOTALL)
            acceptance_criteria = ac_match.group(1).strip() if ac_match else ""
            
            # Extract priority
            priority_match = re.search(r'Priority:\s*(High|Medium|Low)', task_content, re.IGNORECASE)
            priority = priority_match.group(1).lower() if priority_match else "medium"
            
            # Extract estimated time
            time_match = re.search(r'Estimated Time:\s*(\d+)', task_content)
            estimated_time = int(time_match.group(1)) if time_match else 30
            
            tasks.append({
                "id": task_id,
                "title": task_title.strip(),
                "requirements": requirements,
                "acceptance_criteria": acceptance_criteria,
                "priority": priority,
                "estimated_time": estimated_time,
                "milestone_id": milestone_id
            })
        
        return tasks
    
    def organize_execution_stages(self, milestones: List[Dict]) -> Dict[int, List[Dict]]:
        """Organize milestones into execution stages"""
        stages = {}
        
        for milestone in milestones:
            stage = milestone.get("stage", 1)
            if stage not in stages:
                stages[stage] = []
            stages[stage].append(milestone)
        
        # Sort stages
        return dict(sorted(stages.items()))
    
    def execute_milestones(self, milestones: List[Dict]) -> bool:
        """Execute all milestones organized by stages"""
        if not milestones:
            logging.warning("No milestones to execute")
            return True
        
        stages = self.organize_execution_stages(milestones)
        self.state.state["total_start_time"] = datetime.now().isoformat()
        
        logging.info(f"Starting execution of {len(milestones)} milestones across {len(stages)} stages")
        self.state.add_log_entry(f"Starting execution of {len(milestones)} milestones")
        
        # Show execution overview
        print(f"\n=== Starting Milestone Execution ===")
        print(f"   Milestones: {len(milestones)}")
        print(f"   Stages: {len(stages)}")
        if self.verbose:
            for stage_num, stage_milestones in stages.items():
                print(f"   Stage {stage_num}: {len(stage_milestones)} milestones")
        print()
        
        try:
            for stage_num in sorted(stages.keys()):
                if self.shutdown_requested:
                    logging.info("Shutdown requested, stopping execution")
                    break
                
                # Resume from checkpoint if needed
                if stage_num < self.state.state["current_stage"]:
                    logging.info(f"Skipping completed stage {stage_num}")
                    continue
                
                print(f">> Executing Stage {stage_num} ({len(stages[stage_num])} milestones)")
                success = self.execute_stage(stage_num, stages[stage_num])
                if not success:
                    print(f"[FAILED] Stage {stage_num} failed, stopping execution")
                    logging.error(f"Stage {stage_num} failed, stopping execution")
                    return False
                else:
                    print(f"[SUCCESS] Stage {stage_num} completed successfully")
                
                self.state.state["current_stage"] = stage_num + 1
                self.state.save_state()
            
            # Final validation and reporting
            self.generate_final_report()
            logging.info("All stages completed successfully")
            
            # Show completion summary
            print(f"\n=== Execution Complete! ===")
            total_time = (datetime.now() - datetime.fromisoformat(self.state.state["total_start_time"])).total_seconds()
            print(f"   Total time: {total_time:.1f}s")
            if self.verbose:
                completed_tasks = len(self.state.state["completed_tasks"])
                failed_tasks = len(self.state.state["failed_tasks"])
                print(f"   Tasks completed: {completed_tasks}")
                print(f"   Tasks failed: {failed_tasks}")
            
            return True
            
        except Exception as e:
            logging.error(f"Execution failed: {e}")
            self.state.add_log_entry(f"Execution failed: {e}")
            return False
        finally:
            self.cleanup()
    
    def execute_stage(self, stage_num: int, milestones: List[Dict]) -> bool:
        """Execute a single stage with parallel milestone processing"""
        logging.info(f"Executing stage {stage_num} with {len(milestones)} milestones")
        self.state.add_log_entry(f"Starting stage {stage_num}")
        
        stage_start_time = time.time()
        stage_results = []
        
        # Prepare worktrees for parallel execution
        if self.config["git"]["use_worktrees"]:
            self.prepare_stage_worktrees(stage_num, milestones)
        
        # Execute milestones in parallel within the stage
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_milestone = {
                executor.submit(self.execute_milestone, milestone, stage_num): milestone
                for milestone in milestones
            }
            
            # Use timeout to allow checking shutdown_requested more frequently
            while future_to_milestone and not self.shutdown_requested:
                try:
                    for future in as_completed(future_to_milestone, timeout=1.0):
                        if self.shutdown_requested:
                            # Cancel remaining futures
                            for remaining_future in future_to_milestone:
                                remaining_future.cancel()
                            break
                        
                        milestone = future_to_milestone.pop(future)
                        try:
                            result = future.result()
                            stage_results.append(result)
                            
                            if result["success"]:
                                print(f"    [DONE] Milestone completed: {milestone['title']}")
                                logging.info(f"Milestone {milestone['id']} completed successfully")
                                if self.verbose:
                                    duration = result.get('duration', 0)
                                    task_count = len(result.get('task_results', []))
                                    print(f"           Duration: {duration:.1f}s, Tasks: {task_count}")
                            else:
                                error_msg = result.get('error', 'Unknown error')
                                print(f"    [FAIL] Milestone failed: {milestone['title']} - {error_msg}")
                                logging.error(f"Milestone {milestone['id']} failed: {error_msg}")
                        
                        except Exception as e:
                            logging.error(f"Milestone {milestone['id']} execution exception: {e}")
                            stage_results.append({
                                "milestone_id": milestone["id"],
                                "success": False,
                                "error": str(e)
                            })
                        break  # Process one future at a time
                except TimeoutError:
                    # Timeout allows us to check shutdown_requested
                    continue
        
        # Analyze stage results
        stage_duration = time.time() - stage_start_time
        successful_milestones = sum(1 for result in stage_results if result["success"])
        
        self.state.state["stage_results"][stage_num] = {
            "duration": stage_duration,
            "total_milestones": len(milestones),
            "successful_milestones": successful_milestones,
            "results": stage_results
        }
        
        logging.info(f"Stage {stage_num} completed: {successful_milestones}/{len(milestones)} successful, {stage_duration:.1f}s")
        
        # Stage is successful if at least 80% of milestones succeeded
        success_rate = successful_milestones / len(milestones) if milestones else 1.0
        stage_success = success_rate >= 0.8
        
        if not stage_success:
            logging.error(f"Stage {stage_num} failed with success rate {success_rate:.1%}")
        
        return stage_success
    
    def prepare_stage_worktrees(self, stage_num: int, milestones: List[Dict]):
        """Prepare git worktrees for stage execution"""
        for milestone in milestones:
            try:
                worktree_path = self.worktree_manager.create_worktree(
                    milestone["id"], 
                    self.config["git"]["base_branch"],
                    prefix=self.config["git"]["worktree_prefix"]
                )
                self.state.state["worktree_paths"][milestone["id"]] = worktree_path
                logging.debug(f"Created worktree for {milestone['id']}: {worktree_path}")
            except Exception as e:
                logging.warning(f"Failed to create worktree for {milestone['id']}: {e}")
    
    def execute_milestone(self, milestone: Dict, stage_num: int) -> Dict:
        """Execute a single milestone"""
        milestone_id = milestone["id"]
        logging.info(f"Starting milestone {milestone_id}")
        
        if self.verbose:
            print(f"  -> Starting milestone: {milestone['title']} ({milestone_id})")
        else:
            print(f"  -> {milestone['title']}")
        
        milestone_start_time = time.time()
        results = []
        
        try:
            # Validate dependencies
            if not self.validate_milestone_dependencies(milestone):
                return {
                    "milestone_id": milestone_id,
                    "success": False,
                    "error": "Dependencies not met"
                }
            
            # Execute tasks in parallel
            tasks = milestone["tasks"]
            if not tasks:
                logging.warning(f"No tasks found for milestone {milestone_id}")
                return {"milestone_id": milestone_id, "success": True, "tasks": []}
            
            # Group tasks by priority for execution order
            high_priority_tasks = [t for t in tasks if t.get("priority", "medium") == "high"]
            other_tasks = [t for t in tasks if t.get("priority", "medium") != "high"]
            
            # Execute high priority tasks first, then others
            for task_group in [high_priority_tasks, other_tasks]:
                if not task_group or self.shutdown_requested:
                    continue
                
                group_results = self.execute_task_group(task_group, milestone_id)
                results.extend(group_results)
                
                # Check if any critical tasks failed
                critical_failures = [r for r in group_results if not r.success and r.task_id in [t["id"] for t in high_priority_tasks]]
                if critical_failures:
                    logging.error(f"Critical tasks failed in {milestone_id}")
                    break
            
            # Milestone validation
            milestone_success = self.validate_milestone_completion(milestone, results)
            
            # Update TASKS.md
            if milestone_success:
                self.update_tasks_file(milestone, results)
            
            duration = time.time() - milestone_start_time
            logging.info(f"Milestone {milestone_id} completed in {duration:.1f}s")
            
            return {
                "milestone_id": milestone_id,
                "success": milestone_success,
                "duration": duration,
                "task_results": [{"task_id": r.task_id, "success": r.success} for r in results]
            }
            
        except Exception as e:
            logging.error(f"Milestone {milestone_id} execution failed: {e}")
            return {
                "milestone_id": milestone_id,
                "success": False,
                "error": str(e),
                "duration": time.time() - milestone_start_time
            }
    
    def execute_task_group(self, tasks: List[Dict], milestone_id: str) -> List[TaskResult]:
        """Execute a group of tasks in parallel"""
        results = []
        
        with ThreadPoolExecutor(max_workers=min(len(tasks), self.max_workers)) as executor:
            future_to_task = {
                executor.submit(self.execute_single_task, task, milestone_id): task
                for task in tasks
            }
            
            # Use timeout to allow checking shutdown_requested more frequently
            while future_to_task and not self.shutdown_requested:
                try:
                    for future in as_completed(future_to_task, timeout=1.0):
                        if self.shutdown_requested:
                            # Cancel remaining futures
                            for remaining_future in future_to_task:
                                remaining_future.cancel()
                            break
                        
                        task = future_to_task.pop(future)
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            logging.error(f"Task {task['id']} execution exception: {e}")
                            results.append(TaskResult(task["id"], False, error=str(e)))
                        break  # Process one future at a time
                except TimeoutError:
                    # Timeout allows us to check shutdown_requested
                    continue
        
        return results
    
    def execute_single_task(self, task: Dict, milestone_id: str) -> TaskResult:
        """Execute a single task with retries and rate limiting"""
        task_id = task["id"]
        max_retries = self.config["execution"]["max_retries"]
        retry_delay = self.config["execution"]["retry_delay"]
        
        for attempt in range(max_retries + 1):
            try:
                # Check if task already completed
                if task_id in self.state.state["completed_tasks"]:
                    logging.info(f"Task {task_id} already completed, skipping")
                    return TaskResult(task_id, True, output="Previously completed")
                
                # Rate limiting
                self.rate_limiter.wait_if_needed()
                
                # System resource check
                if not self.system_monitor.check_resources():
                    logging.warning("System resources low, waiting...")
                    time.sleep(30)
                
                # Execute task
                if self.verbose:
                    print(f"      * Executing task: {task.get('title', task_id)}")
                
                result = self.claude_wrapper.execute_task(
                    task, 
                    worktree_path=self.state.state["worktree_paths"].get(milestone_id),
                    timeout=self.config["execution"]["task_timeout"]
                )
                
                if self.verbose:
                    status = "[OK]" if result.success else "[ERR]"
                    print(f"      {status} Task {task_id}: {'Completed' if result.success else result.error}")
                
                if result.success:
                    self.state.state["completed_tasks"].add(task_id)
                    logging.info(f"Task {task_id} completed successfully (attempt {attempt + 1})")
                    return result
                else:
                    logging.warning(f"Task {task_id} failed (attempt {attempt + 1}): {result.error}")
                    
                    if attempt < max_retries:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        logging.info(f"Retrying task {task_id} in {wait_time}s")
                        time.sleep(wait_time)
            
            except Exception as e:
                logging.error(f"Task {task_id} exception (attempt {attempt + 1}): {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay * (2 ** attempt))
        
        # All attempts failed
        self.state.state["failed_tasks"].add(task_id)
        return TaskResult(task_id, False, error=f"Failed after {max_retries + 1} attempts")
    
    def validate_milestone_dependencies(self, milestone: Dict) -> bool:
        """Validate that milestone dependencies are satisfied"""
        dependencies = milestone.get("dependencies", [])
        if not dependencies:
            return True
        
        for dep in dependencies:
            # Check if dependency milestone is completed
            dep_tasks = [task_id for task_id in self.state.state["completed_tasks"] 
                        if task_id.startswith(f"{dep}-")]
            if not dep_tasks:
                logging.error(f"Dependency {dep} not satisfied for milestone {milestone['id']}")
                return False
        
        return True
    
    def validate_milestone_completion(self, milestone: Dict, task_results: List[TaskResult]) -> bool:
        """Validate that a milestone is properly completed"""
        if not task_results:
            return False
        
        # Check task success rate
        successful_tasks = sum(1 for result in task_results if result.success)
        success_rate = successful_tasks / len(task_results)
        
        # Milestone succeeds if 80% of tasks succeed
        if success_rate < 0.8:
            logging.error(f"Milestone {milestone['id']} failed validation: {success_rate:.1%} success rate")
            return False
        
        # Additional validation using MilestoneValidator
        try:
            validation_result = self.validator.validate_milestone(milestone, task_results)
            return validation_result.valid
        except Exception as e:
            logging.warning(f"Milestone validation error: {e}")
            return success_rate >= 0.8  # Fallback to success rate
    
    def update_tasks_file(self, milestone: Dict, task_results: List[TaskResult]):
        """Update TASKS.md file with milestone completion"""
        try:
            tasks_file = Path(self.config["tasks_file"])
            
            # Read existing content
            if tasks_file.exists():
                content = tasks_file.read_text(encoding='utf-8')
            else:
                content = "# Task Progress\n\n"
            
            # Add milestone completion entry
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            successful_tasks = sum(1 for r in task_results if r.success)
            total_tasks = len(task_results)
            
            entry = f"## {milestone['id']} - {milestone['title']}\n"
            entry += f"**Completed:** {timestamp}\n"
            entry += f"**Tasks:** {successful_tasks}/{total_tasks} successful\n"
            
            if successful_tasks == total_tasks:
                entry += "**Status:** ✅ COMPLETED\n\n"
            else:
                entry += "**Status:** ⚠️ PARTIALLY COMPLETED\n\n"
            
            # Update file
            content += entry
            tasks_file.write_text(content, encoding='utf-8')
            
            logging.info(f"Updated {tasks_file} with milestone {milestone['id']} completion")
            
        except Exception as e:
            logging.error(f"Failed to update tasks file: {e}")
    
    def generate_final_report(self):
        """Generate comprehensive execution report"""
        try:
            report = {
                "execution_summary": {
                    "start_time": self.state.state.get("total_start_time"),
                    "end_time": datetime.now().isoformat(),
                    "total_stages": len(self.state.state.get("stage_results", {})),
                    "completed_tasks": len(self.state.state["completed_tasks"]),
                    "failed_tasks": len(self.state.state["failed_tasks"]),
                    "skipped_tasks": len(self.state.state["skipped_tasks"])
                },
                "stage_results": self.state.state.get("stage_results", {}),
                "execution_log": self.state.state.get("execution_log", [])
            }
            
            with open("execution_report.json", "w") as f:
                json.dump(report, f, indent=2, default=str)
            
            logging.info("Final execution report generated: execution_report.json")
            
        except Exception as e:
            logging.error(f"Failed to generate final report: {e}")
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            # Cleanup worktrees
            if self.config["git"]["use_worktrees"]:
                for milestone_id, worktree_path in self.state.state.get("worktree_paths", {}).items():
                    try:
                        self.worktree_manager.cleanup_worktree(worktree_path)
                        logging.debug(f"Cleaned up worktree: {worktree_path}")
                    except Exception as e:
                        logging.warning(f"Failed to cleanup worktree {worktree_path}: {e}")
            
            # Shutdown executor
            if hasattr(self, 'executor'):
                self.executor.shutdown(wait=True)
            
            # Save final state
            self.state.save_state()
            
            logging.info("Cleanup completed")
            
        except Exception as e:
            logging.error(f"Cleanup failed: {e}")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Claude Code Milestone Orchestrator")
    parser.add_argument("--config", default="orchestrator.config.json",
                      help="Configuration file path")
    parser.add_argument("--resume", action="store_true",
                      help="Resume from last checkpoint")
    parser.add_argument("--validate-only", action="store_true",
                      help="Only validate milestones without execution")
    parser.add_argument("--stage", type=int,
                      help="Execute specific stage only")
    parser.add_argument("--milestone", 
                      help="Execute specific milestone only")
    parser.add_argument("--dry-run", action="store_true",
                      help="Show execution plan without running")
    parser.add_argument("--verbose", action="store_true",
                      help="Enable verbose output showing detailed progress")
    parser.add_argument("--reset", action="store_true",
                      help="Reset orchestrator state and start fresh")
    
    args = parser.parse_args()
    
    try:
        # Initialize orchestrator
        orchestrator = MilestoneOrchestrator(args.config)
        orchestrator.verbose = args.verbose
        
        # Reset state if requested
        if args.reset:
            orchestrator.state.reset_state()
            print("Orchestrator state has been reset.")
        
        # Discover milestones
        milestones = orchestrator.discover_milestones()
        
        if not milestones:
            print("No milestones found!")
            return 1
        
        # Filter milestones if specific ones requested
        if args.milestone:
            milestones = [m for m in milestones if m["id"] == args.milestone]
            if not milestones:
                print(f"Milestone '{args.milestone}' not found!")
                return 1
        
        if args.stage is not None:
            milestones = [m for m in milestones if m.get("stage", 1) == args.stage]
            if not milestones:
                print(f"No milestones found for stage {args.stage}!")
                return 1
        
        # Validation mode
        if args.validate_only:
            print("Validating milestones...")
            validation_results = []
            for milestone in milestones:
                try:
                    result = orchestrator.validator.validate_milestone_structure(milestone)
                    validation_results.append(result)
                    status = "✅" if result.valid else "❌"
                    print(f"{status} {milestone['id']}: {milestone['title']}")
                    if not result.valid:
                        for error in result.errors:
                            print(f"   - {error}")
                except Exception as e:
                    print(f"❌ {milestone['id']}: Validation failed - {e}")
            
            valid_count = sum(1 for r in validation_results if r.valid)
            print(f"\nValidation complete: {valid_count}/{len(milestones)} valid")
            return 0 if valid_count == len(milestones) else 1
        
        # Dry run mode
        if args.dry_run:
            print("Execution Plan:")
            stages = orchestrator.organize_execution_stages(milestones)
            for stage_num, stage_milestones in stages.items():
                print(f"\nStage {stage_num}:")
                for milestone in stage_milestones:
                    print(f"  - {milestone['id']}: {milestone['title']} ({len(milestone['tasks'])} tasks)")
            return 0
        
        # Execute milestones
        success = orchestrator.execute_milestones(milestones)
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\nExecution interrupted by user")
        return 130
    except Exception as e:
        print(f"Execution failed: {e}")
        logging.exception("Unhandled exception")
        return 1

if __name__ == "__main__":
    sys.exit(main())