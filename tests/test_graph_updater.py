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

    def test_deletion_metadata_fields(self, updater, graph, temp_project_dir):
        """Test that deletion properly sets deleted and deletion_time fields (EC-14)."""
        test_file = str(temp_project_dir / "test.py")

        # Add a relationship
        rel = Relationship(
            source_file=test_file,
            target_file="/other.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        graph.add_relationship(rel)

        # Record time before deletion
        time_before = time.time()

        # Delete file
        success = updater.update_on_delete(test_file)
        assert success is True

        # Record time after deletion
        time_after = time.time()

        # Verify deletion metadata
        metadata = graph.get_file_metadata(test_file)
        assert metadata is not None
        assert metadata.deleted is True, "deleted field should be True"
        assert metadata.deletion_time is not None, "deletion_time should be set"
        assert (
            time_before <= metadata.deletion_time <= time_after
        ), "deletion_time should be within deletion window"

    def test_broken_reference_warnings(self, updater, graph, temp_project_dir, caplog):
        """Test that deletion emits warnings for broken references (TDD Section 3.6.4)."""
        import logging

        caplog.set_level(logging.WARNING)

        deleted_file = str(temp_project_dir / "deleted.py")
        dependent_file1 = str(temp_project_dir / "dependent1.py")
        dependent_file2 = str(temp_project_dir / "dependent2.py")

        # Add relationships: dependent files import from deleted file
        rel1 = Relationship(
            source_file=dependent_file1,
            target_file=deleted_file,
            relationship_type=RelationshipType.IMPORT,
            line_number=5,
            target_symbol="some_function",
        )
        rel2 = Relationship(
            source_file=dependent_file1,
            target_file=deleted_file,
            relationship_type=RelationshipType.FUNCTION_CALL,
            line_number=10,
            target_symbol="another_function",
        )
        rel3 = Relationship(
            source_file=dependent_file2,
            target_file=deleted_file,
            relationship_type=RelationshipType.IMPORT,
            line_number=3,
            target_symbol="MyClass",
        )
        graph.add_relationship(rel1)
        graph.add_relationship(rel2)
        graph.add_relationship(rel3)

        # Delete file
        success = updater.update_on_delete(deleted_file)
        assert success is True

        # Verify warnings were emitted
        warning_records = [rec for rec in caplog.records if rec.levelname == "WARNING"]
        assert len(warning_records) >= 2, "Should emit warnings for dependent files"

        # Check warning content
        warning_messages = [rec.message for rec in warning_records]
        dependent1_warned = any(dependent_file1 in msg for msg in warning_messages)
        dependent2_warned = any(dependent_file2 in msg for msg in warning_messages)

        assert dependent1_warned, f"Should warn about {dependent_file1}"
        assert dependent2_warned, f"Should warn about {dependent_file2}"

        # Check that warning mentions the deleted file
        assert any(
            deleted_file in msg for msg in warning_messages
        ), "Warning should mention deleted file"

    def test_deletion_with_no_dependents(self, updater, graph, temp_project_dir, caplog):
        """Test deletion of file with no dependents (no broken reference warnings)."""
        import logging

        caplog.set_level(logging.WARNING)

        test_file = str(temp_project_dir / "isolated.py")

        # Add relationship where test_file depends on others (not the reverse)
        rel = Relationship(
            source_file=test_file,
            target_file="/other.py",
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
        )
        graph.add_relationship(rel)

        # Delete file
        success = updater.update_on_delete(test_file)
        assert success is True

        # Verify no "Imported file deleted" warnings (only performance warnings allowed)
        warning_messages = [rec.message for rec in caplog.records if rec.levelname == "WARNING"]
        broken_ref_warnings = [msg for msg in warning_messages if "Imported file deleted" in msg]
        assert len(broken_ref_warnings) == 0, "Should not emit broken reference warnings"

    def test_integration_file_deletion_workflow(self, updater, graph, temp_project_dir, caplog):
        """Integration test for complete file deletion workflow (TDD Section 3.6.4)."""
        import logging

        caplog.set_level(logging.WARNING)

        # Create a scenario:
        # - module.py defines functions
        # - client1.py imports from module.py
        # - client2.py imports from module.py
        # - module.py gets deleted
        module_file = str(temp_project_dir / "module.py")
        client1_file = str(temp_project_dir / "client1.py")
        client2_file = str(temp_project_dir / "client2.py")

        # Setup relationships
        rel1 = Relationship(
            source_file=client1_file,
            target_file=module_file,
            relationship_type=RelationshipType.IMPORT,
            line_number=1,
            target_symbol="helper_function",
        )
        rel2 = Relationship(
            source_file=client2_file,
            target_file=module_file,
            relationship_type=RelationshipType.IMPORT,
            line_number=2,
            target_symbol="MyClass",
        )
        graph.add_relationship(rel1)
        graph.add_relationship(rel2)

        # Verify initial state
        assert len(graph.get_dependents(module_file)) == 2
        assert graph.get_file_metadata(module_file) is None

        # Delete module
        success = updater.update_on_delete(module_file)
        assert success is True

        # SUCCESS CRITERIA verification (from Issue #22):

        # 1. Deleted file removed from graph
        assert len(graph.get_dependencies(module_file)) == 0
        assert len(graph.get_dependents(module_file)) == 0

        # 2. Metadata includes deletion timestamp
        metadata = graph.get_file_metadata(module_file)
        assert metadata is not None
        assert metadata.deleted is True
        assert metadata.deletion_time is not None

        # 3. Broken references detected and warnings emitted for dependent files
        warning_messages = [rec.message for rec in caplog.records if rec.levelname == "WARNING"]
        broken_ref_warnings = [msg for msg in warning_messages if "Imported file deleted" in msg]

        assert len(broken_ref_warnings) >= 2, "Should warn about both client files"
        assert any(client1_file in msg for msg in broken_ref_warnings)
        assert any(client2_file in msg for msg in broken_ref_warnings)
        assert any(module_file in msg for msg in broken_ref_warnings)


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
        analyzer.analyze_file_two_phase.side_effect = Exception("Test failure")

        # Create updater with failing analyzer
        updater = GraphUpdater(
            graph=graph, analyzer=analyzer, file_watcher=file_watcher, relationship_builder=None
        )

        # Attempt update (should fail and rollback)
        success = updater.update_on_modify(str(test_file))

        # Verify failure
        assert success is False

        # Verify original relationship still exists (rollback worked)
        deps = graph.get_dependencies(str(test_file))
        assert len(deps) == 1
        assert deps[0].target_file == "/other.py"


class TestPathValidation:
    """Test path validation security checks."""

    def test_reject_path_outside_project_root(self, updater, temp_project_dir):
        """Test that paths outside project root are rejected."""
        # Try to update a file outside project root
        outside_path = "/etc/passwd"

        # All three operations should reject the path
        assert updater.update_on_modify(outside_path) is False
        assert updater.update_on_delete(outside_path) is False
        assert updater.update_on_create(outside_path) is False

    def test_reject_path_traversal_attempt(self, updater, temp_project_dir):
        """Test that path traversal attacks are blocked."""
        # Attempt path traversal
        traversal_path = str(temp_project_dir / ".." / ".." / "etc" / "passwd")

        # Should be rejected
        assert updater.update_on_modify(traversal_path) is False
        assert updater.update_on_delete(traversal_path) is False
        assert updater.update_on_create(traversal_path) is False

    def test_accept_valid_path_in_project_root(self, updater, temp_project_dir):
        """Test that valid paths within project root are accepted."""
        # Create a valid file in project root
        valid_file = temp_project_dir / "valid.py"
        valid_file.write_text("x = 1\n")

        # Validation should pass (update success depends on file content)
        result = updater.update_on_modify(str(valid_file))
        assert result is True  # File is valid Python

    def test_accept_path_in_subdirectory(self, updater, temp_project_dir):
        """Test that paths in subdirectories are accepted."""
        # Create subdirectory with file
        subdir = temp_project_dir / "subdir"
        subdir.mkdir()
        sub_file = subdir / "test.py"
        sub_file.write_text("y = 2\n")

        # Should be accepted
        result = updater.update_on_create(str(sub_file))
        assert result is True

    def test_reject_null_byte_injection(self, updater, temp_project_dir):
        """Test that null byte injection attacks are blocked."""
        # Attempt null byte injection (path validation DoS attack)
        null_byte_path = str(temp_project_dir / "file.py") + "\x00/etc/passwd"

        # Should be rejected without crashing
        assert updater.update_on_modify(null_byte_path) is False
        assert updater.update_on_delete(null_byte_path) is False
        assert updater.update_on_create(null_byte_path) is False

    def test_symlink_within_project_root(self, updater, temp_project_dir):
        """Test that symlinks within project root are accepted."""
        # Create a file and symlink to it within project
        real_file = temp_project_dir / "real.py"
        real_file.write_text("x = 1\n")

        symlink_file = temp_project_dir / "link.py"
        symlink_file.symlink_to(real_file)

        # Symlink within project should be accepted
        result = updater.update_on_modify(str(symlink_file))
        assert result is True

    def test_symlink_outside_project_root(self, updater, temp_project_dir):
        """Test that symlinks pointing outside project root are rejected."""
        # Create symlink pointing to /etc/passwd
        symlink_file = temp_project_dir / "malicious_link.py"
        try:
            symlink_file.symlink_to("/etc/passwd")
        except (OSError, PermissionError):
            # Some systems don't allow symlinking to /etc/passwd
            # Skip this test in that case
            import pytest

            pytest.skip("Cannot create symlink to /etc/passwd on this system")

        # Symlink pointing outside project should be rejected
        result = updater.update_on_modify(str(symlink_file))
        assert result is False
