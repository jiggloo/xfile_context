# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Shared fixtures for integration tests.

Provides representative Python project structures and test utilities
for integration testing per TDD Section 3.13.2 and 3.13.3.
"""

from pathlib import Path

import pytest


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a representative Python project structure for integration testing.

    Creates a multi-module project with:
    - Package structure with __init__.py files
    - Cross-file imports (regular, aliased, conditional)
    - Function calls across modules
    - Class inheritance across files
    - Edge cases (wildcards, TYPE_CHECKING, dynamic patterns)

    Per TDD Section 3.13.3 (Test Data Strategy).

    Returns:
        Path to the project root directory
    """
    project_root = tmp_path / "sample_project"
    project_root.mkdir()

    # Create package structure
    pkg_dir = project_root / "mypackage"
    pkg_dir.mkdir()

    utils_dir = pkg_dir / "utils"
    utils_dir.mkdir()

    models_dir = pkg_dir / "models"
    models_dir.mkdir()

    # Create __init__.py files
    (pkg_dir / "__init__.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Main package init."""

from .core import main_function
from .models.base import BaseModel

__all__ = ["main_function", "BaseModel"]
'''
    )

    (utils_dir / "__init__.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Utilities package."""

from .helpers import format_string, parse_data
'''
    )

    (models_dir / "__init__.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Models package."""

from .base import BaseModel
from .user import User
'''
    )

    # Create utils/helpers.py
    (utils_dir / "helpers.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Helper utilities."""

import json
import os
from typing import Any, Dict


def format_string(value: str) -> str:
    """Format a string value."""
    return value.strip().lower()


def parse_data(data: str) -> Dict[str, Any]:
    """Parse JSON data."""
    return json.loads(data)


def get_env_value(key: str) -> str:
    """Get environment variable."""
    return os.getenv(key, "")
'''
    )

    # Create models/base.py
    (models_dir / "base.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Base model class."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseModel(ABC):
    """Abstract base model."""

    def __init__(self, id: str):
        self.id = id

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        pass

    def validate(self) -> bool:
        """Validate the model."""
        return bool(self.id)
'''
    )

    # Create models/user.py with class inheritance
    (models_dir / "user.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""User model."""

from typing import Any, Dict, TYPE_CHECKING

from .base import BaseModel

if TYPE_CHECKING:
    from ..utils.helpers import format_string


class User(BaseModel):
    """User model with inheritance from BaseModel."""

    def __init__(self, id: str, name: str, email: str):
        super().__init__(id)
        self.name = name
        self.email = email

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
        }

    def get_display_name(self) -> str:
        """Get formatted display name."""
        from ..utils.helpers import format_string
        return format_string(self.name)
'''
    )

    # Create core.py with function calls
    (pkg_dir / "core.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Core module with cross-file dependencies."""

import logging
from typing import Optional

from .models.user import User
from .utils.helpers import format_string, parse_data

logger = logging.getLogger(__name__)


def main_function(data: str) -> Optional[User]:
    """Main function that uses utilities and models."""
    try:
        parsed = parse_data(data)
        user_id = format_string(parsed.get("id", ""))
        name = parsed.get("name", "")
        email = parsed.get("email", "")

        if user_id:
            return User(user_id, name, email)
        return None
    except Exception as e:
        logger.error(f"Error: {e}")
        return None


def process_users(users_data: list) -> list:
    """Process multiple users."""
    results = []
    for data in users_data:
        user = main_function(data)
        if user and user.validate():
            results.append(user.to_dict())
    return results
'''
    )

    # Create edge case files

    # Wildcard imports (EC-3)
    (pkg_dir / "wildcard_example.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Example with wildcard imports."""

from .utils.helpers import *  # noqa: F401,F403

result = format_string("TEST")  # Uses imported function
'''
    )

    # Dynamic patterns (EC-6 through EC-10)
    (pkg_dir / "dynamic_patterns.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Examples of dynamic patterns that cannot be statically analyzed."""

import importlib

# EC-6: Dynamic dispatch via getattr
class PluginLoader:
    def load_plugin(self, name: str):
        module = importlib.import_module(f".plugins.{name}", package=__package__)
        return getattr(module, "Plugin")()

# EC-7: Monkey patching
def patch_module(module, attr_name, new_value):
    setattr(module, attr_name, new_value)

# EC-9: exec/eval
def evaluate_expression(expr: str):
    return eval(expr)

def execute_code(code: str):
    exec(code)

# EC-8: Decorator patterns
def my_decorator(func):
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@my_decorator
def decorated_function():
    pass
'''
    )

    # Circular dependency example (EC-1 - Python allows this)
    (pkg_dir / "circular_a.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Circular dependency example - module A."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .circular_b import function_b


def function_a() -> str:
    """Function A that uses B."""
    from .circular_b import function_b
    return f"A calls {function_b()}"
'''
    )

    (pkg_dir / "circular_b.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Circular dependency example - module B."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .circular_a import function_a


def function_b() -> str:
    """Function B."""
    return "B"


def function_b_uses_a() -> str:
    """Function B that uses A."""
    from .circular_a import function_a
    return f"B calls {function_a()}"
'''
    )

    # Create a test directory (should be detected as test code)
    tests_dir = project_root / "tests"
    tests_dir.mkdir()

    (tests_dir / "__init__.py").write_text(
        """# Copyright (c) 2025 Henru Wang
# All rights reserved.
"""
    )

    (tests_dir / "test_core.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for core module."""

import pytest

from mypackage.core import main_function, process_users


class TestMainFunction:
    def test_valid_data(self):
        data = '{"id": "123", "name": "Test", "email": "test@example.com"}'
        result = main_function(data)
        assert result is not None
        assert result.id == "123"

    def test_invalid_data(self):
        result = main_function("invalid json")
        assert result is None
'''
    )

    return project_root


