# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for warning suppression (T-6.8).

This module tests the warning suppression system per TDD Section 3.9.4:
- File-level suppression (FR-39)
- Directory-level suppression with glob patterns (FR-40)
- Pattern-type suppression (global)
- Per-file pattern-type suppression
- Precedence rules
- Configuration validation

Test Coverage:
- T-6.8: Warning suppression test
- FR-39: File-level suppression
- FR-40: Directory-level suppression
"""

from pathlib import Path

from xfile_context.config import Config
from xfile_context.detectors import DynamicPatternType, DynamicPatternWarning, WarningSeverity
from xfile_context.warning_formatter import StructuredWarning, WarningEmitter
from xfile_context.warning_suppression import VALID_PATTERN_TYPES, WarningSuppressionManager


def create_structured_warning(
    pattern_type: str = "dynamic_dispatch",
    filepath: str = "/project/src/module.py",
    line: int = 42,
) -> StructuredWarning:
    """Helper to create StructuredWarning for testing."""
    return StructuredWarning(
        type=pattern_type,
        file=filepath,
        line=line,
        severity="warning",
        pattern=f"<{pattern_type}>",
        message=f"{pattern_type} detected",
        timestamp="2025-11-25T10:30:00Z",
    )


def create_dynamic_warning(
    pattern_type: DynamicPatternType = DynamicPatternType.DYNAMIC_DISPATCH,
    filepath: str = "/project/src/module.py",
    line: int = 42,
    is_test_module: bool = False,
) -> DynamicPatternWarning:
    """Helper to create DynamicPatternWarning for testing."""
    return DynamicPatternWarning(
        pattern_type=pattern_type,
        filepath=filepath,
        line_number=line,
        message=f"{pattern_type.value} detected",
        severity=WarningSeverity.WARNING,
        is_test_module=is_test_module,
    )


class TestWarningSuppressionManagerInit:
    """Tests for WarningSuppressionManager initialization."""

    def test_default_initialization(self):
        """Test default initialization with no suppression configured."""
        manager = WarningSuppressionManager()

        assert manager.suppress_patterns == []
        assert manager.global_pattern_suppressions == {}
        assert manager.file_specific_suppressions == {}

    def test_init_with_suppress_patterns(self):
        """Test initialization with file/directory patterns."""
        patterns = ["src/legacy/**/*", "scripts/migration.py"]
        manager = WarningSuppressionManager(suppress_patterns=patterns)

        assert manager.suppress_patterns == patterns

    def test_init_with_global_suppressions(self):
        """Test initialization with global pattern-type suppressions."""
        global_suppressions = {
            "dynamic_dispatch": True,
            "metaclass": False,
        }
        manager = WarningSuppressionManager(global_pattern_suppressions=global_suppressions)

        assert manager.global_pattern_suppressions["dynamic_dispatch"] is True
        assert manager.global_pattern_suppressions["metaclass"] is False

    def test_init_with_file_specific_suppressions(self):
        """Test initialization with per-file suppressions."""
        file_specific = {
            "src/utils.py": ["dynamic_dispatch", "decorator"],
            "src/base.py": ["metaclass"],
        }
        manager = WarningSuppressionManager(file_specific_suppressions=file_specific)

        assert "src/utils.py" in manager.file_specific_suppressions
        assert "dynamic_dispatch" in manager.file_specific_suppressions["src/utils.py"]

    def test_init_with_project_root(self, tmp_path):
        """Test initialization with custom project root."""
        manager = WarningSuppressionManager(project_root=tmp_path)

        assert manager.project_root == tmp_path


class TestGlobalPatternSuppression:
    """Tests for global pattern-type suppression."""

    def test_global_suppression_enabled(self):
        """Test that global suppression works when enabled."""
        manager = WarningSuppressionManager(global_pattern_suppressions={"dynamic_dispatch": True})

        warning = create_structured_warning(pattern_type="dynamic_dispatch")
        assert manager.should_suppress(warning) is True

    def test_global_suppression_disabled(self):
        """Test that warnings pass when global suppression is disabled."""
        manager = WarningSuppressionManager(global_pattern_suppressions={"dynamic_dispatch": False})

        warning = create_structured_warning(pattern_type="dynamic_dispatch")
        assert manager.should_suppress(warning) is False

    def test_global_suppression_not_configured(self):
        """Test that warnings pass when type is not configured."""
        manager = WarningSuppressionManager(global_pattern_suppressions={"metaclass": True})

        warning = create_structured_warning(pattern_type="dynamic_dispatch")
        assert manager.should_suppress(warning) is False

    def test_multiple_global_suppressions(self):
        """Test multiple global suppression types."""
        manager = WarningSuppressionManager(
            global_pattern_suppressions={
                "dynamic_dispatch": True,
                "exec_eval": True,
                "monkey_patching": False,
            }
        )

        assert (
            manager.should_suppress(create_structured_warning(pattern_type="dynamic_dispatch"))
            is True
        )
        assert manager.should_suppress(create_structured_warning(pattern_type="exec_eval")) is True
        assert (
            manager.should_suppress(create_structured_warning(pattern_type="monkey_patching"))
            is False
        )


class TestFileLevelSuppression:
    """Tests for file-level suppression (FR-39)."""

    def test_exact_file_path_suppression(self):
        """Test suppression with exact file path."""
        manager = WarningSuppressionManager(
            suppress_patterns=["src/legacy/old_module.py"],
            project_root=Path("/project"),
        )

        # Warning from suppressed file
        warning = create_structured_warning(filepath="/project/src/legacy/old_module.py")
        assert manager.should_suppress(warning) is True

        # Warning from non-suppressed file
        warning2 = create_structured_warning(filepath="/project/src/new_module.py")
        assert manager.should_suppress(warning2) is False

    def test_multiple_file_suppressions(self):
        """Test multiple file-level suppressions."""
        manager = WarningSuppressionManager(
            suppress_patterns=[
                "src/legacy/old_module.py",
                "scripts/migration_script.py",
            ],
            project_root=Path("/project"),
        )

        assert (
            manager.should_suppress(
                create_structured_warning(filepath="/project/src/legacy/old_module.py")
            )
            is True
        )
        assert (
            manager.should_suppress(
                create_structured_warning(filepath="/project/scripts/migration_script.py")
            )
            is True
        )
        assert (
            manager.should_suppress(create_structured_warning(filepath="/project/src/main.py"))
            is False
        )


class TestDirectoryLevelSuppression:
    """Tests for directory-level suppression with glob patterns (FR-40)."""

    def test_star_glob_pattern(self):
        """Test suppression with * glob pattern."""
        manager = WarningSuppressionManager(
            suppress_patterns=["tests/*.py"],
            project_root=Path("/project"),
        )

        # File matching pattern
        warning = create_structured_warning(filepath="/project/tests/test_module.py")
        assert manager.should_suppress(warning) is True

        # File not matching (different directory)
        warning2 = create_structured_warning(filepath="/project/src/module.py")
        assert manager.should_suppress(warning2) is False

    def test_double_star_glob_pattern(self):
        """Test suppression with ** glob pattern (recursive)."""
        manager = WarningSuppressionManager(
            suppress_patterns=["tests/**/*"],
            project_root=Path("/project"),
        )

        # Direct child
        assert (
            manager.should_suppress(create_structured_warning(filepath="/project/tests/test_a.py"))
            is True
        )

        # Nested child
        assert (
            manager.should_suppress(
                create_structured_warning(filepath="/project/tests/unit/test_b.py")
            )
            is True
        )

        # Deeply nested
        assert (
            manager.should_suppress(
                create_structured_warning(filepath="/project/tests/integration/api/test_c.py")
            )
            is True
        )

        # Not matching
        assert (
            manager.should_suppress(create_structured_warning(filepath="/project/src/module.py"))
            is False
        )

    def test_extension_glob_pattern(self):
        """Test suppression with extension pattern."""
        manager = WarningSuppressionManager(
            suppress_patterns=["generated/**/*.py"],
            project_root=Path("/project"),
        )

        # Python files match
        assert (
            manager.should_suppress(
                create_structured_warning(filepath="/project/generated/models.py")
            )
            is True
        )
        assert (
            manager.should_suppress(
                create_structured_warning(filepath="/project/generated/deep/nested.py")
            )
            is True
        )

    def test_vendor_directory_pattern(self):
        """Test suppression for vendor directories."""
        manager = WarningSuppressionManager(
            suppress_patterns=["vendor/**/*.py"],
            project_root=Path("/project"),
        )

        assert (
            manager.should_suppress(
                create_structured_warning(filepath="/project/vendor/lib/module.py")
            )
            is True
        )


class TestFileSpecificPatternSuppression:
    """Tests for per-file pattern-type suppression."""

    def test_file_specific_single_pattern(self):
        """Test file-specific suppression with single pattern type."""
        manager = WarningSuppressionManager(
            file_specific_suppressions={
                "src/utils.py": ["dynamic_dispatch"],
            },
            project_root=Path("/project"),
        )

        # Suppressed: matching file and pattern type
        warning = create_structured_warning(
            pattern_type="dynamic_dispatch",
            filepath="/project/src/utils.py",
        )
        assert manager.should_suppress(warning) is True

        # Not suppressed: matching file, different pattern type
        warning2 = create_structured_warning(
            pattern_type="exec_eval",
            filepath="/project/src/utils.py",
        )
        assert manager.should_suppress(warning2) is False

        # Not suppressed: different file, matching pattern type
        warning3 = create_structured_warning(
            pattern_type="dynamic_dispatch",
            filepath="/project/src/other.py",
        )
        assert manager.should_suppress(warning3) is False

    def test_file_specific_multiple_patterns(self):
        """Test file-specific suppression with multiple pattern types."""
        manager = WarningSuppressionManager(
            file_specific_suppressions={
                "src/utils.py": ["dynamic_dispatch", "decorator"],
            },
            project_root=Path("/project"),
        )

        assert (
            manager.should_suppress(
                create_structured_warning(
                    pattern_type="dynamic_dispatch", filepath="/project/src/utils.py"
                )
            )
            is True
        )
        assert (
            manager.should_suppress(
                create_structured_warning(
                    pattern_type="decorator", filepath="/project/src/utils.py"
                )
            )
            is True
        )
        assert (
            manager.should_suppress(
                create_structured_warning(
                    pattern_type="metaclass", filepath="/project/src/utils.py"
                )
            )
            is False
        )

    def test_file_specific_multiple_files(self):
        """Test file-specific suppression for multiple files."""
        manager = WarningSuppressionManager(
            file_specific_suppressions={
                "src/utils.py": ["dynamic_dispatch"],
                "src/base.py": ["metaclass"],
            },
            project_root=Path("/project"),
        )

        assert (
            manager.should_suppress(
                create_structured_warning(
                    pattern_type="dynamic_dispatch", filepath="/project/src/utils.py"
                )
            )
            is True
        )
        assert (
            manager.should_suppress(
                create_structured_warning(pattern_type="metaclass", filepath="/project/src/base.py")
            )
            is True
        )
        assert (
            manager.should_suppress(
                create_structured_warning(
                    pattern_type="metaclass", filepath="/project/src/utils.py"
                )
            )
            is False
        )


class TestSuppressionPrecedence:
    """Tests for suppression precedence rules (TDD Section 3.9.4)."""

    def test_file_specific_overrides_global(self):
        """Test that file-specific suppression takes precedence over global."""
        # Global suppression is disabled, but file-specific is enabled
        manager = WarningSuppressionManager(
            global_pattern_suppressions={"dynamic_dispatch": False},
            file_specific_suppressions={
                "src/utils.py": ["dynamic_dispatch"],
            },
            project_root=Path("/project"),
        )

        # File-specific should win
        warning = create_structured_warning(
            pattern_type="dynamic_dispatch",
            filepath="/project/src/utils.py",
        )
        assert manager.should_suppress(warning) is True

    def test_global_applies_when_no_file_specific(self):
        """Test that global suppression applies when no file-specific rule."""
        manager = WarningSuppressionManager(
            global_pattern_suppressions={"dynamic_dispatch": True},
            file_specific_suppressions={
                "src/utils.py": ["metaclass"],  # Different pattern type
            },
            project_root=Path("/project"),
        )

        # Global should apply for dynamic_dispatch in other file
        warning = create_structured_warning(
            pattern_type="dynamic_dispatch",
            filepath="/project/src/other.py",
        )
        assert manager.should_suppress(warning) is True

    def test_pattern_type_overrides_file_level(self):
        """Test that pattern-type suppression applies before file-level check."""
        manager = WarningSuppressionManager(
            global_pattern_suppressions={"dynamic_dispatch": True},
            suppress_patterns=[],  # No file-level suppression
            project_root=Path("/project"),
        )

        warning = create_structured_warning(
            pattern_type="dynamic_dispatch",
            filepath="/project/src/any_file.py",
        )
        assert manager.should_suppress(warning) is True

    def test_file_level_applies_to_all_patterns(self):
        """Test that file-level suppression suppresses all pattern types."""
        manager = WarningSuppressionManager(
            suppress_patterns=["src/legacy/**/*"],
            project_root=Path("/project"),
        )

        # All pattern types should be suppressed for files matching pattern
        for pattern_type in VALID_PATTERN_TYPES:
            warning = create_structured_warning(
                pattern_type=pattern_type,
                filepath="/project/src/legacy/old_code.py",
            )
            assert manager.should_suppress(warning) is True


class TestConfigurationValidation:
    """Tests for configuration validation."""

    def test_invalid_pattern_type_in_global_ignored(self, caplog):
        """Test that invalid pattern types in global config are logged and ignored."""
        manager = WarningSuppressionManager(
            global_pattern_suppressions={
                "dynamic_dispatch": True,
                "invalid_type": True,  # Invalid
            }
        )

        # Valid type should be stored
        assert "dynamic_dispatch" in manager.global_pattern_suppressions

        # Invalid type should be ignored
        assert "invalid_type" not in manager.global_pattern_suppressions

    def test_invalid_pattern_type_in_file_specific_ignored(self, caplog):
        """Test that invalid pattern types in file-specific config are ignored."""
        manager = WarningSuppressionManager(
            file_specific_suppressions={
                "src/utils.py": ["dynamic_dispatch", "invalid_type"],
            }
        )

        # Valid type should be stored
        assert "dynamic_dispatch" in manager.file_specific_suppressions["src/utils.py"]

        # Invalid type should be ignored
        assert "invalid_type" not in manager.file_specific_suppressions["src/utils.py"]

    def test_invalid_file_specific_value_type_ignored(self, caplog):
        """Test that invalid value types in file-specific config are ignored."""
        manager = WarningSuppressionManager(
            file_specific_suppressions={
                "src/utils.py": ["dynamic_dispatch"],
                "src/bad.py": "not_a_list",  # Invalid - should be list
            }
        )

        # Valid entry should be stored
        assert "src/utils.py" in manager.file_specific_suppressions

        # Invalid entry should be ignored
        assert "src/bad.py" not in manager.file_specific_suppressions


class TestFromConfigFactory:
    """Tests for WarningSuppressionManager.from_config factory method."""

    def test_from_config_extracts_suppress_warnings(self, tmp_path):
        """Test that from_config extracts suppress_warnings from Config."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text(
            """
suppress_warnings:
  - "tests/**/*"
  - "src/legacy/old_module.py"
"""
        )

        config = Config(config_path=config_file)
        manager = WarningSuppressionManager.from_config(config)

        assert "tests/**/*" in manager.suppress_patterns
        assert "src/legacy/old_module.py" in manager.suppress_patterns

    def test_from_config_extracts_global_suppressions(self, tmp_path):
        """Test that from_config extracts pattern-type suppression flags."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text(
            """
