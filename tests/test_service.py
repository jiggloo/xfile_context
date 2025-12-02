# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for CrossFileContextService stub implementation."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
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


class TestCrossFileContextService:
    """Tests for CrossFileContextService stub."""

    def test_initialization(self):
        """Test service initialization."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps = {}
        cache = WorkingMemoryCache(file_event_timestamps=file_event_timestamps)

        service = CrossFileContextService(config, store, cache)

        assert service.config is config
        assert service.store is store
        assert service.cache is cache

    def test_read_file_with_context_success(self):
        """Test reading an existing file."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps = {}
        cache = WorkingMemoryCache(file_event_timestamps=file_event_timestamps)
        service = CrossFileContextService(config, store, cache)

        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# Test file\nprint('hello')")

            result = service.read_file_with_context(str(test_file))

            assert result.file_path == str(test_file)
            assert result.content == "# Test file\nprint('hello')"
            assert result.injected_context == ""  # Stub returns empty context
            assert result.warnings == []

    def test_read_file_not_found(self):
        """Test reading a non-existent file raises FileNotFoundError."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps = {}
        cache = WorkingMemoryCache(file_event_timestamps=file_event_timestamps)
        service = CrossFileContextService(config, store, cache)

        with pytest.raises(FileNotFoundError):
            service.read_file_with_context("/nonexistent/file.py")

    def test_read_file_not_a_file(self):
        """Test reading a directory raises ValueError."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps = {}
        cache = WorkingMemoryCache(file_event_timestamps=file_event_timestamps)
        service = CrossFileContextService(config, store, cache)

        with TemporaryDirectory() as tmpdir, pytest.raises(ValueError, match="Path is not a file"):
            service.read_file_with_context(tmpdir)

    def test_get_relationship_graph(self):
        """Test getting relationship graph returns graph export."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps = {}
        cache = WorkingMemoryCache(file_event_timestamps=file_event_timestamps)
        service = CrossFileContextService(config, store, cache)

        graph_export = service.get_relationship_graph()

        assert graph_export is not None
        # Stub returns empty graph
        graph_dict = graph_export.to_dict()
        assert "nodes" in graph_dict
        assert "relationships" in graph_dict

    def test_get_dependents(self):
        """Test getting dependents returns empty list (stub)."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps = {}
        cache = WorkingMemoryCache(file_event_timestamps=file_event_timestamps)
        service = CrossFileContextService(config, store, cache)

        dependents = service.get_dependents("/test/file.py")

        # Stub returns empty list
        assert dependents == []

    def test_shutdown(self):
        """Test service shutdown."""
        config = Config()
        store = InMemoryStore()
        file_event_timestamps = {}
        cache = WorkingMemoryCache(file_event_timestamps=file_event_timestamps)
        service = CrossFileContextService(config, store, cache)

        # Should not raise
        service.shutdown()
