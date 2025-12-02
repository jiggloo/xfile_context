# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for dynamic pattern detectors.

This module tests the detection of dynamic Python patterns that cannot be
statically analyzed, according to TDD Section 3.5.4 and Section 3.9.1.

Test Coverage:
- DynamicDispatchDetector: getattr() patterns (EC-6, FR-33, T-6.2)
- MonkeyPatchingDetector: attribute reassignment (EC-7, FR-34, T-6.3)
- ExecEvalDetector: exec()/eval() calls (EC-9, FR-35, T-6.4)
- DecoratorDetector: decorator patterns (EC-8, FR-36, T-6.5)
- MetaclassDetector: metaclass patterns (EC-10, FR-37, T-6.6)
- Test vs source module distinction (DD-3)
- FR-42: No incorrect relationships added (fail-safe)
"""

import ast

import pytest

from xfile_context.detectors import (
    DecoratorDetector,
    DynamicDispatchDetector,
    DynamicPatternType,
    ExecEvalDetector,
    MetaclassDetector,
    MonkeyPatchingDetector,
    WarningSeverity,
)


class TestDynamicDispatchDetector:
    """Tests for DynamicDispatchDetector (EC-6, FR-33, T-6.2)."""

    def test_dynamic_getattr_with_variable(self, tmp_path):
        """Test detection of getattr() with variable second argument."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
obj = SomeClass()
method_name = get_method_name()
result = getattr(obj, method_name)()  # Dynamic dispatch
"""
        )

        detector = DynamicDispatchDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # FR-42: Should NOT create any relationships
        assert len(relationships) == 0

        # Should have detected warning
        warnings = detector.get_warnings()
        assert len(warnings) >= 1

        warning = warnings[0]
        assert warning.pattern_type == DynamicPatternType.DYNAMIC_DISPATCH
        assert warning.severity == WarningSeverity.WARNING
        assert "method_name" in warning.message
        assert warning.filepath == str(test_file)

    def test_static_getattr_no_warning(self, tmp_path):
        """Test that getattr() with string literal does NOT trigger warning."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
obj = SomeClass()
result = getattr(obj, "known_method")()  # Static - no warning
"""
        )

        detector = DynamicDispatchDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should NOT have warnings for static getattr
        warnings = detector.get_warnings()
        assert len(warnings) == 0

    def test_test_module_suppresses_warning(self, tmp_path):
        """Test that warnings are suppressed in test modules."""
        # Create a test file (matches test module pattern)
        test_file = tmp_path / "test_something.py"
        test_file.write_text(
            """
obj = Mock()
attr_name = "mocked_method"
getattr(obj, attr_name)()
"""
        )

        detector = DynamicDispatchDetector(project_root=str(tmp_path))
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should detect but mark as test module
        warnings = detector.get_warnings()
        assert len(warnings) >= 1
        assert warnings[0].is_test_module is True

    def test_getattr_without_call(self, tmp_path):
        """Test detection of getattr() used without immediate call."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
obj = SomeClass()
attr_name = "method"
method = getattr(obj, attr_name)  # Just getattr, not called
"""
        )

        detector = DynamicDispatchDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should still detect dynamic getattr
        warnings = detector.get_warnings()
        assert len(warnings) >= 1

    def test_detector_priority_and_name(self):
        """Test detector metadata."""
        detector = DynamicDispatchDetector()
        assert detector.priority() == 25
        assert detector.name() == "DynamicDispatchDetector"


class TestMonkeyPatchingDetector:
    """Tests for MonkeyPatchingDetector (EC-7, FR-34, T-6.3)."""

    def test_module_attribute_reassignment(self, tmp_path):
        """Test detection of module attribute reassignment."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
import os