suppress_dynamic_dispatch_warnings: true
suppress_metaclass_warnings: false
"""
        )

        config = Config(config_path=config_file)
        manager = WarningSuppressionManager.from_config(config)

        assert manager.global_pattern_suppressions["dynamic_dispatch"] is True
        assert manager.global_pattern_suppressions["metaclass"] is False

    def test_from_config_extracts_file_specific_suppressions(self, tmp_path):
        """Test that from_config extracts file_specific_suppressions."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text(
            """
file_specific_suppressions:
  "src/utils.py":
    - "dynamic_dispatch"
    - "decorator"
"""
        )

        config = Config(config_path=config_file)
        manager = WarningSuppressionManager.from_config(config)

        assert "src/utils.py" in manager.file_specific_suppressions
        assert "dynamic_dispatch" in manager.file_specific_suppressions["src/utils.py"]

    def test_from_config_with_project_root(self, tmp_path):
        """Test that from_config accepts project_root parameter."""
        config = Config()
        manager = WarningSuppressionManager.from_config(config, project_root=tmp_path)

        assert manager.project_root == tmp_path


class TestFilterWarnings:
    """Tests for filter_warnings method."""

    def test_filter_removes_suppressed(self):
        """Test that filter_warnings removes suppressed warnings."""
        manager = WarningSuppressionManager(global_pattern_suppressions={"dynamic_dispatch": True})

        warnings = [
            create_structured_warning(pattern_type="dynamic_dispatch"),
            create_structured_warning(pattern_type="exec_eval"),
            create_structured_warning(pattern_type="monkey_patching"),
        ]

        filtered = manager.filter_warnings(warnings)

        assert len(filtered) == 2
        assert all(w.type != "dynamic_dispatch" for w in filtered)

    def test_filter_preserves_unsuppressed(self):
        """Test that filter_warnings preserves unsuppressed warnings."""
        manager = WarningSuppressionManager()  # No suppression configured

        warnings = [
            create_structured_warning(pattern_type="dynamic_dispatch"),
            create_structured_warning(pattern_type="exec_eval"),
        ]

        filtered = manager.filter_warnings(warnings)

        assert len(filtered) == 2


