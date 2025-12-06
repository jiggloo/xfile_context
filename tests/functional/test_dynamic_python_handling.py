# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
Functional Tests for Dynamic Python Handling and Warnings (Test Category 6).

NOTE: Marked as slow tests - these analyze a full test codebase.
Run with: pytest -m slow

This module validates that dynamic pattern detection and warning system works correctly
according to T-6.1 through T-6.10 from prd_testing.md Section 8.2.

Tests validate warning emission, suppression, and formatting for:
- Dynamic dispatch (EC-6, FR-33)
- Monkey patching (EC-7, FR-34)
- exec/eval usage (EC-9, FR-35)
- Decorators (EC-8, FR-36)
- Metaclasses (EC-10, FR-37)

Test Cases:
- T-6.1: Verify test module identification works correctly (FR-32)
- T-6.2: Verify dynamic dispatch warnings emitted correctly (FR-33, EC-6)
- T-6.3: Verify monkey patching warnings emitted correctly (FR-34, EC-7)
- T-6.4: Verify exec/eval warnings emitted correctly (FR-35, EC-9)
- T-6.5: Verify decorator warnings emitted appropriately (FR-36, EC-8)
- T-6.6: Verify metaclass warnings emitted correctly (FR-37, EC-10)
- T-6.7: Verify warning message format compliance (FR-38)
- T-6.8: Verify warning suppression configuration works (FR-39, FR-40)
- T-6.9: Verify warnings are logged to structured format (FR-41)
- T-6.10: Verify fail-safe principle (FR-42)

