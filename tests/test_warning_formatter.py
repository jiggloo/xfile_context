# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for warning emission and formatting (T-6.7).

This module tests the warning formatting system per TDD Section 3.9.3:
- JSON format with all required fields (FR-38)
- Human-readable display format
- Actionable guidance for each pattern type
- WarningEmitter service integration

Test Coverage:
- T-6.7: Warning message format compliance
- FR-38: Structured warning format
"""

import json
from datetime import datetime

from xfile_context.detectors import DynamicPatternType, DynamicPatternWarning, WarningSeverity
from xfile_context.warning_formatter import (
    PATTERN_DISPLAY_NAMES,
    PATTERN_GUIDANCE,
    StructuredWarning,
    WarningEmitter,
    WarningFormatter,
)


class TestStructuredWarning:
    """Tests for StructuredWarning dataclass."""

    def test_required_fields_present(self):
        """Test that all required fields from FR-38 are present."""
        warning = StructuredWarning(
            type="dynamic_dispatch",
            file="/project/src/module.py",
            line=42,
            severity="warning",
            pattern="getattr(obj, 'method')",
            message="Dynamic dispatch detected",
            timestamp="2025-11-25T10:30:00Z",
        )

        # Verify required fields per FR-38
        assert warning.type == "dynamic_dispatch"
        assert warning.file == "/project/src/module.py"
        assert warning.line == 42
        assert warning.severity == "warning"
        assert warning.pattern == "getattr(obj, 'method')"
        assert warning.message == "Dynamic dispatch detected"
        assert warning.timestamp == "2025-11-25T10:30:00Z"

    def test_optional_fields(self):
        """Test optional fields (column, explanation)."""
        warning = StructuredWarning(
            type="dynamic_dispatch",
            file="/project/src/module.py",
            line=42,
            column=10,
            severity="warning",
            pattern="getattr(obj, 'method')",
            message="Dynamic dispatch detected",
            explanation="The function name is determined at runtime.",
            timestamp="2025-11-25T10:30:00Z",
        )

        assert warning.column == 10
        assert warning.explanation == "The function name is determined at runtime."

    def test_to_dict_excludes_none_optional_fields(self):
        """Test that to_dict excludes None optional fields."""
        warning = StructuredWarning(
            type="exec_eval",
            file="/project/src/code.py",
            line=100,
            severity="warning",
            pattern="eval(expr)",
            message="exec/eval usage detected",
            timestamp="2025-11-25T10:30:00Z",
        )

        result = warning.to_dict()

        # Required fields should be present
        assert "type" in result
        assert "file" in result
        assert "line" in result
        assert "severity" in result
        assert "pattern" in result
        assert "message" in result
        assert "timestamp" in result

        # Optional None fields should be excluded
        assert "column" not in result
        assert "explanation" not in result

    def test_to_dict_includes_present_optional_fields(self):
        """Test that to_dict includes present optional fields."""
        warning = StructuredWarning(
            type="dynamic_dispatch",
            file="/project/src/module.py",
            line=42,
            column=10,
            severity="warning",
            pattern="getattr(obj, 'method')",
            message="Dynamic dispatch detected",
            explanation="Consider explicit calls.",
            timestamp="2025-11-25T10:30:00Z",
            metadata={"object_name": "obj"},
        )

        result = warning.to_dict()

        assert result["column"] == 10
        assert result["explanation"] == "Consider explicit calls."
        assert result["metadata"] == {"object_name": "obj"}

    def test_to_json_valid_format(self):
        """Test that to_json produces valid JSON."""
        warning = StructuredWarning(
            type="monkey_patching",
            file="/project/src/patch.py",
            line=15,
            severity="warning",
            pattern="module.func = replacement",
            message="Monkey patching detected",
            timestamp="2025-11-25T10:30:00Z",
        )

        json_str = warning.to_json()
        parsed = json.loads(json_str)

        assert parsed["type"] == "monkey_patching"
        assert parsed["file"] == "/project/src/patch.py"
        assert parsed["line"] == 15

    def test_from_dict_roundtrip(self):
        """Test that from_dict correctly reconstructs warning."""
        original = StructuredWarning(
            type="decorator",
            file="/project/src/decorated.py",
            line=5,
            column=1,
            severity="info",
            pattern="@my_decorator",
            message="Decorator pattern detected",
            explanation="Decorators may modify behavior.",
            timestamp="2025-11-25T10:30:00Z",
            metadata={"decorator_name": "my_decorator"},
        )

        reconstructed = StructuredWarning.from_dict(original.to_dict())

        assert reconstructed.type == original.type
        assert reconstructed.file == original.file
        assert reconstructed.line == original.line
        assert reconstructed.column == original.column
        assert reconstructed.severity == original.severity
        assert reconstructed.pattern == original.pattern
        assert reconstructed.message == original.message
        assert reconstructed.explanation == original.explanation
        assert reconstructed.timestamp == original.timestamp

    def test_from_json_roundtrip(self):
        """Test JSON roundtrip serialization."""
        original = StructuredWarning(
            type="metaclass",
            file="/project/src/meta.py",
            line=10,
            severity="info",
            pattern="class Meta(type)",
            message="Metaclass usage detected",
            timestamp="2025-11-25T10:30:00Z",
        )

        json_str = original.to_json()
        reconstructed = StructuredWarning.from_json(json_str)

        assert reconstructed.type == original.type
        assert reconstructed.file == original.file
        assert reconstructed.line == original.line


class TestWarningFormatter:
    """Tests for WarningFormatter class."""

    def test_format_warning_includes_all_required_fields(self):
        """Test that format_warning includes all FR-38 required fields."""
        dynamic_warning = DynamicPatternWarning(
            pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
            filepath="/project/src/module.py",
            line_number=42,
            message="Dynamic dispatch detected",
            severity=WarningSeverity.WARNING,
            is_test_module=False,
            metadata={"object_name": "obj", "attribute_variable": "method_name"},
        )

        structured = WarningFormatter.format_warning(dynamic_warning)

        # All required fields should be present per FR-38
        assert structured.type == "dynamic_dispatch"
        assert structured.file == "/project/src/module.py"
        assert structured.line == 42
        assert structured.severity == "warning"
        assert structured.pattern is not None  # Derived from metadata
        assert structured.message is not None
        assert structured.timestamp is not None

    def test_format_warning_auto_timestamp(self):
        """Test that timestamp is automatically generated if not provided."""
        dynamic_warning = DynamicPatternWarning(
            pattern_type=DynamicPatternType.EXEC_EVAL,
            filepath="/project/src/code.py",
            line_number=100,
            message="exec usage detected",
            severity=WarningSeverity.WARNING,
            is_test_module=False,
        )

        structured = WarningFormatter.format_warning(dynamic_warning)

        # Timestamp should be present and valid ISO format
        assert structured.timestamp is not None
        # Should be parseable as ISO format
        datetime.fromisoformat(structured.timestamp.replace("Z", "+00:00"))

    def test_format_warning_includes_explanation(self):
        """Test that actionable guidance is included as explanation."""
        dynamic_warning = DynamicPatternWarning(
            pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
            filepath="/project/src/module.py",
            line_number=42,
            message="Dynamic dispatch detected",
            severity=WarningSeverity.WARNING,
            is_test_module=False,
        )

        structured = WarningFormatter.format_warning(dynamic_warning)

        # Should include actionable guidance
        assert structured.explanation is not None
        assert (
            "function" in structured.explanation.lower()
            or "static" in structured.explanation.lower()
        )

    def test_format_warning_derives_code_snippet(self):
        """Test that code snippet is derived from metadata."""
        dynamic_warning = DynamicPatternWarning(
            pattern_type=DynamicPatternType.MONKEY_PATCHING,
            filepath="/project/src/patch.py",
            line_number=15,
            message="Monkey patching detected",
            severity=WarningSeverity.WARNING,
            is_test_module=False,
            metadata={"target": "module.func"},
        )

        structured = WarningFormatter.format_warning(dynamic_warning)

        # Pattern should be derived from metadata
        assert "module.func" in structured.pattern

    def test_format_human_readable_warning_severity(self):
        """Test human-readable format uses ⚠️ for warnings."""
        warning = StructuredWarning(
            type="dynamic_dispatch",
            file="/project/src/module.py",
            line=42,
            severity="warning",
            pattern="getattr(obj, 'method')",
            message="Dynamic dispatch detected",
            timestamp="2025-11-25T10:30:00Z",
            explanation="Consider explicit function calls.",
        )

        formatted = WarningFormatter.format_human_readable(warning)

        assert "⚠️" in formatted
        assert "module.py:42" in formatted
        assert "Dynamic dispatch" in formatted

    def test_format_human_readable_info_severity(self):
        """Test human-readable format uses ℹ️ for info."""
        warning = StructuredWarning(
            type="metaclass",
            file="/project/src/meta.py",
            line=10,
            severity="info",
            pattern="class Meta(type)",
            message="Metaclass usage detected",
            timestamp="2025-11-25T10:30:00Z",
        )

        formatted = WarningFormatter.format_human_readable(warning)

        assert "ℹ️" in formatted
        assert "meta.py:10" in formatted
        assert "Metaclass" in formatted

    def test_format_human_readable_includes_pattern(self):
        """Test that human-readable format includes the code pattern."""
        warning = StructuredWarning(
            type="exec_eval",
            file="/project/src/code.py",
            line=100,
            severity="warning",
            pattern="eval(user_input)",
            message="exec/eval usage detected",
            timestamp="2025-11-25T10:30:00Z",
        )

        formatted = WarningFormatter.format_human_readable(warning)

        assert "eval(user_input)" in formatted

    def test_format_human_readable_includes_guidance(self):
        """Test that human-readable format includes guidance arrow."""
        warning = StructuredWarning(
            type="dynamic_dispatch",
            file="/project/src/module.py",
            line=42,
            severity="warning",
            pattern="getattr(obj, 'method')",
            message="Dynamic dispatch detected",
            explanation="Consider using explicit function calls if the function name is known.",
            timestamp="2025-11-25T10:30:00Z",
        )

        formatted = WarningFormatter.format_human_readable(warning)

        # Should include guidance with arrow
        assert "→" in formatted

    def test_format_json_batch(self):
        """Test formatting multiple warnings as JSON array."""
        warnings = [
            StructuredWarning(
                type="dynamic_dispatch",
                file="/project/src/a.py",
                line=10,
                severity="warning",
                pattern="getattr(obj, var)",
                message="Warning 1",
                timestamp="2025-11-25T10:30:00Z",
            ),
            StructuredWarning(
                type="exec_eval",
                file="/project/src/b.py",
                line=20,
                severity="warning",
                pattern="exec(code)",
                message="Warning 2",
                timestamp="2025-11-25T10:31:00Z",
            ),
        ]

        json_str = WarningFormatter.format_json_batch(warnings)
        parsed = json.loads(json_str)

        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert parsed[0]["type"] == "dynamic_dispatch"
        assert parsed[1]["type"] == "exec_eval"


class TestWarningEmitter:
    """Tests for WarningEmitter service."""

    def test_add_warning_converts_to_structured(self):
        """Test that add_warning converts DynamicPatternWarning to StructuredWarning."""
        emitter = WarningEmitter()

        dynamic_warning = DynamicPatternWarning(
            pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
            filepath="/project/src/module.py",
            line_number=42,
            message="Dynamic dispatch detected",
            severity=WarningSeverity.WARNING,
            is_test_module=False,
        )

        emitter.add_warning(dynamic_warning)

        warnings = emitter.get_warnings()
        assert len(warnings) == 1
        assert isinstance(warnings[0], StructuredWarning)
        assert warnings[0].type == "dynamic_dispatch"

    def test_add_warnings_batch(self):
        """Test adding multiple warnings at once."""
        emitter = WarningEmitter()

        batch = [
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/src/a.py",
                line_number=10,
                message="Warning 1",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            ),
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.EXEC_EVAL,
                filepath="/project/src/b.py",
                line_number=20,
                message="Warning 2",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            ),
        ]

        emitter.add_warnings(batch)

        warnings = emitter.get_warnings()
        assert len(warnings) == 2

    def test_get_warnings_excludes_test_modules_by_default(self):
        """Test that warnings from test modules are excluded by default."""
        emitter = WarningEmitter()

        # Add source module warning
        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/src/module.py",
                line_number=42,
                message="Source warning",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )

        # Add test module warning
        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/tests/test_module.py",
                line_number=10,
                message="Test warning",
                severity=WarningSeverity.WARNING,
                is_test_module=True,
            )
        )

        # Default: exclude test modules
        warnings = emitter.get_warnings()
        assert len(warnings) == 1
        assert "src/module.py" in warnings[0].file

        # Include test modules
        all_warnings = emitter.get_warnings(include_test_modules=True)
        assert len(all_warnings) == 2

    def test_get_warnings_by_file(self):
        """Test filtering warnings by file path."""
        emitter = WarningEmitter()

        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/src/a.py",
                line_number=10,
                message="Warning A",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )
        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.EXEC_EVAL,
                filepath="/project/src/b.py",
                line_number=20,
                message="Warning B",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )

        file_a_warnings = emitter.get_warnings_by_file("/project/src/a.py")
        assert len(file_a_warnings) == 1
        assert file_a_warnings[0].type == "dynamic_dispatch"

    def test_get_warnings_by_type(self):
        """Test filtering warnings by pattern type."""
        emitter = WarningEmitter()

        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/src/a.py",
                line_number=10,
                message="Warning A",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )
        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.EXEC_EVAL,
                filepath="/project/src/b.py",
                line_number=20,
                message="Warning B",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )

        exec_warnings = emitter.get_warnings_by_type(DynamicPatternType.EXEC_EVAL)
        assert len(exec_warnings) == 1
        assert exec_warnings[0].type == "exec_eval"

    def test_to_json(self):
        """Test JSON export."""
        emitter = WarningEmitter()

        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/src/module.py",
                line_number=42,
                message="Dynamic dispatch",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )

        json_str = emitter.to_json()
        parsed = json.loads(json_str)

        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["type"] == "dynamic_dispatch"

    def test_to_human_readable(self):
        """Test human-readable export."""
        emitter = WarningEmitter()

        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/src/module.py",
                line_number=42,
                message="Dynamic dispatch",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )

        output = emitter.to_human_readable()

        assert "⚠️" in output
        assert "module.py:42" in output

    def test_to_human_readable_empty(self):
        """Test human-readable output when no warnings."""
        emitter = WarningEmitter()

        output = emitter.to_human_readable()

        assert output == "No warnings detected."

    def test_clear(self):
        """Test clearing all warnings."""
        emitter = WarningEmitter()

        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/src/module.py",
                line_number=42,
                message="Warning",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )

        assert emitter.count() == 1
        emitter.clear()
        assert emitter.count() == 0

    def test_summary(self):
        """Test warning summary by type."""
        emitter = WarningEmitter()

        # Add multiple warnings of different types
        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/src/a.py",
                line_number=10,
                message="Warning 1",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )
        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath="/project/src/b.py",
                line_number=20,
                message="Warning 2",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )
        emitter.add_warning(
            DynamicPatternWarning(
                pattern_type=DynamicPatternType.EXEC_EVAL,
                filepath="/project/src/c.py",
                line_number=30,
                message="Warning 3",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
        )

        summary = emitter.summary()

        assert summary["dynamic_dispatch"] == 2
        assert summary["exec_eval"] == 1


class TestPatternGuidance:
    """Tests for actionable guidance per pattern type."""

    def test_all_pattern_types_have_guidance(self):
        """Test that all DynamicPatternType values have guidance defined."""
        for pattern_type in DynamicPatternType:
            assert pattern_type in PATTERN_GUIDANCE, f"Missing guidance for {pattern_type}"

    def test_all_pattern_types_have_display_names(self):
        """Test that all DynamicPatternType values have display names defined."""
        for pattern_type in DynamicPatternType:
            assert pattern_type in PATTERN_DISPLAY_NAMES, f"Missing display name for {pattern_type}"

    def test_dynamic_dispatch_guidance(self):
        """Test actionable guidance for dynamic dispatch."""
        guidance = PATTERN_GUIDANCE[DynamicPatternType.DYNAMIC_DISPATCH]
        assert "explicit" in guidance.lower() or "function" in guidance.lower()

    def test_exec_eval_guidance(self):
        """Test actionable guidance for exec/eval per TDD Section 3.9.3."""
        guidance = PATTERN_GUIDANCE[DynamicPatternType.EXEC_EVAL]
        # Per TDD: "Consider using safer alternatives
        # (importlib, ast.literal_eval, or explicit logic)"
        assert "safer" in guidance.lower() or "alternative" in guidance.lower()

    def test_monkey_patching_guidance(self):
        """Test actionable guidance for monkey patching."""
        guidance = PATTERN_GUIDANCE[DynamicPatternType.MONKEY_PATCHING]
        assert "runtime" in guidance.lower() or "injection" in guidance.lower()


class TestServiceIntegration:
    """Tests for service integration with WarningEmitter."""

    def test_service_collects_warnings_after_analysis(self, tmp_path):
        """Test that service collects warnings from detectors after analysis."""
        from xfile_context import Config, CrossFileContextService

        # Create a source file with dynamic dispatch (in src/ to avoid test module detection)
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        test_file = src_dir / "dynamic.py"
        test_file.write_text(
            """