class TestWarningEmitterIntegration:
    """Tests for WarningEmitter integration with suppression."""

    def test_emitter_with_suppression_manager(self):
        """Test WarningEmitter with suppression manager configured."""
        suppression = WarningSuppressionManager(
            global_pattern_suppressions={"dynamic_dispatch": True}
        )
        emitter = WarningEmitter(suppression_manager=suppression)

        # Add warnings
        emitter.add_warning(create_dynamic_warning(DynamicPatternType.DYNAMIC_DISPATCH))
        emitter.add_warning(create_dynamic_warning(DynamicPatternType.EXEC_EVAL))

        # Get warnings - suppressed ones should be filtered
        warnings = emitter.get_warnings()

        assert len(warnings) == 1
        assert warnings[0].type == "exec_eval"

    def test_emitter_without_suppression_returns_all(self):
        """Test WarningEmitter without suppression returns all warnings."""
        emitter = WarningEmitter()  # No suppression manager

        emitter.add_warning(create_dynamic_warning(DynamicPatternType.DYNAMIC_DISPATCH))
        emitter.add_warning(create_dynamic_warning(DynamicPatternType.EXEC_EVAL))

        warnings = emitter.get_warnings()

        assert len(warnings) == 2

    def test_emitter_apply_suppression_false(self):
        """Test WarningEmitter with apply_suppression=False."""
        suppression = WarningSuppressionManager(
            global_pattern_suppressions={"dynamic_dispatch": True}
        )
        emitter = WarningEmitter(suppression_manager=suppression)

        emitter.add_warning(create_dynamic_warning(DynamicPatternType.DYNAMIC_DISPATCH))
        emitter.add_warning(create_dynamic_warning(DynamicPatternType.EXEC_EVAL))

        # Get warnings without suppression
        warnings = emitter.get_warnings(apply_suppression=False)

        assert len(warnings) == 2

    def test_emitter_set_suppression_manager(self):
        """Test setting suppression manager after construction."""
        emitter = WarningEmitter()

        emitter.add_warning(create_dynamic_warning(DynamicPatternType.DYNAMIC_DISPATCH))
        emitter.add_warning(create_dynamic_warning(DynamicPatternType.EXEC_EVAL))

        # Initially no suppression
        assert len(emitter.get_warnings()) == 2

        # Add suppression manager
        suppression = WarningSuppressionManager(
            global_pattern_suppressions={"dynamic_dispatch": True}
        )
        emitter.set_suppression_manager(suppression)

        # Now suppression should apply
        assert len(emitter.get_warnings()) == 1


