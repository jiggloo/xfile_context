# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Injection event logging module for JSONL output.

This module implements structured injection event logging per TDD Section 3.8.5:
- JSONL format (one JSON object per line)
- Real-time logging with immediate flush
- Date-based file rotation for eventual immutability (Issue #150)
- Injection statistics for session metrics
- Query API for recent injections (FR-29)

Log Location: ~/.cross_file_context/injections/<DATE>-<SESSION-ID>.jsonl

Related Requirements:
- FR-26 (log all context injections)
- FR-27 (structured format with required fields)
- FR-28 (JSONL compatible with Claude Code session logs)
- FR-29 (query API for recent injection events)
- T-5.1 through T-5.7 (injection logging comprehensive tests)
- Issue #150 (logging architecture cleanup)
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from xfile_context.log_config import (
    build_log_filename,
    get_current_utc_date,
    get_injections_dir,
    validate_filename_component,
)

logger = logging.getLogger(__name__)

# Legacy default log directory name (for backwards compatibility in tests)
DEFAULT_LOG_DIR = ".cross_file_context_logs"

# Legacy default injection log filename (for backwards compatibility in tests)
DEFAULT_INJECTION_LOG_FILE = "injections.jsonl"

# Legacy size threshold constant (kept for backwards compatibility in tests)
# Note: Size warnings are no longer issued per Issue #150, but this constant
# remains for test compatibility
LOG_SIZE_WARNING_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50MB


@dataclass
class InjectionEvent:
    """Represents a single context injection event per TDD Section 3.8.5.

    Each injection event logs when context from a source file is injected
    into the context for a target file being read.

    Attributes:
        timestamp: ISO 8601 timestamp of injection event.
        event_type: Always "context_injection" for filtering.
        source_file: File providing the context snippet (dependency).
        target_file: File being read (where context is injected).
        relationship_type: IMPORT, FUNCTION_CALL, or CLASS_INHERITANCE.
        snippet: The actual injected content (signature + docstring).
        snippet_location: File path and line range of snippet (e.g., "retry.py:45-67").
        cache_age_seconds: Age of snippet in cache (None if not cached).
        cache_hit: True if snippet was retrieved from cache.
        token_count: Approximate token count of this single snippet.
        context_token_total: Cumulative token count for all snippets in this injection.
    """

    timestamp: str
    event_type: str
    source_file: str
    target_file: str
    relationship_type: str
    snippet: str
    snippet_location: str
    cache_age_seconds: Optional[float]
    cache_hit: bool
    token_count: int
    context_token_total: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for JSON serialization.

        Returns:
            Dictionary with all injection event fields.
        """
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "source_file": self.source_file,
            "target_file": self.target_file,
            "relationship_type": self.relationship_type,
            "snippet": self.snippet,
            "snippet_location": self.snippet_location,
            "cache_age_seconds": self.cache_age_seconds,
            "cache_hit": self.cache_hit,
            "token_count": self.token_count,
            "context_token_total": self.context_token_total,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InjectionEvent":
        """Create an InjectionEvent from a dictionary.

        Args:
            data: Dictionary with injection event fields.

        Returns:
            InjectionEvent instance.
        """
        return cls(
            timestamp=data["timestamp"],
            event_type=data["event_type"],
            source_file=data["source_file"],
            target_file=data["target_file"],
            relationship_type=data["relationship_type"],
            snippet=data["snippet"],
            snippet_location=data["snippet_location"],
            cache_age_seconds=data.get("cache_age_seconds"),
            cache_hit=data["cache_hit"],
            token_count=data["token_count"],
            context_token_total=data["context_token_total"],
        )

    @classmethod
    def create(
        cls,
        source_file: str,
        target_file: str,
        relationship_type: str,
        snippet: str,
        snippet_location: str,
        cache_age_seconds: Optional[float],
        cache_hit: bool,
        token_count: int,
        context_token_total: int,
    ) -> "InjectionEvent":
        """Factory method to create an InjectionEvent with auto-generated timestamp.

        Args:
            source_file: File providing the context snippet.
            target_file: File being read.
            relationship_type: Type of relationship (IMPORT, FUNCTION_CALL, etc.).
            snippet: The injected content.
            snippet_location: Location of snippet in source file.
            cache_age_seconds: Age of cached content in seconds.
            cache_hit: Whether content was retrieved from cache.
            token_count: Token count of this snippet.
            context_token_total: Cumulative token count.

        Returns:
            New InjectionEvent with current timestamp.
        """
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            event_type="context_injection",
            source_file=source_file,
            target_file=target_file,
            relationship_type=relationship_type,
            snippet=snippet,
            snippet_location=snippet_location,
            cache_age_seconds=cache_age_seconds,
            cache_hit=cache_hit,
            token_count=token_count,
            context_token_total=context_token_total,
        )


@dataclass
class InjectionStatistics:
    """Injection statistics for session metrics.

    Provides aggregated injection data suitable for inclusion in session metrics.

    Attributes:
        total_injections: Total number of injection events logged.
        by_relationship_type: Count of injections by relationship type.
        by_source_file: Count of injections by source file.
        total_tokens_injected: Total token count across all injections.
        cache_hit_count: Number of injections that were cache hits.
        cache_miss_count: Number of injections that were cache misses.
    """

    total_injections: int = 0
    by_relationship_type: Dict[str, int] = field(default_factory=dict)
    by_source_file: Dict[str, int] = field(default_factory=dict)
    total_tokens_injected: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for JSON serialization.

        Returns:
            Dictionary with injection statistics.
        """
        cache_hit_rate = 0.0
        if self.total_injections > 0:
            cache_hit_rate = self.cache_hit_count / self.total_injections

        return {
            "total_injections": self.total_injections,
            "by_relationship_type": self.by_relationship_type,
            "by_source_file": self.by_source_file,
            "total_tokens_injected": self.total_tokens_injected,
            "cache_hit_count": self.cache_hit_count,
            "cache_miss_count": self.cache_miss_count,
            "cache_hit_rate": round(cache_hit_rate, 3),
        }


class InjectionLogger:
    """Logger for writing injection events to JSONL file.

    Provides real-time injection event logging with immediate flush to ensure
    events are persisted even if the session terminates unexpectedly.

    Features:
    - JSONL format (one JSON object per line)
    - Immediate flush after each write
    - Date-based file rotation for eventual immutability (Issue #150)
    - Injection statistics generation for session metrics
    - Query API for recent injections (FR-29)

    Usage:
        logger = InjectionLogger(session_id="abc-123")
        logger.log_injection(injection_event)
        # Or log multiple at once
        logger.log_injections(list_of_events)
        # Get statistics for session metrics
        stats = logger.get_statistics()
        # Query recent injections for a file
        recent = logger.get_recent_injections("/path/to/file.py", limit=10)
        # Close when done
        logger.close()

    Context manager usage:
        with InjectionLogger(session_id="abc-123") as logger:
            logger.log_injection(event)
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        log_file: Optional[str] = None,
        size_warning_threshold: int = LOG_SIZE_WARNING_THRESHOLD_BYTES,
        max_unique_files_tracked: int = 10000,
        session_id: Optional[str] = None,
        data_root: Optional[Path] = None,
    ) -> None:
        """Initialize the injection logger.

        Args:
            log_dir: Directory for log files. If None and data_root is None,
                    uses ~/.cross_file_context/injections/.
                    DEPRECATED: Use data_root instead.
            log_file: Log filename. If None, uses date-session pattern.
                     DEPRECATED: Filename is auto-generated from session_id.
            size_warning_threshold: DEPRECATED - no longer used per Issue #150.
                                   Kept for backwards compatibility.
            max_unique_files_tracked: Maximum number of unique files to track
                                     in statistics. Prevents memory exhaustion.
                                     Default is 10000.
            session_id: Session ID for log filename. Required for new architecture.
                       If None, falls back to legacy static filename.
            data_root: Root directory for logs. If provided, uses
                      {data_root}/injections/ as log directory.

        Raises:
            ValueError: If log_file contains path separators.
        """
        # size_warning_threshold is ignored per Issue #150 (no size limits)
        _ = size_warning_threshold
        # Determine log directory
        if data_root is not None:
            # New architecture: use {data_root}/injections/
            self._log_dir = get_injections_dir(data_root)
        elif log_dir is not None:
            # Legacy: explicit log_dir provided
            self._log_dir = Path(log_dir)
        else:
            # New default: ~/.cross_file_context/injections/
            self._log_dir = get_injections_dir()

        # Determine log filename
        self._session_id = session_id
        if log_file is not None:
            # Legacy: explicit filename provided - validate for security
            validate_filename_component(log_file, "log_file")
            self._log_file = log_file
            self._use_date_rotation = False
        elif session_id is not None:
            # New architecture: date-session filename
            self._log_file = build_log_filename(session_id)
            self._use_date_rotation = True
        else:
            # Fallback to legacy static filename
            self._log_file = DEFAULT_INJECTION_LOG_FILE
            self._use_date_rotation = False

        self._max_unique_files_tracked = max_unique_files_tracked

        # Track current date for rotation
        self._current_date = get_current_utc_date()

        # Statistics tracking
        self._injection_count = 0
        self._by_relationship_type: Counter[str] = Counter()
        self._by_source_file: Counter[str] = Counter()
        self._total_tokens = 0
        self._cache_hits = 0
        self._cache_misses = 0

        # File handle (lazy initialization)
        self._file_handle: Optional[TextIO] = None

    def _ensure_log_dir(self) -> None:
        """Create log directory if it doesn't exist."""
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_path(self) -> Path:
        """Get full path to the log file.

        Returns:
            Path to the injections log file.
        """
        return self._log_dir / self._log_file

    def _check_date_rotation(self) -> None:
        """Check if date has changed and rotate file if needed.

        Per Issue #150: Log files are split by UTC date for eventual immutability.
        """
        if not self._use_date_rotation:
            return

        current_date = get_current_utc_date()
        if current_date != self._current_date:
            # Date has changed - close current file and update filename
            if self._file_handle is not None:
                self._file_handle.close()
                self._file_handle = None
                logger.debug(f"Rotated injection log: {self._current_date} -> {current_date}")
            self._current_date = current_date
            self._log_file = build_log_filename(self._session_id)  # type: ignore[arg-type]

    def _open_file(self) -> TextIO:
        """Open or get the file handle for writing.

        Returns:
            File handle open for appending.
        """
        # Check for date rotation before opening
        self._check_date_rotation()

        if self._file_handle is None:
            self._ensure_log_dir()
            log_path = self._get_log_path()
            # noqa: SIM115 - We manage the file handle lifecycle via close() method
            self._file_handle = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
            logger.debug(f"Opened injection log file: {log_path}")
        return self._file_handle

    def log_injection(self, event: InjectionEvent) -> None:
        """Log a single injection event to the JSONL file.

        The event is immediately flushed to disk to ensure persistence.

        Args:
            event: InjectionEvent to log.
        """
        file_handle = self._open_file()

        # Write JSON line
        json_line = json.dumps(event.to_dict(), separators=(",", ":"))
        file_handle.write(json_line + "\n")
        file_handle.flush()  # Immediate flush per TDD 3.8.5

        # Update statistics
        self._injection_count += 1
        self._by_relationship_type[event.relationship_type] += 1
        self._total_tokens += event.token_count

        if event.cache_hit:
            self._cache_hits += 1
        else:
            self._cache_misses += 1

        # Only track source file stats up to limit to prevent memory exhaustion
        if (
            len(self._by_source_file) < self._max_unique_files_tracked
            or event.source_file in self._by_source_file
        ):
            self._by_source_file[event.source_file] += 1

    def log_injections(self, events: List[InjectionEvent]) -> None:
        """Log multiple injection events to the JSONL file.

        Each event is written on its own line and the file is flushed
        after all events are written.

        Args:
            events: List of InjectionEvents to log.
        """
        if not events:
            return

        file_handle = self._open_file()

        for event in events:
            # Write JSON line
            json_line = json.dumps(event.to_dict(), separators=(",", ":"))
            file_handle.write(json_line + "\n")

            # Update statistics
            self._injection_count += 1
            self._by_relationship_type[event.relationship_type] += 1
            self._total_tokens += event.token_count

            if event.cache_hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

            # Only track source file stats up to limit
            if (
                len(self._by_source_file) < self._max_unique_files_tracked
                or event.source_file in self._by_source_file
            ):
                self._by_source_file[event.source_file] += 1

        # Flush after batch
        file_handle.flush()

    def get_statistics(self, top_files_count: int = 5) -> InjectionStatistics:
        """Get injection statistics for session metrics.

        Generates statistics for metrics integration:
        - Total injection count
        - Count by relationship type
        - Top source files by injection count
        - Cache hit/miss statistics

        Args:
            top_files_count: Number of top files to include in statistics.
                            Default is 5.

        Returns:
            InjectionStatistics with aggregated data.
        """
        # Get top source files by injection count
        top_files = self._by_source_file.most_common(top_files_count)
        by_source_file = dict(top_files)

        return InjectionStatistics(
            total_injections=self._injection_count,
            by_relationship_type=dict(self._by_relationship_type),
            by_source_file=by_source_file,
            total_tokens_injected=self._total_tokens,
            cache_hit_count=self._cache_hits,
            cache_miss_count=self._cache_misses,
        )

    def get_log_path(self) -> Path:
        """Get the path to the log file.

        Returns:
            Path to the injections log file.
        """
        return self._get_log_path()

    def get_log_size(self) -> int:
        """Get the current size of the log file in bytes.

        Returns:
            Size in bytes, or 0 if file doesn't exist.
        """
        log_path = self._get_log_path()
        if log_path.exists():
            return log_path.stat().st_size
        return 0

    def close(self) -> None:
        """Close the log file handle.

        Should be called when logging is complete to ensure resources
        are released.
        """
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None
            logger.debug(f"Closed injection log file: {self._get_log_path()}")

    def clear_statistics(self) -> None:
        """Clear the in-memory statistics.

        Note: This does NOT clear the log file, only the in-memory counters.
        """
        self._injection_count = 0
        self._by_relationship_type.clear()
        self._by_source_file.clear()
        self._total_tokens = 0
        self._cache_hits = 0
        self._cache_misses = 0

    def __enter__(self) -> "InjectionLogger":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - ensures file is closed."""
        self.close()


def get_recent_injections(
    log_path: Path,
    target_file: Optional[str] = None,
    limit: int = 10,
) -> List[InjectionEvent]:
    """Get recent injection events from the log file.

    Implements FR-29: Query API for recent injection events.

    Reads the log file in reverse order (most recent first) and returns
    events matching the filter criteria.

    Args:
        log_path: Path to the injections.jsonl file.
        target_file: If provided, only return events for this target file.
                    If None, returns all recent events.
        limit: Maximum number of events to return. Default is 10.

    Returns:
        List of InjectionEvent objects, most recent first.

    Raises:
        FileNotFoundError: If log file doesn't exist.
    """
    if not log_path.exists():
        return []

    events: List[InjectionEvent] = []

    # Read file and collect matching events
    # Note: For very large files, this could be optimized with reverse reading
    all_events: List[InjectionEvent] = []

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                event = InjectionEvent.from_dict(data)

                # Filter by target file if specified
                if target_file is None or event.target_file == target_file:
                    all_events.append(event)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Skipping malformed log entry: {e}")
                continue

    # Return most recent events (last entries in file are most recent)
    events = all_events[-limit:] if len(all_events) > limit else all_events
    events.reverse()  # Most recent first

    return events


def read_injections_from_log(
    log_path: Path,
    limit: Optional[int] = None,
) -> List[InjectionEvent]:
    """Read injection events from a JSONL log file.

    Utility function for reading back logged events, useful for
    testing and analysis.

    Args:
        log_path: Path to the injections.jsonl file.
        limit: Optional maximum number of events to read.

    Returns:
        List of InjectionEvent objects in chronological order.

    Raises:
        FileNotFoundError: If log file doesn't exist.
        json.JSONDecodeError: If log file contains invalid JSON.
    """
    events: List[InjectionEvent] = []

    with open(log_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break

            line = line.strip()
            if not line:
                continue

            data = json.loads(line)
            events.append(InjectionEvent.from_dict(data))

    return events