os.getcwd = my_custom_getcwd  # Monkey patching
"""
        )

        detector = MonkeyPatchingDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # FR-42: Should NOT create any relationships
        assert len(relationships) == 0

        # Should have detected warning
        warnings = detector.get_warnings()
        assert len(warnings) == 1

        warning = warnings[0]
        assert warning.pattern_type == DynamicPatternType.MONKEY_PATCHING
        assert warning.severity == WarningSeverity.WARNING
        assert "os.getcwd" in warning.message

    def test_self_attr_no_warning(self, tmp_path):
        """Test that self.attr assignments do NOT trigger warning."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
class MyClass:
    def __init__(self):
        self.value = 42  # Normal instance attribute
"""
        )

        detector = MonkeyPatchingDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should NOT have warnings for self.attr
        warnings = detector.get_warnings()
        assert len(warnings) == 0

    def test_cls_attr_no_warning(self, tmp_path):
        """Test that cls.attr assignments do NOT trigger warning."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
class MyClass:
    @classmethod
    def set_value(cls):
        cls.class_value = 42  # Normal class attribute
"""
        )

        detector = MonkeyPatchingDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should NOT have warnings for cls.attr
        warnings = detector.get_warnings()
        assert len(warnings) == 0

    def test_test_module_suppresses_warning(self, tmp_path):
        """Test that warnings are suppressed in test modules (mocking)."""
        test_file = tmp_path / "test_mocking.py"
        test_file.write_text(
            """
import target_module

# Common in tests for mocking
target_module.function = mock_function
"""
        )

        detector = MonkeyPatchingDetector(project_root=str(tmp_path))
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should detect but mark as test module
        warnings = detector.get_warnings()
        assert len(warnings) >= 1
        assert warnings[0].is_test_module is True

    def test_nested_attribute_monkey_patch(self, tmp_path):
        """Test detection of nested attribute monkey patching."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
import package

package.submodule.function = replacement
"""
        )

        detector = MonkeyPatchingDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should detect nested monkey patching
        warnings = detector.get_warnings()
        assert len(warnings) == 1
        assert "package.submodule.function" in warnings[0].message

    def test_detector_priority_and_name(self):
        """Test detector metadata."""
        detector = MonkeyPatchingDetector()
        assert detector.priority() == 25
        assert detector.name() == "MonkeyPatchingDetector"


class TestExecEvalDetector:
    """Tests for ExecEvalDetector (EC-9, FR-35, T-6.4)."""

    def test_exec_detection(self, tmp_path):
        """Test detection of exec() calls."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
code = "print('hello')"
exec(code)  # Dynamic code execution
"""
        )

        detector = ExecEvalDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # FR-42: Should NOT create any relationships
        assert len(relationships) == 0

        # Should have detected warning
        warnings = detector.get_warnings()
        assert len(warnings) == 1

        warning = warnings[0]
        assert warning.pattern_type == DynamicPatternType.EXEC_EVAL
        assert warning.severity == WarningSeverity.WARNING
        assert "exec()" in warning.message
        assert warning.metadata is not None
        assert warning.metadata["function_name"] == "exec"

    def test_eval_detection(self, tmp_path):
        """Test detection of eval() calls."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
expr = "1 + 2"
result = eval(expr)  # Dynamic evaluation
"""
        )

        detector = ExecEvalDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should have detected warning
        warnings = detector.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].metadata["function_name"] == "eval"

    def test_exec_with_globals(self, tmp_path):
        """Test detection of exec() with globals argument."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
exec(code_string, globals(), locals())
"""
        )

        detector = ExecEvalDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should still detect
        warnings = detector.get_warnings()
        assert len(warnings) == 1

    def test_test_module_suppresses_warning(self, tmp_path):
        """Test that warnings are suppressed in test modules."""
        test_file = tmp_path / "test_exec.py"
        test_file.write_text(
            """
# Testing edge cases with exec
exec("assert True")
"""
        )

        detector = ExecEvalDetector(project_root=str(tmp_path))
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        warnings = detector.get_warnings()
        assert len(warnings) >= 1
        assert warnings[0].is_test_module is True

    def test_multiple_exec_eval_calls(self, tmp_path):
        """Test detection of multiple exec/eval calls."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
