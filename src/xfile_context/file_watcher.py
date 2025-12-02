# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""File system watcher with language-agnostic design.

This module implements file system monitoring (TDD Section 3.6):
- Watchdog library for cross-platform file watching
- Timestamp-only tracking (no immediate analysis)
- Extension-based dispatch to language analyzers
- .gitignore and hardcoded ignore patterns
- Cache invalidation callbacks on file modify/delete (Section 3.7.3.3)

Design Decisions:
- DD-2: Language-agnostic watcher extensible to TypeScript, etc.
- NFR-7: Respect .gitignore patterns
- NFR-8: Ignore dependency directories
- FR-15: Cache invalidation on file modification

Performance Characteristics (TDD Section 3.6.2):
- No debouncing: Timestamp updates are cheap, last write wins
- No batching: Bulk operations handled by fast timestamp updates
- Thread-safe: GIL ensures atomicity for dict operations

Cache Invalidation (TDD Section 3.7.3.3):
- Callbacks registered via register_invalidation_callback()
- Invoked synchronously on file modify/delete events
- Enables immediate cache entry removal for stale files

Known Limitations:
- Memory: file_event_timestamps dict grows unbounded (no cleanup of deleted files)
  Suitable for CLI/short-lived processes; consider cleanup for long-running daemons
- Symlinks: Symbolic links are followed by watchdog; no validation that resolved
  paths stay within project_root
- Error handling: No automatic restart/fallback on watcher failure (TDD 3.6.2
  requirement deferred to future enhancement)
