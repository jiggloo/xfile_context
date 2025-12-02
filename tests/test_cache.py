# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Unit tests for WorkingMemoryCache.

Tests coverage (TDD Section 3.13.2, T-3):
- T-3.1: Cache hit/miss behavior
- T-3.2: LRU eviction when size limit exceeded
- T-3.3: Staleness detection and automatic refresh
- T-3.4: Statistics tracking (hit rate, misses, evictions)
- T-3.5: Thread safety (concurrent access)

Edge Cases:
- EC-15: Cache size exceeded triggers eviction
- EC-16: Long-running sessions with many cache operations
"""

import os
import time
from pathlib import Path
from threading import Thread
from typing import Dict

import pytest

from xfile_context.cache import WorkingMemoryCache


class TestCacheBasics:
    """Test basic cache operations (T-3.1)."""

    def test_cache_miss_then_hit(self, tmp_path: Path) -> None:
        """Test cache miss on first access, hit on second access."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass\n")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=50)

        # First access - cache miss
        content1 = cache.get(str(test_file))
        assert content1 == "def foo(): pass\n"
        stats = cache.get_statistics()
        assert stats.misses == 1
        assert stats.hits == 0

        # Second access - cache hit (no file modification)
        content2 = cache.get(str(test_file))
        assert content2 == "def foo(): pass\n"
        stats = cache.get_statistics()
        assert stats.hits == 1
        assert stats.misses == 1

    def test_cache_full_file(self, tmp_path: Path) -> None:
        """Test caching full file content."""
        # Setup
        test_file = tmp_path / "test.py"
        content = "line 1\nline 2\nline 3\n"
        test_file.write_text(content)
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Get full file
        result = cache.get(str(test_file))
        assert result == content

    def test_cache_snippet_with_line_range(self, tmp_path: Path) -> None:
        """Test caching file snippet with line range."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("line 1\nline 2\nline 3\nline 4\n")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Get snippet (lines 2-3)
        result = cache.get(str(test_file), line_range=(2, 3))
        assert result == "line 2\nline 3\n"

    def test_cache_snippet_clamping(self, tmp_path: Path) -> None:
        """Test line range clamping for out-of-bounds requests."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("line 1\nline 2\n")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Request range beyond file length
        result = cache.get(str(test_file), line_range=(1, 100))
        assert result == "line 1\nline 2\n"

    def test_cache_invalidate(self, tmp_path: Path) -> None:
        """Test manual cache invalidation."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("original")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Cache the file
        cache.get(str(test_file))
        stats = cache.get_statistics()
        assert stats.current_entry_count == 1

        # Invalidate
        cache.invalidate(str(test_file))
        stats = cache.get_statistics()
        assert stats.current_entry_count == 0

    def test_cache_clear(self, tmp_path: Path) -> None:
        """Test clearing entire cache."""
        # Setup
        test_file1 = tmp_path / "test1.py"
        test_file2 = tmp_path / "test2.py"
        test_file1.write_text("file1")
        test_file2.write_text("file2")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Cache multiple files
        cache.get(str(test_file1))
        cache.get(str(test_file2))
        stats = cache.get_statistics()
        assert stats.current_entry_count == 2

        # Clear
        cache.clear()
        stats = cache.get_statistics()
        assert stats.current_entry_count == 0
        assert stats.current_size_bytes == 0


class TestStalenessDetection:
    """Test staleness detection and automatic refresh (T-3.3)."""

    def test_staleness_with_watcher_timestamp(self, tmp_path: Path) -> None:
        """Test staleness detection using FileWatcher timestamps."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("original content")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Initial cache
        t1 = time.time()
        file_event_timestamps[str(test_file)] = t1
        content1 = cache.get(str(test_file))
        assert content1 == "original content"

        # Modify file and update watcher timestamp
        time.sleep(0.01)  # Ensure timestamp difference
        test_file.write_text("modified content")
        t2 = time.time()
        file_event_timestamps[str(test_file)] = t2

        # Next access should detect staleness and refresh
        content2 = cache.get(str(test_file))
        assert content2 == "modified content"
        stats = cache.get_statistics()
        assert stats.staleness_refreshes >= 1

    def test_staleness_fallback_to_mtime(self, tmp_path: Path) -> None:
        """Test staleness detection fallback using mtime when watcher not tracking."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("original content")
        file_event_timestamps: Dict[str, float] = {}  # Empty, watcher not tracking
        cache = WorkingMemoryCache(file_event_timestamps)

        # Initial cache
        content1 = cache.get(str(test_file))
        assert content1 == "original content"

        # Modify file (wait to ensure mtime changes)
        time.sleep(0.01)
        test_file.write_text("modified content")
        # Update mtime explicitly to ensure it's newer
        new_mtime = time.time()
        os.utime(str(test_file), (new_mtime, new_mtime))

        # Next access should detect staleness via mtime fallback
        content2 = cache.get(str(test_file))
        assert content2 == "modified content"

    def test_no_staleness_when_file_unchanged(self, tmp_path: Path) -> None:
        """Test that unchanged files are not marked stale."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        t1 = time.time()
        file_event_timestamps: Dict[str, float] = {str(test_file): t1}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Cache the file
        cache.get(str(test_file))
        stats1 = cache.get_statistics()

        # Access again without modification
        cache.get(str(test_file))
        stats2 = cache.get_statistics()

        # Should be a hit, not a refresh
        assert stats2.hits == stats1.hits + 1
        assert stats2.staleness_refreshes == stats1.staleness_refreshes


