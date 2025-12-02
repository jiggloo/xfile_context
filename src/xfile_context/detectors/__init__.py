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

See TDD Section 3.4.4 for detailed specifications.
"""

from .base import RelationshipDetector
from .conditional_import_detector import ConditionalImportDetector
from .import_detector import ImportDetector
from .registry import DetectorRegistry

__all__ = [
    "RelationshipDetector",
    "DetectorRegistry",
    "ImportDetector",
    "ConditionalImportDetector",
]
