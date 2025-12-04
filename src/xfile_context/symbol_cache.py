# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Symbol data cache for incremental two-phase analysis (Issue #125 Phase 3).

This module implements caching for FileSymbolData to enable incremental analysis.
When a file hasn't changed since last analysis, we can reuse the cached symbol
data instead of re-parsing the AST.

Key features:
- In-memory caching with optional persistence to disk
- File modification time tracking for cache invalidation
- LRU-style eviction when cache size limit reached
- Thread-safe operations

Usage:
    cache = SymbolDataCache()

    # Check if file needs re-analysis
    if cache.is_valid(filepath):
        symbol_data = cache.get(filepath)
    else:
        symbol_data = analyzer.extract_file_symbols(filepath)
        cache.set(filepath, symbol_data)
"""

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from xfile_context.models import FileSymbolData, SymbolDefinition, SymbolReference

logger = logging.getLogger(__name__)


class CacheEntry:
    """Entry in the symbol data cache."""

    def __init__(
        self,
        symbol_data: FileSymbolData,
        file_mtime: float,
        file_hash: Optional[str] = None,
        cached_at: Optional[float] = None,
    ):
        """Initialize cache entry.

        Args:
            symbol_data: The cached FileSymbolData.
            file_mtime: File modification time when cached.
            file_hash: Optional content hash for extra validation.
            cached_at: Timestamp when cached (default: now).
        """
        self.symbol_data = symbol_data
        self.file_mtime = file_mtime
        self.file_hash = file_hash
        self.cached_at = cached_at or time.time()
        self.access_count = 0
        self.last_accessed = self.cached_at

    def touch(self) -> None:
        """Update access statistics."""
        self.access_count += 1
        self.last_accessed = time.time()


class SymbolDataCache:
    """Cache for FileSymbolData with modification-time based invalidation.

    This cache enables incremental two-phase analysis by storing symbol data
    and only re-analyzing files that have changed since last analysis.

    Thread Safety:
        All public methods are thread-safe using a reentrant lock.

    Cache Invalidation:
        A cache entry is invalid if:
        - File no longer exists
        - File modification time changed
        - File content hash changed (if hash validation enabled)
        - Entry explicitly invalidated

    Eviction Policy:
        When max_entries is reached, least recently used entries are evicted.
    """

    def __init__(
        self,
        max_entries: int = 1000,
        use_hash_validation: bool = False,
        persist_path: Optional[Path] = None,
    ):
        """Initialize the symbol data cache.

        Args:
            max_entries: Maximum number of entries to cache (default: 1000).
            use_hash_validation: Whether to validate using content hash (slower but more accurate).
            persist_path: Optional path to persist cache to disk.
        """
        self._max_entries = max_entries
        self._use_hash_validation = use_hash_validation
        self._persist_path = persist_path
        self._lock = threading.RLock()

        # Use OrderedDict for LRU eviction
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._invalidations = 0

        # Load persisted cache if available
        if persist_path and persist_path.exists():
            self._load_from_disk()

    def get(self, filepath: str) -> Optional[FileSymbolData]:
        """Get cached symbol data for a file.

        Args:
            filepath: Absolute path to file.

        Returns:
            FileSymbolData if cached and valid, None otherwise.
        """
        with self._lock:
            entry = self._cache.get(filepath)
            if entry is None:
                self._misses += 1
                return None

            # Validate entry
            if not self._is_entry_valid(filepath, entry):
                self._invalidate_entry(filepath)
                self._misses += 1
                return None

            # Update access for LRU
            entry.touch()
            self._cache.move_to_end(filepath)
            self._hits += 1

            return entry.symbol_data

    def set(self, filepath: str, symbol_data: FileSymbolData) -> None:
        """Cache symbol data for a file.

        Args:
            filepath: Absolute path to file.
            symbol_data: FileSymbolData to cache.
        """
        with self._lock:
            # Get file metadata
            try:
                file_mtime = os.path.getmtime(filepath)
                file_hash = self._compute_hash(filepath) if self._use_hash_validation else None
            except OSError:
                # File doesn't exist or can't be accessed
                logger.debug(f"Cannot cache {filepath}: file not accessible")
                return

            # Create entry
            entry = CacheEntry(
                symbol_data=symbol_data,
                file_mtime=file_mtime,
                file_hash=file_hash,
            )

            # Evict if needed
            while len(self._cache) >= self._max_entries:
                self._evict_oldest()

            # Store entry
            self._cache[filepath] = entry
            self._cache.move_to_end(filepath)

    def is_valid(self, filepath: str) -> bool:
        """Check if cached data for a file is valid.

        Args:
            filepath: Absolute path to file.

        Returns:
            True if cache entry exists and is valid.
        """
        with self._lock:
            entry = self._cache.get(filepath)
            if entry is None:
                return False
            return self._is_entry_valid(filepath, entry)

    def invalidate(self, filepath: str) -> None:
        """Invalidate cache entry for a file.

        Args:
            filepath: Absolute path to file.
        """
        with self._lock:
            self._invalidate_entry(filepath)

    def invalidate_all(self) -> None:
        """Invalidate all cache entries."""
        with self._lock:
            self._cache.clear()
            self._invalidations += 1
            logger.debug("Symbol cache cleared")

    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics.
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

            return {
                "entries": len(self._cache),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "invalidations": self._invalidations,
            }

    def get_cached_files(self) -> List[str]:
        """Get list of cached file paths.

        Returns:
            List of file paths with valid cache entries.
        """
        with self._lock:
            return [fp for fp in self._cache if self.is_valid(fp)]

    def persist(self) -> None:
        """Persist cache to disk if persist_path is set."""
        if self._persist_path is None:
            return

        with self._lock:
            try:
                self._save_to_disk()
                logger.debug(f"Symbol cache persisted to {self._persist_path}")
            except Exception as e:
                logger.warning(f"Failed to persist symbol cache: {e}")

    def _is_entry_valid(self, filepath: str, entry: CacheEntry) -> bool:
        """Check if a cache entry is still valid.

        Args:
            filepath: Path to file.
            entry: Cache entry to validate.

        Returns:
            True if entry is valid.
        """
        try:
            # Check file exists
            if not os.path.exists(filepath):
                return False

            # Check modification time
            current_mtime = os.path.getmtime(filepath)
            if current_mtime != entry.file_mtime:
                return False

            # Check hash if enabled
            if self._use_hash_validation and entry.file_hash:
                current_hash = self._compute_hash(filepath)
                if current_hash != entry.file_hash:
                    return False

            return True

        except OSError:
            return False

    def _invalidate_entry(self, filepath: str) -> None:
        """Remove a cache entry.

        Args:
            filepath: Path to invalidate.
        """
        if filepath in self._cache:
            del self._cache[filepath]
            self._invalidations += 1

    def _evict_oldest(self) -> None:
        """Evict the least recently used entry."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"Evicted cache entry: {oldest_key}")

    def _compute_hash(self, filepath: str) -> str:
        """Compute content hash for a file.

        Args:
            filepath: Path to file.

        Returns:
            SHA256 hash of file contents.
        """
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _save_to_disk(self) -> None:
        """Save cache to disk."""
        if self._persist_path is None:
            return

        # Ensure directory exists
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize cache entries
        data: Dict[str, Any] = {
            "version": 1,
            "entries": {},
            "stats": {
                "hits": self._hits,
                "misses": self._misses,
                "invalidations": self._invalidations,
            },
        }

        for filepath, entry in self._cache.items():
            data["entries"][filepath] = {
                "symbol_data": self._serialize_symbol_data(entry.symbol_data),
                "file_mtime": entry.file_mtime,
                "file_hash": entry.file_hash,
                "cached_at": entry.cached_at,
            }

        with open(self._persist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        if self._persist_path is None or not self._persist_path.exists():
            return

        try:
            with open(self._persist_path, encoding="utf-8") as f:
                data = json.load(f)

            if data.get("version") != 1:
                logger.warning("Cache version mismatch, ignoring persisted cache")
                return

            # Restore entries
            for filepath, entry_data in data.get("entries", {}).items():
                symbol_data = self._deserialize_symbol_data(entry_data["symbol_data"])
                if symbol_data:
                    entry = CacheEntry(
                        symbol_data=symbol_data,
                        file_mtime=entry_data["file_mtime"],
                        file_hash=entry_data.get("file_hash"),
                        cached_at=entry_data.get("cached_at"),
                    )
                    self._cache[filepath] = entry

            # Restore stats
            stats = data.get("stats", {})
            self._hits = stats.get("hits", 0)
            self._misses = stats.get("misses", 0)
            self._invalidations = stats.get("invalidations", 0)

            logger.debug(f"Loaded {len(self._cache)} entries from cache")

        except Exception as e:
            logger.warning(f"Failed to load symbol cache: {e}")

    def _serialize_symbol_data(self, data: FileSymbolData) -> Dict[str, Any]:
        """Serialize FileSymbolData for JSON storage."""
        return {
            "filepath": data.filepath,
            "definitions": [self._serialize_definition(d) for d in data.definitions],
            "references": [self._serialize_reference(r) for r in data.references],
            "parse_time": data.parse_time,
            "is_valid": data.is_valid,
            "error_message": data.error_message,
            "has_dynamic_patterns": data.has_dynamic_patterns,
            "dynamic_pattern_types": data.dynamic_pattern_types,
        }

    def _deserialize_symbol_data(self, data: Dict[str, Any]) -> Optional[FileSymbolData]:
        """Deserialize FileSymbolData from JSON."""
        try:
            definitions = [self._deserialize_definition(d) for d in data.get("definitions", [])]
            references = [self._deserialize_reference(r) for r in data.get("references", [])]

            return FileSymbolData(
                filepath=data["filepath"],
                definitions=definitions,
                references=references,
                parse_time=data.get("parse_time", 0),
                is_valid=data.get("is_valid", True),
                error_message=data.get("error_message"),
                has_dynamic_patterns=data.get("has_dynamic_patterns", False),
                dynamic_pattern_types=data.get("dynamic_pattern_types"),
            )
        except Exception as e:
            logger.debug(f"Failed to deserialize symbol data: {e}")
            return None

    def _serialize_definition(self, defn: SymbolDefinition) -> Dict[str, Any]:
        """Serialize SymbolDefinition."""
        return {
            "name": defn.name,
            "symbol_type": defn.symbol_type,
            "line_start": defn.line_start,
            "line_end": defn.line_end,
            "signature": defn.signature,
            "docstring": defn.docstring,
            "decorators": defn.decorators,
            "bases": defn.bases,
        }

    def _deserialize_definition(self, data: Dict[str, Any]) -> SymbolDefinition:
        """Deserialize SymbolDefinition."""
        # line_end defaults to line_start if not provided
        line_end = data.get("line_end")
        if line_end is None:
            line_end = data["line_start"]
        return SymbolDefinition(
            name=data["name"],
            symbol_type=data["symbol_type"],
            line_start=data["line_start"],
            line_end=line_end,
            signature=data.get("signature"),
            docstring=data.get("docstring"),
            decorators=data.get("decorators"),
            bases=data.get("bases"),
        )

    def _serialize_reference(self, ref: SymbolReference) -> Dict[str, Any]:
        """Serialize SymbolReference."""
        return {
            "name": ref.name,
            "reference_type": ref.reference_type,
            "line_number": ref.line_number,
            "resolved_module": ref.resolved_module,
            "resolved_symbol": ref.resolved_symbol,
            "caller_context": ref.caller_context,
            "is_conditional": ref.is_conditional,
            "metadata": ref.metadata,
        }

    def _deserialize_reference(self, data: Dict[str, Any]) -> SymbolReference:
        """Deserialize SymbolReference."""
        return SymbolReference(
            name=data["name"],
            reference_type=data["reference_type"],
            line_number=data["line_number"],
            resolved_module=data.get("resolved_module"),
            resolved_symbol=data.get("resolved_symbol"),
            caller_context=data.get("caller_context"),
            is_conditional=data.get("is_conditional", False),
            metadata=data.get("metadata"),
        )
