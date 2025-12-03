# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""User service for managing user operations."""

from __future__ import annotations

from tests.functional.test_codebase.core.models.user import User
from tests.functional.test_codebase.core.services.base_service import BaseService
from tests.functional.test_codebase.core.utils.validation import validate_email, validate_username
from tests.functional.test_codebase.data.repository import Repository


class UserService(BaseService[User]):
    """Service for managing users."""

    def __init__(self, repository: Repository[User]) -> None:
        """Initialize the user service.

        Args:
            repository: The user repository.
        """
        super().__init__(repository)

    def _validate_create(self, entity: User) -> None:
        """Validate a user before creation.

        Args:
            entity: The user to validate.

        Raises:
            ValueError: If validation fails.
        """
        if not entity.username:
            raise ValueError("Username is required")
        if not validate_username(entity.username):
            raise ValueError("Invalid username format")
        if not entity.email:
            raise ValueError("Email is required")
        if not validate_email(entity.email):
            raise ValueError("Invalid email format")

        # Check for duplicate username
        existing = self.find_by_username(entity.username)
        if existing:
            raise ValueError(f"Username '{entity.username}' already exists")

        # Check for duplicate email
        existing = self.find_by_email(entity.email)
        if existing:
            raise ValueError(f"Email '{entity.email}' already exists")

    def _validate_update(self, entity: User) -> None:
        """Validate a user before update.

        Args:
            entity: The user to validate.

        Raises:
            ValueError: If validation fails.
        """
        if entity.email and not validate_email(entity.email):
            raise ValueError("Invalid email format")

    def find_by_username(self, username: str) -> User | None:
        """Find a user by username.

        Args:
            username: The username to search for.

        Returns:
            The user if found, None otherwise.
        """
        for user in self.get_all():
            if user.username == username:
                return user
        return None

    def find_by_email(self, email: str) -> User | None:
        """Find a user by email.

        Args:
            email: The email to search for.

        Returns:
            The user if found, None otherwise.
        """
        for user in self.get_all():
            if user.email == email:
                return user
        return None

    def get_active_users(self) -> list[User]:
        """Get all active users.

        Returns:
            A list of active users.
        """
        return [user for user in self.get_all() if user.is_active]

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user account.

        Args:
            user_id: The ID of the user to deactivate.

        Returns:
            True if successful, False if user not found.
        """
        user = self.get_by_id(user_id)
        if not user:
            return False
        user.deactivate()
        self.update(user)
        self.logger.info(f"User {user_id} deactivated")
        return True

    def activate_user(self, user_id: str) -> bool:
        """Activate a user account.

        Args:
            user_id: The ID of the user to activate.

        Returns:
            True if successful, False if user not found.
        """
        user = self.get_by_id(user_id)
        if not user:
            return False
        user.activate()
        self.update(user)
        self.logger.info(f"User {user_id} activated")
        return True
