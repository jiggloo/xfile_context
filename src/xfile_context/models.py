# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Core data models for cross-file context links.

This module defines the foundational data structures used throughout the system:
- Relationship: Represents dependencies between files
- RelationshipType: Enum-like class for relationship types
- RelationshipGraph: Bidirectional graph of file relationships
- FileMetadata: Metadata about analyzed files
- CacheEntry: Cached file snippets for working memory
- CacheStatistics: Performance metrics for the cache

All models use JSON-compatible primitives (DD-4) for serialization.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class RelationshipType:
    """Types of relationships between files.

    Design: Using class constants (not Enum) for JSON-compatible strings (DD-4).
    """

    IMPORT = "import"  # from foo import bar
    FUNCTION_CALL = "function_call"  # calling a function from another file
    CLASS_INHERITANCE = "inheritance"  # class Foo(Bar)
    WILDCARD_IMPORT = "wildcard_import"  # from foo import *
    CONDITIONAL_IMPORT = "conditional_import"  # if TYPE_CHECKING: import


@dataclass
class Relationship:
    """Represents a dependency relationship between two files.

    Design Constraint (DD-4): Uses primitives only for easy serialization.
    All fields are JSON-compatible.

    See TDD Section 3.3.1 for detailed specifications.
    """

    # Required fields
    source_file: str  # File that depends on target (absolute or relative path)
    target_file: str  # File being depended upon
    relationship_type: str  # RelationshipType enum value (stored as string)
    line_number: int  # Line in source_file where relationship exists

    # Optional fields
    source_symbol: Optional[str] = None  # Symbol in source (e.g., function name)
    target_symbol: Optional[str] = None  # Symbol in target (e.g., imported name)
    target_line: Optional[int] = None  # Line in target where symbol defined

    # Metadata (JSON-compatible dict)
    metadata: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict.

        Returns:
            Dictionary with all fields, excluding None values.
        """
        result = {
            "source_file": self.source_file,
            "target_file": self.target_file,
            "relationship_type": self.relationship_type,
            "line_number": self.line_number,
        }

        if self.source_symbol is not None:
            result["source_symbol"] = self.source_symbol
        if self.target_symbol is not None:
            result["target_symbol"] = self.target_symbol
        if self.target_line is not None:
            result["target_line"] = self.target_line
        if self.metadata is not None:
            result["metadata"] = self.metadata

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Relationship":
        """Deserialize from JSON-compatible dict.

        Args:
            data: Dictionary containing relationship fields.

        Returns:
            Relationship instance.

        Raises:
            KeyError: If required fields are missing from data dict.
        """
        return cls(
            source_file=data["source_file"],
            target_file=data["target_file"],
            relationship_type=data["relationship_type"],
            line_number=data["line_number"],
            source_symbol=data.get("source_symbol"),
            target_symbol=data.get("target_symbol"),
            target_line=data.get("target_line"),
            metadata=data.get("metadata"),
        )


@dataclass
class FileMetadata:
    """Metadata about a file in the relationship graph.

    See TDD Section 3.3.2 for detailed specifications.
    """

    filepath: str
    last_analyzed: float  # Unix timestamp
    relationship_count: int  # Number of relationships involving this file
    has_dynamic_patterns: bool  # Contains untrackable dynamic patterns (FR-42)
    dynamic_pattern_types: List[str]  # e.g., ["dynamic_dispatch", "monkey_patching"]
    is_unparseable: bool  # Syntax error prevented analysis (EC-18)
    # Note: has_circular_deps removed (cycle detection deferred to v0.1.1+, see Section 3.5.5)

    # File deletion tracking (TDD Section 3.6.4, EC-14)
    deleted: bool = False  # True if file has been deleted
    deletion_time: Optional[float] = None  # Unix timestamp of deletion

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict.

        Returns:
            Dictionary with all metadata fields.
        """
        result = {
            "filepath": self.filepath,
            "last_analyzed": self.last_analyzed,
            "relationship_count": self.relationship_count,
            "has_dynamic_patterns": self.has_dynamic_patterns,
            "dynamic_pattern_types": self.dynamic_pattern_types,
            "is_unparseable": self.is_unparseable,
            "deleted": self.deleted,
        }
        # Only include deletion_time if it's set
        if self.deletion_time is not None:
            result["deletion_time"] = self.deletion_time
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileMetadata":
        """Deserialize from JSON-compatible dict.

        Args:
            data: Dictionary containing file metadata fields.

        Returns:
            FileMetadata instance.

        Raises:
            KeyError: If required fields are missing from data dict.
        """
        return cls(
            filepath=data["filepath"],
            last_analyzed=data["last_analyzed"],
            relationship_count=data["relationship_count"],
            has_dynamic_patterns=data["has_dynamic_patterns"],
            dynamic_pattern_types=data["dynamic_pattern_types"],
            is_unparseable=data["is_unparseable"],
            deleted=data.get("deleted", False),  # Default False for backward compatibility
            deletion_time=data.get("deletion_time"),  # Default None
        )