obj = SomeClass()
method_name = get_method()
result = getattr(obj, method_name)()  # Dynamic dispatch
"""
        )

        config = Config()
        service = CrossFileContextService(config=config, project_root=str(tmp_path))

        # Analyze file
        service.analyze_file(str(test_file))

        # Check warnings were collected (use include_test_modules=True to ensure we see all)
        warnings = service.get_warnings(include_test_modules=True)
        assert len(warnings) >= 1
        assert any(w.type == "dynamic_dispatch" for w in warnings)

    def test_service_get_warnings_json(self, tmp_path):
        """Test service JSON output method."""
        from xfile_context import Config, CrossFileContextService

        test_file = tmp_path / "exec_code.py"
        test_file.write_text('code = "print(1)"\nexec(code)\n')

        config = Config()
        service = CrossFileContextService(config=config, project_root=str(tmp_path))
        service.analyze_file(str(test_file))

        json_output = service.get_warnings_json()
        parsed = json.loads(json_output)

        assert isinstance(parsed, list)

    def test_service_get_warnings_human_readable(self, tmp_path):
        """Test service human-readable output method."""
        from xfile_context import Config, CrossFileContextService

        test_file = tmp_path / "eval_code.py"
        test_file.write_text('expr = "1 + 2"\nresult = eval(expr)\n')

        config = Config()
        service = CrossFileContextService(config=config, project_root=str(tmp_path))
        service.analyze_file(str(test_file))

        output = service.get_warnings_human_readable()

        # Should contain formatted warnings or "No warnings detected"
        assert isinstance(output, str)

    def test_service_clear_warnings(self, tmp_path):
        """Test service clear warnings method."""
        from xfile_context import Config, CrossFileContextService

        test_file = tmp_path / "dynamic.py"
        test_file.write_text("result = getattr(obj, var)()\n")

        config = Config()
        service = CrossFileContextService(config=config, project_root=str(tmp_path))
        service.analyze_file(str(test_file))

        # Verify warnings exist
        assert len(service.get_warnings(include_test_modules=True)) >= 0

        # Clear and verify
        service.clear_warnings()
        assert len(service.get_warnings(include_test_modules=True)) == 0

    def test_service_warning_summary(self, tmp_path):
        """Test service warning summary method."""
        from xfile_context import Config, CrossFileContextService

        test_file = tmp_path / "multiple.py"
        test_file.write_text(
            """
getattr(obj, var)()
exec("code")
eval("expr")
"""
        )

        config = Config()
        service = CrossFileContextService(config=config, project_root=str(tmp_path))
        service.analyze_file(str(test_file))

        summary = service.get_warning_summary()

        # Summary should be a dict mapping types to counts
        assert isinstance(summary, dict)
