# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""User model definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tests.functional.test_codebase.core.models.base import BaseModel
from tests.functional.test_codebase.core.utils.validation import validate_email

if TYPE_CHECKING:
    from tests.functional.test_codebase.core.models.order import Order


@dataclass
class User(BaseModel):
    """Represents a user in the system."""

    username: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    is_active: bool = True
    orders: list[Order] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate user data after initialization."""
        if self.email and not validate_email(self.email):
            raise ValueError(f"Invalid email format: {self.email}")

    @property
    def full_name(self) -> str:
        """Get the user's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    def to_dict(self) -> dict[str, Any]:
        """Convert user to dictionary representation."""
        base_dict = super().to_dict()
        base_dict.update(
            {
                "username": self.username,
                "email": self.email,
                "first_name": self.first_name,
                "last_name": self.last_name,
                "is_active": self.is_active,
                "full_name": self.full_name,
            }
        )
        return base_dict

    def add_order(self, order: Order) -> None:
        """Add an order to the user's order list."""
        self.orders.append(order)
        self.update()

    def deactivate(self) -> None:
        """Deactivate the user account."""
        self.is_active = False
        self.update()

    def activate(self) -> None:
        """Activate the user account."""
        self.is_active = True
        self.update()
