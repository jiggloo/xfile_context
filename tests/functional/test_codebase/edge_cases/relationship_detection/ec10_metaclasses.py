# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-10: Metaclasses (Partially Handled)

This module demonstrates metaclass patterns.
The analyzer can track metaclass usage but cannot analyze metaclass logic.

Expected behavior:
- Analyzer should track metaclass usage in relationship graph metadata
- Analyzer should track metaclass reference if imported
- Informational warning about runtime behavior differences
"""

from typing import Any

# Static import for comparison
from tests.functional.test_codebase.core.models.base import BaseModel


class SingletonMeta(type):
    """Metaclass that implements the singleton pattern."""

    _instances: dict[type, Any] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class RegistryMeta(type):
    """Metaclass that registers all subclasses."""

    registry: dict[str, type] = {}

    def __new__(mcs, name: str, bases: tuple, namespace: dict):  # noqa: N804
        cls = super().__new__(mcs, name, bases, namespace)
        if name != "RegistryBase":
            mcs.registry[name] = cls
        return cls


class ValidationMeta(type):
    """Metaclass that adds validation to all methods."""

    def __new__(mcs, name: str, bases: tuple, namespace: dict):  # noqa: N804
        # Wrap all methods with validation
        for attr_name, attr_value in namespace.items():
            if callable(attr_value) and not attr_name.startswith("_"):
                namespace[attr_name] = mcs._wrap_with_validation(attr_value)
        return super().__new__(mcs, name, bases, namespace)

    @staticmethod
    def _wrap_with_validation(method):
        def wrapper(*args, **kwargs):
            # Pre-call validation
            for arg in args[1:]:  # Skip self
                if arg is None:
                    raise ValueError("None argument not allowed")
            return method(*args, **kwargs)

        return wrapper


# Classes using metaclasses
class DatabaseConnection(metaclass=SingletonMeta):
    """A singleton database connection.

    This class uses SingletonMeta, so only one instance will ever exist.
    The analyzer should note this uses a custom metaclass.
    """

    def __init__(self) -> None:
        self.connected = False
        self.connection_string = ""

    def connect(self, conn_string: str) -> None:
        """Connect to the database."""
        self.connection_string = conn_string
        self.connected = True

    def disconnect(self) -> None:
        """Disconnect from the database."""
        self.connected = False


class RegistryBase(metaclass=RegistryMeta):
    """Base class for registered handlers."""

    pass


class UserHandler(RegistryBase):
    """Handler for user operations - automatically registered."""

    def handle(self, data: dict) -> dict:
        return {"handler": "user", "data": data}


class ProductHandler(RegistryBase):
    """Handler for product operations - automatically registered."""

    def handle(self, data: dict) -> dict:
        return {"handler": "product", "data": data}


class ValidatedService(metaclass=ValidationMeta):
    """Service with automatic method validation."""

    def process(self, data: dict) -> dict:
        """Process data - will be wrapped with validation."""
        return {"processed": True, **data}

    def transform(self, value: str) -> str:
        """Transform value - will be wrapped with validation."""
        return value.upper()


# Regular class for comparison
class RegularClass(BaseModel):
    """A regular class without metaclass for comparison."""

    name: str = ""

    def get_name(self) -> str:
        return self.name


def get_all_handlers() -> dict[str, type]:
    """Get all registered handlers from the registry metaclass."""
    return RegistryMeta.registry.copy()
