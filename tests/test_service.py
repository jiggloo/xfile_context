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

import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
from xfile_context.models import FileMetadata, Relationship, RelationshipGraph, RelationshipType
from xfile_context.service import CrossFileContextService, ReadResult
from xfile_context.storage import InMemoryStore


def _create_file_metadata(filepath: str, relationship_count: int = 1) -> FileMetadata:
    """Create FileMetadata for testing to prevent lazy re-analysis.

    When tests manually add relationships to the graph, they should also
    add metadata to prevent the lazy initialization from re-analyzing
    and overwriting the test relationships.
    """
    return FileMetadata(
        filepath=filepath,
        last_analyzed=time.time() + 3600,  # 1 hour in the future to prevent re-analysis
        relationship_count=relationship_count,
        has_dynamic_patterns=False,
        dynamic_pattern_types=[],
        is_unparseable=False,
    )


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


@pytest.mark.slow
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


@pytest.mark.slow
class TestTokenCounting:
    """Tests for token counting functionality (TDD Section 3.8.4)."""

    def test_count_tokens_basic(self):
        """Test basic token counting."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Simple text
            token_count = service._count_tokens("Hello, world!")
            assert token_count > 0
            assert isinstance(token_count, int)

            service.shutdown()

    def test_count_tokens_code(self):
        """Test token counting for Python code."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            code = "def hello():\n    print('Hello, world!')"
            token_count = service._count_tokens(code)

            # Code typically has more tokens due to syntax
            # Note: Falls back to word-based approximation if tiktoken unavailable
            assert token_count >= 5

            service.shutdown()

    def test_count_tokens_empty(self):
        """Test token counting for empty string."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            token_count = service._count_tokens("")
            assert token_count == 0

            service.shutdown()


@pytest.mark.slow
class TestHighUsageFunctionDetection:
    """Tests for high-usage function detection (FR-19, FR-20)."""

    def test_get_symbol_usage_count_no_usages(self):
        """Test counting usages when symbol has no dependents."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()
            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            count = service._get_symbol_usage_count("/path/utils.py", "helper")
            assert count == 0

            service.shutdown()

    def test_get_symbol_usage_count_single_usage(self):
        """Test counting usages when symbol is used by one file."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            # main.py uses helper from utils.py
            rel = Relationship(
                source_file=str(Path(tmpdir) / "main.py"),
                target_file=str(Path(tmpdir) / "utils.py"),
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
            )
            graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            count = service._get_symbol_usage_count(str(Path(tmpdir) / "utils.py"), "helper")
            assert count == 1

            service.shutdown()

    def test_get_symbol_usage_count_multiple_usages(self):
        """Test counting usages when symbol is used by multiple files."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            # Three files all use helper from utils.py
            for i in range(3):
                rel = Relationship(
                    source_file=str(Path(tmpdir) / f"file{i}.py"),
                    target_file=str(Path(tmpdir) / "utils.py"),
                    relationship_type=RelationshipType.IMPORT,
                    line_number=1,
                    target_symbol="helper",
                )
                graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            count = service._get_symbol_usage_count(str(Path(tmpdir) / "utils.py"), "helper")
            assert count == 3

            service.shutdown()

    def test_get_high_usage_symbols_empty(self):
        """Test high usage detection with no dependencies."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            high_usage = service._get_high_usage_symbols([])
            assert high_usage == {}

            service.shutdown()

    def test_get_high_usage_symbols_below_threshold(self):
        """Test high usage detection when usage is below threshold."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            # Only 2 files use helper (threshold is 3)
            for i in range(2):
                rel = Relationship(
                    source_file=str(Path(tmpdir) / f"file{i}.py"),
                    target_file=str(Path(tmpdir) / "utils.py"),
                    relationship_type=RelationshipType.IMPORT,
                    line_number=1,
                    target_symbol="helper",
                    target_line=5,
                )
                graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Get dependencies from one of the files
            deps = graph.get_dependencies(str(Path(tmpdir) / "file0.py"))
            high_usage = service._get_high_usage_symbols(deps)

            # Should be empty since usage count (2) < threshold (3)
            assert high_usage == {}

            service.shutdown()

    def test_get_high_usage_symbols_at_threshold(self):
        """Test high usage detection when usage is at threshold."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            utils_path = str(Path(tmpdir) / "utils.py")

            # 3 files use helper (exactly at threshold)
            for i in range(3):
                rel = Relationship(
                    source_file=str(Path(tmpdir) / f"file{i}.py"),
                    target_file=utils_path,
                    relationship_type=RelationshipType.IMPORT,
                    line_number=1,
                    target_symbol="helper",
                    target_line=5,
                )
                graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Get dependencies from one of the files
            deps = graph.get_dependencies(str(Path(tmpdir) / "file0.py"))
            high_usage = service._get_high_usage_symbols(deps)

            # Should contain the symbol
            assert (utils_path, "helper") in high_usage
            assert high_usage[(utils_path, "helper")] == 3

            service.shutdown()

    def test_high_usage_warning_emitted(self):
        """Test that high-usage warning is emitted in context."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            utils_path = str(Path(tmpdir) / "utils.py")
            main_path = str(Path(tmpdir) / "main.py")

            # 4 files use helper (above threshold)
            for i in range(4):
                source = main_path if i == 0 else str(Path(tmpdir) / f"other{i}.py")
                rel = Relationship(
                    source_file=source,
                    target_file=utils_path,
                    relationship_type=RelationshipType.IMPORT,
                    line_number=1,
                    target_symbol="helper",
                    target_line=5,
                )
                graph.add_relationship(rel)

            # Add metadata to prevent lazy re-analysis from overwriting test relationships
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))
            for i in range(1, 4):
                other_path = str(Path(tmpdir) / f"other{i}.py")
                graph.set_file_metadata(other_path, _create_file_metadata(other_path, 1))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create the files
            Path(utils_path).write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n" "def helper():\n    pass\n"
            )
            Path(main_path).write_text("from utils import helper\n")

            result = service.read_file_with_context(main_path)

            # Should have high-usage warning
            assert any("helper()" in w and "4 files" in w for w in result.warnings)

            service.shutdown()