class TestLRUEviction:
    """Test LRU eviction policy (T-3.2, EC-15)."""

    def test_lru_eviction_on_size_limit(self, tmp_path: Path) -> None:
        """Test LRU eviction when cache size limit exceeded."""
        # Setup - very small cache (1KB)
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=1)

        # Create files that together exceed 1KB
        files = []
        for i in range(5):
            test_file = tmp_path / f"test{i}.py"
            # Each file ~300 bytes
            test_file.write_text(f"# File {i}\n" + "x" * 300)
            files.append(str(test_file))

        # Cache first 3 files (should fit in 1KB)
        for i in range(3):
            cache.get(files[i])

        stats = cache.get_statistics()
        initial_count = stats.current_entry_count
        assert initial_count <= 3

        # Cache 4th file (should trigger eviction)
        cache.get(files[3])

        stats = cache.get_statistics()
        assert stats.evictions_lru > 0
        assert stats.current_size_bytes <= cache._size_limit_bytes

    def test_lru_evicts_least_recently_used(self, tmp_path: Path) -> None:
        """Test that LRU eviction removes least recently used entries."""
        # Setup - very small cache
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=1)

        # Create files
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        file3 = tmp_path / "file3.py"
        file1.write_text("x" * 400)
        file2.write_text("y" * 400)
        file3.write_text("z" * 400)

        # Cache file1 and file2
        cache.get(str(file1))
        time.sleep(0.01)
        cache.get(str(file2))

        # Access file1 again (make it more recently used than file2)
        time.sleep(0.01)
        cache.get(str(file1))

        # Cache file3 (should evict file2, not file1)
        cache.get(str(file3))

        # Try to access file1 (should be cache hit)
        stats_before = cache.get_statistics()
        cache.get(str(file1))
        stats_after = cache.get_statistics()

        # file1 should still be cached (hit count increases)
        assert stats_after.hits == stats_before.hits + 1

    def test_access_updates_lru_order(self, tmp_path: Path) -> None:
        """Test that accessing an entry moves it to MRU position."""
        # Setup
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=50)

        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        file1.write_text("content1")
        file2.write_text("content2")

        # Cache both files
        cache.get(str(file1))
        cache.get(str(file2))

        # Access file1 again (should update access time)
        time.sleep(0.01)
        cache.get(str(file1))

        # Verify access count increased
        stats = cache.get_statistics()
        assert stats.hits >= 1


class TestCacheStatistics:
    """Test cache statistics tracking (T-3.4)."""

    def test_statistics_hit_miss_counts(self, tmp_path: Path) -> None:
        """Test hit and miss statistics."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # First access (miss)
        cache.get(str(test_file))
        stats = cache.get_statistics()
        assert stats.misses == 1
        assert stats.hits == 0

        # Second access (hit)
        cache.get(str(test_file))
        stats = cache.get_statistics()
        assert stats.hits == 1
        assert stats.misses == 1

    def test_statistics_size_tracking(self, tmp_path: Path) -> None:
        """Test cache size statistics."""
        # Setup
        test_file = tmp_path / "test.py"
        content = "x" * 1000
        test_file.write_text(content)
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Cache file
        cache.get(str(test_file))
        stats = cache.get_statistics()

        # Size should be tracked
        assert stats.current_size_bytes > 0
        assert stats.peak_size_bytes >= stats.current_size_bytes
        assert stats.current_entry_count == 1
        assert stats.peak_entry_count >= stats.current_entry_count

    def test_statistics_eviction_count(self, tmp_path: Path) -> None:
        """Test eviction statistics."""
        # Setup - small cache
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=1)

        # Create files that exceed limit
        files = []
        for i in range(5):
            test_file = tmp_path / f"test{i}.py"
            test_file.write_text("x" * 400)
            files.append(str(test_file))
            cache.get(str(test_file))

        # Check eviction count
        stats = cache.get_statistics()
        assert stats.evictions_lru > 0

    def test_hit_rate_calculation(self, tmp_path: Path) -> None:
        """Test hit rate percentage calculation."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # First access (miss)
        cache.get(str(test_file))
        assert cache.get_hit_rate() == 0.0

        # Three more accesses (hits)
        cache.get(str(test_file))
        cache.get(str(test_file))
        cache.get(str(test_file))

        # Hit rate should be 75% (3 hits / 4 total)
        hit_rate = cache.get_hit_rate()
        assert 74.0 <= hit_rate <= 76.0  # Allow small floating point variance

    def test_statistics_peak_values(self, tmp_path: Path) -> None:
        """Test peak size and entry count tracking."""
        # Setup
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=50)

        # Cache multiple files
        files = []
        for i in range(3):
            test_file = tmp_path / f"test{i}.py"
            test_file.write_text("x" * 100)
            files.append(str(test_file))
            cache.get(str(test_file))

        stats = cache.get_statistics()
        peak_size = stats.peak_size_bytes
        peak_count = stats.peak_entry_count

        # Clear cache
        cache.clear()
        stats = cache.get_statistics()

        # Peak values should persist
        assert stats.peak_size_bytes == peak_size
        assert stats.peak_entry_count == peak_count
        assert stats.current_size_bytes == 0
        assert stats.current_entry_count == 0


