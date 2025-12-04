# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Base interface for relationship detector plugins.

This module defines the abstract base class for detector plugins that extract
relationship information from AST nodes (DD-1: Modular detector plugin pattern).

Two extraction modes are supported (Issue #122):
1. Direct mode: detect() returns Relationship objects directly (original behavior)
2. Symbol mode: extract_symbols() returns SymbolDefinition/SymbolReference objects

Detectors can implement either or both modes. The PythonAnalyzer will use
symbol mode when available for the two-phase approach (AST -> FileSymbolData -> Relationships).

See TDD Section 3.4.4 for detailed specifications.
"""

import ast
from abc import ABC, abstractmethod
from typing import List, Tuple

from xfile_context.models import Relationship, SymbolDefinition, SymbolReference


class RelationshipDetector(ABC):
    """Abstract base class for relationship detector plugins.

    Detectors are independent, stateless plugins that analyze AST nodes
    to extract relationship information. Each detector focuses on a specific
    relationship pattern (e.g., imports, function calls, class inheritance).

    Design Pattern (DD-1):
    - Each detector is independent and stateless
    - Detectors are registered with priority values
    - Higher priority detectors execute first
    - New detectors can be added without modifying existing code

    Lifecycle:
    1. Detector is registered in DetectorRegistry with priority
    2. AST traversal invokes detect() for each relevant node
    3. Detector returns 0 or more Relationship objects
    4. Relationships are aggregated and stored in RelationshipGraph

    See TDD Section 3.4.4 for detailed specifications.
    """

    @abstractmethod
    def detect(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> List[Relationship]:
        """Detect relationships in an AST node.

        This method is called for each node during AST traversal. Detectors
        should check if the node matches their pattern and return corresponding
        relationships.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            List of detected relationships. Empty list if no matches found.

        Design Notes:
        - Detectors MUST be stateless (no instance variables modified)
        - Detectors MUST NOT raise exceptions (return empty list on error)
        - Detectors SHOULD log warnings for unexpected patterns
        - Detectors MUST preserve line number information for warnings
        """
        pass

    @abstractmethod
    def priority(self) -> int:
        """Return detector priority for execution order.

        Higher priority detectors execute first. This allows detectors
        that build foundational data structures (e.g., import maps) to
        run before detectors that use those structures.

        Priority Guidelines:
        - 100+: Foundation detectors (import maps, symbol tables)
        - 50-99: Core detectors (function calls, inheritance)
        - 0-49: Advanced detectors (method chains, nested attributes)
        - Negative: Cleanup/validation detectors

        Returns:
            Integer priority value. Higher values execute first.
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Return detector name for logging and debugging.

        Returns:
            Human-readable detector name (e.g., "ImportDetector").
        """
        pass

    def supports_symbol_extraction(self) -> bool:
        """Check if this detector supports symbol extraction mode (Issue #122).

        Symbol extraction mode allows detectors to return SymbolDefinition and
        SymbolReference objects instead of Relationship objects. This enables
        the two-phase analysis approach: AST -> FileSymbolData -> Relationships.

        Returns:
            True if extract_symbols() is implemented, False otherwise.
        """
        return False

    def extract_symbols(
        self,
        node: ast.AST,
        filepath: str,
        module_ast: ast.Module,
    ) -> Tuple[List[SymbolDefinition], List[SymbolReference]]:
        """Extract symbol definitions and references from an AST node (Issue #122).

        This method is an alternative to detect() that returns intermediate
        symbol data instead of fully-resolved relationships. The PythonAnalyzer
        can use this data to build FileSymbolData, then resolve relationships
        by cross-referencing definitions across files.

        Args:
            node: AST node to analyze.
            filepath: Absolute path to the file being analyzed.
            module_ast: The root AST node of the entire module (for context).

        Returns:
            Tuple of (definitions, references):
            - definitions: List of SymbolDefinition objects for symbols defined by this node
            - references: List of SymbolReference objects for references in this node

        Raises:
            NotImplementedError: If detector doesn't support symbol extraction.
                Check supports_symbol_extraction() before calling.

        Design Notes:
        - Detectors SHOULD implement this method when possible for two-phase analysis
        - References may have resolved_module=None; resolution happens in phase 2
        - Detectors MAY implement both detect() and extract_symbols()
        """
        raise NotImplementedError(
            f"{self.name()} does not support symbol extraction. "
            "Check supports_symbol_extraction() before calling."
        )
