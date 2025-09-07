#!/usr/bin/env python3
"""
Milestone Preprocessor - Normalize milestone files to expected format
Converts any milestone format to the format expected by the orchestrator.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


class MilestonePreprocessor:
    """Preprocesses milestone files to normalize their format"""
    
    def __init__(self):
        self.task_patterns = [
            # Pattern 1: ## Task N: Title format
            r'^## Task (\d+): (.+)$',
            # Pattern 2: ## Task N - Title format  
            r'^## Task (\d+) - (.+)$',
            # Pattern 3: ## Task N. Title format
            r'^## Task (\d+)\. (.+)$',
            # Pattern 4: ## N. Title format
            r'^## (\d+)\. (.+)$',
            # Pattern 5: Just numbered headers
            r'^## (\d+) (.+)$',
        ]
        
        self.deliverables_patterns = [
            r'^\*\*Deliverables:\*\*(.+?)(?=\n\n|\n##|\Z)',
            r'^Deliverables:(.+?)(?=\n\n|\n##|\Z)',
            r'^### Deliverables(.+?)(?=\n\n|\n##|\n###|\Z)',
        ]
        
        self.acceptance_criteria_patterns = [
            r'## Acceptance Criteria(.+?)(?=\n##|\Z)',
            r'### Acceptance Criteria(.+?)(?=\n##|\n###|\Z)',
            r'^\*\*Acceptance Criteria:\*\*(.+?)(?=\n\n|\n##|\Z)',
        ]
    
    def preprocess_milestone(self, filepath: Path) -> str:
        """
        Preprocess a milestone file to normalize its format.
        
        Args:
            filepath: Path to the milestone file
            
        Returns:
            Normalized milestone content as string
        """
        content = filepath.read_text(encoding='utf-8')
        
        # Extract basic information
        milestone_id = filepath.stem
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = title_match.group(1) if title_match else milestone_id
        
        # Extract overview/description
        overview_match = re.search(
            r'## Overview\n(.+?)(?=\n##|\Z)', 
            content, 
            re.MULTILINE | re.DOTALL
        )
        overview = overview_match.group(1).strip() if overview_match else ""
        
        # Extract objectives  
        objectives_match = re.search(
            r'## Objectives\n(.+?)(?=\n##|\Z)', 
            content, 
            re.MULTILINE | re.DOTALL
        )
        objectives = objectives_match.group(1).strip() if objectives_match else ""
        
        # Detect and extract tasks
        tasks = self.extract_tasks(content, milestone_id)
        
        # Extract acceptance criteria
        acceptance_criteria = self.extract_acceptance_criteria(content)
        
        # Generate normalized content
        normalized_content = self.generate_normalized_content(
            title=title,
            overview=overview,
            objectives=objectives,
            tasks=tasks,
            acceptance_criteria=acceptance_criteria,
            milestone_id=milestone_id
        )
        
        return normalized_content
    
    def extract_tasks(self, content: str, milestone_id: str) -> List[Dict]:
        """Extract tasks from various formats and normalize them"""
        tasks = []
        
        # Method 1: Look for explicit "Task N" sections
        task_sections = self.find_task_sections(content)
        if task_sections:
            for task_num, task_title, task_content in task_sections:
                task = self.process_task_section(task_num, task_title, task_content, milestone_id)
                if task:
                    tasks.append(task)
        
        # Method 2: If no explicit tasks, convert "Issues to Fix" to tasks
        if not tasks:
            tasks = self.convert_issues_to_tasks(content, milestone_id)
        
        # Method 3: If no explicit tasks, convert technical requirements to tasks
        if not tasks:
            tasks = self.convert_requirements_to_tasks(content, milestone_id)
        
        # Method 4: If still no tasks, create from objectives
        if not tasks:
            tasks = self.convert_objectives_to_tasks(content, milestone_id)
            
        return tasks
    
    def find_task_sections(self, content: str) -> List[tuple]:
        """Find task sections using various patterns"""
        task_sections = []
        
        for pattern in self.task_patterns:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                task_num = match.group(1)
                task_title = match.group(2).strip()
                
                # Find the content after this task header
                start_pos = match.end()
                
                # Find next task or end of content
                next_task_pattern = r'\n## (?:Task \d+|Tasks?|\d+[\.\:])'
                next_match = re.search(next_task_pattern, content[start_pos:])
                
                if next_match:
                    end_pos = start_pos + next_match.start()
                    task_content = content[start_pos:end_pos].strip()
                else:
                    task_content = content[start_pos:].strip()
                
                task_sections.append((task_num, task_title, task_content))
        
        return task_sections
    
    def process_task_section(self, task_num: str, task_title: str, task_content: str, milestone_id: str) -> Dict:
        """Process a single task section and extract information"""
        task_id = f"{milestone_id}-T{task_num}"
        
        # Extract deliverables as requirements
        requirements = ""
        for pattern in self.deliverables_patterns:
            match = re.search(pattern, task_content, re.MULTILINE | re.DOTALL)
            if match:
                requirements = match.group(1).strip()
                break
        
        # If no deliverables, use the task content as requirements
        if not requirements:
            # Clean up the content for requirements
            requirements = self.clean_task_content(task_content)
        
        # Extract acceptance criteria (if any in the task)
        acceptance_criteria = ""
        ac_match = re.search(
            r'(?:Acceptance Criteria|Success Criteria):(.+?)(?=\n##|\n\*\*|\Z)', 
            task_content, 
            re.MULTILINE | re.DOTALL
        )
        if ac_match:
            acceptance_criteria = ac_match.group(1).strip()
        
        # Extract priority if mentioned
        priority = "medium"
        priority_match = re.search(r'Priority:\s*(High|Medium|Low)', task_content, re.IGNORECASE)
        if priority_match:
            priority = priority_match.group(1).lower()
        
        # Estimate time based on task complexity
        estimated_time = self.estimate_task_time(task_content)
        
        return {
            "id": task_id,
            "title": task_title,
            "requirements": requirements,
            "acceptance_criteria": acceptance_criteria,
            "priority": priority,
            "estimated_time": estimated_time,
            "milestone_id": milestone_id
        }
    
    def convert_requirements_to_tasks(self, content: str, milestone_id: str) -> List[Dict]:
        """Convert technical requirements sections to tasks"""
        tasks = []
        
        # Look for technical requirements section
        req_match = re.search(
            r'## Technical Requirements(.+?)(?=\n##|\Z)', 
            content, 
            re.MULTILINE | re.DOTALL
        )
        
        if req_match:
            req_content = req_match.group(1)
            
            # Extract subsections (### headings)
            subsections = re.findall(
                r'### (\d+\.\s*)?(.+?)\n(.+?)(?=\n###|\Z)', 
                req_content, 
                re.MULTILINE | re.DOTALL
            )
            
            for i, (num_prefix, section_title, section_content) in enumerate(subsections):
                task_id = f"{milestone_id}-T{i+1}"
                tasks.append({
                    "id": task_id,
                    "title": section_title.strip(),
                    "requirements": section_content.strip(),
                    "acceptance_criteria": "",
                    "priority": "medium",
                    "estimated_time": 30,
                    "milestone_id": milestone_id
                })
        
        return tasks
    
    def convert_issues_to_tasks(self, content: str, milestone_id: str) -> List[Dict]:
        """Convert 'Issues to Fix' sections to tasks"""
        tasks = []
        
        # Look for "Issues to Fix" section
        issues_match = re.search(
            r'## Issues to Fix\n(.+?)(?=\n## [^#]|\Z)', 
            content, 
            re.MULTILINE | re.DOTALL
        )
        
        if issues_match:
            issues_content = issues_match.group(1)
            
            # Find numbered subsections like "### 1. Title"
            issue_sections = re.findall(
                r'### (\d+)\.\s*(.+?)\n(.*?)(?=\n### \d+\.|\Z)', 
                issues_content, 
                re.MULTILINE | re.DOTALL
            )
            
            for issue_num, issue_title, issue_content in issue_sections:
                task_id = f"{milestone_id}-T{issue_num}"
                
                # Extract problem description
                problem_match = re.search(r'\*\*Problem\*\*:\s*(.+?)(?=\n\*\*|\Z)', issue_content, re.DOTALL)
                problem = problem_match.group(1).strip() if problem_match else ""
                
                # Extract expected behavior
                expected_match = re.search(r'\*\*Expected Behavior\*\*:\s*(.+?)(?=\n\*\*|\Z)', issue_content, re.DOTALL)
                expected = expected_match.group(1).strip() if expected_match else ""
                
                # Build comprehensive requirements
                requirements = f"Fix Issue: {issue_title.strip()}\n\n"
                if problem:
                    requirements += f"Problem: {problem}\n\n"
                if expected:
                    requirements += f"Expected Behavior: {expected}\n\n"
                requirements += "Please investigate and implement a fix for this issue."
                
                # Use problem + expected as acceptance criteria
                acceptance_criteria = ""
                if problem and expected:
                    acceptance_criteria = f"- Issue is resolved: {problem.replace(problem[:50] + '...', problem[:50] + '...' if len(problem) > 50 else problem)}\n"
                    acceptance_criteria += f"- Expected behavior achieved: {expected.replace(expected[:50] + '...', expected[:50] + '...' if len(expected) > 50 else expected)}"
                
                tasks.append({
                    "id": task_id,
                    "title": f"Fix: {issue_title.strip()}",
                    "requirements": requirements,
                    "acceptance_criteria": acceptance_criteria,
                    "priority": "high",  # Bug fixes are typically high priority
                    "estimated_time": 45,  # Bug fixes often take longer
                    "milestone_id": milestone_id
                })
        
        return tasks
    
    def convert_objectives_to_tasks(self, content: str, milestone_id: str) -> List[Dict]:
        """Convert objectives to tasks as last resort"""
        tasks = []
        
        # Look for objectives
        obj_match = re.search(
            r'## Objectives\n(.+?)(?=\n##|\Z)', 
            content, 
            re.MULTILINE | re.DOTALL
        )
        
        if obj_match:
            obj_content = obj_match.group(1)
            
            # Extract bullet points
            objectives = re.findall(r'^\s*[-*]\s*(.+)$', obj_content, re.MULTILINE)
            
            for i, objective in enumerate(objectives):
                task_id = f"{milestone_id}-T{i+1}"
                tasks.append({
                    "id": task_id,
                    "title": objective.strip(),
                    "requirements": f"Implement: {objective.strip()}",
                    "acceptance_criteria": "",
                    "priority": "medium",
                    "estimated_time": 30,
                    "milestone_id": milestone_id
                })
        
        return tasks
    
    def extract_acceptance_criteria(self, content: str) -> str:
        """Extract acceptance criteria from various locations"""
        for pattern in self.acceptance_criteria_patterns:
            match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return ""
    
    def clean_task_content(self, content: str) -> str:
        """Clean task content for use as requirements"""
        # Remove markdown formatting
        cleaned = re.sub(r'\*\*(.+?)\*\*', r'\1', content)  # Bold
        cleaned = re.sub(r'\*(.+?)\*', r'\1', cleaned)      # Italic
        cleaned = re.sub(r'`(.+?)`', r'\1', cleaned)        # Code
        
        # Remove extra whitespace
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
        
        return cleaned.strip()
    
    def estimate_task_time(self, content: str) -> int:
        """Estimate task time based on content complexity"""
        # Simple heuristic based on content length and complexity
        word_count = len(content.split())
        
        if word_count < 50:
            return 15
        elif word_count < 150:
            return 30
        elif word_count < 300:
            return 60
        else:
            return 90
    
    def generate_normalized_content(self, title: str, overview: str, objectives: str, 
                                  tasks: List[Dict], acceptance_criteria: str, 
                                  milestone_id: str) -> str:
        """Generate normalized milestone content in expected format"""
        content = f"# {title}\n\n"
        
        if overview:
            content += f"{overview}\n\n"
        
        if objectives:
            content += f"## Objectives\n{objectives}\n\n"
        
        # Add tasks in expected format
        for task in tasks:
            task_num = task["id"].split("-T")[1]
            content += f"## Task {task_num}: {task['title']}\n"
            
            if task["requirements"]:
                content += f"### Requirements\n{task['requirements']}\n\n"
            
            if task["acceptance_criteria"]:
                content += f"### Acceptance Criteria\n{task['acceptance_criteria']}\n\n"
            
            # Add metadata
            content += f"Priority: {task['priority'].title()}\n"
            content += f"Estimated Time: {task['estimated_time']} minutes\n\n"
        
        # Add dependencies section if needed
        content += "## Dependencies\n"
        content += "- None specified\n\n"
        
        # Add overall acceptance criteria
        if acceptance_criteria:
            content += f"## Acceptance Criteria\n{acceptance_criteria}\n\n"
        
        return content
    
    def preprocess_milestone_file(self, input_path: Path, output_path: Optional[Path] = None) -> Path:
        """
        Preprocess a milestone file and save the normalized version.
        
        Args:
            input_path: Path to input milestone file
            output_path: Path for output (if None, creates temp file)
            
        Returns:
            Path to the normalized milestone file
        """
        if output_path is None:
            output_path = input_path.parent / f"normalized_{input_path.name}"
        
        normalized_content = self.preprocess_milestone(input_path)
        output_path.write_text(normalized_content, encoding='utf-8')
        
        return output_path


def main():
    """CLI entry point for preprocessing milestone files"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Normalize milestone file format")
    parser.add_argument("input_file", help="Input milestone file")
    parser.add_argument("-o", "--output", help="Output file (default: normalized_<input>)")
    
    args = parser.parse_args()
    
    preprocessor = MilestonePreprocessor()
    input_path = Path(args.input_file)
    output_path = Path(args.output) if args.output else None
    
    try:
        result_path = preprocessor.preprocess_milestone_file(input_path, output_path)
        print(f"Normalized milestone saved to: {result_path}")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())