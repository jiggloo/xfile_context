# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Conditional import relationship detector plugin.

This module implements the ConditionalImportDetector plugin that detects import
relationships inside conditional blocks (TYPE_CHECKING, version checks) and marks
them with conditional metadata.

Supports:
- if TYPE_CHECKING: from typing import ...
- if sys.version_info >= (3, 8): import module
- Other conditional import patterns

The relationships are still tracked as IMPORT type but include metadata indicating
they are conditional and what condition they depend on.

See TDD Section 3.5.2.5 (EC-5) for detailed specifications.
"""

import ast
import logging
from typing import Dict, List, Optional, Tuple

from xfile_context.detectors.base import RelationshipDetector
from xfile_context.detectors.import_detector import ImportDetector
from xfile_context.models import Relationship, SymbolDefinition, SymbolReference

logger = logging.getLogger(__name__)


class ConditionalImportDetector(RelationshipDetector):
    """Detector for conditional import relationships in Python code.

    Detects import statements inside conditional blocks and marks them as
    conditional in metadata. Implements the detector plugin pattern from DD-1.

    Patterns Detected:
    - if TYPE_CHECKING: import/from...import statements
    - if sys.version_info >= ...: import/from...import statements
    - Other if-guarded imports

    Conditional Detection (TDD Section 3.5.2.5):
    - TYPE_CHECKING: Imports that only exist at type-checking time
    - Version conditionals: Imports that depend on Python version
    - General conditionals: Other if-guarded imports

    Metadata includes:
    - conditional: true
    - condition_type: "TYPE_CHECKING" | "version_check" | "other"
    - condition_expr: String representation of the condition

    Priority: 95 (Runs after ImportDetector but before most other detectors)

    See TDD Section 3.5.2.5 for detailed specifications.
    """

    def __init__(self) -> None:
        """Initialize the ConditionalImportDetector."""
        # Use ImportDetector for module resolution logic
        self._import_detector = ImportDetector()

    def detect(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> List[Relationship]:
        """Detect conditional import relationships in an AST node.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            List of detected conditional import relationships. Empty list if no
            conditional imports found.
        """
        relationships: List[Relationship] = []

        # Only process If nodes
        if not isinstance(node, ast.If):
            return relationships

        # Check if this is a conditional import pattern
        try:
            condition_info = self._analyze_condition(node.test)
        except (AttributeError, TypeError) as e:
            # Malformed AST node, skip gracefully
            logger.debug(f"Error analyzing condition in {filepath}: {e}")
            return relationships

        if not condition_info:
            # Not a recognized conditional pattern, skip
            return relationships

        # Process imports only in the immediate body of this If node
        # Don't use ast.walk() as it would traverse nested If blocks
        for stmt in node.body:
            # Check if this is an import statement
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                # Use ImportDetector to detect the import and resolve module
                import_rels = self._import_detector.detect(stmt, filepath, module_ast)

                # Enhance each relationship with conditional metadata
                for rel in import_rels:
                    # Ensure metadata dict exists (ImportDetector always creates it)
                    if rel.metadata is None:
                        rel.metadata = {}

                    # Add conditional metadata (all values must be strings per metadata type)
                    rel.metadata["conditional"] = "true"
                    rel.metadata["condition_type"] = condition_info["type"]
                    rel.metadata["condition_expr"] = condition_info["expr"]

                    relationships.append(rel)

        return relationships

    def _analyze_condition(self, test: ast.AST) -> Optional[Dict[str, str]]:
        """Analyze an if condition to determine if it's a recognized conditional pattern.

        Args:
            test: The test expression from an If node.

        Returns:
            Dict with condition info if recognized pattern, None otherwise.
            Dict contains:
            - type: "TYPE_CHECKING" | "version_check" | "other"
            - expr: String representation of the condition
        """
        # Pattern 1: if TYPE_CHECKING:
        # This is a Name node with id="TYPE_CHECKING"
        if isinstance(test, ast.Name) and hasattr(test, "id") and test.id == "TYPE_CHECKING":
            return {
                "type": "TYPE_CHECKING",
                "expr": "TYPE_CHECKING",
            }

        # Pattern 2: if sys.version_info >= (3, 8):
        # This is a Compare node with sys.version_info on the left
        if isinstance(test, ast.Compare) and self._is_sys_version_info(test.left):
            return {
                "type": "version_check",
                "expr": self._unparse_expr(test),
            }

        # Pattern 3: Other conditional patterns
        # For now, we only track TYPE_CHECKING and version_check patterns
        # as specified in TDD Section 3.5.2.5
        return None

    def _unparse_expr(self, node: ast.AST) -> str:
        """Convert an AST node back to source code string.

        Note: ast.unparse() is available in Python 3.9+, and this project requires 3.10+.
        The fallback code is kept for robustness.

        Args:
            node: AST node to convert.

        Returns:
            String representation of the node.
        """
        # Python 3.9+ has ast.unparse (available since we require 3.10+)
        if hasattr(ast, "unparse"):
            unparse_result: str = ast.unparse(node)
            return unparse_result

        # Fallback: use a simple heuristic for common patterns
        # For version checks, we can build a reasonable string representation
        if isinstance(node, ast.Compare):
            # Build a simple comparison string
            # This is a simplified version that handles the common case
            left = self._node_to_string(node.left)
            op_strings: List[str] = []
            for op in node.ops:
                if isinstance(op, ast.Gt):
                    op_strings.append(">")
                elif isinstance(op, ast.GtE):
                    op_strings.append(">=")
                elif isinstance(op, ast.Lt):
                    op_strings.append("<")
                elif isinstance(op, ast.LtE):
                    op_strings.append("<=")
                elif isinstance(op, ast.Eq):
                    op_strings.append("==")
                elif isinstance(op, ast.NotEq):
                    op_strings.append("!=")
                else:
                    op_strings.append("?")

            comparators = [self._node_to_string(c) for c in node.comparators]

            # Build the comparison string
            result = left
            for op_str, comp in zip(op_strings, comparators):
                result += f" {op_str} {comp}"
            return result

        return "<unknown>"

    def _node_to_string(self, node: ast.AST, depth: int = 0, max_depth: int = 20) -> str:
        """Convert an AST node to a simple string representation.

        Args:
            node: AST node to convert.
            depth: Current recursion depth (for safety limit).
            max_depth: Maximum recursion depth to prevent stack overflow.

        Returns:
            String representation of the node.
        """
        # Prevent stack overflow from deeply nested AST structures
        if depth >= max_depth:
            return "<too_deep>"

        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value_str = self._node_to_string(node.value, depth + 1, max_depth)
            return f"{value_str}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            value_str = self._node_to_string(node.value, depth + 1, max_depth)
            # For slices, just use [...] placeholder
            return f"{value_str}[...]"
        elif isinstance(node, ast.Tuple):
            elements = [self._node_to_string(e, depth + 1, max_depth) for e in node.elts]
            return f"({', '.join(elements)})"
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Num):  # Backward compatibility (deprecated in 3.8+)
            return repr(node.n)
        else:
            return "<expr>"

    def _is_sys_version_info(self, node: ast.AST) -> bool:
        """Check if a node represents sys.version_info or sys.version_info[:2].

        Args:
            node: AST node to check.

        Returns:
            True if node is sys.version_info (with or without subscript), False otherwise.
        """
        # Pattern 1: sys.version_info (Attribute node)
        # - value: Name(id='sys')
        # - attr: 'version_info'
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "version_info"
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
        ):
            return True

        # Pattern 2: sys.version_info[:2] (Subscript node)
        # - value: Attribute(value=Name(id='sys'), attr='version_info')
        # - slice: Slice or Index
        return (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "version_info"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "sys"
        )

    def priority(self) -> int:
        """Return detector priority.

        ConditionalImportDetector has priority 95, running after ImportDetector (100)
        but before most other detectors. This allows it to catch conditional imports
        before other detectors try to use them.

        Returns:
            Priority value (95).
        """
        return 95

    def name(self) -> str:
        """Return detector name.

        Returns:
            Detector name: "ConditionalImportDetector".
        """
        return "ConditionalImportDetector"

    def supports_symbol_extraction(self) -> bool:
        """Check if this detector supports symbol extraction mode.

        Returns:
            True - ConditionalImportDetector supports symbol extraction.
        """
        return True

    def extract_symbols(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> Tuple[List[SymbolDefinition], List[SymbolReference]]:
        """Extract conditional import references from an AST node (Issue #122).

        ConditionalImportDetector only produces references (conditional imports),
        not definitions.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            Tuple of ([], references) - conditional imports produce references only.
        """
        references: List[SymbolReference] = []

        # Only process If nodes
        if not isinstance(node, ast.If):
            return ([], references)

        # Check if this is a conditional import pattern
        try:
            condition_info = self._analyze_condition(node.test)
        except (AttributeError, TypeError):
            return ([], references)

        if not condition_info:
            return ([], references)

        # Process imports only in the immediate body of this If node
        for stmt in node.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                # Use ImportDetector's extract_symbols to get base references
                import_defs, import_refs = self._import_detector.extract_symbols(
                    stmt, filepath, module_ast
                )

                # Enhance each reference with conditional metadata
                for ref in import_refs:
                    # Mark as conditional and add condition info
                    ref.is_conditional = True

                    # Update metadata with conditional information
                    if ref.metadata is None:
                        ref.metadata = {}
                    ref.metadata["conditional"] = "true"
                    ref.metadata["condition_type"] = condition_info["type"]
                    ref.metadata["condition_expr"] = condition_info["expr"]

                    references.append(ref)

        return ([], references)
