# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Monkey patching pattern detector.

This module implements detection of monkey patching patterns (EC-7, FR-34)
that cannot be statically analyzed.

Pattern: module.attr = replacement (runtime reassignment)

Detection (TDD Section 3.5.4.3):
- AST node: Assign where target is Attribute (e.g., module.function)
- Distinguish from initial definition vs reassignment

Handling:
- Warning in source modules only (suppressed in test modules for mocking)
- Track original definition only, not runtime replacement
- Mark in metadata: "monkey_patching"

Related Requirements:
- EC-7 (Monkey patching edge case)
- FR-34 (Monkey patching warning)
- FR-42 (Fail-safe: no incorrect relationships)
- T-6.3 (Warning test)
"""

import ast
import logging
from typing import Optional, Set

from .dynamic_pattern_detector import (
    DynamicPatternDetector,
    DynamicPatternType,
    DynamicPatternWarning,
    WarningSeverity,
)

logger = logging.getLogger(__name__)


class MonkeyPatchingDetector(DynamicPatternDetector):
    """Detector for monkey patching patterns (attribute reassignment).

    Detects patterns like:
    - module.function = my_replacement
    - obj.method = lambda: None

    Does NOT warn for:
    - self.attr = value (instance attribute assignment)
    - cls.attr = value in class body (class attribute definition)

    Priority: 25 (Advanced detector)

    See TDD Section 3.5.4.3 and Section 3.9.1 for specifications.
    """

    def __init__(self, project_root: Optional[str] = None):
        """Initialize the monkey patching detector.

        Args:
            project_root: Project root for test module detection.
        """
        super().__init__(project_root)
        # Cache of imported module names for the current file
        self._imported_modules: Set[str] = set()
        self._imports_built = False

    def _detect_pattern(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Detect monkey patching patterns.

        Args:
            node: AST node to analyze.
            filepath: Path to file being analyzed.
            module_ast: Root AST node of the module.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if monkey patching detected, None otherwise.
        """
        # Build imports cache if needed (once per file)
        if not self._imports_built or self._cached_filepath != filepath:
            self._build_imports_cache(module_ast)
            self._imports_built = True

        # Pattern: Assign where target is Attribute
        if not isinstance(node, ast.Assign):
            return None

        for target in node.targets:
            if isinstance(target, ast.Attribute):
                warning = self._check_attribute_assignment(
                    target, node, filepath, module_ast, is_test
                )
                if warning:
                    return warning

        return None

    def _build_imports_cache(self, module_ast: ast.Module) -> None:
        """Build cache of imported module names.

        Args:
            module_ast: Root AST node of the module.
        """
        self._imported_modules.clear()

        for node in ast.walk(module_ast):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Use alias if provided, otherwise use module name
                    name = alias.asname if alias.asname else alias.name
                    self._imported_modules.add(name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        name = alias.asname if alias.asname else alias.name
                        self._imported_modules.add(name)

    def _check_attribute_assignment(
        self,
        target: ast.Attribute,
        assign_node: ast.Assign,
        filepath: str,
        module_ast: ast.Module,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Check if an attribute assignment is monkey patching.

        Args:
            target: The Attribute node being assigned to.
            assign_node: The Assign node.
            filepath: Path to file being analyzed.
            module_ast: Root AST node of the module.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if monkey patching, None otherwise.
        """
        # Skip self.attr and cls.attr assignments (common instance/class attributes)
        if isinstance(target.value, ast.Name):
            obj_name = target.value.id
            if obj_name in ("self", "cls"):
                return None

            # Check if assigning to an imported module
            if obj_name in self._imported_modules:
                attr_name = target.attr

                message = (
                    f"Monkey patching detected in {filepath}:{assign_node.lineno} - "
                    f"`{obj_name}.{attr_name}` reassigned, relationship tracking may be inaccurate"
                )

                return DynamicPatternWarning(
                    pattern_type=DynamicPatternType.MONKEY_PATCHING,
                    filepath=filepath,
                    line_number=assign_node.lineno,
                    message=message,
                    severity=WarningSeverity.WARNING,
                    is_test_module=is_test,
                    metadata={
                        "module_name": obj_name,
                        "attribute_name": attr_name,
                    },
                )

        # Check for nested attribute assignments (e.g., module.submodule.attr = ...)
        elif isinstance(target.value, ast.Attribute):
            # Get the root object name
            root_obj = self._get_root_name(target.value)
            if root_obj and root_obj in self._imported_modules:
                # Build full attribute path
                attr_path = self._get_attr_path(target)

                message = (
                    f"Monkey patching detected in {filepath}:{assign_node.lineno} - "
                    f"`{attr_path}` reassigned, relationship tracking may be inaccurate"
                )

                return DynamicPatternWarning(
                    pattern_type=DynamicPatternType.MONKEY_PATCHING,
                    filepath=filepath,
                    line_number=assign_node.lineno,
                    message=message,
                    severity=WarningSeverity.WARNING,
                    is_test_module=is_test,
                    metadata={
                        "attribute_path": attr_path,
                    },
                )

        return None

    def _get_root_name(self, node: ast.AST) -> Optional[str]:
        """Get the root Name from a chain of Attribute nodes.

        Args:
            node: AST node (Attribute or Name).

        Returns:
            Root name string, or None if not found.
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_root_name(node.value)
        return None

    def _get_attr_path(self, node: ast.Attribute) -> str:
        """Get the full attribute path as a string.

        Args:
            node: Attribute AST node.

        Returns:
            Dotted attribute path string.
        """
        parts = [node.attr]
        current = node.value

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)

        return ".".join(reversed(parts))

    def _get_pattern_type(self) -> DynamicPatternType:
        """Return the pattern type for this detector.

        Returns:
            DynamicPatternType.MONKEY_PATCHING
        """
        return DynamicPatternType.MONKEY_PATCHING

    def name(self) -> str:
        """Return detector name.

        Returns:
            "MonkeyPatchingDetector"
        """
        return "MonkeyPatchingDetector"
