# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for SymbolDataCache (Issue #125 Phase 3).

Tests symbol data caching functionality including:
- Basic cache operations (get, set, invalidate)
- Cache validation based on file modification time
- LRU eviction when max entries reached
- Statistics tracking
- Persistence to disk
"""

import os
import time
from pathlib import Path

import pytest

from xfile_context.models import FileSymbolData, SymbolDefinition, SymbolType
from xfile_context.symbol_cache import CacheEntry, SymbolDataCache


class TestCacheEntry:
    """Tests for CacheEntry class."""

    def test_cache_entry_creation(self) -> None:
        """Test creating a cache entry."""
        symbol_data = FileSymbolData(
            filepath="/test/file.py",
            definitions=[],
            references=[],
            parse_time=time.time(),
            is_valid=True,
        )
        entry = CacheEntry(
            symbol_data=symbol_data,
            file_mtime=1234567890.0,
        )

        assert entry.symbol_data == symbol_data
        assert entry.file_mtime == 1234567890.0
        assert entry.file_hash is None
        assert entry.access_count == 0

    def test_cache_entry_touch(self) -> None:
        """Test touching a cache entry updates access stats."""
        symbol_data = FileSymbolData(
            filepath="/test/file.py",
            definitions=[],
            references=[],
            parse_time=time.time(),
            is_valid=True,
        )
        entry = CacheEntry(symbol_data=symbol_data, file_mtime=0)

        initial_access = entry.last_accessed
        time.sleep(0.01)  # Small delay
        entry.touch()

        assert entry.access_count == 1
        assert entry.last_accessed > initial_access


class TestSymbolDataCacheBasics:
    """Tests for basic SymbolDataCache operations."""

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary Python file."""
        file_path = tmp_path / "test_file.py"
        file_path.write_text("def hello():\n    pass\n")
        return file_path

    @pytest.fixture
    def symbol_data(self, temp_file: Path) -> FileSymbolData:
        """Create sample FileSymbolData."""
        return FileSymbolData(
            filepath=str(temp_file),
            definitions=[
                SymbolDefinition(
                    name="hello",
                    symbol_type=SymbolType.FUNCTION,
                    line_start=1,
                    line_end=2,
                    signature="def hello()",
                )
            ],
            references=[],
            parse_time=time.time(),
            is_valid=True,
        )

    def test_cache_set_and_get(self, temp_file: Path, symbol_data: FileSymbolData) -> None:
        """Test basic set and get operations."""
        cache = SymbolDataCache()

        cache.set(str(temp_file), symbol_data)
        result = cache.get(str(temp_file))

        assert result is not None
        assert result.filepath == symbol_data.filepath
        assert len(result.definitions) == 1
        assert result.definitions[0].name == "hello"

    def test_cache_miss_returns_none(self) -> None:
        """Test cache miss returns None."""
        cache = SymbolDataCache()
        result = cache.get("/nonexistent/file.py")
        assert result is None

    def test_is_valid_returns_true_for_cached(
        self, temp_file: Path, symbol_data: FileSymbolData
    ) -> None:
        """Test is_valid returns True for cached entries."""
        cache = SymbolDataCache()
        cache.set(str(temp_file), symbol_data)

        assert cache.is_valid(str(temp_file)) is True

    def test_is_valid_returns_false_for_uncached(self) -> None:
        """Test is_valid returns False for uncached files."""
        cache = SymbolDataCache()
        assert cache.is_valid("/nonexistent/file.py") is False

    def test_invalidate_removes_entry(self, temp_file: Path, symbol_data: FileSymbolData) -> None:
        """Test invalidate removes cache entry."""
        cache = SymbolDataCache()
        cache.set(str(temp_file), symbol_data)

        cache.invalidate(str(temp_file))

        assert cache.get(str(temp_file)) is None
        assert cache.is_valid(str(temp_file)) is False

    def test_invalidate_all_clears_cache(
        self, temp_file: Path, symbol_data: FileSymbolData
    ) -> None:
        """Test invalidate_all clears all entries."""
        cache = SymbolDataCache()
        cache.set(str(temp_file), symbol_data)

        cache.invalidate_all()

        assert cache.get(str(temp_file)) is None
        stats = cache.get_statistics()
        assert stats["entries"] == 0