"""

import fnmatch
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set

from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

if TYPE_CHECKING:
    from watchdog.observers.api import BaseObserver

logger = logging.getLogger(__name__)

# Type alias for invalidation callbacks
# Callback signature: (filepath: str) -> None
InvalidationCallback = Callable[[str], None]


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
        "*.jks",  # Java keystores
        "*.keystore",
        "*.truststore",
        "*.cer",
        "*.crt",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",  # SSH private keys
        "secrets.yaml",
        "secrets.yml",
        ".npmrc",
        ".pypirc",  # Package manager credentials
        "gcloud.json",
        ".aws",  # AWS credentials directory
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

        self.file_event_timestamps: Dict[str, float] = {}

        # Load ignore patterns
        self._gitignore_patterns: Set[str] = self._load_gitignore()

        # Invalidation callbacks (FR-15, Section 3.7.3.3)
        # Called on file modify/delete events to invalidate cache entries
        self._invalidation_callbacks: List[InvalidationCallback] = []

        # Watchdog observer and handler
        self._observer: Optional[BaseObserver] = None
        self._event_handler = _FileEventHandler(self)

        logger.info(f"FileWatcher initialized for {self.project_root}")
        logger.debug(f"Loaded {len(self._gitignore_patterns)} .gitignore patterns")

    def _load_gitignore(self) -> Set[str]:
        """Load and parse .gitignore patterns with validation.

        Pattern validation:
        - Maximum length: 1000 characters (prevents pathological patterns)
        - Empty lines and comments are skipped

        Returns:
            Set of gitignore patterns (NFR-7)
        """
        patterns: Set[str] = set()

        if not self.gitignore_path.exists():
            logger.debug(f"No .gitignore found at {self.gitignore_path}")
            return patterns

        try:
            with open(self.gitignore_path, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue

                    # Validate pattern length (security: prevent pathological patterns)
                    if len(line) > 1000:
                        logger.warning(
                            f".gitignore line {line_num}: Pattern too long (>1000 chars), skipping"
                        )
                        continue

                    patterns.add(line)

            logger.debug(f"Loaded {len(patterns)} patterns from .gitignore")
        except (FileNotFoundError, PermissionError) as e:
            logger.warning(f"Failed to load .gitignore: {e}")
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode .gitignore (encoding error): {e}")
        except OSError as e:
            logger.error(f"Failed to read .gitignore: {e}")

        return patterns

    def _matches_pattern(
        self, path: Path, rel_path_str: str, pattern: str, check_parts: bool = True
    ) -> bool:
        """Check if path matches a single pattern.

        Args:
            path: Path object to check
            rel_path_str: String representation of relative path
            pattern: Pattern to match against
            check_parts: Whether to check individual path components

        Returns:
            True if path matches pattern
        """
        # Check if pattern is a wildcard pattern
        if pattern.startswith("*") or pattern.endswith("*"):
            # Check full relative path and filename
            if fnmatch.fnmatch(rel_path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
            # Check if any part of the path matches the wildcard pattern
            if check_parts:
                for part in path.parts:
                    if fnmatch.fnmatch(part, pattern):
                        return True
        else:
            # Exact match - check filename or path components
            if path.name == pattern:
                return True
            if check_parts:
                for part in path.parts:
                    if part == pattern:
                        return True
        return False

    def should_ignore(self, file_path: str) -> bool:
        """Check if file should be ignored based on patterns.

        Pattern matching strategy:
        - ALWAYS_IGNORED & SENSITIVE_PATTERNS: Check path parts for directory/file matches
        - .gitignore patterns: Check relative path and filename (standard gitignore behavior)
        - User patterns: Check relative path and filename (standard glob behavior)

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
            if self._matches_pattern(path, rel_path_str, pattern, check_parts=True):
                return True

        # Sensitive files (check path parts for sensitive directories/files)
        for pattern in self.SENSITIVE_PATTERNS:
            if self._matches_pattern(path, rel_path_str, pattern, check_parts=True):
                logger.debug(f"Ignoring sensitive file/directory: {path.name}")
                return True

        # .gitignore patterns (NFR-7) - standard gitignore matching
        for pattern in self._gitignore_patterns:
            if fnmatch.fnmatch(rel_path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True

        # User-configured patterns - standard glob matching
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

    def register_invalidation_callback(self, callback: InvalidationCallback) -> None:
        """Register a callback for cache invalidation on file events.

        Callbacks are invoked when files are modified or deleted (FR-15).
        This enables cache systems to immediately invalidate stale entries.

        Thread Safety:
            Callbacks are invoked synchronously from the watcher thread.
            Callbacks should be thread-safe and return quickly to avoid
            blocking file event processing.

        Args:
            callback: Function that takes filepath (str) and invalidates
                related cache entries. Should handle exceptions internally.

        Example:
            watcher.register_invalidation_callback(cache.invalidate)
        """
        if callback not in self._invalidation_callbacks:
            self._invalidation_callbacks.append(callback)
            logger.debug(f"Registered invalidation callback: {callback}")

    def unregister_invalidation_callback(self, callback: InvalidationCallback) -> None:
        """Unregister a previously registered invalidation callback.

        Args:
            callback: Previously registered callback to remove.
        """
        if callback in self._invalidation_callbacks:
            self._invalidation_callbacks.remove(callback)
            logger.debug(f"Unregistered invalidation callback: {callback}")

    def _notify_invalidation_callbacks(self, file_path: str) -> None:
        """Notify all registered callbacks about file modification/deletion.

        Called internally when file events occur that require cache invalidation.

        Thread Safety:
            Called from watcher thread. Callbacks should be thread-safe.

        Args:
            file_path: Absolute path to modified/deleted file.
        """
        for callback in self._invalidation_callbacks:
            try:
                callback(file_path)
            except Exception as e:
                # Log but don't re-raise - one callback failure shouldn't
                # prevent other callbacks from being notified
                logger.error(f"Invalidation callback failed for {file_path}: {e}")

    def update_timestamp(self, file_path: str) -> None:
        """Update timestamp for file event.

        Args:
            file_path: Absolute file path
        """
        self.file_event_timestamps[file_path] = time.time()
        logger.debug(f"Updated timestamp for {file_path}")

    def get_timestamp(self, file_path: str) -> Optional[float]:
        """Get last event timestamp for file.

        Args:
            file_path: Absolute file path

        Returns:
            Last event timestamp or None if no events recorded
        """
        return self.file_event_timestamps.get(file_path)

    def start(self) -> None:
        """Start watching file system.

        Raises:
            RuntimeError: If watcher is already running
        """
        if self._observer is not None and self._observer.is_alive():
            raise RuntimeError("FileWatcher is already running")

        self._observer = Observer()
        self._observer.schedule(  # type: ignore  # watchdog types vary by version
            self._event_handler, str(self.project_root), recursive=True
        )
        self._observer.start()  # type: ignore  # watchdog types vary by version

        logger.info(f"FileWatcher started, monitoring {self.project_root}")

    def stop(self) -> None:
        """Stop watching file system.

        Blocks until observer thread terminates (with timeout).
        """
        if self._observer is not None and self._observer.is_alive():
            self._observer.stop()  # type: ignore  # watchdog types vary by version
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

    def _handle_event(self, event: FileSystemEvent, trigger_invalidation: bool = False) -> None:
        """Common event handling logic.

        Args:
            event: File system event from watchdog
            trigger_invalidation: Whether to trigger cache invalidation callbacks.
                Should be True for modify/delete events (FR-15, Section 3.7.3.3).
        """
        # Skip directory events
        if event.is_directory:
            return

        # Convert path from Union[bytes, str] to str
        file_path = str(event.src_path)

        # Check if file should be ignored
        if self.watcher.should_ignore(file_path):
            return

        # Check if file extension is supported
        if not self.watcher.is_supported_file(file_path):
            return

        # Update timestamp (TDD Section 3.6.2: timestamp-only approach)
        self.watcher.update_timestamp(file_path)

        # Trigger cache invalidation for modify/delete events (FR-15)
        if trigger_invalidation:
            self.watcher._notify_invalidation_callbacks(file_path)

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

        Triggers cache invalidation (FR-15, Section 3.7.3.3).

        Args:
            event: File system event
        """
        self._handle_event(event, trigger_invalidation=True)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events.

        Triggers cache invalidation (FR-15, Section 3.7.3.3).
        Note: Timestamp entry persists in dict (acceptable memory overhead).

        Args:
            event: File system event
        """
        self._handle_event(event, trigger_invalidation=True)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename events.

        Treated as Delete (old path) + Create (new path).
        Triggers cache invalidation for old path (FR-15, Section 3.7.3.3).

        Args:
            event: File system event (must be FileMovedEvent)
        """
        if event.is_directory:
            return

        # Type narrow to FileMovedEvent
        if not isinstance(event, FileMovedEvent):
            return

        # Convert paths from Union[bytes, str] to str
        src_path = str(event.src_path)
        dest_path = str(event.dest_path)

        # Old path: Mark as deleted and invalidate cache
        if not self.watcher.should_ignore(src_path) and self.watcher.is_supported_file(src_path):
            self.watcher.update_timestamp(src_path)
            # Invalidate cache for old path (file no longer exists at this location)
            self.watcher._notify_invalidation_callbacks(src_path)
            logger.debug(f"Event: moved_from - {src_path}")

        # New path: Mark as created (no invalidation needed - new file)
        if not self.watcher.should_ignore(dest_path) and self.watcher.is_supported_file(dest_path):
            self.watcher.update_timestamp(dest_path)
            language = self.watcher.get_language(dest_path)
            logger.debug(f"Event: moved_to - {dest_path} (language: {language})")
