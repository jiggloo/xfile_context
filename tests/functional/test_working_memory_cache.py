# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
Functional Tests for Working Memory Cache (Test Category 3).

This module validates that working memory cache behavior works correctly
according to T-3.1 through T-3.5 from prd_testing.md Section 8.2.

Tests validate cache behavior through the CrossFileContextService integration
layer, ensuring proper cache hits, staleness detection, invalidation on edits,
LRU eviction, and accurate statistics tracking.

Test Cases:
- T-3.1: Verify cache hit for recently-read files
- T-3.2: Verify cache miss for old files (>10 min)
- T-3.3: Verify cache invalidation on file edit
- T-3.4: Verify cache size limit enforced (LRU eviction)
- T-3.5: Verify cache statistics accurate
"""

import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
from xfile_context.service import CrossFileContextService

# Path to the functional test codebase
TEST_CODEBASE_PATH = Path(__file__).parent / "test_codebase"
GROUND_TRUTH_PATH = TEST_CODEBASE_PATH / "ground_truth.json"

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def ground_truth() -> Dict[str, Any]:
    """Load ground truth manifest for validation."""
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


@pytest.fixture
def default_config():
    """Create default configuration for tests.

    Yields config and cleans up temporary file after test completes.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write("enable_context_injection: true\n")
        f.write("context_token_limit: 500\n")
        f.write("cache_expiry_minutes: 10\n")
        f.write("cache_size_limit_kb: 50\n")
        config_path = Path(f.name)

    yield Config(config_path)

    # Cleanup temporary config file
    config_path.unlink(missing_ok=True)


