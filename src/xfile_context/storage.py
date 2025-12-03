# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Storage abstraction for relationship graph persistence.

This module provides a storage abstraction layer for the relationship graph,
enabling future migration from in-memory to persistent storage (DD-4).

Components:
- RelationshipStore: Abstract interface for storage backends
- InMemoryStore: v0.1.0 implementation using in-memory data structures
- GraphExport: Type definition for graph export format

See TDD Section 3.4.7 for detailed specifications.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from xfile_context.models import Relationship

# Type alias for graph export format (FR-23, FR-25)
GraphExport = Dict[str, Any]


class RelationshipStore(ABC):
    """Abstract storage interface for relationship graph.

    Enables swapping storage backend without changing business logic (DD-4).

    Design:
    - v0.1.0: InMemoryStore (no persistence)
    - v0.2.0: SQLiteStore (persistent storage)
    - Migration: Change 1 line in service layer initialization

    See TDD Section 3.4.7 for detailed specifications.
    """

    @abstractmethod
    def add_relationship(self, rel: Relationship) -> None:
        """Add a relationship to storage.

        Args:
            rel: Relationship to add.

        Raises:
            Exception: If storage operation fails.
        """
        pass

    @abstractmethod
    def remove_relationship(self, rel: Relationship) -> None:
        """Remove a specific relationship from storage.

        Args:
            rel: Relationship to remove (matched by source_file, target_file,
                 relationship_type, and line_number).

        Raises:
            Exception: If storage operation fails.
        """
        pass

    @abstractmethod
    def get_relationships(self, file_path: str) -> List[Relationship]:
        """Get all relationships involving a file.

        Returns relationships where file_path is either source or target.

        Args:
            file_path: Path to query (absolute or relative).

        Returns:
            List of relationships involving file_path. Empty list if file not found.
        """
        pass

    @abstractmethod
    def get_all_relationships(self) -> List[Relationship]:
        """Get all relationships in storage.

        Returns:
            List of all relationships. Empty list if storage is empty.
        """
        pass

    @abstractmethod
    def export_graph(self, project_root: Optional[str] = None) -> GraphExport:
        """Export graph to JSON-compatible dict (FR-23, FR-25).

        Implements TDD Section 3.10.3 graph export format.

        Args:
            project_root: Project root directory for computing relative paths.
                         If None, relative paths will not be included.

        Returns:
            Dictionary containing:
            - metadata: timestamp, version, language, project_root, counts
            - files: list of file info with paths
            - relationships: List of relationship dicts
            - graph_metadata: circular imports, most connected files
        """
        pass


