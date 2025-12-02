# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for pytest configuration parser.

Test coverage (TDD Section 3.9.2, DD-3):
- Parsing each config file format (pytest.ini, pyproject.toml, setup.cfg, tox.ini)
- Extracting testpaths and python_files correctly
- Test module classification with various file paths
- Fallback to default patterns when no config exists
- Edge cases: malformed configs, missing sections, invalid patterns
- Integration: T-6.1 (test module identification)
"""

from pathlib import Path

from xfile_context.pytest_config_parser import PytestConfig, is_test_module


class TestPytestConfigParser:
    """Test suite for PytestConfig class."""

    def test_no_config_files_uses_defaults(self, tmp_path: Path) -> None:
        """Test that default patterns are used when no config files exist."""
        config = PytestConfig(tmp_path)
        config.load()

        assert config.testpaths == PytestConfig.DEFAULT_TEST_PATHS
        assert config.python_files == PytestConfig.DEFAULT_PYTHON_FILES

    def test_pytest_ini_parsing(self, tmp_path: Path) -> None:
        """Test parsing pytest.ini file."""
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text(
            """[pytest]
testpaths = tests integration_tests
python_files = test_*.py check_*.py
"""
        )

        config = PytestConfig(tmp_path)
        config.load()

        assert config.testpaths == ["tests", "integration_tests"]
        assert config.python_files == ["test_*.py", "check_*.py"]

    def test_pytest_ini_partial_config(self, tmp_path: Path) -> None:
        """Test pytest.ini with only testpaths (python_files should use default)."""
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text(
            """[pytest]
testpaths = tests
"""
        )

        config = PytestConfig(tmp_path)
        config.load()

        assert config.testpaths == ["tests"]
        assert config.python_files == PytestConfig.DEFAULT_PYTHON_FILES

    def test_pyproject_toml_parsing(self, tmp_path: Path) -> None:
        """Test parsing pyproject.toml file."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """[tool.pytest.ini_options]
testpaths = ["tests", "integration"]
python_files = ["test_*.py", "*_test.py"]
"""
        )

        config = PytestConfig(tmp_path)
        config.load()

        assert config.testpaths == ["tests", "integration"]
        assert config.python_files == ["test_*.py", "*_test.py"]

    def test_pyproject_toml_string_values(self, tmp_path: Path) -> None:
        """Test pyproject.toml with string values (space-separated)."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """[tool.pytest.ini_options]
testpaths = "tests integration"
python_files = "test_*.py *_test.py"
"""
        )

        config = PytestConfig(tmp_path)
        config.load()

        assert config.testpaths == ["tests", "integration"]
        assert config.python_files == ["test_*.py", "*_test.py"]

    def test_setup_cfg_parsing(self, tmp_path: Path) -> None:
        """Test parsing setup.cfg file."""
        setup_cfg = tmp_path / "setup.cfg"
        setup_cfg.write_text(
            """[tool:pytest]
testpaths = tests unit_tests
python_files = test_*.py
"""
        )

        config = PytestConfig(tmp_path)
        config.load()

        assert config.testpaths == ["tests", "unit_tests"]
        assert config.python_files == ["test_*.py"]

    def test_tox_ini_parsing(self, tmp_path: Path) -> None:
        """Test parsing tox.ini file."""
        tox_ini = tmp_path / "tox.ini"
        tox_ini.write_text(
            """[pytest]
testpaths = tests
python_files = test_*.py check_*.py
"""
        )

        config = PytestConfig(tmp_path)
        config.load()

        assert config.testpaths == ["tests"]
        assert config.python_files == ["test_*.py", "check_*.py"]

    def test_config_precedence_pytest_ini_wins(self, tmp_path: Path) -> None:
        """Test that pytest.ini takes precedence over other config files."""
        # Create multiple config files
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text(
            """[pytest]
testpaths = from_pytest_ini
"""
        )

        setup_cfg = tmp_path / "setup.cfg"
        setup_cfg.write_text(
            """[tool:pytest]