@pytest.fixture
def minimal_project(tmp_path: Path) -> Path:
    """Create a minimal Python project for simple integration tests.

    Returns:
        Path to the project root directory
    """
    project_root = tmp_path / "minimal_project"
    project_root.mkdir()

    (project_root / "main.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Main module."""

from utils import helper_function


def main():
    result = helper_function()
    print(result)


if __name__ == "__main__":
    main()
'''
    )

    (project_root / "utils.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Utility functions."""


def helper_function() -> str:
    """Helper function."""
    return "Hello from helper"


def another_function() -> int:
    """Another helper."""
    return 42
'''
    )

    return project_root


@pytest.fixture
def edge_case_project(tmp_path: Path) -> Path:
    """Create a project with edge cases for thorough testing.

    Covers EC-1 through EC-20 edge cases from TDD Section 3.13.3.

    Returns:
        Path to the project root directory
    """
    project_root = tmp_path / "edge_cases"
    project_root.mkdir()

    # EC-2: Aliased imports
    (project_root / "aliased_imports.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Aliased import examples."""

import numpy as np
import pandas as pd
from collections import OrderedDict as OD
from typing import Dict as D, List as L
'''
    )

    # EC-4: Conditional imports based on platform
    (project_root / "conditional_imports.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Conditional import examples."""

import sys

if sys.platform == "win32":
    import winreg
else:
    import posix

try:
    import optional_module
except ImportError:
    optional_module = None

# Version-based import
if sys.version_info >= (3, 11):
    from tomllib import loads
else:
    from tomli import loads
'''
    )

    # EC-5: TYPE_CHECKING imports
    (project_root / "type_checking_imports.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""TYPE_CHECKING import examples."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from heavy_module import HeavyClass
    from another_module import AnotherClass


def process(item: "HeavyClass") -> "AnotherClass":
    """Process using type hints."""
    pass
'''
    )

    # EC-17: Large file (boundary test)
    large_file = project_root / "large_file.py"
    lines = ["# Copyright (c) 2025 Henru Wang\n", "# All rights reserved.\n", "\n"]
    lines.extend(["# Line of code\n"] * 100)
    lines.append("import os\n")
    large_file.write_text("".join(lines))

    # EC-18: Syntax error file
    (project_root / "syntax_error.py").write_text(
        '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""File with syntax error."""

def broken_function(
    # Missing closing paren and colon
'''
    )

    # EC-19: Binary file (should be skipped)
    binary_file = project_root / "binary_data.pyc"
    binary_file.write_bytes(b"\x00\x01\x02\x03\x04\x05")

    # EC-20: Empty file
    (project_root / "empty_file.py").write_text("")

    return project_root
