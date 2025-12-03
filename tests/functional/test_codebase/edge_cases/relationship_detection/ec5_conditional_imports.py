# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-5: Conditional Imports

This module demonstrates conditional import patterns,
particularly TYPE_CHECKING which is common for avoiding circular imports.

Expected behavior:
- Analyzer should track conditional dependencies with metadata
- TYPE_CHECKING imports should be marked as type-only dependencies
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Conditional imports for type hints only
if TYPE_CHECKING:
    from tests.functional.test_codebase.core.models.order import Order
    from tests.functional.test_codebase.core.models.product import Product
    from tests.functional.test_codebase.core.models.user import User
    from tests.functional.test_codebase.core.services.user_service import UserService

# Regular imports
from tests.functional.test_codebase.core.utils.validation import validate_email


class UserProcessor:
    """Processes user data with type hints from conditional imports."""

    def __init__(self, service: UserService) -> None:
        """Initialize with a user service.

        The UserService type hint comes from TYPE_CHECKING import.
        At runtime, this is just a regular object.
        """
        self.service = service

    def process_user(self, user: User) -> dict[str, Any]:
        """Process a user and return results.

        Args:
            user: The User instance (type from TYPE_CHECKING).

        Returns:
            A dictionary with processed user data.
        """
        return {
            "id": user.id,
            "username": user.username,
            "email_valid": validate_email(user.email),
        }

    def get_user_orders(self, user: User) -> list[Order]:
        """Get orders for a user.

        Both User and Order types come from TYPE_CHECKING imports.
        """
        return user.orders

    def create_order_summary(self, order: Order) -> dict[str, Any]:
        """Create a summary of an order."""
        return {
            "id": order.id,
            "status": order.status.value,
            "total": str(order.total),
        }


def get_product_info(product: Product) -> dict[str, Any]:
    """Get product information using TYPE_CHECKING import type."""
    return {
        "id": product.id,
        "name": product.name,
        "price": str(product.price),
    }
