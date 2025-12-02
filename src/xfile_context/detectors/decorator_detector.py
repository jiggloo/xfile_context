# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Decorator pattern detector.

This module implements detection of decorator patterns (EC-8, FR-36)
where decorators may modify function/class behavior.

Pattern: @decorator_name before function/class definition

Detection (TDD Section 3.5.4.5):
- AST node: FunctionDef or ClassDef with non-empty decorator_list

Handling:
- Track decorated function/class definition
- Track decorator as dependency if imported from another module
- Warning for complex decorators in source modules
- No warning for common test decorators: @pytest.mark.*, @unittest.skip, @mock.patch

Related Requirements:
- EC-8 (Decorator edge case)
- FR-36 (Decorator warning)
- FR-42 (Fail-safe: no incorrect relationships)
- T-6.5 (Warning test)
"""

import ast
import logging
from typing import FrozenSet, Optional

from .dynamic_pattern_detector import (
    DynamicPatternDetector,
    DynamicPatternType,
    DynamicPatternWarning,
    WarningSeverity,
)

logger = logging.getLogger(__name__)


class DecoratorDetector(DynamicPatternDetector):
    """Detector for decorator patterns that may modify behavior.

    Detects patterns like:
    - @decorator
    - @decorator(args)
    - @module.decorator

    Does NOT warn for common test/framework decorators:
    - @pytest.mark.*
    - @unittest.skip*
    - @mock.patch*
    - @staticmethod, @classmethod, @property (built-in)

    Priority: 25 (Advanced detector)

    See TDD Section 3.5.4.5 and Section 3.9.1 for specifications.
    """

    # Built-in decorators that don't require warnings
    BUILTIN_DECORATORS: FrozenSet[str] = frozenset(
        {
            "staticmethod",
            "classmethod",
            "property",
            "abstractmethod",
            "abstractproperty",
            "overload",
            "final",
            "dataclass",
            "contextmanager",
            "asynccontextmanager",
            "cached_property",
            "lru_cache",
            "singledispatch",
            "singledispatchmethod",
            "functools.lru_cache",
            "functools.cached_property",
            "functools.singledispatch",
            "functools.singledispatchmethod",
            "functools.wraps",
            "abc.abstractmethod",
            "abc.abstractproperty",
            "typing.overload",
            "typing.final",
            "dataclasses.dataclass",
            "contextlib.contextmanager",
            "contextlib.asynccontextmanager",
        }
    )

    # Test framework decorators that should be suppressed
    TEST_DECORATOR_PREFIXES: FrozenSet[str] = frozenset(
        {
            "pytest.mark",
            "pytest.fixture",
            "pytest.param",
            "unittest.skip",
            "unittest.skipIf",
            "unittest.skipUnless",
            "unittest.expectedFailure",
            "mock.patch",
            "unittest.mock.patch",
            "patch",  # Common import alias
        }
    )

    def _detect_pattern(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Detect decorator patterns.

        Args:
            node: AST node to analyze.
            filepath: Path to file being analyzed.
            module_ast: Root AST node of the module.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if complex decorator detected, None otherwise.
        """
        # Pattern: FunctionDef or ClassDef with non-empty decorator_list
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return None

        if not node.decorator_list:
            return None

        # Check each decorator
        for decorator in node.decorator_list:
            warning = self._check_decorator(decorator, node, filepath, is_test)
            if warning:
                return warning

        return None

    def _check_decorator(
        self,
        decorator: ast.expr,
        definition_node: ast.AST,
        filepath: str,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Check if a decorator should trigger a warning.

        Args:
            decorator: Decorator AST node.
            definition_node: The decorated function/class node.
            filepath: Path to file being analyzed.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if warning needed, None otherwise.
        """
        decorator_name = self._get_decorator_name(decorator)

        if not decorator_name:
            return None

        # Skip built-in decorators
        if decorator_name in self.BUILTIN_DECORATORS:
            return None

        # Skip test framework decorators
        if self._is_test_decorator(decorator_name):
            return None

        # Get the definition type and name
        if isinstance(definition_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            def_type = "function"
            def_name = definition_node.name
        elif isinstance(definition_node, ast.ClassDef):
            def_type = "class"
            def_name = definition_node.name
        else:
            # Shouldn't happen, but handle gracefully
            def_type = "unknown"
            def_name = "unknown"

        message = (
            f"Decorator `{decorator_name}` in {filepath}:{decorator.lineno} "
            f"may modify {def_type} behavior - tracking original definition only"
        )

        return DynamicPatternWarning(
            pattern_type=DynamicPatternType.DECORATOR,
            filepath=filepath,
            line_number=decorator.lineno,
            message=message,
            severity=WarningSeverity.INFO,
            is_test_module=is_test,
            metadata={
                "decorator_name": decorator_name,
                "definition_type": def_type,
                "definition_name": def_name,
            },
        )

    def _get_decorator_name(self, decorator: ast.expr) -> Optional[str]:
        """Get the name of a decorator.

        Args:
            decorator: Decorator AST node.

        Returns:
            Decorator name as string, or None if cannot determine.
        """
        # Simple decorator: @name
        if isinstance(decorator, ast.Name):
            return decorator.id

        # Decorator with arguments: @name(args)
        if isinstance(decorator, ast.Call):
            return self._get_decorator_name(decorator.func)

        # Attribute decorator: @module.name
        if isinstance(decorator, ast.Attribute):
            base_name = self._get_decorator_name(decorator.value)
            if base_name:
                return f"{base_name}.{decorator.attr}"
            return decorator.attr

        return None

    def _is_test_decorator(self, decorator_name: str) -> bool:
        """Check if decorator is a test framework decorator.

        Args:
            decorator_name: Full decorator name.

        Returns:
            True if test decorator, False otherwise.
        """
        # Check for exact match
        if decorator_name in self.TEST_DECORATOR_PREFIXES:
            return True

        # Check for prefix match (e.g., pytest.mark.skip)
        for prefix in self.TEST_DECORATOR_PREFIXES:
            if decorator_name.startswith(prefix + ".") or decorator_name.startswith(prefix):
                return True

        return False

    def _get_pattern_type(self) -> DynamicPatternType:
        """Return the pattern type for this detector.

        Returns:
            DynamicPatternType.DECORATOR
        """
        return DynamicPatternType.DECORATOR

    def name(self) -> str:
        """Return detector name.

        Returns:
            "DecoratorDetector"
        """
        return "DecoratorDetector"
