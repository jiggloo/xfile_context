# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-13: Multiple Definitions - Alternative Module

This module contains alternative definitions of functions
also defined in ec13_multiple_definitions.py.

Expected behavior:
- When either 'process' is referenced, analyzer should note both locations
- Context injection should disambiguate: "process from ec13_multiple_definitions.py:X
  or ec13_multiple_definitions_alt.py:Y"
"""

from typing import Any


def process(data: str) -> str:
    """Process data - alternative version.

    This is an alternative definition of 'process'.
    The main definition is in ec13_multiple_definitions.py.
    """
    return f"Processed in ec13_alt: {data.upper()}"


def transform(value: Any) -> Any:
    """Transform a value - alternative version.

    Uses different transformation logic than the other module.
    """
    return {"transformed_in": "ec13_alt", "value": str(value)}


def validate(input_data: str) -> bool:
    """Validate input - alternative version.

    More strict validation than the other module.
    """
    return len(input_data) >= 3 and input_data.isalnum()


class Handler:
    """Handler class - alternative version.

    Different implementation than ec13_multiple_definitions.py.
    """

    def __init__(self, name: str = "ec13_alt") -> None:
        self.name = name
        self.processed_count = 0

    def handle(self, data: Any) -> dict[str, Any]:
        """Handle data with counting."""
        self.processed_count += 1
        return {
            "handler": self.name,
            "data": data,
            "count": self.processed_count,
        }


class Processor:
    """Processor class - alternative version."""

    @staticmethod
    def run(data: str) -> str:
        """Run the alternative processor."""
        return process(data)


# Alternative constant values
DEFAULT_TIMEOUT = 60  # Different from ec13
MAX_RETRIES = 5  # Different from ec13
DEBUG = True  # Different from ec13