class RelationshipGraph:
    """Bidirectional graph of file relationships.

    Maintains two indices for efficient queries:
    - dependencies: file → files it depends on
    - dependents: file → files that depend on it

    See TDD Section 3.3.2 for detailed specifications.
    """

    def __init__(self) -> None:
        """Initialize empty relationship graph."""
        # Core data (stored in RelationshipStore per DD-4)
        self._relationships: List[Relationship] = []

        # Bidirectional indices for fast lookups
        self._dependencies: Dict[str, Set[str]] = {}  # file → files it depends on
        self._dependents: Dict[str, Set[str]] = {}  # file → files that depend on it

        # Metadata
        self._file_metadata: Dict[str, FileMetadata] = {}

        # Note: _circular_groups removed (cycle detection deferred to v0.1.1+, see Section 3.5.5)

    def add_relationship(self, rel: Relationship) -> None:
        """Add relationship and update bidirectional indices.

        Error handling: At target scale (10,000 files, <500MB), dict updates
        are highly unlikely to fail. If they do fail (e.g., out of memory),
        raise error immediately - do NOT attempt rollback/recovery.

        Args:
            rel: Relationship to add.

        Raises:
            Exception: If dict update fails (extremely unlikely at target scale).
        """
        try:
            # Update forward index
            if rel.source_file not in self._dependencies:
                self._dependencies[rel.source_file] = set()
            self._dependencies[rel.source_file].add(rel.target_file)

            # Update reverse index
            if rel.target_file not in self._dependents:
                self._dependents[rel.target_file] = set()
            self._dependents[rel.target_file].add(rel.source_file)

            # Add to relationships list
            self._relationships.append(rel)
        except Exception as e:
            # If dict update fails (extremely unlikely at target scale):
            # Log error with full context and re-raise
            # Do NOT attempt rollback - indices may be inconsistent
            # System will rebuild graph from scratch on next session
            logger.error(f"Graph update failed for {rel.source_file} → {rel.target_file}: {e}")
            raise

    def get_dependencies(self, filepath: str) -> List[Relationship]:
        """Get relationships where filepath depends on others.

        Args:
            filepath: Path to query.

        Returns:
            List of relationships where filepath is the source.
        """
        return [rel for rel in self._relationships if rel.source_file == filepath]

    def get_dependents(self, filepath: str) -> List[Relationship]:
        """Get relationships where others depend on filepath.

        Args:
            filepath: Path to query.

        Returns:
            List of relationships where filepath is the target.
        """
        return [rel for rel in self._relationships if rel.target_file == filepath]

    def remove_relationships_for_file(self, filepath: str) -> None:
        """Remove all relationships involving file.

        Args:
            filepath: Path to remove relationships for.

        Raises:
            Exception: If removal operation fails (extremely unlikely at target scale).
        """
        try:
            # Remove from relationships list
            self._relationships = [
                rel
                for rel in self._relationships
                if rel.source_file != filepath and rel.target_file != filepath
            ]

            # Remove from indices
            if filepath in self._dependencies:
                del self._dependencies[filepath]
            if filepath in self._dependents:
                del self._dependents[filepath]

            # Remove from other files' indices
            for deps in self._dependencies.values():
                deps.discard(filepath)
            for deps in self._dependents.values():
                deps.discard(filepath)

            # Remove metadata
            if filepath in self._file_metadata:
                del self._file_metadata[filepath]
        except Exception as e:
            # If removal fails (extremely unlikely at target scale):
            # Log error with full context and re-raise
            # Graph may be in inconsistent state - validation will detect issues
            logger.error(f"Graph removal failed for {filepath}: {e}")
            raise

    def export_to_dict(self) -> Dict[str, Any]:
        """Export graph to JSON-compatible dict (FR-23, FR-25).

        Returns:
            Dictionary containing relationships, file metadata, and statistics.
        """
        return {
            "version": "0.1.0",
            "timestamp": time.time(),
            "relationships": [rel.to_dict() for rel in self._relationships],
            "file_metadata": {
                filepath: metadata.to_dict() for filepath, metadata in self._file_metadata.items()
            },
            "statistics": {
                "total_files": len(self._file_metadata),
                "total_relationships": len(self._relationships),
                "files_with_dynamic_patterns": sum(
                    1 for m in self._file_metadata.values() if m.has_dynamic_patterns
                ),
            },
        }

    def get_all_relationships(self) -> List[Relationship]:
        """Get all relationships in the graph.

        Returns:
            List of all relationships.
        """
        return self._relationships.copy()

    def set_file_metadata(self, filepath: str, metadata: FileMetadata) -> None:
        """Set metadata for a file.

        Args:
            filepath: Path to set metadata for.
            metadata: FileMetadata to store.
        """
        self._file_metadata[filepath] = metadata

    def get_file_metadata(self, filepath: str) -> Optional[FileMetadata]:
        """Get metadata for a file.

        Args:
            filepath: Path to get metadata for.

        Returns:
            FileMetadata if exists, None otherwise.
        """
        return self._file_metadata.get(filepath)

    def validate_graph(self) -> Tuple[bool, List[str]]:
        """Validate graph structure for consistency (EC-19).

        Checks for:
        - Orphaned references: Relationships referencing files not in metadata
        - Bidirectional consistency: If A → B exists, both A and B should be tracked
        - Duplicate relationships: Same source, target, type, and line

        Returns:
            Tuple of (is_valid, error_messages).
            - is_valid: True if graph is consistent, False if corruption detected
            - error_messages: List of validation errors found (empty if valid)
        """
        errors: List[str] = []

        # Track all files referenced in relationships
        referenced_files: Set[str] = set()
        seen_relationships: Set[Tuple[str, str, str, int]] = set()

        # Check each relationship
        for rel in self._relationships:
            # Track referenced files
            referenced_files.add(rel.source_file)
            referenced_files.add(rel.target_file)

            # Check for duplicates
            rel_key = (rel.source_file, rel.target_file, rel.relationship_type, rel.line_number)
            if rel_key in seen_relationships:
                errors.append(
                    f"Duplicate relationship: {rel.source_file} → {rel.target_file} "
                    f"({rel.relationship_type}) at line {rel.line_number}"
                )
            else:
                seen_relationships.add(rel_key)

            # Check bidirectional index consistency
            # Verify source_file is in dependencies index
            if rel.source_file not in self._dependencies:
                errors.append(
                    f"Index inconsistency: {rel.source_file} missing from dependencies index"
                )
            elif rel.target_file not in self._dependencies.get(rel.source_file, set()):
                errors.append(
                    f"Index inconsistency: {rel.source_file} → {rel.target_file} "
                    f"not in dependencies index"
                )

            # Verify target_file is in dependents index
            if rel.target_file not in self._dependents:
                errors.append(
                    f"Index inconsistency: {rel.target_file} missing from dependents index"
                )
            elif rel.source_file not in self._dependents.get(rel.target_file, set()):
                errors.append(
                    f"Index inconsistency: {rel.target_file} ← {rel.source_file} "
                    f"not in dependents index"
                )

        # Check for orphaned index entries (files in indices but no relationships)
        all_indexed_files = set(self._dependencies.keys()) | set(self._dependents.keys())
        for filepath in all_indexed_files:
            # This is only an error if there are no relationships for this file
            if filepath not in referenced_files and (
                (filepath not in self._dependencies or not self._dependencies[filepath])
                and (filepath not in self._dependents or not self._dependents[filepath])
            ):
                errors.append(
                    f"Orphaned index entry: {filepath} has empty indices but exists in graph"
                )

        is_valid = len(errors) == 0
        return is_valid, errors

    def detect_corruption(self) -> bool:
        """Detect graph corruption and log details (EC-19).

        This is a convenience method that runs validation and logs any errors found.

        Returns:
            True if corruption detected, False if graph is valid.
        """
        is_valid, errors = self.validate_graph()
        if not is_valid:
            logger.error(
                f"Graph corruption detected! Found {len(errors)} consistency errors. "
                f"Errors: {errors}"
            )
            return True
        return False

    def clear(self) -> None:
        """Clear all relationships and metadata from graph.

        Used for:
        - Graph corruption recovery (EC-19): Clear and rebuild from scratch
        - Testing: Reset graph to clean state
        """
        self._relationships.clear()
        self._dependencies.clear()
        self._dependents.clear()
        self._file_metadata.clear()


