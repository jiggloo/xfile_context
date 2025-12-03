# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-2: Dynamic Imports

This module demonstrates dynamic imports using importlib.
These cannot be statically analyzed.

Expected behavior:
- Analyzer should skip the dynamic import
- Analyzer should log this as untrackable
- Static imports in this file should still be tracked
"""

import importlib
from typing import Any

# This static import SHOULD be tracked
from tests.functional.test_codebase.core.utils.helpers import generate_slug


def load_module_dynamically(module_name: str) -> Any:
    """Load a module dynamically by name.

    This function uses importlib which cannot be statically analyzed.
    The analyzer should not attempt to track this relationship.

    Args:
        module_name: The fully qualified module name.

    Returns:
        The loaded module.
    """
    return importlib.import_module(module_name)


def load_class_dynamically(module_name: str, class_name: str) -> type:
    """Load a class dynamically from a module.

    Args:
        module_name: The fully qualified module name.
        class_name: The class name to load.

    Returns:
        The loaded class.
    """
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def load_plugin(plugin_name: str) -> Any:
    """Load a plugin by name.

    This is a common pattern in plugin systems where the
    module to load is determined at runtime.

    Args:
        plugin_name: The plugin name.

    Returns:
        The loaded plugin module.
    """
    plugin_module = f"plugins.{plugin_name}"
    return importlib.import_module(plugin_module)


# Use static import to demonstrate mixed tracking
def create_slug(text: str) -> str:
    """Create a URL slug using the static import."""
    return generate_slug(text)
