#!/usr/bin/env python3
"""Version information for Claude Code Orchestrator"""

# Version format: MAJOR.MINOR.PATCH.BUILD
# MAJOR: Breaking changes
# MINOR: New features, non-breaking changes  
# PATCH: Bug fixes
# BUILD: Build number for tracking deployments

__version__ = "1.1.0.002"
__version_info__ = (1, 1, 0, 2)

# Build information
BUILD_DATE = "2025-01-08"
BUILD_COMMIT = "v1.1-claude"  # Version 1.1 with Claude-driven orchestration

def get_version_string() -> str:
    """Get formatted version string"""
    return f"Claude Code Orchestrator v{__version__} (build {BUILD_DATE})"

def get_detailed_version() -> str:
    """Get detailed version information"""
    return f"""Claude Code Orchestrator
Version: {__version__}
Build Date: {BUILD_DATE}
Commit: {BUILD_COMMIT}
Python Package: claude-orchestrator"""