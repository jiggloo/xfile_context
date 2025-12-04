# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Base class for dynamic pattern detectors.

This module implements the base class for detectors that identify dynamic Python
patterns that cannot be statically analyzed (TDD Section 3.5.4, Section 3.9.1).

Dynamic patterns include:
- Dynamic dispatch: getattr(obj, dynamic_name)() (EC-6)
- Monkey patching: module.attr = replacement (EC-7)
- exec/eval: exec(code_string), eval(expression) (EC-9)
- Decorators: Track decorator usage (EC-8)
- Metaclasses: Detect custom metaclasses (EC-10)

Design Principles:
- FR-42 (Fail-Safe): Emit warning but do NOT track incorrectly
- DD-3: Test vs source distinction for warning suppression

Related Requirements:
- FR-33 through FR-37 (dynamic pattern warnings)
- EC-6 through EC-10 (edge cases)
- T-6.2 through T-6.6 (warning tests)
"""

import ast
import logging
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Tuple

from xfile_context.detectors.base import RelationshipDetector
from xfile_context.models import SymbolDefinition, SymbolReference
from xfile_context.pytest_config_parser import is_test_module

logger = logging.getLogger(__name__)


class DynamicPatternType(Enum):
    """Types of dynamic patterns that cannot be statically analyzed.

    Each type corresponds to an edge case (EC) from the TDD.
    """

    DYNAMIC_DISPATCH = "dynamic_dispatch"  # EC-6: getattr(obj, var)()
    MONKEY_PATCHING = "monkey_patching"  # EC-7: module.attr = replacement
    EXEC_EVAL = "exec_eval"  # EC-9: exec()/eval()
    DECORATOR = "decorator"  # EC-8: @decorator
    METACLASS = "metaclass"  # EC-10: class Foo(metaclass=...)


class WarningSeverity(Enum):
    """Severity level for dynamic pattern warnings.

    From TDD Section 3.9.1:
    - Warning: For patterns that may cause incorrect tracking
    - Info: For informational patterns (decorators, metaclasses)
    """

    WARNING = "warning"  # ⚠️ prefix
    INFO = "info"  # ℹ️ prefix


@dataclass
class DynamicPatternWarning:
    """A warning about a detected dynamic pattern.

    Attributes:
        pattern_type: Type of dynamic pattern detected
        filepath: Path to the file containing the pattern
        line_number: Line number where pattern was detected
        message: Human-readable warning message
        severity: Warning severity (warning or info)
        is_test_module: Whether pattern is in a test module
        metadata: Additional pattern-specific metadata
    """

    pattern_type: DynamicPatternType
    filepath: str
    line_number: int
    message: str
    severity: WarningSeverity
    is_test_module: bool
    metadata: Optional[dict[str, str]] = None


class DynamicPatternDetector(RelationshipDetector):
    """Base class for detectors that identify dynamic Python patterns.

    Dynamic pattern detectors do NOT create relationships (per FR-42 fail-safe).
    Instead, they:
    1. Detect patterns that cannot be statically analyzed
    2. Emit warnings for source modules (suppressed in test modules)
    3. Mark patterns in file metadata

    Subclasses must implement:
    - _detect_pattern(): Detect the specific pattern in an AST node
    - _get_pattern_type(): Return the DynamicPatternType for this detector

    Priority: 25 (Advanced detector - runs after core detectors)

    See TDD Section 3.5.4 and Section 3.9.1 for specifications.
    """

    def __init__(self, project_root: Optional[str] = None):
        """Initialize the dynamic pattern detector.

        Args:
            project_root: Project root directory for test module detection.
                          If None, uses default patterns only.
        """
        self._project_root = project_root
        self._warnings: List[DynamicPatternWarning] = []
        # Cache for test module status (per-file cache)
        self._cached_filepath: Optional[str] = None
        self._cached_is_test: bool = False

    def detect(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> List[Any]:
        """Detect dynamic patterns in an AST node.

        Dynamic pattern detectors return empty relationship lists (FR-42 fail-safe)
        but emit warnings for detected patterns.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module.

        Returns:
            Empty list (dynamic patterns do not create relationships).
        """
        # Check if this is a test module (with caching)
        if self._cached_filepath != filepath:
            self._cached_filepath = filepath
            self._cached_is_test = is_test_module(filepath, self._project_root)

        # Try to detect the pattern
        warning = self._detect_pattern(node, filepath, module_ast, self._cached_is_test)

        if warning:
            self._warnings.append(warning)
            # Emit warning to log (only for source modules unless severity is INFO)
            self._emit_warning(warning)

        # FR-42: Return empty list - do NOT add incorrect relationships
        return []

    @abstractmethod
    def _detect_pattern(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Detect a specific dynamic pattern in an AST node.

        Subclasses must implement this method to detect their specific pattern.

        Args:
            node: AST node to analyze.
            filepath: Path to file being analyzed.
            module_ast: Root AST node of the module.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if pattern detected, None otherwise.
        """
        pass

    @abstractmethod
    def _get_pattern_type(self) -> DynamicPatternType:
        """Return the pattern type this detector handles.

        Returns:
            DynamicPatternType for this detector.
        """
        pass

    def _emit_warning(self, warning: DynamicPatternWarning) -> None:
        """Emit a warning to the logger.

        Warnings are suppressed for test modules unless the severity is INFO
        and applies to all modules (like metaclasses).

        Args:
            warning: The warning to emit.
        """
        # Determine if we should emit this warning
        should_emit = False

        if warning.severity == WarningSeverity.INFO:
            # INFO severity: emit for all modules (metaclass detection)
            should_emit = True
        elif not warning.is_test_module:
            # WARNING severity: emit only for source modules
            should_emit = True

        if should_emit:
            prefix = "⚠️" if warning.severity == WarningSeverity.WARNING else "ℹ️"
            logger.warning(f"{prefix} {warning.message}")

    def get_warnings(self) -> List[DynamicPatternWarning]:
        """Get all detected warnings.

        Returns:
            List of detected DynamicPatternWarning objects.
        """
        return self._warnings.copy()

    def clear_warnings(self) -> None:
        """Clear all detected warnings.

        Call this between analyzing different files to reset state.
        """
        self._warnings.clear()

    def get_pattern_types(self) -> List[str]:
        """Get unique pattern types from detected warnings.

        Returns:
            List of pattern type strings for metadata tracking.
        """
        return list({w.pattern_type.value for w in self._warnings})

    def priority(self) -> int:
        """Return detector priority.

        Dynamic pattern detectors have low priority (25) as they run after
        core detectors like ImportDetector and FunctionCallDetector.

        Returns:
            Priority value (25).
        """
        return 25

    @abstractmethod
    def name(self) -> str:
        """Return detector name.

        Subclasses must implement this.

        Returns:
            Human-readable detector name.
        """
        pass

    def supports_symbol_extraction(self) -> bool:
        """Check if this detector supports symbol extraction mode.

        Dynamic pattern detectors support symbol extraction but return empty
        results per FR-42 (fail-safe - do not add incorrect relationships).

        Returns:
            True - DynamicPatternDetector supports symbol extraction.
        """
        return True

    def extract_symbols(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> Tuple[List[SymbolDefinition], List[SymbolReference]]:
        """Extract symbols from an AST node (Issue #122).

        Dynamic pattern detectors do NOT produce definitions or references
        per FR-42 (fail-safe). They detect patterns and emit warnings, but
        do not create relationships that could be incorrect.

        This base implementation:
        1. Detects the pattern (to emit warnings)
        2. Returns empty lists (no definitions or references)

        Subclasses may override this method to provide additional symbol
        extraction behavior if their pattern can produce valid symbols.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            Tuple of ([], []) - dynamic patterns do not produce symbols.
        """
        # Check if this is a test module (with caching)
        if self._cached_filepath != filepath:
            self._cached_filepath = filepath
            self._cached_is_test = is_test_module(filepath, self._project_root)

        # Try to detect the pattern (to emit warnings)
        warning = self._detect_pattern(node, filepath, module_ast, self._cached_is_test)

        if warning:
            self._warnings.append(warning)
            self._emit_warning(warning)

        # FR-42: Return empty lists - do NOT add incorrect relationships
        return ([], [])