@dataclass
class CacheEntry:
    """Cached file snippet for working memory (FR-13).

    Design: Cache snippets (function signatures), not full files.

    See TDD Section 3.3.3 for detailed specifications.
    """

    # Core data
    filepath: str
    line_start: int
    line_end: int
    content: str  # The cached snippet (function signature + docstring)

    # Metadata
    last_accessed: float  # Unix timestamp of last access (for LRU eviction)
    access_count: int  # Number of times accessed
    size_bytes: int  # Size in bytes for cache size tracking

    # Context
    symbol_name: Optional[str] = None  # Function/class name if applicable

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict.

        Returns:
            Dictionary with all fields, excluding None values for optional fields.
        """
        result = {
            "filepath": self.filepath,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "content": self.content,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "size_bytes": self.size_bytes,
        }

        if self.symbol_name is not None:
            result["symbol_name"] = self.symbol_name

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        """Deserialize from JSON-compatible dict.

        Args:
            data: Dictionary containing cache entry fields.

        Returns:
            CacheEntry instance.

        Raises:
            KeyError: If required fields are missing from data dict.
        """
        return cls(
            filepath=data["filepath"],
            line_start=data["line_start"],
            line_end=data["line_end"],
            content=data["content"],
            last_accessed=data["last_accessed"],
            access_count=data["access_count"],
            size_bytes=data["size_bytes"],
            symbol_name=data.get("symbol_name"),
        )


@dataclass
class CacheStatistics:
    """Statistics for working memory cache (FR-17).

    See TDD Section 3.3.3 for detailed specifications.
    """

    hits: int
    misses: int
    staleness_refreshes: int  # Number of refreshes due to staleness detection
    evictions_lru: int  # Number of LRU evictions
    current_size_bytes: int
    peak_size_bytes: int
    current_entry_count: int
    peak_entry_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict.

        Returns:
            Dictionary with all statistics fields.
        """
        return {
            "hits": self.hits,
            "misses": self.misses,
            "staleness_refreshes": self.staleness_refreshes,
            "evictions_lru": self.evictions_lru,
            "current_size_bytes": self.current_size_bytes,
            "peak_size_bytes": self.peak_size_bytes,
            "current_entry_count": self.current_entry_count,
            "peak_entry_count": self.peak_entry_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheStatistics":
        """Deserialize from JSON-compatible dict.

        Args:
            data: Dictionary containing cache statistics fields.

        Returns:
            CacheStatistics instance.

        Raises:
            KeyError: If required fields are missing from data dict.
        """
        return cls(
            hits=data["hits"],
            misses=data["misses"],
            staleness_refreshes=data["staleness_refreshes"],
            evictions_lru=data["evictions_lru"],
            current_size_bytes=data["current_size_bytes"],
            peak_size_bytes=data["peak_size_bytes"],
            current_entry_count=data["current_entry_count"],
            peak_entry_count=data["peak_entry_count"],
        )
