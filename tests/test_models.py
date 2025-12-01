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

        # Check structure
        assert "version" in export
        assert "relationships" in export
        assert "file_metadata" in export
        assert "statistics" in export

        # Check version
        assert export["version"] == "0.1.0"

        # Check relationships
        assert len(export["relationships"]) == 1
        assert export["relationships"][0]["source_file"] == "src/bot.py"
        assert export["relationships"][0]["target_file"] == "src/retry.py"

        # Check file metadata
        assert "src/bot.py" in export["file_metadata"]
        assert export["file_metadata"]["src/bot.py"]["relationship_count"] == 1

        # Check statistics
        assert export["statistics"]["total_files"] == 1
        assert export["statistics"]["total_relationships"] == 1
        assert export["statistics"]["files_with_dynamic_patterns"] == 0

    def test_export_with_dynamic_patterns(self):
        """Test export statistics count files with dynamic patterns correctly."""
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

        assert export["statistics"]["total_files"] == 2
        assert export["statistics"]["files_with_dynamic_patterns"] == 1


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