References:
- prd_testing.md Section 8.2 (Test Category 6: Dynamic Python Handling and Warnings)
- prd_edge_cases.md (EC-6 through EC-10)
- TDD Section 3.13.2 (Functional Tests)
"""

import ast
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator, List

import pytest

from xfile_context.config import Config
from xfile_context.detectors import (
    DecoratorDetector,
    DynamicDispatchDetector,
    DynamicPatternType,
    DynamicPatternWarning,
    ExecEvalDetector,
    MetaclassDetector,
    MonkeyPatchingDetector,
    WarningSeverity,
)
from xfile_context.pytest_config_parser import PytestConfig, is_test_module
from xfile_context.warning_formatter import StructuredWarning, WarningEmitter, WarningFormatter
from xfile_context.warning_logger import WarningLogger, read_warnings_from_log
from xfile_context.warning_suppression import WarningSuppressionManager

# Mark entire module as slow - these tests analyze a full codebase
pytestmark = pytest.mark.slow

# Path to the functional test codebase
TEST_CODEBASE_PATH = Path(__file__).parent / "test_codebase"
GROUND_TRUTH_PATH = TEST_CODEBASE_PATH / "ground_truth.json"

# Edge case files for dynamic patterns
EC6_DYNAMIC_DISPATCH = (
    TEST_CODEBASE_PATH / "edge_cases" / "relationship_detection" / "ec6_dynamic_dispatch.py"
)
EC7_MONKEY_PATCHING = (
    TEST_CODEBASE_PATH / "edge_cases" / "relationship_detection" / "ec7_monkey_patching.py"
)
EC8_DECORATORS = TEST_CODEBASE_PATH / "edge_cases" / "relationship_detection" / "ec8_decorators.py"
EC9_EXEC_EVAL = TEST_CODEBASE_PATH / "edge_cases" / "relationship_detection" / "ec9_exec_eval.py"
EC10_METACLASSES = (
    TEST_CODEBASE_PATH / "edge_cases" / "relationship_detection" / "ec10_metaclasses.py"
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def ground_truth() -> Dict[str, Any]:
    """Load ground truth manifest for validation."""
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


@pytest.fixture
def temp_log_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_file() -> Generator[Path, None, None]:
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write("enable_context_injection: true\n")
        f.write("context_token_limit: 500\n")
        config_path = Path(f.name)
    yield config_path
    config_path.unlink(missing_ok=True)


def parse_file(filepath: Path) -> ast.Module:
    """Parse a Python file and return its AST."""
    with open(filepath, encoding="utf-8") as f:
        return ast.parse(f.read(), filename=str(filepath))


def run_detector_on_file(
    detector_class: type, filepath: Path, project_root: str | None = None
) -> List[DynamicPatternWarning]:
    """Run a detector on a file and return detected warnings."""
    detector = detector_class(project_root=project_root)
    module_ast = parse_file(filepath)

    # Walk AST and run detector on each node
    for node in ast.walk(module_ast):
        detector.detect(node, str(filepath), module_ast)

    return detector.get_warnings()


class TestT61TestModuleIdentification:
    """T-6.1: Verify test module identification works correctly (FR-32)."""

    def test_test_file_patterns_match(self) -> None:
        """Files matching test patterns should be identified as test modules.

        Patterns: **/test_*.py, **/*_test.py, **/tests/**/*.py, **/conftest.py
        """
        # test_*.py pattern
        assert is_test_module("test_example.py") is True
        assert is_test_module("/path/to/test_module.py") is True
        assert is_test_module("/path/to/tests/test_something.py") is True

        # *_test.py pattern
        assert is_test_module("module_test.py") is True
        assert is_test_module("/path/to/module_test.py") is True

        # **/tests/**/*.py pattern
        assert is_test_module("/project/tests/unit/test_foo.py") is True
        assert is_test_module("/project/tests/integration/module.py") is True

        # conftest.py pattern
        assert is_test_module("conftest.py") is True
        assert is_test_module("/path/to/conftest.py") is True
        assert is_test_module("/project/tests/conftest.py") is True

    def test_source_files_not_matched(self) -> None:
        """Regular source files should NOT be identified as test modules."""
        assert is_test_module("module.py") is False
        assert is_test_module("/path/to/source.py") is False
        assert is_test_module("/src/service.py") is False
        assert is_test_module("/project/core/models/user.py") is False
        assert is_test_module("testing_utils.py") is False  # 'testing' != 'test_'

    def test_pytest_config_patterns(self) -> None:
        """Test patterns from pytest configuration are respected."""
        # Use project root with pyproject.toml or pytest.ini
        # The test_codebase doesn't have pytest config, so defaults are used
        config = PytestConfig(TEST_CODEBASE_PATH)
        config.load()

        # Should have default patterns
        assert "test_*.py" in config.python_files or "**/test_*.py" in config.get_test_patterns()

    def test_test_module_in_test_codebase(self) -> None:
        """Verify edge case files path detection behavior.

        Note: Edge case fixture files live under tests/ directory, so they match
        the **/tests/**/*.py pattern. This is expected behavior per TDD Section 3.9.2.
        For real source files that shouldn't be treated as tests, they should
        NOT be placed under a tests/ directory structure.
        """
        # Files under tests/ directory ARE identified as test modules
        # This is correct behavior - the path-based detection takes precedence
        assert is_test_module(str(EC6_DYNAMIC_DISPATCH)) is True
        assert is_test_module(str(EC7_MONKEY_PATCHING)) is True

    def test_source_file_outside_tests_not_matched(self) -> None:
        """Verify source files outside tests directory are not matched."""
        # Source files not under tests/ and not matching test patterns
        assert is_test_module("/project/src/service.py") is False
        assert is_test_module("/project/core/models/user.py") is False

    def test_actual_test_file_identified(self) -> None:
        """This test file itself should be identified as a test module."""
        this_file = Path(__file__)
        assert is_test_module(str(this_file)) is True


class TestT62DynamicDispatchWarnings:
    """T-6.2: Verify dynamic dispatch warnings emitted correctly (FR-33, EC-6)."""

    def test_source_module_dynamic_dispatch_warns(self) -> None:
        """Source module with getattr(obj, dynamic_name)() should emit warning."""
        warnings = run_detector_on_file(
            DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH, str(TEST_CODEBASE_PATH)
        )

        # Should detect dynamic dispatch patterns
        assert len(warnings) > 0, "Should detect dynamic dispatch in source module"

        # All warnings should be for dynamic dispatch
        for warning in warnings:
            assert warning.pattern_type == DynamicPatternType.DYNAMIC_DISPATCH

    def test_source_module_warning_not_suppressed(self) -> None:
        """Dynamic dispatch warnings in source modules should not be suppressed."""
        # Create a source file outside of tests/ directory to test source module behavior
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write("obj = object()\n")
            f.write("method_name = 'dynamic'\n")
            f.write("getattr(obj, method_name)()\n")
            source_file = Path(f.name)

        try:
            warnings = run_detector_on_file(DynamicDispatchDetector, source_file)

            # Should detect and warnings should have is_test_module=False
            assert len(warnings) > 0, "Should detect dynamic dispatch"
            for warning in warnings:
                assert (
                    warning.is_test_module is False
                ), "Source module warnings should not be marked as test"
        finally:
            source_file.unlink()

    def test_test_module_no_warning(self) -> None:
        """Test module with getattr(obj, dynamic_name)() should NOT emit warning.

        Test modules commonly use dynamic dispatch for test infrastructure.
        """
        # Create a test file with dynamic dispatch
        with tempfile.NamedTemporaryFile(mode="w", suffix="_test.py", delete=False) as f:
            f.write("obj = object()\n")
            f.write("method_name = 'test'\n")
            f.write("getattr(obj, method_name)()\n")
            test_file = Path(f.name)

        try:
            detector = DynamicDispatchDetector()
            module_ast = parse_file(test_file)

            for node in ast.walk(module_ast):
                detector.detect(node, str(test_file), module_ast)

            warnings = detector.get_warnings()

            # Filter warnings by test module status
            source_warnings = [w for w in warnings if not w.is_test_module]

            # Source warnings should not be emitted for test modules
            assert len(source_warnings) == 0, "Test modules should not have source warnings"
        finally:
            test_file.unlink()

    def test_warning_includes_required_fields(self) -> None:
        """Warning should include file path, line number, and explanation."""
        warnings = run_detector_on_file(
            DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH, str(TEST_CODEBASE_PATH)
        )

        assert len(warnings) > 0
        warning = warnings[0]

        # Check required fields
        assert warning.filepath == str(EC6_DYNAMIC_DISPATCH)
        assert warning.line_number > 0
        assert len(warning.message) > 0
        assert "getattr" in warning.message.lower() or "dynamic" in warning.message.lower()

    def test_static_getattr_no_warning(self) -> None:
        """Static getattr (string literal) should NOT trigger warning."""
        # Create file with static getattr
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("obj = object()\n")
            f.write("getattr(obj, 'known_method')()\n")  # Static - known at parse time
            source_file = Path(f.name)

        try:
            warnings = run_detector_on_file(DynamicDispatchDetector, source_file)
            # Static getattr with string literal should not warn
            assert len(warnings) == 0, "Static getattr should not warn"
        finally:
            source_file.unlink()


class TestT63MonkeyPatchingWarnings:
    """T-6.3: Verify monkey patching warnings emitted correctly (FR-34, EC-7)."""

    def test_source_module_monkey_patching_warns(self) -> None:
        """Source module with module.attr = replacement should emit warning."""
        warnings = run_detector_on_file(
            MonkeyPatchingDetector, EC7_MONKEY_PATCHING, str(TEST_CODEBASE_PATH)
        )

        # Should detect monkey patching patterns
        assert len(warnings) > 0, "Should detect monkey patching in source module"

        # All warnings should be for monkey patching
        for warning in warnings:
            assert warning.pattern_type == DynamicPatternType.MONKEY_PATCHING

    def test_warning_includes_attribute_name(self) -> None:
        """Warning should include file path, line number, modified attribute name."""
        warnings = run_detector_on_file(
            MonkeyPatchingDetector, EC7_MONKEY_PATCHING, str(TEST_CODEBASE_PATH)
        )

        assert len(warnings) > 0
        warning = warnings[0]

        # Check required fields
        assert warning.filepath == str(EC7_MONKEY_PATCHING)
        assert warning.line_number > 0
        assert warning.metadata is not None

        # Message should mention the patched attribute
        assert "validation" in warning.message or warning.metadata.get("module_name")

    def test_test_module_no_warning(self) -> None:
        """Test module with module.attr = replacement (mocking) should NOT emit warning."""
        # Create a test file with monkey patching (common for mocking)
        with tempfile.NamedTemporaryFile(mode="w", suffix="_test.py", delete=False) as f:
            f.write("import os\n")
            f.write("os.path.exists = lambda x: True\n")  # Mock
            test_file = Path(f.name)

        try:
            detector = MonkeyPatchingDetector()
            module_ast = parse_file(test_file)

            for node in ast.walk(module_ast):
                detector.detect(node, str(test_file), module_ast)

            warnings = detector.get_warnings()

            # All warnings should be marked as test module
            source_warnings = [w for w in warnings if not w.is_test_module]
            assert len(source_warnings) == 0, "Test modules should not emit source warnings"
        finally:
            test_file.unlink()

    def test_self_assignment_no_warning(self) -> None:
        """self.attr = value (instance attribute) should NOT trigger warning."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("class Foo:\n")
            f.write("    def __init__(self):\n")
            f.write("        self.value = 42\n")  # Instance attribute, not monkey patch
            source_file = Path(f.name)

        try:
            warnings = run_detector_on_file(MonkeyPatchingDetector, source_file)
            assert len(warnings) == 0, "self.attr assignment should not warn"
        finally:
            source_file.unlink()


