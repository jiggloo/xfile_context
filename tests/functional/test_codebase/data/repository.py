# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Repository pattern for data access abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from tests.functional.test_codebase.core.models.base import BaseModel

T = TypeVar("T", bound=BaseModel)


class Repository(ABC, Generic[T]):
    """Abstract repository interface for data access."""

    @abstractmethod
    def get(self, entity_id: str) -> T | None:
        """Get an entity by its ID.

        Args:
            entity_id: The ID of the entity.

        Returns:
            The entity if found, None otherwise.
        """
        pass

    @abstractmethod
    def get_all(self) -> list[T]:
        """Get all entities.

        Returns:
            A list of all entities.
        """
        pass

    @abstractmethod
    def save(self, entity: T) -> T:
        """Save an entity (create or update).

        Args:
            entity: The entity to save.

        Returns:
            The saved entity.
        """
        pass

    @abstractmethod
    def delete(self, entity_id: str) -> bool:
        """Delete an entity by its ID.

        Args:
            entity_id: The ID of the entity to delete.

        Returns:
            True if deleted, False if not found.
        """
        pass

    @abstractmethod
    def exists(self, entity_id: str) -> bool:
        """Check if an entity exists.

        Args:
            entity_id: The ID of the entity.

        Returns:
            True if the entity exists, False otherwise.
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """Get the total count of entities.

        Returns:
            The number of entities.
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all entities from the repository."""
        pass