@pytest.fixture
def small_cache_config():
    """Create configuration with a small cache size for LRU eviction testing.

    Yields config and cleans up temporary file after test completes.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write("enable_context_injection: true\n")
        f.write("context_token_limit: 500\n")
        f.write("cache_expiry_minutes: 10\n")
        # Small cache size to trigger LRU eviction
        f.write("cache_size_limit_kb: 2\n")
        config_path = Path(f.name)

    yield Config(config_path)

    # Cleanup temporary config file
    config_path.unlink(missing_ok=True)


@pytest.fixture
def service_with_analyzed_codebase(
    default_config: Config,
) -> Generator[CrossFileContextService, None, None]:
    """Create a service with the test codebase already analyzed."""
    service = CrossFileContextService(
        config=default_config,
        project_root=str(TEST_CODEBASE_PATH),
    )

    # Analyze the test codebase
    service.analyze_directory(str(TEST_CODEBASE_PATH))

    yield service

    # Cleanup
    service.shutdown()


@pytest.fixture
def service_small_cache(
    small_cache_config: Config,
) -> Generator[CrossFileContextService, None, None]:
    """Create a service with a small cache for LRU eviction testing."""
    service = CrossFileContextService(
        config=small_cache_config,
        project_root=str(TEST_CODEBASE_PATH),
    )

    # Analyze the test codebase
    service.analyze_directory(str(TEST_CODEBASE_PATH))

    yield service

    # Cleanup
    service.shutdown()


class TestWorkingMemoryCache:
    """Functional tests for working memory cache (Test Category 3)."""

    def test_t_3_1_cache_hit_for_recently_read_files(
        self,
        service_with_analyzed_codebase: CrossFileContextService,
    ) -> None:
        """T-3.1: Verify cache hit for recently-read files.

        Tests that when a file is read through the cache, subsequent
        reads within the cache window result in cache hits.

        Note: The cache is used for reading dependency files during context
        injection, not for the main file read by read_file_with_context().
        This test validates direct cache behavior.
        """
        service = service_with_analyzed_codebase
        cache = service.cache

        # Read a file directly through the cache
        user_file = TEST_CODEBASE_PATH / "core" / "models" / "user.py"

        # First read - should be a cache miss
        stats_before = cache.get_statistics()
        initial_misses = stats_before.misses
        initial_hits = stats_before.hits

        content1 = cache.get(str(user_file))
        assert content1, "File content should be returned"

        stats_after_first = cache.get_statistics()
        # First read is a miss (file not in cache)
        assert stats_after_first.misses > initial_misses, "First read should be a cache miss"

        # Second read - should be a cache hit
        content2 = cache.get(str(user_file))
        assert content2 == content1, "Content should match on second read"

        stats_after_second = cache.get_statistics()
        # Second read should be a hit (file now in cache)
        assert stats_after_second.hits > initial_hits, "Second read should be a cache hit"

    def test_t_3_1_cache_content_consistency(
        self,
        service_with_analyzed_codebase: CrossFileContextService,
    ) -> None:
        """T-3.1: Verify cache returns consistent content.

        Tests that cached content matches the original file content
        and is consistent across multiple reads.
        """
        service = service_with_analyzed_codebase
        cache = service.cache

        # Read a file directly through the cache
        order_file = TEST_CODEBASE_PATH / "core" / "models" / "order.py"

        # First read
        content1 = cache.get(str(order_file))
        assert content1, "Cache should return content"

        # Second read
        content2 = cache.get(str(order_file))
        assert content2 == content1, "Cached content should be consistent"

        # Verify it matches actual file content
        with open(order_file) as f:
            actual_content = f.read()
        assert content1 == actual_content, "Cached content should match file"

    def test_t_3_2_cache_staleness_detection(
        self,
        default_config: Config,
    ) -> None:
        """T-3.2: Verify cache staleness detection (demand-driven refresh).

        Tests that the cache detects when a file has been modified and
        returns fresh content on the next read (demand-driven staleness
        per FR-15). Note: In v0.1.0, staleness is demand-driven, not
        time-based expiry.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = Path(tmpdir) / "test_module.py"
            test_file.write_text("# Original content\ndef foo(): pass\n")

            # Create service with test directory
            service = CrossFileContextService(
                config=default_config,
                project_root=tmpdir,
            )

            try:
                # Initialize file event timestamp
                service._file_watcher.file_event_timestamps[str(test_file)] = time.time()

                # First read - cache the file
                content1 = service.cache.get(str(test_file))
                assert "Original content" in content1

                # Modify the file
                time.sleep(0.01)  # Ensure timestamp difference
                test_file.write_text("# Modified content\ndef foo(): return 42\n")

                # Update file event timestamp (simulating file watcher detection)
                service._file_watcher.file_event_timestamps[str(test_file)] = time.time()

                # Second read - should detect staleness and refresh
                content2 = service.cache.get(str(test_file))
                assert "Modified content" in content2, "Cache should return fresh content"

                # Verify staleness refresh was recorded
                stats = service.cache.get_statistics()
                assert (
                    stats.staleness_refreshes >= 1
                ), "Cache should have recorded staleness refresh"

            finally:
                service.shutdown()

    def test_t_3_2_cache_expiry_awareness(
        self,
        default_config: Config,
    ) -> None:
        """T-3.2: Verify cache is aware of configured expiry time.

        Tests that the cache configuration includes the expiry time
        setting (10 minutes default per TDD Section 3.7).
        """
        # Verify default cache expiry is 10 minutes
        assert (
            default_config.cache_expiry_minutes == 10
        ), "Default cache expiry should be 10 minutes"

    def test_t_3_3_cache_invalidation_on_file_edit(
        self,
        default_config: Config,
    ) -> None:
        """T-3.3: Verify cache invalidation on file edit.

        Tests that when a file is edited (detected via file watcher),
        the cache entry is invalidated and subsequent reads return
        the new content.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file = Path(tmpdir) / "editable.py"
            test_file.write_text("def original(): pass\n")

            service = CrossFileContextService(
                config=default_config,
                project_root=tmpdir,
            )

            try:
                # Cache the file
                initial_content = service.cache.get(str(test_file))
                assert "original" in initial_content

                # Verify file is cached
                stats = service.cache.get_statistics()
                assert stats.current_entry_count >= 1, "File should be cached"

                # Edit the file
                test_file.write_text("def edited(): return True\n")

                # Invalidate the cache entry (simulating what file watcher would do)
                service.invalidate_cache(str(test_file))

                # Verify cache entry was removed
                stats = service.cache.get_statistics()
                assert (
                    stats.current_entry_count == 0
                ), "Cache entry should be removed after invalidation"

                # Read again - should get fresh content
                new_content = service.cache.get(str(test_file))
                assert "edited" in new_content, "Should get fresh content after edit"

            finally:
                service.shutdown()

    def test_t_3_3_cache_invalidation_integration_with_service(
        self,
        service_with_analyzed_codebase: CrossFileContextService,
    ) -> None:
        """T-3.3: Verify cache invalidation through service layer.

        Tests the service.invalidate_cache() method clears cache entries.
        """
        service = service_with_analyzed_codebase
        cache = service.cache

        # Read some files to populate cache
        user_file = TEST_CODEBASE_PATH / "core" / "models" / "user.py"
        order_file = TEST_CODEBASE_PATH / "core" / "models" / "order.py"

        cache.get(str(user_file))
        cache.get(str(order_file))

        stats = cache.get_statistics()
        assert stats.current_entry_count >= 2, "Cache should have entries"

        # Invalidate specific file
        service.invalidate_cache(str(user_file))

        # Read the invalidated file again (should re-cache)
        content = cache.get(str(user_file))
        assert content, "Should be able to re-read after invalidation"

        # Clear entire cache
        service.invalidate_cache()  # No file_path = clear all

        stats = cache.get_statistics()
        assert stats.current_entry_count == 0, "Cache should be empty after clear"

    def test_t_3_4_lru_eviction_on_size_limit(
        self,
        service_small_cache: CrossFileContextService,
    ) -> None:
        """T-3.4: Verify cache size limit enforced (LRU eviction).

        Tests that when the cache size limit is reached, least-recently-used
        entries are evicted to make room for new entries.
        """
        service = service_small_cache
        cache = service.cache

        # Get the cache size limit
        size_limit_bytes = cache._size_limit_bytes
        assert size_limit_bytes == 2 * 1024, "Cache limit should be 2KB"

        # Read multiple files to exceed cache limit
        files_to_read = [
            TEST_CODEBASE_PATH / "core" / "models" / "user.py",
            TEST_CODEBASE_PATH / "core" / "models" / "order.py",
            TEST_CODEBASE_PATH / "core" / "models" / "base.py",
            TEST_CODEBASE_PATH / "core" / "services" / "user_service.py",
            TEST_CODEBASE_PATH / "core" / "services" / "order_service.py",
        ]

        for file_path in files_to_read:
            if file_path.exists():
                cache.get(str(file_path))

        # Verify evictions occurred
        stats = cache.get_statistics()
        assert stats.evictions_lru > 0, "LRU evictions should have occurred"

        # Verify current size is within limit
        assert stats.current_size_bytes <= size_limit_bytes, (
            f"Current size ({stats.current_size_bytes}B) should not exceed limit "
            f"({size_limit_bytes}B)"
        )

    def test_t_3_4_lru_eviction_order(
        self,
        small_cache_config: Config,
    ) -> None:
        """T-3.4: Verify LRU eviction removes least-recently-used entries.

        Tests that the eviction policy correctly identifies and removes
        the entries that were accessed least recently.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files with predictable sizes
            file_a = Path(tmpdir) / "file_a.py"
            file_b = Path(tmpdir) / "file_b.py"
            file_c = Path(tmpdir) / "file_c.py"

            # Each file is ~800 bytes (2KB cache = room for ~2 files)
            file_a.write_text("a" * 800)
            file_b.write_text("b" * 800)
            file_c.write_text("c" * 800)

            file_event_timestamps: Dict[str, float] = {}
            cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=2)

            # Cache file_a (oldest)
            cache.get(str(file_a))
            time.sleep(0.01)

            # Cache file_b (second oldest)
            cache.get(str(file_b))
            time.sleep(0.01)

            # Access file_a again (makes it more recent than file_b)
            cache.get(str(file_a))

            # Cache file_c - should evict file_b (least recently used)
            cache.get(str(file_c))

            # file_a should still be cached (more recently used)
            stats_before = cache.get_statistics()
            _ = cache.get(str(file_a))  # Read file_a to check cache hit
            stats_after = cache.get_statistics()

            # If file_a is cached, this should be a hit (not a miss)
            assert (
                stats_after.hits > stats_before.hits
            ), "file_a should still be cached (was accessed more recently than file_b)"

    def test_t_3_5_cache_statistics_accuracy(
        self,
        service_with_analyzed_codebase: CrossFileContextService,
    ) -> None:
        """T-3.5: Verify cache statistics accurate.

        Tests that cache statistics (hits, misses, evictions, size)
        are accurately tracked and reported.
        """
        service = service_with_analyzed_codebase
        cache = service.cache

        # Get initial statistics
        initial_stats = cache.get_statistics()

        # Read a new file (should be a miss)
        helpers_file = TEST_CODEBASE_PATH / "core" / "utils" / "helpers.py"
        if helpers_file.exists():
            cache.get(str(helpers_file))

            # Check statistics after miss
            after_miss = cache.get_statistics()
            assert after_miss.misses == initial_stats.misses + 1, "Miss count should increment"

            # Read the same file (should be a hit)
            cache.get(str(helpers_file))

            after_hit = cache.get_statistics()
            assert after_hit.hits == after_miss.hits + 1, "Hit count should increment"

    def test_t_3_5_cache_statistics_size_tracking(
        self,
        default_config: Config,
    ) -> None:
        """T-3.5: Verify cache size statistics are accurate.

        Tests that current_size_bytes and peak_size_bytes are
        correctly tracked as entries are added and removed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files with known sizes
            file1 = Path(tmpdir) / "file1.py"
            file2 = Path(tmpdir) / "file2.py"
            content1 = "x" * 100
            content2 = "y" * 200
            file1.write_text(content1)
            file2.write_text(content2)

            file_event_timestamps: Dict[str, float] = {}
            cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=50)

            # Initial stats
            stats = cache.get_statistics()
            assert stats.current_size_bytes == 0, "Initial size should be 0"
            assert stats.current_entry_count == 0, "Initial entry count should be 0"

            # Add first file
            cache.get(str(file1))
            stats = cache.get_statistics()
            assert stats.current_size_bytes >= 100, "Size should account for file1"
            assert stats.current_entry_count == 1, "Should have 1 entry"

            # Add second file
            cache.get(str(file2))
            stats = cache.get_statistics()
            assert stats.current_size_bytes >= 300, "Size should account for both files"
            assert stats.current_entry_count == 2, "Should have 2 entries"
            assert stats.peak_size_bytes >= stats.current_size_bytes, "Peak should be >= current"

            # Clear and verify
            cache.clear()
            stats = cache.get_statistics()
            assert stats.current_size_bytes == 0, "Size should be 0 after clear"
            assert stats.current_entry_count == 0, "Entry count should be 0 after clear"
            assert stats.peak_size_bytes > 0, "Peak should persist after clear"

    def test_t_3_5_cache_hit_rate_calculation(
        self,
        default_config: Config,
    ) -> None:
        """T-3.5: Verify cache hit rate is calculated correctly.

        Tests that get_hit_rate() returns accurate percentages.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("content")

            file_event_timestamps: Dict[str, float] = {}
            cache = WorkingMemoryCache(file_event_timestamps)

            # Initial hit rate (no reads)
            assert cache.get_hit_rate() == 0.0, "Hit rate should be 0% with no reads"

            # First read (miss)
            cache.get(str(test_file))
            assert cache.get_hit_rate() == 0.0, "Hit rate should be 0% after one miss"

            # Three more reads (hits)
            cache.get(str(test_file))
            cache.get(str(test_file))
            cache.get(str(test_file))

            # Hit rate should be 75% (3 hits / 4 total reads)
            hit_rate = cache.get_hit_rate()
            assert 74.0 <= hit_rate <= 76.0, f"Hit rate should be ~75%, got {hit_rate}%"


