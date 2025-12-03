# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""exec/eval pattern detector.

This module implements detection of exec() and eval() patterns (EC-9, FR-35)
that cannot be statically analyzed.

Pattern: exec(code_string), eval(expression_string)

Detection (TDD Section 3.5.4.4):
- AST node: Call with func = Name(id='exec') or Name(id='eval')

Handling:
- Warning in source modules only (suppressed in test modules)
- Mark file in metadata: "contains_dynamic_execution": true
- Mark in metadata: "exec_eval"

Related Requirements:
- EC-9 (exec/eval edge case)
- FR-35 (exec/eval warning)
- FR-42 (Fail-safe: no incorrect relationships)
- T-6.4 (Warning test)
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


class ExecEvalDetector(DynamicPatternDetector):
    """Detector for exec() and eval() dynamic code execution patterns.

    Detects patterns like:
    - exec(code_string)
    - exec(code_string, globals_dict)
    - eval(expression)
    - eval(expression, globals_dict, locals_dict)

    Priority: 25 (Advanced detector)

    See TDD Section 3.5.4.4 and Section 3.9.1 for specifications.
    """

    # Functions that execute code dynamically
    DYNAMIC_EXEC_FUNCTIONS = frozenset({"exec", "eval"})

    def _detect_pattern(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
        is_test: bool,
    ) -> Optional[DynamicPatternWarning]:
        """Detect exec() and eval() calls.

        Args:
            node: AST node to analyze.
            filepath: Path to file being analyzed.
            module_ast: Root AST node of the module.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning if exec/eval detected, None otherwise.
        """
        # Pattern: Call with func = Name(id='exec' or 'eval')
        if not isinstance(node, ast.Call):
            return None

        # Check for direct call to exec or eval
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in self.DYNAMIC_EXEC_FUNCTIONS:
                return self._create_warning(node, func_name, filepath, is_test)

        return None

    def _create_warning(
        self,
        node: ast.Call,
        func_name: str,
        filepath: str,
        is_test: bool,
    ) -> DynamicPatternWarning:
        """Create a warning for exec/eval usage.

        Args:
            node: The Call AST node.
            func_name: Name of the function ('exec' or 'eval').
            filepath: Path to file being analyzed.
            is_test: Whether this is a test module.

        Returns:
            DynamicPatternWarning for the detected pattern.
        """
        message = (
            f"Dynamic code execution detected in {filepath}:{node.lineno} - "
            f"`{func_name}()` prevents static analysis, relationships may be incomplete"
        )

        return DynamicPatternWarning(
            pattern_type=DynamicPatternType.EXEC_EVAL,
            filepath=filepath,
            line_number=node.lineno,
            message=message,
            severity=WarningSeverity.WARNING,
            is_test_module=is_test,
            metadata={
                "function_name": func_name,
                "contains_dynamic_execution": "true",
            },
        )

    def _get_pattern_type(self) -> DynamicPatternType:
        """Return the pattern type for this detector.

        Returns:
            DynamicPatternType.EXEC_EVAL
        """
        return DynamicPatternType.EXEC_EVAL

    def name(self) -> str:
        """Return detector name.

        Returns:
            "ExecEvalDetector"
        """
        return "ExecEvalDetector"