class TestCacheInvalidation:
    """Tests for cache invalidation based on file changes."""

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary Python file."""
        file_path = tmp_path / "test_file.py"
        file_path.write_text("def hello():\n    pass\n")
        return file_path

    @pytest.fixture
    def symbol_data(self, temp_file: Path) -> FileSymbolData:
        """Create sample FileSymbolData."""
        return FileSymbolData(
            filepath=str(temp_file),
            definitions=[],
            references=[],
            parse_time=time.time(),
            is_valid=True,
        )

    def test_cache_invalidated_when_file_modified(
        self, temp_file: Path, symbol_data: FileSymbolData
    ) -> None:
        """Test cache is invalidated when file is modified."""
        cache = SymbolDataCache()
        cache.set(str(temp_file), symbol_data)

        # Modify the file
        time.sleep(0.1)  # Ensure mtime changes
        temp_file.write_text("def goodbye():\n    pass\n")

        # Cache should be invalid
        assert cache.is_valid(str(temp_file)) is False
        assert cache.get(str(temp_file)) is None

    def test_cache_invalidated_when_file_deleted(
        self, temp_file: Path, symbol_data: FileSymbolData
    ) -> None:
        """Test cache is invalidated when file is deleted."""
        cache = SymbolDataCache()
        cache.set(str(temp_file), symbol_data)

        # Delete the file
        temp_file.unlink()

        # Cache should be invalid
        assert cache.is_valid(str(temp_file)) is False
        assert cache.get(str(temp_file)) is None


class TestCacheLRUEviction:
    """Tests for LRU eviction when cache is full."""

    def test_eviction_when_max_entries_reached(self, tmp_path: Path) -> None:
        """Test LRU eviction when max entries reached."""
        cache = SymbolDataCache(max_entries=3)

        # Create 4 files
        files = []
        for i in range(4):
            file_path = tmp_path / f"file_{i}.py"
            file_path.write_text(f"# File {i}\n")
            files.append(file_path)

            symbol_data = FileSymbolData(
                filepath=str(file_path),
                definitions=[],
                references=[],
                parse_time=time.time(),
                is_valid=True,
            )
            cache.set(str(file_path), symbol_data)

        # First file should be evicted
        assert cache.get(str(files[0])) is None
        # Other files should be present
        assert cache.get(str(files[1])) is not None
        assert cache.get(str(files[2])) is not None
        assert cache.get(str(files[3])) is not None

    def test_recently_accessed_not_evicted(self, tmp_path: Path) -> None:
        """Test recently accessed entries are not evicted."""
        cache = SymbolDataCache(max_entries=2)

        # Create first file and cache it
        file1 = tmp_path / "file1.py"
        file1.write_text("# File 1\n")
        data1 = FileSymbolData(
            filepath=str(file1), definitions=[], references=[], parse_time=0, is_valid=True
        )
        cache.set(str(file1), data1)

        # Create second file
        file2 = tmp_path / "file2.py"
        file2.write_text("# File 2\n")
        data2 = FileSymbolData(
            filepath=str(file2), definitions=[], references=[], parse_time=0, is_valid=True
        )
        cache.set(str(file2), data2)

        # Access first file (moves it to end)
        cache.get(str(file1))

        # Create third file - should evict file2, not file1
        file3 = tmp_path / "file3.py"
        file3.write_text("# File 3\n")
        data3 = FileSymbolData(
            filepath=str(file3), definitions=[], references=[], parse_time=0, is_valid=True
        )
        cache.set(str(file3), data3)

        # file1 was recently accessed, so file2 should be evicted
        assert cache.get(str(file1)) is not None
        assert cache.get(str(file2)) is None
        assert cache.get(str(file3)) is not None


class TestCacheStatistics:
    """Tests for cache statistics tracking."""

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary Python file."""
        file_path = tmp_path / "test_file.py"
        file_path.write_text("def hello():\n    pass\n")
        return file_path

    def test_statistics_tracking(self, temp_file: Path) -> None:
        """Test statistics are tracked correctly."""
        cache = SymbolDataCache(max_entries=100)

        # Initial stats
        stats = cache.get_statistics()
        assert stats["entries"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # Cache miss
        cache.get(str(temp_file))
        stats = cache.get_statistics()
        assert stats["misses"] == 1

        # Cache set
        symbol_data = FileSymbolData(
            filepath=str(temp_file),
            definitions=[],
            references=[],
            parse_time=0,
            is_valid=True,
        )
        cache.set(str(temp_file), symbol_data)
        stats = cache.get_statistics()
        assert stats["entries"] == 1

        # Cache hit
        cache.get(str(temp_file))
        stats = cache.get_statistics()
        assert stats["hits"] == 1
        assert stats["hit_rate"] == 0.5  # 1 hit / 2 total

    def test_get_cached_files(self, tmp_path: Path) -> None:
        """Test get_cached_files returns valid entries."""
        cache = SymbolDataCache()

        # Create and cache files
        files = []
        for i in range(3):
            file_path = tmp_path / f"file_{i}.py"
            file_path.write_text(f"# File {i}\n")
            files.append(file_path)

            symbol_data = FileSymbolData(
                filepath=str(file_path),
                definitions=[],
                references=[],
                parse_time=0,
                is_valid=True,
            )
            cache.set(str(file_path), symbol_data)

        cached_files = cache.get_cached_files()
        assert len(cached_files) == 3
        for file in files:
            assert str(file) in cached_files


class TestCachePersistence:
    """Tests for cache persistence to disk."""

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary Python file."""
        file_path = tmp_path / "test_file.py"
        file_path.write_text("def hello():\n    pass\n")
        return file_path

    def test_persist_and_load(self, tmp_path: Path, temp_file: Path) -> None:
        """Test persisting cache to disk and loading it back."""
        cache_file = tmp_path / "symbol_cache.json"

        # Create cache and add entry
        cache1 = SymbolDataCache(persist_path=cache_file)
        symbol_data = FileSymbolData(
            filepath=str(temp_file),
            definitions=[
                SymbolDefinition(
                    name="hello",
                    symbol_type=SymbolType.FUNCTION,
                    line_start=1,
                    line_end=2,
                )
            ],
            references=[],
            parse_time=time.time(),
            is_valid=True,
        )
        cache1.set(str(temp_file), symbol_data)
        cache1.persist()

        # Create new cache from persisted data
        cache2 = SymbolDataCache(persist_path=cache_file)

        # Should have the entry
        result = cache2.get(str(temp_file))
        assert result is not None
        assert len(result.definitions) == 1
        assert result.definitions[0].name == "hello"


class TestCacheWithHashValidation:
    """Tests for cache with content hash validation."""

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary Python file."""
        file_path = tmp_path / "test_file.py"
        file_path.write_text("def hello():\n    pass\n")
        return file_path

    def test_hash_validation_detects_content_change(self, temp_file: Path) -> None:
        """Test hash validation detects content changes even with same mtime."""
        cache = SymbolDataCache(use_hash_validation=True)

        symbol_data = FileSymbolData(
            filepath=str(temp_file),
            definitions=[],
            references=[],
            parse_time=0,
            is_valid=True,
        )
        cache.set(str(temp_file), symbol_data)

        # Change content without changing mtime
        original_mtime = os.path.getmtime(str(temp_file))
        temp_file.write_text("def goodbye():\n    pass\n")
        os.utime(str(temp_file), (original_mtime, original_mtime))

        # With hash validation, cache should be invalid
        assert cache.is_valid(str(temp_file)) is False
