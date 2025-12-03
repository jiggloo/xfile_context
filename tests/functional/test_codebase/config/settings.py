# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Application settings management."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from tests.functional.test_codebase.config.constants import (
    CACHE_TTL,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)


@dataclass
class DatabaseSettings:
    """Database configuration settings."""

    host: str = "localhost"
    port: int = 5432
    name: str = "app_db"
    user: str = "app_user"
    password: str = ""


@dataclass
class CacheSettings:
    """Cache configuration settings."""

    enabled: bool = True
    ttl: int = CACHE_TTL
    max_size: int = 1000


@dataclass
class APISettings:
    """API configuration settings."""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    page_size: int = DEFAULT_PAGE_SIZE
    max_page_size: int = MAX_PAGE_SIZE


@dataclass
class Settings:
    """Application settings container."""

    environment: str = "development"
    debug: bool = False
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)
    api: APISettings = field(default_factory=APISettings)

    @classmethod
    def from_env(cls) -> Settings:
        """Create settings from environment variables.

        Returns:
            A Settings instance configured from environment.
        """
        env = os.environ.get("APP_ENV", "development")
        debug = os.environ.get("APP_DEBUG", "false").lower() == "true"

        db_settings = DatabaseSettings(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            name=os.environ.get("DB_NAME", "app_db"),
            user=os.environ.get("DB_USER", "app_user"),
            password=os.environ.get("DB_PASSWORD", ""),
        )

        cache_settings = CacheSettings(
            enabled=os.environ.get("CACHE_ENABLED", "true").lower() == "true",
            ttl=int(os.environ.get("CACHE_TTL", str(CACHE_TTL))),
            max_size=int(os.environ.get("CACHE_MAX_SIZE", "1000")),
        )

        api_settings = APISettings(
            host=os.environ.get("API_HOST", "0.0.0.0"),
            port=int(os.environ.get("API_PORT", "8000")),
            debug=debug,
            page_size=int(os.environ.get("API_PAGE_SIZE", str(DEFAULT_PAGE_SIZE))),
            max_page_size=int(os.environ.get("API_MAX_PAGE_SIZE", str(MAX_PAGE_SIZE))),
        )

        return cls(
            environment=env,
            debug=debug,
            database=db_settings,
            cache=cache_settings,
            api=api_settings,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to dictionary.

        Returns:
            A dictionary representation of settings.
        """
        return {
            "environment": self.environment,
            "debug": self.debug,
            "database": {
                "host": self.database.host,
                "port": self.database.port,
                "name": self.database.name,
                "user": self.database.user,
                # Never include password in serialization
            },
            "cache": {
                "enabled": self.cache.enabled,
                "ttl": self.cache.ttl,
                "max_size": self.cache.max_size,
            },
            "api": {
                "host": self.api.host,
                "port": self.api.port,
                "debug": self.api.debug,
                "page_size": self.api.page_size,
                "max_page_size": self.api.max_page_size,
            },
        }


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the application settings singleton.

    Returns:
        The Settings instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reset_settings() -> None:
    """Reset the settings singleton (useful for testing)."""
    global _settings
    _settings = None
