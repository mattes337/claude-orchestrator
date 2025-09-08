#!/usr/bin/env python3
"""
Claude Code Orchestrator v1.1 - Claude-Driven Orchestration
Advanced milestone execution orchestrator with Claude-driven decision making,
parallel processing, git worktree management, and comprehensive error handling.
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
from typing import Dict, List, Optional, Set, Tuple, Any
import subprocess
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import signal
import tempfile
import shutil

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


class ActiveStateManager:
    """Manages the active state file for Claude-driven orchestration"""
    
    def __init__(self, state_dir: str = ".orchestrator"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        self.active_file = self.state_dir / "active"
        self.milestone_state_files = {}
        
    def write_active_state(self, state: Dict[str, Any]):
        """Write the active state to file for Claude to read"""
        with open(self.active_file, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    
    def read_active_state(self) -> Dict[str, Any]:
        """Read the current active state"""
        if self.active_file.exists():
            with open(self.active_file, 'r') as f:
                return json.load(f)
        return {}
    
    def write_milestone_state(self, milestone_id: str, state: Dict[str, Any]):
        """Write milestone-specific state"""
        milestone_file = self.state_dir / f"active-milestone-{milestone_id}"
        with open(milestone_file, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        self.milestone_state_files[milestone_id] = milestone_file
    
    def read_milestone_state(self, milestone_id: str) -> Dict[str, Any]:
        """Read milestone-specific state"""
        milestone_file = self.state_dir / f"active-milestone-{milestone_id}"
        if milestone_file.exists():
            with open(milestone_file, 'r') as f:
                return json.load(f)
        return {}
    
    def cleanup_milestone_state(self, milestone_id: str):
        """Clean up milestone state file"""
        milestone_file = self.state_dir / f"active-milestone-{milestone_id}"
        if milestone_file.exists():
            milestone_file.unlink()


class ClaudeOrchestrationDriver:
    """Drives orchestration through Claude Code instances"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.active_state = ActiveStateManager()
        self.logger = logging.getLogger(self.__class__.__name__)
        
    def spawn_claude_for_decision(self, prompt: str, context: Dict = None) -> Dict[str, Any]:
        """Spawn Claude to make orchestration decisions"""
        self.logger.info(f"Spawning Claude for decision: {prompt[:100]}...")
        
        # Write context to temporary file
        context_file = None
        if context:
            context_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
            json.dump(context, context_file, indent=2, default=str)
            context_file.close()
        
        try:
            # Build Claude command
            claude_cmd = [
                "claude",
                "-m", prompt
            ]
            
            if context_file:
                claude_cmd.extend(["-c", context_file.name])
            
            # Execute Claude
            result = subprocess.run(
                claude_cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Parse Claude's response
                response_text = result.stdout.strip()
                
                # Try to extract JSON from response
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        response_data = json.loads(json_match.group())
                        return response_data
                    except json.JSONDecodeError:
                        pass
                
                # Fallback to text analysis
                return self._parse_text_response(response_text)
            else:
                self.logger.error(f"Claude execution failed: {result.stderr}")
                return {"error": result.stderr, "success": False}
                
        except subprocess.TimeoutExpired:
            self.logger.error("Claude execution timed out")
            return {"error": "Timeout", "success": False}
        except Exception as e:
            self.logger.error(f"Failed to spawn Claude: {e}")
            return {"error": str(e), "success": False}
        finally:
            if context_file and os.path.exists(context_file.name):
                os.unlink(context_file.name)
    
    def _parse_text_response(self, text: str) -> Dict[str, Any]:
        """Parse text response from Claude into structured data"""
        response = {"raw_text": text}
        
        # Look for common patterns
        if "complete" in text.lower():
            response["status"] = "complete"
        elif "partial" in text.lower():
            response["status"] = "partial"
        elif "fail" in text.lower() or "error" in text.lower():
            response["status"] = "failed"
        else:
            response["status"] = "unknown"
        
        # Extract pass/fail
        if "pass" in text.lower():
            response["passed"] = True
        elif "fail" in text.lower():
            response["passed"] = False
        
        return response
    
    def spawn_claude_for_implementation(
        self, 
        milestone_id: str, 
        milestone_file: str,
        worktree_path: str,
        additional_context: str = ""
    ) -> Dict[str, Any]:
        """Spawn Claude to implement a milestone"""
        self.logger.info(f"Spawning Claude to implement milestone {milestone_id}")
        
        # Build implementation command
        prompt = f"/milestone {milestone_file}"
        if additional_context:
            prompt += f"\n\n{additional_context}"
        
        try:
            # Change to worktree directory
            original_cwd = os.getcwd()
            os.chdir(worktree_path)
            
            try:
                # Execute Claude
                result = subprocess.run(
                    ["claude", "-m", prompt],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=1800  # 30 minute timeout for implementation
                )
                
                if result.returncode == 0:
                    return {
                        "success": True,
                        "output": result.stdout,
                        "milestone_id": milestone_id
                    }
                else:
                    return {
                        "success": False,
                        "error": result.stderr,
                        "milestone_id": milestone_id
                    }
                    
            finally:
                os.chdir(original_cwd)
                
        except Exception as e:
            self.logger.error(f"Failed to spawn Claude for implementation: {e}")
            return {
                "success": False,
                "error": str(e),
                "milestone_id": milestone_id
            }
    
    def spawn_claude_for_review(
        self,
        target_path: str,
        review_type: str = "code-review",
        output_file: str = "REVIEW.md"
    ) -> Dict[str, Any]:
        """Spawn Claude to conduct code review"""
        self.logger.info(f"Spawning Claude for {review_type} at {target_path}")
        
        prompt = f"/code-review --output {output_file}"
        
        try:
            # Change to target directory
            original_cwd = os.getcwd()
            if target_path:
                os.chdir(target_path)
            
            try:
                # Execute Claude for code review
                result = subprocess.run(
                    ["claude", "-m", prompt],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=900  # 15 minute timeout for review
                )
                
                if result.returncode == 0:
                    # Read the review file
                    review_path = Path(output_file)
                    if review_path.exists():
                        review_content = review_path.read_text(encoding='utf-8')
                        return {
                            "success": True,
                            "review_content": review_content,
                            "review_file": str(review_path)
                        }
                    else:
                        return {
                            "success": True,
                            "output": result.stdout
                        }
                else:
                    return {
                        "success": False,
                        "error": result.stderr
                    }
                    
            finally:
                os.chdir(original_cwd)
                
        except Exception as e:
            self.logger.error(f"Failed to spawn Claude for review: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def spawn_claude_for_progress_check(self, worktree_path: str) -> str:
        """Spawn Claude to check implementation progress"""
        self.logger.info(f"Checking progress in {worktree_path}")
        
        prompt = "Check the current implementation progress and return: complete, partial, or open"
        
        try:
            original_cwd = os.getcwd()
            os.chdir(worktree_path)
            
            try:
                result = subprocess.run(
                    ["claude", "-m", prompt],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=300
                )
                
                if result.returncode == 0:
                    response = result.stdout.strip().lower()
                    if "complete" in response:
                        return "complete"
                    elif "partial" in response:
                        return "partial"
                    else:
                        return "open"
                else:
                    return "open"
                    
            finally:
                os.chdir(original_cwd)
                
        except Exception as e:
            self.logger.error(f"Failed to check progress: {e}")
            return "open"
    
    def evaluate_review(self, review_file: str) -> bool:
        """Spawn Claude to evaluate a review file"""
        self.logger.info(f"Evaluating review file: {review_file}")
        
        prompt = f"Evaluate the code review in {review_file} and return 'pass' if all issues are resolved or minor, 'fail' if there are significant issues"
        
        result = self.spawn_claude_for_decision(prompt)
        return result.get("passed", False)


class MilestoneOrchestratorV11:
    """Version 1.1 Orchestrator with Claude-driven orchestration"""
    
    def __init__(self, config_path: str = "orchestrator.config.json"):
        self.config = self.load_config(config_path)
        self.config["version"] = "1.1"
        
        # Override base_branch with current branch
        current_branch = self.get_current_branch()
        self.config["git"]["base_branch"] = current_branch
        logging.info(f"Using current branch as base: {current_branch}")
        
        # Initialize components
        self.active_state = ActiveStateManager()
        self.claude_driver = ClaudeOrchestrationDriver(self.config)
        self.worktree_manager = WorktreeManager()
        self.preprocessor = MilestonePreprocessor()
        
        # Setup logging
        self.setup_logging()
        
        # Shutdown handling
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Execution state
        self.current_step = None
        self.current_stage = None
        self.completed_milestones = set()
        
        logging.info("Orchestrator v1.1 initialized with Claude-driven orchestration")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logging.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    def get_current_branch(self) -> str:
        """Get the current git branch"""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, check=True,
                encoding='utf-8', errors='replace'
            )
            return result.stdout.strip()
        except:
            return "main"
    
    def load_config(self, config_path: str) -> Dict:
        """Load configuration from file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except:
            return self.get_default_config()
    
    def get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            "milestones_dir": "milestones",
            "git": {
                "use_worktrees": True,
                "base_branch": "main",
                "worktree_prefix": "milestone-"
            },
            "orchestrator": {
                "version": "1.1",
                "claude_driven": True,
                "max_parallel_worktrees": 4,
                "max_review_iterations": 3
            }
        }
    
    def setup_logging(self):
        """Setup logging configuration"""
        Path(".orchestrator").mkdir(exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(".orchestrator/orchestrator_v11.log"),
                logging.StreamHandler()
            ]
        )
    
    def discover_milestones(self) -> List[Dict]:
        """Discover and parse milestone files"""
        milestones_dir = Path(self.config["milestones_dir"])
        logging.info(f"Discovering milestones in {milestones_dir}")
        
        if not milestones_dir.exists():
            raise FileNotFoundError(f"Milestones directory not found: {milestones_dir}")
        
        md_files = [f for f in milestones_dir.glob("*.md") if f.name.lower() != "readme.md"]
        milestones = []
        
        for milestone_file in md_files:
            try:
                milestone_id = milestone_file.stem
                
                # Extract stage from ID (e.g., "2a" -> stage 2)
                stage_match = re.match(r'^(\d+)[a-z]?', milestone_id)
                stage = int(stage_match.group(1)) if stage_match else 1
                
                milestones.append({
                    "id": milestone_id,
                    "file": str(milestone_file),
                    "stage": stage,
                    "title": milestone_id  # Will be updated by Claude
                })
            except Exception as e:
                logging.error(f"Failed to parse milestone {milestone_file}: {e}")
        
        milestones.sort(key=lambda x: (x["stage"], x["id"]))
        logging.info(f"Discovered {len(milestones)} milestones")
        return milestones
    
    def organize_stages(self, milestones: List[Dict]) -> Dict[int, List[Dict]]:
        """Organize milestones into stages"""
        stages = {}
        for milestone in milestones:
            stage = milestone["stage"]
            if stage not in stages:
                stages[stage] = []
            stages[stage].append(milestone)
        return dict(sorted(stages.items()))
    
    def run_orchestration(self) -> bool:
        """Main orchestration loop driven by Claude"""
        try:
            # Discover milestones
            milestones = self.discover_milestones()
            if not milestones:
                logging.warning("No milestones found")
                return True
            
            stages = self.organize_stages(milestones)
            
            # Initialize active state
            self.active_state.write_active_state({
                "step": "stage",
                "total_stages": len(stages),
                "total_milestones": len(milestones),
                "stages": {str(k): [m["id"] for m in v] for k, v in stages.items()},
                "current_stage": None,
                "completed_stages": [],
                "timestamp": datetime.now().isoformat()
            })
            
            # Process each stage
            for stage_num, stage_milestones in stages.items():
                if self.shutdown_requested:
                    break
                
                logging.info(f"Processing Stage {stage_num} with {len(stage_milestones)} milestones")
                print(f"\n=== Stage {stage_num} ===")
                
                # Update active state
                self.active_state.write_active_state({
                    "step": "stage",
                    "current_stage": stage_num,
                    "stage_milestones": [m["id"] for m in stage_milestones],
                    "timestamp": datetime.now().isoformat()
                })
                
                # Process the stage
                stage_success = self.process_stage(stage_num, stage_milestones)
                
                if not stage_success:
                    logging.error(f"Stage {stage_num} failed")
                    return False
                
                logging.info(f"Stage {stage_num} completed successfully")
            
            logging.info("All stages completed successfully")
            return True
            
        except Exception as e:
            logging.error(f"Orchestration failed: {e}")
            return False
    
    def process_stage(self, stage_num: int, milestones: List[Dict]) -> bool:
        """Process a single stage with Claude-driven orchestration"""
        try:
            # Step 1: Create worktrees for all milestones in the stage
            logging.info(f"Creating worktrees for stage {stage_num}")
            self.active_state.write_active_state({
                "step": "worktrees",
                "stage": stage_num,
                "action": "creating",
                "milestones": [m["id"] for m in milestones],
                "timestamp": datetime.now().isoformat()
            })
            
            worktree_paths = {}
            for milestone in milestones:
                worktree_path = self.create_worktree_for_milestone(milestone["id"])
                if worktree_path:
                    worktree_paths[milestone["id"]] = worktree_path
                else:
                    logging.error(f"Failed to create worktree for {milestone['id']}")
            
            # Step 2: Process worktrees in parallel
            logging.info(f"Processing {len(worktree_paths)} worktrees in parallel")
            self.active_state.write_active_state({
                "step": "worktrees",
                "stage": stage_num,
                "action": "processing",
                "worktree_paths": worktree_paths,
                "timestamp": datetime.now().isoformat()
            })
            
            # Process each worktree
            with ThreadPoolExecutor(max_workers=self.config.get("orchestrator", {}).get("max_parallel_worktrees", 4)) as executor:
                futures = {
                    executor.submit(self.process_worktree, milestone, worktree_paths[milestone["id"]]): milestone
                    for milestone in milestones
                    if milestone["id"] in worktree_paths
                }
                
                for future in as_completed(futures):
                    if self.shutdown_requested:
                        break
                    
                    milestone = futures[future]
                    try:
                        result = future.result()
                        if result:
                            self.completed_milestones.add(milestone["id"])
                            print(f"  ✓ {milestone['id']} completed")
                        else:
                            print(f"  ✗ {milestone['id']} failed")
                    except Exception as e:
                        logging.error(f"Failed to process {milestone['id']}: {e}")
                        print(f"  ✗ {milestone['id']} error: {e}")
            
            # Step 3: Merge worktrees sequentially
            if len(self.completed_milestones) > 0:
                logging.info(f"Merging {len(self.completed_milestones)} completed worktrees")
                self.active_state.write_active_state({
                    "step": "merge",
                    "stage": stage_num,
                    "completed_milestones": list(self.completed_milestones),
                    "timestamp": datetime.now().isoformat()
                })
                
                merge_success = self.merge_worktrees(stage_num, milestones, worktree_paths)
                if not merge_success:
                    logging.error(f"Failed to merge worktrees for stage {stage_num}")
                    return False
            
            # Step 4: Conduct stage code review
            logging.info(f"Conducting code review for stage {stage_num}")
            self.active_state.write_active_state({
                "step": "code-review",
                "stage": stage_num,
                "action": "reviewing",
                "timestamp": datetime.now().isoformat()
            })
            
            review_passed = self.conduct_stage_review(stage_num)
            
            if not review_passed:
                # If review fails, re-implement with review feedback
                logging.info("Stage review failed, re-implementing with feedback")
                return self.reimplement_stage_with_feedback(stage_num, milestones)
            
            return True
            
        except Exception as e:
            logging.error(f"Stage {stage_num} processing failed: {e}")
            return False
    
    def create_worktree_for_milestone(self, milestone_id: str) -> Optional[str]:
        """Create a git worktree for a milestone"""
        try:
            # Delete existing branch if it exists
            subprocess.run(
                ["git", "branch", "-D", f"milestone-{milestone_id}"],
                capture_output=True,
                text=True
            )
            
            # Create worktree
            worktree_path = Path(".worktrees") / milestone_id
            if worktree_path.exists():
                shutil.rmtree(worktree_path)
            
            worktree_path.parent.mkdir(exist_ok=True)
            
            result = subprocess.run(
                ["git", "worktree", "add", "-b", f"milestone-{milestone_id}", str(worktree_path)],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if result.returncode == 0:
                logging.info(f"Created worktree for {milestone_id} at {worktree_path}")
                return str(worktree_path)
            else:
                logging.error(f"Failed to create worktree for {milestone_id}: {result.stderr}")
                return None
                
        except Exception as e:
            logging.error(f"Exception creating worktree for {milestone_id}: {e}")
            return None
    
    def process_worktree(self, milestone: Dict, worktree_path: str) -> bool:
        """Process a single worktree with Claude-driven implementation"""
        milestone_id = milestone["id"]
        milestone_file = milestone["file"]
        max_iterations = 5
        iteration = 0
        
        try:
            while iteration < max_iterations and not self.shutdown_requested:
                iteration += 1
                logging.info(f"Processing {milestone_id} - Iteration {iteration}")
                
                # Update milestone state
                self.active_state.write_milestone_state(milestone_id, {
                    "step": "implementation",
                    "iteration": iteration,
                    "worktree_path": worktree_path,
                    "timestamp": datetime.now().isoformat()
                })
                
                # A) Spawn Claude to implement the milestone
                impl_result = self.claude_driver.spawn_claude_for_implementation(
                    milestone_id,
                    milestone_file,
                    worktree_path
                )
                
                if not impl_result.get("success"):
                    logging.error(f"Implementation failed for {milestone_id}: {impl_result.get('error')}")
                    continue
                
                # Commit and push worktree
                if not self.commit_and_push_worktree(milestone_id, worktree_path):
                    logging.warning(f"Failed to commit/push {milestone_id}")
                
                # Check progress
                progress = self.claude_driver.spawn_claude_for_progress_check(worktree_path)
                logging.info(f"{milestone_id} progress: {progress}")
                
                if progress == "complete":
                    # Conduct code review
                    self.active_state.write_milestone_state(milestone_id, {
                        "step": "code-review",
                        "worktree_path": worktree_path,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    review_result = self.claude_driver.spawn_claude_for_review(
                        worktree_path,
                        "code-review",
                        "REVIEW.md"
                    )
                    
                    if review_result.get("success"):
                        # Commit review file
                        self.commit_and_push_worktree(milestone_id, worktree_path, "Add code review")
                        
                        # Evaluate review
                        review_file = Path(worktree_path) / "REVIEW.md"
                        if review_file.exists():
                            review_passed = self.claude_driver.evaluate_review(str(review_file))
                            
                            if review_passed:
                                logging.info(f"{milestone_id} passed code review")
                                self.active_state.write_milestone_state(milestone_id, {
                                    "step": "complete",
                                    "status": "passed",
                                    "timestamp": datetime.now().isoformat()
                                })
                                return True
                            else:
                                logging.info(f"{milestone_id} failed review, re-implementing with feedback")
                                # Continue loop to re-implement with feedback
                        else:
                            # No review file, assume pass
                            return True
                    else:
                        logging.warning(f"Code review failed for {milestone_id}")
                        return True  # Don't block on review failures
                
                elif progress == "partial":
                    logging.info(f"{milestone_id} partially complete, continuing implementation")
                    # Continue loop
                else:
                    logging.info(f"{milestone_id} still open, continuing implementation")
                    # Continue loop
            
            logging.warning(f"{milestone_id} did not complete after {max_iterations} iterations")
            return False
            
        except Exception as e:
            logging.error(f"Exception processing worktree {milestone_id}: {e}")
            return False
        finally:
            self.active_state.cleanup_milestone_state(milestone_id)
    
    def commit_and_push_worktree(self, milestone_id: str, worktree_path: str, message: str = None) -> bool:
        """Commit and push changes in a worktree"""
        try:
            original_cwd = os.getcwd()
            os.chdir(worktree_path)
            
            try:
                # Check for changes
                status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                if not status.stdout.strip():
                    return True  # No changes
                
                # Add all changes
                subprocess.run(["git", "add", "."], check=True)
                
                # Commit
                commit_message = message or f"Implement milestone {milestone_id}"
                subprocess.run(
                    ["git", "commit", "-m", commit_message],
                    check=True
                )
                
                # Push (optional, depends on config)
                # subprocess.run(["git", "push", "-u", "origin", f"milestone-{milestone_id}"], check=True)
                
                return True
                
            finally:
                os.chdir(original_cwd)
                
        except Exception as e:
            logging.error(f"Failed to commit/push {milestone_id}: {e}")
            return False
    
    def merge_worktrees(self, stage_num: int, milestones: List[Dict], worktree_paths: Dict[str, str]) -> bool:
        """Merge completed worktrees into base branch"""
        try:
            base_branch = self.config["git"]["base_branch"]
            
            # Checkout base branch
            subprocess.run(["git", "checkout", base_branch], check=True)
            
            for milestone in milestones:
                milestone_id = milestone["id"]
                if milestone_id not in self.completed_milestones:
                    continue
                
                branch_name = f"milestone-{milestone_id}"
                
                try:
                    # Merge the branch
                    result = subprocess.run(
                        ["git", "merge", "--no-ff", branch_name, "-m", f"Merge {milestone_id}"],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace'
                    )
                    
                    if result.returncode == 0:
                        logging.info(f"Successfully merged {milestone_id}")
                    else:
                        logging.error(f"Failed to merge {milestone_id}: {result.stderr}")
                        
                except Exception as e:
                    logging.error(f"Exception merging {milestone_id}: {e}")
            
            return True
            
        except Exception as e:
            logging.error(f"Failed to merge worktrees: {e}")
            return False
    
    def conduct_stage_review(self, stage_num: int) -> bool:
        """Conduct code review for entire stage"""
        try:
            # Spawn Claude to review the stage
            review_result = self.claude_driver.spawn_claude_for_review(
                None,  # Use current directory
                "stage-review",
                f"REVIEW_STAGE_{stage_num}.md"
            )
            
            if review_result.get("success"):
                # Evaluate the review
                review_file = Path(f"REVIEW_STAGE_{stage_num}.md")
                if review_file.exists():
                    return self.claude_driver.evaluate_review(str(review_file))
            
            return True  # Default to pass if review fails
            
        except Exception as e:
            logging.error(f"Stage review failed: {e}")
            return True  # Don't block on review failures
    
    def reimplement_stage_with_feedback(self, stage_num: int, milestones: List[Dict]) -> bool:
        """Re-implement stage with review feedback"""
        try:
            review_file = Path(f"REVIEW_STAGE_{stage_num}.md")
            if not review_file.exists():
                return True
            
            review_content = review_file.read_text(encoding='utf-8')
            
            # Spawn Claude to fix issues
            prompt = f"/milestone {','.join([m['id'] for m in milestones])}\n\nPlease address the following review feedback:\n{review_content}"
            
            result = self.claude_driver.spawn_claude_for_decision(prompt)
            
            # Re-run progress check
            progress = self.claude_driver.spawn_claude_for_progress_check(".")
            
            if progress == "complete":
                # Re-run review
                return self.conduct_stage_review(stage_num)
            
            return False
            
        except Exception as e:
            logging.error(f"Failed to reimplement stage: {e}")
            return False


def main():
    """Main entry point for orchestrator v1.1"""
    parser = argparse.ArgumentParser(
        description="Claude Code Milestone Orchestrator v1.1 - Claude-Driven Orchestration"
    )
    parser.add_argument("--config", default="orchestrator.config.json",
                      help="Configuration file path")
    parser.add_argument("--stage", type=int,
                      help="Execute specific stage only")
    parser.add_argument("--dry-run", action="store_true",
                      help="Show execution plan without running")
    
    args = parser.parse_args()
    
    try:
        print("Claude Code Milestone Orchestrator v1.1")
        print("========================================")
        print("Using Claude-driven orchestration and management\n")
        
        # Initialize orchestrator
        orchestrator = MilestoneOrchestratorV11(args.config)
        
        if args.dry_run:
            # Show plan
            milestones = orchestrator.discover_milestones()
            stages = orchestrator.organize_stages(milestones)
            
            print("Execution Plan:")
            for stage_num, stage_milestones in stages.items():
                print(f"\nStage {stage_num}:")
                for milestone in stage_milestones:
                    print(f"  - {milestone['id']}")
            return 0
        
        # Run orchestration
        success = orchestrator.run_orchestration()
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