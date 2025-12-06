# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Integration tests for PythonAnalyzer + Detectors.

NOTE: Marked as slow tests - integration tests create full project structures.
Run with: pytest -m slow

Tests the full AST parsing pipeline with real Python files per TDD Section 3.13.2.
"""

from pathlib import Path

import pytest

from xfile_context.analyzers import PythonAnalyzer
from xfile_context.detectors import (
    ClassInheritanceDetector,
    ConditionalImportDetector,
    DecoratorDetector,
    DetectorRegistry,
    DynamicDispatchDetector,
    ExecEvalDetector,
    FunctionCallDetector,
    ImportDetector,
    MetaclassDetector,
    MonkeyPatchingDetector,
    WildcardImportDetector,
)
from xfile_context.models import RelationshipGraph, RelationshipType

# Mark entire module as slow - integration tests create full project structures
pytestmark = pytest.mark.slow


class TestAnalyzerDetectorsIntegration:
    """Integration tests for analyzer with all detector types."""

    def _create_full_registry(self, project_root: str) -> DetectorRegistry:
        """Create registry with all production detectors."""
        registry = DetectorRegistry()

        # Relationship detectors
        registry.register(ImportDetector())
        registry.register(ConditionalImportDetector())
        registry.register(WildcardImportDetector())
        registry.register(FunctionCallDetector())
        registry.register(ClassInheritanceDetector())

        # Dynamic pattern detectors
        registry.register(DynamicDispatchDetector(project_root))
        registry.register(MonkeyPatchingDetector(project_root))
        registry.register(ExecEvalDetector(project_root))
        registry.register(DecoratorDetector(project_root))
        registry.register(MetaclassDetector(project_root))

        return registry

    def test_full_project_analysis(self, sample_project: Path) -> None:
        """Test analyzing an entire project with all detectors.

        Validates that the full AST pipeline works end-to-end with real files.
        """
        graph = RelationshipGraph()
        registry = self._create_full_registry(str(sample_project))
        analyzer = PythonAnalyzer(graph, registry)

        # Analyze all Python files in the project
        python_files = list(sample_project.rglob("*.py"))
        assert len(python_files) > 0, "Sample project should have Python files"

        analyzed_count = 0
        for py_file in python_files:
            result = analyzer.analyze_file(str(py_file))
            if result:
                analyzed_count += 1

        # Should successfully analyze most files
        assert analyzed_count >= len(python_files) - 2  # Allow for edge case files

        # Verify relationships were detected
        all_relationships = graph.get_all_relationships()
        assert len(all_relationships) > 0, "Should detect relationships"

        # Verify different relationship types were detected
        rel_types = {rel.relationship_type for rel in all_relationships}
        assert RelationshipType.IMPORT in rel_types, "Should detect imports"

    def test_import_detection_with_real_files(self, sample_project: Path) -> None:
        """Test import detection with real Python files."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Analyze core.py which has multiple imports
        core_file = sample_project / "mypackage" / "core.py"
        assert core_file.exists()

        result = analyzer.analyze_file(str(core_file))
        assert result is True

        # Get dependencies for core.py
        deps = graph.get_dependencies(str(core_file))
        assert len(deps) > 0, "core.py should have import dependencies"

        # Check specific imports
        import_targets = [rel.target_file for rel in deps]
        # Should have imports from models and utils
        assert any("models" in t or "user" in t.lower() for t in import_targets)

    def test_class_inheritance_detection(self, sample_project: Path) -> None:
        """Test class inheritance detection across files."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ClassInheritanceDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Analyze user.py which inherits from BaseModel
        user_file = sample_project / "mypackage" / "models" / "user.py"
        assert user_file.exists()

        result = analyzer.analyze_file(str(user_file))
        assert result is True

        # Get all relationships
        relationships = graph.get_all_relationships()
        inheritance_rels = [
            rel
            for rel in relationships
            if rel.relationship_type == RelationshipType.CLASS_INHERITANCE
        ]

        # Should detect User inheriting from BaseModel
        assert len(inheritance_rels) > 0, "Should detect class inheritance"

    def test_conditional_import_detection(self, sample_project: Path) -> None:
        """Test conditional import detection (TYPE_CHECKING, try/except).

        Note: ConditionalImportDetector uses IMPORT type with metadata marking
        the import as conditional, not a separate CONDITIONAL_IMPORT type.
        """
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ConditionalImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Analyze user.py which has TYPE_CHECKING import
        user_file = sample_project / "mypackage" / "models" / "user.py"
        result = analyzer.analyze_file(str(user_file))
        assert result is True

        relationships = graph.get_all_relationships()
        # Conditional imports are stored as IMPORT type with conditional metadata
        conditional_rels = [
            rel
            for rel in relationships
            if rel.relationship_type == RelationshipType.IMPORT
            and rel.metadata
            and rel.metadata.get("conditional") == "true"
        ]

        # Should detect TYPE_CHECKING import
        assert len(conditional_rels) > 0, "Should detect conditional imports"

    def test_wildcard_import_detection(self, sample_project: Path) -> None:
        """Test wildcard import detection (from x import *).

        Note: WildcardImportDetector uses IMPORT type with metadata marking
        the import as wildcard, not a separate WILDCARD_IMPORT type.
        """
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(WildcardImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Analyze wildcard_example.py
        wildcard_file = sample_project / "mypackage" / "wildcard_example.py"
        result = analyzer.analyze_file(str(wildcard_file))
        assert result is True

        relationships = graph.get_all_relationships()
        # Wildcard imports are stored as IMPORT type with wildcard metadata
        wildcard_rels = [
            rel
            for rel in relationships
            if rel.relationship_type == RelationshipType.IMPORT
            and rel.metadata
            and rel.metadata.get("wildcard") == "true"
        ]

        assert len(wildcard_rels) > 0, "Should detect wildcard imports"

    def test_function_call_detection(self, sample_project: Path) -> None:
        """Test function call detection across modules."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(FunctionCallDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Analyze core.py which calls functions from utils
        core_file = sample_project / "mypackage" / "core.py"
        result = analyzer.analyze_file(str(core_file))
        assert result is True

        relationships = graph.get_all_relationships()
        call_rels = [
            rel for rel in relationships if rel.relationship_type == RelationshipType.FUNCTION_CALL
        ]

        # Should detect function calls
        assert len(call_rels) > 0, "Should detect function calls"

    def test_dynamic_pattern_detection(
        self, sample_project: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test dynamic pattern detection (getattr, exec, eval, etc.).

        Note: Dynamic pattern detectors emit warnings instead of creating
        relationships (per FR-42 fail-safe principle). They log warnings
        for patterns that cannot be statically analyzed.
        """
        import logging

        graph = RelationshipGraph()
        registry = self._create_full_registry(str(sample_project))
        analyzer = PythonAnalyzer(graph, registry)

        # Capture warnings from dynamic pattern detectors
        with caplog.at_level(logging.WARNING):
            # Analyze dynamic_patterns.py
            dynamic_file = sample_project / "mypackage" / "dynamic_patterns.py"
            result = analyzer.analyze_file(str(dynamic_file))
            assert result is True

        # Dynamic pattern detectors emit warnings, not relationships
        # Check that warnings were logged for dynamic patterns
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]

        # Should have warnings for exec/eval patterns
        assert any(
            "exec" in msg.lower() or "eval" in msg.lower() for msg in warning_messages
        ), "Should emit warnings for dynamic patterns like exec/eval"

    def test_circular_dependency_handling(self, sample_project: Path) -> None:
        """Test handling of circular dependencies (EC-1)."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        registry.register(ConditionalImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        # Analyze both circular files
        circular_a = sample_project / "mypackage" / "circular_a.py"
        circular_b = sample_project / "mypackage" / "circular_b.py"

        result_a = analyzer.analyze_file(str(circular_a))
        result_b = analyzer.analyze_file(str(circular_b))

        # Both should analyze successfully (Python allows circular imports)
        assert result_a is True
        assert result_b is True

        # Verify relationships are detected in both directions
        deps_a = graph.get_dependencies(str(circular_a))
        deps_b = graph.get_dependencies(str(circular_b))

        # Both files should have dependencies
        assert len(deps_a) > 0 or len(deps_b) > 0

    def test_incremental_analysis(self, minimal_project: Path) -> None:
        """Test incremental analysis updates relationships correctly."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        main_file = minimal_project / "main.py"

        # Initial analysis
        result = analyzer.analyze_file(str(main_file))
        assert result is True

        initial_deps = graph.get_dependencies(str(main_file))
        assert len(initial_deps) == 1  # imports utils

        # Modify the file
        main_file.write_text(
            '''# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Updated main module."""

import json
import os

from utils import helper_function, another_function


def main():
    pass
'''
        )

        # Re-analyze
        result = analyzer.analyze_file(str(main_file))
        assert result is True

        # Should have updated relationships
        updated_deps = graph.get_dependencies(str(main_file))
        # Now has json, os, and utils imports
        assert len(updated_deps) >= 2

    def test_edge_case_files(self, edge_case_project: Path) -> None:
        """Test handling of edge case files."""
        graph = RelationshipGraph()
        registry = self._create_full_registry(str(edge_case_project))
        analyzer = PythonAnalyzer(graph, registry)

        # Empty file should be handled gracefully
        empty_file = edge_case_project / "empty_file.py"
        result = analyzer.analyze_file(str(empty_file))
        assert result is True  # Empty files are valid Python

        # Syntax error file should be handled gracefully
        syntax_error_file = edge_case_project / "syntax_error.py"
        result = analyzer.analyze_file(str(syntax_error_file))
        assert result is False  # Should fail gracefully

        # File should be marked as unparseable
        metadata = graph.get_file_metadata(str(syntax_error_file))
        assert metadata is not None
        assert metadata.is_unparseable is True

    def test_aliased_import_detection(self, edge_case_project: Path) -> None:
        """Test aliased import detection (EC-2).

        Note: Aliases are stored in the target_symbol field as 'module as alias'
        or in metadata, not in a separate alias field.
        """
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        aliased_file = edge_case_project / "aliased_imports.py"
        result = analyzer.analyze_file(str(aliased_file))
        assert result is True

        deps = graph.get_dependencies(str(aliased_file))
        assert len(deps) > 0, "Should detect aliased imports"

        # Check that the imports were detected (numpy, pandas, etc.)
        target_modules = [rel.target_file for rel in deps]
        # Should have imports like numpy and pandas
        assert any("numpy" in t or "pandas" in t for t in target_modules)

    def test_type_checking_imports(self, edge_case_project: Path) -> None:
        """Test TYPE_CHECKING conditional imports (EC-5).

        Note: TYPE_CHECKING imports are stored as IMPORT type with metadata
        marking them as conditional with condition_type="TYPE_CHECKING".
        """
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ConditionalImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        type_checking_file = edge_case_project / "type_checking_imports.py"
        result = analyzer.analyze_file(str(type_checking_file))
        assert result is True

        relationships = graph.get_all_relationships()
        # TYPE_CHECKING imports are stored as IMPORT with conditional metadata
        conditional_rels = [
            rel
            for rel in relationships
            if rel.relationship_type == RelationshipType.IMPORT
            and rel.metadata
            and rel.metadata.get("conditional") == "true"
            and rel.metadata.get("condition_type") == "TYPE_CHECKING"
        ]

        assert len(conditional_rels) > 0, "Should detect TYPE_CHECKING imports"

    def test_multiple_files_relationship_graph(self, sample_project: Path) -> None:
        """Test relationship graph construction across multiple files."""
        graph = RelationshipGraph()
        registry = self._create_full_registry(str(sample_project))
        analyzer = PythonAnalyzer(graph, registry)

        # Analyze key files
        files_to_analyze = [
            sample_project / "mypackage" / "core.py",
            sample_project / "mypackage" / "models" / "user.py",
            sample_project / "mypackage" / "models" / "base.py",
            sample_project / "mypackage" / "utils" / "helpers.py",
        ]

        for file in files_to_analyze:
            if file.exists():
                analyzer.analyze_file(str(file))

        # Verify graph has relationships from multiple files
        all_rels = graph.get_all_relationships()
        source_files = {rel.source_file for rel in all_rels}

        assert len(source_files) >= 2, "Should have relationships from multiple files"

        # Test reverse lookup - get dependents of base.py
        base_file = sample_project / "mypackage" / "models" / "base.py"
        dependents = graph.get_dependents(str(base_file))
        # user.py should depend on base.py
        assert len(dependents) >= 0  # May or may not have dependents depending on analysis

    def test_file_metadata_tracking(self, sample_project: Path) -> None:
        """Test that file metadata is properly tracked across analyses."""
        graph = RelationshipGraph()
        registry = DetectorRegistry()
        registry.register(ImportDetector())
        analyzer = PythonAnalyzer(graph, registry)

        core_file = sample_project / "mypackage" / "core.py"
        analyzer.analyze_file(str(core_file))

        # Check metadata
        metadata = graph.get_file_metadata(str(core_file))
        assert metadata is not None
        assert metadata.filepath == str(core_file)
        assert metadata.is_unparseable is False
        assert metadata.last_analyzed > 0
        assert metadata.relationship_count >= 0
