# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""API endpoint implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tests.functional.test_codebase.core.models.user import User
from tests.functional.test_codebase.core.services.order_service import OrderService
from tests.functional.test_codebase.core.services.product_service import ProductService
from tests.functional.test_codebase.core.services.user_service import UserService


@dataclass
class APIResponse:
    """Standard API response structure."""

    success: bool
    data: Any = None
    error: str | None = None
    status_code: int = 200


class BaseEndpoint:
    """Base class for API endpoints."""

    def _success(self, data: Any, status_code: int = 200) -> APIResponse:
        """Create a success response.

        Args:
            data: The response data.
            status_code: The HTTP status code.

        Returns:
            An APIResponse object.
        """
        return APIResponse(success=True, data=data, status_code=status_code)

    def _error(self, message: str, status_code: int = 400) -> APIResponse:
        """Create an error response.

        Args:
            message: The error message.
            status_code: The HTTP status code.

        Returns:
            An APIResponse object.
        """
        return APIResponse(success=False, error=message, status_code=status_code)


class UserEndpoint(BaseEndpoint):
    """API endpoints for user operations."""

    def __init__(self, user_service: UserService) -> None:
        """Initialize the endpoint.

        Args:
            user_service: The user service.
        """
        self.service = user_service

    def get_user(self, user_id: str) -> APIResponse:
        """Get a user by ID.

        Args:
            user_id: The user ID.

        Returns:
            An APIResponse with the user data.
        """
        user = self.service.get_by_id(user_id)
        if not user:
            return self._error("User not found", 404)
        return self._success(user.to_dict())

    def create_user(self, data: dict[str, Any]) -> APIResponse:
        """Create a new user.

        Args:
            data: The user data.

        Returns:
            An APIResponse with the created user.
        """
        try:
            user = User(
                username=data.get("username", ""),
                email=data.get("email", ""),
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
            )
            created = self.service.create(user)
            return self._success(created.to_dict(), 201)
        except ValueError as e:
            return self._error(str(e))

    def list_users(self) -> APIResponse:
        """List all users.

        Returns:
            An APIResponse with the list of users.
        """
        users = self.service.get_all()
        return self._success([u.to_dict() for u in users])


class ProductEndpoint(BaseEndpoint):
    """API endpoints for product operations."""

    def __init__(self, product_service: ProductService) -> None:
        """Initialize the endpoint.

        Args:
            product_service: The product service.
        """
        self.service = product_service

    def get_product(self, product_id: str) -> APIResponse:
        """Get a product by ID.

        Args:
            product_id: The product ID.

        Returns:
            An APIResponse with the product data.
        """
        product = self.service.get_by_id(product_id)
        if not product:
            return self._error("Product not found", 404)
        return self._success(product.to_dict())

    def list_products(self, category: str | None = None) -> APIResponse:
        """List products, optionally filtered by category.

        Args:
            category: Optional category filter.

        Returns:
            An APIResponse with the list of products.
        """
        products = self.service.find_by_category(category) if category else self.service.get_all()
        return self._success([p.to_dict() for p in products])

    def list_in_stock(self) -> APIResponse:
        """List all in-stock products.

        Returns:
            An APIResponse with the list of in-stock products.
        """
        products = self.service.find_in_stock()
        return self._success([p.to_dict() for p in products])


class OrderEndpoint(BaseEndpoint):
    """API endpoints for order operations."""

    def __init__(self, order_service: OrderService) -> None:
        """Initialize the endpoint.

        Args:
            order_service: The order service.
        """
        self.service = order_service

    def get_order(self, order_id: str) -> APIResponse:
        """Get an order by ID.

        Args:
            order_id: The order ID.

        Returns:
            An APIResponse with the order data.
        """
        order = self.service.get_by_id(order_id)
        if not order:
            return self._error("Order not found", 404)
        return self._success(order.to_dict())

    def get_user_orders(self, user_id: str) -> APIResponse:
        """Get all orders for a user.

        Args:
            user_id: The user ID.

        Returns:
            An APIResponse with the list of orders.
        """
        orders = self.service.get_orders_by_user(user_id)
        return self._success([o.to_dict() for o in orders])

    def confirm_order(self, order_id: str) -> APIResponse:
        """Confirm an order.

        Args:
            order_id: The order ID.

        Returns:
            An APIResponse indicating success or failure.
        """
        order = self.service.get_by_id(order_id)
        if not order:
            return self._error("Order not found", 404)
        if self.service.confirm_order(order):
            return self._success(order.to_dict())
        return self._error("Could not confirm order")
