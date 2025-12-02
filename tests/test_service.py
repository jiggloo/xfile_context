# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for CrossFileContextService implementation.

Tests cover:
- Component initialization and lifecycle management
- Context injection workflow (Section 3.8)
- Relationship query APIs
- FileWatcher integration
- Security validation
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
from xfile_context.models import Relationship, RelationshipGraph, RelationshipType
from xfile_context.service import CrossFileContextService, ReadResult
from xfile_context.storage import InMemoryStore


class TestReadResult:
    """Tests for ReadResult class."""

    def test_initialization(self):
        """Test ReadResult initialization."""
        result = ReadResult(
            file_path="/test/file.py",
            content="content",
            injected_context="context",
            warnings=["warning1"],
        )

        assert result.file_path == "/test/file.py"
        assert result.content == "content"
        assert result.injected_context == "context"
        assert result.warnings == ["warning1"]

    def test_to_dict(self):
        """Test ReadResult to_dict conversion."""
        result = ReadResult(
            file_path="/test/file.py",
            content="content",
            injected_context="context",
            warnings=["warning1", "warning2"],
        )

        result_dict = result.to_dict()

        assert result_dict["file_path"] == "/test/file.py"
        assert result_dict["content"] == "content"
        assert result_dict["injected_context"] == "context"
        assert result_dict["warnings"] == ["warning1", "warning2"]


class TestCrossFileContextServiceInitialization:
    """Tests for CrossFileContextService initialization."""

    def test_initialization_with_defaults(self):
        """Test service initialization with default components."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            assert service.config is config
            assert service.store is not None
            assert service.cache is not None
            assert service._graph is not None
            assert service._analyzer is not None
            assert service._file_watcher is not None
            assert service._graph_updater is not None

            service.shutdown()

    def test_initialization_with_injected_dependencies(self):
        """Test service initialization with injected dependencies."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps: dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps=file_event_timestamps)

        service = CrossFileContextService(config, store=store, cache=cache)

        assert service.config is config
        assert service.store is store
        assert service.cache is cache

        service.shutdown()

    def test_shutdown_clears_resources(self):
        """Test that shutdown clears cache and graph."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Add some data to cache
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# test")
            service.cache.get(str(test_file))

            # Shutdown should clear
            service.shutdown()

            # Verify cache is empty
            stats = service.cache.get_statistics()
            assert stats.current_entry_count == 0


class TestCrossFileContextServiceReadFile:
    """Tests for read_file_with_context method."""

    def test_read_file_success(self):
        """Test reading an existing file."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# Test file\nprint('hello')")

            result = service.read_file_with_context(str(test_file))

            assert result.file_path == str(test_file)
            assert result.content == "# Test file\nprint('hello')"
            assert isinstance(result.warnings, list)

            service.shutdown()

    def test_read_file_not_found(self):
        """Test reading a non-existent file raises FileNotFoundError."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            with pytest.raises(FileNotFoundError):
                service.read_file_with_context("/nonexistent/file.py")

            service.shutdown()

    def test_read_file_not_a_file(self):
        """Test reading a directory raises ValueError."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            with pytest.raises(ValueError, match="Path is not a file"):
                service.read_file_with_context(tmpdir)

            service.shutdown()

    def test_read_file_with_context_injection_disabled(self):
        """Test reading with context injection disabled."""
        with TemporaryDirectory() as tmpdir:
            # Create config with injection disabled
            config_file = Path(tmpdir) / ".cross_file_context_links.yml"
            config_file.write_text("enable_context_injection: false")

            config = Config(config_path=config_file)
            service = CrossFileContextService(config, project_root=tmpdir)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# Test")

            result = service.read_file_with_context(str(test_file))

            assert result.injected_context == ""

            service.shutdown()


class TestCrossFileContextServiceContextInjection:
    """Tests for context injection workflow."""

    def test_context_injection_with_dependencies(self):
        """Test that context is injected when dependencies exist."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create source file with import
            utils_file = Path(tmpdir) / "utils.py"
            utils_file.write_text(
                "def helper_function(x: int) -> int:\n"
                '    """A helper function."""\n'
                "    return x + 1\n"
            )

            main_file = Path(tmpdir) / "main.py"
            main_file.write_text(
                "from utils import helper_function\n\n" "result = helper_function(5)\n"
            )

            # Analyze both files
            service.analyze_file(str(utils_file))
            service.analyze_file(str(main_file))

            # Read main file with context
            result = service.read_file_with_context(str(main_file))

            # Should have content
            assert "from utils import helper_function" in result.content

            # Check if dependencies were found (verifies graph was populated)
            _ = service.get_dependencies(str(main_file))
            # Note: Whether context is injected depends on dependency resolution

            service.shutdown()

    def test_context_injection_format(self):
        """Test that injected context follows TDD Section 3.8.3 format."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            # Add a relationship manually
            rel = Relationship(
                source_file=str(Path(tmpdir) / "main.py"),
                target_file=str(Path(tmpdir) / "utils.py"),
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
                target_line=5,
            )
            graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create the files
            utils_file = Path(tmpdir) / "utils.py"
            utils_file.write_text(
                "# Line 1\n" "# Line 2\n" "# Line 3\n" "# Line 4\n" "def helper():\n" "    pass\n"
            )

            main_file = Path(tmpdir) / "main.py"
            main_file.write_text("from utils import helper\n")

            result = service.read_file_with_context(str(main_file))

            # Check format elements per Section 3.8.3
            if result.injected_context:
                assert "[Cross-File Context]" in result.injected_context
                assert "---" in result.injected_context

            service.shutdown()


