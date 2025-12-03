# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-8: Decorators Modifying Behavior (Partially Handled)

This module demonstrates decorator patterns.
The analyzer can track decorated functions but cannot analyze decorator logic.

Expected behavior:
- Analyzer should track decorated function definitions
- Analyzer should track decorator as a dependency if imported
- Informational warning for complex/dynamic decorators
"""

import functools
import time
from typing import Any, Callable, TypeVar

# Import a class to use in decorators
from tests.functional.test_codebase.core.models.user import User

F = TypeVar("F", bound=Callable[..., Any])


# Simple decorator - can be tracked
def log_calls(func: F) -> F:
    """Decorator that logs function calls."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print(f"Calling {func.__name__}")
        result = func(*args, **kwargs)
        print(f"Finished {func.__name__}")
        return result

    return wrapper  # type: ignore


# Decorator with arguments
def retry(attempts: int = 3, delay: float = 1.0):
    """Decorator that retries a function on failure."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < attempts - 1:
                        time.sleep(delay)
            raise last_exception  # type: ignore

        return wrapper  # type: ignore

    return decorator


# Decorator that modifies return type
def ensure_list(func: Callable[..., Any]) -> Callable[..., list]:
    """Decorator that ensures the return value is always a list."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> list:
        result = func(*args, **kwargs)
        if isinstance(result, list):
            return result
        return [result]

    return wrapper


# Class-based decorator
class CacheResult:
    """Decorator class that caches function results."""

    def __init__(self, ttl: int = 60) -> None:
        self.ttl = ttl
        self.cache: dict[str, tuple[Any, float]] = {}

    def __call__(self, func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            if key in self.cache:
                result, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    return result
            result = func(*args, **kwargs)
            self.cache[key] = (result, time.time())
            return result

        return wrapper  # type: ignore


# Using decorators on functions
@log_calls
def greet(name: str) -> str:
    """A decorated function."""
    return f"Hello, {name}!"


@retry(attempts=3, delay=0.5)
def fetch_data(url: str) -> dict[str, Any]:
    """A function with retry decorator."""
    # Simulated fetch
    return {"url": url, "data": "fetched"}


@ensure_list
def get_items(count: int) -> list[int]:
    """A function that ensures list return."""
    if count == 1:
        return [1]  # Single item
    return list(range(count))


@CacheResult(ttl=300)
def expensive_calculation(x: int, y: int) -> int:
    """A function with caching decorator."""
    time.sleep(0.1)  # Simulate expensive operation
    return x * y


# Multiple decorators stacked
@log_calls
@retry(attempts=2)
def complex_operation(data: dict[str, Any]) -> dict[str, Any]:
    """A function with multiple decorators."""
    return {"processed": True, **data}


# Method decorator using imported class
@log_calls
def create_user(username: str, email: str) -> User:
    """Create a user with logging."""
    return User(username=username, email=email)