testpaths = from_setup_cfg
"""
        )

        config = PytestConfig(tmp_path)
        config.load()

        # Should use pytest.ini
        assert config.testpaths == ["from_pytest_ini"]

    def test_malformed_config_falls_back_to_next(self, tmp_path: Path) -> None:
        """Test that malformed config falls back to next config file."""
        # Create malformed pytest.ini (wrong section name)
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text(
            """[wrong_section]
testpaths = should_not_be_used
"""
        )

        # Create valid setup.cfg
        setup_cfg = tmp_path / "setup.cfg"
        setup_cfg.write_text(
            """[tool:pytest]
testpaths = from_setup_cfg
"""
        )

        config = PytestConfig(tmp_path)
        config.load()

        # Should skip pytest.ini and use setup.cfg
        assert config.testpaths == ["from_setup_cfg"]

    def test_get_test_patterns(self, tmp_path: Path) -> None:
        """Test that get_test_patterns returns correct glob patterns."""
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text(
            """[pytest]
testpaths = tests custom_tests
python_files = test_*.py check_*.py
"""
        )

        config = PytestConfig(tmp_path)
        patterns = config.get_test_patterns()

        # Should include python_files patterns with **/ prefix
        assert "**/test_*.py" in patterns
        assert "**/check_*.py" in patterns

        # Should include testpaths patterns
        assert "tests/**/*.py" in patterns
        assert "custom_tests/**/*.py" in patterns
        assert "**/tests/**/*.py" in patterns
        assert "**/custom_tests/**/*.py" in patterns

        # Should always include conftest.py
        assert "**/conftest.py" in patterns

    def test_get_test_patterns_with_wildcard_prefix(self, tmp_path: Path) -> None:
        """Test that patterns already with **/ are not duplicated."""
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text(
            """[pytest]