class TestGetSuppressionReason:
    """Tests for get_suppression_reason method."""

    def test_reason_for_file_specific(self):
        """Test reason string for file-specific suppression."""
        manager = WarningSuppressionManager(
            file_specific_suppressions={
                "src/utils.py": ["dynamic_dispatch"],
            },
            project_root=Path("/project"),
        )

        warning = create_structured_warning(
            pattern_type="dynamic_dispatch",
            filepath="/project/src/utils.py",
        )

        reason = manager.get_suppression_reason(warning)
        assert "File-specific" in reason
        assert "dynamic_dispatch" in reason

    def test_reason_for_global(self):
        """Test reason string for global suppression."""
        manager = WarningSuppressionManager(global_pattern_suppressions={"exec_eval": True})

        warning = create_structured_warning(pattern_type="exec_eval")

        reason = manager.get_suppression_reason(warning)
        assert "Global" in reason
        assert "exec_eval" in reason

    def test_reason_for_file_level(self):
        """Test reason string for file-level suppression."""
        manager = WarningSuppressionManager(
            suppress_patterns=["src/legacy.py"],
            project_root=Path("/project"),
        )

        warning = create_structured_warning(filepath="/project/src/legacy.py")

        reason = manager.get_suppression_reason(warning)
        assert "File-level" in reason

    def test_reason_for_directory_level(self):
        """Test reason string for directory-level suppression."""
        manager = WarningSuppressionManager(
            suppress_patterns=["tests/**/*"],
            project_root=Path("/project"),
        )

        warning = create_structured_warning(filepath="/project/tests/test_mod.py")

        reason = manager.get_suppression_reason(warning)
        assert "Directory-level" in reason

    def test_reason_none_when_not_suppressed(self):
        """Test that None is returned when not suppressed."""
        manager = WarningSuppressionManager()

        warning = create_structured_warning()

        reason = manager.get_suppression_reason(warning)
        assert reason is None


