# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""In-memory implementation of the repository pattern."""

from __future__ import annotations

from typing import Generic, TypeVar

from tests.functional.test_codebase.core.models.base import BaseModel
from tests.functional.test_codebase.data.repository import Repository

T = TypeVar("T", bound=BaseModel)


class InMemoryStore(Repository[T], Generic[T]):
    """In-memory repository implementation using a dictionary."""

    def __init__(self) -> None:
        """Initialize the in-memory store."""
        self._data: dict[str, T] = {}

    def get(self, entity_id: str) -> T | None:
        """Get an entity by its ID.

        Args:
            entity_id: The ID of the entity.

        Returns:
            The entity if found, None otherwise.
        """
        return self._data.get(entity_id)

    def get_all(self) -> list[T]:
        """Get all entities.

        Returns:
            A list of all entities.
        """
        return list(self._data.values())

    def save(self, entity: T) -> T:
        """Save an entity (create or update).

        Args:
            entity: The entity to save.

        Returns:
            The saved entity.
        """
        self._data[entity.id] = entity
        return entity

    def delete(self, entity_id: str) -> bool:
        """Delete an entity by its ID.

        Args:
            entity_id: The ID of the entity to delete.

        Returns:
            True if deleted, False if not found.
        """
        if entity_id in self._data:
            del self._data[entity_id]
            return True
        return False

    def exists(self, entity_id: str) -> bool:
        """Check if an entity exists.

        Args:
            entity_id: The ID of the entity.

        Returns:
            True if the entity exists, False otherwise.
        """
        return entity_id in self._data

    def count(self) -> int:
        """Get the total count of entities.

        Returns:
            The number of entities.
        """
        return len(self._data)

    def clear(self) -> None:
        """Clear all entities from the repository."""
        self._data.clear()

    def find_by(self, **kwargs) -> list[T]:
        """Find entities matching the given criteria.

        Args:
            **kwargs: Key-value pairs to match against entity attributes.

        Returns:
            A list of matching entities.
        """
        results = []
        for entity in self._data.values():
            match = True
            for key, value in kwargs.items():
                if not hasattr(entity, key) or getattr(entity, key) != value:
                    match = False
                    break
            if match:
                results.append(entity)
        return results
