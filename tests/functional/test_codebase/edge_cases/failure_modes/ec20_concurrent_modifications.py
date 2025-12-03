# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-20: Concurrent File Modifications

This module demonstrates handling of concurrent file modifications.
The file watcher should handle each change and maintain consistency.

Expected behavior:
- File watcher detects each change
- Cache is invalidated on each change
- System relies on filesystem consistency
"""

import threading
import time
from typing import Any, Callable

from tests.functional.test_codebase.core.models.product import Product
from tests.functional.test_codebase.core.models.user import User
from tests.functional.test_codebase.core.utils.validation import validate_email


class ConcurrentModificationHandler:
    """Handles concurrent modifications to files.

    When multiple processes or threads modify files simultaneously,
    the system should detect all changes and invalidate caches.
    """

    def __init__(self) -> None:
        self.modification_log: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def record_modification(self, file_path: str, modifier_id: str) -> None:
        """Record a file modification.

        Args:
            file_path: Path to the modified file.
            modifier_id: ID of the modifier (process/thread).
        """
        with self.lock:
            self.modification_log.append(
                {
                    "timestamp": time.time(),
                    "file": file_path,
                    "modifier": modifier_id,
                }
            )

    def get_modifications(self, file_path: str | None = None) -> list[dict[str, Any]]:
        """Get modification history, optionally filtered by file.

        Args:
            file_path: Optional file to filter by.

        Returns:
            List of modifications.
        """
        with self.lock:
            if file_path:
                return [m for m in self.modification_log if m["file"] == file_path]
            return self.modification_log.copy()

    def detect_conflicts(self, window_seconds: float = 1.0) -> list[tuple[str, int]]:
        """Detect files modified multiple times in a short window.

        Args:
            window_seconds: Time window to check for conflicts.

        Returns:
            List of (file_path, modification_count) tuples.
        """
        with self.lock:
            file_times: dict[str, list[float]] = {}
            for mod in self.modification_log:
                file_path = mod["file"]
                if file_path not in file_times:
                    file_times[file_path] = []
                file_times[file_path].append(mod["timestamp"])

            conflicts = []
            for file_path, times in file_times.items():
                times.sort()
                for i in range(len(times) - 1):
                    if times[i + 1] - times[i] < window_seconds:
                        conflicts.append((file_path, len(times)))
                        break

            return conflicts


class FileWatcherSimulator:
    """Simulates a file watcher for testing concurrent modifications.

    Demonstrates how the analyzer should handle rapid file changes.
    """

    def __init__(self) -> None:
        self.watched_files: set[str] = set()
        self.callbacks: list[Callable[[str, str], None]] = []
        self.events: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def watch(self, file_path: str) -> None:
        """Add a file to the watch list."""
        self.watched_files.add(file_path)

    def on_change(self, callback: Callable[[str, str], None]) -> None:
        """Register a callback for file changes."""
        self.callbacks.append(callback)

    def simulate_change(self, file_path: str, change_type: str = "modified") -> None:
        """Simulate a file change event.

        Args:
            file_path: Path to the changed file.
            change_type: Type of change (modified, created, deleted).
        """
        with self.lock:
            event = {
                "timestamp": time.time(),
                "file": file_path,
                "type": change_type,
            }
            self.events.append(event)

            for callback in self.callbacks:
                callback(file_path, change_type)

    def get_events(self) -> list[dict[str, Any]]:
        """Get all recorded events."""
        with self.lock:
            return self.events.copy()


class CacheInvalidator:
    """Handles cache invalidation on file changes.

    Ensures that concurrent modifications properly invalidate
    cached file contents.
    """

    def __init__(self) -> None:
        self.cache: dict[str, str] = {}
        self.invalidation_count: dict[str, int] = {}
        self.lock = threading.Lock()

    def get(self, file_path: str) -> str | None:
        """Get cached content for a file."""
        with self.lock:
            return self.cache.get(file_path)

    def set(self, file_path: str, content: str) -> None:
        """Set cached content for a file."""
        with self.lock:
            self.cache[file_path] = content

    def invalidate(self, file_path: str) -> None:
        """Invalidate cache for a file."""
        with self.lock:
            if file_path in self.cache:
                del self.cache[file_path]
            self.invalidation_count[file_path] = self.invalidation_count.get(file_path, 0) + 1

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            return {
                "cached_files": len(self.cache),
                "total_invalidations": sum(self.invalidation_count.values()),
                "invalidation_by_file": dict(self.invalidation_count),
            }


# Functions using imported models to create dependencies
def process_concurrent_users(users: list[User]) -> list[dict[str, Any]]:
    """Process users that might be modified concurrently.

    Uses User model, creating a dependency that might be
    affected by concurrent modifications.
    """
    results = []
    for user in users:
        if validate_email(user.email):
            results.append(user.to_dict())
    return results


def process_concurrent_products(products: list[Product]) -> list[dict[str, Any]]:
    """Process products that might be modified concurrently."""
    return [p.to_dict() for p in products if p.in_stock]
