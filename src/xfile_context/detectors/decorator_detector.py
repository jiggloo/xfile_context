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
from typing import FrozenSet, List, Optional, Tuple

from xfile_context.detectors.dynamic_pattern_detector import (
    DynamicPatternDetector,
    DynamicPatternType,
    DynamicPatternWarning,
    WarningSeverity,
)
from xfile_context.models import SymbolDefinition, SymbolReference, SymbolType
from xfile_context.pytest_config_parser import is_test_module

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

    def extract_symbols(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> Tuple[List[SymbolDefinition], List[SymbolReference]]:
        """Extract decorated function/class definitions (Issue #122).

        DecoratorDetector can produce definitions for decorated functions/classes.
        It does not produce references since the decorator relationship is complex
        and better handled by other detectors.

        The definitions include decorator information in the metadata.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            Tuple of (definitions, []) - decorated items produce definitions.
        """
        definitions: List[SymbolDefinition] = []

        # Only process function/class definitions with decorators
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return ([], [])

        if not node.decorator_list:
            return ([], [])

        # Check if this is a test module (with caching)
        if self._cached_filepath != filepath:
            self._cached_filepath = filepath
            self._cached_is_test = is_test_module(filepath, self._project_root)

        # Extract decorator names
        decorator_names: List[str] = []
        for decorator in node.decorator_list:
            dec_name = self._get_decorator_name(decorator)
            if dec_name:
                decorator_names.append(dec_name)

        # Determine symbol type and build definition
        line_end: int = node.end_lineno if node.end_lineno else node.lineno

        if isinstance(node, ast.ClassDef):
            symbol_type = SymbolType.CLASS
            signature = f"class {node.name}"

            # Get base class names
            bases = None
            if node.bases:
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        parts = [base.attr]
                        current = base.value
                        while isinstance(current, ast.Attribute):
                            parts.append(current.attr)
                            current = current.value
                        if isinstance(current, ast.Name):
                            parts.append(current.id)
                        bases.append(".".join(reversed(parts)))

            # Extract docstring if present
            docstring = None
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                full_doc = node.body[0].value.value
                docstring = full_doc.split("\n")[0].strip()

            definition = SymbolDefinition(
                name=node.name,
                symbol_type=symbol_type,
                line_start=node.lineno,
                line_end=line_end,
                signature=signature,
                decorators=decorator_names if decorator_names else None,
                bases=bases,
                docstring=docstring,
            )
        else:
            # Function or async function
            symbol_type = SymbolType.FUNCTION

            # Build signature
            args_list = []
            for arg in node.args.args:
                args_list.append(arg.arg)
            args_str = ", ".join(args_list)
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            signature = f"{prefix} {node.name}({args_str})"

            # Extract docstring if present
            docstring = None
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                full_doc = node.body[0].value.value
                docstring = full_doc.split("\n")[0].strip()

            definition = SymbolDefinition(
                name=node.name,
                symbol_type=symbol_type,
                line_start=node.lineno,
                line_end=line_end,
                signature=signature,
                decorators=decorator_names if decorator_names else None,
                docstring=docstring,
            )

        definitions.append(definition)

        # Also call parent to detect pattern and emit warnings
        for decorator in node.decorator_list:
            warning = self._check_decorator(decorator, node, filepath, self._cached_is_test)
            if warning:
                self._warnings.append(warning)
                self._emit_warning(warning)

        return (definitions, [])
