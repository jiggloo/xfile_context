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
- ClassInheritanceDetector: Detector for class inheritance relationships

Dynamic Pattern Detectors (Section 3.5.4, Section 3.9.1):
- DynamicPatternDetector: Base class for dynamic pattern detection
- DynamicDispatchDetector: Detector for getattr() dynamic dispatch (EC-6)
- MonkeyPatchingDetector: Detector for attribute reassignment (EC-7)
- ExecEvalDetector: Detector for exec()/eval() calls (EC-9)
- DecoratorDetector: Detector for decorator patterns (EC-8)
- MetaclassDetector: Detector for metaclass patterns (EC-10)

See TDD Section 3.4.4 for detailed specifications.
"""

from .base import RelationshipDetector
from .class_inheritance_detector import ClassInheritanceDetector
from .conditional_import_detector import ConditionalImportDetector
from .decorator_detector import DecoratorDetector
from .dynamic_dispatch_detector import DynamicDispatchDetector
from .dynamic_pattern_detector import (
    DynamicPatternDetector,
    DynamicPatternType,
    DynamicPatternWarning,
    WarningSeverity,
)
from .exec_eval_detector import ExecEvalDetector
from .function_call_detector import FunctionCallDetector
from .import_detector import ImportDetector
from .metaclass_detector import MetaclassDetector
from .monkey_patching_detector import MonkeyPatchingDetector
from .registry import DetectorRegistry
from .wildcard_import_detector import WildcardImportDetector

__all__ = [
    # Base classes
    "RelationshipDetector",
    "DetectorRegistry",
    # Relationship detectors
    "ImportDetector",
    "ConditionalImportDetector",
    "WildcardImportDetector",
    "FunctionCallDetector",
    "ClassInheritanceDetector",
    # Dynamic pattern detectors (Section 3.5.4)
    "DynamicPatternDetector",
    "DynamicPatternType",
    "DynamicPatternWarning",
    "WarningSeverity",
    "DynamicDispatchDetector",
    "MonkeyPatchingDetector",
    "ExecEvalDetector",
    "DecoratorDetector",
    "MetaclassDetector",
]