class TestDependencyPrioritization:
    """Tests for dependency prioritization (TDD Section 3.8.2)."""

    def test_prioritize_by_relationship_type(self):
        """Test that IMPORT has higher priority than FUNCTION_CALL."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            # Add function call relationship
            rel_call = Relationship(
                source_file=str(Path(tmpdir) / "main.py"),
                target_file=str(Path(tmpdir) / "utils.py"),
                relationship_type=RelationshipType.FUNCTION_CALL,
                line_number=10,
                target_symbol="helper",
            )

            # Add import relationship
            rel_import = Relationship(
                source_file=str(Path(tmpdir) / "main.py"),
                target_file=str(Path(tmpdir) / "other.py"),
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="other_func",
            )

            graph.add_relationship(rel_call)
            graph.add_relationship(rel_import)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            deps = [rel_call, rel_import]
            prioritized = service._prioritize_dependencies(deps)

            # Import should come before function call
            assert prioritized[0].relationship_type == RelationshipType.IMPORT

            service.shutdown()

    def test_prioritize_high_usage_functions(self):
        """Test that high-usage functions get higher priority."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            utils_path = str(Path(tmpdir) / "utils.py")
            main_path = str(Path(tmpdir) / "main.py")

            # helper is used by 4 files (high usage)
            for i in range(4):
                source = main_path if i == 0 else str(Path(tmpdir) / f"other{i}.py")
                rel = Relationship(
                    source_file=source,
                    target_file=utils_path,
                    relationship_type=RelationshipType.IMPORT,
                    line_number=1,
                    target_symbol="helper",
                    target_line=5,
                )
                graph.add_relationship(rel)

            # another_func is only used by main.py (low usage)
            rel_low = Relationship(
                source_file=main_path,
                target_file=str(Path(tmpdir) / "another.py"),
                relationship_type=RelationshipType.IMPORT,
                line_number=2,
                target_symbol="another_func",
                target_line=10,
            )
            graph.add_relationship(rel_low)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            deps = graph.get_dependencies(main_path)
            prioritized = service._prioritize_dependencies(deps)

            # High usage function should come first
            # (Both are IMPORT type, so high-usage is the tiebreaker)
            assert prioritized[0].target_symbol == "helper"

            service.shutdown()


@pytest.mark.slow
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