class TestT64ExecEvalWarnings:
    """T-6.4: Verify exec/eval warnings emitted correctly (FR-35, EC-9)."""

    def test_source_module_exec_warns(self) -> None:
        """Source module with exec(code_string) should emit warning."""
        warnings = run_detector_on_file(ExecEvalDetector, EC9_EXEC_EVAL, str(TEST_CODEBASE_PATH))

        # Should detect exec/eval patterns
        exec_warnings = [
            w for w in warnings if w.metadata and w.metadata.get("function_name") == "exec"
        ]
        assert len(exec_warnings) > 0, "Should detect exec() in source module"

    def test_source_module_eval_warns(self) -> None:
        """Source module with eval(expr) should emit warning."""
        warnings = run_detector_on_file(ExecEvalDetector, EC9_EXEC_EVAL, str(TEST_CODEBASE_PATH))

        # Should detect eval patterns
        eval_warnings = [
            w for w in warnings if w.metadata and w.metadata.get("function_name") == "eval"
        ]
        assert len(eval_warnings) > 0, "Should detect eval() in source module"

    def test_warning_includes_security_implications(self) -> None:
        """Warning should include file path, line number, and security/analysis implications."""
        warnings = run_detector_on_file(ExecEvalDetector, EC9_EXEC_EVAL, str(TEST_CODEBASE_PATH))

        assert len(warnings) > 0
        warning = warnings[0]

        # Check required fields
        assert warning.filepath == str(EC9_EXEC_EVAL)
        assert warning.line_number > 0

        # Message should mention analysis implications
        assert "static analysis" in warning.message.lower() or "dynamic" in warning.message.lower()

    def test_test_module_no_warning(self) -> None:
        """Test module with exec()/eval() should NOT emit warning."""
        with tempfile.NamedTemporaryFile(mode="w", suffix="_test.py", delete=False) as f:
            f.write("# Testing edge cases\n")
            f.write("result = eval('1 + 1')\n")
            test_file = Path(f.name)

        try:
            detector = ExecEvalDetector()
            module_ast = parse_file(test_file)

            for node in ast.walk(module_ast):
                detector.detect(node, str(test_file), module_ast)

            warnings = detector.get_warnings()
            source_warnings = [w for w in warnings if not w.is_test_module]
            assert len(source_warnings) == 0, "Test modules should not emit source warnings"
        finally:
            test_file.unlink()


