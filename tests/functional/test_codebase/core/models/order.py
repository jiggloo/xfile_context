# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Order model definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from tests.functional.test_codebase.core.models.base import BaseModel
from tests.functional.test_codebase.core.utils.formatting import format_currency

if TYPE_CHECKING:
    from tests.functional.test_codebase.core.models.product import Product


class OrderStatus(Enum):
    """Possible statuses for an order."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class OrderItem:
    """Represents an item in an order."""

    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal

    @property
    def subtotal(self) -> Decimal:
        """Calculate the subtotal for this item."""
        return self.unit_price * self.quantity


@dataclass
class Order(BaseModel):
    """Represents a customer order."""

    user_id: str = ""
    status: OrderStatus = OrderStatus.PENDING
    items: list[OrderItem] = field(default_factory=list)
    shipping_address: str = ""
    notes: str = ""

    @property
    def total(self) -> Decimal:
        """Calculate the total order amount."""
        return sum((item.subtotal for item in self.items), Decimal("0.00"))

    @property
    def formatted_total(self) -> str:
        """Get the formatted total string."""
        return format_currency(self.total)

    @property
    def item_count(self) -> int:
        """Get the total number of items in the order."""
        return sum(item.quantity for item in self.items)

    def to_dict(self) -> dict[str, Any]:
        """Convert order to dictionary representation."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "user_id": self.user_id,
                "status": self.status.value,
                "items": [
                    {
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "unit_price": str(item.unit_price),
                        "subtotal": str(item.subtotal),
                    }
                    for item in self.items
                ],
                "shipping_address": self.shipping_address,
                "notes": self.notes,
                "total": str(self.total),
                "formatted_total": self.formatted_total,
                "item_count": self.item_count,
            }
        )
        return base_dict

    def add_item(self, product: Product, quantity: int) -> bool:
        """Add a product to the order."""
        if quantity <= 0:
            return False
        if not product.in_stock or product.quantity < quantity:
            return False

        item = OrderItem(
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            unit_price=product.price,
        )
        self.items.append(item)
        self.update()
        return True

    def confirm(self) -> bool:
        """Confirm the order."""
        if self.status != OrderStatus.PENDING:
            return False
        if not self.items:
            return False
        self.status = OrderStatus.CONFIRMED
        self.update()
        return True

    def cancel(self) -> bool:
        """Cancel the order."""
        if self.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            return False
        self.status = OrderStatus.CANCELLED
        self.update()
        return True

    def ship(self) -> bool:
        """Mark the order as shipped."""
        if self.status != OrderStatus.CONFIRMED:
            return False
        self.status = OrderStatus.SHIPPED
        self.update()
        return True

    def deliver(self) -> bool:
        """Mark the order as delivered."""
        if self.status != OrderStatus.SHIPPED:
            return False
        self.status = OrderStatus.DELIVERED
        self.update()
        return True
