# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""File system watcher with language-agnostic design.

This module implements file system monitoring (TDD Section 3.6):
- Watchdog library for cross-platform file watching
- Timestamp-only tracking (no immediate analysis)
- Extension-based dispatch to language analyzers
- .gitignore and hardcoded ignore patterns

Design Decisions:
- DD-2: Language-agnostic watcher extensible to TypeScript, etc.
- NFR-7: Respect .gitignore patterns
- NFR-8: Ignore dependency directories

Performance Characteristics (TDD Section 3.6.2):
- No debouncing: Timestamp updates are cheap, last write wins
- No batching: Bulk operations handled by fast timestamp updates
- Thread-safe: GIL ensures atomicity for dict operations
"""

import fnmatch
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Set

from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from watchdog.observers.api import BaseObserver

logger = logging.getLogger(__name__)


class FileWatcher:
    """Language-agnostic file system watcher.

    Monitors file system changes and tracks timestamps for modified files.
    Dispatches to language-specific analyzers based on file extension.

    Thread Safety:
    - file_event_timestamps: Simple dict operations protected by GIL
    - No explicit locking needed for basic dict read/write

    Usage:
        watcher = FileWatcher(project_root="/path/to/project")
        watcher.start()
        # ... check timestamps as needed ...
        watcher.stop()
    """

    # Hardcoded ignore patterns (NFR-8)
    ALWAYS_IGNORED = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "node_modules",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".eggs",
        "*.egg-info",
        "dist",
        "build",
    }

    # Sensitive files that should never be watched
    SENSITIVE_PATTERNS = {
        ".env",
        ".env.*",
        "credentials.json",
        "*.key",
        "*.pem",
        "*.p12",
        "*.pfx",
        "*_key",
        "*_secret",
    }

    # Supported file extensions (extensible for future languages)
    SUPPORTED_EXTENSIONS = {
        ".py": "python",
        # Future: ".ts": "typescript", ".js": "javascript", etc.
    }

    def __init__(
        self,
        project_root: str,
        gitignore_path: Optional[str] = None,
        user_ignore_patterns: Optional[Set[str]] = None,
    ):
        """Initialize FileWatcher.

        Args:
            project_root: Root directory to watch (where .git/ exists or user-specified)
            gitignore_path: Path to .gitignore file (defaults to {project_root}/.gitignore)
            user_ignore_patterns: Additional user-configured ignore patterns
        """
        self.project_root = Path(project_root).resolve()
        self.gitignore_path = (
            Path(gitignore_path) if gitignore_path else self.project_root / ".gitignore"
        )
        self.user_ignore_patterns = user_ignore_patterns or set()

        # Thread-safe: GIL ensures atomicity for dict operations
        self.file_event_timestamps: Dict[str, float] = {}

        # Load ignore patterns
        self._gitignore_patterns: Set[str] = self._load_gitignore()

        # Watchdog observer and handler
        self._observer: Optional[BaseObserver] = None
        self._event_handler = _FileEventHandler(self)

        logger.info(f"FileWatcher initialized for {self.project_root}")
        logger.debug(f"Loaded {len(self._gitignore_patterns)} .gitignore patterns")

    def _load_gitignore(self) -> Set[str]:
        """Load and parse .gitignore patterns.

        Returns:
            Set of gitignore patterns (NFR-7)
        """
        patterns: Set[str] = set()

        if not self.gitignore_path.exists():
            logger.debug(f"No .gitignore found at {self.gitignore_path}")
            return patterns

        try:
            with open(self.gitignore_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith("#"):
                        patterns.add(line)

            logger.debug(f"Loaded {len(patterns)} patterns from .gitignore")
        except Exception as e:
            logger.warning(f"Failed to load .gitignore: {e}")

        return patterns

    def should_ignore(self, file_path: str) -> bool:
        """Check if file should be ignored based on patterns.

        Args:
            file_path: Absolute or relative file path

        Returns:
            True if file should be ignored
        """
        path = Path(file_path)
        path_str = str(path)

        # Check if path is relative to project root
        try:
            rel_path = path.relative_to(self.project_root)
            rel_path_str = str(rel_path)
        except ValueError:
            # Path is not under project root, use as-is
            rel_path_str = path_str

        # Always ignored directories and patterns (NFR-8)
        for pattern in self.ALWAYS_IGNORED:
            if pattern.startswith("*") or pattern.endswith("*"):
                # Check full relative path and filename
                if fnmatch.fnmatch(rel_path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
                    return True
                # Check if any part of the path matches the wildcard pattern
                for part in path.parts:
                    if fnmatch.fnmatch(part, pattern):
                        return True
            else:
                # Check if any part of the path matches
                for part in path.parts:
                    if part == pattern:
                        return True

        # Sensitive files
        for pattern in self.SENSITIVE_PATTERNS:
            if fnmatch.fnmatch(path.name, pattern):
                logger.debug(f"Ignoring sensitive file: {path.name}")
                return True

        # .gitignore patterns (NFR-7)
        for pattern in self._gitignore_patterns:
            if fnmatch.fnmatch(rel_path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True

        # User-configured patterns
        for pattern in self.user_ignore_patterns:
            if fnmatch.fnmatch(rel_path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True

        return False

    def is_supported_file(self, file_path: str) -> bool:
        """Check if file extension is supported for analysis.

        Args:
            file_path: File path to check

        Returns:
            True if file has a supported extension (.py in v0.1.0)
        """
        path = Path(file_path)
        return path.suffix in self.SUPPORTED_EXTENSIONS

    def get_language(self, file_path: str) -> Optional[str]:
        """Get language identifier for file extension.

        Args:
            file_path: File path

        Returns:
            Language identifier (e.g., "python") or None if unsupported
        """
        path = Path(file_path)
        return self.SUPPORTED_EXTENSIONS.get(path.suffix)

    def update_timestamp(self, file_path: str) -> None:
        """Update timestamp for file event.

        Thread-safe: GIL ensures atomicity for dict write.

        Args:
            file_path: Absolute file path
        """
        # Thread-safe: GIL ensures atomicity for dict operations
        self.file_event_timestamps[file_path] = time.time()
        logger.debug(f"Updated timestamp for {file_path}")

    def get_timestamp(self, file_path: str) -> Optional[float]:
        """Get last event timestamp for file.

        Thread-safe: GIL ensures atomicity for dict read.

        Args:
            file_path: Absolute file path

        Returns:
            Last event timestamp or None if no events recorded
        """
        # Thread-safe: GIL ensures atomicity for dict operations
        return self.file_event_timestamps.get(file_path)

    def start(self) -> None:
        """Start watching file system.

        Raises:
            RuntimeError: If watcher is already running
        """
        if self._observer is not None and self._observer.is_alive():
            raise RuntimeError("FileWatcher is already running")

        self._observer = Observer()
        self._observer.schedule(self._event_handler, str(self.project_root), recursive=True)  # type: ignore[no-untyped-call]
        self._observer.start()  # type: ignore[no-untyped-call]

        logger.info(f"FileWatcher started, monitoring {self.project_root}")

    def stop(self) -> None:
        """Stop watching file system.

        Blocks until observer thread terminates (with timeout).
        """
        if self._observer is not None and self._observer.is_alive():
            self._observer.stop()  # type: ignore[no-untyped-call]
            self._observer.join(timeout=5.0)
            logger.info("FileWatcher stopped")

    def is_running(self) -> bool:
        """Check if watcher is currently running.

        Returns:
            True if observer is alive
        """
        return self._observer is not None and self._observer.is_alive()


class _FileEventHandler(FileSystemEventHandler):
    """Internal event handler for watchdog.

    Delegates to FileWatcher for filtering and timestamp tracking.
    """

    def __init__(self, watcher: FileWatcher):
        """Initialize handler.

        Args:
            watcher: Parent FileWatcher instance
        """
        super().__init__()
        self.watcher = watcher

    def _handle_event(self, event: FileSystemEvent) -> None:
        """Common event handling logic.

        Args:
            event: File system event from watchdog
        """
        # Skip directory events
        if event.is_directory:
            return

        file_path = event.src_path

        # Check if file should be ignored
        if self.watcher.should_ignore(file_path):
            return

        # Check if file extension is supported
        if not self.watcher.is_supported_file(file_path):
            return

        # Update timestamp (TDD Section 3.6.2: timestamp-only approach)
        self.watcher.update_timestamp(file_path)

        # Log the event with language info
        language = self.watcher.get_language(file_path)
        logger.debug(f"Event: {event.event_type} - {file_path} (language: {language})")

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events.

        Args:
            event: File system event
        """
        self._handle_event(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events.

        Args:
            event: File system event
        """
        self._handle_event(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events.

        Note: Timestamp entry persists in dict (acceptable memory overhead).

        Args:
            event: File system event
        """
        self._handle_event(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename events.

        Treated as Delete (old path) + Create (new path).

        Args:
            event: File system event (must be FileMovedEvent)
        """
        if event.is_directory:
            return

        # Type narrow to FileMovedEvent
        if not isinstance(event, FileMovedEvent):
            return

        # Old path: Mark as deleted
        if not self.watcher.should_ignore(event.src_path) and self.watcher.is_supported_file(
            event.src_path
        ):
            self.watcher.update_timestamp(event.src_path)
            logger.debug(f"Event: moved_from - {event.src_path}")

        # New path: Mark as created
        if not self.watcher.should_ignore(event.dest_path) and self.watcher.is_supported_file(
            event.dest_path
        ):
            self.watcher.update_timestamp(event.dest_path)
            language = self.watcher.get_language(event.dest_path)
            logger.debug(f"Event: moved_to - {event.dest_path} (language: {language})")
