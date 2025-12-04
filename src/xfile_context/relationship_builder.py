# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Relationship builder for FileSymbolData (Issue #122).

This module implements the RelationshipBuilder that converts FileSymbolData
into Relationships. It takes symbol data from multiple files and resolves
cross-file references by matching references to definitions.

Flow: FileSymbolData (multiple files) -> RelationshipBuilder -> Relationships

The builder supports:
- Import references -> Import relationships
- Function call references -> Function call relationships
- Class inheritance references -> Inheritance relationships
- Cross-file symbol resolution using definition lookups

See Issue #122 for design discussion.
"""

import logging
from typing import Dict, List, Optional, Tuple

from xfile_context.models import (
    FileSymbolData,
    ReferenceType,
    Relationship,
    RelationshipType,
    SymbolDefinition,
    SymbolReference,
)

logger = logging.getLogger(__name__)


class RelationshipBuilder:
    """Builds Relationships from FileSymbolData.

    This component implements phase 2 of the two-phase analysis approach:
    Phase 1: AST -> FileSymbolData (done by detectors)
    Phase 2: FileSymbolData -> Relationships (done by this builder)

    The builder:
    1. Stores FileSymbolData for multiple files
    2. Resolves references by looking up definitions in other files
    3. Creates Relationships with resolved target information

    Usage:
        builder = RelationshipBuilder()
        builder.add_file_data(file1_data)
        builder.add_file_data(file2_data)
        relationships = builder.build_relationships()
    """

    def __init__(self) -> None:
        """Initialize the relationship builder."""
        # Map filepath -> FileSymbolData for all analyzed files
        self._file_data: Dict[str, FileSymbolData] = {}

        # Index: symbol_name -> list of (filepath, SymbolDefinition)
        # Used for fast definition lookups
        self._definition_index: Dict[str, List[Tuple[str, SymbolDefinition]]] = {}

    def add_file_data(self, data: FileSymbolData) -> None:
        """Add FileSymbolData for a file.

        This stores the data and indexes definitions for fast lookups.

        Args:
            data: FileSymbolData for a single file.
        """
        self._file_data[data.filepath] = data

        # Index all definitions from this file
        for defn in data.definitions:
            if defn.name not in self._definition_index:
                self._definition_index[defn.name] = []
            self._definition_index[defn.name].append((data.filepath, defn))

    def remove_file_data(self, filepath: str) -> None:
        """Remove FileSymbolData for a file.

        Args:
            filepath: Path to file to remove.
        """
        if filepath not in self._file_data:
            return

        data = self._file_data.pop(filepath)

        # Remove definitions from index
        for defn in data.definitions:
            if defn.name in self._definition_index:
                self._definition_index[defn.name] = [
                    (fp, d) for fp, d in self._definition_index[defn.name] if fp != filepath
                ]
                # Clean up empty entries
                if not self._definition_index[defn.name]:
                    del self._definition_index[defn.name]

    def get_file_data(self, filepath: str) -> Optional[FileSymbolData]:
        """Get FileSymbolData for a file.

        Args:
            filepath: Path to file to query.

        Returns:
            FileSymbolData if exists, None otherwise.
        """
        return self._file_data.get(filepath)

    def clear(self) -> None:
        """Clear all stored file data."""
        self._file_data.clear()
        self._definition_index.clear()

    def build_relationships(self) -> List[Relationship]:
        """Build all relationships from stored FileSymbolData.

        This iterates through all files and converts their references
        into relationships by resolving definitions.

        Returns:
            List of all relationships across all files.
        """
        all_relationships: List[Relationship] = []

        for filepath in self._file_data:
            relationships = self.build_relationships_for_file(filepath)
            all_relationships.extend(relationships)

        return all_relationships

    def build_relationships_for_file(self, filepath: str) -> List[Relationship]:
        """Build relationships for a single file.

        Args:
            filepath: Path to file to build relationships for.

        Returns:
            List of relationships where this file is the source.
        """
        data = self._file_data.get(filepath)
        if not data:
            return []

        relationships: List[Relationship] = []

        for ref in data.references:
            rel = self._reference_to_relationship(filepath, ref)
            if rel:
                relationships.append(rel)

        return relationships

    def _reference_to_relationship(
        self, source_filepath: str, ref: SymbolReference
    ) -> Optional[Relationship]:
        """Convert a SymbolReference into a Relationship.

        Args:
            source_filepath: Path to file containing the reference.
            ref: SymbolReference to convert.

        Returns:
            Relationship if conversion successful, None otherwise.
        """
        # Determine relationship type from reference type
        rel_type = self._get_relationship_type(ref.reference_type)

        # Get target file (resolved during detection or lookup now)
        target_file = ref.resolved_module or self._resolve_reference(ref)

        # Try to get target line number by looking up definition
        target_line = self._get_target_line(ref, target_file)

        # Build metadata from reference metadata
        metadata = dict(ref.metadata) if ref.metadata else {}

        return Relationship(
            source_file=source_filepath,
            target_file=target_file,
            relationship_type=rel_type,
            line_number=ref.line_number,
            source_symbol=ref.caller_context,
            target_symbol=ref.resolved_symbol or ref.name,
            target_line=target_line,
            metadata=metadata,
        )

    def _get_relationship_type(self, ref_type: str) -> str:
        """Map ReferenceType to RelationshipType.

        Args:
            ref_type: ReferenceType value.

        Returns:
            Corresponding RelationshipType value.
        """
        mapping: Dict[str, str] = {
            ReferenceType.IMPORT: RelationshipType.IMPORT,
            ReferenceType.FUNCTION_CALL: RelationshipType.FUNCTION_CALL,
            ReferenceType.CLASS_REFERENCE: RelationshipType.CLASS_INHERITANCE,
            # Attribute access treated as function call
            ReferenceType.ATTRIBUTE_ACCESS: RelationshipType.FUNCTION_CALL,
        }
        return mapping.get(ref_type, RelationshipType.IMPORT)

    def _resolve_reference(self, ref: SymbolReference) -> str:
        """Resolve a reference to a target file.

        Used when resolved_module wasn't set during detection.

        Args:
            ref: SymbolReference to resolve.

        Returns:
            Target file path or special marker.
        """
        # If already resolved, return it
        if ref.resolved_module:
            return ref.resolved_module

        # Look up the symbol in our definition index
        symbol_name = ref.resolved_symbol or ref.name.split(".")[-1]

        if symbol_name in self._definition_index:
            definitions = self._definition_index[symbol_name]
            if definitions:
                # Return the first matching definition's file
                # TODO: Better disambiguation for multiple definitions
                return definitions[0][0]

        return f"<unresolved:{ref.name}>"

    def _get_target_line(self, ref: SymbolReference, target_file: str) -> Optional[int]:
        """Get the line number where the target symbol is defined.

        Args:
            ref: SymbolReference being resolved.
            target_file: Target file path.

        Returns:
            Line number if found, None otherwise.
        """
        # Skip special markers (stdlib, third-party, etc.)
        if target_file.startswith("<") and target_file.endswith(">"):
            return None

        # Look up the file's data
        target_data = self._file_data.get(target_file)
        if not target_data:
            return None

        # Look up the definition
        symbol_name = ref.resolved_symbol or ref.name.split(".")[-1]
        defn = target_data.get_definition(symbol_name)

        return defn.line_start if defn else None

    def lookup_definition(
        self, symbol_name: str, target_file: Optional[str] = None
    ) -> Optional[SymbolDefinition]:
        """Look up a symbol definition.

        Args:
            symbol_name: Name of symbol to find.
            target_file: Optional file to search in. If None, searches all files.

        Returns:
            SymbolDefinition if found, None otherwise.
        """
        if target_file:
            # Search in specific file
            data = self._file_data.get(target_file)
            if data:
                return data.get_definition(symbol_name)
            return None

        # Search in index
        if symbol_name in self._definition_index:
            definitions = self._definition_index[symbol_name]
            if definitions:
                return definitions[0][1]  # Return first definition

        return None

    def get_all_definitions_for_symbol(
        self, symbol_name: str
    ) -> List[Tuple[str, SymbolDefinition]]:
        """Get all definitions for a symbol name across all files.

        Args:
            symbol_name: Name of symbol to find.

        Returns:
            List of (filepath, SymbolDefinition) tuples.
        """
        return self._definition_index.get(symbol_name, [])