class TestWorkingMemoryCacheEdgeCases:
    """Edge case tests for working memory cache."""

    def test_cache_with_empty_file(
        self,
        default_config: Config,
    ) -> None:
        """Test cache behavior with empty files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_file = Path(tmpdir) / "empty.py"
            empty_file.write_text("")

            file_event_timestamps: Dict[str, float] = {}
            cache = WorkingMemoryCache(file_event_timestamps)

            content = cache.get(str(empty_file))
            assert content == "", "Empty file should return empty string"

            stats = cache.get_statistics()
            assert stats.current_entry_count == 1, "Empty file should still be cached"

    def test_cache_with_large_file_exceeding_limit(
        self,
        small_cache_config: Config,
    ) -> None:
        """Test cache behavior with file larger than cache limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file larger than 2KB cache limit
            large_file = Path(tmpdir) / "large.py"
            large_file.write_text("x" * 5000)  # 5KB

            file_event_timestamps: Dict[str, float] = {}
            cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=2)

            # Read should still work (content returned) but not cached
            content = cache.get(str(large_file))
            assert len(content) == 5000, "Large file content should be returned"

            stats = cache.get_statistics()
            assert stats.current_entry_count == 0, "Large file should not be cached"
            assert stats.misses == 1, "Should count as a miss"

    def test_cache_unicode_content(
        self,
        default_config: Config,
    ) -> None:
        """Test cache handles unicode content correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            unicode_file = Path(tmpdir) / "unicode.py"
            unicode_content = (
                "# Unicode test: \u4e2d\u6587\u3053\u3093\u306b\u3061\u306f\ndef foo(): pass\n"
            )
            unicode_file.write_text(unicode_content)

            file_event_timestamps: Dict[str, float] = {}
            cache = WorkingMemoryCache(file_event_timestamps)

            content = cache.get(str(unicode_file))
            assert content == unicode_content, "Unicode content should be preserved"

    def test_cache_line_range_snippets(
        self,
        service_with_analyzed_codebase: CrossFileContextService,
    ) -> None:
        """Test cache with line range snippets."""
        service = service_with_analyzed_codebase
        cache = service.cache

        # Get a file with multiple lines
        user_file = TEST_CODEBASE_PATH / "core" / "models" / "user.py"
        if not user_file.exists():
            pytest.skip("Test file not found")

        # Read full file
        full_content = cache.get(str(user_file))
        lines = full_content.splitlines()
        if len(lines) < 5:
            pytest.skip("Test file too small")

        # Read a snippet (lines 2-4)
        snippet = cache.get(str(user_file), line_range=(2, 4))
        expected_lines = lines[1:4]  # 0-indexed
        expected = "\n".join(expected_lines)
        if expected_lines:
            expected += "\n"

        assert snippet == expected, "Snippet should match expected lines"

    def test_cache_statistics_persistence_after_eviction(
        self,
        small_cache_config: Config,
    ) -> None:
        """Test that statistics persist correctly through evictions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple files
            files = []
            for i in range(10):
                f = Path(tmpdir) / f"file{i}.py"
                f.write_text("x" * 400)  # Each ~400 bytes, 2KB cache fits ~5
                files.append(str(f))

            file_event_timestamps: Dict[str, float] = {}
            cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=2)

            # Read all files to trigger multiple evictions
            for filepath in files:
                cache.get(filepath)

            stats = cache.get_statistics()

            # Verify statistics are consistent
            assert stats.evictions_lru > 0, "Evictions should have occurred"
            assert stats.misses == 10, "All reads were misses"
            assert stats.current_size_bytes <= 2 * 1024, "Size within limit"
            assert stats.peak_size_bytes > 0, "Peak size should be recorded"
            assert stats.peak_entry_count > 0, "Peak entry count should be recorded"
