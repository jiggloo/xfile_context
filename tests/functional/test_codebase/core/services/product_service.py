# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Product service for managing product operations."""

from __future__ import annotations

from decimal import Decimal

from tests.functional.test_codebase.core.models.product import Product
from tests.functional.test_codebase.core.services.base_service import BaseService
from tests.functional.test_codebase.data.repository import Repository


class ProductService(BaseService[Product]):
    """Service for managing products."""

    def __init__(self, repository: Repository[Product]) -> None:
        """Initialize the product service.

        Args:
            repository: The product repository.
        """
        super().__init__(repository)

    def _validate_create(self, entity: Product) -> None:
        """Validate a product before creation.

        Args:
            entity: The product to validate.

        Raises:
            ValueError: If validation fails.
        """
        if not entity.name:
            raise ValueError("Product name is required")
        if entity.price < 0:
            raise ValueError("Price cannot be negative")

    def _validate_update(self, entity: Product) -> None:
        """Validate a product before update.

        Args:
            entity: The product to validate.

        Raises:
            ValueError: If validation fails.
        """
        if entity.price < 0:
            raise ValueError("Price cannot be negative")
        if entity.quantity < 0:
            raise ValueError("Quantity cannot be negative")

    def find_by_category(self, category: str) -> list[Product]:
        """Find products by category.

        Args:
            category: The category to search for.

        Returns:
            A list of products in the category.
        """
        return [p for p in self.get_all() if p.category == category]

    def find_in_stock(self) -> list[Product]:
        """Find all products that are in stock.

        Returns:
            A list of in-stock products.
        """
        return [p for p in self.get_all() if p.in_stock]

    def find_by_price_range(self, min_price: Decimal, max_price: Decimal) -> list[Product]:
        """Find products within a price range.

        Args:
            min_price: The minimum price.
            max_price: The maximum price.

        Returns:
            A list of products within the price range.
        """
        return [p for p in self.get_all() if min_price <= p.price <= max_price]

    def update_stock(self, product_id: str, quantity: int) -> bool:
        """Update the stock quantity for a product.

        Args:
            product_id: The ID of the product.
            quantity: The new quantity.

        Returns:
            True if successful, False if product not found.
        """
        product = self.get_by_id(product_id)
        if not product:
            return False

        if quantity < 0:
            raise ValueError("Quantity cannot be negative")

        product.quantity = quantity
        self.update(product)
        self.logger.info(f"Product {product_id} stock updated to {quantity}")
        return True

    def reduce_stock(self, product_id: str, amount: int) -> bool:
        """Reduce the stock for a product.

        Args:
            product_id: The ID of the product.
            amount: The amount to reduce.

        Returns:
            True if successful, False if insufficient stock or not found.
        """
        product = self.get_by_id(product_id)
        if not product:
            return False

        if product.reduce_stock(amount):
            self.update(product)
            self.logger.info(f"Product {product_id} stock reduced by {amount}")
            return True
        return False

    def get_low_stock_products(self, threshold: int = 10) -> list[Product]:
        """Get products with low stock.

        Args:
            threshold: The stock level threshold.

        Returns:
            A list of products with stock below the threshold.
        """
        return [p for p in self.get_all() if p.is_available and p.quantity <= threshold]
