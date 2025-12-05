# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for core data models.

This test module validates:
- Relationship and RelationshipType (TDD 3.3.1)
- RelationshipGraph and FileMetadata (TDD 3.3.2)
- CacheEntry and CacheStatistics (TDD 3.3.3)

Success criteria from Issue #8:
- All dataclasses instantiate correctly
- Can serialize to/from dict (for future JSON export)
- JSON-compatible primitives used (DD-4 requirement)
"""


from xfile_context.models import (
    CacheEntry,
    CacheStatistics,
    FileMetadata,
    Relationship,
    RelationshipGraph,
    RelationshipType,
)


class TestRelationshipType:
    """Tests for RelationshipType class constants."""

    def test_relationship_type_constants(self):
        """Test that all relationship types are defined with correct values."""
        assert RelationshipType.IMPORT == "import"
        assert RelationshipType.FUNCTION_CALL == "function_call"
        assert RelationshipType.CLASS_INHERITANCE == "inheritance"
        assert RelationshipType.WILDCARD_IMPORT == "wildcard_import"
        assert RelationshipType.CONDITIONAL_IMPORT == "conditional_import"


class TestRelationship:
    """Tests for Relationship dataclass."""

    def test_relationship_instantiation_minimal(self):
        """Test creating a relationship with only required fields."""
        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        assert rel.source_file == "src/bot.py"
        assert rel.target_file == "src/retry.py"
        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.line_number == 5
        assert rel.source_symbol is None
        assert rel.target_symbol is None
        assert rel.target_line is None
        assert rel.metadata is None

    def test_relationship_instantiation_full(self):
        """Test creating a relationship with all fields."""
        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
            source_symbol="retry_with_backoff",
            target_symbol="retry_with_backoff",
            target_line=120,
            metadata={"note": "test"},
        )

        assert rel.source_file == "src/bot.py"
        assert rel.target_file == "src/retry.py"
        assert rel.relationship_type == RelationshipType.IMPORT
        assert rel.line_number == 5
        assert rel.source_symbol == "retry_with_backoff"
        assert rel.target_symbol == "retry_with_backoff"
        assert rel.target_line == 120
        assert rel.metadata == {"note": "test"}

    def test_relationship_to_dict_minimal(self):
        """Test serialization of relationship with minimal fields."""
        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        data = rel.to_dict()

        assert data == {
            "source_file": "src/bot.py",
            "target_file": "src/retry.py",
            "relationship_type": "import",
            "line_number": 5,
        }
        # Verify JSON-compatible primitives (DD-4)
        assert isinstance(data["source_file"], str)
        assert isinstance(data["target_file"], str)
        assert isinstance(data["relationship_type"], str)
        assert isinstance(data["line_number"], int)

    def test_relationship_to_dict_full(self):
        """Test serialization of relationship with all fields."""
        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=46,
            source_symbol="handle_request",
            target_symbol="retry_with_backoff",
            target_line=120,
            metadata={"context": "error_handling"},
        )

        data = rel.to_dict()

        assert data["source_file"] == "src/bot.py"
        assert data["target_file"] == "src/retry.py"
        assert data["relationship_type"] == "function_call"
        assert data["line_number"] == 46
        assert data["source_symbol"] == "handle_request"
        assert data["target_symbol"] == "retry_with_backoff"
        assert data["target_line"] == 120
        assert data["metadata"] == {"context": "error_handling"}

    def test_relationship_from_dict_minimal(self):
        """Test deserialization of relationship with minimal fields."""
        data = {
            "source_file": "src/bot.py",
            "target_file": "src/retry.py",
            "relationship_type": "import",
            "line_number": 5,
        }

        rel = Relationship.from_dict(data)

        assert rel.source_file == "src/bot.py"
        assert rel.target_file == "src/retry.py"
        assert rel.relationship_type == "import"
        assert rel.line_number == 5
        assert rel.source_symbol is None
        assert rel.target_symbol is None
        assert rel.target_line is None
        assert rel.metadata is None

    def test_relationship_from_dict_full(self):
        """Test deserialization of relationship with all fields."""
        data = {
            "source_file": "src/bot.py",
            "target_file": "src/retry.py",
            "relationship_type": "function_call",
            "line_number": 46,
            "source_symbol": "handle_request",
            "target_symbol": "retry_with_backoff",
            "target_line": 120,
            "metadata": {"context": "error_handling"},
        }

        rel = Relationship.from_dict(data)

        assert rel.source_file == "src/bot.py"
        assert rel.target_file == "src/retry.py"
        assert rel.relationship_type == "function_call"
        assert rel.line_number == 46
        assert rel.source_symbol == "handle_request"
        assert rel.target_symbol == "retry_with_backoff"
        assert rel.target_line == 120
        assert rel.metadata == {"context": "error_handling"}

    def test_relationship_roundtrip_serialization(self):
        """Test that to_dict and from_dict are inverses."""
        original = Relationship(
            source_file="src/handlers.py",
            target_file="src/utils.py",
            relationship_type=RelationshipType.WILDCARD_IMPORT,
            line_number=3,
            source_symbol="*",
            target_symbol=None,
            target_line=None,
            metadata={"limitation": "function-level tracking unavailable"},
        )

        data = original.to_dict()
        reconstructed = Relationship.from_dict(data)

        assert reconstructed.source_file == original.source_file
        assert reconstructed.target_file == original.target_file
        assert reconstructed.relationship_type == original.relationship_type
        assert reconstructed.line_number == original.line_number
        assert reconstructed.source_symbol == original.source_symbol
        assert reconstructed.target_symbol == original.target_symbol
        assert reconstructed.target_line == original.target_line
        assert reconstructed.metadata == original.metadata


class TestFileMetadata:
    """Tests for FileMetadata dataclass."""

    def test_file_metadata_instantiation(self):
        """Test creating file metadata with all fields."""
        metadata = FileMetadata(
            filepath="src/bot.py",
            last_analyzed=1700000000.0,
            relationship_count=5,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )

        assert metadata.filepath == "src/bot.py"
        assert metadata.last_analyzed == 1700000000.0
        assert metadata.relationship_count == 5
        assert metadata.has_dynamic_patterns is False
        assert metadata.dynamic_pattern_types == []
        assert metadata.is_unparseable is False

    def test_file_metadata_with_dynamic_patterns(self):
        """Test file metadata with dynamic patterns."""
        metadata = FileMetadata(
            filepath="src/dynamic.py",
            last_analyzed=1700000100.0,
            relationship_count=3,
            has_dynamic_patterns=True,
            dynamic_pattern_types=["dynamic_dispatch", "monkey_patching"],
            is_unparseable=False,
        )

        assert metadata.has_dynamic_patterns is True
        assert len(metadata.dynamic_pattern_types) == 2
        assert "dynamic_dispatch" in metadata.dynamic_pattern_types
        assert "monkey_patching" in metadata.dynamic_pattern_types

    def test_file_metadata_to_dict(self):
        """Test serialization of file metadata."""
        metadata = FileMetadata(
            filepath="src/bot.py",
            last_analyzed=1700000000.0,
            relationship_count=5,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )

        data = metadata.to_dict()

        assert data["filepath"] == "src/bot.py"
        assert data["last_analyzed"] == 1700000000.0
        assert data["relationship_count"] == 5
        assert data["has_dynamic_patterns"] is False
        assert data["dynamic_pattern_types"] == []
        assert data["is_unparseable"] is False

    def test_file_metadata_from_dict(self):
        """Test deserialization of file metadata."""
        data = {
            "filepath": "src/bot.py",
            "last_analyzed": 1700000000.0,
            "relationship_count": 5,
            "has_dynamic_patterns": True,
            "dynamic_pattern_types": ["exec_eval"],
            "is_unparseable": False,
        }

        metadata = FileMetadata.from_dict(data)

        assert metadata.filepath == "src/bot.py"
        assert metadata.last_analyzed == 1700000000.0
        assert metadata.relationship_count == 5
        assert metadata.has_dynamic_patterns is True
        assert metadata.dynamic_pattern_types == ["exec_eval"]
        assert metadata.is_unparseable is False

    def test_file_metadata_roundtrip_serialization(self):
        """Test that to_dict and from_dict are inverses."""
        original = FileMetadata(
            filepath="src/complex.py",
            last_analyzed=1700000200.0,
            relationship_count=12,
            has_dynamic_patterns=True,
            dynamic_pattern_types=["decorators", "metaclasses"],
            is_unparseable=False,
        )

        data = original.to_dict()
        reconstructed = FileMetadata.from_dict(data)

        assert reconstructed.filepath == original.filepath
        assert reconstructed.last_analyzed == original.last_analyzed
        assert reconstructed.relationship_count == original.relationship_count
        assert reconstructed.has_dynamic_patterns == original.has_dynamic_patterns
        assert reconstructed.dynamic_pattern_types == original.dynamic_pattern_types
        assert reconstructed.is_unparseable == original.is_unparseable


class TestRelationshipGraph:
    """Tests for RelationshipGraph class."""

    def test_graph_initialization(self):
        """Test creating an empty relationship graph."""
        graph = RelationshipGraph()

        assert len(graph.get_all_relationships()) == 0
        assert graph._dependencies == {}
        assert graph._dependents == {}
        assert graph._file_metadata == {}

    def test_add_single_relationship(self):
        """Test adding a single relationship to the graph."""
        graph = RelationshipGraph()
        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        graph.add_relationship(rel)

        relationships = graph.get_all_relationships()
        assert len(relationships) == 1
        assert relationships[0].source_file == "src/bot.py"
        assert relationships[0].target_file == "src/retry.py"

    def test_bidirectional_indexing(self):
        """Test that bidirectional indices are maintained correctly."""
        graph = RelationshipGraph()
        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        graph.add_relationship(rel)

        # Check forward index (dependencies)
        assert "src/retry.py" in graph._dependencies["src/bot.py"]

        # Check reverse index (dependents)
        assert "src/bot.py" in graph._dependents["src/retry.py"]

    def test_get_dependencies(self):
        """Test querying dependencies for a file."""
        graph = RelationshipGraph()

        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/bot.py",
            target_file="src/utils.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=6,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        dependencies = graph.get_dependencies("src/bot.py")
        assert len(dependencies) == 2
        target_files = {rel.target_file for rel in dependencies}
        assert target_files == {"src/retry.py", "src/utils.py"}

    def test_get_dependents(self):
        """Test querying dependents for a file."""
        graph = RelationshipGraph()

        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/handlers.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=10,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        dependents = graph.get_dependents("src/retry.py")
        assert len(dependents) == 2
        source_files = {rel.source_file for rel in dependents}
        assert source_files == {"src/bot.py", "src/handlers.py"}

    def test_remove_relationships_for_file(self):
        """Test removing all relationships involving a file."""
        graph = RelationshipGraph()

        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/retry.py",
            target_file="src/utils.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=3,
        )
        rel3 = Relationship(
            source_file="src/handlers.py",
            target_file="src/bot.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=8,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)
        graph.add_relationship(rel3)

        # Remove all relationships involving src/retry.py
        graph.remove_relationships_for_file("src/retry.py")

        # Should only have rel3 left
        relationships = graph.get_all_relationships()
        assert len(relationships) == 1
        assert relationships[0].source_file == "src/handlers.py"
        assert relationships[0].target_file == "src/bot.py"

        # Check indices updated correctly
        assert "src/retry.py" not in graph._dependencies
        assert "src/retry.py" not in graph._dependents

    def test_file_metadata_operations(self):
        """Test setting and getting file metadata."""
        graph = RelationshipGraph()

        metadata = FileMetadata(
            filepath="src/bot.py",
            last_analyzed=1700000000.0,
            relationship_count=5,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )

        graph.set_file_metadata("src/bot.py", metadata)

        retrieved = graph.get_file_metadata("src/bot.py")
        assert retrieved is not None
        assert retrieved.filepath == "src/bot.py"
        assert retrieved.relationship_count == 5

    def test_export_to_dict(self):
        """Test exporting graph to JSON-compatible dict (FR-23, FR-25)."""
        graph = RelationshipGraph()

        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
            source_symbol="retry_with_backoff",
            target_symbol="retry_with_backoff",
            target_line=120,
        )

        metadata = FileMetadata(
            filepath="src/bot.py",
            last_analyzed=1700000000.0,
            relationship_count=1,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )

        graph.add_relationship(rel)
        graph.set_file_metadata("src/bot.py", metadata)

        export = graph.export_to_dict()

        # Check TDD Section 3.10.3 structure
        assert "metadata" in export
        assert "files" in export
        assert "relationships" in export
        assert "graph_metadata" in export

        # Check metadata section
        assert export["metadata"]["version"] == "0.1.0"
        assert export["metadata"]["language"] == "python"
        assert export["metadata"]["total_files"] == 1
        assert export["metadata"]["total_relationships"] == 1
        assert "timestamp" in export["metadata"]

        # Check relationships
        assert len(export["relationships"]) == 1
        assert export["relationships"][0]["source_file"] == "src/bot.py"
        assert export["relationships"][0]["target_file"] == "src/retry.py"

        # Check files section
        assert len(export["files"]) == 1
        assert export["files"][0]["path"] == "src/bot.py"
        assert export["files"][0]["relationship_count"] == 1
        assert "last_modified" in export["files"][0]

        # Check graph_metadata section
        assert "circular_imports" in export["graph_metadata"]
        assert "most_connected_files" in export["graph_metadata"]

    def test_export_metadata_section(self):
        """Test export metadata section contains required fields (TDD 3.10.3)."""
        graph = RelationshipGraph()

        metadata1 = FileMetadata(
            filepath="src/bot.py",
            last_analyzed=1700000000.0,
            relationship_count=1,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )

        metadata2 = FileMetadata(
            filepath="src/dynamic.py",
            last_analyzed=1700000100.0,
            relationship_count=2,
            has_dynamic_patterns=True,
            dynamic_pattern_types=["exec_eval"],
            is_unparseable=False,
        )

        graph.set_file_metadata("src/bot.py", metadata1)
        graph.set_file_metadata("src/dynamic.py", metadata2)

        export = graph.export_to_dict()

        # Check metadata section
        assert export["metadata"]["total_files"] == 2
        assert export["metadata"]["version"] == "0.1.0"
        assert export["metadata"]["language"] == "python"

    def test_export_includes_timestamp(self):
        """Test that export includes ISO format timestamp (TDD 3.10.3)."""
        from datetime import datetime

        graph = RelationshipGraph()
        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        graph.add_relationship(rel)

        export = graph.export_to_dict()

        # Check timestamp exists and is ISO format string
        assert "timestamp" in export["metadata"]
        timestamp_str = export["metadata"]["timestamp"]
        assert isinstance(timestamp_str, str)
        # Verify ISO format by parsing
        parsed = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        assert parsed is not None

    def test_validate_graph_valid(self):
        """Test validation passes for a correctly structured graph (EC-19)."""
        graph = RelationshipGraph()

        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/handlers.py",
            target_file="src/utils.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=10,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        is_valid, errors = graph.validate_graph()

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_graph_detects_duplicates(self):
        """Test validation detects duplicate relationships (EC-19)."""
        graph = RelationshipGraph()

        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        is_valid, errors = graph.validate_graph()

        assert is_valid is False
        assert len(errors) > 0
        assert any("Duplicate relationship" in error for error in errors)

    def test_get_dependencies_deduplicates(self):
        """Test get_dependencies filters out duplicate relationships (Issue #144)."""
        graph = RelationshipGraph()

        # Create duplicate relationships with different object instances but same attributes
        rel1 = Relationship(
            source_file="src/main.py",
            target_file="src/models.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=10,
            target_symbol="MyClass",
            target_line=50,
        )
        rel2 = Relationship(
            source_file="src/main.py",
            target_file="src/models.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=10,
            target_symbol="MyClass",
            target_line=50,
        )
        # Add a non-duplicate relationship
        rel3 = Relationship(
            source_file="src/main.py",
            target_file="src/utils.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=11,
            target_symbol="helper",
            target_line=20,
        )

        # Add all relationships including duplicates
        graph.add_relationship(rel1)
        graph.add_relationship(rel2)
        graph.add_relationship(rel3)

        # Get dependencies should return only unique relationships
        dependencies = graph.get_dependencies("src/main.py")

        # Should have 2 unique relationships, not 3
        assert len(dependencies) == 2

        # Verify we have both unique relationships
        target_files = {rel.target_file for rel in dependencies}
        assert "src/models.py" in target_files
        assert "src/utils.py" in target_files

    def test_get_dependents_deduplicates(self):
        """Test get_dependents filters out duplicate relationships (Issue #144)."""
        graph = RelationshipGraph()

        # Create duplicate relationships pointing to the same target
        rel1 = Relationship(
            source_file="src/main.py",
            target_file="src/models.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=10,
            target_symbol="MyClass",
            target_line=50,
        )
        rel2 = Relationship(
            source_file="src/main.py",
            target_file="src/models.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=10,
            target_symbol="MyClass",
            target_line=50,
        )
        # Add a non-duplicate relationship
        rel3 = Relationship(
            source_file="src/other.py",
            target_file="src/models.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
            target_symbol="MyClass",
            target_line=50,
        )

        # Add all relationships including duplicates
        graph.add_relationship(rel1)
        graph.add_relationship(rel2)
        graph.add_relationship(rel3)

        # Get dependents should return only unique relationships
        dependents = graph.get_dependents("src/models.py")

        # Should have 2 unique relationships, not 3
        assert len(dependents) == 2

        # Verify we have both unique relationships
        source_files = {rel.source_file for rel in dependents}
        assert "src/main.py" in source_files
        assert "src/other.py" in source_files

    def test_validate_graph_detects_index_inconsistency(self):
        """Test validation detects bidirectional index inconsistencies (EC-19)."""
        graph = RelationshipGraph()

        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        graph.add_relationship(rel)

        # Manually corrupt the dependencies index
        graph._dependencies["src/bot.py"].remove("src/retry.py")

        is_valid, errors = graph.validate_graph()

        assert is_valid is False
        assert len(errors) > 0
        assert any("Index inconsistency" in error for error in errors)

    def test_validate_graph_detects_missing_index(self):
        """Test validation detects missing index entries (EC-19)."""
        graph = RelationshipGraph()

        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        graph.add_relationship(rel)

        # Manually corrupt by removing an index entirely
        del graph._dependents["src/retry.py"]

        is_valid, errors = graph.validate_graph()

        assert is_valid is False
        assert len(errors) > 0
        assert any("missing from dependents index" in error for error in errors)

    def test_detect_corruption_returns_false_when_valid(self):
        """Test detect_corruption returns False for valid graph (EC-19)."""
        graph = RelationshipGraph()

        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        graph.add_relationship(rel)

        is_corrupted = graph.detect_corruption()

        assert is_corrupted is False

    def test_detect_corruption_returns_true_when_invalid(self):
        """Test detect_corruption returns True for corrupted graph (EC-19)."""
        graph = RelationshipGraph()

        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        is_corrupted = graph.detect_corruption()

        assert is_corrupted is True

    def test_clear_graph(self):
        """Test clearing graph removes all data (EC-19 recovery)."""
        graph = RelationshipGraph()

        # Add multiple relationships and metadata
        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/handlers.py",
            target_file="src/utils.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=10,
        )

        metadata = FileMetadata(
            filepath="src/bot.py",
            last_analyzed=1700000000.0,
            relationship_count=1,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)
        graph.set_file_metadata("src/bot.py", metadata)

        # Clear everything
        graph.clear()

        # Verify all data structures are empty
        assert len(graph.get_all_relationships()) == 0
        assert len(graph._dependencies) == 0
        assert len(graph._dependents) == 0
        assert len(graph._file_metadata) == 0

    def test_atomic_updates(self):
        """Test that relationship updates are atomic (T-4.1)."""
        graph = RelationshipGraph()

        rel = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )

        graph.add_relationship(rel)

        # After add, all indices should be updated
        assert len(graph.get_all_relationships()) == 1
        assert "src/retry.py" in graph._dependencies["src/bot.py"]
        assert "src/bot.py" in graph._dependents["src/retry.py"]

        # Validation should pass (no partial state)
        is_valid, _ = graph.validate_graph()
        assert is_valid is True

    def test_bidirectional_query_correctness(self):
        """Test bidirectional queries work correctly (T-4.2)."""
        graph = RelationshipGraph()

        # Create a graph: bot.py → retry.py, handlers.py → retry.py
        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/handlers.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=10,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        # Query dependencies of bot.py
        bot_deps = graph.get_dependencies("src/bot.py")
        assert len(bot_deps) == 1
        assert bot_deps[0].target_file == "src/retry.py"

        # Query dependents of retry.py
        retry_dependents = graph.get_dependents("src/retry.py")
        assert len(retry_dependents) == 2
        source_files = {rel.source_file for rel in retry_dependents}
        assert source_files == {"src/bot.py", "src/handlers.py"}

    def test_get_all_relationships(self):
        """Test get_all_relationships returns complete graph export (T-4.3)."""
        graph = RelationshipGraph()

        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/handlers.py",
            target_file="src/utils.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=10,
        )
        rel3 = Relationship(
            source_file="src/bot.py",
            target_file="src/utils.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=20,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)
        graph.add_relationship(rel3)

        all_rels = graph.get_all_relationships()

        assert len(all_rels) == 3
        # Verify we got all relationships
        source_target_pairs = {(r.source_file, r.target_file) for r in all_rels}
        assert source_target_pairs == {
            ("src/bot.py", "src/retry.py"),
            ("src/handlers.py", "src/utils.py"),
            ("src/bot.py", "src/utils.py"),
        }

    def test_query_operations_api(self):
        """Test query operations API works correctly (T-4.4)."""
        graph = RelationshipGraph()

        # Build a simple graph
        rel1 = Relationship(
            source_file="src/bot.py",
            target_file="src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
        )
        rel2 = Relationship(
            source_file="src/bot.py",
            target_file="src/utils.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=6,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        # Test get_dependencies
        deps = graph.get_dependencies("src/bot.py")
        assert len(deps) == 2
        assert all(rel.source_file == "src/bot.py" for rel in deps)

        # Test get_dependencies for file with no dependencies
        no_deps = graph.get_dependencies("src/retry.py")
        assert len(no_deps) == 0

        # Test get_dependents
        dependents = graph.get_dependents("src/retry.py")
        assert len(dependents) == 1
        assert dependents[0].source_file == "src/bot.py"

        # Test get_all_relationships
        all_rels = graph.get_all_relationships()
        assert len(all_rels) == 2


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_instantiation_minimal(self):
        """Test creating a cache entry with minimal fields."""
        entry = CacheEntry(
            filepath="src/retry.py",
            line_start=120,
            line_end=135,
            content='def retry_with_backoff(func, max_attempts=3):\n    """Retry function"""',
            last_accessed=1700000480.0,
            access_count=3,
            size_bytes=250,
        )

        assert entry.filepath == "src/retry.py"
        assert entry.line_start == 120
        assert entry.line_end == 135
        assert entry.last_accessed == 1700000480.0
        assert entry.access_count == 3
        assert entry.size_bytes == 250
        assert entry.symbol_name is None

    def test_cache_entry_instantiation_full(self):
        """Test creating a cache entry with all fields."""
        entry = CacheEntry(
            filepath="src/retry.py",
            line_start=120,
            line_end=135,
            content='def retry_with_backoff(func, max_attempts=3):\n    """Retry function"""',
            last_accessed=1700000480.0,
            access_count=3,
            size_bytes=250,
            symbol_name="retry_with_backoff",
        )

        assert entry.symbol_name == "retry_with_backoff"

    def test_cache_entry_to_dict(self):
        """Test serialization of cache entry."""
        entry = CacheEntry(
            filepath="src/retry.py",
            line_start=120,
            line_end=135,
            content="def retry_with_backoff(func):\n    pass",
            last_accessed=1700000480.0,
            access_count=3,
            size_bytes=250,
            symbol_name="retry_with_backoff",
        )

        data = entry.to_dict()

        assert data["filepath"] == "src/retry.py"
        assert data["line_start"] == 120
        assert data["line_end"] == 135
        assert data["content"] == "def retry_with_backoff(func):\n    pass"
        assert data["last_accessed"] == 1700000480.0
        assert data["access_count"] == 3
        assert data["size_bytes"] == 250
        assert data["symbol_name"] == "retry_with_backoff"

    def test_cache_entry_from_dict(self):
        """Test deserialization of cache entry."""
        data = {
            "filepath": "src/retry.py",
            "line_start": 120,
            "line_end": 135,
            "content": "def retry_with_backoff(func):\n    pass",
            "last_accessed": 1700000480.0,
            "access_count": 3,
            "size_bytes": 250,
            "symbol_name": "retry_with_backoff",
        }

        entry = CacheEntry.from_dict(data)

        assert entry.filepath == "src/retry.py"
        assert entry.line_start == 120
        assert entry.line_end == 135
        assert entry.content == "def retry_with_backoff(func):\n    pass"
        assert entry.last_accessed == 1700000480.0
        assert entry.access_count == 3
        assert entry.size_bytes == 250
        assert entry.symbol_name == "retry_with_backoff"

    def test_cache_entry_roundtrip_serialization(self):
        """Test that to_dict and from_dict are inverses."""
        original = CacheEntry(
            filepath="src/utils.py",
            line_start=50,
            line_end=75,
            content='class Helper:\n    """Helper class"""',
            last_accessed=1700000600.0,
            access_count=10,
            size_bytes=500,
            symbol_name="Helper",
        )

        data = original.to_dict()
        reconstructed = CacheEntry.from_dict(data)

        assert reconstructed.filepath == original.filepath
        assert reconstructed.line_start == original.line_start
        assert reconstructed.line_end == original.line_end
        assert reconstructed.content == original.content
        assert reconstructed.last_accessed == original.last_accessed
        assert reconstructed.access_count == original.access_count
        assert reconstructed.size_bytes == original.size_bytes
        assert reconstructed.symbol_name == original.symbol_name


class TestCacheStatistics:
    """Tests for CacheStatistics dataclass."""

    def test_cache_statistics_instantiation(self):
        """Test creating cache statistics."""
        stats = CacheStatistics(
            hits=100,
            misses=25,
            staleness_refreshes=5,
            evictions_lru=3,
            current_size_bytes=45000,
            peak_size_bytes=50000,
            current_entry_count=20,
            peak_entry_count=25,
        )

        assert stats.hits == 100
        assert stats.misses == 25
        assert stats.staleness_refreshes == 5
        assert stats.evictions_lru == 3
        assert stats.current_size_bytes == 45000
        assert stats.peak_size_bytes == 50000
        assert stats.current_entry_count == 20
        assert stats.peak_entry_count == 25

    def test_cache_statistics_to_dict(self):
        """Test serialization of cache statistics."""
        stats = CacheStatistics(
            hits=100,
            misses=25,
            staleness_refreshes=5,
            evictions_lru=3,
            current_size_bytes=45000,
            peak_size_bytes=50000,
            current_entry_count=20,
            peak_entry_count=25,
        )

        data = stats.to_dict()

        assert data["hits"] == 100
        assert data["misses"] == 25
        assert data["staleness_refreshes"] == 5
        assert data["evictions_lru"] == 3
        assert data["current_size_bytes"] == 45000
        assert data["peak_size_bytes"] == 50000
        assert data["current_entry_count"] == 20
        assert data["peak_entry_count"] == 25

    def test_cache_statistics_from_dict(self):
        """Test deserialization of cache statistics."""
        data = {
            "hits": 150,
            "misses": 30,
            "staleness_refreshes": 8,
            "evictions_lru": 5,
            "current_size_bytes": 48000,
            "peak_size_bytes": 51000,
            "current_entry_count": 22,
            "peak_entry_count": 27,
        }

        stats = CacheStatistics.from_dict(data)

        assert stats.hits == 150
        assert stats.misses == 30
        assert stats.staleness_refreshes == 8
        assert stats.evictions_lru == 5
        assert stats.current_size_bytes == 48000
        assert stats.peak_size_bytes == 51000
        assert stats.current_entry_count == 22
        assert stats.peak_entry_count == 27

    def test_cache_statistics_roundtrip_serialization(self):
        """Test that to_dict and from_dict are inverses."""
        original = CacheStatistics(
            hits=200,
            misses=40,
            staleness_refreshes=10,
            evictions_lru=7,
            current_size_bytes=49000,
            peak_size_bytes=50000,
            current_entry_count=24,
            peak_entry_count=30,
        )

        data = original.to_dict()
        reconstructed = CacheStatistics.from_dict(data)

        assert reconstructed.hits == original.hits
        assert reconstructed.misses == original.misses
        assert reconstructed.staleness_refreshes == original.staleness_refreshes
        assert reconstructed.evictions_lru == original.evictions_lru
        assert reconstructed.current_size_bytes == original.current_size_bytes
        assert reconstructed.peak_size_bytes == original.peak_size_bytes
        assert reconstructed.current_entry_count == original.current_entry_count
        assert reconstructed.peak_entry_count == original.peak_entry_count


class TestGraphExportValidation:
    """Tests for graph export validation (T-4.5, T-4.6, T-4.7).

    These tests validate the graph export functionality per TDD Section 3.10.3.
    """

    def test_export_produces_valid_json_t45(self):
        """T-4.5: Graph export produces valid JSON.

        Validates that the export can be serialized to JSON without errors.
        """
        import json

        graph = RelationshipGraph()
        rel = Relationship(
            source_file="/project/src/bot.py",
            target_file="/project/src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
            target_symbol="retry_with_backoff",
            target_line=120,
        )
        metadata = FileMetadata(
            filepath="/project/src/bot.py",
            last_analyzed=1700000000.0,
            relationship_count=1,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )

        graph.add_relationship(rel)
        graph.set_file_metadata("/project/src/bot.py", metadata)

        export = graph.export_to_dict(project_root="/project")

        # Should not raise - valid JSON
        json_str = json.dumps(export)
        assert len(json_str) > 0

        # Round-trip should work
        parsed = json.loads(json_str)
        assert parsed["metadata"]["version"] == "0.1.0"

    def test_export_contains_all_required_fields_t46(self):
        """T-4.6: Exported graph contains all required fields.

        Validates TDD Section 3.10.3 structure:
        - metadata: timestamp, version, language, project_root, counts
        - files: path, relative_path, last_modified, relationship_count, in_import_cycle
        - relationships: all relationship fields
        - graph_metadata: circular_imports, most_connected_files
        """
        graph = RelationshipGraph()

        # Add relationships
        rel1 = Relationship(
            source_file="/project/src/bot.py",
            target_file="/project/src/retry.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
            target_symbol="retry_with_backoff",
            target_line=120,
            metadata={"import_style": "from...import"},
        )
        rel2 = Relationship(
            source_file="/project/src/handlers.py",
            target_file="/project/src/retry.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=10,
        )

        # Add file metadata
        metadata1 = FileMetadata(
            filepath="/project/src/bot.py",
            last_analyzed=1700000000.0,
            relationship_count=1,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )
        metadata2 = FileMetadata(
            filepath="/project/src/handlers.py",
            last_analyzed=1700000100.0,
            relationship_count=1,
            has_dynamic_patterns=True,
            dynamic_pattern_types=["exec_eval"],
            is_unparseable=False,
        )

        graph.add_relationship(rel1)
        graph.add_relationship(rel2)
        graph.set_file_metadata("/project/src/bot.py", metadata1)
        graph.set_file_metadata("/project/src/handlers.py", metadata2)

        export = graph.export_to_dict(project_root="/project")

        # Validate metadata section (TDD 3.10.3)
        meta = export["metadata"]
        assert "timestamp" in meta
        assert meta["version"] == "0.1.0"
        assert meta["language"] == "python"
        assert meta["project_root"] == "/project"
        assert meta["total_files"] == 2
        assert meta["total_relationships"] == 2

        # Validate files section (TDD 3.10.3)
        assert len(export["files"]) == 2
        for file_entry in export["files"]:
            assert "path" in file_entry
            assert "relative_path" in file_entry
            assert "last_modified" in file_entry
            assert "relationship_count" in file_entry
            assert "in_import_cycle" in file_entry

        # Validate relationships section (TDD 3.10.3)
        assert len(export["relationships"]) == 2
        for rel_entry in export["relationships"]:
            assert "source_file" in rel_entry
            assert "target_file" in rel_entry
            assert "relationship_type" in rel_entry
            assert "line_number" in rel_entry

        # Validate graph_metadata section (TDD 3.10.3)
        graph_meta = export["graph_metadata"]
        assert "circular_imports" in graph_meta
        assert "most_connected_files" in graph_meta
        assert isinstance(graph_meta["circular_imports"], list)
        assert isinstance(graph_meta["most_connected_files"], list)

    def test_export_can_be_parsed_by_external_tools_t47(self):
        """T-4.7: External tools can parse exported graph.

        Validates that the export format is machine-parseable by simulating
        an external tool parsing and extracting relationships.
        """
        import json

        graph = RelationshipGraph()

        # Create a realistic graph
        files = [
            "/project/src/main.py",
            "/project/src/utils.py",
            "/project/src/config.py",
            "/project/lib/helpers.py",
        ]

        for i, source in enumerate(files):
            for j, target in enumerate(files):
                if i != j:
                    rel = Relationship(
                        source_file=source,
                        target_file=target,
                        relationship_type=RelationshipType.IMPORT,
                        line_number=i * 10 + j + 1,
                    )
                    graph.add_relationship(rel)

            metadata = FileMetadata(
                filepath=source,
                last_analyzed=1700000000.0 + i * 100,
                relationship_count=len(files) - 1,
                has_dynamic_patterns=False,
                dynamic_pattern_types=[],
                is_unparseable=False,
            )
            graph.set_file_metadata(source, metadata)

        export = graph.export_to_dict(project_root="/project")

        # Serialize and parse (simulating external tool)
        json_str = json.dumps(export)
        parsed = json.loads(json_str)

        # External tool operations:
        # 1. Get version for compatibility check
        version = parsed["metadata"]["version"]
        assert version == "0.1.0"

        # 2. Count relationships
        rel_count = len(parsed["relationships"])
        assert rel_count == 12  # 4 files * 3 relationships each

        # 3. Extract all source files
        source_files = {r["source_file"] for r in parsed["relationships"]}
        assert len(source_files) == 4

        # 4. Find most connected files
        most_connected = parsed["graph_metadata"]["most_connected_files"]
        assert len(most_connected) > 0
        # Each file should have 3 incoming dependencies
        for mc in most_connected:
            assert mc["dependency_count"] == 3

        # 5. Get relative paths for portability
        for file_entry in parsed["files"]:
            assert file_entry["relative_path"].startswith("src/") or file_entry[
                "relative_path"
            ].startswith("lib/")

    def test_export_includes_both_absolute_and_relative_paths(self):
        """Test that export includes both absolute and relative paths (FR-25)."""
        graph = RelationshipGraph()

        metadata = FileMetadata(
            filepath="/project/src/module.py",
            last_analyzed=1700000000.0,
            relationship_count=0,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )
        graph.set_file_metadata("/project/src/module.py", metadata)

        export = graph.export_to_dict(project_root="/project")

        # Check files have both path types
        file_entry = export["files"][0]
        assert file_entry["path"] == "/project/src/module.py"  # Absolute
        assert file_entry["relative_path"] == "src/module.py"  # Relative

    def test_export_most_connected_files_sorted(self):
        """Test that most_connected_files are sorted by dependency count."""
        graph = RelationshipGraph()

        # Create relationships where utils.py is most imported
        source_files = ["a.py", "b.py", "c.py", "d.py"]
        target_counts = {
            "utils.py": 4,  # Most imported
            "config.py": 2,
            "helpers.py": 1,
        }

        line_num = 1
        for target, count in target_counts.items():
            for i in range(count):
                rel = Relationship(
                    source_file=source_files[i],
                    target_file=target,
                    relationship_type=RelationshipType.IMPORT,
                    line_number=line_num,
                )
                graph.add_relationship(rel)
                line_num += 1

        export = graph.export_to_dict()

        most_connected = export["graph_metadata"]["most_connected_files"]

        # Should be sorted descending by dependency_count
        assert len(most_connected) >= 3
        assert most_connected[0]["file"] == "utils.py"
        assert most_connected[0]["dependency_count"] == 4
        assert most_connected[1]["file"] == "config.py"
        assert most_connected[1]["dependency_count"] == 2

    def test_export_without_project_root(self):
        """Test export works without project_root (no relative paths)."""
        graph = RelationshipGraph()

        metadata = FileMetadata(
            filepath="/some/path/file.py",
            last_analyzed=1700000000.0,
            relationship_count=0,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )
        graph.set_file_metadata("/some/path/file.py", metadata)

        export = graph.export_to_dict()  # No project_root

        # Should still work
        assert "metadata" in export
        assert "files" in export

        # project_root should not be in metadata
        assert "project_root" not in export["metadata"]

        # Files should have path but no relative_path
        assert export["files"][0]["path"] == "/some/path/file.py"
        assert "relative_path" not in export["files"][0]