exec(code1)
eval(expr1)
exec(code2)
"""
        )

        detector = ExecEvalDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should detect all three
        warnings = detector.get_warnings()
        assert len(warnings) == 3

    def test_detector_priority_and_name(self):
        """Test detector metadata."""
        detector = ExecEvalDetector()
        assert detector.priority() == 25
        assert detector.name() == "ExecEvalDetector"


class TestDecoratorDetector:
    """Tests for DecoratorDetector (EC-8, FR-36, T-6.5)."""

    def test_custom_decorator_detection(self, tmp_path):
        """Test detection of custom decorators."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
@custom_decorator
def my_function():
    pass
"""
        )

        detector = DecoratorDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # FR-42: Should NOT create any relationships
        assert len(relationships) == 0

        # Should have detected warning
        warnings = detector.get_warnings()
        assert len(warnings) == 1

        warning = warnings[0]
        assert warning.pattern_type == DynamicPatternType.DECORATOR
        assert warning.severity == WarningSeverity.INFO
        assert "custom_decorator" in warning.message
        assert warning.metadata["decorator_name"] == "custom_decorator"
        assert warning.metadata["definition_type"] == "function"

    def test_builtin_decorator_no_warning(self, tmp_path):
        """Test that built-in decorators do NOT trigger warning."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
class MyClass:
    @staticmethod
    def static_method():
        pass

    @classmethod
    def class_method(cls):
        pass

    @property
    def prop(self):
        return self._value
"""
        )

        detector = DecoratorDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should NOT have warnings for built-in decorators
        warnings = detector.get_warnings()
        assert len(warnings) == 0

    def test_pytest_decorators_no_warning(self, tmp_path):
        """Test that pytest decorators do NOT trigger warning."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
import pytest

@pytest.mark.skip
def test_skipped():
    pass

@pytest.fixture
def my_fixture():
    return 42
"""
        )

        detector = DecoratorDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should NOT have warnings for pytest decorators
        warnings = detector.get_warnings()
        assert len(warnings) == 0

    def test_mock_patch_no_warning(self, tmp_path):
        """Test that mock.patch decorators do NOT trigger warning."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
from unittest import mock

@mock.patch("module.function")
def test_something():
    pass
"""
        )

        detector = DecoratorDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should NOT have warnings for mock decorators
        warnings = detector.get_warnings()
        assert len(warnings) == 0

    def test_class_decorator_detection(self, tmp_path):
        """Test detection of decorators on classes."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
@register
class MyPlugin:
    pass
"""
        )

        detector = DecoratorDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        warnings = detector.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].metadata["definition_type"] == "class"

    def test_decorator_with_args(self, tmp_path):
        """Test detection of decorators with arguments."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
@rate_limit(calls=10, period=60)
def api_endpoint():
    pass
"""
        )

        detector = DecoratorDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        warnings = detector.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].metadata["decorator_name"] == "rate_limit"

    def test_module_qualified_decorator(self, tmp_path):
        """Test detection of module-qualified decorators."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
@mymodule.custom_decorator
def my_function():
    pass
"""
        )

        detector = DecoratorDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        warnings = detector.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].metadata["decorator_name"] == "mymodule.custom_decorator"

    def test_test_module_suppresses_warning(self, tmp_path):
        """Test that warnings are suppressed in test modules."""
        test_file = tmp_path / "test_decorators.py"
        test_file.write_text(
            """
@custom_decorator
def test_something():
    pass
