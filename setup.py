#!/usr/bin/env python3
"""
Setup script for Claude Orchestrator
Installs the orchestrator as a global command: claude-orchestrator
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_long_description():
    with open('README.md', 'r', encoding='utf-8') as fh:
        return fh.read()

# Get the list of requirements
def get_requirements():
    requirements = []
    if os.path.exists('requirements.txt'):
        with open('requirements.txt', 'r') as f:
            requirements = [line.strip() for line in f 
                          if line.strip() and not line.startswith('#')]
    return requirements

setup(
    name='claude-orchestrator',
    version='1.0.0',
    author='Claude Orchestrator Team',
    description='Claude Code Milestone Orchestrator - A tool for managing and executing development milestones',
    long_description=read_long_description(),
    long_description_content_type='text/markdown',
    url='https://github.com/yourusername/claude-orchestrator',
    py_modules=['orchestrator', 'advanced'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.8',
    install_requires=[
        # Core dependencies only - not the full requirements.txt
        'psutil>=5.9.0',
        'requests>=2.31.0',
        'colorama>=0.4.6',
        'rich>=13.0.0',
        'click>=8.1.0',
        'pyyaml>=6.0',
        'toml>=0.10.2',
        'jsonschema>=4.17.0',
        'GitPython>=3.1.32',
        'python-dotenv>=1.0.0',
        'structlog>=23.1.0',
        'watchdog>=3.0.0',
        'tqdm>=4.65.0',
        'tenacity>=8.2.0',
    ],
    extras_require={
        'dev': [
            'pytest>=7.4.0',
            'pytest-asyncio>=0.21.0',
            'pytest-cov>=4.1.0',
            'black>=23.0.0',
            'flake8>=6.0.0',
            'mypy>=1.5.0',
        ],
        'full': get_requirements(),
    },
    entry_points={
        'console_scripts': [
            'claude-orchestrator=orchestrator:main',
        ],
    },
    include_package_data=True,
    package_data={
        '': ['*.json', '*.yaml', '*.yml', '*.md'],
    },
)