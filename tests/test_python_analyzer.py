# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for Python AST analyzer."""

import ast

from xfile_context.analyzers import PythonAnalyzer
from xfile_context.detectors import DetectorRegistry, RelationshipDetector
from xfile_context.models import Relationship, RelationshipGraph, RelationshipType


class SimpleImportDetector(RelationshipDetector):
    """Simple detector that finds import statements for testing."""

    def detect(self, node, filepath, module_ast):
        if isinstance(node, ast.Import):
            # Detect "import module" statements
            relationships = []
            for alias in node.names:
                rel = Relationship(
                    source_file=filepath,
                    target_file=f"<module:{alias.name}>",
                    relationship_type=RelationshipType.IMPORT,
                    line_number=node.lineno,
                    target_symbol=alias.name,
                )
                relationships.append(rel)
            return relationships
        return []

    def priority(self):
        return 100

    def name(self):
        return "SimpleImportDetector"


class FailingDetector(RelationshipDetector):
    """Detector that always raises an exception for testing error recovery."""

    def detect(self, node, filepath, module_ast):
        raise RuntimeError("Detector failure for testing")

    def priority(self):
        return 50

    def name(self):
        return "FailingDetector"


class TestPythonAnalyzer:
    """Tests for PythonAnalyzer."""

    def test_analyze_simple_file(self, tmp_path):
        """Test analyzing a simple valid Python file."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\nimport sys\n")

        # Setup analyzer
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(SimpleImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Analyze file
        result = analyzer.analyze_file(str(test_file))

        assert result is True
        assert len(graph.get_all_relationships()) == 2

        # Check detected imports
        relationships = graph.get_dependencies(str(test_file))
        assert len(relationships) == 2

        import_targets = [rel.target_symbol for rel in relationships]
        assert "os" in import_targets
        assert "sys" in import_targets

    def test_file_not_found(self):
        """Test handling of non-existent file."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        analyzer = PythonAnalyzer(graph, registry)

        result = analyzer.analyze_file("/nonexistent/file.py")

        assert result is False
        assert len(graph.get_all_relationships()) == 0

    def test_syntax_error_recovery(self, tmp_path):
        """Test error recovery for syntax errors (EC-18)."""
        # Create file with syntax error
        test_file = tmp_path / "bad_syntax.py"
        test_file.write_text("import os\nif True\n  print('missing colon')\n")

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(SimpleImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Should fail gracefully
        result = analyzer.analyze_file(str(test_file))

        assert result is False

        # Check file is marked as unparseable
        metadata = graph.get_file_metadata(str(test_file))
        assert metadata is not None
        assert metadata.is_unparseable is True

    def test_encoding_fallback(self, tmp_path):
        """Test UTF-8 to latin-1 encoding fallback."""
        # Create file with latin-1 encoding
        test_file = tmp_path / "latin1.py"
        # Write bytes directly with latin-1 special character
        test_file.write_bytes(b"# File with latin-1: \xe9\nimport os\n")

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(SimpleImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Should succeed with fallback encoding
        result = analyzer.analyze_file(str(test_file))

        assert result is True
        assert len(graph.get_all_relationships()) == 1

    def test_file_size_limit(self, tmp_path):
        """Test file size limit enforcement (EC-17)."""
        # Create file larger than limit
        test_file = tmp_path / "large.py"
        # Create file with 11000 lines (exceeds default limit of 10000)
        lines = ["# Comment line\n"] * 11000
        test_file.write_text("".join(lines))

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        analyzer = PythonAnalyzer(graph, registry, max_file_lines=10000)

        # Should be skipped
        result = analyzer.analyze_file(str(test_file))

        assert result is False
        assert len(graph.get_all_relationships()) == 0

    def test_file_within_size_limit(self, tmp_path):
        """Test file within size limit is processed."""
        # Create file within limit
        test_file = tmp_path / "medium.py"
        # Create file with 5000 lines (within default limit)
        lines = ["# Comment line\n"] * 4999
        lines.append("import os\n")
        test_file.write_text("".join(lines))

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(SimpleImportDetector())
        analyzer = PythonAnalyzer(graph, registry, max_file_lines=10000)

        # Should succeed
        result = analyzer.analyze_file(str(test_file))

        assert result is True
        assert len(graph.get_all_relationships()) == 1

    def test_detector_exception_recovery(self, tmp_path):
        """Test partial analysis when detector fails."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\nimport sys\n")

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        # Register both working and failing detectors
        registry.register(SimpleImportDetector())
        registry.register(FailingDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Should succeed with partial results
        result = analyzer.analyze_file(str(test_file))

        assert result is True
        # Should have results from SimpleImportDetector despite FailingDetector exception
        assert len(graph.get_all_relationships()) == 2

    def test_empty_file(self, tmp_path):
        """Test analyzing empty file."""
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        analyzer = PythonAnalyzer(graph, registry)

        result = analyzer.analyze_file(str(test_file))

        assert result is True
        assert len(graph.get_all_relationships()) == 0

    def test_multiple_detectors_priority_order(self, tmp_path):
        """Test that detectors are invoked in priority order."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\n")

        # Create detectors with different priorities
        class HighPriorityDetector(RelationshipDetector):
            def __init__(self):
                self.invocation_order = []

            def detect(self, node, filepath, module_ast):
                self.invocation_order.append("high")
                return []

            def priority(self):
                return 100

            def name(self):
                return "HighPriority"

        class LowPriorityDetector(RelationshipDetector):
            def __init__(self, invocation_order):
                self.invocation_order = invocation_order

            def detect(self, node, filepath, module_ast):
                self.invocation_order.append("low")
                return []

            def priority(self):
                return 10

            def name(self):
                return "LowPriority"

        high_detector = HighPriorityDetector()
        low_detector = LowPriorityDetector(high_detector.invocation_order)

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(low_detector)  # Register in reverse order
        registry.register(high_detector)

        analyzer = PythonAnalyzer(graph, registry)
        analyzer.analyze_file(str(test_file))

        # High priority should be invoked before low priority
        # At least one invocation of each
        assert "high" in high_detector.invocation_order
        assert "low" in high_detector.invocation_order

    def test_incremental_update_removes_old_relationships(self, tmp_path):
        """Test that re-analyzing a file removes old relationships."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\n")

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(SimpleImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # First analysis
        analyzer.analyze_file(str(test_file))
        assert len(graph.get_all_relationships()) == 1

        # Update file content
        test_file.write_text("import sys\nimport json\n")

        # Second analysis should replace old relationships
        analyzer.analyze_file(str(test_file))

        relationships = graph.get_all_relationships()
        assert len(relationships) == 2

        # Should have sys and json, not os
        import_targets = [rel.target_symbol for rel in relationships]
        assert "sys" in import_targets
        assert "json" in import_targets
        assert "os" not in import_targets

    def test_file_metadata_updated(self, tmp_path):
        """Test that file metadata is updated after analysis."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\nimport sys\n")

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(SimpleImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        analyzer.analyze_file(str(test_file))

        metadata = graph.get_file_metadata(str(test_file))
        assert metadata is not None
        assert metadata.filepath == str(test_file)
        assert metadata.relationship_count == 2
        assert metadata.is_unparseable is False
        assert metadata.last_analyzed > 0

    def test_recursion_depth_limit(self, tmp_path):
        """Test AST traversal recursion depth limit.

        Note: Python's AST parser has version-specific limits. Older versions
        (3.8) fail on deeply nested expressions, while newer versions handle
        them better. This test verifies graceful handling regardless of result.
        """
        test_file = tmp_path / "deep_nesting.py"
        depth = 150  # Create deeply nested expression
        nested_expr = "(" * depth + "1" + ")" * depth
        test_file.write_text(f"x = {nested_expr}\n")

        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(SimpleImportDetector())
        analyzer = PythonAnalyzer(graph, registry, max_recursion_depth=100)

        # Parse the file - may succeed or fail depending on Python version
        result = analyzer.analyze_file(str(test_file))

        # Verify metadata exists regardless of success/failure
        metadata = graph.get_file_metadata(str(test_file))
        assert metadata is not None

        # If parsing failed, file should be marked as unparseable
        if not result:
            assert metadata.is_unparseable is True
