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

# Import version information
from ._version import __version__, get_version_string, get_detailed_version

# Import shared types
from .types_shared import ValidationResult, CodeReviewResult, TaskResult

# Import advanced modules
from .advanced import (
    RateLimitManager,
    SystemMonitor,
    WorktreeManager,
    ClaudeCodeWrapper,
    MilestoneValidator,
    CodeReviewManager
)
from .milestone_preprocessor import MilestonePreprocessor

def setup_windows_console():
    """Setup console encoding for Windows to handle Unicode characters"""
    if sys.platform.startswith('win'):
        try:
            # Try to enable UTF-8 mode for Windows console
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
        except (AttributeError, OSError):
            # Fallback if UTF-8 setup fails
            pass
    return True

def safe_unicode_print(text, fallback_symbols=None):
    """
    Print text with Unicode characters, falling back to ASCII alternatives on Windows
    if Unicode encoding fails.
    
    Args:
        text: The text to print
        fallback_symbols: Dict mapping Unicode chars to ASCII alternatives
    """
    if fallback_symbols is None:
        fallback_symbols = {
            '✅': '[OK]',
            '❌': '[FAIL]',
            '⚠️': '[WARN]',
            '🔍': '[INFO]'
        }
    
    if sys.platform.startswith('win'):
        try:
            print(text)
        except UnicodeEncodeError:
            # Replace Unicode characters with ASCII alternatives
            safe_text = text
            for unicode_char, ascii_alt in fallback_symbols.items():
                safe_text = safe_text.replace(unicode_char, ascii_alt)
            print(safe_text)
    else:
        print(text)

def get_safe_unicode_string(text, fallback_symbols=None):
    """
    Return a safe Unicode string with fallback symbols for Windows compatibility.
    
    Args:
        text: The text to process
        fallback_symbols: Dict mapping Unicode chars to ASCII alternatives
    Returns:
        Safe string that can be displayed on Windows console
    """
    if fallback_symbols is None:
        fallback_symbols = {
            '✅': '[OK]',
            '❌': '[FAIL]',
            '⚠️': '[WARN]',
            '🔍': '[INFO]'
        }
    
    if sys.platform.startswith('win'):
        # Always use safe alternatives on Windows for consistency
        safe_text = text
        for unicode_char, ascii_alt in fallback_symbols.items():
            safe_text = safe_text.replace(unicode_char, ascii_alt)
        return safe_text
    else:
        return text

class OrchestratorState:
    """Manages orchestrator state and persistence"""
    
    def __init__(self, state_file: str = ".orchestrator/orchestrator_state.json"):
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

# TaskResult is now imported from types_shared

