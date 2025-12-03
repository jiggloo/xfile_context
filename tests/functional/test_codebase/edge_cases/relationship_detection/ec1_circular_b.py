# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-1: Circular Dependencies - Module B

This module completes the circular import with module A.
Uses module-level import to allow the circular dependency to work.

Expected behavior:
- Analyzer should detect the circular dependency: ec1_circular_b -> ec1_circular_a -> ec1_circular_b
- Both directions of the relationship should be tracked
"""

from tests.functional.test_codebase.edge_cases.relationship_detection import ec1_circular_a


class ServiceB:
    """A service that depends on ServiceA."""

    def __init__(self) -> None:
        self.name = "ServiceB"

    def call_service_a(self) -> str:
        """Call ServiceA and return result."""
        service_a = ec1_circular_a.ServiceA()
        return f"{self.name} called {service_a.get_name()}"

    def get_name(self) -> str:
        """Get the service name."""
        return self.name


def get_service_b() -> ServiceB:
    """Factory function to get ServiceB instance."""
    return ServiceB()
