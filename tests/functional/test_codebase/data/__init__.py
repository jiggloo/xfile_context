# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Data access layer for the test codebase."""

from tests.functional.test_codebase.data.in_memory_store import InMemoryStore
from tests.functional.test_codebase.data.repository import Repository

__all__ = ["Repository", "InMemoryStore"]
