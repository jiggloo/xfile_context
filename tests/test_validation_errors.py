# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
Validation test file to verify developer experience infrastructure.

This file successfully validated that pre-commit hooks, GitHub Actions, and
branch protection rules work correctly by testing with intentional errors.

All test scenarios validated:
1. ✅ Formatting Error: black/isort caught and auto-fixed
2. ✅ Linting Error: ruff caught violations
3. ✅ Type Error: mypy caught type mismatches
4. ✅ Test Failure: pytest caught failing tests
5. ✅ Multi-Environment: Matrix tests ran across Python 3.8-3.12
6. ✅ Branch Protection: PR blocked until all checks passed

Errors have been fixed - this file now passes all checks.
"""

from typing import List


def properly_formatted_function(x: int, y: int, z: int) -> int:
    """Add three numbers together."""
    result = x + y + z
    return result


def type_correct_function(x: int) -> int:
    """Add 5 to input (fixed: return type now matches)."""
    return x + 5


def another_type_correct_function(items: List[str]) -> int:
    """Return count of items (fixed: return type now matches)."""
    return len(items)


def test_validation_success():
    """Test that validates infrastructure works correctly."""
    # This test now passes to verify PR can merge after fixes
    assert properly_formatted_function(1, 2, 3) == 6


def test_type_checking_success():
    """Test the corrected type-safe functions."""
    result = type_correct_function(10)
    assert result == 15
    assert isinstance(result, int)

    items_count = another_type_correct_function(["a", "b", "c"])
    assert items_count == 3
    assert isinstance(items_count, int)
