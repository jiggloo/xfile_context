# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for StalenessResolver (Issue #117 Option B).

These tests verify the topological sort-based algorithm for resolving
stale files and their transitive dependencies.
"""

from typing import List

from xfile_context.models import FileMetadata, Relationship, RelationshipGraph, RelationshipType
from xfile_context.staleness_resolver import StalenessResolver


class TestTopologicalSort:
    """Test the topological sort algorithm."""

    def test_topological_sort_simple_chain(self):
        """Test sorting A -> B -> C results in [C, B, A]."""
        graph = RelationshipGraph()

        # A -> B -> C
        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="/b.py",
                target_file="/c.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="c",
                line_number=1,
            )
        )

        # All files are stale
        stale_files = {"/a.py", "/b.py", "/c.py"}
        analyzed_files: List[str] = []

        resolver = StalenessResolver(
            graph=graph,
            is_file_stale=lambda f: f in stale_files,
            analyze_file=lambda f: (analyzed_files.append(f), True)[1],
        )

        dep_graph = graph.copy_dependency_graph()
        sorted_files = resolver._topological_sort(["/a.py", "/b.py", "/c.py"], dep_graph)

        # C should come first (no deps), then B, then A
        assert sorted_files == ["/c.py", "/b.py", "/a.py"]

    def test_topological_sort_diamond(self):
        """Test diamond pattern: A -> B, A -> C, B -> D, C -> D."""
        graph = RelationshipGraph()

        # A -> B, A -> C
        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/c.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="c",
                line_number=2,
            )
        )
        # B -> D, C -> D
        graph.add_relationship(
            Relationship(
                source_file="/b.py",
                target_file="/d.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="d",
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="/c.py",
                target_file="/d.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="d",
                line_number=1,
            )
        )

        dep_graph = graph.copy_dependency_graph()
        sorted_files = StalenessResolver(
            graph=graph,
            is_file_stale=lambda f: True,
            analyze_file=lambda f: True,
        )._topological_sort(["/a.py", "/b.py", "/c.py", "/d.py"], dep_graph)

        # D should come first (no deps in set)
        assert sorted_files[0] == "/d.py"
        # A should come last (depends on B and C)
        assert sorted_files[-1] == "/a.py"
        # B and C should be in the middle (order between them doesn't matter)
        assert set(sorted_files[1:3]) == {"/b.py", "/c.py"}

    def test_topological_sort_partial_stale(self):
        """Test sorting when only some files are stale."""
        graph = RelationshipGraph()

        # A -> B -> C
        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="/b.py",
                target_file="/c.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="c",
                line_number=1,
            )
        )

        dep_graph = graph.copy_dependency_graph()
        # Only A and C are stale (B is not)
        sorted_files = StalenessResolver(
            graph=graph,
            is_file_stale=lambda f: f in {"/a.py", "/c.py"},
            analyze_file=lambda f: True,
        )._topological_sort(["/a.py", "/c.py"], dep_graph)

        # C should come before A (C has no deps in the stale set)
        assert sorted_files == ["/c.py", "/a.py"]


class TestPendingRelationships:
    """Test pending relationship storage and restoration."""

    def test_store_pending_relationships(self):
        """Test storing relationships before removal."""
        graph = RelationshipGraph()

        rel = Relationship(
            source_file="/a.py",
            target_file="/b.py",
            relationship_type=RelationshipType.IMPORT,
            target_symbol="b",
            line_number=1,
        )
        graph.add_relationship(rel)

        stored = graph.store_pending_relationships("/a.py")
        assert len(stored) == 1
        assert stored[0].source_file == "/a.py"
        assert stored[0].target_file == "/b.py"

    def test_restore_pending_relationships(self):
        """Test restoring stored relationships."""
        graph = RelationshipGraph()

        rel = Relationship(
            source_file="/a.py",
            target_file="/b.py",
            relationship_type=RelationshipType.IMPORT,
            target_symbol="b",
            line_number=1,
        )
        graph.add_relationship(rel)

        # Store relationships
        graph.store_pending_relationships("/a.py")

        # Remove them
        graph.remove_relationships_for_file("/a.py")
        assert len(graph.get_dependencies("/a.py")) == 0

        # Restore them
        restored = graph.restore_pending_relationships("/a.py")
        assert restored is True
        assert len(graph.get_dependencies("/a.py")) == 1

    def test_has_pending_relationships(self):
        """Test checking for pending relationships."""
        graph = RelationshipGraph()

        rel = Relationship(
            source_file="/a.py",
            target_file="/b.py",
            relationship_type=RelationshipType.IMPORT,
            target_symbol="b",
            line_number=1,
        )
        graph.add_relationship(rel)

        assert graph.has_pending_relationships("/a.py") is False

        graph.store_pending_relationships("/a.py")
        assert graph.has_pending_relationships("/a.py") is True

        graph.restore_pending_relationships("/a.py")
        assert graph.has_pending_relationships("/a.py") is False


class TestTransitiveDependencies:
    """Test transitive dependency traversal."""

    def test_get_transitive_dependencies_simple(self):
        """Test getting transitive deps for A -> B -> C."""
        graph = RelationshipGraph()

        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="/b.py",
                target_file="/c.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="c",
                line_number=1,
            )
        )

        deps = graph.get_transitive_dependencies("/a.py")
        assert set(deps) == {"/b.py", "/c.py"}

    def test_get_transitive_dependencies_skips_special_markers(self):
        """Test that special markers like <stdlib> are skipped."""
        graph = RelationshipGraph()

        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="<stdlib>",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="os",
                line_number=2,
            )
        )

        deps = graph.get_transitive_dependencies("/a.py")
        assert "<stdlib>" not in deps
        assert "/b.py" in deps


class TestStalenessResolution:
    """Test the full staleness resolution algorithm."""

    def test_resolve_no_stale_files(self):
        """Test that nothing happens when no files are stale."""
        graph = RelationshipGraph()

        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )

        # Add metadata so files are "analyzed"
        graph.set_file_metadata(
            "/a.py",
            FileMetadata(
                filepath="/a.py",
                last_analyzed=1000.0,
                relationship_count=1,
                has_dynamic_patterns=False,
                dynamic_pattern_types=[],
                is_unparseable=False,
            ),
        )

        analyzed: List[str] = []
        resolver = StalenessResolver(
            graph=graph,
            is_file_stale=lambda f: False,  # Nothing is stale
            analyze_file=lambda f: (analyzed.append(f), True)[1],
        )

        result = resolver.resolve_staleness("/a.py")
        assert result == []
        assert analyzed == []

    def test_resolve_single_stale_file(self):
        """Test resolving a single stale target file."""
        graph = RelationshipGraph()

        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )

        analyzed: List[str] = []
        stale_files = {"/a.py"}

        resolver = StalenessResolver(
            graph=graph,
            is_file_stale=lambda f: f in stale_files,
            analyze_file=lambda f: (analyzed.append(f), True)[1],
        )

        result = resolver.resolve_staleness("/a.py")
        assert "/a.py" in result
        assert "/a.py" in analyzed

    def test_resolve_transitive_stale_chain(self):
        """Test resolving A -> B -> C where all are stale."""
        graph = RelationshipGraph()

        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="/b.py",
                target_file="/c.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="c",
                line_number=1,
            )
        )

        analyzed: List[str] = []
        stale_files = {"/a.py", "/b.py", "/c.py"}

        resolver = StalenessResolver(
            graph=graph,
            is_file_stale=lambda f: f in stale_files,
            analyze_file=lambda f: (analyzed.append(f), True)[1],
        )

        resolver.resolve_staleness("/a.py")

        # All should be analyzed
        assert set(analyzed) == {"/a.py", "/b.py", "/c.py"}

        # Order should be topological: C, B, A
        assert analyzed.index("/c.py") < analyzed.index("/b.py")
        assert analyzed.index("/b.py") < analyzed.index("/a.py")

    def test_resolve_partial_stale_with_pending_restoration(self):
        """Test when only some files are stale and others need restoration."""
        graph = RelationshipGraph()

        # A -> B -> C
        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="/b.py",
                target_file="/c.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="c",
                line_number=1,
            )
        )

        # Add metadata for B so it's "analyzed" but not stale
        graph.set_file_metadata(
            "/b.py",
            FileMetadata(
                filepath="/b.py",
                last_analyzed=1000.0,
                relationship_count=1,
                has_dynamic_patterns=False,
                dynamic_pattern_types=[],
                is_unparseable=False,
            ),
        )

        analyzed: List[str] = []
        # Only A and C are stale
        stale_files = {"/a.py", "/c.py"}

        resolver = StalenessResolver(
            graph=graph,
            is_file_stale=lambda f: f in stale_files,
            analyze_file=lambda f: (analyzed.append(f), True)[1],
        )

        resolver.resolve_staleness("/a.py")

        # Only A and C should be analyzed (B just needs restoration)
        assert set(analyzed) == {"/a.py", "/c.py"}

    def test_resolve_marks_pending_flag(self):
        """Test that pending_relationships flag is properly managed."""
        graph = RelationshipGraph()

        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )

        # X -> A (X depends on A)
        graph.add_relationship(
            Relationship(
                source_file="/x.py",
                target_file="/a.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="a",
                line_number=1,
            )
        )

        # Add metadata for X
        graph.set_file_metadata(
            "/x.py",
            FileMetadata(
                filepath="/x.py",
                last_analyzed=1000.0,
                relationship_count=1,
                has_dynamic_patterns=False,
                dynamic_pattern_types=[],
                is_unparseable=False,
            ),
        )

        stale_files = {"/a.py"}

        resolver = StalenessResolver(
            graph=graph,
            is_file_stale=lambda f: f in stale_files,
            analyze_file=lambda f: True,
        )

        resolver.resolve_staleness("/a.py")

        # X should be marked as pending (it depends on A which was stale)
        x_meta = graph.get_file_metadata("/x.py")
        assert x_meta is not None
        assert x_meta.pending_relationships is True


class TestFileMetadataPendingFlag:
    """Test the pending_relationships flag in FileMetadata."""

    def test_pending_relationships_default_false(self):
        """Test that pending_relationships defaults to False."""
        metadata = FileMetadata(
            filepath="/a.py",
            last_analyzed=1000.0,
            relationship_count=1,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )
        assert metadata.pending_relationships is False

    def test_pending_relationships_serialization(self):
        """Test that pending_relationships is serialized correctly."""
        metadata = FileMetadata(
            filepath="/a.py",
            last_analyzed=1000.0,
            relationship_count=1,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
            pending_relationships=True,
        )

        d = metadata.to_dict()
        assert d["pending_relationships"] is True

        restored = FileMetadata.from_dict(d)
        assert restored.pending_relationships is True

    def test_pending_relationships_backward_compatibility(self):
        """Test that missing pending_relationships defaults to False."""
        d = {
            "filepath": "/a.py",
            "last_analyzed": 1000.0,
            "relationship_count": 1,
            "has_dynamic_patterns": False,
            "dynamic_pattern_types": [],
            "is_unparseable": False,
            # No pending_relationships key
        }

        metadata = FileMetadata.from_dict(d)
        assert metadata.pending_relationships is False


class TestCopyDependencyGraph:
    """Test copying the dependency graph."""

    def test_copy_is_deep(self):
        """Test that the copy is a deep copy."""
        graph = RelationshipGraph()

        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )

        copied = graph.copy_dependency_graph()

        # Modify original
        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/c.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="c",
                line_number=2,
            )
        )

        # Copy should not be affected
        assert "/c.py" not in copied.get("/a.py", set())

    def test_copy_preserves_structure(self):
        """Test that copy preserves the graph structure."""
        graph = RelationshipGraph()

        graph.add_relationship(
            Relationship(
                source_file="/a.py",
                target_file="/b.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="b",
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="/b.py",
                target_file="/c.py",
                relationship_type=RelationshipType.IMPORT,
                target_symbol="c",
                line_number=1,
            )
        )

        copied = graph.copy_dependency_graph()

        assert "/b.py" in copied.get("/a.py", set())
        assert "/c.py" in copied.get("/b.py", set())
