# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Warning logging module for JSONL output.

This module implements structured warning logging per TDD Section 3.9.5:
- JSONL format (one JSON object per line)
- Real-time logging with immediate flush
- Log file size monitoring
- Warning statistics for session metrics

Log Location: .cross_file_context_logs/warnings.jsonl

Related Requirements:
- FR-41 (structured warning log)
- FR-44 (warning statistics in session metrics)
- T-6.9 (warnings logged to structured format)
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from xfile_context.warning_formatter import StructuredWarning

logger = logging.getLogger(__name__)

# Default log directory name
DEFAULT_LOG_DIR = ".cross_file_context_logs"

# Default warning log filename
DEFAULT_WARNING_LOG_FILE = "warnings.jsonl"

# Size threshold for warning about large log files (10MB per TDD 3.9.5)
LOG_SIZE_WARNING_THRESHOLD_BYTES = 10 * 1024 * 1024  # 10MB


@dataclass
class WarningStatistics:
    """Warning statistics for session metrics per FR-44.

    Provides aggregated warning data suitable for inclusion in session metrics.

    Attributes:
        total_warnings: Total number of warnings logged.
        by_type: Count of warnings by pattern type.
        files_with_most_warnings: List of files with highest warning counts.
    """

    total_warnings: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    files_with_most_warnings: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for JSON serialization.

        Returns:
            Dictionary with warning statistics.
        """
        return {
            "total_warnings": self.total_warnings,
            "by_type": self.by_type,
            "files_with_most_warnings": self.files_with_most_warnings,
        }


class WarningLogger:
    """Logger for writing warnings to JSONL file.

    Provides real-time warning logging with immediate flush to ensure
    warnings are persisted even if the session terminates unexpectedly.

    Features:
    - JSONL format (one JSON object per line)
    - Immediate flush after each write
    - Log file size monitoring with warnings
    - Warning statistics generation for session metrics

    Usage:
        logger = WarningLogger()
        logger.log_warning(structured_warning)
        # Or log multiple at once
        logger.log_warnings(list_of_warnings)
        # Get statistics for session metrics
        stats = logger.get_statistics()
        # Close when done
        logger.close()

    Context manager usage:
        with WarningLogger() as logger:
            logger.log_warning(warning)
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        log_file: Optional[str] = None,
        size_warning_threshold: int = LOG_SIZE_WARNING_THRESHOLD_BYTES,
        max_unique_files_tracked: int = 10000,
    ) -> None:
        """Initialize the warning logger.

        Args:
            log_dir: Directory for log files. If None, uses current working
                    directory + .cross_file_context_logs/
            log_file: Log filename. If None, uses warnings.jsonl.
                     Must be a simple filename without path separators.
            size_warning_threshold: File size in bytes at which to warn about
                                   large log files. Default is 10MB.
            max_unique_files_tracked: Maximum number of unique files to track
                                     in statistics. Prevents memory exhaustion.
                                     Default is 10000.

        Raises:
            ValueError: If log_file contains path separators.
        """
        if log_dir is None:
            log_dir = Path.cwd() / DEFAULT_LOG_DIR
        self._log_dir = Path(log_dir)

        # Validate log_file doesn't contain path components (security)
        # Check for /, \, and : (Windows drive letters) to prevent path traversal
        log_file = log_file or DEFAULT_WARNING_LOG_FILE
        if "/" in log_file or "\\" in log_file or ":" in log_file:
            raise ValueError(f"log_file must be a filename only, not a path: {log_file}")
        self._log_file = log_file

        self._size_warning_threshold = size_warning_threshold
        self._max_unique_files_tracked = max_unique_files_tracked

        # Statistics tracking
        self._warning_count = 0
        self._by_type: Counter[str] = Counter()
        self._by_file: Counter[str] = Counter()

        # File handle (lazy initialization)
        self._file_handle: Optional[TextIO] = None
        self._size_warning_issued = False

    def _ensure_log_dir(self) -> None:
        """Create log directory if it doesn't exist."""
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_path(self) -> Path:
        """Get full path to the log file.

        Returns:
            Path to the warnings log file.
        """
        return self._log_dir / self._log_file

    def _open_file(self) -> TextIO:
        """Open or get the file handle for writing.

        Returns:
            File handle open for appending.
        """
        if self._file_handle is None:
            self._ensure_log_dir()
            log_path = self._get_log_path()
            # noqa: SIM115 - We manage the file handle lifecycle via close() method
            self._file_handle = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
            logger.debug(f"Opened warning log file: {log_path}")
        return self._file_handle

    def _check_file_size(self) -> None:
        """Check log file size and warn if exceeds threshold.

        Per TDD Section 3.9.5: If file grows >10MB, warn user.
        """
        if self._size_warning_issued:
            return

        log_path = self._get_log_path()
        if log_path.exists():
            size = log_path.stat().st_size
            if size > self._size_warning_threshold:
                size_mb = size / (1024 * 1024)
                logger.warning(
                    f"Warning log file has grown to {size_mb:.1f}MB. "
                    f"Consider cleaning up {log_path} or enabling warning suppression. "
                    f"See TDD Section 3.9.4 for suppression configuration."
                )
                self._size_warning_issued = True

    def log_warning(self, warning: StructuredWarning) -> None:
        """Log a single warning to the JSONL file.

        The warning is immediately flushed to disk to ensure persistence.

        Args:
            warning: StructuredWarning to log.
        """
        file_handle = self._open_file()

        # Write JSON line
        json_line = json.dumps(warning.to_dict(), separators=(",", ":"))
        file_handle.write(json_line + "\n")
        file_handle.flush()  # Immediate flush per TDD 3.9.5

        # Update statistics
        self._warning_count += 1
        self._by_type[warning.type] += 1
        # Only track file stats up to limit to prevent memory exhaustion
        if len(self._by_file) < self._max_unique_files_tracked or warning.file in self._by_file:
            self._by_file[warning.file] += 1

        # Check file size periodically (every 100 warnings)
        if self._warning_count % 100 == 0:
            self._check_file_size()

    def log_warnings(self, warnings: List[StructuredWarning]) -> None:
        """Log multiple warnings to the JSONL file.

        Each warning is written on its own line and the file is flushed
        after all warnings are written.

        Args:
            warnings: List of StructuredWarnings to log.
        """
        if not warnings:
            return

        file_handle = self._open_file()

        for warning in warnings:
            # Write JSON line
            json_line = json.dumps(warning.to_dict(), separators=(",", ":"))
            file_handle.write(json_line + "\n")

            # Update statistics
            self._warning_count += 1
            self._by_type[warning.type] += 1
            # Only track file stats up to limit to prevent memory exhaustion
            if len(self._by_file) < self._max_unique_files_tracked or warning.file in self._by_file:
                self._by_file[warning.file] += 1

        # Flush after batch
        file_handle.flush()

        # Check file size
        self._check_file_size()

    def get_statistics(self, top_files_count: int = 5) -> WarningStatistics:
        """Get warning statistics for session metrics.

        Generates statistics per FR-44:
        - Total warning count
        - Count by type
        - Files with most warnings

        Args:
            top_files_count: Number of top files to include in statistics.
                            Default is 5.

        Returns:
            WarningStatistics with aggregated data.
        """
        # Get top files by warning count
        top_files = self._by_file.most_common(top_files_count)
        files_with_most_warnings = [
            {"file": filepath, "warning_count": count} for filepath, count in top_files
        ]

        return WarningStatistics(
            total_warnings=self._warning_count,
            by_type=dict(self._by_type),
            files_with_most_warnings=files_with_most_warnings,
        )

    def get_log_path(self) -> Path:
        """Get the path to the log file.

        Returns:
            Path to the warnings log file.
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
            logger.debug(f"Closed warning log file: {self._get_log_path()}")

    def clear_statistics(self) -> None:
        """Clear the in-memory statistics.

        Note: This does NOT clear the log file, only the in-memory counters.
        """
        self._warning_count = 0
        self._by_type.clear()
        self._by_file.clear()
        self._size_warning_issued = False

    def __enter__(self) -> "WarningLogger":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - ensures file is closed."""
        self.close()


def read_warnings_from_log(
    log_path: Path,
    limit: Optional[int] = None,
) -> List[StructuredWarning]:
    """Read warnings from a JSONL log file.

    Utility function for reading back logged warnings, useful for
    testing and analysis.

    Args:
        log_path: Path to the warnings.jsonl file.
        limit: Optional maximum number of warnings to read.

    Returns:
        List of StructuredWarning objects.

    Raises:
        FileNotFoundError: If log file doesn't exist.
        json.JSONDecodeError: If log file contains invalid JSON.
    """
    warnings: List[StructuredWarning] = []

    with open(log_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break

            line = line.strip()
            if not line:
                continue

            data = json.loads(line)
            warnings.append(StructuredWarning.from_dict(data))

    return warnings
