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
from typing import List, Optional, Tuple

from xfile_context.detectors.dynamic_pattern_detector import (
    DynamicPatternDetector,
    DynamicPatternType,
    DynamicPatternWarning,
    WarningSeverity,
)
from xfile_context.models import ReferenceType, SymbolDefinition, SymbolReference, SymbolType
from xfile_context.pytest_config_parser import is_test_module

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

    def extract_symbols(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> Tuple[List[SymbolDefinition], List[SymbolReference]]:
        """Extract class definitions with metaclasses and metaclass references (Issue #141).

        MetaclassDetector produces:
        - Definitions for classes with metaclasses
        - References to the metaclasses themselves

        The definition includes metaclass information in the metadata.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            Tuple of (definitions, references) - metaclass classes and their metaclass refs.
        """
        definitions: List[SymbolDefinition] = []
        references: List[SymbolReference] = []

        # Only process ClassDef nodes
        if not isinstance(node, ast.ClassDef):
            return ([], [])

        # Check for metaclass keyword
        metaclass_name = None
        metaclass_keyword = None
        for keyword in node.keywords:
            if keyword.arg == "metaclass":
                metaclass_name = self._get_metaclass_name(keyword.value)
                metaclass_keyword = keyword
                break

        if not metaclass_name:
            return ([], [])

        # Check if this is a test module (with caching)
        if self._cached_filepath != filepath:
            self._cached_filepath = filepath
            self._cached_is_test = is_test_module(filepath, self._project_root)

        # Create metaclass reference (Issue #141)
        reference = SymbolReference(
            name=metaclass_name,
            reference_type=ReferenceType.METACLASS,
            line_number=node.lineno,
            resolved_symbol=metaclass_name,
            # Note: resolved_module would require import resolution
            # We set it to None here - it can be resolved in a later phase
            resolved_module=None,
        )
        references.append(reference)

        # Build class definition
        line_end: int = node.end_lineno if node.end_lineno else node.lineno

        # Get decorator names
        decorators = None
        if node.decorator_list:
            decorators = []
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name):
                    decorators.append(dec.id)
                elif isinstance(dec, ast.Attribute):
                    parts = [dec.attr]
                    current = dec.value
                    while isinstance(current, ast.Attribute):
                        parts.append(current.attr)
                        current = current.value
                    if isinstance(current, ast.Name):
                        parts.append(current.id)
                    decorators.append(".".join(reversed(parts)))
                elif isinstance(dec, ast.Call):
                    if isinstance(dec.func, ast.Name):
                        decorators.append(dec.func.id)
                    elif isinstance(dec.func, ast.Attribute):
                        parts = [dec.func.attr]
                        current = dec.func.value
                        while isinstance(current, ast.Attribute):
                            parts.append(current.attr)
                            current = current.value
                        if isinstance(current, ast.Name):
                            parts.append(current.id)
                        decorators.append(".".join(reversed(parts)))

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
            symbol_type=SymbolType.CLASS,
            line_start=node.lineno,
            line_end=line_end,
            signature=f"class {node.name}(metaclass={metaclass_name})",
            decorators=decorators,
            bases=bases,
            docstring=docstring,
        )
        definitions.append(definition)

        # Also detect pattern and emit warnings for non-standard metaclasses
        if metaclass_keyword is not None:
            warning = self._check_metaclass(
                metaclass_keyword,
                node,
                filepath,
                self._cached_is_test,
            )
            if warning:
                self._warnings.append(warning)
                self._emit_warning(warning)

        return (definitions, references)