"""
        )

        detector = DecoratorDetector(project_root=str(tmp_path))
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        warnings = detector.get_warnings()
        assert len(warnings) >= 1
        assert warnings[0].is_test_module is True

    def test_detector_priority_and_name(self):
        """Test detector metadata."""
        detector = DecoratorDetector()
        assert detector.priority() == 25
        assert detector.name() == "DecoratorDetector"


class TestMetaclassDetector:
    """Tests for MetaclassDetector (EC-10, FR-37, T-6.6)."""

    def test_custom_metaclass_detection(self, tmp_path):
        """Test detection of custom metaclasses."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
class MyClass(metaclass=CustomMeta):
    pass
"""
        )

        detector = MetaclassDetector()
        tree = ast.parse(test_file.read_text())

        relationships = []
        for node in ast.walk(tree):
            rels = detector.detect(node, str(test_file), tree)
            relationships.extend(rels)

        # FR-42: Should NOT create any relationships
        assert len(relationships) == 0

        # Should have detected warning
        warnings = detector.get_warnings()
        assert len(warnings) == 1

        warning = warnings[0]
        assert warning.pattern_type == DynamicPatternType.METACLASS
        assert warning.severity == WarningSeverity.INFO
        assert "CustomMeta" in warning.message
        assert warning.metadata["class_name"] == "MyClass"
        assert warning.metadata["metaclass_name"] == "CustomMeta"

    def test_standard_metaclass_no_warning(self, tmp_path):
        """Test that standard metaclasses do NOT trigger warning."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
from abc import ABCMeta

class MyAbstract(metaclass=ABCMeta):
    pass
"""
        )

        detector = MetaclassDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should NOT have warnings for ABCMeta
        warnings = detector.get_warnings()
        assert len(warnings) == 0

    def test_type_metaclass_no_warning(self, tmp_path):
        """Test that type metaclass does NOT trigger warning."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
class MyClass(metaclass=type):
    pass
"""
        )

        detector = MetaclassDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should NOT have warnings for type
        warnings = detector.get_warnings()
        assert len(warnings) == 0

    def test_metaclass_emits_in_test_modules(self, tmp_path):
        """Test that metaclass warnings are emitted in test modules too."""
        # Per TDD Section 3.9.1: Metaclass warnings emitted in ALL modules
        test_file = tmp_path / "test_metaclass.py"
        test_file.write_text(
            """
class TestClass(metaclass=CustomMeta):
    pass
"""
        )

        detector = MetaclassDetector(project_root=str(tmp_path))
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should still emit warning even in test module
        warnings = detector.get_warnings()
        assert len(warnings) == 1
        # The warning is marked as test module
        assert warnings[0].is_test_module is True

    def test_module_qualified_metaclass(self, tmp_path):
        """Test detection of module-qualified metaclasses."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
class MyClass(metaclass=mymodule.CustomMeta):
    pass
"""
        )

        detector = MetaclassDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        warnings = detector.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].metadata["metaclass_name"] == "mymodule.CustomMeta"

    def test_class_with_bases_and_metaclass(self, tmp_path):
        """Test detection of metaclass in class with multiple bases."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
class MyClass(Base1, Base2, metaclass=CustomMeta):
    pass
"""
        )

        detector = MetaclassDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        warnings = detector.get_warnings()
        assert len(warnings) == 1

    def test_detector_priority_and_name(self):
        """Test detector metadata."""
        detector = MetaclassDetector()
        assert detector.priority() == 25
        assert detector.name() == "MetaclassDetector"


class TestDynamicPatternIntegration:
    """Integration tests for dynamic pattern detection."""

    def test_multiple_patterns_in_file(self, tmp_path):
        """Test detection of multiple different patterns in same file."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
import module

# Dynamic dispatch
getattr(obj, var_name)()

# Monkey patching
module.func = replacement

# exec/eval
exec(code_string)
eval(expression)

# Decorator
@custom_decorator
def my_func():
    pass

# Metaclass
class MyClass(metaclass=CustomMeta):
    pass
