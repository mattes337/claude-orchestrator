#!/usr/bin/env python3
"""
Claude Orchestrator - Global command entry point
This wrapper allows the orchestrator to be run from any directory
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

def find_project_root():
    """Find the project root directory (containing milestones or git repo)"""
    current = Path.cwd()
    
    # Check if current directory is a valid project
    markers = ['.git', 'milestones', 'package.json', 'requirements.txt', 'pyproject.toml']
    
    # Search up the directory tree
    for parent in [current] + list(current.parents):
        for marker in markers:
            if (parent / marker).exists():
                return parent
    
    # If no project markers found, use current directory
    return current

def main():
    """Main entry point for the global claude-orchestrator command"""
    parser = argparse.ArgumentParser(
        description='Claude Code Milestone Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  claude-orchestrator                    # Run in current project directory
  claude-orchestrator --config custom.json  # Use custom config
  claude-orchestrator --milestone A1     # Execute specific milestone
  claude-orchestrator --stage 2           # Execute all milestones in stage 2
        """
    )
    
    # Pass all arguments to the actual orchestrator
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--milestone', help='Specific milestone to execute')
    parser.add_argument('--stage', help='Execute all milestones in a stage')
    parser.add_argument('--parallel', action='store_true', help='Execute milestones in parallel')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be executed without running')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--project-dir', help='Specify project directory to work in')
    
    args, unknown = parser.parse_known_args()
    
    # Determine project directory
    if args.project_dir:
        project_dir = Path(args.project_dir).resolve()
    else:
        project_dir = find_project_root()
    
    # Check if orchestrator.py exists in the installation directory
    orchestrator_path = Path(__file__).parent / 'orchestrator.py'
    
    if not orchestrator_path.exists():
        # Fallback to the original orchestrator.py in the same directory
        orchestrator_path = Path(__file__).parent.resolve() / 'orchestrator.py'
    
    if not orchestrator_path.exists():
        print(f"Error: orchestrator.py not found at {orchestrator_path}")
        sys.exit(1)
    
    # Change to project directory
    os.chdir(project_dir)
    print(f"Working in project directory: {project_dir}")
    
    # Build command to run the actual orchestrator
    cmd = [sys.executable, str(orchestrator_path)]
    
    # Add all arguments
    if args.config:
        cmd.extend(['--config', args.config])
    if args.milestone:
        cmd.extend(['--milestone', args.milestone])
    if args.stage:
        cmd.extend(['--stage', args.stage])
    if args.parallel:
        cmd.append('--parallel')
    if args.dry_run:
        cmd.append('--dry-run')
    if args.verbose:
        cmd.append('--verbose')
    
    # Add any unknown arguments
    cmd.extend(unknown)
    
    # Run the orchestrator
    try:
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\nOrchestrator interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error running orchestrator: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()