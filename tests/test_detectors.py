# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for detector base interface and registry."""

import ast

import pytest

from xfile_context.detectors import DetectorRegistry, RelationshipDetector


class MockDetector(RelationshipDetector):
    """Mock detector for testing."""

    def __init__(self, name: str, priority: int):
        self._name = name
        self._priority = priority
        self.detect_called = False

    def detect(self, node, filepath, module_ast):
        self.detect_called = True
        return []

    def priority(self):
        return self._priority

    def name(self):
        return self._name


class TestDetectorRegistry:
    """Tests for DetectorRegistry."""

    def test_empty_registry(self):
        """Test empty registry has no detectors."""
        registry = DetectorRegistry()
        assert registry.count() == 0
        assert registry.get_detectors() == []

    def test_register_detector(self):
        """Test registering a detector."""
        registry = DetectorRegistry()
        detector = MockDetector("TestDetector", 50)

        registry.register(detector)

        assert registry.count() == 1
        assert len(registry.get_detectors()) == 1
        assert registry.get_detectors()[0] == detector

    def test_register_multiple_detectors(self):
        """Test registering multiple detectors."""
        registry = DetectorRegistry()
        detector1 = MockDetector("Detector1", 50)
        detector2 = MockDetector("Detector2", 100)
        detector3 = MockDetector("Detector3", 25)

        registry.register(detector1)
        registry.register(detector2)
        registry.register(detector3)

        assert registry.count() == 3

    def test_priority_ordering(self):
        """Test detectors are returned in priority order (highest first)."""
        registry = DetectorRegistry()
        detector_low = MockDetector("LowPriority", 10)
        detector_high = MockDetector("HighPriority", 100)
        detector_med = MockDetector("MedPriority", 50)

        # Register in random order
        registry.register(detector_med)
        registry.register(detector_low)
        registry.register(detector_high)

        detectors = registry.get_detectors()

        # Should be ordered: high (100), med (50), low (10)
        assert detectors[0] == detector_high
        assert detectors[1] == detector_med
        assert detectors[2] == detector_low

    def test_priority_tie_broken_by_name(self):
        """Test that detectors with same priority are ordered by name."""
        registry = DetectorRegistry()
        detector_a = MockDetector("ADetector", 50)
        detector_b = MockDetector("BDetector", 50)
        detector_c = MockDetector("CDetector", 50)

        registry.register(detector_b)
        registry.register(detector_c)
        registry.register(detector_a)

        detectors = registry.get_detectors()

        # Should be alphabetically ordered when priority is the same
        assert detectors[0].name() == "ADetector"
        assert detectors[1].name() == "BDetector"
        assert detectors[2].name() == "CDetector"

    def test_clear_registry(self):
        """Test clearing all detectors from registry."""
        registry = DetectorRegistry()
        registry.register(MockDetector("Detector1", 50))
        registry.register(MockDetector("Detector2", 100))

        assert registry.count() == 2

        registry.clear()

        assert registry.count() == 0
        assert registry.get_detectors() == []

    def test_register_non_detector_raises_error(self):
        """Test registering non-detector raises TypeError."""
        registry = DetectorRegistry()

        with pytest.raises(TypeError, match="must be a RelationshipDetector"):
            registry.register("not a detector")  # type: ignore

        with pytest.raises(TypeError, match="must be a RelationshipDetector"):
            registry.register(42)  # type: ignore


class TestRelationshipDetector:
    """Tests for RelationshipDetector abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that RelationshipDetector cannot be instantiated directly."""
        with pytest.raises(TypeError):
            RelationshipDetector()  # type: ignore

    def test_mock_detector_implementation(self):
        """Test that mock detector properly implements interface."""
        detector = MockDetector("TestDetector", 50)

        assert detector.name() == "TestDetector"
        assert detector.priority() == 50

        # Test detect method
        node = ast.parse("x = 1")
        result = detector.detect(node, "/test/file.py", node)

        assert detector.detect_called is True
        assert result == []  # Mock returns empty list
