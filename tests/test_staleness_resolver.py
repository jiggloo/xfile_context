# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for StalenessResolver (Issue #117 Option B).

Tests cover:
- Basic staleness detection and resolution
- Topological sort ordering
- Transitive dependency handling
- Diamond pattern handling
- Pending relationships storage and restoration
- Integration with RelationshipGraph new methods
"""

import time
from typing import List

from xfile_context.models import FileMetadata, Relationship, RelationshipGraph, RelationshipType
from xfile_context.staleness_resolver import StalenessResolver


def _create_metadata(filepath: str, stale: bool = False) -> FileMetadata:
    """Create FileMetadata for testing.

    Args:
        filepath: File path.
        stale: If True, set last_analyzed to past time to simulate staleness.
    """
    return FileMetadata(
        filepath=filepath,
        # Set to past time if stale, future time if not
        last_analyzed=time.time() - 3600 if stale else time.time() + 3600,
        relationship_count=0,
        has_dynamic_patterns=False,
        dynamic_pattern_types=[],
        is_unparseable=False,
    )


class TestRelationshipGraphNewMethods:
    """Tests for new RelationshipGraph methods added for Issue #117 Option B."""

    def test_copy_dependency_graph(self):
        """Test that copy_dependency_graph returns a deep copy."""
        graph = RelationshipGraph()

        # Add relationships: A -> B, A -> C, B -> D
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="C",
                relationship_type=RelationshipType.IMPORT,
                line_number=2,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="B",
                target_file="D",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )

        copy = graph.copy_dependency_graph()

        # Verify copy has same structure
        assert "A" in copy
        assert copy["A"] == {"B", "C"}
        assert "B" in copy
        assert copy["B"] == {"D"}

        # Verify it's a deep copy (modifications don't affect original)
        copy["A"].add("X")
        assert "X" not in graph._dependencies["A"]

    def test_get_transitive_dependencies(self):
        """Test transitive dependency traversal."""
        graph = RelationshipGraph()

        # Build chain: A -> B -> C -> D
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="B",
                target_file="C",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="C",
                target_file="D",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )

        # Get transitive deps of A
        deps = graph.get_transitive_dependencies("A")

        assert deps == {"B", "C", "D"}

    def test_get_transitive_dependencies_diamond(self):
        """Test transitive dependencies with diamond pattern."""
        graph = RelationshipGraph()

        # Diamond: A -> B, A -> C, B -> D, C -> D
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="C",
                relationship_type=RelationshipType.IMPORT,
                line_number=2,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="B",
                target_file="D",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="C",
                target_file="D",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )

        deps = graph.get_transitive_dependencies("A")

        assert deps == {"B", "C", "D"}

    def test_get_direct_dependents(self):
        """Test getting direct dependents."""
        graph = RelationshipGraph()

        # Multiple files depend on B
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="C",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="D",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )

        dependents = graph.get_direct_dependents("B")

        assert dependents == {"A", "C", "D"}

    def test_store_pending_relationships(self):
        """Test storing relationships before removal."""
        graph = RelationshipGraph()

        rel1 = Relationship(
            source_file="A",
            target_file="B",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="A",
            target_file="C",
            relationship_type=RelationshipType.IMPORT,
            line_number=2,
        )
        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        stored = graph.store_pending_relationships("A")

        assert len(stored) == 2
        assert rel1 in stored
        assert rel2 in stored

    def test_remove_outgoing_relationships(self):
        """Test removing only outgoing relationships."""
        graph = RelationshipGraph()

        # A -> B, A -> C, X -> A
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="C",
                relationship_type=RelationshipType.IMPORT,
                line_number=2,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="X",
                target_file="A",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )

        removed = graph.remove_outgoing_relationships("A")

        # Should remove A -> B and A -> C but keep X -> A
        assert len(removed) == 2
        assert len(graph.get_dependencies("A")) == 0
        assert len(graph.get_dependents("A")) == 1  # X -> A still exists

    def test_restore_pending_relationships(self):
        """Test restoring previously stored relationships."""
        graph = RelationshipGraph()

        rel1 = Relationship(
            source_file="A",
            target_file="B",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="A",
            target_file="C",
            relationship_type=RelationshipType.IMPORT,
            line_number=2,
        )

        # Store, remove, then restore
        graph.add_relationship(rel1)
        graph.add_relationship(rel2)
        stored = graph.store_pending_relationships("A")
        graph.remove_outgoing_relationships("A")

        assert len(graph.get_dependencies("A")) == 0

        graph.restore_pending_relationships(stored)

        assert len(graph.get_dependencies("A")) == 2

    def test_mark_and_clear_pending_relationships(self):
        """Test marking and clearing pending_relationships flag."""
        graph = RelationshipGraph()

        metadata = _create_metadata("/path/to/file.py")
        graph.set_file_metadata("/path/to/file.py", metadata)

        # Initially not pending
        assert not graph.get_file_metadata("/path/to/file.py").pending_relationships

        # Mark as pending
        graph.mark_file_pending_relationships("/path/to/file.py")
        assert graph.get_file_metadata("/path/to/file.py").pending_relationships

        # Clear pending
        graph.clear_pending_relationships("/path/to/file.py")
        assert not graph.get_file_metadata("/path/to/file.py").pending_relationships

    def test_get_files_with_pending_relationships(self):
        """Test getting all files with pending relationships."""
        graph = RelationshipGraph()

        # Set up metadata
        for f in ["A", "B", "C"]:
            graph.set_file_metadata(f, _create_metadata(f))

        # Mark A and C as pending
        graph.mark_file_pending_relationships("A")
        graph.mark_file_pending_relationships("C")

        pending = graph.get_files_with_pending_relationships()

        assert set(pending) == {"A", "C"}


