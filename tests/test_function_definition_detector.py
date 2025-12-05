# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for FunctionDefinitionDetector.

This module tests function and method definition detection according to
TDD Section 3.5.1 specifications and Issue #140 requirements.

Test Coverage:
- Simple function definitions
- Async function definitions
- Functions with decorators
- Functions with docstrings
- Functions with various argument patterns
- Methods inside classes
- Detector priority and name
- Detector reuse across files
"""

import ast

from xfile_context.detectors import FunctionDefinitionDetector
from xfile_context.models import SymbolType


class TestFunctionDefinitionDetector:
    """Tests for FunctionDefinitionDetector."""

    def test_simple_function_definition(self, tmp_path):
        """Test detection of a simple function definition."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def foo():
    pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        # Should detect one function definition
        assert len(definitions) == 1

        defn = definitions[0]
        assert defn.name == "foo"
        assert defn.symbol_type == SymbolType.FUNCTION
        assert defn.line_start == 2
        assert defn.signature == "def foo()"
        assert defn.decorators is None
        assert defn.docstring is None
        assert defn.parent_class is None

    def test_function_with_arguments(self, tmp_path):
        """Test detection of function with various argument types."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def bar(a, b, *args, keyword=None, **kwargs):
    pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        assert len(definitions) == 1
        defn = definitions[0]
        assert defn.name == "bar"
        assert defn.signature == "def bar(a, b, *args, keyword, **kwargs)"

    def test_async_function_definition(self, tmp_path):
        """Test detection of async function definition."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
async def async_handler():
    pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        assert len(definitions) == 1
        defn = definitions[0]
        assert defn.name == "async_handler"
        assert defn.symbol_type == SymbolType.FUNCTION
        assert defn.signature == "async def async_handler()"

    def test_function_with_decorators(self, tmp_path):
        """Test detection of decorated function."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
@staticmethod
@custom_decorator
def decorated_func():
    pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        assert len(definitions) == 1
        defn = definitions[0]
        assert defn.name == "decorated_func"
        assert defn.decorators == ["staticmethod", "custom_decorator"]

    def test_function_with_module_qualified_decorator(self, tmp_path):
        """Test detection of function with module.decorator style."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
@pytest.mark.parametrize("x", [1, 2])
def test_something(x):
    pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        assert len(definitions) == 1
        defn = definitions[0]
        assert defn.name == "test_something"
        assert defn.decorators == ["pytest.mark.parametrize"]

    def test_function_with_docstring(self, tmp_path):
        """Test extraction of function docstring."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''
def documented():
    """This is the docstring.

    More details here.
    """
    pass
'''
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        assert len(definitions) == 1
        defn = definitions[0]
        assert defn.docstring == "This is the docstring."

    def test_method_inside_class(self, tmp_path):
        """Test detection of method inside a class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class MyClass:
    def my_method(self):
        pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        assert len(definitions) == 1
        defn = definitions[0]
        assert defn.name == "my_method"
        assert defn.parent_class == "MyClass"
        assert defn.signature == "def my_method(self)"

    def test_multiple_functions(self, tmp_path):
        """Test detection of multiple functions in one file."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def first():
    pass

def second():
    pass

async def third():
    pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        assert len(definitions) == 3
        names = {d.name for d in definitions}
        assert names == {"first", "second", "third"}

    def test_line_number_tracking(self, tmp_path):
        """Test that line numbers are correctly tracked."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def foo():  # Line 2
    pass    # Line 3
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        assert len(definitions) == 1
        defn = definitions[0]
        assert defn.line_start == 2
        assert defn.line_end == 3

    def test_detect_returns_empty_list(self, tmp_path):
        """Test that detect() returns empty list (definitions only via extract_symbols)."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def foo():
    pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # detect() should return empty - this detector only produces definitions
        assert len(relationships) == 0

    def test_detector_priority(self):
        """Test that FunctionDefinitionDetector has correct priority."""
        detector = FunctionDefinitionDetector()
        assert detector.priority() == 50  # Core detector priority

    def test_detector_name(self):
        """Test that FunctionDefinitionDetector has correct name."""
        detector = FunctionDefinitionDetector()
        assert detector.name() == "FunctionDefinitionDetector"

    def test_supports_symbol_extraction(self):
        """Test that FunctionDefinitionDetector supports symbol extraction."""
        detector = FunctionDefinitionDetector()
        assert detector.supports_symbol_extraction() is True

    def test_detector_reuse_across_files(self, tmp_path):
        """Test that detector instance can be safely reused across multiple files.

        This tests the production scenario where DetectorRegistry registers a single
        detector instance and reuses it for all files in the project.
        """
        # Create file1 with a function
        file1 = tmp_path / "file1.py"
        file1.write_text(
            """
def foo():
    pass
"""
        )

        # Create file2 with a different function
        file2 = tmp_path / "file2.py"
        file2.write_text(
            """
def bar():
    pass
"""
        )

        # Use same detector instance for both files (production pattern)
        detector = FunctionDefinitionDetector()

        # Analyze file1
        tree1 = ast.parse(file1.read_text())
        file1_defs = []
        for node in ast.walk(tree1):
            defs, refs = detector.extract_symbols(node, str(file1), tree1)
            file1_defs.extend(defs)

        assert len(file1_defs) == 1
        assert file1_defs[0].name == "foo"

        # Analyze file2 with SAME detector instance
        tree2 = ast.parse(file2.read_text())
        file2_defs = []
        for node in ast.walk(tree2):
            defs, refs = detector.extract_symbols(node, str(file2), tree2)
            file2_defs.extend(defs)

        assert len(file2_defs) == 1
        assert file2_defs[0].name == "bar"

    def test_nested_function(self, tmp_path):
        """Test detection of nested function definitions."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def outer():
    def inner():
        pass
    return inner
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        # Should detect both outer and inner functions
        assert len(definitions) == 2
        names = {d.name for d in definitions}
        assert names == {"outer", "inner"}

    def test_staticmethod_and_classmethod(self, tmp_path):
        """Test detection of static and class methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class MyClass:
    @staticmethod
    def static_method():
        pass

    @classmethod
    def class_method(cls):
        pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        assert len(definitions) == 2

        static = next(d for d in definitions if d.name == "static_method")
        assert static.decorators == ["staticmethod"]
        assert static.parent_class == "MyClass"

        classm = next(d for d in definitions if d.name == "class_method")
        assert classm.decorators == ["classmethod"]
        assert classm.parent_class == "MyClass"

    def test_property_method(self, tmp_path):
        """Test detection of property methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class MyClass:
    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, val):
        self._value = val
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        # Both property getter and setter should be detected
        assert len(definitions) == 2
        assert all(d.name == "value" for d in definitions)
        assert all(d.parent_class == "MyClass" for d in definitions)

    def test_lambda_not_detected(self, tmp_path):
        """Test that lambda expressions are not detected as function definitions."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
x = lambda a, b: a + b
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        definitions = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            definitions.extend(defs)

        # Lambdas should not be detected (they are anonymous)
        assert len(definitions) == 0

    def test_extract_symbols_returns_no_references(self, tmp_path):
        """Test that extract_symbols returns empty references list."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def foo():
    pass
"""
        )

        detector = FunctionDefinitionDetector()
        tree = ast.parse(test_file.read_text())

        all_refs = []
        for node in ast.walk(tree):
            defs, refs = detector.extract_symbols(node, str(test_file), tree)
            all_refs.extend(refs)

        # This detector produces only definitions, no references
        assert len(all_refs) == 0