class TestFileReadRetry:
    """Test file read retry logic."""

    def test_successful_read_first_try(self, tmp_path: Path) -> None:
        """Test successful file read on first attempt."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps, max_retries=3)

        # Should succeed immediately
        content = cache.get(str(test_file))
        assert content == "content"

    def test_file_not_found_error(self, tmp_path: Path) -> None:
        """Test FileNotFoundError for non-existent file."""
        # Setup
        non_existent = tmp_path / "nonexistent.py"
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            cache.get(str(non_existent))


class TestThreadSafety:
    """Test thread safety of cache operations (T-3.5)."""

    def test_concurrent_reads(self, tmp_path: Path) -> None:
        """Test concurrent reads from multiple threads."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("shared content")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        results = []
        errors = []

        def read_file():
            try:
                content = cache.get(str(test_file))
                results.append(content)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [Thread(target=read_file) for _ in range(10)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Verify no errors and all reads succeeded
        assert len(errors) == 0
        assert len(results) == 10
        assert all(r == "shared content" for r in results)

    def test_concurrent_reads_and_writes(self, tmp_path: Path) -> None:
        """Test concurrent reads with file modifications."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("initial")
        file_event_timestamps: Dict[str, float] = {str(test_file): time.time()}
        cache = WorkingMemoryCache(file_event_timestamps)

        errors = []

        def read_file():
            try:
                cache.get(str(test_file))
            except Exception as e:
                errors.append(e)

        def modify_file():
            try:
                time.sleep(0.01)
                test_file.write_text("modified")
                file_event_timestamps[str(test_file)] = time.time()
            except Exception as e:
                errors.append(e)

        # Create threads
        threads = []
        threads.extend([Thread(target=read_file) for _ in range(5)])
        threads.append(Thread(target=modify_file))
        threads.extend([Thread(target=read_file) for _ in range(5)])

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0


class TestEdgeCases:
    """Test edge cases (EC-15, EC-16)."""

    def test_empty_file(self, tmp_path: Path) -> None:
        """Test caching empty file."""
        # Setup
        test_file = tmp_path / "empty.py"
        test_file.write_text("")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Cache empty file
        content = cache.get(str(test_file))
        assert content == ""
        stats = cache.get_statistics()
        assert stats.current_entry_count == 1

    def test_very_large_file(self, tmp_path: Path) -> None:
        """Test caching file larger than cache size limit."""
        # Setup - 1KB cache limit
        test_file = tmp_path / "large.py"
        # Create 2KB file
        test_file.write_text("x" * 2048)
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=1)

        # Cache large file (should skip caching but return content)
        content = cache.get(str(test_file))
        assert len(content) == 2048

        stats = cache.get_statistics()
        # File should not be cached (too large)
        assert stats.current_size_bytes == 0
        assert stats.current_entry_count == 0
        # Should count as a miss
        assert stats.misses == 1

    def test_many_cache_operations(self, tmp_path: Path) -> None:
        """Test long-running session with many operations (EC-16)."""
        # Setup
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps, size_limit_kb=10)

        # Create multiple files
        files = []
        for i in range(20):
            test_file = tmp_path / f"file{i}.py"
            test_file.write_text(f"content {i}")
            files.append(str(test_file))

        # Perform many operations
        for _ in range(100):
            for filepath in files:
                cache.get(filepath)

        # Cache should remain stable
        stats = cache.get_statistics()
        assert stats.hits > 0
        assert stats.current_size_bytes <= cache._size_limit_bytes

    def test_unicode_content(self, tmp_path: Path) -> None:
        """Test caching file with unicode content."""
        # Setup
        test_file = tmp_path / "unicode.py"
        test_file.write_text("# 中文注释\ndef foo(): pass\n")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Cache and retrieve
        content = cache.get(str(test_file))
        assert "中文注释" in content

    def test_line_range_edge_cases(self, tmp_path: Path) -> None:
        """Test line range with edge cases."""
        # Setup
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")
        file_event_timestamps: Dict[str, float] = {}
        cache = WorkingMemoryCache(file_event_timestamps)

        # Test: Start line beyond file length
        result = cache.get(str(test_file), line_range=(100, 200))
        assert result == ""

        # Test: Single line
        result = cache.get(str(test_file), line_range=(2, 2))
        assert result == "line2\n"
