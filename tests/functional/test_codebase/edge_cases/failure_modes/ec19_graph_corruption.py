# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-19: Relationship Graph Corruption

This module demonstrates patterns for handling graph corruption.
The analyzer should detect and recover from inconsistent state.

Expected behavior:
- Detect inconsistencies via validation checks
- Clear corrupted graph
- Rebuild from scratch
"""

from typing import Any

from tests.functional.test_codebase.core.models.user import User


class GraphNode:
    """Represents a node in the relationship graph."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.dependencies: set[str] = set()
        self.dependents: set[str] = set()
        self.last_updated: float = 0.0

    def add_dependency(self, other_path: str) -> None:
        """Add a dependency."""
        self.dependencies.add(other_path)

    def add_dependent(self, other_path: str) -> None:
        """Add a dependent."""
        self.dependents.add(other_path)


class GraphValidator:
    """Validates relationship graph consistency.

    Detects corruption such as:
    - Orphaned nodes (referenced but don't exist)
    - Asymmetric relationships (A depends on B but B doesn't list A as dependent)
    - Self-references
    - Cycles that shouldn't exist
    """

    def __init__(self, nodes: dict[str, GraphNode]) -> None:
        self.nodes = nodes
        self.errors: list[str] = []

    def validate(self) -> tuple[bool, list[str]]:
        """Validate the entire graph.

        Returns:
            Tuple of (is_valid, list_of_errors).
        """
        self.errors = []
        self._check_orphaned_references()
        self._check_relationship_symmetry()
        self._check_self_references()
        return (len(self.errors) == 0, self.errors)

    def _check_orphaned_references(self) -> None:
        """Check for references to non-existent nodes."""
        for path, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    self.errors.append(f"Orphaned reference: {path} depends on non-existent {dep}")
            for dep in node.dependents:
                if dep not in self.nodes:
                    self.errors.append(
                        f"Orphaned reference: {path} has non-existent dependent {dep}"
                    )

    def _check_relationship_symmetry(self) -> None:
        """Check that relationships are properly bidirectional."""
        for path, node in self.nodes.items():
            for dep in node.dependencies:
                if dep in self.nodes and path not in self.nodes[dep].dependents:
                    self.errors.append(
                        f"Asymmetric relationship: {path} depends on {dep} "
                        f"but {dep} doesn't list {path} as dependent"
                    )

    def _check_self_references(self) -> None:
        """Check for nodes that reference themselves."""
        for path, node in self.nodes.items():
            if path in node.dependencies:
                self.errors.append(f"Self-reference: {path} depends on itself")
            if path in node.dependents:
                self.errors.append(f"Self-reference: {path} lists itself as dependent")


class GraphRecovery:
    """Recovery strategies for corrupted graphs.

    When corruption is detected, the graph should be
    cleared and rebuilt from scratch.
    """

    def __init__(self) -> None:
        self.recovery_attempts: list[dict[str, Any]] = []

    def attempt_recovery(
        self, nodes: dict[str, GraphNode], errors: list[str]
    ) -> dict[str, GraphNode]:
        """Attempt to recover from graph corruption.

        Args:
            nodes: The corrupted graph nodes.
            errors: List of detected errors.

        Returns:
            A new, clean graph (empty, ready to rebuild).
        """
        recovery_info = {
            "original_node_count": len(nodes),
            "error_count": len(errors),
            "errors": errors,
            "action": "cleared_and_rebuilt",
        }
        self.recovery_attempts.append(recovery_info)

        # Clear and return empty graph for rebuilding
        return {}

    def get_recovery_history(self) -> list[dict[str, Any]]:
        """Get history of recovery attempts."""
        return self.recovery_attempts


# Example usage of models to create dependencies
def create_user_graph_node(user: User) -> GraphNode:
    """Create a graph node for user-related files.

    Uses User model to demonstrate dependencies.
    """
    node = GraphNode("core/models/user.py")
    node.add_dependency("core/models/base.py")
    node.add_dependency("core/utils/validation.py")
    return node


def validate_user(user: User) -> bool:
    """Validate a user instance.

    Creates a dependency on User model.
    """
    return bool(user.username and user.email)