class TestT65DecoratorWarnings:
    """T-6.5: Verify decorator warnings emitted appropriately (FR-36, EC-8)."""

    def test_custom_decorator_warns(self) -> None:
        """Source module with custom decorator should emit informational warning."""
        warnings = run_detector_on_file(DecoratorDetector, EC8_DECORATORS, str(TEST_CODEBASE_PATH))

        # Should detect custom decorators
        assert len(warnings) > 0, "Should detect custom decorators"

        # Should be INFO severity
        info_warnings = [w for w in warnings if w.severity == WarningSeverity.INFO]
        assert len(info_warnings) > 0, "Decorator warnings should be INFO severity"

    def test_warning_includes_decorator_name(self) -> None:
        """Warning should include decorator name and explanation of limitation."""
        warnings = run_detector_on_file(DecoratorDetector, EC8_DECORATORS, str(TEST_CODEBASE_PATH))

        assert len(warnings) > 0
        warning = warnings[0]

        # Check metadata includes decorator name
        assert warning.metadata is not None
        assert "decorator_name" in warning.metadata
        assert len(warning.metadata["decorator_name"]) > 0

    def test_common_test_decorators_no_warning(self) -> None:
        """Test module with @pytest.mark, @unittest.skip should NOT emit warning."""
        with tempfile.NamedTemporaryFile(mode="w", suffix="_test.py", delete=False) as f:
            f.write("import pytest\n")
            f.write("@pytest.mark.skip\n")
            f.write("def test_something():\n")
            f.write("    pass\n")
            test_file = Path(f.name)

        try:
            warnings = run_detector_on_file(DecoratorDetector, test_file)
            # pytest.mark decorators should not trigger warnings
            pytest_warnings = [
                w
                for w in warnings
                if w.metadata and "pytest" in w.metadata.get("decorator_name", "")
            ]
            assert len(pytest_warnings) == 0, "@pytest.mark should not warn"
        finally:
            test_file.unlink()

    def test_builtin_decorators_no_warning(self) -> None:
        """Built-in decorators like @staticmethod should NOT emit warning."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("class Foo:\n")
            f.write("    @staticmethod\n")
            f.write("    def bar():\n")
            f.write("        pass\n")
            f.write("    @classmethod\n")
            f.write("    def baz(cls):\n")
            f.write("        pass\n")
            f.write("    @property\n")
            f.write("    def qux(self):\n")
            f.write("        return 1\n")
            source_file = Path(f.name)

        try:
            warnings = run_detector_on_file(DecoratorDetector, source_file)
            builtin_names = {"staticmethod", "classmethod", "property"}
            builtin_warnings = [
                w
                for w in warnings
                if w.metadata and w.metadata.get("decorator_name") in builtin_names
            ]
            assert len(builtin_warnings) == 0, "Built-in decorators should not warn"
        finally:
            source_file.unlink()


class TestT66MetaclassWarnings:
    """T-6.6: Verify metaclass warnings emitted correctly (FR-37, EC-10)."""

    def test_custom_metaclass_warns(self) -> None:
        """Class with custom metaclass should emit informational warning."""
        warnings = run_detector_on_file(
            MetaclassDetector, EC10_METACLASSES, str(TEST_CODEBASE_PATH)
        )

        # Should detect custom metaclasses
        metaclass_warnings = [w for w in warnings if w.pattern_type == DynamicPatternType.METACLASS]
        assert len(metaclass_warnings) > 0, "Should detect custom metaclasses"

    def test_warning_includes_metaclass_name(self) -> None:
        """Warning should include metaclass name and behavior caveat."""
        warnings = run_detector_on_file(
            MetaclassDetector, EC10_METACLASSES, str(TEST_CODEBASE_PATH)
        )

        metaclass_warnings = [w for w in warnings if w.pattern_type == DynamicPatternType.METACLASS]
        assert len(metaclass_warnings) > 0

        warning = metaclass_warnings[0]

        # Check metadata includes metaclass name
        assert warning.metadata is not None
        assert "metaclass_name" in warning.metadata
        assert "class_name" in warning.metadata

        # Message should mention behavior differences
        assert "runtime" in warning.message.lower() or "behavior" in warning.message.lower()

    def test_standard_metaclasses_no_warning(self) -> None:
        """Standard metaclasses like ABCMeta should NOT emit warning."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("from abc import ABCMeta\n")
            f.write("class Interface(metaclass=ABCMeta):\n")
            f.write("    pass\n")
            source_file = Path(f.name)

        try:
            warnings = run_detector_on_file(MetaclassDetector, source_file)
            # ABCMeta is a standard metaclass
            abc_warnings = [
                w
                for w in warnings
                if w.metadata and w.metadata.get("metaclass_name") in ("ABCMeta", "abc.ABCMeta")
            ]
            assert len(abc_warnings) == 0, "ABCMeta should not warn"
        finally:
            source_file.unlink()

    def test_metaclass_warning_severity_info(self) -> None:
        """Metaclass warnings should have INFO severity."""
        warnings = run_detector_on_file(
            MetaclassDetector, EC10_METACLASSES, str(TEST_CODEBASE_PATH)
        )

        for warning in warnings:
            assert warning.severity == WarningSeverity.INFO, "Metaclass warnings should be INFO"


