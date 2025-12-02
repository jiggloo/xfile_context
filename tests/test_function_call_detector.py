# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for FunctionCallDetector.

This module tests function call detection and resolution according to
TDD Section 3.5.2.2 specifications.

Test Coverage:
- Simple direct function calls
- Module-qualified function calls
- Function resolution order (local, imported, built-in, unresolved)
- v0.1.0 limitations (no method chains, no nested attributes)
"""

import ast

from xfile_context.detectors import FunctionCallDetector
from xfile_context.models import RelationshipType


class TestFunctionCallDetector:
    """Tests for FunctionCallDetector."""

    def test_simple_direct_call(self, tmp_path):
        """Test detection of simple direct function calls: function_name()."""
        # Create test file with local function definition and call
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def helper():
    pass

def main():
    helper()  # Simple direct call
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one function call
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.relationship_type == RelationshipType.FUNCTION_CALL
        assert rel.target_symbol == "helper"
        assert rel.target_file == str(test_file)  # Resolves to local file
        assert rel.metadata["call_pattern"] == "simple"
        assert rel.metadata["function_name"] == "helper"

    def test_builtin_function_call(self, tmp_path):
        """Test detection of built-in function calls."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def main():
    print("hello")  # Built-in function
    len([1, 2, 3])  # Built-in function
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect two built-in calls
        assert len(relationships) == 2

        # Check print() call
        print_rel = [r for r in relationships if r.target_symbol == "print"][0]
        assert print_rel.target_file == "<builtin:print>"
        assert print_rel.metadata["call_pattern"] == "simple"

        # Check len() call
        len_rel = [r for r in relationships if r.target_symbol == "len"][0]
        assert len_rel.target_file == "<builtin:len>"

    def test_unresolved_function_call(self, tmp_path):
        """Test detection of unresolved function calls."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def main():
    unknown_function()  # Not defined, not imported, not built-in
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one unresolved call
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.target_symbol == "unknown_function"
        assert rel.target_file == "<unresolved:unknown_function>"
        assert rel.metadata["call_pattern"] == "simple"

    def test_imported_function_call(self, tmp_path):
        """Test resolution of imported function calls."""
        # Create helper module
        helper_file = tmp_path / "helper.py"
        helper_file.write_text(
            """
def utility():
    pass
"""
        )

        # Create main file that imports and calls
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
from helper import utility

def main():
    utility()  # Imported function call
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one function call
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.target_symbol == "utility"
        # Should resolve to helper.py (since it exists in same directory)
        assert rel.target_file == str(helper_file)
        assert rel.metadata["call_pattern"] == "simple"

    def test_aliased_import_function_call(self, tmp_path):
        """Test resolution of function calls using aliased imports."""
        # Create helper module
        helper_file = tmp_path / "helper.py"
        helper_file.write_text(
            """
def original_name():
    pass
"""
        )

        # Create main file with aliased import
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
from helper import original_name as alias

def main():
    alias()  # Call using alias
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one function call
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.target_symbol == "alias"
        # Should resolve to helper.py via alias tracking
        assert rel.target_file == str(helper_file)

    def test_module_qualified_call(self, tmp_path):
        """Test detection of module-qualified calls: module.function()."""
        # Create helper module
        helper_file = tmp_path / "helper.py"
        helper_file.write_text(
            """
def utility():
    pass
"""
        )

        # Create main file that imports module and calls function
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
import helper

def main():
    helper.utility()  # Module-qualified call
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one function call
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.target_symbol == "helper.utility"
        assert rel.target_file == str(helper_file)
        assert rel.metadata["call_pattern"] == "module_qualified"
        assert rel.metadata["module_name"] == "helper"
        assert rel.metadata["function_name"] == "utility"

    def test_module_qualified_call_stdlib(self, tmp_path):
        """Test module-qualified calls to stdlib modules."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
import os

