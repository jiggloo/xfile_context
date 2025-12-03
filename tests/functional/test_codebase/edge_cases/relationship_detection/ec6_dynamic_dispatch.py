# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-6: Dynamic Dispatch (Unhandled in v0.1.0)

This module demonstrates dynamic dispatch patterns using getattr.
These cannot be statically analyzed as the function name is runtime-determined.

Expected behavior:
- Analyzer should emit warning for dynamic dispatch in source modules
- Analyzer should NOT attempt to track these relationships
- Warning should include file path, line number, and explanation
"""

from typing import Any, Callable

# Static import for comparison
from tests.functional.test_codebase.core.models.user import User


class PluginManager:
    """Manages plugins with dynamic method invocation."""

    def __init__(self) -> None:
        self.plugins: dict[str, Any] = {}

    def register(self, name: str, plugin: Any) -> None:
        """Register a plugin."""
        self.plugins[name] = plugin

    def call_plugin_method(self, plugin_name: str, method_name: str, *args) -> Any:
        """Call a method on a plugin dynamically.

        This uses getattr with a runtime-determined method name.
        The analyzer cannot know which method will be called.
        """
        plugin = self.plugins.get(plugin_name)
        if plugin is None:
            raise ValueError(f"Plugin not found: {plugin_name}")

        # Dynamic dispatch - method_name is determined at runtime
        method = getattr(plugin, method_name)
        return method(*args)


class DynamicHandler:
    """Handler that uses dynamic method dispatch."""

    def handle_request(self, action: str, data: dict[str, Any]) -> Any:
        """Handle a request by dynamically calling the appropriate method.

        The action parameter determines which method is called.
        This is a common pattern but cannot be statically analyzed.
        """
        handler_name = f"handle_{action}"

        # Dynamic dispatch - handler_name determined at runtime
        if hasattr(self, handler_name):
            handler = getattr(self, handler_name)
            return handler(data)
        else:
            raise ValueError(f"Unknown action: {action}")

    def handle_create(self, data: dict[str, Any]) -> dict[str, str]:
        """Handle create action."""
        return {"status": "created", "data": str(data)}

    def handle_update(self, data: dict[str, Any]) -> dict[str, str]:
        """Handle update action."""
        return {"status": "updated", "data": str(data)}

    def handle_delete(self, data: dict[str, Any]) -> dict[str, str]:
        """Handle delete action."""
        return {"status": "deleted", "data": str(data)}


def call_method_by_name(obj: Any, method_name: str, *args, **kwargs) -> Any:
    """Generic function to call any method by name.

    This is another form of dynamic dispatch that cannot be analyzed.
    """
    method: Callable = getattr(obj, method_name)
    return method(*args, **kwargs)


# Static usage for comparison - this CAN be tracked
def create_user_statically(username: str, email: str) -> User:
    """Create a user using static method call."""
    return User(username=username, email=email)
