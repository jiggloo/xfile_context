# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Registry for relationship detector plugins.

This module implements the detector registry that manages detector plugins
with priority-based dispatch (DD-1: Modular detector plugin pattern).

See TDD Section 3.4.4 for detailed specifications.
"""

import logging
from typing import List

from .base import RelationshipDetector

logger = logging.getLogger(__name__)


class DetectorRegistry:
    """Registry for relationship detector plugins with priority-based dispatch.

    The registry maintains a list of detector plugins and dispatches AST nodes
    to them in priority order (highest priority first).

    Design Pattern (DD-1):
    - Detectors are registered with priority values
    - Higher priority detectors execute first
    - Registry maintains sorted order for efficient dispatch
    - New detectors can be added without modifying existing code

    Thread Safety:
    - NOT thread-safe: Designed for single-threaded use
    - Register all detectors during initialization before processing

    See TDD Section 3.4.4 for detailed specifications.
    """

    def __init__(self) -> None:
        """Initialize empty detector registry."""
        self._detectors: List[RelationshipDetector] = []
        self._sorted: bool = True  # Track if detectors list is sorted

    def register(self, detector: RelationshipDetector) -> None:
        """Register a detector plugin.

        Args:
            detector: Detector to register.

        Raises:
            TypeError: If detector is not a RelationshipDetector instance.
        """
        if not isinstance(detector, RelationshipDetector):
            raise TypeError(
                f"Detector must be a RelationshipDetector instance, got {type(detector)}"
            )

        self._detectors.append(detector)
        self._sorted = False  # Mark as needing re-sort

        logger.debug(f"Registered detector '{detector.name()}' with priority {detector.priority()}")

    def get_detectors(self) -> List[RelationshipDetector]:
        """Get all registered detectors in priority order.

        Detectors are sorted by priority (highest first) on first access
        after registration changes.

        Returns:
            List of detectors sorted by priority (highest first).
        """
        if not self._sorted:
            # Sort by priority (highest first), then by name for stability
            self._detectors.sort(key=lambda d: (-d.priority(), d.name()))
            self._sorted = True

        return self._detectors

    def clear(self) -> None:
        """Remove all registered detectors.

        Used for testing and reconfiguration.
        """
        self._detectors.clear()
        self._sorted = True

    def count(self) -> int:
        """Return number of registered detectors.

        Returns:
            Number of detectors in registry.
        """
        return len(self._detectors)
