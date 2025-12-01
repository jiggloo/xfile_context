# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Unit tests for storage abstraction layer.

Tests cover:
- RelationshipStore interface contract
- InMemoryStore implementation
- O(1) lookup performance characteristics
- Graph export functionality
"""

import pytest

from xfile_context.models import Relationship, RelationshipType
from xfile_context.storage import InMemoryStore, RelationshipStore


class TestInMemoryStore:
    """Tests for InMemoryStore implementation."""

    def test_initialization(self):
        """Test store initializes empty."""
        store = InMemoryStore()
        assert store.get_all_relationships() == []

    def test_add_single_relationship(self):
        """Test adding a single relationship."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )

        store.add_relationship(rel)

        all_rels = store.get_all_relationships()
        assert len(all_rels) == 1
        assert all_rels[0] == rel

    def test_add_multiple_relationships(self):
        """Test adding multiple relationships."""
        store = InMemoryStore()
        rel1 = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="a.py",
            target_file="c.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=5,
        )
        rel3 = Relationship(
            source_file="b.py",
            target_file="c.py",
            relationship_type=RelationshipType.CLASS_INHERITANCE,
            line_number=10,
        )

        store.add_relationship(rel1)
        store.add_relationship(rel2)
        store.add_relationship(rel3)

        all_rels = store.get_all_relationships()
        assert len(all_rels) == 3
        assert rel1 in all_rels
        assert rel2 in all_rels
        assert rel3 in all_rels

    def test_get_relationships_by_file_source(self):
        """Test getting relationships where file is source."""
        store = InMemoryStore()
        rel1 = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="a.py",
            target_file="c.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=5,
        )
        rel3 = Relationship(
            source_file="b.py",
            target_file="c.py",
            relationship_type=RelationshipType.CLASS_INHERITANCE,
            line_number=10,
        )

        store.add_relationship(rel1)
        store.add_relationship(rel2)
        store.add_relationship(rel3)

        # Get relationships for a.py (source in 2 relationships)
        a_rels = store.get_relationships("a.py")
        assert len(a_rels) == 2
        assert rel1 in a_rels
        assert rel2 in a_rels

    def test_get_relationships_by_file_target(self):
        """Test getting relationships where file is target."""
        store = InMemoryStore()
        rel1 = Relationship(
            source_file="a.py",
            target_file="c.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="b.py",
            target_file="c.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=5,
        )

        store.add_relationship(rel1)
        store.add_relationship(rel2)

        # Get relationships for c.py (target in 2 relationships)
        c_rels = store.get_relationships("c.py")
        assert len(c_rels) == 2
        assert rel1 in c_rels
        assert rel2 in c_rels

    def test_get_relationships_by_file_both_source_and_target(self):
        """Test getting relationships where file is both source and target."""
        store = InMemoryStore()
        rel1 = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="b.py",
            target_file="c.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=5,
        )

        store.add_relationship(rel1)
        store.add_relationship(rel2)

        # Get relationships for b.py (target in rel1, source in rel2)
        b_rels = store.get_relationships("b.py")
        assert len(b_rels) == 2
        assert rel1 in b_rels
        assert rel2 in b_rels

    def test_get_relationships_file_not_found(self):
        """Test getting relationships for non-existent file."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        store.add_relationship(rel)

        # Query for file not in store
        rels = store.get_relationships("z.py")
        assert rels == []

    def test_get_relationships_empty_store(self):
        """Test getting relationships from empty store."""
        store = InMemoryStore()
        rels = store.get_relationships("a.py")
        assert rels == []

    def test_remove_relationship(self):
        """Test removing a relationship."""
        store = InMemoryStore()
        rel1 = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="a.py",
            target_file="c.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=5,
        )

        store.add_relationship(rel1)
        store.add_relationship(rel2)

        # Remove rel1
        store.remove_relationship(rel1)

        # Verify only rel2 remains
        all_rels = store.get_all_relationships()
        assert len(all_rels) == 1
        assert all_rels[0] == rel2

        # Verify file indices updated
        a_rels = store.get_relationships("a.py")
        assert len(a_rels) == 1
        assert a_rels[0] == rel2

        b_rels = store.get_relationships("b.py")
        assert len(b_rels) == 0

    def test_remove_relationship_by_identity(self):
        """Test that remove matches by fields, not by object identity."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
            source_symbol="foo",
        )
        store.add_relationship(rel)

        # Create identical relationship (different object)
        rel_copy = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
            source_symbol="bar",  # Different optional field
        )

        # Remove should match by required fields only
        store.remove_relationship(rel_copy)

        all_rels = store.get_all_relationships()
        assert len(all_rels) == 0

    def test_remove_relationship_not_found(self):
        """Test removing non-existent relationship (should be idempotent)."""
        store = InMemoryStore()
        rel1 = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        store.add_relationship(rel1)

        rel2 = Relationship(
            source_file="x.py",
            target_file="y.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=99,
        )

        # Remove non-existent relationship (should not raise)
        store.remove_relationship(rel2)

        # Verify original relationship still present
        all_rels = store.get_all_relationships()
        assert len(all_rels) == 1
        assert all_rels[0] == rel1

    def test_self_dependency(self):
        """Test relationship where source_file == target_file."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="a.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=10,
        )

        store.add_relationship(rel)

        # Should appear in results for a.py
        a_rels = store.get_relationships("a.py")
        assert len(a_rels) == 1
        assert a_rels[0] == rel

    def test_export_graph_empty(self):
        """Test exporting empty graph."""
        store = InMemoryStore()
        export = store.export_graph()

        assert export["version"] == "0.1.0"
        assert export["relationships"] == []
        assert export["statistics"]["total_relationships"] == 0
        assert export["statistics"]["total_files"] == 0

    def test_export_graph_with_relationships(self):
        """Test exporting graph with relationships."""
        store = InMemoryStore()
        rel1 = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="a.py",
            target_file="c.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=5,
        )

        store.add_relationship(rel1)
        store.add_relationship(rel2)

        export = store.export_graph()

        assert export["version"] == "0.1.0"
        assert len(export["relationships"]) == 2
        assert export["statistics"]["total_relationships"] == 2
        assert export["statistics"]["total_files"] == 3  # a, b, c

        # Verify relationship dicts are correct
        rel_dicts = export["relationships"]
        assert any(r["source_file"] == "a.py" and r["target_file"] == "b.py" for r in rel_dicts)
        assert any(r["source_file"] == "a.py" and r["target_file"] == "c.py" for r in rel_dicts)

    def test_export_graph_excludes_removed_relationships(self):
        """Test that export excludes removed relationships."""
        store = InMemoryStore()
        rel1 = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="a.py",
            target_file="c.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=5,
        )

        store.add_relationship(rel1)
        store.add_relationship(rel2)
        store.remove_relationship(rel1)

        export = store.export_graph()

        assert export["statistics"]["total_relationships"] == 1
        assert len(export["relationships"]) == 1
        assert export["relationships"][0]["target_file"] == "c.py"

    def test_clear(self):
        """Test clearing all relationships."""
        store = InMemoryStore()
        rel1 = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="a.py",
            target_file="c.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=5,
        )

        store.add_relationship(rel1)
        store.add_relationship(rel2)

        store.clear()

        assert store.get_all_relationships() == []
        assert store.get_relationships("a.py") == []
        assert store.get_relationships("b.py") == []
        assert store.get_relationships("c.py") == []

    def test_o1_lookup_performance_characteristic(self):
        """Test that file-based lookup is O(1) by checking index structure.

        Note: This is a structural test, not a performance benchmark.
        """
        store = InMemoryStore()

        # Add relationships (start from 1 to avoid line_number=0)
        for i in range(1, 101):
            rel = Relationship(
                source_file=f"file_{i}.py",
                target_file="common.py",
                relationship_type=RelationshipType.IMPORT,
                line_number=i,
            )
            store.add_relationship(rel)

        # Verify index exists for O(1) lookup
        # Internal implementation detail: _by_file dict
        assert hasattr(store, "_by_file")
        assert "common.py" in store._by_file

        # Lookup should use index (O(1) dict access)
        rels = store.get_relationships("common.py")
        assert len(rels) == 100

    def test_mock_implementation_swap(self):
        """Test that RelationshipStore interface allows mock implementation.

        This validates the abstraction layer enables testing with mock stores.
        """

        # Create a minimal mock store
        class MockStore(RelationshipStore):
            def __init__(self):
                self.added = []
                self.removed = []

            def add_relationship(self, rel):
                self.added.append(rel)

            def remove_relationship(self, rel):
                self.removed.append(rel)

            def get_relationships(self, file_path):
                return [r for r in self.added if r.source_file == file_path]

            def get_all_relationships(self):
                return self.added

            def export_graph(self):
                return {"version": "mock", "relationships": []}

        # Use mock store
        mock = MockStore()
        rel = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )

        mock.add_relationship(rel)
        assert len(mock.added) == 1
        assert mock.get_all_relationships() == [rel]

    def test_relationships_with_all_optional_fields(self):
        """Test storing relationships with all optional fields populated."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=10,
            source_symbol="call_foo",
            target_symbol="foo",
            target_line=50,
            metadata={"context": "conditional"},
        )

        store.add_relationship(rel)

        retrieved = store.get_relationships("a.py")
        assert len(retrieved) == 1
        assert retrieved[0].source_symbol == "call_foo"
        assert retrieved[0].target_symbol == "foo"
        assert retrieved[0].target_line == 50
        assert retrieved[0].metadata == {"context": "conditional"}


