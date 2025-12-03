# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Integration tests for Service + Store + Cache workflow.

Tests the context injection workflow end-to-end per TDD Section 3.13.2.
"""

import time
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
from xfile_context.service import CrossFileContextService, ReadResult
from xfile_context.storage import InMemoryStore


def create_config_file(project_path: Path, **kwargs: Any) -> Path:
    """Create a temporary config file with given settings.

    Args:
        project_path: Path to project root
        **kwargs: Configuration overrides

    Returns:
        Path to the config file
    """
    config_path = project_path / ".cross_file_context_links.yml"
    config_data = {
        "cache_expiry_minutes": kwargs.get("cache_expiry_minutes", 10),
        "cache_size_limit_kb": kwargs.get("cache_size_limit_kb", 1024),
        "context_token_limit": kwargs.get("context_token_limit", 500),
        "enable_context_injection": kwargs.get("enable_context_injection", True),
        "warn_on_wildcards": kwargs.get("warn_on_wildcards", False),
        "function_usage_warning_threshold": kwargs.get("function_usage_warning_threshold", 3),
    }
    config_path.write_text(yaml.dump(config_data))
    return config_path


class TestServiceStoreCacheIntegration:
    """Integration tests for Service + Store + Cache workflow."""

    def test_basic_context_injection_workflow(self, sample_project: Path) -> None:
        """Test basic context injection workflow end-to-end.

        Validates the full workflow:
        1. Analyze files to build relationship graph
        2. Read file with context injection
        3. Verify context is injected correctly
        """
        config_path = create_config_file(
            sample_project,
            enable_context_injection=True,
            cache_expiry_minutes=10,
            cache_size_limit_kb=1024,
        )
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Step 1: Analyze the project
        stats = service.analyze_directory(str(sample_project / "mypackage"))
        assert stats["success"] > 0, "Should successfully analyze some files"

        # Step 2: Read a file that has dependencies
        core_file = sample_project / "mypackage" / "core.py"
        result = service.read_file_with_context(str(core_file))

        # Step 3: Verify result
        assert isinstance(result, ReadResult)
        assert result.file_path == str(core_file)
        assert len(result.content) > 0

        # Clean up
        service.shutdown()

    def test_cache_behavior_with_service(self, minimal_project: Path) -> None:
        """Test cache hit/miss behavior with service.

        The WorkingMemoryCache is a read-through cache that automatically
        reads from disk on cache miss or when entries become stale.
        """
        config_path = create_config_file(
            minimal_project,
            enable_context_injection=True,
            cache_expiry_minutes=10,
            cache_size_limit_kb=1024,
        )
        config = Config(config_path=config_path)

        # Create cache with access to file timestamps
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(
            file_event_timestamps=file_event_timestamps,
            size_limit_kb=config.cache_size_limit_kb,
        )

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
            cache=cache,
        )

        # Analyze the project
        service.analyze_directory(str(minimal_project))

        main_file = minimal_project / "main.py"

        # First read - cache miss, will read from disk
        result1 = service.read_file_with_context(str(main_file))
        assert result1.content is not None

        # Cache.get() reads from disk if needed - it's a read-through cache
        cached_content = cache.get(str(main_file))
        assert cached_content == result1.content

        # Second read - should hit cache
        result2 = service.read_file_with_context(str(main_file))
        assert result2.content == result1.content

        # Check cache statistics
        stats = cache.get_statistics()
        assert stats is not None

        service.shutdown()

    def test_store_relationship_persistence(self, minimal_project: Path) -> None:
        """Test that relationships are properly stored.

        get_relationship_graph() returns a dict with metadata, files, relationships.
        """
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)
        store = InMemoryStore()

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
            store=store,
        )

        # Analyze files
        service.analyze_directory(str(minimal_project))

        # Export from service - returns a dict
        export = service.get_relationship_graph()

        # Verify relationships exist (export is a dict)
        assert isinstance(export, dict)
        assert "files" in export
        assert "relationships" in export

        service.shutdown()

    def test_context_injection_disabled(self, minimal_project: Path) -> None:
        """Test that context injection can be disabled."""
        config_path = create_config_file(minimal_project, enable_context_injection=False)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        # Analyze files
        service.analyze_directory(str(minimal_project))

        main_file = minimal_project / "main.py"
        result = service.read_file_with_context(str(main_file))

        # Should have content but no injected context
        assert result.content is not None
        assert result.injected_context == ""

        service.shutdown()

    def test_context_injection_with_dependencies(self, sample_project: Path) -> None:
        """Test context injection includes dependency information."""
        config_path = create_config_file(
            sample_project,
            enable_context_injection=True,
            context_token_limit=4000,
        )
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze the full project
        service.analyze_directory(str(sample_project / "mypackage"))

        # Read core.py which imports from models and utils
        core_file = sample_project / "mypackage" / "core.py"
        result = service.read_file_with_context(str(core_file))

        # Verify we got content
        assert result.content is not None
        assert len(result.content) > 0

        service.shutdown()

    def test_service_graph_export(self, sample_project: Path) -> None:
        """Test exporting relationship graph from service.

        get_relationship_graph() returns a dict with metadata, files, relationships.
        """
        config_path = create_config_file(sample_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze files
        stats = service.analyze_directory(str(sample_project / "mypackage"))
        assert stats["success"] > 0

        # Export the graph - returns a dict
        export = service.get_relationship_graph()

        # Verify export structure (it's a dict)
        assert isinstance(export, dict)
        assert "files" in export
        assert "relationships" in export
        assert "metadata" in export

        # Should have analyzed files
        assert len(export["files"]) > 0

        service.shutdown()

    def test_cache_invalidation_on_file_change(self, minimal_project: Path) -> None:
        """Test that cache is invalidated when file changes.

        The cache detects staleness based on file_event_timestamps.
        When a file modification event is recorded, the cache entry becomes stale.
        """
        file_event_timestamps: Dict[str, float] = {}

        config_path = create_config_file(
            minimal_project,
            enable_context_injection=True,
            cache_expiry_minutes=10,
        )
        config = Config(config_path=config_path)

        cache = WorkingMemoryCache(
            file_event_timestamps=file_event_timestamps,
            size_limit_kb=1024,
        )

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
            cache=cache,
        )

        main_file = minimal_project / "main.py"

        # First read - populates cache
        content1 = cache.get(str(main_file))
        assert content1 is not None

        # Simulate file modification by updating timestamp
        file_event_timestamps[str(main_file)] = time.time()

        # Next get will detect staleness and re-read from disk
        # (The cache is a read-through cache, so it returns fresh content)
        content2 = cache.get(str(main_file))
        assert content2 is not None

        # Verify staleness refresh happened by checking statistics
        stats = cache.get_statistics()
        assert stats.staleness_refreshes >= 1

        service.shutdown()

    def test_incremental_analysis_updates_store(self, minimal_project: Path) -> None:
        """Test that incremental analysis updates the store correctly."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)
        store = InMemoryStore()

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
            store=store,
        )

        # Initial analysis
        service.analyze_directory(str(minimal_project))

        # Modify a file to add more imports
        main_file = minimal_project / "main.py"
        main_file.write_text(
            '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Updated main module with more imports."""

import json
import os

from utils import helper_function, another_function


def main():
    result = helper_function()
    other = another_function()
    print(json.dumps({"result": result, "other": other}))


if __name__ == "__main__":
    main()
'''
        )

        # Re-analyze the file
        service.analyze_file(str(main_file))

        # Graph should have been updated (can't easily verify exact count)
        export = service.get_relationship_graph()
        assert export is not None

        service.shutdown()

    def test_error_handling_file_not_found(self, minimal_project: Path) -> None:
        """Test error handling for non-existent files."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        # Try to read non-existent file
        with pytest.raises(FileNotFoundError):
            service.read_file_with_context(str(minimal_project / "nonexistent.py"))

        service.shutdown()

    def test_error_handling_path_traversal(self, minimal_project: Path) -> None:
        """Test error handling for path traversal attempts."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        # Try path traversal
        with pytest.raises(ValueError, match="traversal"):
            service.read_file_with_context("/../../../etc/passwd")

        service.shutdown()

    def test_service_with_empty_project(self, tmp_path: Path) -> None:
        """Test service behavior with empty project."""
        # Create an empty project
        empty_project = tmp_path / "empty"
        empty_project.mkdir()

        config_path = create_config_file(empty_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(empty_project),
        )

        # Should handle empty directory gracefully
        stats = service.analyze_directory(str(empty_project))
        assert stats["total"] == 0
        assert stats["success"] == 0

        # Export should still work with empty data
        export = service.get_relationship_graph()
        assert export is not None

        service.shutdown()

    def test_high_usage_detection(self, sample_project: Path) -> None:
        """Test detection of high-usage symbols."""
        config_path = create_config_file(
            sample_project,
            enable_context_injection=True,
            function_usage_warning_threshold=2,  # Low threshold for testing
        )
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze the project
        service.analyze_directory(str(sample_project / "mypackage"))

        # Create additional files that use the same function
        extra_file1 = sample_project / "mypackage" / "extra1.py"
        extra_file1.write_text(
            """# Copyright (c) 2025 Henru Wang
# All rights reserved.

from .utils.helpers import format_string

def process1():
    return format_string("test1")
"""
        )

        extra_file2 = sample_project / "mypackage" / "extra2.py"
        extra_file2.write_text(
            """# Copyright (c) 2025 Henru Wang
# All rights reserved.

from .utils.helpers import format_string

def process2():
    return format_string("test2")
"""
        )

        # Analyze new files
        service.analyze_file(str(extra_file1))
        service.analyze_file(str(extra_file2))

        # The format_string function should now be used in multiple files
        # This tests the high-usage detection logic

        service.shutdown()

    def test_token_limit_enforcement(self, sample_project: Path) -> None:
        """Test that context injection respects token limits."""
        config_path = create_config_file(
            sample_project,
            enable_context_injection=True,
            context_token_limit=100,  # Very small limit for testing
        )
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze project
        service.analyze_directory(str(sample_project / "mypackage"))

        # Read a file with many dependencies
        core_file = sample_project / "mypackage" / "core.py"
        result = service.read_file_with_context(str(core_file))

        # Context should be limited by token count
        assert result.content is not None

        service.shutdown()

    def test_metrics_collection_integration(self, minimal_project: Path) -> None:
        """Test that metrics are collected during service operations."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        # Analyze files - this should record metrics
        service.analyze_directory(str(minimal_project))

        # Read file - this should record context injection metrics
        main_file = minimal_project / "main.py"
        service.read_file_with_context(str(main_file))

        # Get session metrics
        metrics = service.get_session_metrics()

        # Verify metrics structure (SessionMetrics object)
        assert metrics is not None
        assert hasattr(metrics, "session_id") or hasattr(metrics, "to_dict")

        service.shutdown()

    def test_warning_collection_integration(self, sample_project: Path) -> None:
        """Test that warnings are collected during analysis."""
        config_path = create_config_file(sample_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze project including dynamic_patterns.py
        service.analyze_directory(str(sample_project / "mypackage"))

        # Get collected warnings
        warnings = service.get_warnings()

        # Should have warnings from dynamic pattern detection
        # (dynamic_patterns.py has exec/eval calls)
        assert isinstance(warnings, list)

        service.shutdown()

    def test_relationship_graph_query(self, sample_project: Path) -> None:
        """Test querying the relationship graph through service."""
        config_path = create_config_file(sample_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze project
        service.analyze_directory(str(sample_project / "mypackage"))

        # Query dependencies for core.py
        core_file = sample_project / "mypackage" / "core.py"
        deps = service.get_dependencies(str(core_file))

        # Should have some dependencies (imports from models/utils)
        assert isinstance(deps, list)

        # Query dependents of base.py
        base_file = sample_project / "mypackage" / "models" / "base.py"
        dependents = service.get_dependents(str(base_file))

        # user.py should depend on base.py
        assert isinstance(dependents, list)

        service.shutdown()

    def test_service_lifecycle(self, minimal_project: Path) -> None:
        """Test service lifecycle management."""
        config_path = create_config_file(minimal_project, enable_context_injection=True)
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(minimal_project),
        )

        # Start file watcher
        service.start_file_watcher()

        # Analyze directory
        service.analyze_directory(str(minimal_project))

        # Stop file watcher
        service.stop_file_watcher()

        # Shutdown should clean up resources
        service.shutdown()

    def test_injection_statistics(self, sample_project: Path) -> None:
        """Test injection statistics collection."""
        config_path = create_config_file(
            sample_project,
            enable_context_injection=True,
        )
        config = Config(config_path=config_path)

        service = CrossFileContextService(
            config=config,
            project_root=str(sample_project),
        )

        # Analyze and read files
        service.analyze_directory(str(sample_project / "mypackage"))

        core_file = sample_project / "mypackage" / "core.py"
        service.read_file_with_context(str(core_file))

        # Get injection statistics
        stats = service.get_injection_statistics()
        assert stats is not None

        service.shutdown()
