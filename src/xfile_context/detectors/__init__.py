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
- FunctionDefinitionDetector: Detector for function/method definitions (Issue #140)
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

from xfile_context.detectors.base import RelationshipDetector
from xfile_context.detectors.class_inheritance_detector import ClassInheritanceDetector
from xfile_context.detectors.conditional_import_detector import ConditionalImportDetector
from xfile_context.detectors.decorator_detector import DecoratorDetector
from xfile_context.detectors.dynamic_dispatch_detector import DynamicDispatchDetector
from xfile_context.detectors.dynamic_pattern_detector import (
    DynamicPatternDetector,
    DynamicPatternType,
    DynamicPatternWarning,
    WarningSeverity,
)
from xfile_context.detectors.exec_eval_detector import ExecEvalDetector
from xfile_context.detectors.function_call_detector import FunctionCallDetector
from xfile_context.detectors.function_definition_detector import FunctionDefinitionDetector
from xfile_context.detectors.import_detector import ImportDetector
from xfile_context.detectors.metaclass_detector import MetaclassDetector
from xfile_context.detectors.monkey_patching_detector import MonkeyPatchingDetector
from xfile_context.detectors.registry import DetectorRegistry
from xfile_context.detectors.wildcard_import_detector import WildcardImportDetector

__all__ = [
    # Base classes
    "RelationshipDetector",
    "DetectorRegistry",
    # Relationship detectors
    "ImportDetector",
    "ConditionalImportDetector",
    "WildcardImportDetector",
    "FunctionCallDetector",
    "FunctionDefinitionDetector",
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
