# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-18: Parsing Failure

This module is VALID Python code that imports from files
that might have syntax errors.

Expected behavior when a referenced file has syntax errors:
- Skip relationship detection for the broken file
- Log error about parsing failure
- Continue processing other files normally

NOTE: The actual file with syntax errors would be created
separately during testing (e.g., ec18_syntax_error.py.broken).
This file demonstrates code that DEPENDS on potentially broken files.
"""

from typing import Any

# Normal imports that should work
from tests.functional.test_codebase.core.models.user import User
from tests.functional.test_codebase.core.utils.validation import validate_email


class ParsingErrorHandler:
    """Handler for dealing with parsing errors gracefully.

    When the analyzer encounters a file with syntax errors,
    it should handle the error gracefully without crashing.
    """

    def __init__(self) -> None:
        self.parse_errors: list[dict[str, Any]] = []
        self.successful_parses: list[str] = []

    def record_parse_error(
        self, file_path: str, error_message: str, line_number: int | None = None
    ) -> None:
        """Record a parsing error.

        Args:
            file_path: Path to the file with error.
            error_message: The error message.
            line_number: Line number where error occurred.
        """
        self.parse_errors.append(
            {
                "file": file_path,
                "error": error_message,
                "line": line_number,
            }
        )

    def record_successful_parse(self, file_path: str) -> None:
        """Record a successful parse."""
        self.successful_parses.append(file_path)

    def get_stats(self) -> dict[str, Any]:
        """Get parsing statistics."""
        return {
            "successful": len(self.successful_parses),
            "errors": len(self.parse_errors),
            "error_details": self.parse_errors,
        }


class SyntaxErrorRecovery:
    """Recovery strategies for syntax errors.

    Demonstrates how the system should handle syntax errors
    in dependent files.
    """

    @staticmethod
    def handle_import_error(module_name: str, error: Exception) -> dict[str, Any]:
        """Handle an import error gracefully.

        Args:
            module_name: Name of the module that failed to import.
            error: The exception that occurred.

        Returns:
            Error information dictionary.
        """
        return {
            "module": module_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "recovery": "Module marked as unanalyzable",
        }

    @staticmethod
    def safe_import(module_name: str) -> tuple[Any | None, str | None]:
        """Attempt to import a module safely.

        Returns:
            Tuple of (module or None, error message or None).
        """
        try:
            import importlib

            module = importlib.import_module(module_name)
            return (module, None)
        except SyntaxError as e:
            return (None, f"Syntax error at line {e.lineno}: {e.msg}")
        except ImportError as e:
            return (None, f"Import error: {e}")
        except Exception as e:
            return (None, f"Unexpected error: {e}")


# Normal functions that use correctly imported modules
def process_user_safely(user_data: dict[str, Any]) -> User | None:
    """Process user data safely.

    Uses correctly imported User model and validation.
    """
    email = user_data.get("email", "")
    if not validate_email(email):
        return None

    return User(
        username=user_data.get("username", ""),
        email=email,
        first_name=user_data.get("first_name", ""),
        last_name=user_data.get("last_name", ""),
    )