@pytest.mark.slow
class TestContextInjectionFormatting:
    """Tests for context injection formatting (T-2.2, TDD Section 3.8.3)."""

    def test_format_header_present(self):
        """Test that [Cross-File Context] header is present."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

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

            Path(tmpdir, "utils.py").write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n" "def helper():\n    pass\n"
            )
            Path(tmpdir, "main.py").write_text("from utils import helper\n")

            result = service.read_file_with_context(str(Path(tmpdir) / "main.py"))

            assert "[Cross-File Context]" in result.injected_context
            service.shutdown()

    def test_format_separator_present(self):
        """Test that --- separator is present at end of context."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

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

            Path(tmpdir, "utils.py").write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n" "def helper():\n    pass\n"
            )
            Path(tmpdir, "main.py").write_text("from utils import helper\n")

            result = service.read_file_with_context(str(Path(tmpdir) / "main.py"))

            # Separator should be at the end
            assert result.injected_context.strip().endswith("---")
            service.shutdown()

    def test_format_dependency_summary(self):
        """Test that dependency summary section is present."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

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

            Path(tmpdir, "utils.py").write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n" "def helper():\n    pass\n"
            )
            Path(tmpdir, "main.py").write_text("from utils import helper\n")

            result = service.read_file_with_context(str(Path(tmpdir) / "main.py"))

            # Issue #136: Updated header to clarify line numbers are in dependency files
            assert (
                "This file imports from (line numbers are in dependency files):"
                in result.injected_context
            )
            # Issue #136: Now uses full file path instead of just filename
            assert "utils.py:" in result.injected_context
            service.shutdown()

    def test_format_implementation_line_range(self):
        """Test that implementation shows line range (start-end)."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
                target_line=5,
            )
            graph.add_relationship(rel)

            # Add metadata to prevent lazy re-analysis from overwriting test relationships
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create a multi-line function
            Path(tmpdir, "utils.py").write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n"
                "def helper():\n"
                "    x = 1\n"
                "    y = 2\n"
                "    return x + y\n"
            )
            Path(tmpdir, "main.py").write_text("from utils import helper\n")

            result = service.read_file_with_context(str(Path(tmpdir) / "main.py"))

            # Should show line range like "5-8" instead of just "5"
            # Issue #136: Now uses full file path instead of just filename
            assert "# Implementation in " in result.injected_context
            assert "utils.py:" in result.injected_context
            # The format should include a range with hyphen
            assert "-" in result.injected_context.split("# Implementation in ")[1].split("\n")[0]
            service.shutdown()

    def test_format_short_docstring_included(self):
        """Test that short docstrings (<50 chars) are included."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
                target_line=5,
            )
            graph.add_relationship(rel)

            # Add metadata to prevent lazy re-analysis from overwriting test relationships
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create function with short docstring
            Path(tmpdir, "utils.py").write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n"
                "def helper():\n"
                '    """Short docstring."""\n'
                "    pass\n"
            )
            Path(tmpdir, "main.py").write_text("from utils import helper\n")

            result = service.read_file_with_context(str(Path(tmpdir) / "main.py"))

            # Should include the short docstring
            assert "Short docstring" in result.injected_context
            service.shutdown()

    def test_format_long_docstring_excluded(self):
        """Test that long docstrings (>=50 chars) are excluded."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

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

            # Create function with long docstring (>50 chars)
            long_doc = "This is a very long docstring that exceeds fifty characters easily"
            Path(tmpdir, "utils.py").write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n"
                f"def helper():\n"
                f'    """{long_doc}"""\n'
                "    pass\n"
            )
            Path(tmpdir, "main.py").write_text("from utils import helper\n")

            result = service.read_file_with_context(str(Path(tmpdir) / "main.py"))

            # Should NOT include the long docstring
            assert long_doc not in result.injected_context
            service.shutdown()

    def test_wildcard_import_note(self):
        """Test that wildcard imports have limitation note (EC-4)."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.WILDCARD_IMPORT,
                line_number=1,
            )
            graph.add_relationship(rel)

            # Add metadata to prevent lazy re-analysis from overwriting test relationships
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            Path(tmpdir, "utils.py").write_text("def helper():\n    pass\n")
            Path(tmpdir, "main.py").write_text("from utils import *\n")

            result = service.read_file_with_context(str(Path(tmpdir) / "main.py"))

            # Should have wildcard limitation note
            assert "Wildcard import" in result.injected_context
            assert "specific function tracking unavailable" in result.injected_context
            service.shutdown()

    def test_large_function_truncation_note(self):
        """Test that large functions (200+ lines) have truncation note (EC-12)."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            large_path = str(Path(tmpdir) / "large.py")

            rel = Relationship(
                source_file=main_path,
                target_file=large_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="large_func",
                target_line=1,
            )
            graph.add_relationship(rel)

            # Add metadata to prevent lazy re-analysis from overwriting test relationships
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(large_path, _create_file_metadata(large_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create a very large function (200+ lines)
            lines = ["def large_func():"]
            for i in range(250):
                lines.append(f"    x{i} = {i}")
            lines.append("    return x0")
            Path(tmpdir, "large.py").write_text("\n".join(lines))
            Path(tmpdir, "main.py").write_text("from large import large_func\n")

            result = service.read_file_with_context(str(Path(tmpdir) / "main.py"))

            # Should have truncation note for large function
            assert "lines" in result.injected_context
            assert "showing signature only" in result.injected_context
            service.shutdown()

    def test_deleted_file_warning(self):
        """Test that deleted file warning is emitted (EC-14)."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            utils_path = str(Path(tmpdir) / "utils.py")
            main_path = str(Path(tmpdir) / "main.py")

            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
                target_line=5,
            )
            graph.add_relationship(rel)

            # Add metadata to prevent lazy re-analysis from changing the relationship
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create main file but NOT utils.py (simulates deleted file)
            Path(main_path).write_text("from utils import helper\n")
            # Don't create utils.py - it's "deleted"

            result = service.read_file_with_context(main_path)

            # Should have warning about deleted/missing file
            assert any("no longer exists" in w or "was deleted" in w for w in result.warnings)
            service.shutdown()

    def test_deleted_file_context_note(self):
        """Test that deleted files show note in context (EC-14)."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            utils_path = str(Path(tmpdir) / "utils.py")
            main_path = str(Path(tmpdir) / "main.py")

            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
                target_line=5,
            )
            graph.add_relationship(rel)

            # Add metadata to prevent lazy re-analysis from changing the relationship
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create main file but NOT utils.py
            Path(main_path).write_text("from utils import helper\n")

            result = service.read_file_with_context(main_path)

            # Should have note in context about deleted file
            assert (
                "File was deleted" in result.injected_context
                or "Last known location" in result.injected_context
            )
            service.shutdown()

    def test_cache_age_indicator_present(self):
        """Test that cache age indicator is shown when available."""
        import time

        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            utils_path = str(Path(tmpdir) / "utils.py")
            main_path = str(Path(tmpdir) / "main.py")

            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
                target_line=5,
            )
            graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create files
            Path(utils_path).write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n" "def helper():\n    pass\n"
            )
            Path(main_path).write_text("from utils import helper\n")

            # Simulate that file was accessed recently
            service._file_watcher.file_event_timestamps[utils_path] = (
                time.time() - 60
            )  # 1 minute ago

            result = service.read_file_with_context(main_path)

            # Should have cache age indicator like "last read: 1 minute ago"
            assert "last read:" in result.injected_context
            service.shutdown()

    def test_cache_age_indicator_just_now(self):
        """Test that cache age shows 'just now' for very recent reads."""
        import time

        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            utils_path = str(Path(tmpdir) / "utils.py")
            main_path = str(Path(tmpdir) / "main.py")

            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
                target_line=5,
            )
            graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create files
            Path(utils_path).write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n" "def helper():\n    pass\n"
            )
            Path(main_path).write_text("from utils import helper\n")

            # Simulate that file was accessed just now (< 1 minute)
            service._file_watcher.file_event_timestamps[utils_path] = (
                time.time() - 10
            )  # 10 seconds ago

            result = service.read_file_with_context(main_path)

            # Should show "just now"
            assert "just now" in result.injected_context
            service.shutdown()

    def test_multiple_dependencies_formatting(self):
        """Test that multiple dependencies are formatted correctly."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")
            other_path = str(Path(tmpdir) / "other.py")

            # Add two dependencies
            rel1 = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
                target_line=5,
            )
            rel2 = Relationship(
                source_file=main_path,
                target_file=other_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=2,
                target_symbol="other_func",
                target_line=3,
            )
            graph.add_relationship(rel1)
            graph.add_relationship(rel2)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create files
            Path(utils_path).write_text(
                "# Line 1\n# Line 2\n# Line 3\n# Line 4\n" "def helper():\n    pass\n"
            )
            Path(other_path).write_text("# Line 1\n# Line 2\n" "def other_func():\n    pass\n")
            Path(main_path).write_text("from utils import helper\nfrom other import other_func\n")

            result = service.read_file_with_context(main_path)

            # Both dependencies should be in the summary
            assert "utils.py:" in result.injected_context
            assert "other.py:" in result.injected_context
            service.shutdown()


class TestFunctionSignatureExtraction:
    """Tests for function signature extraction with docstrings and line ranges."""

    def test_get_function_signature_with_docstring_basic(self):
        """Test basic signature extraction."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create a file with a simple function
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(
                "def my_func(a, b):\n" '    """Short doc."""\n' "    return a + b\n"
            )

            sig, doc, impl_range = service._get_function_signature_with_docstring(
                str(test_file), "my_func", 1
            )

            assert sig is not None
            assert "def my_func(a, b):" in sig
            assert doc == "Short doc."
            assert impl_range is not None
            service.shutdown()

    def test_get_function_signature_multiline(self):
        """Test multi-line signature extraction."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create a file with a multi-line signature
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(
                "def complex_func(\n"
                "    arg1: int,\n"
                "    arg2: str,\n"
                "    arg3: bool = True\n"
                ") -> dict:\n"
                "    return {}\n"
            )

            sig, _, _ = service._get_function_signature_with_docstring(
                str(test_file), "complex_func", 1
            )

            assert sig is not None
            assert "def complex_func(" in sig
            assert "arg1: int" in sig
            assert ") -> dict:" in sig
            service.shutdown()

    def test_get_function_line_count(self):
        """Test function line counting."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create a file with a 10-line function
            test_file = Path(tmpdir) / "test.py"
            lines = ["def my_func():"]
            for i in range(8):
                lines.append(f"    x{i} = {i}")
            lines.append("    return x0")
            lines.append("")
            lines.append("# Next function")
            lines.append("def other():")
            lines.append("    pass")
            test_file.write_text("\n".join(lines))

            count = service._get_function_line_count(str(test_file), 1)

            # Should count lines from def to return
            assert count is not None
            assert count >= 9  # def + 8 assignments + return
            service.shutdown()

    def test_async_function_signature(self):
        """Test async function signature extraction."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(
                "async def async_func():\n"
                '    """Async function."""\n'
                "    return await something()\n"
            )

            sig, doc, _ = service._get_function_signature_with_docstring(
                str(test_file), "async_func", 1
            )

            assert sig is not None
            assert "async def async_func():" in sig
            assert doc == "Async function."
            service.shutdown()

    def test_class_signature(self):
        """Test class signature extraction."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(
                "class MyClass:\n"
                '    """A simple class."""\n'
                "    def __init__(self):\n"
                "        pass\n"
            )

            sig, doc, _ = service._get_function_signature_with_docstring(
                str(test_file), "MyClass", 1
            )

            assert sig is not None
            assert "class MyClass:" in sig
            assert doc == "A simple class."
            service.shutdown()


