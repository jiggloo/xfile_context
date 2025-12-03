# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Order service for managing order operations."""

from __future__ import annotations

from tests.functional.test_codebase.core.models.order import Order, OrderStatus
from tests.functional.test_codebase.core.models.product import Product
from tests.functional.test_codebase.core.models.user import User
from tests.functional.test_codebase.core.services.base_service import BaseService
from tests.functional.test_codebase.core.services.notification_service import NotificationService
from tests.functional.test_codebase.core.services.product_service import ProductService
from tests.functional.test_codebase.data.repository import Repository


class OrderService(BaseService[Order]):
    """Service for managing orders."""

    def __init__(
        self,
        repository: Repository[Order],
        product_service: ProductService,
        notification_service: NotificationService,
    ) -> None:
        """Initialize the order service.

        Args:
            repository: The order repository.
            product_service: The product service for stock management.
            notification_service: The notification service for sending alerts.
        """
        super().__init__(repository)
        self.product_service = product_service
        self.notification_service = notification_service

    def _validate_create(self, entity: Order) -> None:
        """Validate an order before creation.

        Args:
            entity: The order to validate.

        Raises:
            ValueError: If validation fails.
        """
        if not entity.user_id:
            raise ValueError("User ID is required")
        if not entity.shipping_address:
            raise ValueError("Shipping address is required")

    def _validate_update(self, entity: Order) -> None:
        """Validate an order before update.

        Args:
            entity: The order to validate.

        Raises:
            ValueError: If validation fails.
        """
        pass  # Orders can be updated freely

    def create_order(self, user: User, shipping_address: str) -> Order:
        """Create a new order for a user.

        Args:
            user: The user placing the order.
            shipping_address: The shipping address.

        Returns:
            The created order.
        """
        order = Order(user_id=user.id, shipping_address=shipping_address)
        return self.create(order)

    def add_product_to_order(self, order: Order, product: Product, quantity: int) -> bool:
        """Add a product to an order.

        Args:
            order: The order to add to.
            product: The product to add.
            quantity: The quantity to add.

        Returns:
            True if successful, False otherwise.
        """
        if order.status != OrderStatus.PENDING:
            self.logger.warning(f"Cannot add to order {order.id} - status is {order.status}")
            return False

        if order.add_item(product, quantity):
            self.update(order)
            return True
        return False

    def confirm_order(self, order: Order) -> bool:
        """Confirm an order and reduce product stock.

        Args:
            order: The order to confirm.

        Returns:
            True if successful, False otherwise.
        """
        if not order.confirm():
            return False

        # Reduce stock for all items
        for item in order.items:
            self.product_service.reduce_stock(item.product_id, item.quantity)

        self.update(order)

        # Send confirmation notification
        self.notification_service.send_order_confirmation(order)

        return True

    def cancel_order(self, order: Order) -> bool:
        """Cancel an order and restore product stock.

        Args:
            order: The order to cancel.

        Returns:
            True if successful, False otherwise.
        """
        if not order.cancel():
            return False

        # Restore stock if order was confirmed
        if order.status == OrderStatus.CONFIRMED:
            for item in order.items:
                product = self.product_service.get_by_id(item.product_id)
                if product:
                    product.add_stock(item.quantity)
                    self.product_service.update(product)

        self.update(order)

        # Send cancellation notification
        self.notification_service.send_order_cancellation(order)

        return True

    def ship_order(self, order: Order) -> bool:
        """Mark an order as shipped.

        Args:
            order: The order to ship.

        Returns:
            True if successful, False otherwise.
        """
        if not order.ship():
            return False

        self.update(order)
        self.notification_service.send_shipping_notification(order)
        return True

    def deliver_order(self, order: Order) -> bool:
        """Mark an order as delivered.

        Args:
            order: The order to mark delivered.

        Returns:
            True if successful, False otherwise.
        """
        if not order.deliver():
            return False

        self.update(order)
        self.notification_service.send_delivery_notification(order)
        return True

    def get_orders_by_user(self, user_id: str) -> list[Order]:
        """Get all orders for a user.

        Args:
            user_id: The user ID.

        Returns:
            A list of orders for the user.
        """
        return [o for o in self.get_all() if o.user_id == user_id]

    def get_orders_by_status(self, status: OrderStatus) -> list[Order]:
        """Get all orders with a specific status.

        Args:
            status: The order status.

        Returns:
            A list of orders with the status.
        """
        return [o for o in self.get_all() if o.status == status]
