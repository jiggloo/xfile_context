# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Validation utility functions."""

import re
from typing import Pattern

# Compiled regex patterns for performance
EMAIL_PATTERN: Pattern[str] = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_PATTERN: Pattern[str] = re.compile(r"^\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$")
POSTAL_CODE_PATTERN: Pattern[str] = re.compile(r"^\d{5}(-\d{4})?$")
USERNAME_PATTERN: Pattern[str] = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


def validate_email(email: str) -> bool:
    """Validate an email address format.

    Args:
        email: The email address to validate.

    Returns:
        True if the email format is valid, False otherwise.
    """
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_PATTERN.match(email))


def validate_phone(phone: str) -> bool:
    """Validate a phone number format (US format).

    Args:
        phone: The phone number to validate.

    Returns:
        True if the phone format is valid, False otherwise.
    """
    if not phone or not isinstance(phone, str):
        return False
    # Remove common separators for validation
    cleaned = phone.replace(" ", "").replace("-", "").replace(".", "")
    return bool(PHONE_PATTERN.match(phone)) or (cleaned.isdigit() and len(cleaned) in (10, 11))


def validate_postal_code(postal_code: str) -> bool:
    """Validate a US postal code format.

    Args:
        postal_code: The postal code to validate.

    Returns:
        True if the postal code format is valid, False otherwise.
    """
    if not postal_code or not isinstance(postal_code, str):
        return False
    return bool(POSTAL_CODE_PATTERN.match(postal_code))


def validate_username(username: str) -> bool:
    """Validate a username format.

    Args:
        username: The username to validate.

    Returns:
        True if the username format is valid, False otherwise.
    """
    if not username or not isinstance(username, str):
        return False
    return bool(USERNAME_PATTERN.match(username))


def validate_password_strength(password: str) -> tuple[bool, list[str]]:
    """Validate password strength and return any issues.

    Args:
        password: The password to validate.

    Returns:
        A tuple of (is_valid, list_of_issues).
    """
    issues = []

    if len(password) < 8:
        issues.append("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        issues.append("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        issues.append("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        issues.append("Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        issues.append("Password must contain at least one special character")

    return (len(issues) == 0, issues)