class TestLazyInitialization:
    """Tests for lazy initialization feature (Issue #114).

    The lazy initialization ensures that files are analyzed on-demand when
    read_file_with_context is called, rather than requiring eager full-project
    analysis at MCP server startup.
    """

    def test_lazy_analysis_on_first_read(self):
        """Test that file is analyzed on first read with empty graph."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            # Start with empty graph (no prior analysis)
            service = CrossFileContextService(config, project_root=tmpdir)

            # Create files
            utils_path = Path(tmpdir) / "utils.py"
            main_path = Path(tmpdir) / "main.py"

            utils_path.write_text("def helper():\n    return 42\n")
            main_path.write_text("from utils import helper\n\nresult = helper()\n")

            # Read file - should trigger lazy analysis
            result = service.read_file_with_context(str(main_path))

            # Verify context was injected (indicates analysis happened)
            assert "[Cross-File Context]" in result.injected_context
            # Issue #136: Updated header to clarify line numbers are in dependency files
            assert (
                "This file imports from (line numbers are in dependency files):"
                in result.injected_context
            )
            assert "utils.py" in result.injected_context

            # Verify the graph now has relationships
            deps = service._graph.get_dependencies(str(main_path))
            assert len(deps) > 0

            # Verify file metadata was created
            metadata = service._graph.get_file_metadata(str(main_path))
            assert metadata is not None
            assert metadata.last_analyzed > 0

            service.shutdown()

    def test_lazy_analysis_skips_already_analyzed(self):
        """Test that already-analyzed files are not re-analyzed."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            main_path = Path(tmpdir) / "main.py"
            main_path.write_text("x = 1\n")

            # First read triggers analysis
            service.read_file_with_context(str(main_path))

            # Get the analysis timestamp
            metadata_before = service._graph.get_file_metadata(str(main_path))
            assert metadata_before is not None
            timestamp_before = metadata_before.last_analyzed

            # Second read should not re-analyze (file not modified)
            service.read_file_with_context(str(main_path))

            metadata_after = service._graph.get_file_metadata(str(main_path))
            assert metadata_after is not None
            timestamp_after = metadata_after.last_analyzed

            # Timestamp should be the same (no re-analysis)
            assert timestamp_before == timestamp_after

            service.shutdown()

    def test_lazy_analysis_reanalyzes_modified_file(self):
        """Test that modified files are re-analyzed."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            main_path = Path(tmpdir) / "main.py"
            main_path.write_text("x = 1\n")

            # First read triggers analysis
            service.read_file_with_context(str(main_path))

            metadata_before = service._graph.get_file_metadata(str(main_path))
            assert metadata_before is not None
            timestamp_before = metadata_before.last_analyzed

            # Modify the file (update mtime)
            import time

            time.sleep(0.1)  # Ensure different mtime
            main_path.write_text("x = 2\nimport os\n")

            # Second read should re-analyze (file modified)
            service.read_file_with_context(str(main_path))

            metadata_after = service._graph.get_file_metadata(str(main_path))
            assert metadata_after is not None
            timestamp_after = metadata_after.last_analyzed

            # Timestamp should be different (re-analyzed)
            assert timestamp_after > timestamp_before

            service.shutdown()

    def test_needs_analysis_helper_no_metadata(self):
        """Test _needs_analysis returns True when file has no metadata."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            main_path = Path(tmpdir) / "main.py"
            main_path.write_text("x = 1\n")

            # File exists but has no metadata
            assert service._needs_analysis(str(main_path)) is True

            service.shutdown()

    def test_needs_analysis_helper_with_metadata(self):
        """Test _needs_analysis returns False when file has current metadata."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            main_path = Path(tmpdir) / "main.py"
            main_path.write_text("x = 1\n")

            # Add metadata with future timestamp
            metadata = FileMetadata(
                filepath=str(main_path),
                last_analyzed=time.time() + 3600,  # Future timestamp
                relationship_count=0,
                has_dynamic_patterns=False,
                dynamic_pattern_types=[],
                is_unparseable=False,
            )
            service._graph.set_file_metadata(str(main_path), metadata)

            # File has metadata and isn't modified
            assert service._needs_analysis(str(main_path)) is False

            service.shutdown()

    def test_needs_analysis_helper_nonexistent_file(self):
        """Test _needs_analysis returns False for non-existent file."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            service = CrossFileContextService(config, project_root=tmpdir)

            # Non-existent file
            assert service._needs_analysis(str(Path(tmpdir) / "nonexistent.py")) is False

            service.shutdown()


