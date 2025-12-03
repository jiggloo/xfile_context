# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Metaclass pattern detector.

This module implements detection of metaclass patterns (EC-10, FR-37)
where classes use custom metaclasses.

Pattern: class Foo(metaclass=CustomMeta):

Detection (TDD Section 3.5.4.6):
- AST node: ClassDef with keywords containing keyword(arg='metaclass')

Handling:
- Track class definition
- Track metaclass as dependency if imported
- Informational warning (emitted in ALL modules, not just source)

Related Requirements:
- EC-10 (Metaclass edge case)
- FR-37 (Metaclass warning)
- FR-42 (Fail-safe: no incorrect relationships)
- T-6.6 (Warning test)
"""

import ast
import logging
from typing import Optional

from xfile_context.detectors.dynamic_pattern_detector import (
    DynamicPatternDetector,
    DynamicPatternType,
    DynamicPatternWarning,
    WarningSeverity,
)

logger = logging.getLogger(__name__)


class MetaclassDetector(DynamicPatternDetector):
    """Detector for metaclass patterns.

    Detects patterns like:
    - class Foo(metaclass=CustomMeta):
    - class Foo(Base, metaclass=CustomMeta):

    Note: Metaclass warnings are emitted for ALL modules (test and source)
    because metaclasses fundamentally change class behavior.

    Priority: 25 (Advanced detector)

    See TDD Section 3.5.4.6 and Section 3.9.1 for specifications.
    """

    # Common metaclasses that don't need warnings (well-understood behavior)
    STANDARD_METACLASSES = frozenset(
        {
            "type",  # Default metaclass
            "ABCMeta",
            "abc.ABCMeta",
            "EnumMeta",
            "enum.EnumMeta",
        }
    )

    def _detect_pattern(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Detect metaclass patterns.

        Args:
            node: AST node to analyze.
            filepath: Path to file being analyzed.
            module_ast: Root AST node of the module.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if custom metaclass detected, None otherwise.
        """
        # Pattern: ClassDef with metaclass keyword
        if not isinstance(node, ast.ClassDef):
            return None

        # Look for metaclass keyword argument
        for keyword in node.keywords:
            if keyword.arg == "metaclass":
                return self._check_metaclass(keyword, node, filepath, is_test)

        return None

    def _check_metaclass(
        self,
        keyword: ast.keyword,
        class_node: ast.ClassDef,
        filepath: str,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Check if a metaclass keyword should trigger a warning.

        Args:
            keyword: The metaclass keyword AST node.
            class_node: The ClassDef node.
            filepath: Path to file being analyzed.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if warning needed, None otherwise.
        """
        metaclass_name = self._get_metaclass_name(keyword.value)

        # Skip standard/well-understood metaclasses
        if metaclass_name in self.STANDARD_METACLASSES:
            return None

        class_name = class_node.name

        message = (
            f"Metaclass detected in {filepath}:{class_node.lineno} - "
            f"class `{class_name}` uses metaclass `{metaclass_name}`, "
            f"runtime behavior may differ from static definition"
        )

        return DynamicPatternWarning(
            pattern_type=DynamicPatternType.METACLASS,
            filepath=filepath,
            line_number=class_node.lineno,
            message=message,
            severity=WarningSeverity.INFO,
            is_test_module=is_test,
            metadata={
                "class_name": class_name,
                "metaclass_name": metaclass_name,
            },
        )

    def _get_metaclass_name(self, value_node: ast.expr) -> str:
        """Get the name of the metaclass.

        Args:
            value_node: The value node of the metaclass keyword.

        Returns:
            Metaclass name as string.
        """
        # Simple name: metaclass=CustomMeta
        if isinstance(value_node, ast.Name):
            return value_node.id

        # Attribute: metaclass=module.CustomMeta
        if isinstance(value_node, ast.Attribute):
            parts = [value_node.attr]
            current = value_node.value

            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value

            if isinstance(current, ast.Name):
                parts.append(current.id)

            return ".".join(reversed(parts))

        # Other expressions (rare): just indicate unknown
        return "<unknown>"

    def _emit_warning(self, warning: DynamicPatternWarning) -> None:
        """Emit a warning to the logger.

        Override to emit metaclass warnings for ALL modules (not just source).

        Args:
            warning: The warning to emit.
        """
        # Metaclass warnings are INFO severity and emitted for all modules
        prefix = "ℹ️"
        logger.warning(f"{prefix} {warning.message}")

    def _get_pattern_type(self) -> DynamicPatternType:
        """Return the pattern type for this detector.

        Returns:
            DynamicPatternType.METACLASS
        """
        return DynamicPatternType.METACLASS

    def name(self) -> str:
        """Return detector name.

        Returns:
            "MetaclassDetector"
        """
        return "MetaclassDetector"
