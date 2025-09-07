#!/usr/bin/env python3
"""
Shared Types Module for Claude Code Orchestrator
Contains common data types to avoid circular imports.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List

@dataclass
class ValidationResult:
    """Result of milestone or task validation"""
    valid: bool
    errors: List[str]
    warnings: List[str]
    score: float = 0.0
    
    def add_error(self, error: str):
        self.errors.append(error)
        self.valid = False
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)

@dataclass
class CodeReviewResult:
    """Result of code review process"""
    success: bool
    quality_score: float
    todos_found: List[str]
    quality_gates_failed: List[str]
    recommendations: List[str]
    report_file: str
    iterations_completed: int = 0
    
    @property
    def has_quality_issues(self) -> bool:
        return len(self.todos_found) > 0 or len(self.quality_gates_failed) > 0 or self.quality_score < 0.8

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