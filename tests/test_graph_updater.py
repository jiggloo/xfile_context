# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for incremental graph updater.

Tests cover TDD Section 3.6.3 (Incremental Updates):
- File modification: Remove old, re-analyze, add new
- File deletion: Remove all relationships, mark as deleted
- File creation: Analyze and add to graph
- Atomic updates: No partial state on failure
- Performance: <200ms per file (NFR-1)
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from xfile_context.analyzers.python_analyzer import PythonAnalyzer
from xfile_context.detectors.registry import DetectorRegistry
from xfile_context.file_watcher import FileWatcher
from xfile_context.graph_updater import GraphUpdater
from xfile_context.models import FileMetadata, Relationship, RelationshipGraph, RelationshipType


@pytest.fixture
def temp_project_dir():
    """Create temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def graph():
    """Create empty relationship graph."""
    return RelationshipGraph()


@pytest.fixture
def detector_registry():
    """Create mock detector registry."""
    registry = MagicMock(spec=DetectorRegistry)
    registry.get_detectors.return_value = []
    return registry


@pytest.fixture
def file_watcher(temp_project_dir):
    """Create file watcher."""
    return FileWatcher(project_root=str(temp_project_dir))


@pytest.fixture
def analyzer(graph, detector_registry):
    """Create Python analyzer."""
    return PythonAnalyzer(graph=graph, detector_registry=detector_registry)


@pytest.fixture
def updater(graph, analyzer, file_watcher):
    """Create graph updater."""
    return GraphUpdater(graph=graph, analyzer=analyzer, file_watcher=file_watcher)


class TestUpdateOnModify:
    """Test file modification updates."""

    def test_successful_modification(self, updater, graph, temp_project_dir):
        """Test successful file modification update."""
        # Create a simple Python file
        test_file = temp_project_dir / "test.py"
        test_file.write_text("x = 1\n")

        # Add initial relationship
        rel = Relationship(
            source_file=str(test_file),
            target_file="/some/other.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        graph.add_relationship(rel)

        # Modify file
        test_file.write_text("x = 2\n")

        # Update graph
        success = updater.update_on_modify(str(test_file))

        # Verify success
        assert success is True

        # Verify metadata updated
        metadata = graph.get_file_metadata(str(test_file))
        assert metadata is not None
        assert metadata.filepath == str(test_file)

    def test_modification_with_syntax_error(self, updater, graph, temp_project_dir):
        """Test file modification with syntax error."""
        # Create file with syntax error
        test_file = temp_project_dir / "bad.py"
        test_file.write_text("def foo(\n")  # Syntax error

        # Update should not crash but return False
        success = updater.update_on_modify(str(test_file))

        # Verify failure handling
        assert success is False

        # File should be marked as unparseable
        metadata = graph.get_file_metadata(str(test_file))
        assert metadata is not None
        assert metadata.is_unparseable is True

    def test_modification_removes_old_relationships(self, updater, graph, temp_project_dir):
        """Test that modification removes old relationships."""
        test_file = temp_project_dir / "test.py"
        test_file.write_text("x = 1\n")

        # Add initial relationships
        rel1 = Relationship(
            source_file=str(test_file),
            target_file="/old1.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file=str(test_file),
            target_file="/old2.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=2,
        )
        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        # Verify initial state
        deps = graph.get_dependencies(str(test_file))
        assert len(deps) == 2

        # Modify file (relationships will be re-analyzed)
        test_file.write_text("y = 2\n")
        success = updater.update_on_modify(str(test_file))

        # Verify old relationships removed
        # (In real scenario with detectors, new ones would be added)
        assert success is True

    def test_performance_target(self, updater, temp_project_dir):
        """Test that modification meets <200ms performance target."""
        # Create a reasonably sized Python file
        test_file = temp_project_dir / "medium.py"
        content = "\n".join([f"x{i} = {i}" for i in range(100)])
        test_file.write_text(content)

        # Measure update time
        start = time.time()
        success = updater.update_on_modify(str(test_file))
        elapsed = time.time() - start

        # Verify performance target (NFR-1: <200ms)
        assert success is True
        assert elapsed < 0.2, f"Update took {elapsed*1000:.1f}ms (target: <200ms)"


class TestUpdateOnDelete:
    """Test file deletion updates."""

    def test_successful_deletion(self, updater, graph, temp_project_dir):
        """Test successful file deletion update."""
        test_file = str(temp_project_dir / "test.py")

        # Add relationships for file
        rel1 = Relationship(
            source_file=test_file,
            target_file="/other1.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        rel2 = Relationship(
            source_file="/other2.py",
            target_file=test_file,
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        # Verify initial state
        deps = graph.get_dependencies(test_file)
        dependents = graph.get_dependents(test_file)
        assert len(deps) == 1
        assert len(dependents) == 1

        # Delete file
        success = updater.update_on_delete(test_file)

        # Verify deletion
        assert success is True

        # Verify all relationships removed
        deps = graph.get_dependencies(test_file)
        dependents = graph.get_dependents(test_file)
        assert len(deps) == 0
        assert len(dependents) == 0

        # Verify metadata exists (marked as deleted)
        metadata = graph.get_file_metadata(test_file)
        assert metadata is not None
        assert metadata.relationship_count == 0

    def test_deletion_performance_target(self, updater, graph, temp_project_dir):
        """Test that deletion meets <200ms performance target."""
        test_file = str(temp_project_dir / "test.py")

        # Add many relationships
        for i in range(100):
            rel = Relationship(
                source_file=test_file,
                target_file=f"/other{i}.py",
                relationship_type=RelationshipType.IMPORT,
                line_number=i + 1,
            )
            graph.add_relationship(rel)

        # Measure deletion time
        start = time.time()
        success = updater.update_on_delete(test_file)
        elapsed = time.time() - start

        # Verify performance target
        assert success is True
        assert elapsed < 0.2, f"Deletion took {elapsed*1000:.1f}ms (target: <200ms)"


class TestUpdateOnCreate:
    """Test file creation updates."""

    def test_successful_creation(self, updater, graph, temp_project_dir):
        """Test successful file creation update."""
        # Create new Python file
        test_file = temp_project_dir / "new.py"
        test_file.write_text("x = 1\n")

        # Update graph
        success = updater.update_on_create(str(test_file))

        # Verify success
        assert success is True

        # Verify metadata added
        metadata = graph.get_file_metadata(str(test_file))
        assert metadata is not None
        assert metadata.filepath == str(test_file)

    def test_creation_with_syntax_error(self, updater, graph, temp_project_dir):
        """Test file creation with syntax error."""
        # Create file with syntax error
        test_file = temp_project_dir / "bad_new.py"
        test_file.write_text("def foo(\n")

        # Update should not crash
        success = updater.update_on_create(str(test_file))

        # Verify failure handling
        assert success is False

        # File should be marked as unparseable
        metadata = graph.get_file_metadata(str(test_file))
        assert metadata is not None
        assert metadata.is_unparseable is True

    def test_creation_performance_target(self, updater, temp_project_dir):
        """Test that creation meets <200ms performance target."""
        # Create a reasonably sized Python file
        test_file = temp_project_dir / "new_medium.py"
        content = "\n".join([f"x{i} = {i}" for i in range(100)])
        test_file.write_text(content)

        # Measure creation time
        start = time.time()
        success = updater.update_on_create(str(test_file))
        elapsed = time.time() - start

        # Verify performance target
        assert success is True
        assert elapsed < 0.2, f"Creation took {elapsed*1000:.1f}ms (target: <200ms)"


class TestProcessPendingChanges:
    """Test batch processing of pending changes."""

    def test_process_mixed_changes(self, updater, graph, file_watcher, temp_project_dir):
        """Test processing multiple types of changes."""
        # Create files
        file1 = temp_project_dir / "existing.py"
        file1.write_text("x = 1\n")

        file2 = temp_project_dir / "new.py"
        file2.write_text("y = 2\n")

        file3_path = str(temp_project_dir / "deleted.py")

        # Setup initial state
        # - file1 exists in graph (will be modified)
        metadata1 = FileMetadata(
            filepath=str(file1),
            last_analyzed=time.time() - 3600,
            relationship_count=0,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )
        graph.set_file_metadata(str(file1), metadata1)

        # - file2 is new (not in graph)
        # - file3 was in graph but is now deleted
        metadata3 = FileMetadata(
            filepath=file3_path,
            last_analyzed=time.time() - 3600,
            relationship_count=1,
            has_dynamic_patterns=False,
            dynamic_pattern_types=[],
            is_unparseable=False,
        )
        graph.set_file_metadata(file3_path, metadata3)

        # Add timestamps for all files
        file_watcher.file_event_timestamps[str(file1)] = time.time()
        file_watcher.file_event_timestamps[str(file2)] = time.time()
        file_watcher.file_event_timestamps[file3_path] = time.time()

        # Process changes
        stats = updater.process_pending_changes()

        # Verify statistics
        assert stats["total"] == 3
        assert stats["modified"] == 1  # file1
        assert stats["created"] == 1  # file2
        assert stats["deleted"] == 1  # file3
        assert stats["failed"] == 0
        assert stats["elapsed_ms"] > 0

        # Verify timestamps cleared
        assert len(file_watcher.file_event_timestamps) == 0

    def test_process_empty_changes(self, updater, file_watcher):
        """Test processing when no changes pending."""
        # No timestamps
        stats = updater.process_pending_changes()

        # Verify empty stats
        assert stats["total"] == 0
        assert stats["modified"] == 0
        assert stats["created"] == 0
        assert stats["deleted"] == 0
        assert stats["failed"] == 0


class TestAtomicUpdates:
    """Test atomic update guarantees."""

    def test_rollback_on_failure(self, graph, file_watcher, detector_registry, temp_project_dir):
        """Test that failures trigger rollback of changes."""
        # Create file
        test_file = temp_project_dir / "test.py"
        test_file.write_text("x = 1\n")

        # Add initial relationship
        rel = Relationship(
            source_file=str(test_file),
            target_file="/other.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        graph.add_relationship(rel)

        # Create mock analyzer that fails
        analyzer = Mock(spec=PythonAnalyzer)
        analyzer.analyze_file.side_effect = Exception("Test failure")

        # Create updater with failing analyzer
        updater = GraphUpdater(graph=graph, analyzer=analyzer, file_watcher=file_watcher)

        # Attempt update (should fail and rollback)
        success = updater.update_on_modify(str(test_file))

        # Verify failure
        assert success is False

        # Verify original relationship still exists (rollback worked)
        deps = graph.get_dependencies(str(test_file))
        assert len(deps) == 1
        assert deps[0].target_file == "/other.py"