class TestT67WarningMessageFormat:
    """T-6.7: Verify warning message format compliance (FR-38)."""

    def test_all_warnings_include_required_fields(self) -> None:
        """All warnings should include: file path, line number, pattern type, explanation."""
        # Test with each detector
        detectors_and_files = [
            (DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH),
            (MonkeyPatchingDetector, EC7_MONKEY_PATCHING),
            (ExecEvalDetector, EC9_EXEC_EVAL),
            (DecoratorDetector, EC8_DECORATORS),
            (MetaclassDetector, EC10_METACLASSES),
        ]

        for detector_class, filepath in detectors_and_files:
            warnings = run_detector_on_file(detector_class, filepath, str(TEST_CODEBASE_PATH))

            for warning in warnings:
                # File path
                assert warning.filepath, f"Warning from {detector_class.__name__} missing filepath"
                assert Path(warning.filepath).exists() or warning.filepath == str(filepath)

                # Line number
                assert (
                    warning.line_number > 0
                ), f"Warning from {detector_class.__name__} missing line number"

                # Pattern type
                assert (
                    warning.pattern_type is not None
                ), f"Warning from {detector_class.__name__} missing pattern type"

                # Message (explanation)
                assert (
                    len(warning.message) > 0
                ), f"Warning from {detector_class.__name__} missing message"

    def test_warnings_are_machine_parseable(self) -> None:
        """Warnings should be machine-parseable (structured format)."""
        warnings = run_detector_on_file(
            DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH, str(TEST_CODEBASE_PATH)
        )

        assert len(warnings) > 0

        # Convert to structured format
        formatter = WarningFormatter()
        for warning in warnings:
            structured = formatter.format_warning(warning)

            # Should convert to dict without error
            warning_dict = structured.to_dict()
            assert isinstance(warning_dict, dict)

            # Required fields per FR-38
            assert "type" in warning_dict
            assert "file" in warning_dict
            assert "line" in warning_dict
            assert "severity" in warning_dict
            assert "message" in warning_dict
            assert "timestamp" in warning_dict

            # Should serialize to JSON without error
            json_str = structured.to_json()
            parsed = json.loads(json_str)
            assert parsed["type"] == warning_dict["type"]

    def test_structured_warning_round_trip(self) -> None:
        """StructuredWarning should survive JSON round-trip."""
        warnings = run_detector_on_file(ExecEvalDetector, EC9_EXEC_EVAL, str(TEST_CODEBASE_PATH))

        assert len(warnings) > 0
        formatter = WarningFormatter()

        for warning in warnings:
            original = formatter.format_warning(warning)

            # Round trip through JSON
            json_str = original.to_json()
            restored = StructuredWarning.from_json(json_str)

            assert restored.type == original.type
            assert restored.file == original.file
            assert restored.line == original.line
            assert restored.severity == original.severity
            assert restored.message == original.message


