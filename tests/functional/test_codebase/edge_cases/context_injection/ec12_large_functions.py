# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-12: Large Functions

This module contains large functions that might exceed token limits.
The analyzer should inject function signature only, with pointer to full definition.

Expected behavior:
- If function exceeds token limit, inject signature only
- Provide pointer to full definition location
"""

from decimal import Decimal
from typing import Any

from tests.functional.test_codebase.core.models.order import Order, OrderItem, OrderStatus
from tests.functional.test_codebase.core.models.product import Product
from tests.functional.test_codebase.core.models.user import User


def process_complex_order(
    user: User,
    products: list[Product],
    quantities: list[int],
    shipping_address: str,
    billing_address: str,
    payment_method: str,
    coupon_code: str | None = None,
    gift_wrap: bool = False,
    gift_message: str | None = None,
    rush_delivery: bool = False,
    insurance: bool = False,
) -> dict[str, Any]:
    """Process a complex order with many options.

    This is a large function that demonstrates the token limit scenario.
    When context injection occurs, only the signature should be injected
    if the full function would exceed the token limit.

    Args:
        user: The user placing the order.
        products: List of products to order.
        quantities: Quantities for each product.
        shipping_address: Where to ship the order.
        billing_address: Billing address for payment.
        payment_method: Payment method (card, paypal, etc).
        coupon_code: Optional discount coupon.
        gift_wrap: Whether to gift wrap the items.
        gift_message: Optional gift message.
        rush_delivery: Whether to use rush delivery.
        insurance: Whether to add shipping insurance.

    Returns:
        A dictionary containing order details and status.

    Raises:
        ValueError: If validation fails.
        RuntimeError: If processing fails.
    """
    # Validate inputs
    if not user:
        raise ValueError("User is required")
    if not products:
        raise ValueError("At least one product is required")
    if len(products) != len(quantities):
        raise ValueError("Products and quantities must match")
    if not shipping_address:
        raise ValueError("Shipping address is required")
    if not billing_address:
        raise ValueError("Billing address is required")
    if not payment_method:
        raise ValueError("Payment method is required")

    # Validate payment method
    valid_payment_methods = ["card", "paypal", "bank_transfer", "crypto"]
    if payment_method not in valid_payment_methods:
        raise ValueError(f"Invalid payment method: {payment_method}")

    # Check product availability
    unavailable_products = []
    for product, quantity in zip(products, quantities):
        if not product.in_stock:
            unavailable_products.append(product.name)
        elif product.quantity < quantity:
            unavailable_products.append(f"{product.name} (only {product.quantity} available)")

    if unavailable_products:
        raise ValueError(
            f"The following products are unavailable: {', '.join(unavailable_products)}"
        )

    # Create order
    order = Order(user_id=user.id, shipping_address=shipping_address)

    # Add items to order
    subtotal = Decimal("0.00")
    for product, quantity in zip(products, quantities):
        item = OrderItem(
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            unit_price=product.price,
        )
        order.items.append(item)
        subtotal += item.subtotal

    # Calculate discounts
    discount = Decimal("0.00")
    if coupon_code:
        # Simulate coupon validation
        coupon_discounts = {
            "SAVE10": Decimal("0.10"),
            "SAVE20": Decimal("0.20"),
            "FREESHIP": Decimal("0.00"),  # Free shipping handled separately
        }
        if coupon_code in coupon_discounts:
            discount = subtotal * coupon_discounts[coupon_code]

    # Calculate shipping
    base_shipping = Decimal("5.99")
    if rush_delivery:
        base_shipping += Decimal("15.00")
    if insurance:
        base_shipping += Decimal("3.99")
    if coupon_code == "FREESHIP":
        base_shipping = Decimal("0.00")

    # Calculate gift wrap cost
    gift_wrap_cost = Decimal("0.00")
    if gift_wrap:
        gift_wrap_cost = Decimal("4.99")

    # Calculate tax (simplified - 8% tax rate)
    tax_rate = Decimal("0.08")
    taxable_amount = subtotal - discount
    tax = taxable_amount * tax_rate

    # Calculate total
    total = subtotal - discount + base_shipping + gift_wrap_cost + tax

    # Process payment (simulated)
    payment_result = {
        "status": "success",
        "transaction_id": f"TXN-{order.id[:8]}",
        "amount": str(total),
        "method": payment_method,
    }

    # Update order status
    order.status = OrderStatus.CONFIRMED
    order.notes = ""
    if gift_message:
        order.notes += f"Gift message: {gift_message}\n"
    if rush_delivery:
        order.notes += "Rush delivery requested.\n"

    # Prepare response
    result = {
        "order_id": order.id,
        "status": order.status.value,
        "user_id": user.id,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "subtotal": str(item.subtotal),
            }
            for item in order.items
        ],
        "subtotal": str(subtotal),
        "discount": str(discount),
        "coupon_applied": coupon_code if discount > 0 else None,
        "shipping": str(base_shipping),
        "gift_wrap_cost": str(gift_wrap_cost),
        "tax": str(tax),
        "total": str(total),
        "payment": payment_result,
        "shipping_address": shipping_address,
        "billing_address": billing_address,
        "gift_wrap": gift_wrap,
        "gift_message": gift_message,
        "rush_delivery": rush_delivery,
        "insurance": insurance,
    }

    return result


def validate_order_comprehensively(
    order_data: dict[str, Any],
    validate_user: bool = True,
    validate_products: bool = True,
    validate_payment: bool = True,
    validate_shipping: bool = True,
    strict_mode: bool = False,
) -> tuple[bool, list[str]]:
    """Comprehensive order validation with multiple checks.

    Another large function for testing token limit handling.

    Args:
        order_data: The order data to validate.
        validate_user: Whether to validate user data.
        validate_products: Whether to validate product data.
        validate_payment: Whether to validate payment data.
        validate_shipping: Whether to validate shipping data.
        strict_mode: Whether to use strict validation rules.

    Returns:
        A tuple of (is_valid, list_of_errors).
    """
    errors: list[str] = []

    # User validation
    if validate_user:
        user_data = order_data.get("user", {})
        if not user_data.get("id"):
            errors.append("User ID is required")
        if not user_data.get("email"):
            errors.append("User email is required")
        if strict_mode and not user_data.get("verified"):
            errors.append("User must be verified in strict mode")

    # Product validation
    if validate_products:
        items = order_data.get("items", [])
        if not items:
            errors.append("Order must have at least one item")
        for i, item in enumerate(items):
            if not item.get("product_id"):
                errors.append(f"Item {i}: Product ID is required")
            if not item.get("quantity") or item["quantity"] <= 0:
                errors.append(f"Item {i}: Valid quantity is required")
            if strict_mode and item.get("quantity", 0) > 100:
                errors.append(f"Item {i}: Quantity exceeds limit in strict mode")

    # Payment validation
    if validate_payment:
        payment = order_data.get("payment", {})
        if not payment.get("method"):
            errors.append("Payment method is required")
        if not payment.get("amount"):
            errors.append("Payment amount is required")
        if strict_mode and not payment.get("verified"):
            errors.append("Payment must be verified in strict mode")

    # Shipping validation
    if validate_shipping:
        shipping = order_data.get("shipping", {})
        if not shipping.get("address"):
            errors.append("Shipping address is required")
        if strict_mode:
            if not shipping.get("phone"):
                errors.append("Phone number required for shipping in strict mode")
            if not shipping.get("postal_code"):
                errors.append("Postal code required in strict mode")

    return (len(errors) == 0, errors)
