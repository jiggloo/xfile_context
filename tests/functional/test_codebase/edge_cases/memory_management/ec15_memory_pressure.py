# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-15: Memory Pressure

This module demonstrates patterns that could cause memory pressure.
The analyzer should implement LRU eviction when cache exceeds limits.

Expected behavior:
- Cache grows up to 50KB limit
- LRU eviction removes least-recently-used entries first
- Core functionality remains stable under memory pressure
"""

from typing import Any

from tests.functional.test_codebase.core.models.base import BaseModel
from tests.functional.test_codebase.core.models.order import Order
from tests.functional.test_codebase.core.models.product import Product
from tests.functional.test_codebase.core.models.user import User


class LargeDataProcessor:
    """Processor that works with large amounts of data.

    This class simulates scenarios where many files are accessed,
    potentially causing memory pressure in the cache.
    """

    def __init__(self) -> None:
        self.processed_items: list[dict[str, Any]] = []
        self.cache: dict[str, Any] = {}

    def process_user_batch(self, users: list[User]) -> list[dict[str, Any]]:
        """Process a batch of users.

        Simulates accessing many User objects, which would cause
        the analyzer to cache user.py content multiple times.
        """
        results = []
        for user in users:
            result = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
            }
            results.append(result)
            self.processed_items.append(result)
        return results

    def process_product_batch(self, products: list[Product]) -> list[dict[str, Any]]:
        """Process a batch of products.

        Simulates accessing many Product objects.
        """
        results = []
        for product in products:
            result = {
                "id": product.id,
                "name": product.name,
                "price": str(product.price),
                "in_stock": product.in_stock,
            }
            results.append(result)
            self.processed_items.append(result)
        return results

    def process_order_batch(self, orders: list[Order]) -> list[dict[str, Any]]:
        """Process a batch of orders.

        Simulates accessing many Order objects.
        """
        results = []
        for order in orders:
            result = {
                "id": order.id,
                "user_id": order.user_id,
                "status": order.status.value,
                "total": str(order.total),
                "item_count": order.item_count,
            }
            results.append(result)
            self.processed_items.append(result)
        return results

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return {
            "items": len(self.cache),
            "processed_total": len(self.processed_items),
        }


def generate_many_models(count: int) -> list[BaseModel]:
    """Generate many model instances.

    This function creates many objects, simulating a scenario
    where the analyzer must track many relationships.
    """
    models: list[BaseModel] = []
    for i in range(count):
        if i % 3 == 0:
            models.append(User(username=f"user_{i}", email=f"user{i}@example.com"))
        elif i % 3 == 1:
            from decimal import Decimal

            models.append(Product(name=f"Product {i}", price=Decimal(str(i * 10)), quantity=100))
        else:
            models.append(Order(user_id=f"user_{i // 3}"))
    return models


class CacheTester:
    """Helper class for testing cache behavior under pressure."""

    def __init__(self, max_entries: int = 100) -> None:
        self.max_entries = max_entries
        self.entries: dict[str, Any] = {}
        self.access_order: list[str] = []

    def add(self, key: str, value: Any) -> None:
        """Add an entry, evicting LRU if necessary."""
        if len(self.entries) >= self.max_entries and key not in self.entries and self.access_order:
            # Evict LRU
            lru_key = self.access_order.pop(0)
            del self.entries[lru_key]

        self.entries[key] = value
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

    def get(self, key: str) -> Any | None:
        """Get an entry, updating access order."""
        if key in self.entries:
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.entries[key]
        return None

    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        return {
            "entries": len(self.entries),
            "max_entries": self.max_entries,
        }