class TestStalenessResolverBasic:
    """Basic tests for StalenessResolver."""

    def test_no_staleness(self):
        """Test resolver when no files are stale."""
        graph = RelationshipGraph()

        # A -> B
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.set_file_metadata("A", _create_metadata("A", stale=False))
        graph.set_file_metadata("B", _create_metadata("B", stale=False))

        analyzed_files: List[str] = []

        def needs_analysis(path: str) -> bool:
            meta = graph.get_file_metadata(path)
            return meta is None or meta.last_analyzed < time.time()

        def analyze_file(path: str) -> bool:
            analyzed_files.append(path)
            return True

        resolver = StalenessResolver(graph, needs_analysis, analyze_file)
        resolver.resolve_staleness("A")

        # No files should be analyzed
        assert len(analyzed_files) == 0

    def test_target_file_stale(self):
        """Test resolver when only target file is stale."""
        graph = RelationshipGraph()

        # A -> B
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.set_file_metadata("A", _create_metadata("A", stale=True))
        graph.set_file_metadata("B", _create_metadata("B", stale=False))

        analyzed_files: List[str] = []

        def needs_analysis(path: str) -> bool:
            meta = graph.get_file_metadata(path)
            if meta is None:
                return True
            return meta.last_analyzed < time.time()

        def analyze_file(path: str) -> bool:
            analyzed_files.append(path)
            # Update metadata to mark as analyzed
            graph.set_file_metadata(path, _create_metadata(path, stale=False))
            return True

        resolver = StalenessResolver(graph, needs_analysis, analyze_file)
        resolver.resolve_staleness("A")

        # Only A should be analyzed
        assert analyzed_files == ["A"]

    def test_dependency_file_stale(self):
        """Test resolver when a dependency is stale."""
        graph = RelationshipGraph()

        # A -> B, B is stale
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.set_file_metadata("A", _create_metadata("A", stale=False))
        graph.set_file_metadata("B", _create_metadata("B", stale=True))

        analyzed_files: List[str] = []

        def needs_analysis(path: str) -> bool:
            meta = graph.get_file_metadata(path)
            if meta is None:
                return True
            return meta.last_analyzed < time.time()

        def analyze_file(path: str) -> bool:
            analyzed_files.append(path)
            graph.set_file_metadata(path, _create_metadata(path, stale=False))
            return True

        resolver = StalenessResolver(graph, needs_analysis, analyze_file)
        resolver.resolve_staleness("A")

        # B should be analyzed (it's stale and a dependency of A)
        assert "B" in analyzed_files


