# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Wildcard import relationship detector plugin.

This module implements the WildcardImportDetector plugin that detects wildcard
import relationships (from module import *) with module-level tracking limitations.

Supports:
- from module import * (wildcard imports)
- Module-level tracking (cannot track specific imported names)
- Optional warning via warn_on_wildcards configuration
- Context injection noting the limitation

The relationships are tracked as IMPORT type but include metadata indicating
they are wildcard imports with tracking limitations.

See TDD Section 3.5.2.6 (EC-4) for detailed specifications.
"""

import ast
import logging
from typing import List

from ..models import Relationship
from .base import RelationshipDetector
from .import_detector import ImportDetector

logger = logging.getLogger(__name__)


class WildcardImportDetector(RelationshipDetector):
    """Detector for wildcard import relationships in Python code.

    Detects wildcard import statements (from module import *) and marks them
    with wildcard metadata. Implements the detector plugin pattern from DD-1.

    Patterns Detected:
    - from module import * (wildcard imports)

    Wildcard Detection (TDD Section 3.5.2.6, EC-4):
    - Tracks at module level only
    - Cannot determine which specific names were imported
    - Optional warning via warn_on_wildcards configuration (default: false)
    - Context injection explains limitation

    Metadata includes:
    - wildcard: "true"
    - limitation: Description of tracking limitation

    Priority: 90 (Runs after ConditionalImportDetector)

    See TDD Section 3.5.2.6 for detailed specifications.
    """

    def __init__(self, warn_on_wildcards: bool = False) -> None:
        """Initialize the WildcardImportDetector.

        Args:
            warn_on_wildcards: Whether to emit warnings for wildcard imports.
                              Default is False per Code Style Philosophy (PRD 2.5).
        """
        # Use ImportDetector for module resolution logic
        self._import_detector = ImportDetector()
        self._warn_on_wildcards = warn_on_wildcards

    def detect(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> List[Relationship]:
        """Detect wildcard import relationships in an AST node.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            List of detected wildcard import relationships. Empty list if no
            wildcard imports found.
        """
        relationships: List[Relationship] = []

        # Only process ImportFrom nodes (wildcard imports use this pattern)
        if not isinstance(node, ast.ImportFrom):
            return relationships

        # Check if this is a wildcard import: from module import *
        # Wildcard is represented by a single alias with name='*'
        if not self._is_wildcard_import(node):
            return relationships

        # Use ImportDetector to detect the import and resolve module
        try:
            import_rels = self._import_detector.detect(node, filepath, module_ast)
        except Exception as e:
            # Malformed AST or resolution error, skip gracefully
            logger.debug(f"Error detecting wildcard import in {filepath}: {e}")
            return relationships

        # Enhance each relationship with wildcard metadata
        for rel in import_rels:
            # Ensure metadata dict exists (ImportDetector always creates it)
            if rel.metadata is None:
                rel.metadata = {}

            # For wildcard imports, target_symbol should be the module name, not "*"
            # This is because we're tracking the module-level dependency (TDD 3.5.2.6)
            # The module name is stored in metadata by ImportDetector
            if "module_name" in rel.metadata:
                # Use the module name as target_symbol for better clarity
                # For absolute imports: module_name is the actual module (e.g., "os")
                # For relative imports: module_name might be empty or "." notation
                module_name = rel.metadata["module_name"]
                if module_name and module_name != "." and module_name != "..":
                    rel.target_symbol = module_name
                elif not module_name and "relative_level" in rel.metadata:
                    # Keep the existing target_symbol for relative imports without module
                    # (e.g., "from . import *" - target_symbol stays as is)
                    pass

            # Add wildcard metadata (all values must be strings per metadata type)
            rel.metadata["wildcard"] = "true"
            rel.metadata["limitation"] = (
                "Cannot track which specific names are imported from this module"
            )

            # Emit warning if configured to do so
            if self._warn_on_wildcards:
                # Get module name for warning message
                module_name = node.module if node.module else "<relative>"
                logger.warning(
                    f"Wildcard import detected in {filepath}:{node.lineno}: "
                    f"from {module_name} import * - "
                    f"Cannot track specific names imported (EC-4)"
                )

            relationships.append(rel)

        return relationships

    def _is_wildcard_import(self, node: ast.ImportFrom) -> bool:
        """Check if an ImportFrom node is a wildcard import.

        Args:
            node: ImportFrom AST node to check.

        Returns:
            True if this is a wildcard import (from X import *), False otherwise.
        """
        # Wildcard imports have a single alias with name='*'
        # Example AST: ImportFrom(module='os', names=[alias(name='*', asname=None)])
        return bool(
            node.names
            and len(node.names) == 1
            and hasattr(node.names[0], "name")
            and node.names[0].name == "*"
        )

    def priority(self) -> int:
        """Return detector priority.

        WildcardImportDetector has priority 90, running after ConditionalImportDetector (95)
        and ImportDetector (100). This allows it to catch wildcard imports that weren't
        already handled by more specific detectors.

        Returns:
            Priority value (90).
        """
        return 90

    def name(self) -> str:
        """Return detector name.

        Returns:
            Detector name: "WildcardImportDetector".
        """
        return "WildcardImportDetector"
