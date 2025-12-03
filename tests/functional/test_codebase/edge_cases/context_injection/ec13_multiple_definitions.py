# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-13: Multiple Definitions

This module demonstrates functions defined in multiple places.
The analyzer should inject both with disambiguation.

Expected behavior:
- Analyzer detects both definitions
- Context injection includes disambiguation info
- Example: "process from utils.py:45 or helpers.py:78"
"""

from typing import Any

# Import functions with same name from different modules
# Note: In real code, this would cause a name conflict
# We're demonstrating the edge case for the analyzer


def process(data: str) -> str:
    """Process data - version in this module.

    This is one definition of 'process'. There's another
    in ec13_multiple_definitions_alt.py.
    """
    return f"Processed in ec13: {data}"


def transform(value: Any) -> Any:
    """Transform a value - version in this module.

    Also defined in ec13_multiple_definitions_alt.py.
    """
    return {"transformed_in": "ec13", "value": value}


def validate(input_data: str) -> bool:
    """Validate input - version in this module.

    The same function name exists in multiple places.
    """
    return len(input_data) > 0


class Handler:
    """Handler class - also defined elsewhere.

    This class name appears in multiple files to test
    the multiple definitions edge case.
    """

    def __init__(self, name: str = "ec13") -> None:
        self.name = name

    def handle(self, data: Any) -> dict[str, Any]:
        """Handle data."""
        return {"handler": self.name, "data": data}


class Processor:
    """Processor class with same name as in other files."""

    @staticmethod
    def run(data: str) -> str:
        """Run the processor."""
        return process(data)


# Constants that might be defined in multiple places
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
DEBUG = False
