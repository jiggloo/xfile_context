# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-3: Aliased Imports

This module demonstrates various aliased import patterns.
The analyzer should track both original names and aliases.

Expected behavior:
- Analyzer should track original name AND alias
- When the alias is used, analyzer should match it to the original
"""

# Standard library alias (common pattern)
from datetime import datetime as dt
from decimal import Decimal as Dec

# Module alias
import tests.functional.test_codebase.core.utils.formatting as fmt

# Class alias
from tests.functional.test_codebase.core.models.user import User as UserModel

# Multiple aliases from same module
from tests.functional.test_codebase.core.utils.helpers import generate_slug as slugify
from tests.functional.test_codebase.core.utils.helpers import sanitize_input as sanitize
from tests.functional.test_codebase.core.utils.helpers import truncate_text as truncate

# Function alias with 'from' import
from tests.functional.test_codebase.core.utils.validation import validate_email as check_email
from tests.functional.test_codebase.core.utils.validation import validate_phone as check_phone


def format_user_currency(amount: Dec) -> str:
    """Format currency using aliased import.

    This uses fmt.format_currency where fmt is an alias for the formatting module.
    """
    return fmt.format_currency(amount)


def validate_user_data(email: str, phone: str) -> dict[str, bool]:
    """Validate user data using aliased validators.

    Uses check_email and check_phone aliases.
    """
    return {
        "email_valid": check_email(email),
        "phone_valid": check_phone(phone),
    }


def create_user_model(username: str, email: str) -> UserModel:
    """Create a user using the aliased class name."""
    return UserModel(username=username, email=email)


def process_text(text: str, max_length: int = 100) -> str:
    """Process text using multiple aliased functions."""
    safe_text = sanitize(text)
    slug = slugify(safe_text)
    return truncate(slug, max_length)


def get_timestamp() -> str:
    """Get current timestamp using aliased datetime."""
    return dt.now().isoformat()
