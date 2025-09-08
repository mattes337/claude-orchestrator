#!/usr/bin/env python3
"""Version information for Claude Code Orchestrator"""

# Version format: MAJOR.MINOR.PATCH.BUILD
# MAJOR: Breaking changes
# MINOR: New features, non-breaking changes  
# PATCH: Bug fixes
# BUILD: Build number for tracking deployments

__version__ = "1.2.0.001"
__version_info__ = (1, 2, 0, 1)

# Build information
BUILD_DATE = "2025-09-08"
BUILD_COMMIT = "claude-driven"  # Latest commit hash

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