# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-4: Wildcard Imports

This module demonstrates wildcard import patterns.
These can only be tracked at module level, not function level.

Expected behavior:
- Analyzer should track module-level dependency
- Analyzer CANNOT track specific function usage from wildcard imports
- Optional warning may be emitted based on configuration
"""

# Wildcard import - all exports from utils
from tests.functional.test_codebase.core.utils import *  # noqa: F401, F403

# Note: This imports format_currency, format_date, format_percentage,
# validate_email, validate_phone, validate_postal_code,
# generate_slug, truncate_text, sanitize_input
# But analyzer cannot know which specific functions are used.


def process_user_email(email: str) -> bool:
    """Process user email using wildcard-imported function.

    The analyzer knows this file imports from core.utils.*
    but cannot determine which specific function is called.
    """
    return validate_email(email)  # noqa: F405


def format_price(amount) -> str:
    """Format a price using wildcard-imported function."""
    return format_currency(amount)  # noqa: F405


def create_product_slug(name: str) -> str:
    """Create a product slug using wildcard-imported function."""
    return generate_slug(name)  # noqa: F405


def safe_user_input(text: str) -> str:
    """Sanitize user input using wildcard-imported function."""
    return sanitize_input(text)  # noqa: F405


def validate_contact_info(email: str, phone: str, postal_code: str) -> dict[str, bool]:
    """Validate contact information using multiple wildcard-imported functions."""
    return {
        "email": validate_email(email),  # noqa: F405
        "phone": validate_phone(phone),  # noqa: F405
        "postal_code": validate_postal_code(postal_code),  # noqa: F405
    }
