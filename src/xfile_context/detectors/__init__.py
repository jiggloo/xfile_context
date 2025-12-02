# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Detector plugins for relationship extraction from AST nodes.

This package implements the detector plugin pattern (DD-1) for modular
relationship detection in Abstract Syntax Trees.

Components:
- RelationshipDetector: Abstract base class for detector plugins
- DetectorRegistry: Priority-based registry for detector plugins
- ImportDetector: Detector for import relationships
- ConditionalImportDetector: Detector for conditional import relationships
- WildcardImportDetector: Detector for wildcard import relationships
- FunctionCallDetector: Detector for simple function call relationships

See TDD Section 3.4.4 for detailed specifications.
"""

from .base import RelationshipDetector
from .conditional_import_detector import ConditionalImportDetector
from .function_call_detector import FunctionCallDetector
from .import_detector import ImportDetector
from .registry import DetectorRegistry
from .wildcard_import_detector import WildcardImportDetector

__all__ = [
    "RelationshipDetector",
    "DetectorRegistry",
    "ImportDetector",
    "ConditionalImportDetector",
    "WildcardImportDetector",
    "FunctionCallDetector",
]
