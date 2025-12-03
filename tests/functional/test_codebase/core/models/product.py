# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Product model definition."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from tests.functional.test_codebase.core.models.base import BaseModel
from tests.functional.test_codebase.core.utils.formatting import format_currency


@dataclass
class Product(BaseModel):
    """Represents a product in the catalog."""

    name: str = ""
    description: str = ""
    price: Decimal = Decimal("0.00")
    quantity: int = 0
    category: str = ""
    is_available: bool = True

    def __post_init__(self) -> None:
        """Validate product data after initialization."""
        if self.price < 0:
            raise ValueError("Price cannot be negative")
        if self.quantity < 0:
            raise ValueError("Quantity cannot be negative")

    @property
    def formatted_price(self) -> str:
        """Get the formatted price string."""
        return format_currency(self.price)

    @property
    def in_stock(self) -> bool:
        """Check if the product is in stock."""
        return self.quantity > 0 and self.is_available

    def to_dict(self) -> dict[str, Any]:
        """Convert product to dictionary representation."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "name": self.name,
                "description": self.description,
                "price": str(self.price),
                "formatted_price": self.formatted_price,
                "quantity": self.quantity,
                "category": self.category,
                "is_available": self.is_available,
                "in_stock": self.in_stock,
            }
        )
        return base_dict

    def reduce_stock(self, amount: int) -> bool:
        """Reduce the stock quantity by the specified amount."""
        if amount > self.quantity:
            return False
        self.quantity -= amount
        self.update()
        return True

    def add_stock(self, amount: int) -> None:
        """Add to the stock quantity."""
        if amount < 0:
            raise ValueError("Cannot add negative stock")
        self.quantity += amount
        self.update()