def main():
    os.getcwd()  # Stdlib module call
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one function call
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.target_symbol == "os.getcwd"
        assert rel.target_file == "<stdlib:os.getcwd>"
        assert rel.metadata["call_pattern"] == "module_qualified"

    def test_local_function_shadows_import(self, tmp_path):
        """Test that local function definition shadows imported function."""
        # Create helper module
        helper_file = tmp_path / "helper.py"
        helper_file.write_text(
            """
def utility():
    pass
"""
        )

        # Create main file where local definition shadows import
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
from helper import utility

def utility():  # Local definition shadows import
    pass

def main():
    utility()  # Should resolve to local definition
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one function call
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.target_symbol == "utility"
        # Should resolve to local file (not helper.py)
        assert rel.target_file == str(test_file)

    def test_method_chains_not_detected(self, tmp_path):
        """Test that method chains are NOT detected in v0.1.0."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def main():
    obj.method().another_method()  # Method chain - should NOT detect
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should NOT detect any function calls (method chains deferred)
        assert len(relationships) == 0

    def test_nested_attributes_not_detected(self, tmp_path):
        """Test that nested attributes are NOT detected in v0.1.0."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
import module

def main():
    module.submodule.function()  # Nested attribute - should NOT detect
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should NOT detect (nested attributes deferred to v0.1.2)
        assert len(relationships) == 0

    def test_multiple_calls_in_file(self, tmp_path):
        """Test detection of multiple function calls in same file."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def helper1():
    pass

def helper2():
    pass

def main():
    helper1()  # Call 1
    helper2()  # Call 2
    print("test")  # Call 3 (built-in)
    unknown()  # Call 4 (unresolved)
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect 4 function calls
        assert len(relationships) == 4

        # Check each call
        symbols = [r.target_symbol for r in relationships]
        assert "helper1" in symbols
        assert "helper2" in symbols
        assert "print" in symbols
        assert "unknown" in symbols

    def test_function_call_in_class(self, tmp_path):
        """Test detection of function calls inside class methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def helper():
    pass

class MyClass:
    def method(self):
        helper()  # Call inside method
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one function call
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.target_symbol == "helper"
        assert rel.source_symbol == "method"  # Context: inside method

    def test_detector_priority(self):
        """Test that FunctionCallDetector has correct priority."""
        detector = FunctionCallDetector()
        assert detector.priority() == 50  # Core detector priority

    def test_detector_name(self):
        """Test that FunctionCallDetector has correct name."""
        detector = FunctionCallDetector()
        assert detector.name() == "FunctionCallDetector"

    def test_relative_import_function_call(self, tmp_path):
        """Test resolution of function calls from relative imports."""
        # Create package structure
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")

        # Create helper module in package
        helper_file = pkg_dir / "helper.py"
        helper_file.write_text(
            """
def utility():
    pass
"""
        )

        # Create main file in package with relative import
        test_file = pkg_dir / "main.py"
        test_file.write_text(
            """
from .helper import utility

def main():
    utility()  # Relative import function call
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one function call
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.target_symbol == "utility"
        # Should resolve to helper.py in same package
        assert rel.target_file == str(helper_file)

    def test_line_number_tracking(self, tmp_path):
        """Test that line numbers are correctly tracked."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def helper():
    pass

def main():
    helper()  # Line 6
    print("test")  # Line 7
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Check line numbers
        helper_rel = [r for r in relationships if r.target_symbol == "helper"][0]
        assert helper_rel.line_number == 6

        print_rel = [r for r in relationships if r.target_symbol == "print"][0]
        assert print_rel.line_number == 7

    def test_wildcard_import_unresolved(self, tmp_path):
        """Test that function calls from wildcard imports are unresolved."""
        # Create helper module
        helper_file = tmp_path / "helper.py"
        helper_file.write_text(
            """
def utility():
    pass
"""
        )

        # Create main file with wildcard import
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
from helper import *

def main():
    utility()  # From wildcard import - cannot track
"""
        )

        detector = FunctionCallDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # Should detect one function call, but marked as unresolved
        # (wildcard imports don't track specific names)
        assert len(relationships) == 1

        rel = relationships[0]
        assert rel.target_symbol == "utility"
        # Cannot resolve from wildcard import in v0.1.0
        assert rel.target_file == "<unresolved:utility>"
