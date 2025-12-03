# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Base service class with common functionality."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from tests.functional.test_codebase.core.models.base import BaseModel
from tests.functional.test_codebase.data.repository import Repository

T = TypeVar("T", bound=BaseModel)


class BaseService(ABC, Generic[T]):
    """Abstract base class for all services."""

    def __init__(self, repository: Repository[T]) -> None:
        """Initialize the service with a repository.

        Args:
            repository: The repository for data access.
        """
        self.repository = repository
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_by_id(self, entity_id: str) -> T | None:
        """Get an entity by its ID.

        Args:
            entity_id: The ID of the entity to retrieve.

        Returns:
            The entity if found, None otherwise.
        """
        self.logger.debug(f"Getting entity with ID: {entity_id}")
        return self.repository.get(entity_id)

    def get_all(self) -> list[T]:
        """Get all entities.

        Returns:
            A list of all entities.
        """
        self.logger.debug("Getting all entities")
        return self.repository.get_all()

    def create(self, entity: T) -> T:
        """Create a new entity.

        Args:
            entity: The entity to create.

        Returns:
            The created entity.
        """
        self.logger.info(f"Creating entity with ID: {entity.id}")
        self._validate_create(entity)
        return self.repository.save(entity)

    def update(self, entity: T) -> T:
        """Update an existing entity.

        Args:
            entity: The entity to update.

        Returns:
            The updated entity.
        """
        self.logger.info(f"Updating entity with ID: {entity.id}")
        self._validate_update(entity)
        entity.update()
        return self.repository.save(entity)

    def delete(self, entity_id: str) -> bool:
        """Delete an entity by its ID.

        Args:
            entity_id: The ID of the entity to delete.

        Returns:
            True if deleted, False if not found.
        """
        self.logger.info(f"Deleting entity with ID: {entity_id}")
        return self.repository.delete(entity_id)

    @abstractmethod
    def _validate_create(self, entity: T) -> None:
        """Validate an entity before creation.

        Args:
            entity: The entity to validate.

        Raises:
            ValueError: If validation fails.
        """
        pass

    @abstractmethod
    def _validate_update(self, entity: T) -> None:
        """Validate an entity before update.

        Args:
            entity: The entity to validate.

        Raises:
            ValueError: If validation fails.
        """
        pass

    def to_dict(self, entity: T) -> dict[str, Any]:
        """Convert an entity to a dictionary.

        Args:
            entity: The entity to convert.

        Returns:
            A dictionary representation of the entity.
        """
        return entity.to_dict()