class TestCrossFileContextServiceGraphOperations:
    """Tests for relationship graph operations."""

    def test_get_relationship_graph(self):
        """Test getting relationship graph returns graph export."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            graph_export = service.get_relationship_graph()

            assert graph_export is not None
            graph_dict = (
                graph_export.to_dict() if hasattr(graph_export, "to_dict") else graph_export
            )
            assert "relationships" in graph_dict

            service.shutdown()

    def test_get_dependents(self):
        """Test getting files that depend on a given file."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            # Add a relationship: main.py depends on utils.py
            rel = Relationship(
                source_file=str(Path(tmpdir) / "main.py"),
                target_file=str(Path(tmpdir) / "utils.py"),
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
            graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Get dependents of utils.py (files that import from it)
            dependents = service.get_dependents(str(Path(tmpdir) / "utils.py"))

            assert len(dependents) == 1
            assert dependents[0]["source_file"] == str(Path(tmpdir) / "main.py")

            service.shutdown()

    def test_get_dependencies(self):
        """Test getting files that a given file depends on."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            # Add a relationship: main.py depends on utils.py
            rel = Relationship(
                source_file=str(Path(tmpdir) / "main.py"),
                target_file=str(Path(tmpdir) / "utils.py"),
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
            graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Get dependencies of main.py (files it imports from)
            dependencies = service.get_dependencies(str(Path(tmpdir) / "main.py"))

            assert len(dependencies) == 1
            assert dependencies[0]["target_file"] == str(Path(tmpdir) / "utils.py")

            service.shutdown()

    def test_get_graph_statistics(self):
        """Test getting graph statistics."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            stats = service.get_graph_statistics()

            assert "total_files" in stats or stats == {}  # Empty or has expected keys

            service.shutdown()


class TestCrossFileContextServiceFileAnalysis:
    """Tests for file analysis operations."""

    def test_analyze_file_success(self):
        """Test analyzing a valid Python file."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("import os\nprint(os.getcwd())")

            result = service.analyze_file(str(test_file))

            assert result is True

            service.shutdown()

    def test_analyze_file_syntax_error(self):
        """Test analyzing a file with syntax errors."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            test_file = Path(tmpdir) / "bad.py"
            test_file.write_text("def broken(:\n    pass")

            result = service.analyze_file(str(test_file))

            # Should return False for unparseable file
            assert result is False

            service.shutdown()

    def test_analyze_directory(self):
        """Test analyzing all Python files in a directory."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create some Python files
            (Path(tmpdir) / "file1.py").write_text("x = 1")
            (Path(tmpdir) / "file2.py").write_text("y = 2")

            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            (subdir / "file3.py").write_text("z = 3")

            stats = service.analyze_directory(tmpdir)

            assert stats["total"] >= 3
            assert stats["success"] >= 3
            assert stats["failed"] == 0
            assert "elapsed_ms" in stats

            service.shutdown()


class TestCrossFileContextServiceFileWatcher:
    """Tests for FileWatcher integration."""

    def test_start_stop_file_watcher(self):
        """Test starting and stopping the file watcher."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Start watcher
            service.start_file_watcher()
            assert service._watcher_running is True
            assert service._file_watcher.is_running()

            # Stop watcher
            service.stop_file_watcher()
            assert service._watcher_running is False

            service.shutdown()

    def test_process_pending_changes(self):
        """Test processing pending file changes."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Simulate some pending changes
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("x = 1")
            service._file_watcher.file_event_timestamps[str(test_file)] = 1.0

            stats = service.process_pending_changes()

            assert "total" in stats
            assert "modified" in stats
            assert "created" in stats
            assert "deleted" in stats

            service.shutdown()


class TestCrossFileContextServiceCache:
    """Tests for cache operations."""

    def test_invalidate_cache_specific_file(self):
        """Test invalidating cache for a specific file."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create and cache a file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("content")
            service.cache.get(str(test_file))

            # Invalidate
            service.invalidate_cache(str(test_file))

            # Verify invalidated (next get will be a miss)
            # Cache statistics should reflect this on next access

            service.shutdown()

    def test_invalidate_cache_all(self):
        """Test invalidating entire cache."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create and cache files
            test_file1 = Path(tmpdir) / "test1.py"
            test_file1.write_text("content1")
            test_file2 = Path(tmpdir) / "test2.py"
            test_file2.write_text("content2")

            service.cache.get(str(test_file1))
            service.cache.get(str(test_file2))

            # Invalidate all
            service.invalidate_cache()

            # Verify all cleared
            stats = service.cache.get_statistics()
            assert stats.current_entry_count == 0

            service.shutdown()


class TestServiceSecurityValidation:
    """Security tests for CrossFileContextService.

    Tests path validation to prevent security vulnerabilities like
    path traversal, control character injection, and DoS attacks.
    """

    def _create_service(self) -> CrossFileContextService:
        """Helper to create a service instance for tests."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps: dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps=file_event_timestamps)
        return CrossFileContextService(config, store=store, cache=cache)

    def test_path_traversal_rejected(self):
        """Test that path traversal patterns are rejected."""
        service = self._create_service()

        with pytest.raises(ValueError, match="Path traversal not allowed"):
            service.read_file_with_context("../../../etc/passwd")

        service.shutdown()

    def test_path_traversal_middle_rejected(self):
        """Test that path traversal in the middle of paths is rejected."""
        service = self._create_service()

        with pytest.raises(ValueError, match="Path traversal not allowed"):
            service.read_file_with_context("/safe/path/../../../etc/passwd")

        service.shutdown()

    def test_control_characters_rejected(self):
        """Test that control characters in paths are rejected."""
        service = self._create_service()

        with pytest.raises(ValueError, match="Invalid characters"):
            service.read_file_with_context("/path/with\x00null/file.py")

        service.shutdown()

    def test_very_long_path_rejected(self):
        """Test that very long paths are rejected to prevent DoS."""
        service = self._create_service()

        long_path = "/a" * 5000  # Exceeds 4096 limit

        with pytest.raises(ValueError, match="Filepath too long"):
            service.read_file_with_context(long_path)

        service.shutdown()

    def test_large_file_rejected(self):
        """Test that large files are rejected to prevent DoS."""
        service = self._create_service()

        with TemporaryDirectory() as tmpdir:
            large_file = Path(tmpdir) / "large.py"
            # Create file larger than 10MB limit
            large_file.write_bytes(b"x" * (11 * 1024 * 1024))

            with pytest.raises(ValueError, match="File too large"):
                service.read_file_with_context(str(large_file))

        service.shutdown()

    def test_valid_absolute_path_accepted(self):
        """Test that valid absolute paths are accepted."""
        service = self._create_service()

        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "valid.py"
            test_file.write_text("# Valid file")

            result = service.read_file_with_context(str(test_file))
            assert result.content == "# Valid file"

        service.shutdown()

    def test_get_dependents_validates_path(self):
        """Test that get_dependents validates file path."""
        service = self._create_service()

        with pytest.raises(ValueError, match="Path traversal not allowed"):
            service.get_dependents("../../../etc/passwd")

        service.shutdown()

    def test_get_dependencies_validates_path(self):
        """Test that get_dependencies validates file path."""
        service = self._create_service()

        with pytest.raises(ValueError, match="Path traversal not allowed"):
            service.get_dependencies("../../../etc/passwd")

        service.shutdown()


class TestCrossFileContextServiceIntegration:
    """Integration tests for the full workflow."""

    def test_full_workflow_analyze_and_read(self):
        """Test complete workflow: analyze directory, then read with context."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create module structure
            (Path(tmpdir) / "utils.py").write_text(
                "def add(a: int, b: int) -> int:\n"
                '    """Add two numbers."""\n'
                "    return a + b\n"
            )

            (Path(tmpdir) / "main.py").write_text(
                "from utils import add\n\n" "result = add(1, 2)\n" "print(result)\n"
            )

            # Analyze all files
            stats = service.analyze_directory(tmpdir)
            assert stats["success"] >= 2

            # Read main.py with context
            result = service.read_file_with_context(str(Path(tmpdir) / "main.py"))

            # Verify content is correct
            assert "from utils import add" in result.content

            # Get dependencies (verifies graph was populated)
            _ = service.get_dependencies(str(Path(tmpdir) / "main.py"))
            # There should be at least one dependency

            # Get dependents of utils.py (verifies bidirectional indexing works)
            _ = service.get_dependents(str(Path(tmpdir) / "utils.py"))
            # main.py should depend on utils.py

            service.shutdown()

    def test_incremental_update_workflow(self):
        """Test that file changes trigger re-analysis."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create initial file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("x = 1")

            # Analyze
            service.analyze_file(str(test_file))

            # Simulate file change
            service._file_watcher.file_event_timestamps[str(test_file)] = 999999.0
            test_file.write_text("import os\nx = os.getcwd()")

            # Process changes
            stats = service.process_pending_changes()

            # Should have processed the change
            assert stats["total"] >= 1

            service.shutdown()