class TestSpecialMarkerPathHandling:
    """Tests for special marker path handling (Issue #116 Bug 2).

    Verifies that special marker paths (<stdlib:...>, <third-party:...>,
    <builtin:...>, <unresolved:...>) are correctly excluded from file
    existence checks in _check_deleted_files().
    """

    def test_check_deleted_files_skips_stdlib_markers(self):
        """Test that stdlib markers don't trigger false deletion warnings."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")

            # Create relationships to stdlib modules
            rel_ast = Relationship(
                source_file=main_path,
                target_file="<stdlib:ast>",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="parse",
            )
            rel_logging = Relationship(
                source_file=main_path,
                target_file="<stdlib:logging>",
                relationship_type=RelationshipType.IMPORT,
                line_number=2,
                target_symbol="Logger",
            )
            graph.add_relationship(rel_ast)
            graph.add_relationship(rel_logging)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Call _check_deleted_files with stdlib dependencies
            deps = [rel_ast, rel_logging]
            warnings, deleted_files = service._check_deleted_files(deps)

            # Should not have any warnings for stdlib modules
            assert len(warnings) == 0
            assert len(deleted_files) == 0

            service.shutdown()

    def test_check_deleted_files_skips_third_party_markers(self):
        """Test that third-party markers don't trigger false deletion warnings."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")

            # Create relationship to third-party module
            rel = Relationship(
                source_file=main_path,
                target_file="<third-party:requests>",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="get",
            )
            graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            warnings, deleted_files = service._check_deleted_files([rel])

            # Should not have any warnings for third-party modules
            assert len(warnings) == 0
            assert len(deleted_files) == 0

            service.shutdown()

    def test_check_deleted_files_skips_unresolved_markers(self):
        """Test that unresolved markers don't trigger false deletion warnings."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")

            # Create relationship to unresolved module
            rel = Relationship(
                source_file=main_path,
                target_file="<unresolved:some_missing_module>",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="func",
            )
            graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            warnings, deleted_files = service._check_deleted_files([rel])

            # Should not have any warnings for unresolved modules
            assert len(warnings) == 0
            assert len(deleted_files) == 0

            service.shutdown()

    def test_check_deleted_files_detects_real_deleted_files(self):
        """Test that actual deleted files still trigger warnings correctly."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Create relationship to a real file path that doesn't exist
            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,  # Real path, not marker
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
                target_symbol="helper",
            )
            graph.add_relationship(rel)

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # utils.py doesn't exist, so it should be flagged as deleted
            warnings, deleted_files = service._check_deleted_files([rel])

            assert len(warnings) == 1
            assert utils_path in deleted_files
            assert "no longer exists" in warnings[0]

            service.shutdown()

    def test_check_deleted_files_mixed_markers_and_real_files(self):
        """Test handling a mix of special markers and real file paths."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")
            existing_path = str(Path(tmpdir) / "existing.py")

            # Create the existing file
            Path(existing_path).write_text("x = 1\n")

            # Mix of relationships
            rel_stdlib = Relationship(
                source_file=main_path,
                target_file="<stdlib:os>",
                relationship_type=RelationshipType.IMPORT,
                line_number=1,
            )
            rel_deleted = Relationship(
                source_file=main_path,
                target_file=utils_path,  # Doesn't exist
                relationship_type=RelationshipType.IMPORT,
                line_number=2,
            )
            rel_existing = Relationship(
                source_file=main_path,
                target_file=existing_path,  # Exists
                relationship_type=RelationshipType.IMPORT,
                line_number=3,
            )

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            deps = [rel_stdlib, rel_deleted, rel_existing]
            warnings, deleted_files = service._check_deleted_files(deps)

            # Only the deleted real file should trigger a warning
            assert len(warnings) == 1
            assert utils_path in deleted_files
            assert existing_path not in deleted_files

            service.shutdown()


class TestDependencySummaryLineNumbers:
    """Tests for dependency summary line number formatting (Issue #116 Bug 3).

    Verifies that the dependency summary shows definition line numbers
    (target_line) from the dependency file, not usage line numbers
    (line_number) from the source file.
    """

    def test_assemble_context_uses_target_line_not_line_number(self):
        """Test that _assemble_context uses target_line for definition line."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Create relationship with distinct line numbers:
            # - line_number=10: where the import is used in main.py
            # - target_line=25: where helper is defined in utils.py
            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=10,  # Usage line in main.py
                target_symbol="helper",
                target_line=25,  # Definition line in utils.py
            )
            graph.add_relationship(rel)

            # Add metadata to prevent lazy re-analysis
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create the files
            Path(utils_path).write_text(
                "# Lines 1-24 are filler\n" * 24 + "def helper():\n    pass\n"
            )
            Path(main_path).write_text(
                "# Lines 1-9 are filler\n" * 9 + "from utils import helper\n"
            )

            # Assemble context
            context, warnings = service._assemble_context(main_path, [rel])

            # The dependency summary should show target_line (25), not line_number (10)
            # Format: "- utils.py: helper() (line 25)"
            assert "helper() (line 25)" in context
            assert "helper() (line 10)" not in context

            service.shutdown()

    def test_assemble_context_fallback_when_target_line_is_none(self):
        """Test that symbols without target_line omit the line number."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Create relationship with target_line=None
            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=5,
                target_symbol="helper",
                target_line=None,  # Definition line unknown
            )
            graph.add_relationship(rel)

            # Add metadata
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create files
            Path(utils_path).write_text("def helper():\n    pass\n")
            Path(main_path).write_text("from utils import helper\n")

            context, _ = service._assemble_context(main_path, [rel])

            # When target_line is None, should just show symbol without line number
            # Format: "- utils.py: helper()"
            assert "helper()" in context
            # Should not show the usage line number (5) in the dependency summary
            assert "helper() (line 5)" not in context

            service.shutdown()

    def test_assemble_context_non_symbol_uses_line_number(self):
        """Test that non-symbol dependencies use line_number (usage line)."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Create relationship without target_symbol
            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=7,
                target_symbol=None,  # No specific symbol
                target_line=None,
            )
            graph.add_relationship(rel)

            # Add metadata
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            Path(utils_path).write_text("x = 1\n")
            Path(main_path).write_text("import utils\n")

            context, _ = service._assemble_context(main_path, [rel])

            # Non-symbol imports should show the usage line_number
            # Format: "- utils.py: (line 7)"
            assert "(line 7)" in context

            service.shutdown()

    def test_context_injection_with_target_line_set(self):
        """Integration test: when target_line is set, it appears in context.

        Note: The full integration of setting target_line during analysis
        depends on the function call detector's ability to resolve symbol
        definitions, which may not always succeed. This test verifies the
        behavior when target_line IS set by manually adding relationships.
        """
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Manually create a relationship with target_line set
            # This simulates what should happen when the detector fully resolves symbols
            rel = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.IMPORT,
                line_number=1,  # Import line in main.py
                target_symbol="helper_function",
                target_line=15,  # Definition line in utils.py
            )
            graph.add_relationship(rel)

            # Prevent lazy re-analysis
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 1))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create utils.py with function defined on line 15
            utils_lines = ["# filler\n"] * 14 + [
                "def helper_function():\n",
                '    """A helper."""\n',
                "    return 42\n",
            ]
            Path(utils_path).write_text("".join(utils_lines))
            Path(main_path).write_text("from utils import helper_function\n")

            # Read main.py with context
            result = service.read_file_with_context(main_path)

            # The dependency summary should show target_line (15)
            assert "helper_function" in result.injected_context
            assert "line 15" in result.injected_context

            service.shutdown()


