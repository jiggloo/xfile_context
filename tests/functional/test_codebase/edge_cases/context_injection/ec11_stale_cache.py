# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-11: Stale Cache After External Edit

This module is designed to test cache invalidation scenarios.
When this file is edited externally, the cache should be invalidated.

Expected behavior:
- File watcher should detect modification
- Cache should be invalidated
- Next access should force re-read
"""

from tests.functional.test_codebase.core.models.user import User
from tests.functional.test_codebase.core.utils.validation import validate_email

# Version marker - change this to simulate external edit
VERSION = "1.0.0"


def get_version() -> str:
    """Get the current version.

    If the cache is stale, this might return an old version.
    """
    return VERSION


def create_user_v1(username: str, email: str) -> User:
    """Create a user (version 1 implementation).

    This function might be modified by an external editor.
    The cache should be invalidated when that happens.
    """
    if not validate_email(email):
        raise ValueError(f"Invalid email: {email}")
    return User(username=username, email=email)


class ConfigurableService:
    """A service whose behavior might change with external edits.

    Configuration changes made by external editors should
    trigger cache invalidation.
    """

    # Configuration that might be edited externally
    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 30
    DEBUG_MODE = False

    def __init__(self) -> None:
        self.retries = self.MAX_RETRIES
        self.timeout = self.TIMEOUT_SECONDS

    def get_config(self) -> dict:
        """Get current configuration."""
        return {
            "max_retries": self.MAX_RETRIES,
            "timeout_seconds": self.TIMEOUT_SECONDS,
            "debug_mode": self.DEBUG_MODE,
            "version": VERSION,
        }

    def process(self, data: str) -> str:
        """Process data according to current configuration."""
        if self.DEBUG_MODE:
            print(f"Processing: {data}")
        return f"Processed: {data}"