python_files = **/test_*.py
"""
        )

        config = PytestConfig(tmp_path)
        patterns = config.get_test_patterns()

        # Should not add another **/ prefix
        count = sum(1 for p in patterns if p == "**/test_*.py")
        assert count == 1  # Should appear exactly once

    def test_empty_config_file(self, tmp_path: Path) -> None:
        """Test handling of empty config file."""
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text("")

        config = PytestConfig(tmp_path)
        config.load()

        # Should fall back to defaults
        assert config.testpaths == PytestConfig.DEFAULT_TEST_PATHS
        assert config.python_files == PytestConfig.DEFAULT_PYTHON_FILES

    def test_invalid_toml_syntax(self, tmp_path: Path) -> None:
        """Test handling of invalid TOML syntax."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            """[tool.pytest.ini_options
# Missing closing bracket - invalid TOML
testpaths = ["tests"]
"""
        )

        config = PytestConfig(tmp_path)
        config.load()

        # Should fall back to defaults due to parsing error
        assert config.testpaths == PytestConfig.DEFAULT_TEST_PATHS
        assert config.python_files == PytestConfig.DEFAULT_PYTHON_FILES

    def test_load_only_once(self, tmp_path: Path) -> None:
        """Test that config is only loaded once even if load() called multiple times."""
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text(
            """[pytest]
testpaths = tests
"""
        )

        config = PytestConfig(tmp_path)
        config.load()
        first_testpaths = config.testpaths

        # Modify config file
        pytest_ini.write_text(
            """[pytest]
testpaths = different_tests
"""
        )

        # Call load() again - should not reload
        config.load()

        # Should still have first values
        assert config.testpaths == first_testpaths


class TestIsTestModule:
    """Test suite for is_test_module function (T-6.1)."""

    def test_default_pattern_test_prefix(self) -> None:
        """Test detection of test_*.py pattern."""
        assert is_test_module("test_foo.py")
        assert is_test_module("tests/test_foo.py")
        assert is_test_module("/path/to/tests/test_foo.py")

    def test_default_pattern_test_suffix(self) -> None:
        """Test detection of *_test.py pattern."""
        assert is_test_module("foo_test.py")
        assert is_test_module("tests/foo_test.py")
        assert is_test_module("/path/to/tests/foo_test.py")

    def test_default_pattern_tests_directory(self) -> None:
        """Test detection of files in tests/ directory."""
        assert is_test_module("tests/foo.py")
        assert is_test_module("tests/bar/baz.py")
        assert is_test_module("/path/to/tests/anything.py")

    def test_default_pattern_conftest(self) -> None:
        """Test detection of conftest.py."""
        assert is_test_module("conftest.py")
        assert is_test_module("tests/conftest.py")
        assert is_test_module("/path/to/tests/conftest.py")

    def test_not_test_module(self) -> None:
        """Test that non-test files are not detected as test modules."""
        assert not is_test_module("foo.py")
        assert not is_test_module("src/foo.py")
        assert not is_test_module("lib/utils.py")
        assert not is_test_module("main.py")

    def test_with_project_root_and_custom_config(self, tmp_path: Path) -> None:
        """Test is_test_module with custom pytest config."""
        # Create custom config
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text(
            """[pytest]
testpaths = custom_tests
python_files = check_*.py
"""
        )

        # Should match custom patterns
        assert is_test_module("check_foo.py", project_root=str(tmp_path))
        assert is_test_module("custom_tests/foo.py", project_root=str(tmp_path))

        # Default patterns should also work (conftest always included)
        assert is_test_module("conftest.py", project_root=str(tmp_path))

    def test_with_project_root_no_config(self, tmp_path: Path) -> None:
        """Test is_test_module with project root but no config (uses defaults)."""
        assert is_test_module("test_foo.py", project_root=str(tmp_path))
        assert is_test_module("tests/foo.py", project_root=str(tmp_path))
        assert not is_test_module("src/foo.py", project_root=str(tmp_path))

    def test_pathlib_path_input(self, tmp_path: Path) -> None:
        """Test is_test_module with Path object input."""
        test_file = tmp_path / "test_foo.py"
        assert is_test_module(str(test_file))

    def test_relative_path(self) -> None:
        """Test is_test_module with relative paths."""
        assert is_test_module("./tests/test_foo.py")
        assert is_test_module("../tests/test_foo.py")
        assert is_test_module("tests/subdir/test_foo.py")

    def test_nested_tests_directory(self) -> None:
        """Test detection of nested tests directories."""
        assert is_test_module("src/tests/test_foo.py")
        assert is_test_module("lib/submodule/tests/foo.py")
        assert is_test_module("deeply/nested/tests/anything.py")

    def test_integration_t61(self, tmp_path: Path) -> None:
        """Integration test T-6.1: Test module identification.

        Validates that test module detection works correctly with:
        - Default patterns
        - Custom pytest configuration
        - Various file path formats
        """
        # Create pytest config with custom patterns
        pytest_ini = tmp_path / "pytest.ini"
        pytest_ini.write_text(
            """[pytest]
testpaths = tests integration_tests
python_files = test_*.py *_test.py check_*.py
"""
        )

        # Test files that should be detected
        test_cases_positive = [
            "test_foo.py",
            "foo_test.py",
            "check_bar.py",
            "tests/anything.py",
            "integration_tests/something.py",
            "tests/subdir/file.py",
            "conftest.py",
        ]

        for test_file in test_cases_positive:
            assert is_test_module(
                test_file, project_root=str(tmp_path)
            ), f"Expected {test_file} to be detected as test module"

        # Files that should NOT be detected
        test_cases_negative = [
            "src/main.py",
            "lib/utils.py",
            "setup.py",
            "not_tests/foo.py",
        ]

        for test_file in test_cases_negative:
            assert not is_test_module(
                test_file, project_root=str(tmp_path)
            ), f"Expected {test_file} NOT to be detected as test module"
