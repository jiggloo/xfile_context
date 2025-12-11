# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Shared logging configuration for cross-file context.

This module provides centralized configuration for all logging components
per Issue #150 (Clean up logging architecture):
- Configurable data root directory (default: ~/.cross_file_context/)
- Date-session filename pattern (YYYY-MM-DD-<SESSION-ID>.jsonl)
- Date-based file rotation for eventual immutability
- Subdirectory structure: injections/, warnings/, session_metrics/

Note: The logs/ subdirectory (for Python logging output via setup_logging())
is deferred. Currently, setup_logging() is not called by the MCP server.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Default data root directory (user home)
DEFAULT_DATA_ROOT = Path.home() / ".cross_file_context"

# Subdirectory names
INJECTIONS_SUBDIR = "injections"
WARNINGS_SUBDIR = "warnings"
SESSION_METRICS_SUBDIR = "session_metrics"


def get_default_data_root() -> Path:
    """Get the default data root directory.

    Returns:
        Path to ~/.cross_file_context/
    """
    return DEFAULT_DATA_ROOT


def get_current_utc_date() -> str:
    """Get the current UTC date in YYYY-MM-DD format.

    Returns:
        Date string like "2025-12-11"
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def validate_filename_component(value: str, name: str = "value") -> None:
    """Validate a string for safe use in filenames.

    Checks for path traversal attacks and invalid characters.

    Args:
        value: The string to validate.
        name: Name of the parameter for error messages.

    Raises:
        ValueError: If value contains path separators, parent references,
                   or null bytes.
    """
    if "\0" in value:
        raise ValueError(f"{name} contains null bytes: {value}")
    if "/" in value or "\\" in value or ":" in value:
        raise ValueError(f"{name} must not contain path separators: {value}")
    if ".." in value:
        raise ValueError(f"{name} must not contain parent references: {value}")


def build_log_filename(session_id: str, extension: str = "jsonl") -> str:
    """Build a log filename with date and session ID.

    Args:
        session_id: Session ID (UUID string).
        extension: File extension without dot. Default is "jsonl".

    Returns:
        Filename like "2025-12-11-abc123-def456.jsonl"

    Raises:
        ValueError: If session_id contains path separators or invalid chars.
    """
    validate_filename_component(session_id, "session_id")
    date_str = get_current_utc_date()
    return f"{date_str}-{session_id}.{extension}"


def get_injections_dir(data_root: Optional[Path] = None) -> Path:
    """Get the injections log directory.

    Args:
        data_root: Data root directory. If None, uses default.

    Returns:
        Path to {data_root}/injections/
    """
    root = data_root or DEFAULT_DATA_ROOT
    return root / INJECTIONS_SUBDIR


def get_warnings_dir(data_root: Optional[Path] = None) -> Path:
    """Get the warnings log directory.

    Args:
        data_root: Data root directory. If None, uses default.

    Returns:
        Path to {data_root}/warnings/
    """
    root = data_root or DEFAULT_DATA_ROOT
    return root / WARNINGS_SUBDIR


def get_session_metrics_dir(data_root: Optional[Path] = None) -> Path:
    """Get the session metrics log directory.

    Args:
        data_root: Data root directory. If None, uses default.

    Returns:
        Path to {data_root}/session_metrics/
    """
    root = data_root or DEFAULT_DATA_ROOT
    return root / SESSION_METRICS_SUBDIR


def ensure_log_directories(data_root: Optional[Path] = None) -> None:
    """Create all log subdirectories if they don't exist.

    Args:
        data_root: Data root directory. If None, uses default.
    """
    root = data_root or DEFAULT_DATA_ROOT
    root.mkdir(parents=True, exist_ok=True)
    (root / INJECTIONS_SUBDIR).mkdir(exist_ok=True)
    (root / WARNINGS_SUBDIR).mkdir(exist_ok=True)
    (root / SESSION_METRICS_SUBDIR).mkdir(exist_ok=True)