class TestT68WarningSuppressionConfiguration:
    """T-6.8: Verify warning suppression configuration works (FR-39, FR-40)."""

    def test_file_level_suppression(self) -> None:
        """Configuration can suppress warnings at file level."""
        # Create suppression manager with file-level suppression
        suppression = WarningSuppressionManager(
            suppress_patterns=[str(EC6_DYNAMIC_DISPATCH)],
            project_root=TEST_CODEBASE_PATH,
        )

        # Create a warning for the suppressed file
        warning = StructuredWarning(
            type="dynamic_dispatch",
            file=str(EC6_DYNAMIC_DISPATCH),
            line=42,
            severity="warning",
            pattern="getattr(obj, name)",
            message="Test warning",
            timestamp="2025-01-01T00:00:00Z",
        )

        assert suppression.should_suppress(warning) is True

    def test_directory_level_suppression(self) -> None:
        """Configuration can suppress warnings at directory level with glob patterns."""
        # Suppress all files in edge_cases directory
        suppression = WarningSuppressionManager(
            suppress_patterns=["edge_cases/**/*"],
            project_root=TEST_CODEBASE_PATH,
        )

        # Warning from edge_cases should be suppressed
        warning = StructuredWarning(
            type="dynamic_dispatch",
            file=str(EC6_DYNAMIC_DISPATCH),
            line=42,
            severity="warning",
            pattern="getattr(obj, name)",
            message="Test warning",
            timestamp="2025-01-01T00:00:00Z",
        )

        assert suppression.should_suppress(warning) is True

    def test_pattern_type_suppression(self) -> None:
        """Configuration can suppress specific pattern types globally."""
        # Suppress all dynamic_dispatch warnings
        suppression = WarningSuppressionManager(
            global_pattern_suppressions={"dynamic_dispatch": True},
            project_root=TEST_CODEBASE_PATH,
        )

        warning = StructuredWarning(
            type="dynamic_dispatch",
            file="/any/path/file.py",
            line=42,
            severity="warning",
            pattern="getattr(obj, name)",
            message="Test warning",
            timestamp="2025-01-01T00:00:00Z",
        )

        assert suppression.should_suppress(warning) is True

        # Other pattern types should not be suppressed
        other_warning = StructuredWarning(
            type="exec_eval",
            file="/any/path/file.py",
            line=42,
            severity="warning",
            pattern="exec(code)",
            message="Test warning",
            timestamp="2025-01-01T00:00:00Z",
        )

        assert suppression.should_suppress(other_warning) is False

    def test_warning_emitter_applies_suppression(self) -> None:
        """WarningEmitter should apply suppression configuration."""
        suppression = WarningSuppressionManager(
            global_pattern_suppressions={"dynamic_dispatch": True},
        )

        emitter = WarningEmitter(suppression_manager=suppression)

        # Add warnings of different types
        warnings = run_detector_on_file(
            DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH, str(TEST_CODEBASE_PATH)
        )

        for warning in warnings:
            emitter.add_warning(warning)

        # Get filtered warnings
        filtered = emitter.get_warnings(apply_suppression=True)

        # Dynamic dispatch warnings should be suppressed
        assert len(filtered) == 0, "Dynamic dispatch warnings should be suppressed"

    def test_suppression_from_config_object(self, temp_config_file: Path) -> None:
        """Suppression manager can be created from Config object."""
        # Write suppression config
        with open(temp_config_file, "w") as f:
            f.write("suppress_dynamic_dispatch_warnings: true\n")

        config = Config(temp_config_file)
        suppression = WarningSuppressionManager.from_config(config)

        # Should have dynamic dispatch suppression enabled
        assert suppression.global_pattern_suppressions.get("dynamic_dispatch") is True