class MilestoneOrchestrator:
    """Main orchestrator class for milestone execution"""
    
    def __init__(self, config_path: str = "orchestrator.config.json"):
        self.config = self.load_config(config_path)
        
        # Override base_branch with current branch
        current_branch = self.get_current_branch()
        if "git" not in self.config:
            self.config["git"] = {}
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
        # Will set whatif mode later when flag is available
        self.validator = MilestoneValidator()
        self.preprocessor = MilestonePreprocessor()
        self.code_reviewer = CodeReviewManager(self.claude_wrapper, self.config)
        
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
        self.whatif = False
        self.whatif_prompts = []  # Store all prompts for whatif mode
        
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
                capture_output=True, text=True, check=True,
                encoding='utf-8', errors='replace'
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
                "quality_threshold": 0.8,
                "max_iterations": 3
            },
            "mcp_servers": {
                "enabled": True,
                "context7": {
                    "enabled": True,
                    "use_for": ["documentation", "research", "context"]
                },
                "playwright": {
                    "enabled": True,
                    "use_for": ["browser_testing", "e2e_testing", "ui_testing"]
                },
                "aceternity": {
                    "enabled": True,
                    "use_for": ["ui_design", "components", "styling"]
                }
            },
            "notifications": {
                "enabled": False,
                "webhook_url": ""
            },
            "advanced": {
                "enable_system_monitoring": True
            }
        }
    
    def setup_logging(self):
        """Setup logging configuration"""
        # Ensure .orchestrator directory exists
        Path(".orchestrator").mkdir(exist_ok=True)
        
        log_level = getattr(logging, self.config.get("logging", {}).get("level", "INFO").upper())
        log_format = self.config.get("logging", {}).get("format", 
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        
        # File handler
        file_handler = logging.FileHandler(".orchestrator/orchestrator.log")
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
        logging.info(f"🔍 Starting milestone discovery in directory: {milestones_dir}")
        
        if not milestones_dir.exists():
            raise FileNotFoundError(f"Milestones directory not found: {milestones_dir}")
        
        # Log all files in the directory for debugging
        all_files = list(milestones_dir.iterdir())
        logging.info(f"📁 Found {len(all_files)} files/directories in {milestones_dir}:")
        for file_path in all_files:
            logging.info(f"  - {file_path.name} ({'file' if file_path.is_file() else 'directory'})")
        
        # Find all .md files, excluding README.md
        all_md_files = list(milestones_dir.glob("*.md"))
        md_files = [f for f in all_md_files if f.name.lower() != "readme.md"]
        
        if len(all_md_files) != len(md_files):
            excluded_count = len(all_md_files) - len(md_files)
            logging.info(f"📄 Found {len(all_md_files)} .md files, excluded {excluded_count} (README.md)")
        else:
            logging.info(f"📄 Found {len(md_files)} .md files:")
        
        for md_file in md_files:
            logging.info(f"  - {md_file.name}")
        
        milestones = []
        for milestone_file in md_files:
            logging.info(f"🔍 Processing milestone file: {milestone_file.name}")
            try:
                milestone = self.parse_milestone_file(milestone_file)
                if milestone:
                    logging.info(f"✅ Successfully parsed milestone: {milestone['id']} (stage {milestone.get('stage', 'unknown')})")
                    milestones.append(milestone)
                else:
                    logging.warning(f"⚠️  Failed to parse milestone file (returned None): {milestone_file.name}")
            except Exception as e:
                logging.error(f"❌ Failed to parse milestone {milestone_file}: {e}")
        
        # Sort by milestone ID
        milestones.sort(key=lambda x: x["id"])
        logging.info(f"📊 Discovery complete: {len(milestones)} milestones discovered")
        
        # Log milestone summary for debugging
        if milestones:
            logging.info("📋 Milestone summary:")
            for milestone in milestones:
                logging.info(f"  - {milestone['id']}: {milestone.get('title', 'No title')} (Stage {milestone.get('stage', 'unknown')}, {len(milestone.get('tasks', []))} tasks)")
        
        return milestones
    
    def parse_milestone_file(self, filepath: Path) -> Optional[Dict]:
        """Parse a milestone file and create a single task for Claude Code to handle"""
        try:
            # Read the raw milestone content
            original_content = filepath.read_text(encoding='utf-8')
            milestone_id = filepath.stem
            
            # Extract basic metadata from the raw content
            title_match = re.search(r'^#\s+(.+)$', original_content, re.MULTILINE)
            title = title_match.group(1) if title_match else milestone_id
            
            # Extract description (everything after title until first ##)
            desc_match = re.search(r'^#\s+.+?\n\n(.+?)(?=\n##|\Z)', original_content, re.MULTILINE | re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ""
            
            # Extract dependencies
            deps_match = re.search(r'## Dependencies\n(.+?)(?=\n##|\Z)', original_content, re.MULTILINE | re.DOTALL)
            dependencies = []
            if deps_match:
                deps_text = deps_match.group(1)
                if "None specified" not in deps_text:
                    dependencies = re.findall(r'- (.+)', deps_text)
            
            # Extract stage information from milestone ID (e.g., "1a" -> stage 1)
            stage = 1
            if milestone_id:
                id_stage_match = re.search(r'^(\d+)[a-z]?', milestone_id)
                if id_stage_match:
                    stage = int(id_stage_match.group(1))
                    logging.info(f"🔍 Detected stage {stage} from milestone ID: {milestone_id}")
                else:
                    logging.info(f"🔍 No stage found in ID {milestone_id}, using default stage 1")
            
            # Create a single task that passes the entire milestone to Claude Code
            task = {
                "id": f"{milestone_id}_claude_execution",
                "title": f"Implement {title}",
                "description": f"Let Claude Code implement the entire milestone: {title}",
                "priority": "high",
                "estimated_time": 60,
                "milestone_content": original_content,
                "milestone_filepath": str(filepath),
                "claude_driven": True
            }
            
            logging.info(f"✅ Created Claude-driven task for {milestone_id}: {title}")
            
            return {
                "id": milestone_id,
                "title": title,
                "description": description,
                "stage": stage,
                "tasks": [task],  # Single task containing the whole milestone
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
        logging.info(f"🗂️  Organizing {len(milestones)} milestones into execution stages")
        stages = {}
        
        for milestone in milestones:
            stage = milestone.get("stage", 1)
            milestone_id = milestone.get("id", "unknown")
            logging.info(f"  📌 Milestone {milestone_id} assigned to stage {stage}")
            
            if stage not in stages:
                stages[stage] = []
            stages[stage].append(milestone)
        
        # Sort stages and log results
        sorted_stages = dict(sorted(stages.items()))
        logging.info(f"📊 Stage organization complete - {len(sorted_stages)} stages created:")
        
        for stage_num, stage_milestones in sorted_stages.items():
            milestone_ids = [m.get("id", "unknown") for m in stage_milestones]
            logging.info(f"  📋 Stage {stage_num}: {len(stage_milestones)} milestones ({', '.join(milestone_ids)})")
        
        return sorted_stages
    
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
        if self.config.get("git", {}).get("use_worktrees", False):
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
        
        # If stage was successful and using worktrees, merge them sequentially
        if stage_success and self.config.get("git", {}).get("use_worktrees", False):
            merge_success = self.merge_stage_worktrees(stage_num, milestones)
            if not merge_success:
                logging.error(f"Stage {stage_num} worktree merging failed")
                return False
        
        # Conduct final stage code review after merging
        if stage_success and self.config.get("code_review", {}).get("enabled", True):
            stage_review_result = self.conduct_stage_code_review(stage_num, milestones)
            if not stage_review_result.success and stage_review_result.has_quality_issues:
                logging.error(f"Stage {stage_num} failed final code review")
                return False
        
        # Commit the complete stage to the root branch
        if stage_success:
            commit_success = self.commit_stage_completion(stage_num, milestones)
            if not commit_success:
                logging.warning(f"Failed to commit stage {stage_num} completion")
                # Don't fail the stage for commit issues, just warn
        
        return stage_success
    
    def prepare_stage_worktrees(self, stage_num: int, milestones: List[Dict]):
        """Prepare git worktrees for stage execution"""
        for milestone in milestones:
            try:
                worktree_path = self.worktree_manager.create_worktree(
                    milestone["id"], 
                    self.config.get("git", {}).get("base_branch", "main"),
                    prefix=self.config.get("git", {}).get("worktree_prefix", "milestone-")
                )
                self.state.state["worktree_paths"][milestone["id"]] = worktree_path
                logging.debug(f"Created worktree for {milestone['id']}: {worktree_path}")
            except Exception as e:
                logging.warning(f"Failed to create worktree for {milestone['id']}: {e}")
    
    def merge_stage_worktrees(self, stage_num: int, milestones: List[Dict]) -> bool:
        """Merge worktrees sequentially into the root branch"""
        logging.info(f"Merging worktrees for stage {stage_num}")
        
        if self.verbose:
            print(f"  → Merging {len(milestones)} worktrees into root branch...")
        
        successful_merges = 0
        
        for milestone in milestones:
            milestone_id = milestone["id"]
            worktree_path = self.state.state.get("worktree_paths", {}).get(milestone_id)
            
            if not worktree_path:
                logging.warning(f"No worktree path found for milestone {milestone_id}")
                continue
            
            try:
                # Get the branch name for this worktree
                worktree_info = self.worktree_manager.get_worktree_info(milestone_id)
                if not worktree_info:
                    logging.warning(f"No worktree info found for {milestone_id}")
                    continue
                
                branch_name = worktree_info["branch"]
                
                # Switch to base branch and merge the feature branch
                base_branch = self.config.get("git", {}).get("base_branch", "main")
                
                merge_result = subprocess.run([
                    "git", "checkout", base_branch
                ], capture_output=True, text=True, encoding='utf-8', errors='replace')
                
                if merge_result.returncode != 0:
                    logging.error(f"Failed to checkout base branch {base_branch}: {merge_result.stderr}")
                    continue
                
                merge_result = subprocess.run([
                    "git", "merge", "--no-ff", branch_name, 
                    "-m", f"Merge milestone {milestone_id}: {milestone['title']}"
                ], capture_output=True, text=True, encoding='utf-8', errors='replace')
                
                if merge_result.returncode == 0:
                    successful_merges += 1
                    logging.info(f"Successfully merged {milestone_id}")
                    
                    if self.verbose:
                        print(f"    [MERGED] {milestone_id}: {milestone['title']}")
                else:
                    logging.error(f"Failed to merge {milestone_id}: {merge_result.stderr}")
                    if self.verbose:
                        print(f"    [MERGE_FAIL] {milestone_id}: {merge_result.stderr[:100]}")
            
            except Exception as e:
                logging.error(f"Exception during merge of {milestone_id}: {e}")
                if self.verbose:
                    print(f"    [ERROR] {milestone_id}: {str(e)}")
        
        merge_success = successful_merges >= len(milestones) * 0.8  # At least 80% successful
        
        if merge_success:
            logging.info(f"Stage {stage_num} worktree merging completed: {successful_merges}/{len(milestones)} successful")
        else:
            logging.error(f"Stage {stage_num} worktree merging failed: only {successful_merges}/{len(milestones)} successful")
        
        return merge_success
    
    def conduct_stage_code_review(self, stage_num: int, milestones: List[Dict]) -> CodeReviewResult:
        """Conduct comprehensive code review for entire stage after merging"""
        logging.info(f"Conducting final code review for stage {stage_num}")
        
        if self.verbose:
            print(f"  → Running final code review for stage {stage_num}...")
        
        stage_id = f"stage-{stage_num}"
        
        try:
            # Conduct stage-level code review (no worktree path since we're in main branch now)
            review_result = self.code_reviewer.conduct_code_review(
                stage_id, 
                worktree_path=None,  # Use main branch 
                review_type="stage"
            )
            
            if self.verbose:
                status = "[OK]" if review_result.success and not review_result.has_quality_issues else "[NEEDS_WORK]"
                print(f"      {status} Stage code review completed - Score: {review_result.quality_score:.2f}, Iterations: {review_result.iterations_completed}")
                
                if review_result.has_quality_issues:
                    if review_result.todos_found:
                        print(f"           TODOs found: {len(review_result.todos_found)}")
                    if review_result.quality_gates_failed:
                        print(f"           Quality gates failed: {len(review_result.quality_gates_failed)}")
            
            return review_result
            
        except Exception as e:
            logging.error(f"Stage code review failed for stage {stage_num}: {e}")
            return CodeReviewResult(
                success=False,
                quality_score=0.0,
                todos_found=[],
                quality_gates_failed=[f"Stage code review exception: {str(e)}"],
                recommendations=["Debug and retry stage code review"],
                report_file=f"code_review_stage_{stage_num}_error.md"
            )
    
    def commit_stage_completion(self, stage_num: int, milestones: List[Dict]) -> bool:
        """Commit the complete stage to the root branch"""
        logging.info(f"Committing stage {stage_num} completion to root branch")
        
        if self.verbose:
            print(f"  → Committing complete stage {stage_num} to root branch...")
        
        try:
            # Check if there are any changes to commit
            status_result = subprocess.run([
                "git", "status", "--porcelain"
            ], capture_output=True, text=True, encoding='utf-8', errors='replace')
            
            if not status_result.stdout.strip():
                logging.info(f"No changes to commit for stage {stage_num}")
                return True
            
            # Add all changes
            add_result = subprocess.run([
                "git", "add", "."
            ], capture_output=True, text=True, encoding='utf-8', errors='replace')
            
            if add_result.returncode != 0:
                logging.error(f"Failed to add changes for stage {stage_num}: {add_result.stderr}")
                return False
            
            # Create comprehensive commit message
            commit_message = f"Complete Stage {stage_num}: {len(milestones)} milestones integrated\n\n"
            
            commit_message += "Milestones completed in this stage:\n"
            for milestone in milestones:
                commit_message += f"- {milestone['id']}: {milestone['title']}\n"
                tasks = milestone.get('tasks', [])
                if tasks:
                    for task in tasks[:3]:  # Show first 3 tasks
                        commit_message += f"  • {task.get('title', task.get('id', 'Task'))}\n"
                    if len(tasks) > 3:
                        commit_message += f"  • ... and {len(tasks) - 3} more tasks\n"
            
            commit_message += "\n"
            commit_message += "Stage completed with:\n"
            commit_message += "- Individual milestone worktrees merged\n"
            commit_message += "- Comprehensive code review conducted\n" 
            commit_message += "- Quality gates validated\n"
            commit_message += "- All changes integrated to main branch\n\n"
            
            commit_message += f"Stage {stage_num} represents a significant milestone in the project development.\n\n"
            commit_message += "🤖 Generated with [Claude Code](https://claude.ai/code)\n\n"
            commit_message += "Co-Authored-By: Claude <noreply@anthropic.com>"
            
            # Commit the stage
            commit_result = subprocess.run([
                "git", "commit", "-m", commit_message
            ], capture_output=True, text=True, encoding='utf-8', errors='replace')
            
            if commit_result.returncode == 0:
                logging.info(f"Successfully committed stage {stage_num} completion")
                if self.verbose:
                    print(f"  [STAGE_COMMITTED] Stage {stage_num}")
                return True
            else:
                logging.error(f"Failed to commit stage {stage_num}: {commit_result.stderr}")
                if self.verbose:
                    print(f"  [STAGE_COMMIT_FAIL] Stage {stage_num}: {commit_result.stderr[:100]}")
                return False
                
        except Exception as e:
            logging.error(f"Exception during stage {stage_num} commit: {e}")
            return False
    
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
            
            # Conduct code review if milestone succeeded and code review is enabled
            code_review_result = None
            if milestone_success and self.config.get("code_review", {}).get("enabled", True):
                code_review_result = self.conduct_milestone_code_review(milestone_id, milestone, stage_num)
                if not code_review_result.success and code_review_result.has_quality_issues:
                    milestone_success = False
                    logging.warning(f"Milestone {milestone_id} failed code review quality gates")
            
            # Commit worktree changes if milestone succeeded
            if milestone_success and self.config.get("git", {}).get("use_worktrees", False):
                commit_success = self.commit_milestone_worktree(milestone_id, milestone)
                if not commit_success:
                    logging.warning(f"Failed to commit worktree for milestone {milestone_id}")
                    # Don't fail the milestone for commit issues, just warn
            
            # Update TASKS.md
            if milestone_success:
                self.update_tasks_file(milestone, results)
            
            duration = time.time() - milestone_start_time
            logging.info(f"Milestone {milestone_id} completed in {duration:.1f}s")
            
            return {
                "milestone_id": milestone_id,
                "success": milestone_success,
                "duration": duration,
                "task_results": [{"task_id": r.task_id, "success": r.success} for r in results],
                "code_review": {
                    "conducted": code_review_result is not None,
                    "success": code_review_result.success if code_review_result else True,
                    "quality_score": code_review_result.quality_score if code_review_result else 1.0,
                    "report_file": code_review_result.report_file if code_review_result else None,
                    "iterations": code_review_result.iterations_completed if code_review_result else 0
                }
            }
            
        except Exception as e:
            logging.error(f"Milestone {milestone_id} execution failed: {e}")
            return {
                "milestone_id": milestone_id,
                "success": False,
                "error": str(e),
                "duration": time.time() - milestone_start_time
            }
    
    def conduct_milestone_code_review(self, milestone_id: str, milestone: Dict, stage_num: int) -> CodeReviewResult:
        """Conduct milestone validation and iterative code review"""
        logging.info(f"Conducting code review for milestone {milestone_id}")
        
        if self.verbose:
            print(f"      → Running milestone validation and code review for {milestone_id}...")
        
        worktree_path = self.state.state.get("worktree_paths", {}).get(milestone_id)
        
        try:
            # Step 1: Pre-review milestone validation with Claude Code
            milestone_validation = self._conduct_pre_review_validation(milestone_id, milestone, worktree_path)
            
            if not milestone_validation.valid:
                if self.verbose:
                    print(f"      [MILESTONE_VALIDATION] Failed: {'; '.join(milestone_validation.errors)}")
                
                # Execute gap fixing if validation fails
                gap_fix_result = self._execute_stage_milestone_gap_fix(
                    milestone_id, 
                    '; '.join(milestone_validation.errors), 
                    worktree_path
                )
                
                if not gap_fix_result:
                    return CodeReviewResult(
                        success=False,
                        quality_score=0.0,
                        todos_found=[],
                        quality_gates_failed=[f"Milestone validation failed: {milestone_validation.error}"],
                        recommendations=["Review and complete milestone requirements"],
                        report_file=f"milestone_validation_{milestone_id}_failed.md"
                    )
            
            # Step 2: Conduct regular code review
            review_result = self.code_reviewer.conduct_code_review(
                milestone_id, 
                worktree_path=worktree_path, 
                review_type="milestone"
            )
            
            if self.verbose:
                status = "[OK]" if review_result.success and not review_result.has_quality_issues else "[NEEDS_WORK]"
                print(f"      {status} Code review completed - Score: {review_result.quality_score:.2f}, Iterations: {review_result.iterations_completed}")
                
                if review_result.has_quality_issues:
                    if review_result.todos_found:
                        print(f"           TODOs found: {len(review_result.todos_found)}")
                    if review_result.quality_gates_failed:
                        print(f"           Quality gates failed: {len(review_result.quality_gates_failed)}")
                
            return review_result
            
        except Exception as e:
            logging.error(f"Code review failed for milestone {milestone_id}: {e}")
            return CodeReviewResult(
                success=False,
                quality_score=0.0,
                todos_found=[],
                quality_gates_failed=[f"Code review exception: {str(e)}"],
                recommendations=["Debug and retry code review"],
                report_file=f"code_review_{milestone_id}_error.md"
            )
    
    def commit_milestone_worktree(self, milestone_id: str, milestone: Dict) -> bool:
        """Commit changes in a milestone worktree"""
        worktree_path = self.state.state.get("worktree_paths", {}).get(milestone_id)
        
        if not worktree_path:
            logging.warning(f"No worktree path found for milestone {milestone_id}")
            return False
        
        logging.info(f"Committing worktree for milestone {milestone_id}")
        
        if self.verbose:
            print(f"      → Committing worktree changes for {milestone_id}...")
        
        try:
            original_cwd = os.getcwd()
            os.chdir(worktree_path)
            
            try:
                # Check if there are any changes to commit
                status_result = subprocess.run([
                    "git", "status", "--porcelain"
                ], capture_output=True, text=True, encoding='utf-8', errors='replace')
                
                if not status_result.stdout.strip():
                    logging.info(f"No changes to commit in worktree {milestone_id}")
                    return True
                
                # Add all changes
                add_result = subprocess.run([
                    "git", "add", "."
                ], capture_output=True, text=True, encoding='utf-8', errors='replace')
                
                if add_result.returncode != 0:
                    logging.error(f"Failed to add changes in worktree {milestone_id}: {add_result.stderr}")
                    return False
                
                # Commit changes
                commit_message = f"Implement milestone {milestone_id}: {milestone['title']}\n\n"
                
                # Add task details to commit message
                tasks = milestone.get("tasks", [])
                if tasks:
                    commit_message += "Tasks completed:\n"
                    for task in tasks:
                        commit_message += f"- {task.get('title', task.get('id', 'Unknown task'))}\n"
                    commit_message += "\n"
                
                commit_message += f"Milestone completed as part of automated orchestration.\n\n"
                commit_message += "🤖 Generated with [Claude Code](https://claude.ai/code)\n\n"
                commit_message += "Co-Authored-By: Claude <noreply@anthropic.com>"
                
                commit_result = subprocess.run([
                    "git", "commit", "-m", commit_message
                ], capture_output=True, text=True, encoding='utf-8', errors='replace')
                
                if commit_result.returncode == 0:
                    logging.info(f"Successfully committed worktree {milestone_id}")
                    if self.verbose:
                        print(f"      [COMMITTED] {milestone_id}")
                    return True
                else:
                    logging.error(f"Failed to commit worktree {milestone_id}: {commit_result.stderr}")
                    if self.verbose:
                        print(f"      [COMMIT_FAIL] {milestone_id}: {commit_result.stderr[:100]}")
                    return False
                    
            finally:
                os.chdir(original_cwd)
                
        except Exception as e:
            logging.error(f"Exception during commit of worktree {milestone_id}: {e}")
            return False
    
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
                
                # System resource check (only if enabled)
                if self.config.get("advanced", {}).get("enable_system_monitoring", False):
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
                    # For Claude-driven tasks, validate implementation against milestone
                    if task.get('claude_driven') and 'milestone_content' in task:
                        validation_result = self._validate_milestone_implementation(
                            task, 
                            self.state.state["worktree_paths"].get(milestone_id),
                            milestone_id
                        )
                        
                        if not validation_result.valid:
                            logging.warning(f"Milestone validation failed for {task_id}: {'; '.join(validation_result.errors)}")
                            if self.verbose:
                                print(f"      [VALIDATION] Milestone implementation incomplete, retrying...")
                            
                            # Re-execute with gap information
                            gap_result = self._execute_milestone_gap_fix(
                                task, 
                                '; '.join(validation_result.errors),
                                self.state.state["worktree_paths"].get(milestone_id)
                            )
                            
                            if gap_result.success:
                                result = gap_result  # Use the gap-fixed result
                            else:
                                logging.error(f"Gap fix failed for {task_id}: {gap_result.error}")
                                result = TaskResult(task_id, False, error=f"Milestone validation failed: {'; '.join(validation_result.errors)}")
                    
                    if result.success:  # Check again after potential gap fixing
                        self.state.state["completed_tasks"].add(task_id)
                        logging.info(f"Task {task_id} completed successfully (attempt {attempt + 1})")
                        return result
                else:
                    error_details = f"Task {task_id} failed (attempt {attempt + 1}): {result.error}"
                    logging.warning(error_details)
                    
                    # Print error details in verbose mode
                    if self.verbose:
                        print(f"      [ERR] {error_details}")
                        if hasattr(result, 'output') and result.output:
                            print(f"      Output: {result.output[:200]}...")  # First 200 chars
                    
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
    
    def _validate_milestone_implementation(self, task: Dict, worktree_path: str, milestone_id: str) -> 'ValidationResult':
        """Validate that milestone implementation matches requirements"""
        try:
            milestone_content = task.get('milestone_content', '')
            
            # Create validation prompt
            validation_prompt = f"""Please validate if the current implementation matches the milestone requirements.

=== MILESTONE SPECIFICATION ===
{milestone_content}
=== END MILESTONE SPECIFICATION ===

VALIDATION INSTRUCTIONS:
1. Analyze the current project files and structure
2. Compare what has been implemented against the milestone specification above
3. Check if all acceptance criteria have been met
4. Identify any gaps or missing implementations

RESPONSE FORMAT:
If implementation is complete: "VALIDATION: COMPLETE - All requirements satisfied"
If implementation is incomplete: "VALIDATION: INCOMPLETE - [specific gaps found]"

Begin validation now."""

            # Execute validation in the worktree
            original_cwd = os.getcwd()
            if worktree_path and os.path.exists(worktree_path):
                os.chdir(worktree_path)
            
            try:
                validation_result = self.claude_wrapper._execute_claude_command(validation_prompt, 60, context="validation")
                output = validation_result.get("output", "").strip()
                
                if "VALIDATION: COMPLETE" in output:
                    return ValidationResult(True, [], [])
                else:
                    # Extract gap information
                    gap_info = output
                    if "VALIDATION: INCOMPLETE" in output:
                        gap_info = output.split("VALIDATION: INCOMPLETE - ", 1)[1] if " - " in output else output
                    
                    return ValidationResult(False, [gap_info], [])
                    
            finally:
                if worktree_path:
                    os.chdir(original_cwd)
                    
        except Exception as e:
            logging.error(f"Milestone validation error: {e}")
            return ValidationResult(False, [f"Validation error: {e}"], [])
    
    def _execute_milestone_gap_fix(self, task: Dict, gap_info: str, worktree_path: str) -> 'TaskResult':
        """Execute milestone implementation to fix identified gaps"""
        try:
            milestone_content = task.get('milestone_content', '')
            
            # Create gap-fixing prompt
            gap_prompt = f"""The previous implementation was incomplete. Please fix the identified gaps.

=== MILESTONE SPECIFICATION ===
{milestone_content}
=== END MILESTONE SPECIFICATION ===

=== IDENTIFIED GAPS ===
{gap_info}
=== END GAPS ===

INSTRUCTIONS:
1. Review the current implementation
2. Address all identified gaps above
3. Complete any missing parts of the milestone specification
4. Ensure all acceptance criteria are now satisfied
5. Create/modify files as needed using Write, Edit, or MultiEdit tools

Begin gap fixing now."""

            # Execute gap fixing
            original_cwd = os.getcwd()
            if worktree_path and os.path.exists(worktree_path):
                os.chdir(worktree_path)
                
            try:
                result = self.claude_wrapper._execute_claude_command(gap_prompt, 300, context="gap_fix")
                success = self.claude_wrapper._analyze_result(result, task)
                
                if success:
                    return TaskResult(task["id"], True, output=result.get("output", ""), duration=0)
                else:
                    return TaskResult(task["id"], False, error=result.get("error", "Gap fix failed"))
                    
            finally:
                if worktree_path:
                    os.chdir(original_cwd)
                    
        except Exception as e:
            logging.error(f"Gap fixing error: {e}")
            return TaskResult(task["id"], False, error=f"Gap fixing error: {e}")

    def _conduct_pre_review_validation(self, milestone_id: str, milestone: Dict, worktree_path: str) -> 'ValidationResult':
        """Conduct pre-review validation comparing implementation to milestone specification"""
        try:
            # Get milestone filepath to read raw content
            milestone_filepath = milestone.get('filepath', '')
            if not milestone_filepath or not os.path.exists(milestone_filepath):
                return ValidationResult(False, ["Milestone file not found"], [])
            
            # Read milestone content
            milestone_content = Path(milestone_filepath).read_text(encoding='utf-8')
            
            # Create comprehensive validation prompt
            validation_prompt = f"""Please conduct a comprehensive validation of the current implementation against the milestone specification.

=== MILESTONE SPECIFICATION ===
{milestone_content}
=== END MILESTONE SPECIFICATION ===

VALIDATION INSTRUCTIONS:
1. Analyze all files in the current project directory
2. Compare the current implementation against every requirement in the milestone specification
3. Check if all acceptance criteria have been satisfied
4. Verify that the implementation follows best practices and project conventions
5. Identify any missing functionality, incomplete implementations, or gaps

RESPONSE FORMAT:
If validation passes: "MILESTONE_VALIDATION: COMPLETE - All requirements fully implemented"
If validation fails: "MILESTONE_VALIDATION: INCOMPLETE - [detailed description of gaps and missing implementations]"

Begin comprehensive validation now."""

            # Execute validation in the worktree
            original_cwd = os.getcwd()
            if worktree_path and os.path.exists(worktree_path):
                os.chdir(worktree_path)
            
            try:
                validation_result = self.claude_wrapper._execute_claude_command(validation_prompt, 120, context="validation")
                output = validation_result.get("output", "").strip()
                
                if "MILESTONE_VALIDATION: COMPLETE" in output:
                    return ValidationResult(True, [], [])
                else:
                    # Extract gap information
                    gap_info = output
                    if "MILESTONE_VALIDATION: INCOMPLETE" in output:
                        gap_info = output.split("MILESTONE_VALIDATION: INCOMPLETE - ", 1)[1] if " - " in output else output
                    
                    return ValidationResult(False, [gap_info], [])
                    
            finally:
                if worktree_path:
                    os.chdir(original_cwd)
                    
        except Exception as e:
            logging.error(f"Pre-review validation error: {e}")
            return ValidationResult(False, [f"Pre-review validation error: {e}"], [])
    
    def _execute_stage_milestone_gap_fix(self, milestone_id: str, gap_info: str, worktree_path: str) -> bool:
        """Execute gap fixing for milestone during code review stage"""
        try:
            # Get all completed milestones in the same stage to provide context
            completed_milestones = []
            current_stage = self._extract_stage_from_milestone_id(milestone_id)
            
            for completed_task in self.state.state.get("completed_tasks", []):
                if completed_task.endswith("_claude_execution"):
                    completed_milestone_id = completed_task.replace("_claude_execution", "")
                    task_stage = self._extract_stage_from_milestone_id(completed_milestone_id)
                    if task_stage == current_stage:
                        # Get milestone filepath and content
                        milestone_filepath = self._get_milestone_filepath(completed_milestone_id)
                        if milestone_filepath:
                            milestone_content = Path(milestone_filepath).read_text(encoding='utf-8')
                            completed_milestones.append({
                                'id': completed_milestone_id,
                                'content': milestone_content
                            })
            
            # Create gap-fixing prompt with all stage milestone context
            all_milestones_content = ""
            for ms in completed_milestones:
                all_milestones_content += f"\n=== MILESTONE {ms['id'].upper()} ===\n{ms['content']}\n=== END {ms['id'].upper()} ===\n"
            
            gap_prompt = f"""Implementation gaps have been identified. Please fix all identified issues.

=== ALL STAGE MILESTONE SPECIFICATIONS ===
{all_milestones_content}
=== END ALL SPECIFICATIONS ===

=== IDENTIFIED GAPS FOR {milestone_id.upper()} ===
{gap_info}
=== END GAPS ===

INSTRUCTIONS:
1. Review the current project implementation
2. Consider all milestone specifications in this stage for context
3. Address all identified gaps for milestone {milestone_id}
4. Ensure the implementation meets all requirements across all milestones
5. Create/modify files as needed using Write, Edit, or MultiEdit tools
6. Maintain consistency with other implemented milestones

Begin comprehensive gap fixing now."""

            # Execute gap fixing
            original_cwd = os.getcwd()
            if worktree_path and os.path.exists(worktree_path):
                os.chdir(worktree_path)
                
            try:
                result = self.claude_wrapper._execute_claude_command(gap_prompt, 600, context="gap_fix")  # Longer timeout for comprehensive fix
                return result.get("success", True)  # Assume success if no error
                    
            finally:
                if worktree_path:
                    os.chdir(original_cwd)
                    
        except Exception as e:
            logging.error(f"Stage gap fixing error: {e}")
            return False
    
    def _extract_stage_from_milestone_id(self, milestone_id: str) -> int:
        """Extract stage number from milestone ID"""
        import re
        match = re.search(r'^(\d+)[a-z]', milestone_id)
        return int(match.group(1)) if match else 1
    
    def _get_milestone_filepath(self, milestone_id: str) -> str:
        """Get filepath for a milestone by ID"""
        milestones_dir = Path(self.config["milestones_dir"])
        milestone_file = milestones_dir / f"{milestone_id}.md"
        return str(milestone_file) if milestone_file.exists() else ""

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
                entry += "**Status:** [SUCCESS] COMPLETED\n\n"
            else:
                entry += "**Status:** [PARTIAL] PARTIALLY COMPLETED\n\n"
            
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
            
            with open(".orchestrator/execution_report.json", "w") as f:
                json.dump(report, f, indent=2, default=str)
            
            logging.info("Final execution report generated: .orchestrator/execution_report.json")
            
        except Exception as e:
            logging.error(f"Failed to generate final report: {e}")
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            # Cleanup worktrees
            use_worktrees = self.config.get("git", {}).get("use_worktrees", False)
            if use_worktrees and hasattr(self, 'state') and hasattr(self, 'worktree_manager'):
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
            if hasattr(self, 'state'):
                self.state.save_state()
            
            logging.info("Cleanup completed")
            
        except Exception as e:
            logging.error(f"Cleanup failed: {e}")

def main():
    """Main entry point"""
    # Setup Windows console for Unicode handling
    setup_windows_console()
    
    parser = argparse.ArgumentParser(
        description=f"Claude Code Milestone Orchestrator v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=get_detailed_version()
    )
    parser.add_argument("--version", action="version", version=get_version_string())
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
    parser.add_argument("--whatif", action="store_true",
                      help="Capture all prompts and commands without execution (includes failure scenarios)")
    parser.add_argument("--verbose", action="store_true",
                      help="Enable verbose output showing detailed progress")
    parser.add_argument("--reset", action="store_true",
                      help="Reset orchestrator state and start fresh")
    
    args = parser.parse_args()
    
    try:
        # Show version on startup
        print(get_version_string())
        print()
        
        # Initialize orchestrator
        orchestrator = MilestoneOrchestrator(args.config)
        orchestrator.verbose = args.verbose
        orchestrator.whatif = args.whatif
        
        # Pass whatif mode to components
        orchestrator.claude_wrapper.whatif = args.whatif
        orchestrator.claude_wrapper.orchestrator_prompts = orchestrator.whatif_prompts
        
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
                    status = "[OK]" if result.valid else "[FAIL]"
                    print(f"{status} {milestone['id']}: {milestone['title']}")
                    if not result.valid:
                        for error in result.errors:
                            print(f"   - {error}")
                except Exception as e:
                    print(f"[FAIL] {milestone['id']}: Validation failed - {e}")
            
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
        
        # Output whatif results to file if in whatif mode
        if args.whatif:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            whatif_file = f".orchestrator/whatif_prompts_{timestamp}.txt"
            
            try:
                with open(whatif_file, 'w', encoding='utf-8') as f:
                    f.write("# Claude Code Orchestrator - Whatif Mode Results\n")
                    f.write(f"# Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"# Milestones: {', '.join([m['id'] for m in milestones])}\n\n")
                    
                    for i, prompt_entry in enumerate(orchestrator.whatif_prompts, 1):
                        f.write(f"## Prompt #{i}\n")
                        f.write(f"**Context:** {prompt_entry['context']}\n")
                        f.write(f"**Timestamp:** {prompt_entry['timestamp']}\n")
                        f.write(f"**Timeout:** {prompt_entry['timeout']}s\n")
                        if prompt_entry.get('simulated_result'):
                            f.write(f"**Simulated Result:** {prompt_entry['simulated_result']}\n")
                        f.write("\n**Command:**\n")
                        f.write(f"```bash\n{prompt_entry['command_would_be']}\n```\n\n")
                        f.write("**Prompt:**\n")
                        f.write(f"```\n{prompt_entry['prompt']}\n```\n\n")
                        f.write("---\n\n")
                
                print(f"\nWhatif mode results written to: {whatif_file}")
                print(f"Total prompts captured: {len(orchestrator.whatif_prompts)}")
            except Exception as e:
                print(f"Failed to write whatif results: {e}")
        
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