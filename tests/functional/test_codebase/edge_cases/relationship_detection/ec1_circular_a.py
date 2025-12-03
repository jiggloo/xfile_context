# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
EC-1: Circular Dependencies - Module A

This module demonstrates circular imports with module B.
Python allows this but it's considered a code smell.

Expected behavior:
- Analyzer should detect the circular dependency: ec1_circular_a -> ec1_circular_b -> ec1_circular_a
- Analyzer should emit a warning about the circular import
- Analyzer should NOT crash during graph construction
"""

from tests.functional.test_codebase.edge_cases.relationship_detection import ec1_circular_b


class ServiceA:
    """A service that depends on ServiceB."""

    def __init__(self) -> None:
        self.name = "ServiceA"

    def call_service_b(self) -> str:
        """Call ServiceB and return result."""
        service_b = ec1_circular_b.ServiceB()
        return f"{self.name} called {service_b.get_name()}"

    def get_name(self) -> str:
        """Get the service name."""
        return self.name


def get_service_a() -> ServiceA:
    """Factory function to get ServiceA instance."""
    return ServiceA()
