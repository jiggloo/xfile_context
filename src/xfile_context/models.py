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

Intermediate AST data models (Issue #122):
- SymbolType: Types of symbol definitions
- ReferenceType: Types of symbol references
- SymbolDefinition: A symbol defined in a file (function, class, etc.)
- SymbolReference: A reference to a symbol from another file
- FileSymbolData: All definitions and references for a single file

All models use JSON-compatible primitives (DD-4) for serialization.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
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


class SymbolType:
    """Types of symbols that can be defined in a file.

    Design: Using class constants (not Enum) for JSON-compatible strings (DD-4).
    """

    FUNCTION = "function"  # def foo(): or async def foo():
    CLASS = "class"  # class Foo:
    METHOD = "method"  # def foo(self): inside a class
    VARIABLE = "variable"  # module-level assignment: foo = ...
    CONSTANT = "constant"  # module-level UPPER_CASE = ...


class ReferenceType:
    """Types of references to symbols in other files.

    Design: Using class constants (not Enum) for JSON-compatible strings (DD-4).
    """

    IMPORT = "import"  # import foo or from foo import bar
    FUNCTION_CALL = "function_call"  # foo() or module.foo()
    CLASS_REFERENCE = "class_reference"  # class Foo(Bar): where Bar is imported
    ATTRIBUTE_ACCESS = "attribute_access"  # module.attribute
    DECORATOR = "decorator"  # @decorator applied to function/class
    METACLASS = "metaclass"  # class Foo(metaclass=Meta)


@dataclass
class SymbolDefinition:
    """A symbol defined in a Python file.

    Represents functions, classes, methods, and module-level assignments.
    Used by FileSymbolData to track all definitions in a file.

    Design Constraint (DD-4): Uses primitives only for easy serialization.
    """

    name: str  # Symbol name (e.g., "my_function", "MyClass")
    symbol_type: str  # SymbolType value
    line_start: int  # First line of definition
    line_end: int  # Last line of definition (inclusive)

    # Optional fields for richer information
    signature: Optional[str] = None  # Function/method signature (e.g., "def foo(a, b):")
    decorators: Optional[List[str]] = None  # List of decorator names
    bases: Optional[List[str]] = None  # For classes: base class names
    docstring: Optional[str] = None  # First line of docstring if present
    parent_class: Optional[str] = None  # For methods: containing class name

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        result: Dict[str, Any] = {
            "name": self.name,
            "symbol_type": self.symbol_type,
            "line_start": self.line_start,
            "line_end": self.line_end,
        }
        if self.signature is not None:
            result["signature"] = self.signature
        if self.decorators is not None:
            result["decorators"] = self.decorators
        if self.bases is not None:
            result["bases"] = self.bases
        if self.docstring is not None:
            result["docstring"] = self.docstring
        if self.parent_class is not None:
            result["parent_class"] = self.parent_class
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolDefinition":
        """Deserialize from JSON-compatible dict."""
        return cls(
            name=data["name"],
            symbol_type=data["symbol_type"],
            line_start=data["line_start"],
            line_end=data["line_end"],
            signature=data.get("signature"),
            decorators=data.get("decorators"),
            bases=data.get("bases"),
            docstring=data.get("docstring"),
            parent_class=data.get("parent_class"),
        )


@dataclass
class SymbolReference:
    """A reference to a symbol from another file.

    Represents imports, function calls, class references, and attribute accesses.
    Used by FileSymbolData to track all references in a file.

    Design Constraint (DD-4): Uses primitives only for easy serialization.
    """

    name: str  # Referenced symbol name (e.g., "foo", "module.bar")
    reference_type: str  # ReferenceType value
    line_number: int  # Line where reference occurs

    # Resolution information (populated during analysis)
    resolved_module: Optional[str] = None  # Resolved module path or marker
    resolved_symbol: Optional[str] = None  # Resolved symbol name in target module

    # Import-specific fields
    module_name: Optional[str] = None  # For imports: the module being imported
    is_relative: bool = False  # True for relative imports (from . import)
    relative_level: int = 0  # Number of dots (1 for ., 2 for .., etc.)
    alias: Optional[str] = None  # Import alias (import foo as bar -> alias="bar")
    is_wildcard: bool = False  # True for "from module import *"
    is_conditional: bool = False  # True if inside TYPE_CHECKING or version check

    # Call-specific fields
    is_method_call: bool = False  # True if calling a method on an object
    caller_context: Optional[str] = None  # Enclosing function/class name

    # Metadata (JSON-compatible dict for extensibility)
    metadata: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        result: Dict[str, Any] = {
            "name": self.name,
            "reference_type": self.reference_type,
            "line_number": self.line_number,
        }
        if self.resolved_module is not None:
            result["resolved_module"] = self.resolved_module
        if self.resolved_symbol is not None:
            result["resolved_symbol"] = self.resolved_symbol
        if self.module_name is not None:
            result["module_name"] = self.module_name
        if self.is_relative:
            result["is_relative"] = self.is_relative
        if self.relative_level > 0:
            result["relative_level"] = self.relative_level
        if self.alias is not None:
            result["alias"] = self.alias
        if self.is_wildcard:
            result["is_wildcard"] = self.is_wildcard
        if self.is_conditional:
            result["is_conditional"] = self.is_conditional
        if self.is_method_call:
            result["is_method_call"] = self.is_method_call
        if self.caller_context is not None:
            result["caller_context"] = self.caller_context
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolReference":
        """Deserialize from JSON-compatible dict."""
        return cls(
            name=data["name"],
            reference_type=data["reference_type"],
            line_number=data["line_number"],
            resolved_module=data.get("resolved_module"),
            resolved_symbol=data.get("resolved_symbol"),
            module_name=data.get("module_name"),
            is_relative=data.get("is_relative", False),
            relative_level=data.get("relative_level", 0),
            alias=data.get("alias"),
            is_wildcard=data.get("is_wildcard", False),
            is_conditional=data.get("is_conditional", False),
            is_method_call=data.get("is_method_call", False),
            caller_context=data.get("caller_context"),
            metadata=data.get("metadata"),
        )


@dataclass
class FileSymbolData:
    """Intermediate data model for AST-parsed file data (Issue #122).

    This model captures all definitions and references in a Python file,
    serving as an intermediate representation between AST parsing and
    relationship generation.

    Flow: Python AST -> FileSymbolData -> Relationships

    Benefits:
    - Separation of concerns: AST parsing vs relationship resolution
    - Inspectable intermediate state for debugging
    - Enables cross-file symbol resolution
    - Can be cached/stored independently of relationships

    Design Constraint (DD-4): Uses primitives only for easy serialization.
    """

    filepath: str  # Absolute path to the file
    definitions: List[SymbolDefinition]  # All symbols defined in this file
    references: List[SymbolReference]  # All references to other files/symbols

    # Parsing metadata
    parse_time: float  # Unix timestamp when file was parsed
    is_valid: bool = True  # False if file has syntax errors
    error_message: Optional[str] = None  # Syntax error message if not valid

    # Dynamic pattern tracking (for warnings)
    has_dynamic_patterns: bool = False
    dynamic_pattern_types: Optional[List[str]] = None

    def get_definition(self, name: str) -> Optional[SymbolDefinition]:
        """Look up a definition by name.

        Args:
            name: Symbol name to find.

        Returns:
            SymbolDefinition if found, None otherwise.
        """
        for defn in self.definitions:
            if defn.name == name:
                return defn
        return None

    def get_definitions_by_type(self, symbol_type: str) -> List[SymbolDefinition]:
        """Get all definitions of a specific type.

        Args:
            symbol_type: SymbolType value to filter by.

        Returns:
            List of matching definitions.
        """
        return [d for d in self.definitions if d.symbol_type == symbol_type]

    def get_references_by_type(self, reference_type: str) -> List[SymbolReference]:
        """Get all references of a specific type.

        Args:
            reference_type: ReferenceType value to filter by.

        Returns:
            List of matching references.
        """
        return [r for r in self.references if r.reference_type == reference_type]

    def get_import_references(self) -> List[SymbolReference]:
        """Get all import references.

        Returns:
            List of import references (regular, wildcard, conditional).
        """
        return [r for r in self.references if r.reference_type == ReferenceType.IMPORT]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        result: Dict[str, Any] = {
            "filepath": self.filepath,
            "definitions": [d.to_dict() for d in self.definitions],
            "references": [r.to_dict() for r in self.references],
            "parse_time": self.parse_time,
            "is_valid": self.is_valid,
        }
        if self.error_message is not None:
            result["error_message"] = self.error_message
        if self.has_dynamic_patterns:
            result["has_dynamic_patterns"] = self.has_dynamic_patterns
        if self.dynamic_pattern_types is not None:
            result["dynamic_pattern_types"] = self.dynamic_pattern_types
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileSymbolData":
        """Deserialize from JSON-compatible dict."""
        return cls(
            filepath=data["filepath"],
            definitions=[SymbolDefinition.from_dict(d) for d in data["definitions"]],
            references=[SymbolReference.from_dict(r) for r in data["references"]],
            parse_time=data["parse_time"],
            is_valid=data.get("is_valid", True),
            error_message=data.get("error_message"),
            has_dynamic_patterns=data.get("has_dynamic_patterns", False),
            dynamic_pattern_types=data.get("dynamic_pattern_types"),
        )


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

    # Pending relationships tracking (Issue #117 Option B)
    # True if file's relationships need to be restored without re-analysis
    pending_relationships: bool = False

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
        # Only include pending_relationships if True (Issue #117 Option B)
        if self.pending_relationships:
            result["pending_relationships"] = self.pending_relationships
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
            pending_relationships=data.get("pending_relationships", False),  # Issue #117 Option B
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

    def _deduplicate_relationships(self, relationships: List[Relationship]) -> List[Relationship]:
        """Deduplicate relationships based on key attributes (Issue #144).

        Two relationships are considered duplicates if they have the same:
        source_file, target_file, relationship_type, line_number, source_symbol,
        target_symbol, and target_line. The metadata field is intentionally excluded
        from the deduplication key.

        When duplicates exist, the first occurrence is preserved.

        Args:
            relationships: List of relationships to deduplicate.

        Returns:
            List of unique relationships.
        """
        seen: Dict[
            Tuple[str, str, str, int, Optional[str], Optional[str], Optional[int]], Relationship
        ] = {}
        for rel in relationships:
            key = (
                rel.source_file,
                rel.target_file,
                rel.relationship_type,
                rel.line_number,
                rel.source_symbol,
                rel.target_symbol,
                rel.target_line,
            )
            if key not in seen:
                seen[key] = rel
        return list(seen.values())

    def get_dependencies(self, filepath: str) -> List[Relationship]:
        """Get relationships where filepath depends on others.

        Deduplicates relationships to prevent duplicate entries in injected context
        (Issue #144). See _deduplicate_relationships() for deduplication logic.

        Args:
            filepath: Path to query.

        Returns:
            List of unique relationships where filepath is the source.
        """
        file_rels = [rel for rel in self._relationships if rel.source_file == filepath]
        return self._deduplicate_relationships(file_rels)

    def get_dependents(self, filepath: str) -> List[Relationship]:
        """Get relationships where others depend on filepath.

        Deduplicates relationships to prevent duplicate entries (Issue #144).
        See _deduplicate_relationships() for deduplication logic.

        Args:
            filepath: Path to query.

        Returns:
            List of unique relationships where filepath is the target.
        """
        file_rels = [rel for rel in self._relationships if rel.target_file == filepath]
        return self._deduplicate_relationships(file_rels)

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

    def export_to_dict(self, project_root: Optional[str] = None) -> Dict[str, Any]:
        """Export graph to JSON-compatible dict (FR-23, FR-25).

        Implements TDD Section 3.10.3 graph export format with:
        - metadata: timestamp, version, language, project_root, counts
        - files: list of file info with absolute and relative paths
        - relationships: all detected relationships with full metadata
        - graph_metadata: circular imports, most connected files

        Args:
            project_root: Project root directory for computing relative paths.
                         If None, relative paths will not be included.

        Returns:
            Dictionary containing full graph export per TDD Section 3.10.3.
        """
        # Build metadata section
        metadata = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "0.1.0",
            "language": "python",
            "total_files": len(self._file_metadata),
            "total_relationships": len(self._relationships),
        }
        if project_root:
            metadata["project_root"] = project_root

        # Build files section with both absolute and relative paths
        files = []
        for filepath, file_meta in self._file_metadata.items():
            file_entry: Dict[str, Any] = {
                "path": filepath,
                "last_modified": datetime.fromtimestamp(
                    file_meta.last_analyzed, tz=timezone.utc
                ).isoformat(),
                "relationship_count": file_meta.relationship_count,
                "in_import_cycle": False,  # Cycle detection deferred to v0.1.1+
            }
            # Add relative path if project_root provided
            if project_root:
                file_entry["relative_path"] = self._compute_relative_path(filepath, project_root)
            files.append(file_entry)

        # Build relationships section
        relationships = []
        for rel in self._relationships:
            rel_entry = rel.to_dict()
            # Ensure metadata structure matches TDD 3.10.3
            if rel.metadata:
                rel_entry["metadata"] = rel.metadata
            relationships.append(rel_entry)

        # Build graph_metadata section
        graph_metadata = {
            # Circular imports detection deferred to v0.1.1+ (see TDD Section 3.5.5)
            "circular_imports": [],
            "most_connected_files": self._get_most_connected_files(limit=10),
        }

        return {
            "metadata": metadata,
            "files": files,
            "relationships": relationships,
            "graph_metadata": graph_metadata,
        }

    def _compute_relative_path(self, filepath: str, project_root: str) -> str:
        """Compute relative path from project root.

        Args:
            filepath: Absolute file path.
            project_root: Project root directory.

        Returns:
            Relative path from project root, or original path if not under root.
        """
        try:
            return os.path.relpath(filepath, project_root)
        except ValueError:
            # On Windows, relpath fails for paths on different drives
            return filepath

    def _get_most_connected_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get files with highest dependency counts.

        Counts files that have the most dependents (most imported by other files).

        Args:
            limit: Maximum number of files to return.

        Returns:
            List of dicts with 'file' and 'dependency_count' keys, sorted by count.
        """
        # Count dependents for each file (how many files depend on it)
        dependency_counts: Dict[str, int] = {}
        for filepath in self._dependents:
            dependency_counts[filepath] = len(self._dependents[filepath])

        # Sort by count descending and take top N
        sorted_files = sorted(dependency_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

        return [{"file": filepath, "dependency_count": count} for filepath, count in sorted_files]

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

    # =========================================================================
    # Issue #117 Option B: Staleness Resolution Support Methods
    # =========================================================================

    def copy_dependency_graph(self) -> Dict[str, Set[str]]:
        """Create a copy of the dependency graph for staleness resolution.

        Returns a deep copy of the dependencies index, preserving the graph
        structure before any relationship removal. This copy is used to
        determine transitive dependencies when resolving stale files.

        Returns:
            Dict mapping filepath -> set of files it depends on.
        """
        return {filepath: deps.copy() for filepath, deps in self._dependencies.items()}

    def get_transitive_dependencies(
        self,
        filepath: str,
        dependency_graph: Optional[Dict[str, Set[str]]] = None,
    ) -> Set[str]:
        """Get all transitive dependencies of a file.

        Performs a breadth-first traversal of the dependency graph to find
        all files that the given file depends on, directly or transitively.

        Args:
            filepath: File to find dependencies for.
            dependency_graph: Optional graph to use (default: current graph).
                             Pass a copied graph for staleness resolution.

        Returns:
            Set of all transitive dependency file paths (not including filepath).
        """
        graph = dependency_graph if dependency_graph is not None else self._dependencies
        visited: Set[str] = set()
        queue: List[str] = [filepath]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            # Add dependencies to queue
            deps = graph.get(current, set())
            for dep in deps:
                if dep not in visited:
                    queue.append(dep)

        # Remove the starting file from results
        visited.discard(filepath)
        return visited

    def get_direct_dependents(self, filepath: str) -> Set[str]:
        """Get files that directly depend on the given file.

        Args:
            filepath: File to find dependents for.

        Returns:
            Set of files that directly import from filepath.
        """
        return self._dependents.get(filepath, set()).copy()

    def store_pending_relationships(self, filepath: str) -> List[Relationship]:
        """Store relationships for a file before removal (Issue #117 Option B).

        Extracts all relationships where filepath is the source (dependencies)
        before they are removed from the graph. These can be restored later
        without re-analyzing the file.

        Args:
            filepath: File whose outgoing relationships to store.

        Returns:
            List of relationships where filepath is the source.
        """
        return [rel for rel in self._relationships if rel.source_file == filepath]

    def restore_pending_relationships(self, relationships: List[Relationship]) -> None:
        """Restore previously stored relationships (Issue #117 Option B).

        Re-adds relationships to the graph without requiring re-analysis.
        Used when a file was marked as pending_relationships but not stale.

        Args:
            relationships: List of relationships to restore.
        """
        for rel in relationships:
            self.add_relationship(rel)

    def remove_outgoing_relationships(self, filepath: str) -> List[Relationship]:
        """Remove only outgoing relationships from a file (Issue #117 Option B).

        Unlike remove_relationships_for_file(), this only removes relationships
        where filepath is the source. Relationships where filepath is the target
        are preserved. Returns the removed relationships for potential restoration.

        Args:
            filepath: File whose outgoing relationships to remove.

        Returns:
            List of removed relationships.
        """
        # Find and remove outgoing relationships
        removed: List[Relationship] = []
        remaining: List[Relationship] = []

        for rel in self._relationships:
            if rel.source_file == filepath:
                removed.append(rel)
            else:
                remaining.append(rel)

        self._relationships = remaining

        # Update dependencies index (outgoing edges from this file)
        if filepath in self._dependencies:
            # Get the targets before clearing
            targets = self._dependencies[filepath].copy()
            # Clear the source's dependencies
            del self._dependencies[filepath]
            # Remove this file from dependents of its targets
            for target in targets:
                if target in self._dependents:
                    self._dependents[target].discard(filepath)

        return removed

    def mark_file_pending_relationships(self, filepath: str) -> None:
        """Mark a file as having pending relationships (Issue #117 Option B).

        The file's relationships have been removed from the graph but can be
        restored without re-analyzing the file (its content hasn't changed).

        Args:
            filepath: File to mark as pending.
        """
        metadata = self.get_file_metadata(filepath)
        if metadata is not None:
            metadata.pending_relationships = True

    def clear_pending_relationships(self, filepath: str) -> None:
        """Clear the pending_relationships flag for a file (Issue #117 Option B).

        Called after relationships have been restored or rebuilt.

        Args:
            filepath: File to clear pending flag for.
        """
        metadata = self.get_file_metadata(filepath)
        if metadata is not None:
            metadata.pending_relationships = False

    def get_files_with_pending_relationships(self) -> List[str]:
        """Get all files marked as having pending relationships.

        Returns:
            List of filepaths with pending_relationships=True.
        """
        return [
            filepath
            for filepath, metadata in self._file_metadata.items()
            if metadata.pending_relationships
        ]


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
