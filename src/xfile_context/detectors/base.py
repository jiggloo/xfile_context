# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Base interface for relationship detector plugins.

This module defines the abstract base class for detector plugins that extract
relationship information from AST nodes (DD-1: Modular detector plugin pattern).

See TDD Section 3.4.4 for detailed specifications.
"""

import ast
from abc import ABC, abstractmethod
from typing import List

from ..models import Relationship


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