class TestValidPatternTypes:
    """Tests for VALID_PATTERN_TYPES constant."""

    def test_all_dynamic_pattern_types_valid(self):
        """Test that all DynamicPatternType values are in VALID_PATTERN_TYPES."""
        for pattern_type in DynamicPatternType:
            assert pattern_type.value in VALID_PATTERN_TYPES

    def test_valid_pattern_types_complete(self):
        """Test that VALID_PATTERN_TYPES contains expected types."""
        expected = {
            "dynamic_dispatch",
            "monkey_patching",
            "exec_eval",
            "decorator",
            "metaclass",
        }
        assert expected == VALID_PATTERN_TYPES


class TestConfigFileSpecificSuppressions:
    """Tests for file_specific_suppressions config option."""

    def test_config_loads_file_specific_suppressions(self, tmp_path):
        """Test that Config correctly loads file_specific_suppressions."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text(
            """
file_specific_suppressions:
  "src/utils.py":
    - "dynamic_dispatch"
    - "decorator"
  "src/base.py":
    - "metaclass"
"""
        )

        config = Config(config_path=config_file)

        assert "src/utils.py" in config.file_specific_suppressions
        assert "dynamic_dispatch" in config.file_specific_suppressions["src/utils.py"]
        assert "decorator" in config.file_specific_suppressions["src/utils.py"]
        assert "src/base.py" in config.file_specific_suppressions
        assert "metaclass" in config.file_specific_suppressions["src/base.py"]

    def test_config_default_file_specific_suppressions(self, tmp_path):
        """Test that Config has empty default for file_specific_suppressions."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text("")  # Empty config

        config = Config(config_path=config_file)

        assert config.file_specific_suppressions == {}

    def test_config_invalid_file_specific_suppressions_uses_default(self, tmp_path):
        """Test that invalid file_specific_suppressions uses default."""
        config_file = tmp_path / ".cross_file_context_links.yml"
        config_file.write_text(
            """
file_specific_suppressions: "not_a_dict"
"""
        )

        config = Config(config_path=config_file)

        # Should use default (empty dict) when invalid
        assert config.file_specific_suppressions == {}