class TestT69StructuredWarningLogging:
    """T-6.9: Verify warnings are logged to structured format (FR-41)."""

    def test_warnings_logged_to_jsonl(self, temp_log_dir: Path) -> None:
        """All warnings should be logged to .jsonl file."""
        warning_logger = WarningLogger(log_dir=temp_log_dir)

        try:
            # Create and log a warning
            warning = StructuredWarning(
                type="dynamic_dispatch",
                file="/path/to/file.py",
                line=42,
                severity="warning",
                pattern="getattr(obj, name)",
                message="Test warning",
                timestamp="2025-01-01T00:00:00Z",
            )

            warning_logger.log_warning(warning)

            # Read back the log
            log_path = warning_logger.get_log_path()
            assert log_path.exists(), "Log file should be created"

            logged = read_warnings_from_log(log_path)
            assert len(logged) == 1
            assert logged[0].type == "dynamic_dispatch"
            assert logged[0].file == "/path/to/file.py"
        finally:
            warning_logger.close()

    def test_log_entries_include_required_fields(self, temp_log_dir: Path) -> None:
        """Log entries should include timestamp, file, line, pattern type, message."""
        warning_logger = WarningLogger(log_dir=temp_log_dir)

        try:
            warning = StructuredWarning(
                type="exec_eval",
                file="/path/to/file.py",
                line=100,
                severity="warning",
                pattern="exec(code)",
                message="Dynamic code execution detected",
                timestamp="2025-01-01T12:00:00Z",
            )

            warning_logger.log_warning(warning)

            log_path = warning_logger.get_log_path()
            with open(log_path) as f:
                log_entry = json.loads(f.readline())

            # Check all required fields
            assert "timestamp" in log_entry
            assert "file" in log_entry
            assert "line" in log_entry
            assert "type" in log_entry  # pattern type
            assert "message" in log_entry

            assert log_entry["timestamp"] == "2025-01-01T12:00:00Z"
            assert log_entry["file"] == "/path/to/file.py"
            assert log_entry["line"] == 100
            assert log_entry["type"] == "exec_eval"
        finally:
            warning_logger.close()

    def test_emitter_integration_with_logger(self, temp_log_dir: Path) -> None:
        """WarningEmitter should log warnings when logger is configured."""
        warning_logger = WarningLogger(log_dir=temp_log_dir)
        emitter = WarningEmitter(warning_logger=warning_logger)

        try:
            # Add warnings from detector
            warnings = run_detector_on_file(
                ExecEvalDetector, EC9_EXEC_EVAL, str(TEST_CODEBASE_PATH)
            )

            for warning in warnings:
                emitter.add_warning(warning)

            # Verify logged
            log_path = warning_logger.get_log_path()
            logged = read_warnings_from_log(log_path)

            assert len(logged) == len(warnings), "All warnings should be logged"
        finally:
            warning_logger.close()

    def test_warning_statistics(self, temp_log_dir: Path) -> None:
        """Warning logger should track statistics per FR-44."""
        warning_logger = WarningLogger(log_dir=temp_log_dir)

        try:
            # Log multiple warnings of different types
            warnings = [
                StructuredWarning(
                    type="dynamic_dispatch",
                    file="/file1.py",
                    line=10,
                    severity="warning",
                    pattern="getattr()",
                    message="msg1",
                    timestamp="2025-01-01T00:00:00Z",
                ),
                StructuredWarning(
                    type="dynamic_dispatch",
                    file="/file1.py",
                    line=20,
                    severity="warning",
                    pattern="getattr()",
                    message="msg2",
                    timestamp="2025-01-01T00:00:01Z",
                ),
                StructuredWarning(
                    type="exec_eval",
                    file="/file2.py",
                    line=30,
                    severity="warning",
                    pattern="exec()",
                    message="msg3",
                    timestamp="2025-01-01T00:00:02Z",
                ),
            ]

            warning_logger.log_warnings(warnings)

            stats = warning_logger.get_statistics()

            assert stats.total_warnings == 3
            assert stats.by_type["dynamic_dispatch"] == 2
            assert stats.by_type["exec_eval"] == 1
            assert len(stats.files_with_most_warnings) > 0
        finally:
            warning_logger.close()


class TestT610FailSafePrinciple:
    """T-6.10: Verify fail-safe principle (FR-42)."""

    def test_detector_returns_empty_relationships(self) -> None:
        """Dynamic pattern detectors should NOT return relationships (FR-42)."""
        detectors_and_files = [
            (DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH),
            (MonkeyPatchingDetector, EC7_MONKEY_PATCHING),
            (ExecEvalDetector, EC9_EXEC_EVAL),
            (DecoratorDetector, EC8_DECORATORS),
            (MetaclassDetector, EC10_METACLASSES),
        ]

        for detector_class, filepath in detectors_and_files:
            detector = detector_class(project_root=str(TEST_CODEBASE_PATH))
            module_ast = parse_file(filepath)

            # Walk AST and collect return values from detect()
            all_relationships = []
            for node in ast.walk(module_ast):
                relationships = detector.detect(node, str(filepath), module_ast)
                all_relationships.extend(relationships)

            # Detector should return empty list (no relationships)
            assert (
                len(all_relationships) == 0
            ), f"{detector_class.__name__} should return empty list per FR-42 fail-safe"

    def test_untrackable_patterns_marked_in_metadata(self) -> None:
        """Untrackable patterns should be marked in warning metadata."""
        # Dynamic dispatch should indicate pattern is untrackable
        warnings = run_detector_on_file(
            DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH, str(TEST_CODEBASE_PATH)
        )

        for warning in warnings:
            # Warning indicates the pattern cannot be tracked
            assert (
                "unavailable" in warning.message.lower() or "untrackable" in warning.message.lower()
            )

    def test_no_incorrect_relationships_added(self) -> None:
        """System should NOT attempt to track relationships for unhandled dynamic patterns."""
        # This is verified by test_detector_returns_empty_relationships
        # Additional verification: check that warnings explicitly state tracking unavailable

        all_warnings = []
        detector_files = [
            (DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH),
            (MonkeyPatchingDetector, EC7_MONKEY_PATCHING),
            (ExecEvalDetector, EC9_EXEC_EVAL),
        ]

        for detector_class, filepath in detector_files:
            warnings = run_detector_on_file(detector_class, filepath, str(TEST_CODEBASE_PATH))
            all_warnings.extend(warnings)

        # All warnings should indicate tracking is not available
        for warning in all_warnings:
            # Message should indicate tracking unavailable or similar
            message_lower = warning.message.lower()
            tracking_keywords = ["unavailable", "incomplete", "inaccurate", "cannot"]
            assert any(
                kw in message_lower for kw in tracking_keywords
            ), f"Warning should indicate tracking limitation: {warning.message}"

    def test_exec_eval_marks_file_metadata(self) -> None:
        """exec/eval detection should mark contains_dynamic_execution in metadata."""
        warnings = run_detector_on_file(ExecEvalDetector, EC9_EXEC_EVAL, str(TEST_CODEBASE_PATH))

        # At least one warning should have dynamic execution marker
        exec_warnings = [
            w
            for w in warnings
            if w.metadata and w.metadata.get("contains_dynamic_execution") == "true"
        ]

        assert len(exec_warnings) > 0, "exec/eval should mark contains_dynamic_execution"


