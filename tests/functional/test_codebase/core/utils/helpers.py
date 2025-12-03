# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""General helper utility functions."""

import html
import re
import unicodedata
from typing import Any


def generate_slug(text: str, max_length: int = 50) -> str:
    """Generate a URL-friendly slug from text.

    Args:
        text: The text to convert to a slug.
        max_length: Maximum length of the slug.

    Returns:
        A URL-friendly slug string.
    """
    if not text:
        return ""

    # Normalize unicode characters
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

    # Convert to lowercase and replace spaces with hyphens
    slug = ascii_text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)

    # Truncate to max length, avoiding cutting in the middle of a word
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit("-", 1)[0]

    return slug.strip("-")


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to a maximum length with an optional suffix.

    Args:
        text: The text to truncate.
        max_length: Maximum length of the result (including suffix).
        suffix: The suffix to add if truncated.

    Returns:
        The truncated text.
    """
    if not text or len(text) <= max_length:
        return text

    truncate_at = max_length - len(suffix)
    if truncate_at <= 0:
        return suffix[:max_length]

    # Try to truncate at a word boundary
    truncated = text[:truncate_at]
    last_space = truncated.rfind(" ")
    if last_space > truncate_at * 0.5:
        truncated = truncated[:last_space]

    return truncated.rstrip() + suffix


def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS attacks.

    Args:
        text: The text to sanitize.

    Returns:
        The sanitized text.
    """
    if not text:
        return ""

    # Escape HTML special characters
    sanitized = html.escape(text)

    # Remove any null bytes
    sanitized = sanitized.replace("\x00", "")

    return sanitized


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries.

    Args:
        base: The base dictionary.
        override: The dictionary with values to override.

    Returns:
        A new dictionary with merged values.
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def chunk_list(items: list[Any], chunk_size: int) -> list[list[Any]]:
    """Split a list into chunks of a specified size.

    Args:
        items: The list to split.
        chunk_size: The size of each chunk.

    Returns:
        A list of chunks.
    """
    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")

    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]