class InMemoryStore(RelationshipStore):
    """In-memory storage implementation for v0.1.0.

    Features:
    - Fast O(1) lookups for file-based queries
    - No persistence across sessions
    - Memory-efficient data structures

    Limitations:
    - NOT thread-safe: Designed for single-threaded use only
    - Target scale: 10K files, <500MB memory
    - No automatic cleanup of removed relationships (None markers remain until clear())

    Data Structure:
    - _relationships: List of all relationships
    - _by_file: Index mapping file_path -> relationship indices for O(1) lookup

    See TDD Section 3.4.7 for detailed specifications.
    """

    def __init__(self) -> None:
        """Initialize empty in-memory store."""
        # Core storage
        self._relationships: List[Relationship] = []

        # Index for O(1) file-based lookups
        # Maps file_path -> list of indices in _relationships
        # A file appears in index if it's source OR target of a relationship
        self._by_file: Dict[str, List[int]] = {}

    def _validate_relationship(self, rel: Relationship) -> None:
        """Validate relationship data for basic security and correctness.

        Args:
            rel: Relationship to validate.

        Raises:
            ValueError: If relationship data is invalid.
        """
        # Validate file paths are not empty
        if not rel.source_file or not rel.target_file:
            raise ValueError("File paths cannot be empty")

        # Validate no control characters (null bytes, newlines, etc.)
        # ASCII control characters (0-31) can enable injection attacks
        for path in [rel.source_file, rel.target_file]:
            if any(ord(c) < 32 for c in path):
                raise ValueError(f"File path contains invalid control characters: {repr(path)}")

        # Validate no directory traversal patterns
        # Check for "../" or paths starting with ".."
        for path in [rel.source_file, rel.target_file]:
            if "/.." in path or path.startswith(".."):
                raise ValueError(
                    f"Directory traversal not allowed: {rel.source_file} -> {rel.target_file}"
                )

        # Validate line number is positive
        if rel.line_number <= 0:
            raise ValueError(f"Line number must be positive: {rel.line_number}")

        # Validate relationship type is not empty
        if not rel.relationship_type:
            raise ValueError("Relationship type cannot be empty")

    def add_relationship(self, rel: Relationship) -> None:
        """Add a relationship to storage.

        Complexity: O(1) average case for index updates.

        Args:
            rel: Relationship to add.

        Raises:
            ValueError: If relationship data is invalid.
            Exception: If memory allocation fails (unlikely at target scale).
        """
        # Validate input
        self._validate_relationship(rel)

        # Add to main storage
        idx = len(self._relationships)
        self._relationships.append(rel)

        # Update indices for both source and target files
        if rel.source_file not in self._by_file:
            self._by_file[rel.source_file] = []
        self._by_file[rel.source_file].append(idx)

        if rel.target_file not in self._by_file:
            self._by_file[rel.target_file] = []
        # Avoid duplicate indices if source_file == target_file (self-dependency)
        if rel.source_file != rel.target_file:
            self._by_file[rel.target_file].append(idx)

    def remove_relationship(self, rel: Relationship) -> None:
        """Remove a specific relationship from storage.

        Matches by: source_file, target_file, relationship_type, line_number.

        Design Note: This is O(n) operation but called infrequently (only during
        incremental updates when file changes). For v0.1.0 target scale (10K files),
        this is acceptable.

        Args:
            rel: Relationship to remove.

        Raises:
            ValueError: If relationship data is invalid.
            Exception: If storage operation fails.
        """
        # Validate input
        self._validate_relationship(rel)

        # Find matching relationship
        for i, stored_rel in enumerate(self._relationships):
            # Skip None entries (from previous removals)
            if stored_rel is None:
                continue

            if (
                stored_rel.source_file == rel.source_file
                and stored_rel.target_file == rel.target_file
                and stored_rel.relationship_type == rel.relationship_type
                and stored_rel.line_number == rel.line_number
            ):
                # Remove from main storage
                # Note: This leaves a gap but maintains index stability
                # Gaps are acceptable for v0.1.0 (no persistence)
                self._relationships[i] = None  # type: ignore

                # Remove from file indices
                self._remove_from_index(rel.source_file, i)
                if rel.source_file != rel.target_file:
                    self._remove_from_index(rel.target_file, i)

                break

    def _remove_from_index(self, file_path: str, idx: int) -> None:
        """Remove index from file's index list.

        Args:
            file_path: File to update index for.
            idx: Index to remove.
        """
        if file_path in self._by_file:
            try:
                self._by_file[file_path].remove(idx)
                # Clean up empty index lists
                if not self._by_file[file_path]:
                    del self._by_file[file_path]
            except ValueError:
                # Index not found, which is ok (idempotent operation)
                pass

    def get_relationships(self, file_path: str) -> List[Relationship]:
        """Get all relationships involving a file.

        Complexity: O(1) for index lookup + O(k) for building result where
        k = number of relationships for this file (typically small).

        Args:
            file_path: Path to query.

        Returns:
            List of relationships involving file_path. Empty list if file not found.
        """
        if file_path not in self._by_file:
            return []

        result = []
        for idx in self._by_file[file_path]:
            rel = self._relationships[idx]
            # Skip None entries (from remove_relationship)
            if rel is not None:
                result.append(rel)

        return result

    def get_all_relationships(self) -> List[Relationship]:
        """Get all relationships in storage.

        Returns:
            List of all relationships. Excludes None entries from removals.
        """
        return [rel for rel in self._relationships if rel is not None]

    def export_graph(self, project_root: Optional[str] = None) -> GraphExport:
        """Export graph to JSON-compatible dict (FR-23, FR-25).

        Implements TDD Section 3.10.3 graph export format.
        Note: InMemoryStore has limited metadata - for full export with file
        metadata, use RelationshipGraph.export_to_dict() via the service layer.

        Args:
            project_root: Project root directory for computing relative paths.
                         If None, relative paths will not be included.

        Returns:
            Dictionary containing graph export per TDD Section 3.10.3.
        """
        import os

        all_rels = self.get_all_relationships()

        # Build metadata section
        metadata: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "0.1.0",
            "language": "python",
            "total_files": len(self._by_file),
            "total_relationships": len(all_rels),
        }
        if project_root:
            metadata["project_root"] = project_root

        # Build files section (basic info from index)
        files = []
        for filepath in self._by_file:
            file_entry: Dict[str, Any] = {
                "path": filepath,
                "relationship_count": len(self._by_file[filepath]),
                "in_import_cycle": False,  # Cycle detection deferred to v0.1.1+
            }
            if project_root:
                try:
                    file_entry["relative_path"] = os.path.relpath(filepath, project_root)
                except ValueError:
                    file_entry["relative_path"] = filepath
            files.append(file_entry)

        # Build relationships section
        relationships = [rel.to_dict() for rel in all_rels]

        # Build graph_metadata section
        # Count dependents for most connected files
        dependency_counts: Dict[str, int] = {}
        for rel in all_rels:
            if rel.target_file not in dependency_counts:
                dependency_counts[rel.target_file] = 0
            dependency_counts[rel.target_file] += 1

        sorted_files = sorted(dependency_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        graph_metadata = {
            "circular_imports": [],  # Deferred to v0.1.1+
            "most_connected_files": [
                {"file": filepath, "dependency_count": count} for filepath, count in sorted_files
            ],
        }

        return {
            "metadata": metadata,
            "files": files,
            "relationships": relationships,
            "graph_metadata": graph_metadata,
        }

    def clear(self) -> None:
        """Clear all stored relationships.

        Used for testing and rebuilding graph from scratch.
        """
        self._relationships.clear()
        self._by_file.clear()
