# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Working memory cache with LRU eviction and staleness detection.

This module implements the caching layer (TDD Section 3.7) that reduces
redundant file re-reads by storing recently-accessed content.

Key Features:
- LRU (Least Recently Used) eviction policy
- Timestamp-based staleness detection (demand-driven refresh)
- Configurable size limits
- Thread-safe cache operations
- Statistics tracking for cache performance

Design Decisions:
- DD-4: Uses OrderedDict for LRU implementation (simple, efficient)
- FR-15: Demand-driven staleness detection (no time-based expiry)
- FR-16: Size limit enforced with LRU eviction
- NFR-4: Memory footprint kept minimal (<500MB total system)

Thread Safety:
- Single _cache_lock protects: _cache, _file_last_read_timestamps, _stats
- file_event_timestamps (FileWatcher) read without lock (GIL protection)
- No deadlock risk: Single lock, no nested locking
"""

import logging
import os
import time
from collections import OrderedDict
from threading import Lock
from typing import Dict, Optional, Tuple

from xfile_context.models import CacheEntry, CacheStatistics

logger = logging.getLogger(__name__)


class WorkingMemoryCache:
    """LRU cache with staleness detection for file snippets.

    Maintains a cache of recently-accessed file content with automatic
    refresh when files are modified. Integrates with FileWatcher for
    staleness detection using timestamp comparison.

    Thread Safety:
        All public methods are thread-safe via _cache_lock.

    Usage:
        cache = WorkingMemoryCache(
            file_event_timestamps=watcher.file_event_timestamps,
            size_limit_kb=50
        )
        content = cache.get("/path/to/file.py")
        stats = cache.get_statistics()
    """

    def __init__(
        self,
        file_event_timestamps: Dict[str, float],
        size_limit_kb: int = 50,
        max_retries: int = 3,
    ) -> None:
        """Initialize working memory cache.

        Args:
            file_event_timestamps: Reference to FileWatcher's timestamp dict.
                This dict is owned by FileWatcher and updated by watcher thread.
            size_limit_kb: Maximum cache size in kilobytes (default: 50KB).
            max_retries: Maximum retries for file reads with locks (default: 3).
        """
        # External timestamp tracking (owned by FileWatcher)
        self._file_event_timestamps = file_event_timestamps

        # Internal state (protected by _cache_lock)
        self._cache: OrderedDict[Tuple[str, Optional[Tuple[int, int]]], CacheEntry] = OrderedDict()
        self._file_last_read_timestamps: Dict[str, float] = {}

        # Configuration
        self._size_limit_bytes = size_limit_kb * 1024
        self._max_retries = max_retries

        # Statistics (protected by _cache_lock)
        self._stats = CacheStatistics(
            hits=0,
            misses=0,
            staleness_refreshes=0,
            evictions_lru=0,
            current_size_bytes=0,
            peak_size_bytes=0,
            current_entry_count=0,
            peak_entry_count=0,
        )

        # Thread safety
        self._cache_lock = Lock()

        logger.debug(
            f"WorkingMemoryCache initialized with size_limit={size_limit_kb}KB, "
            f"max_retries={max_retries}"
        )

    def get(self, filepath: str, line_range: Optional[Tuple[int, int]] = None) -> str:
        """Get cached content, automatically refreshing if stale.

        This is the core operation that integrates staleness detection,
        cache refresh, and statistics tracking.

        Args:
            filepath: Absolute path to file.
            line_range: Optional (start_line, end_line) tuple for snippets.
                If None, reads entire file.

        Returns:
            File content (full file or snippet).

        Raises:
            FileNotFoundError: If file doesn't exist.
            IOError: If file read fails after max_retries.
            PermissionError: If file is not readable.
        """
        with self._cache_lock:
            cache_key = (filepath, line_range)

            # Check if entry exists and is stale
            is_cache_miss = cache_key not in self._cache
            is_stale = not is_cache_miss and self._is_stale(filepath)

            if is_cache_miss or is_stale:
                # Miss or stale - refresh from disk
                t = time.time()  # Capture timestamp BEFORE read

                # Read file content (with retry logic)
                full_content = self._read_from_disk_with_retry(filepath)

                # Extract snippet if line_range specified
                if line_range:
                    lines = full_content.splitlines(keepends=True)
                    start, end = line_range
                    # Convert 1-based to 0-based indexing, clamp to valid range
                    start_idx = max(0, start - 1)
                    end_idx = min(len(lines), end)
                    content = "".join(lines[start_idx:end_idx])
                else:
                    content = full_content

                # Calculate size
                size_bytes = len(content.encode("utf-8"))

                # Check if file is larger than cache limit
                if size_bytes > self._size_limit_bytes:
                    # File too large to cache - evict everything and skip caching
                    logger.warning(
                        f"File {filepath} ({size_bytes}B) exceeds cache limit "
                        f"({self._size_limit_bytes}B). Skipping cache."
                    )
                    # Update miss count and return content without caching
                    if is_cache_miss:
                        self._stats.misses += 1
                    else:
                        self._stats.staleness_refreshes += 1
                    return content

                # Evict LRU entries if needed to make space
                if self._stats.current_size_bytes + size_bytes > self._size_limit_bytes:
                    self._evict_lru(size_bytes)

                # Create cache entry
                entry = CacheEntry(
                    filepath=filepath,
                    line_start=line_range[0] if line_range else 1,
                    line_end=line_range[1] if line_range else len(full_content.splitlines()),
                    content=content,
                    last_accessed=t,
                    access_count=1,
                    size_bytes=size_bytes,
                    symbol_name=None,  # Can be enhanced in future versions
                )

                # Update cache (OrderedDict maintains insertion order)
                self._cache[cache_key] = entry

                # Synchronize timestamp (uses start time for correctness)
                self._file_last_read_timestamps[filepath] = t

                # Update statistics
                if is_stale:
                    self._stats.staleness_refreshes += 1
                else:
                    self._stats.misses += 1
                self._stats.current_size_bytes += size_bytes
                self._stats.current_entry_count = len(self._cache)

                # Update peaks
                if self._stats.current_size_bytes > self._stats.peak_size_bytes:
                    self._stats.peak_size_bytes = self._stats.current_size_bytes
                if self._stats.current_entry_count > self._stats.peak_entry_count:
                    self._stats.peak_entry_count = self._stats.current_entry_count

                logger.debug(
                    f"Cache {'refresh' if is_stale else 'miss'}: {filepath} "
                    f"(size={size_bytes}B, total={self._stats.current_size_bytes}B)"
                )
            else:
                # Cache hit - update access time for LRU
                entry = self._cache[cache_key]
                entry.last_accessed = time.time()
                entry.access_count += 1
                self._stats.hits += 1

                # Move to end of OrderedDict (most recently used)
                self._cache.move_to_end(cache_key)

                logger.debug(f"Cache hit: {filepath} (access_count={entry.access_count})")

            return self._cache[cache_key].content

    def _is_stale(self, filepath: str) -> bool:
        """Check if cached file is stale (modified since last read).

        Thread safety: Reads from file_event_timestamps (GIL-protected).

        Args:
            filepath: Absolute path to file.

        Returns:
            True if file is stale and needs refresh, False otherwise.
        """
        # File never tracked by watcher - treat as stale
        if filepath not in self._file_event_timestamps:
            # Fallback: Check if file exists and use mtime
            if os.path.exists(filepath):
                try:
                    file_mtime = os.path.getmtime(filepath)
                    last_read = self._file_last_read_timestamps.get(filepath, 0)
                    return file_mtime > last_read
                except OSError:
                    return True
            return True

        # File never read before - treat as stale (first access)
        if filepath not in self._file_last_read_timestamps:
            return True

        # Normal case: Compare timestamps
        event_time = self._file_event_timestamps[filepath]
        last_read_time = self._file_last_read_timestamps[filepath]

        return event_time > last_read_time

    def _read_from_disk_with_retry(self, filepath: str) -> str:
        """Read file from disk with retry logic for file locks.

        Implements exponential backoff: 100ms, 200ms, 400ms

        Args:
            filepath: Absolute path to file.

        Returns:
            File content as string.

        Raises:
            FileNotFoundError: If file doesn't exist.
            IOError: If file read fails after max_retries.
            PermissionError: If file is not readable.
        """
        for attempt in range(self._max_retries):
            try:
                with open(filepath, encoding="utf-8") as f:
                    return f.read()
            except OSError as e:
                if attempt < self._max_retries - 1:
                    delay = 0.1 * (2**attempt)  # 100ms, 200ms, 400ms
                    logger.debug(
                        f"File read attempt {attempt + 1} failed for {filepath}: {e}. "
                        f"Retrying in {delay * 1000}ms..."
                    )
                    time.sleep(delay)
                else:
                    # Final failure - log and re-raise
                    logger.warning(
                        f"Failed to read {filepath} after {self._max_retries} attempts: {e}"
                    )
                    raise

        # Should never reach here, but satisfy type checker
        raise OSError(f"Failed to read {filepath} after {self._max_retries} attempts")

    def _evict_lru(self, bytes_needed: int) -> None:
        """Evict least-recently-used entries to make space.

        Args:
            bytes_needed: Bytes required for new entry.
        """
        bytes_freed = 0
        evicted_count = 0

        # OrderedDict maintains insertion/access order
        # Items at the beginning are least recently used
        while bytes_freed < bytes_needed and self._cache:
            # Get first (least recently used) key
            cache_key = next(iter(self._cache))
            entry = self._cache[cache_key]

            # Remove from cache
            del self._cache[cache_key]

            # Update size tracking
            bytes_freed += entry.size_bytes
            self._stats.current_size_bytes -= entry.size_bytes
            evicted_count += 1

            logger.debug(
                f"Evicted LRU entry: {entry.filepath} "
                f"(freed={entry.size_bytes}B, total_freed={bytes_freed}B)"
            )

        # Update statistics
        self._stats.evictions_lru += evicted_count
        self._stats.current_entry_count = len(self._cache)

        logger.debug(
            f"LRU eviction complete: evicted={evicted_count} entries, " f"freed={bytes_freed}B"
        )

    def invalidate(self, filepath: str) -> None:
        """Invalidate all cache entries for a file.

        This removes entries from cache but does NOT update file_last_read_timestamps.
        Next access will be treated as stale and trigger refresh.

        Args:
            filepath: Absolute path to file to invalidate.
        """
        with self._cache_lock:
            # Find and remove all entries for this file
            keys_to_remove = [key for key in self._cache if key[0] == filepath]

            for key in keys_to_remove:
                entry = self._cache[key]
                del self._cache[key]
                self._stats.current_size_bytes -= entry.size_bytes
                logger.debug(f"Invalidated cache entry: {filepath}")

            self._stats.current_entry_count = len(self._cache)

    def clear(self) -> None:
        """Clear all cache entries.

        Used for:
        - Testing: Reset cache to clean state
        - Manual cache management
        """
        with self._cache_lock:
            self._cache.clear()
            self._file_last_read_timestamps.clear()
            self._stats.current_size_bytes = 0
            self._stats.current_entry_count = 0

            logger.debug("Cache cleared")

    def get_statistics(self) -> CacheStatistics:
        """Get cache performance statistics.

        Returns:
            CacheStatistics with current metrics.
        """
        with self._cache_lock:
            # Return a copy to avoid external mutation
            return CacheStatistics(
                hits=self._stats.hits,
                misses=self._stats.misses,
                staleness_refreshes=self._stats.staleness_refreshes,
                evictions_lru=self._stats.evictions_lru,
                current_size_bytes=self._stats.current_size_bytes,
                peak_size_bytes=self._stats.peak_size_bytes,
                current_entry_count=self._stats.current_entry_count,
                peak_entry_count=self._stats.peak_entry_count,
            )

    def get_hit_rate(self) -> float:
        """Calculate cache hit rate.

        Returns:
            Hit rate as percentage (0.0-100.0), or 0.0 if no reads.
        """
        with self._cache_lock:
            total_reads = self._stats.hits + self._stats.misses + self._stats.staleness_refreshes
            if total_reads == 0:
                return 0.0
            return (self._stats.hits / total_reads) * 100.0