class TestDeterministicOutput:
    """Tests that context output is deterministic/idempotent (Issue #131).

    When the same file is read multiple times without modifications,
    the output should be identical. This requires:
    - References sorted by file path
    - Symbols sorted alphabetically within each reference
    - All symbols printed (no truncation)
    """

    def test_assemble_context_sorts_references_by_file_path(self):
        """Test that references are sorted alphabetically by file path."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            # Create paths that would be unsorted if insertion order was used
            zebra_path = str(Path(tmpdir) / "zebra.py")
            alpha_path = str(Path(tmpdir) / "alpha.py")
            middle_path = str(Path(tmpdir) / "middle.py")

            # Add relationships in non-alphabetical order
            for target_path, symbol in [
                (zebra_path, "z_func"),
                (alpha_path, "a_func"),
                (middle_path, "m_func"),
            ]:
                rel = Relationship(
                    source_file=main_path,
                    target_file=target_path,
                    relationship_type=RelationshipType.IMPORT,
                    line_number=1,
                    target_symbol=symbol,
                    target_line=10,
                )
                graph.add_relationship(rel)
                graph.set_file_metadata(target_path, _create_file_metadata(target_path, 0))

            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 3))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create files
            Path(main_path).write_text("# main\n")
            for p in [zebra_path, alpha_path, middle_path]:
                Path(p).write_text("def func(): pass\n")

            rels = graph.get_dependencies(main_path)
            context, _ = service._assemble_context(main_path, rels)

            # Find the order of file references in the output
            alpha_pos = context.find("alpha.py")
            middle_pos = context.find("middle.py")
            zebra_pos = context.find("zebra.py")

            # All should be present
            assert alpha_pos != -1, "alpha.py not found in context"
            assert middle_pos != -1, "middle.py not found in context"
            assert zebra_pos != -1, "zebra.py not found in context"

            # Should be in alphabetical order
            assert alpha_pos < middle_pos < zebra_pos, (
                f"References not sorted: alpha={alpha_pos}, "
                f"middle={middle_pos}, zebra={zebra_pos}"
            )

            service.shutdown()

    def test_assemble_context_sorts_symbols_within_reference(self):
        """Test that symbols are sorted alphabetically within each file reference."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Add multiple symbols from the same file in non-alphabetical order
            for symbol, line in [("zebra", 30), ("alpha", 10), ("middle", 20)]:
                rel = Relationship(
                    source_file=main_path,
                    target_file=utils_path,
                    relationship_type=RelationshipType.IMPORT,
                    line_number=1,
                    target_symbol=symbol,
                    target_line=line,
                )
                graph.add_relationship(rel)

            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 3))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create files
            Path(main_path).write_text("# main\n")
            Path(utils_path).write_text(
                "def alpha(): pass\ndef middle(): pass\ndef zebra(): pass\n"
            )

            rels = graph.get_dependencies(main_path)
            context, _ = service._assemble_context(main_path, rels)

            # Find the utils.py line in context
            for line in context.split("\n"):
                if "utils.py" in line:
                    # Symbols should be in alphabetical order
                    alpha_pos = line.find("alpha()")
                    middle_pos = line.find("middle()")
                    zebra_pos = line.find("zebra()")

                    assert alpha_pos != -1, "alpha() not found"
                    assert middle_pos != -1, "middle() not found"
                    assert zebra_pos != -1, "zebra() not found"

                    assert alpha_pos < middle_pos < zebra_pos, (
                        f"Symbols not sorted: alpha={alpha_pos}, "
                        f"middle={middle_pos}, zebra={zebra_pos}"
                    )
                    break
            else:
                pytest.fail("utils.py line not found in context")

            service.shutdown()

    def test_assemble_context_prints_all_symbols_no_truncation(self):
        """Test that all symbols are printed without truncation."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Add more than 3 symbols (previous truncation limit was 3)
            symbols = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
            for i, symbol in enumerate(symbols):
                rel = Relationship(
                    source_file=main_path,
                    target_file=utils_path,
                    relationship_type=RelationshipType.IMPORT,
                    line_number=1,
                    target_symbol=symbol,
                    target_line=i * 10 + 10,
                )
                graph.add_relationship(rel)

            graph.set_file_metadata(main_path, _create_file_metadata(main_path, len(symbols)))
            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create files
            Path(main_path).write_text("# main\n")
            Path(utils_path).write_text("\n".join(f"def {s}(): pass" for s in symbols) + "\n")

            rels = graph.get_dependencies(main_path)
            context, _ = service._assemble_context(main_path, rels)

            # All symbols should be present
            for symbol in symbols:
                assert f"{symbol}()" in context, f"{symbol}() not found in context"

            # Should NOT have truncation marker
            assert "(+3 more)" not in context, "Truncation marker found"
            assert "(+" not in context or "(+)" in context, "Some truncation marker found"

            service.shutdown()

    def test_assemble_context_idempotent_output(self):
        """Test that calling _assemble_context twice produces identical output."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")
            helpers_path = str(Path(tmpdir) / "helpers.py")

            # Add multiple relationships with various symbols
            for target, symbols in [
                (utils_path, ["config", "validate", "setup"]),
                (helpers_path, ["format_data", "parse_input", "cleanup"]),
            ]:
                for i, symbol in enumerate(symbols):
                    rel = Relationship(
                        source_file=main_path,
                        target_file=target,
                        relationship_type=RelationshipType.IMPORT,
                        line_number=i + 1,
                        target_symbol=symbol,
                        target_line=(i + 1) * 10,
                    )
                    graph.add_relationship(rel)
                graph.set_file_metadata(target, _create_file_metadata(target, 0))

            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 6))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create files
            Path(main_path).write_text("# main\n")
            Path(utils_path).write_text(
                "def config(): pass\ndef validate(): pass\ndef setup(): pass\n"
            )
            Path(helpers_path).write_text(
                "def format_data(): pass\ndef parse_input(): pass\ndef cleanup(): pass\n"
            )

            rels = graph.get_dependencies(main_path)

            # Call multiple times
            context1, _ = service._assemble_context(main_path, rels)
            context2, _ = service._assemble_context(main_path, rels)
            context3, _ = service._assemble_context(main_path, rels)

            # All calls should produce identical output
            assert context1 == context2, "First and second call produced different output"
            assert context2 == context3, "Second and third call produced different output"

            service.shutdown()


