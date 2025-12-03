# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Dynamic dispatch pattern detector.

This module implements detection of dynamic dispatch patterns (EC-6, FR-33)
that cannot be statically analyzed.

Pattern: getattr(obj, dynamic_name)()

Detection (TDD Section 3.5.4.2):
- AST node: Call where func is Call to getattr
- Check if second argument to getattr is variable vs constant

Handling:
- If variable: Cannot determine which function will be called
- Warning in source modules only (suppressed in test modules)
- Mark in metadata: "dynamic_dispatch"

Related Requirements:
- EC-6 (Dynamic dispatch edge case)
- FR-33 (Dynamic dispatch warning)
- FR-42 (Fail-safe: no incorrect relationships)
- T-6.2 (Warning test)
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


class DynamicDispatchDetector(DynamicPatternDetector):
    """Detector for dynamic dispatch patterns using getattr().

    Detects patterns like:
    - getattr(obj, variable_name)()  # Dynamic - warned
    - getattr(obj, "literal")()       # Static - not warned

    Priority: 25 (Advanced detector)

    See TDD Section 3.5.4.2 and Section 3.9.1 for specifications.
    """

    def _detect_pattern(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Detect getattr() dynamic dispatch patterns.

        Args:
            node: AST node to analyze.
            filepath: Path to file being analyzed.
            module_ast: Root AST node of the module.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if dynamic getattr detected, None otherwise.
        """
        # Pattern: Call where func is a Call to getattr
        # e.g., getattr(obj, name)() - the outer call invokes the result of getattr
        if not isinstance(node, ast.Call):
            return None

        # Check if this is a call to the result of getattr
        # The func can be the getattr call itself, or getattr without a subsequent call
        func = node.func

        # Case 1: getattr(obj, name)() - calling the result of getattr
        if isinstance(func, ast.Call):
            inner_call = func
            if self._is_getattr_call(inner_call):
                return self._check_getattr_args(inner_call, filepath, is_test)

        # Case 2: Direct getattr call (may or may not be invoked)
        # We also want to detect getattr with variable second arg even without call
        if self._is_getattr_call(node):
            return self._check_getattr_args(node, filepath, is_test)

        return None

    def _is_getattr_call(self, node: ast.Call) -> bool:
        """Check if a Call node is a call to getattr.

        Args:
            node: Call AST node.

        Returns:
            True if this is a call to getattr, False otherwise.
        """
        if isinstance(node.func, ast.Name):
            return node.func.id == "getattr"
        return False

    def _check_getattr_args(
        self,
        node: ast.Call,
        filepath: str,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Check if getattr call has dynamic (variable) second argument.

        Args:
            node: Call node for getattr().
            filepath: Path to file being analyzed.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if second arg is variable, None if constant.
        """
        # getattr requires at least 2 arguments: getattr(obj, name)
        if len(node.args) < 2:
            return None

        second_arg = node.args[1]

        # If second argument is a string constant, we can statically analyze it
        if isinstance(second_arg, ast.Constant) and isinstance(second_arg.value, str):
            # Static attribute name - no warning needed
            return None

        # If second argument is a variable (Name) or other expression, it's dynamic
        attr_name = second_arg.id if isinstance(second_arg, ast.Name) else "<expression>"

        # Get the object being accessed
        first_arg = node.args[0]
        obj_name = first_arg.id if isinstance(first_arg, ast.Name) else "<object>"

        message = (
            f"Dynamic dispatch detected in {filepath}:{node.lineno} - "
            f"relationship tracking unavailable for `getattr({obj_name}, '{attr_name}')`"
        )

        return DynamicPatternWarning(
            pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
            filepath=filepath,
            line_number=node.lineno,
            message=message,
            severity=WarningSeverity.WARNING,
            is_test_module=is_test,
            metadata={
                "object_name": obj_name,
                "attribute_variable": attr_name,
            },
        )

    def _get_pattern_type(self) -> DynamicPatternType:
        """Return the pattern type for this detector.

        Returns:
            DynamicPatternType.DYNAMIC_DISPATCH
        """
        return DynamicPatternType.DYNAMIC_DISPATCH

    def name(self) -> str:
        """Return detector name.

        Returns:
            "DynamicDispatchDetector"
        """
        return "DynamicDispatchDetector"
