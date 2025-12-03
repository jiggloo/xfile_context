# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Language analyzers for parsing and relationship extraction.

This package implements language-specific analyzers that parse source code
and extract cross-file relationships using detector plugins.

Components:
- PythonAnalyzer: AST-based analyzer for Python files

Architecture (DD-2: Language-agnostic file watcher):
- Layer 1: File Watcher (language-agnostic)
- Layer 2: Language Analyzers (language-specific plugins)
- Layer 3: Relationship Detectors (pattern-specific plugins, per DD-1)

See TDD Section 3.4.2 for detailed specifications.
"""

from xfile_context.analyzers.python_analyzer import PythonAnalyzer

__all__ = ["PythonAnalyzer"]