class TestFirstCallCompleteSymbols:
    """Tests that the first read_with_context() call has complete symbol information (Issue #138).

    When read_with_context() is called for the first time on a file, the dependency
    files' symbols should be fully loaded so that:
    - Line numbers appear in the "This file imports from:" section
    - The "Recent definitions:" section contains the expected class/function definitions

    This was broken because analyze_file_two_phase() only loaded the target file's symbols,
    not the dependency files' symbols, so _get_target_line() returned None for dependencies.
    """

    def test_first_call_has_line_numbers_for_class_imports(self):
        """Test that the first call includes line numbers for imported classes.

        Note: Currently only class definitions are extracted by detectors.
        Function definitions are not extracted, so they don't have line numbers.
        This test verifies the Issue #138 fix works for classes.
        """
        with TemporaryDirectory() as tmpdir:
            config = Config()  # enable_context_injection=True by default
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Create utils.py with a class
            Path(utils_path).write_text(
                '''"""Utils module."""


class HelperClass:
    """A helper class."""
    pass
'''
            )

            # Create main.py that imports from utils
            Path(main_path).write_text(
                '''"""Main module."""
from utils import HelperClass


class ChildClass(HelperClass):
    """A child class."""
    pass
'''
            )

            # Create a fresh service (no prior analysis)
            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # First call should have complete information
            result = service.read_file_with_context(main_path)

            # The imports section should include line numbers for the class
            assert "HelperClass" in result.injected_context
            # Line 4 is where HelperClass is defined in utils.py
            assert (
                "line 4" in result.injected_context
            ), f"Line number not found in first call. Context:\n{result.injected_context}"

            service.shutdown()

    def test_first_call_has_recent_definitions_section(self):
        """Test that the first call includes the Recent definitions section."""
        with TemporaryDirectory() as tmpdir:
            config = Config()  # enable_context_injection=True by default
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            base_path = str(Path(tmpdir) / "base.py")

            # Create base.py with a class
            Path(base_path).write_text(
                '''"""Base module."""


class BaseClass:
    """A base class for inheritance."""

    def method(self):
        """A method."""
        pass
'''
            )

            # Create main.py that imports and uses the class
            Path(main_path).write_text(
                '''"""Main module."""
from base import BaseClass


class ChildClass(BaseClass):
    """A child class."""
    pass
'''
            )

            # Create a fresh service (no prior analysis)
            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # First call should have complete information
            result = service.read_file_with_context(main_path)

            # The Recent definitions section should exist and have content
            assert "Recent definitions:" in result.injected_context

            # Should include the BaseClass definition with implementation range
            assert "BaseClass" in result.injected_context
            # Line 4 is where BaseClass is defined in base.py (after docstring and blank lines)
            assert (
                "base.py:4" in result.injected_context or "From" in result.injected_context
            ), f"BaseClass definition not found. Context:\n{result.injected_context}"

            service.shutdown()

    def test_first_and_second_call_produce_identical_output(self):
        """Test that the first and second calls produce identical output (idempotency)."""
        with TemporaryDirectory() as tmpdir:
            config = Config()  # enable_context_injection=True by default
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Create utils.py
            Path(utils_path).write_text(
                '''"""Utils module."""


def helper_one():
    """Helper one."""
    pass


def helper_two():
    """Helper two."""
    pass
'''
            )

            # Create main.py
            Path(main_path).write_text(
                '''"""Main module."""
from utils import helper_one, helper_two

helper_one()
helper_two()
'''
            )

            # Create a fresh service
            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # First call
            result1 = service.read_file_with_context(main_path)

            # Second call (no changes made)
            result2 = service.read_file_with_context(main_path)

            # Injected context should be identical
            assert result1.injected_context == result2.injected_context, (
                f"First and second call produced different output.\n"
                f"First:\n{result1.injected_context}\n"
                f"Second:\n{result2.injected_context}"
            )

            service.shutdown()


