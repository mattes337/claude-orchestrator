#!/usr/bin/env python3
"""
Claude Orchestrator Development Wrapper
This script can be used directly or as a fallback when the installed package needs updates.
"""

import sys
import os
from pathlib import Path

# Add the current directory to Python path if it contains orchestrator.py
current_dir = Path(__file__).parent
if (current_dir / "orchestrator.py").exists():
    sys.path.insert(0, str(current_dir))

try:
    # Try to import from the development version
    import orchestrator
    if __name__ == "__main__":
        sys.exit(orchestrator.main())
except ImportError:
    # Fallback to installed package
    try:
        import claude_orchestrator
        if __name__ == "__main__":
            sys.exit(claude_orchestrator.main())
    except ImportError:
        print("Error: Neither development nor installed version of claude-orchestrator found")
        print("Please ensure you're running from the development directory or have installed the package")
        sys.exit(1)