class TestInMemoryStoreValidation:
    """Tests for input validation in InMemoryStore."""

    def test_reject_empty_source_file(self):
        """Test that empty source file path is rejected."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )

        with pytest.raises(ValueError, match="File paths cannot be empty"):
            store.add_relationship(rel)

    def test_reject_empty_target_file(self):
        """Test that empty target file path is rejected."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )

        with pytest.raises(ValueError, match="File paths cannot be empty"):
            store.add_relationship(rel)

    def test_reject_directory_traversal_in_source(self):
        """Test that directory traversal in source file is rejected."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="../../etc/passwd",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )

        with pytest.raises(ValueError, match="Directory traversal not allowed"):
            store.add_relationship(rel)

    def test_reject_directory_traversal_in_target(self):
        """Test that directory traversal in target file is rejected."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="../../../root/.ssh/id_rsa",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )

        with pytest.raises(ValueError, match="Directory traversal not allowed"):
            store.add_relationship(rel)

    def test_reject_negative_line_number(self):
        """Test that negative line number is rejected."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=-1,
        )

        with pytest.raises(ValueError, match="Line number must be positive"):
            store.add_relationship(rel)

    def test_reject_zero_line_number(self):
        """Test that zero line number is rejected."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=0,
        )

        with pytest.raises(ValueError, match="Line number must be positive"):
            store.add_relationship(rel)

    def test_reject_empty_relationship_type(self):
        """Test that empty relationship type is rejected."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="a.py",
            target_file="b.py",
            relationship_type="",
            line_number=1,
        )

        with pytest.raises(ValueError, match="Relationship type cannot be empty"):
            store.add_relationship(rel)

    def test_validation_on_remove(self):
        """Test that validation also applies to remove_relationship."""
        store = InMemoryStore()
        rel = Relationship(
            source_file="../../etc/passwd",
            target_file="b.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )

        with pytest.raises(ValueError, match="Directory traversal not allowed"):
            store.remove_relationship(rel)
