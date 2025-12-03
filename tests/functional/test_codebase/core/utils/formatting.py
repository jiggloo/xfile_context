# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Formatting utility functions."""

from datetime import datetime
from decimal import Decimal


def format_currency(amount: Decimal, currency: str = "USD") -> str:
    """Format a decimal amount as a currency string.

    Args:
        amount: The decimal amount to format.
        currency: The currency code (default: USD).

    Returns:
        A formatted currency string (e.g., "$1,234.56").
    """
    symbols = {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
    }
    symbol = symbols.get(currency, currency + " ")

    # Format with thousands separator and 2 decimal places
    formatted = f"{float(amount):,.2f}"
    return f"{symbol}{formatted}"


def format_date(dt: datetime, format_style: str = "short") -> str:
    """Format a datetime object as a string.

    Args:
        dt: The datetime to format.
        format_style: One of "short", "long", or "iso".

    Returns:
        A formatted date string.
    """
    formats = {
        "short": "%m/%d/%Y",
        "long": "%B %d, %Y",
        "iso": "%Y-%m-%d",
        "datetime": "%Y-%m-%d %H:%M:%S",
    }
    fmt = formats.get(format_style, formats["short"])
    return dt.strftime(fmt)


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a float as a percentage string.

    Args:
        value: The value to format (0.0 to 1.0).
        decimals: Number of decimal places.

    Returns:
        A formatted percentage string (e.g., "75.5%").
    """
    percentage = value * 100
    return f"{percentage:.{decimals}f}%"


def format_file_size(size_bytes: int) -> str:
    """Format a file size in bytes as a human-readable string.

    Args:
        size_bytes: The size in bytes.

    Returns:
        A formatted size string (e.g., "1.5 MB").
    """
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"