"""
        )

        # Run all detectors
        detectors = [
            DynamicDispatchDetector(),
            MonkeyPatchingDetector(),
            ExecEvalDetector(),
            DecoratorDetector(),
            MetaclassDetector(),
        ]

        tree = ast.parse(test_file.read_text())

        all_warnings = []
        for detector in detectors:
            for node in ast.walk(tree):
                detector.detect(node, str(test_file), tree)
            all_warnings.extend(detector.get_warnings())

        # Should detect all pattern types
        pattern_types = {w.pattern_type for w in all_warnings}
        assert DynamicPatternType.DYNAMIC_DISPATCH in pattern_types
        assert DynamicPatternType.MONKEY_PATCHING in pattern_types
        assert DynamicPatternType.EXEC_EVAL in pattern_types
        assert DynamicPatternType.DECORATOR in pattern_types
        assert DynamicPatternType.METACLASS in pattern_types

    def test_no_relationships_created(self, tmp_path):
        """Test that dynamic pattern detectors never create relationships (FR-42)."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
import module
getattr(obj, var)()
module.func = replacement
exec(code)
@custom
def func(): pass
class C(metaclass=M): pass
"""
        )

        detectors = [
            DynamicDispatchDetector(),
            MonkeyPatchingDetector(),
            ExecEvalDetector(),
            DecoratorDetector(),
            MetaclassDetector(),
        ]

        tree = ast.parse(test_file.read_text())

        total_relationships = 0
        for detector in detectors:
            for node in ast.walk(tree):
                rels = detector.detect(node, str(test_file), tree)
                total_relationships += len(rels)

        # FR-42: NO relationships should be created
        assert total_relationships == 0

    def test_clear_warnings(self, tmp_path):
        """Test that warnings can be cleared between files."""
        file1 = tmp_path / "file1.py"
        file1.write_text("exec(code)")

        file2 = tmp_path / "file2.py"
        file2.write_text("print('no dynamic patterns')")

        detector = ExecEvalDetector()

        # Analyze file1
        tree1 = ast.parse(file1.read_text())
        for node in ast.walk(tree1):
            detector.detect(node, str(file1), tree1)

        assert len(detector.get_warnings()) == 1

        # Clear warnings
        detector.clear_warnings()
        assert len(detector.get_warnings()) == 0

        # Analyze file2
        tree2 = ast.parse(file2.read_text())
        for node in ast.walk(tree2):
            detector.detect(node, str(file2), tree2)

        # No new warnings from file2
        assert len(detector.get_warnings()) == 0

    def test_get_pattern_types(self, tmp_path):
        """Test aggregating pattern types from warnings."""
        test_file = tmp_path / "source.py"
        test_file.write_text(
            """
exec(code1)
eval(expr1)
exec(code2)
"""
        )

        detector = ExecEvalDetector()
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        # Should return unique pattern types
        pattern_types = detector.get_pattern_types()
        assert pattern_types == ["exec_eval"]  # Only one unique type


class TestTestModuleDetection:
    """Tests for test vs source module distinction (DD-3)."""

    @pytest.mark.parametrize(
        "filename,is_test",
        [
            ("test_something.py", True),
            ("something_test.py", True),
            ("conftest.py", True),
            ("source.py", False),
            ("main.py", False),
            ("utils.py", False),
        ],
    )
    def test_test_module_classification(self, tmp_path, filename, is_test):
        """Test that files are correctly classified as test/source."""
        test_file = tmp_path / filename
        test_file.write_text("exec(code)")

        detector = ExecEvalDetector(project_root=str(tmp_path))
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        warnings = detector.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].is_test_module is is_test

    def test_tests_directory(self, tmp_path):
        """Test that files in tests/ directory are classified as test modules."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "module.py"
        test_file.write_text("exec(code)")

        detector = ExecEvalDetector(project_root=str(tmp_path))
        tree = ast.parse(test_file.read_text())

        for node in ast.walk(tree):
            detector.detect(node, str(test_file), tree)

        warnings = detector.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].is_test_module is True