class TestWarningEmitterIntegration:
    """Integration tests for WarningEmitter with full detection pipeline."""

    def test_emitter_collects_from_multiple_detectors(self) -> None:
        """WarningEmitter should aggregate warnings from multiple detectors."""
        emitter = WarningEmitter()

        # Run multiple detectors
        detectors_and_files = [
            (DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH),
            (ExecEvalDetector, EC9_EXEC_EVAL),
        ]

        for detector_class, filepath in detectors_and_files:
            warnings = run_detector_on_file(detector_class, filepath, str(TEST_CODEBASE_PATH))
            emitter.add_warnings(warnings)

        # Should have warnings from both
        all_warnings = emitter.get_warnings(include_test_modules=True)
        types = {w.type for w in all_warnings}

        assert "dynamic_dispatch" in types
        assert "exec_eval" in types

    def test_emitter_json_export(self) -> None:
        """WarningEmitter should export warnings as JSON."""
        # Create source file outside tests/ to get non-test warnings
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write("obj = object()\n")
            f.write("method_name = 'dynamic'\n")
            f.write("getattr(obj, method_name)()\n")
            source_file = Path(f.name)

        try:
            emitter = WarningEmitter()
            warnings = run_detector_on_file(DynamicDispatchDetector, source_file)
            emitter.add_warnings(warnings)

            json_output = emitter.to_json()
            parsed = json.loads(json_output)

            assert isinstance(parsed, list)
            assert len(parsed) > 0
            assert all("type" in w for w in parsed)
        finally:
            source_file.unlink()

    def test_emitter_human_readable_export(self) -> None:
        """WarningEmitter should export warnings as human-readable text."""
        # Create source file outside tests/ to get non-test warnings
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write("obj = object()\n")
            f.write("method_name = 'dynamic'\n")
            f.write("getattr(obj, method_name)()\n")
            source_file = Path(f.name)

        try:
            emitter = WarningEmitter()
            warnings = run_detector_on_file(DynamicDispatchDetector, source_file)
            emitter.add_warnings(warnings)

            human_output = emitter.to_human_readable()

            # Should contain warning markers and file references
            assert "⚠️" in human_output or "ℹ️" in human_output
            assert "dynamic" in human_output.lower()
        finally:
            source_file.unlink()

    def test_emitter_summary(self) -> None:
        """WarningEmitter should provide summary by type."""
        # Create source file outside tests/ to get non-test warnings
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir="/tmp") as f:
            f.write("obj = object()\n")
            f.write("method_name = 'dynamic'\n")
            f.write("getattr(obj, method_name)()\n")
            source_file = Path(f.name)

        try:
            emitter = WarningEmitter()
            warnings = run_detector_on_file(DynamicDispatchDetector, source_file)
            emitter.add_warnings(warnings)

            summary = emitter.summary()

            assert "dynamic_dispatch" in summary
            assert summary["dynamic_dispatch"] > 0
        finally:
            source_file.unlink()

    def test_emitter_includes_test_module_warnings_when_requested(self) -> None:
        """WarningEmitter should include test module warnings when explicitly requested."""
        emitter = WarningEmitter()

        # Use fixture files which are under tests/ directory
        warnings = run_detector_on_file(
            DynamicDispatchDetector, EC6_DYNAMIC_DISPATCH, str(TEST_CODEBASE_PATH)
        )
        emitter.add_warnings(warnings)

        # Without include_test_modules, should be empty (filtered out)
        filtered = emitter.get_warnings(include_test_modules=False)
        assert len(filtered) == 0, "Test module warnings should be filtered by default"

        # With include_test_modules=True, should have warnings
        all_warnings = emitter.get_warnings(include_test_modules=True)
        assert len(all_warnings) > 0, "Test module warnings should be available when requested"