class TestStalenessResolverTopologicalSort:
    """Tests for topological sort ordering in StalenessResolver."""

    def test_chain_ordering(self):
        """Test that dependencies are analyzed before dependents."""
        graph = RelationshipGraph()

        # Chain: A -> B -> C -> D (all stale)
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="B",
                target_file="C",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="C",
                target_file="D",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )

        for f in ["A", "B", "C", "D"]:
            graph.set_file_metadata(f, _create_metadata(f, stale=True))

        analyzed_files: List[str] = []

        def needs_analysis(path: str) -> bool:
            meta = graph.get_file_metadata(path)
            if meta is None:
                return True
            return meta.last_analyzed < time.time()

        def analyze_file(path: str) -> bool:
            analyzed_files.append(path)
            graph.set_file_metadata(path, _create_metadata(path, stale=False))
            return True

        resolver = StalenessResolver(graph, needs_analysis, analyze_file)
        resolver.resolve_staleness("A")

        # D should be first (no stale dependencies)
        # C should be before B
        # B should be before A
        # Order should be: D, C, B, A
        assert analyzed_files.index("D") < analyzed_files.index("C")
        assert analyzed_files.index("C") < analyzed_files.index("B")
        assert analyzed_files.index("B") < analyzed_files.index("A")

    def test_partial_staleness_ordering(self):
        """Test ordering when only some files in chain are stale."""
        graph = RelationshipGraph()

        # Chain: A -> B -> C (A and C stale, B not stale)
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="B",
                target_file="C",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )

        graph.set_file_metadata("A", _create_metadata("A", stale=True))
        graph.set_file_metadata("B", _create_metadata("B", stale=False))
        graph.set_file_metadata("C", _create_metadata("C", stale=True))

        analyzed_files: List[str] = []

        def needs_analysis(path: str) -> bool:
            meta = graph.get_file_metadata(path)
            if meta is None:
                return True
            return meta.last_analyzed < time.time()

        def analyze_file(path: str) -> bool:
            analyzed_files.append(path)
            graph.set_file_metadata(path, _create_metadata(path, stale=False))
            return True

        resolver = StalenessResolver(graph, needs_analysis, analyze_file)
        resolver.resolve_staleness("A")

        # C should be analyzed before A (C is a transitive dependency)
        assert "C" in analyzed_files
        assert "A" in analyzed_files
        assert analyzed_files.index("C") < analyzed_files.index("A")
        # B should not be analyzed (not stale)
        assert "B" not in analyzed_files