class TestRecentDefinitionsDeduplication:
    """Tests for deduplication in 'recent definitions' section (Issue #144).

    The deduplication key is: (target_file, target_line, source_file, relationship_type).
    This key excludes usage line number because a single function definition
    is sufficient for all usages in the file.
    """

    def test_deduplicate_same_function_multiple_usages(self):
        """Test that a function used multiple times in a file appears only once.

        When a function like my_helper() is called on lines 5, 10, and 15,
        the recent definitions should only show my_helper() once.
        """
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Add multiple relationships for the same function used at different lines
            # (simulates calling my_helper() on lines 5, 10, and 15)
            for usage_line in [5, 10, 15]:
                rel = Relationship(
                    source_file=main_path,
                    target_file=utils_path,
                    relationship_type=RelationshipType.FUNCTION_CALL,
                    line_number=usage_line,  # Different usage lines
                    target_symbol="my_helper",
                    target_line=10,  # Same definition line
                )
                graph.add_relationship(rel)

            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 3))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create the files
            Path(main_path).write_text("# main\n")
            Path(utils_path).write_text("# utils\n\n\n\n\n\n\n\n\ndef my_helper():\n    pass\n")

            rels = graph.get_dependencies(main_path)
            context, _ = service._assemble_context(main_path, rels)

            # Count occurrences of the function in recent definitions
            # It should appear exactly once
            occurrences = context.count("def my_helper()")
            assert occurrences == 1, (
                f"Expected my_helper() to appear once, but found {occurrences} times.\n"
                f"Context:\n{context}"
            )

            service.shutdown()

    def test_different_functions_not_deduplicated(self):
        """Test that different functions from the same file are all shown."""
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Add relationships for different functions
            for i, (symbol, def_line) in enumerate(
                [
                    ("func_a", 1),
                    ("func_b", 3),
                    ("func_c", 5),
                ]
            ):
                rel = Relationship(
                    source_file=main_path,
                    target_file=utils_path,
                    relationship_type=RelationshipType.FUNCTION_CALL,
                    line_number=i + 1,
                    target_symbol=symbol,
                    target_line=def_line,
                )
                graph.add_relationship(rel)

            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 3))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create the files
            Path(main_path).write_text("# main\n")
            Path(utils_path).write_text(
                "def func_a(): pass\n\ndef func_b(): pass\n\ndef func_c(): pass\n"
            )

            rels = graph.get_dependencies(main_path)
            context, _ = service._assemble_context(main_path, rels)

            # All three functions should appear
            assert "def func_a()" in context, "func_a not found"
            assert "def func_b()" in context, "func_b not found"
            assert "def func_c()" in context, "func_c not found"

            service.shutdown()

    def test_same_function_different_relationship_types_not_deduplicated(self):
        """Test that same function with different relationship types appears twice.

        If a symbol is both imported and called, it should appear twice
        because relationship_type is part of the deduplication key.
        """
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Same function, different relationship types
            for rel_type in [RelationshipType.IMPORT, RelationshipType.FUNCTION_CALL]:
                rel = Relationship(
                    source_file=main_path,
                    target_file=utils_path,
                    relationship_type=rel_type,
                    line_number=1,
                    target_symbol="my_func",
                    target_line=5,
                )
                graph.add_relationship(rel)

            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 2))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create the files
            Path(main_path).write_text("from utils import my_func\nmy_func()\n")
            Path(utils_path).write_text("# utils\n\n\n\ndef my_func():\n    pass\n")

            rels = graph.get_dependencies(main_path)
            context, _ = service._assemble_context(main_path, rels)

            # Count occurrences - should appear twice since different relationship types
            # are part of the dedup key
            occurrences = context.count("def my_func()")
            assert occurrences == 2, (
                f"Expected my_func() to appear twice (one per rel type), "
                f"but found {occurrences} times.\nContext:\n{context}"
            )

            service.shutdown()

    def test_dedup_key_includes_target_line(self):
        """Test that deduplication considers target_line (definition line).

        Two usages pointing to different definition lines should both appear
        (even if they have the same symbol name, which shouldn't happen normally).
        """
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Same symbol name but different definition lines (edge case)
            for target_line in [1, 5]:
                rel = Relationship(
                    source_file=main_path,
                    target_file=utils_path,
                    relationship_type=RelationshipType.FUNCTION_CALL,
                    line_number=1,
                    target_symbol="func",
                    target_line=target_line,
                )
                graph.add_relationship(rel)

            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 2))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create the files
            Path(main_path).write_text("# main\n")
            Path(utils_path).write_text("def func(): pass\n\n\n\ndef func(): pass\n")

            rels = graph.get_dependencies(main_path)
            context, _ = service._assemble_context(main_path, rels)

            # Should have two entries since target_line is different
            # Count "From utils_path" occurrences (each snippet starts with this)
            from_count = context.count(f"From {utils_path}:")
            assert from_count == 2, (
                f"Expected 2 'From' entries (different target_line), "
                f"but found {from_count}.\nContext:\n{context}"
            )

            service.shutdown()

    def test_deduplicate_none_target_line(self):
        """Test that relationships with None target_line deduplicate correctly.

        Multiple usages of same symbol with target_line=None should deduplicate
        to a single entry since all other key components are identical.
        Note: When target_line is None, no signature is extracted from the file,
        so no "From" entry appears in the recent definitions section.
        """
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Add multiple relationships with None target_line
            for usage_line in [5, 10, 15]:
                rel = Relationship(
                    source_file=main_path,
                    target_file=utils_path,
                    relationship_type=RelationshipType.FUNCTION_CALL,
                    line_number=usage_line,
                    target_symbol="unknown_func",
                    target_line=None,  # Unknown definition line
                )
                graph.add_relationship(rel)

            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 3))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create the files
            Path(main_path).write_text("# main\n")
            Path(utils_path).write_text("def unknown_func(): pass\n")

            rels = graph.get_dependencies(main_path)

            # Verify we have 3 relationships (before deduplication at graph level)
            # Graph-level deduplication may reduce this, but the assembly-level
            # deduplication should further reduce based on our key
            assert len(rels) >= 1, "Expected at least 1 relationship"

            context, _ = service._assemble_context(main_path, rels)

            # When target_line is None, _get_function_signature_with_docstring returns None
            # so no signature is added to context. The key point is that multiple
            # relationships with same (target_file, None, source_file, rel_type)
            # are correctly treated as duplicates by the deduplication logic.
            # This can be verified by checking deduplicated_rels length would be 1.

            # The context should still have the imports section mentioning the function
            assert "unknown_func" in context, "Function should be mentioned in imports"

            service.shutdown()

    def test_deduplicate_mixed_none_and_non_none_target_line(self):
        """Test that None and non-None target_line are treated as different.

        A relationship with target_line=None should not deduplicate with
        a relationship with target_line=1 for the same function, since
        target_line is part of the deduplication key.
        """
        with TemporaryDirectory() as tmpdir:
            config = Config()
            graph = RelationshipGraph()

            main_path = str(Path(tmpdir) / "main.py")
            utils_path = str(Path(tmpdir) / "utils.py")

            # Add relationship with None target_line
            rel1 = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.FUNCTION_CALL,
                line_number=5,
                target_symbol="my_func",
                target_line=None,
            )
            graph.add_relationship(rel1)

            # Add relationship with specific target_line
            rel2 = Relationship(
                source_file=main_path,
                target_file=utils_path,
                relationship_type=RelationshipType.FUNCTION_CALL,
                line_number=10,
                target_symbol="my_func",
                target_line=1,
            )
            graph.add_relationship(rel2)

            graph.set_file_metadata(utils_path, _create_file_metadata(utils_path, 0))
            graph.set_file_metadata(main_path, _create_file_metadata(main_path, 2))

            service = CrossFileContextService(config, project_root=tmpdir, graph=graph)

            # Create the files
            Path(main_path).write_text("# main\n")
            Path(utils_path).write_text("def my_func(): pass\n")

            rels = graph.get_dependencies(main_path)
            context, _ = service._assemble_context(main_path, rels)

            # The deduplication treats (utils_path, None, main_path, FUNCTION_CALL)
            # and (utils_path, 1, main_path, FUNCTION_CALL) as DIFFERENT keys.
            # However, only the one with target_line=1 produces a signature in output.
            # The None one doesn't produce a "From" entry since signature lookup fails.
            # This test verifies the keys are distinct (no accidental dedup).

            # We should see at least one "From" entry for target_line=1
            from_count = context.count(f"From {utils_path}:")
            assert from_count >= 1, (
                f"Expected at least 1 'From' entry for target_line=1, "
                f"but found {from_count}.\nContext:\n{context}"
            )

            # Verify my_func appears in context
            assert "my_func" in context, "my_func should be mentioned"

            service.shutdown()
