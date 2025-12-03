# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-16: Long-Running Sessions

This module demonstrates patterns common in long-running sessions.
The analyzer should implement rolling window for session management.

Expected behavior:
- Keep only last 2 hours of context
- Handle 8-hour sessions with 500+ file accesses
- Session metrics should be tracked
"""

from datetime import datetime, timedelta
from typing import Any

from tests.functional.test_codebase.core.models.product import Product
from tests.functional.test_codebase.core.models.user import User


class SessionManager:
    """Manages long-running sessions with rolling window.

    This class simulates a session that runs for many hours
    and accesses many files.
    """

    def __init__(self, window_hours: int = 2) -> None:
        self.window_hours = window_hours
        self.session_start = datetime.now()
        self.access_log: list[dict[str, Any]] = []
        self.file_accesses: dict[str, int] = {}

    @property
    def session_duration(self) -> timedelta:
        """Get the current session duration."""
        return datetime.now() - self.session_start

    @property
    def session_hours(self) -> float:
        """Get session duration in hours."""
        return self.session_duration.total_seconds() / 3600

    def log_file_access(self, file_path: str) -> None:
        """Log a file access."""
        now = datetime.now()
        self.access_log.append(
            {
                "timestamp": now,
                "file": file_path,
            }
        )
        self.file_accesses[file_path] = self.file_accesses.get(file_path, 0) + 1

        # Implement rolling window - remove old entries
        self._cleanup_old_entries()

    def _cleanup_old_entries(self) -> None:
        """Remove entries older than the window."""
        cutoff = datetime.now() - timedelta(hours=self.window_hours)
        self.access_log = [entry for entry in self.access_log if entry["timestamp"] > cutoff]

    def get_recent_accesses(self) -> list[dict[str, Any]]:
        """Get recent file accesses within the window."""
        return self.access_log.copy()

    def get_access_stats(self) -> dict[str, Any]:
        """Get access statistics."""
        return {
            "total_accesses": sum(self.file_accesses.values()),
            "unique_files": len(self.file_accesses),
            "session_hours": self.session_hours,
            "recent_accesses": len(self.access_log),
            "most_accessed": sorted(self.file_accesses.items(), key=lambda x: x[1], reverse=True)[
                :10
            ],
        }


class LongRunningProcessor:
    """Processor that simulates long-running operations.

    Uses multiple services and models over an extended period.
    """

    def __init__(self) -> None:
        self.session = SessionManager()
        self.processed_users: list[str] = []
        self.processed_products: list[str] = []

    def process_user(self, user: User) -> dict[str, Any]:
        """Process a user and log the access."""
        self.session.log_file_access("core/models/user.py")
        self.processed_users.append(user.id)
        return user.to_dict()

    def process_product(self, product: Product) -> dict[str, Any]:
        """Process a product and log the access."""
        self.session.log_file_access("core/models/product.py")
        self.processed_products.append(product.id)
        return product.to_dict()

    def run_batch_operations(self, users: list[User], products: list[Product]) -> dict[str, Any]:
        """Run batch operations on users and products."""
        # Process all users
        for user in users:
            self.process_user(user)

        # Process all products
        for product in products:
            self.process_product(product)

        # Log service accesses
        self.session.log_file_access("core/services/user_service.py")
        self.session.log_file_access("core/services/product_service.py")

        return {
            "users_processed": len(self.processed_users),
            "products_processed": len(self.processed_products),
            "session_stats": self.session.get_access_stats(),
        }


def simulate_long_session(duration_hours: int = 8, accesses_per_hour: int = 100) -> dict:
    """Simulate a long-running session.

    Args:
        duration_hours: How long the session runs.
        accesses_per_hour: How many file accesses per hour.

    Returns:
        Session statistics.
    """
    session = SessionManager()

    # Simulate file accesses
    files = [
        "core/models/user.py",
        "core/models/product.py",
        "core/models/order.py",
        "core/services/user_service.py",
        "core/services/product_service.py",
        "core/services/order_service.py",
        "core/utils/validation.py",
        "core/utils/formatting.py",
        "api/endpoints.py",
        "data/repository.py",
    ]

    total_accesses = duration_hours * accesses_per_hour
    for i in range(total_accesses):
        file_index = i % len(files)
        session.log_file_access(files[file_index])

    return session.get_access_stats()