class TestStalenessResolverDiamondPattern:
    """Tests for diamond pattern handling."""

    def test_diamond_all_stale(self):
        """Test diamond pattern with all files stale."""
        graph = RelationshipGraph()

        # Diamond: A -> B, A -> C, B -> D, C -> D
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="C",
                relationship_type=RelationshipType.IMPORT,
                line_number=2,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="B",
                target_file="D",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="C",
                target_file="D",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )

        for f in ["A", "B", "C", "D"]:
            graph.set_file_metadata(f, _create_metadata(f, stale=True))

        analyzed_files: List[str] = []

        def needs_analysis(path: str) -> bool:
            meta = graph.get_file_metadata(path)
            if meta is None:
                return True
            return meta.last_analyzed < time.time()

        def analyze_file(path: str) -> bool:
            analyzed_files.append(path)
            graph.set_file_metadata(path, _create_metadata(path, stale=False))
            return True

        resolver = StalenessResolver(graph, needs_analysis, analyze_file)
        resolver.resolve_staleness("A")

        # D should be first (no dependencies)
        # B and C should be before A
        # A should be last
        assert analyzed_files[0] == "D"
        assert analyzed_files[-1] == "A"
        assert analyzed_files.index("B") < analyzed_files.index("A")
        assert analyzed_files.index("C") < analyzed_files.index("A")

    def test_diamond_partial_stale(self):
        """Test diamond pattern with partial staleness."""
        graph = RelationshipGraph()

        # Diamond: A -> B, A -> C, B -> D, C -> D
        # Only A and D are stale
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="B",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="C",
                relationship_type=RelationshipType.IMPORT,
                line_number=2,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="B",
                target_file="D",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.add_relationship(
            Relationship(
                source_file="C",
                target_file="D",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )

        graph.set_file_metadata("A", _create_metadata("A", stale=True))
        graph.set_file_metadata("B", _create_metadata("B", stale=False))
        graph.set_file_metadata("C", _create_metadata("C", stale=False))
        graph.set_file_metadata("D", _create_metadata("D", stale=True))

        analyzed_files: List[str] = []

        def needs_analysis(path: str) -> bool:
            meta = graph.get_file_metadata(path)
            if meta is None:
                return True
            return meta.last_analyzed < time.time()

        def analyze_file(path: str) -> bool:
            analyzed_files.append(path)
            graph.set_file_metadata(path, _create_metadata(path, stale=False))
            return True

        resolver = StalenessResolver(graph, needs_analysis, analyze_file)
        resolver.resolve_staleness("A")

        # Only A and D should be analyzed
        # D should be before A (transitive dependency)
        assert set(analyzed_files) == {"A", "D"}
        assert analyzed_files.index("D") < analyzed_files.index("A")


class TestStalenessResolverSkipsSpecialMarkers:
    """Tests that special marker paths are skipped."""

    def test_skips_stdlib_marker(self):
        """Test that <stdlib:...> markers are skipped."""
        graph = RelationshipGraph()

        # A -> <stdlib:os>
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="<stdlib:os>",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.set_file_metadata("A", _create_metadata("A", stale=True))

        analyzed_files: List[str] = []

        def needs_analysis(path: str) -> bool:
            if path.startswith("<") and path.endswith(">"):
                return False
            meta = graph.get_file_metadata(path)
            if meta is None:
                return True
            return meta.last_analyzed < time.time()

        def analyze_file(path: str) -> bool:
            analyzed_files.append(path)
            graph.set_file_metadata(path, _create_metadata(path, stale=False))
            return True

        resolver = StalenessResolver(graph, needs_analysis, analyze_file)
        resolver.resolve_staleness("A")

        # Only A should be analyzed, not the stdlib marker
        assert analyzed_files == ["A"]

    def test_skips_third_party_marker(self):
        """Test that <third-party:...> markers are skipped."""
        graph = RelationshipGraph()

        # A -> <third-party:requests>
        graph.add_relationship(
            Relationship(
                source_file="A",
                target_file="<third-party:requests>",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
        )
        graph.set_file_metadata("A", _create_metadata("A", stale=True))

        analyzed_files: List[str] = []

        def needs_analysis(path: str) -> bool:
            if path.startswith("<") and path.endswith(">"):
                return False
            meta = graph.get_file_metadata(path)
            if meta is None:
                return True
            return meta.last_analyzed < time.time()

        def analyze_file(path: str) -> bool:
            analyzed_files.append(path)
            graph.set_file_metadata(path, _create_metadata(path, stale=False))
            return True

        resolver = StalenessResolver(graph, needs_analysis, analyze_file)
        resolver.resolve_staleness("A")

        # Only A should be analyzed
        assert analyzed_files == ["A"]


class TestFileMetadataPendingRelationships:
    """Tests for pending_relationships field in FileMetadata."""

    def test_default_value(self):
        """Test that pending_relationships defaults to False."""
        metadata = FileMetadata(
            filepath="/test.py",
            last_analyzed=time.time(),
            relationship_count=0,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )

        assert metadata.pending_relationships is False

    def test_to_dict_excludes_false(self):
        """Test that to_dict excludes pending_relationships when False."""
        metadata = FileMetadata(
            filepath="/test.py",
            last_analyzed=time.time(),
            relationship_count=0,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
            pending_relationships=False,
        )

        d = metadata.to_dict()

        assert "pending_relationships" not in d

    def test_to_dict_includes_true(self):
        """Test that to_dict includes pending_relationships when True."""
        metadata = FileMetadata(
            filepath="/test.py",
            last_analyzed=time.time(),
            relationship_count=0,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
            pending_relationships=True,
        )

        d = metadata.to_dict()

        assert d["pending_relationships"] is True

    def test_from_dict_with_pending_relationships(self):
        """Test that from_dict handles pending_relationships."""
        d = {
            "filepath": "/test.py",
            "last_analyzed": time.time(),
            "relationship_count": 0,
            "has_dynamic_patterns": False,
            "dynamic_pattern_types": [],
            "is_unparseable": False,
            "pending_relationships": True,
        }

        metadata = FileMetadata.from_dict(d)

        assert metadata.pending_relationships is True

    def test_from_dict_backward_compatible(self):
        """Test that from_dict handles missing pending_relationships."""
        d = {
            "filepath": "/test.py",
            "last_analyzed": time.time(),
            "relationship_count": 0,
            "has_dynamic_patterns": False,
            "dynamic_pattern_types": [],
            "is_unparseable": False,
        }

        metadata = FileMetadata.from_dict(d)

        assert metadata.pending_relationships is False
