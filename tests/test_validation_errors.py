# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
Validation test file with INTENTIONAL errors to verify developer experience infrastructure.
This file tests that pre-commit hooks, GitHub Actions, and branch protection work correctly.

Test Scenarios:
1. Formatting Error: Unformatted code (black/isort violations)
2. Linting Error: Code quality violations (ruff)
3. Type Error: Type checking violations (mypy)
4. Test Failure: Failing test case (pytest)
5. Multi-Environment: Tests run across Python versions
6. Branch Protection: PR blocked until all checks pass
"""

from typing import List


# FORMATTING ERROR: Intentionally bad formatting
def badly_formatted_function(x, y, z):
    result = x + y + z
    return result



# LINTING ERROR: Unused imports and variables

unused_variable = 42


# TYPE ERROR: Invalid type annotations and usage
def type_error_function(x: int) -> str:
    return x + 5  # Returns int but annotated as str


def another_type_error(items: List[str]) -> int:
    return items  # Returns List[str] but annotated as int


# TEST FAILURE: Intentionally failing test
def test_validation_failure():
    """This test MUST fail to verify pytest catches it."""
    assert False, "Intentional test failure to verify infrastructure"


def test_type_checking():
    """This test uses the type-error functions."""
    result = type_error_function(10)
    assert isinstance(result, str)  # This will fail at runtime
