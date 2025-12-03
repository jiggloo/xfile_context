# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-14: Deleted Files

This module imports from other files that may be deleted.
When a referenced file is deleted, the relationship graph should be updated.

Expected behavior:
- File watcher detects deletion
- Deleted file is removed from relationship graph
- Warning is logged about broken references
"""

from typing import Any

from tests.functional.test_codebase.core.models.product import Product

# These imports create dependencies that can be tested for deletion handling
from tests.functional.test_codebase.core.models.user import User
from tests.functional.test_codebase.core.services.user_service import UserService

# This module may reference a file that gets deleted during testing
# The analyzer should handle this gracefully


class DeletionTestHelper:
    """Helper class for testing file deletion scenarios.

    This class has dependencies on other modules. If those modules
    are deleted, the analyzer should:
    1. Detect the deletion via file watcher
    2. Remove the deleted file from the relationship graph
    3. Log a warning about the missing dependency
    """

    def __init__(self) -> None:
        self.users: list[User] = []
        self.products: list[Product] = []

    def add_user(self, user: User) -> None:
        """Add a user to the list."""
        self.users.append(user)

    def add_product(self, product: Product) -> None:
        """Add a product to the list."""
        self.products.append(product)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of stored items."""
        return {
            "user_count": len(self.users),
            "product_count": len(self.products),
        }


def create_test_user() -> User:
    """Create a test user.

    This function depends on User model.
    If user.py is deleted, this reference becomes broken.
    """
    return User(username="test_user", email="test@example.com")


def create_test_product() -> Product:
    """Create a test product.

    This function depends on Product model.
    If product.py is deleted, this reference becomes broken.
    """
    from decimal import Decimal

    return Product(name="Test Product", price=Decimal("19.99"), quantity=10)


# Function that uses a service which could be deleted
def get_user_via_service(user_id: str, service: UserService) -> User | None:
    """Get a user via the user service.

    If UserService is deleted, this function breaks.
    """
    return service.get_by_id(user_id)
