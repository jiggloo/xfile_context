# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Pytest configuration parser for test module detection.

This module implements pytest configuration parsing (TDD Section 3.9.2, DD-3):
- Parse pytest.ini, pyproject.toml, setup.cfg, tox.ini
- Extract testpaths and python_files patterns
- Fall back to default patterns if config not found
- No runtime dependency on pytest (static parsing only)

Design Decision DD-3:
- Parse pytest configuration files statically
- Treat conftest.py as test infrastructure
- Enable accurate test vs source distinction for warning suppression

Related Requirements:
- DD-3 (Test File Detection)
- Section 3.9.2 (Test vs Source Module Detection)
- T-6.1 (test module identification)
"""

import configparser
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Python 3.11+ has tomllib built-in, earlier versions need tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore


class PytestConfig:
    """Pytest configuration parser.

    Parses pytest configuration files in order of precedence:
    1. pytest.ini
    2. pyproject.toml (section [tool.pytest.ini_options])
    3. setup.cfg (section [tool:pytest])
    4. tox.ini (section [pytest])

    Extracts:
    - testpaths: Directories containing tests
    - python_files: File patterns for test modules

    Falls back to default patterns if no config found.

    Security limits:
    - Max config file size: 10MB
    - Max testpaths: 100
    - Max python_files: 50
    - Max pattern length: 500 characters
    """

    # Default patterns from TDD Section 3.9.2
    DEFAULT_TEST_PATHS: List[str] = ["tests"]
    DEFAULT_PYTHON_FILES: List[str] = ["test_*.py", "*_test.py"]
    DEFAULT_CONFTEST_PATTERN: str = "**/conftest.py"
    DEFAULT_TESTS_DIR_PATTERN: str = "**/tests/**/*.py"

    # Security limits to prevent resource exhaustion
    MAX_CONFIG_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    MAX_TESTPATHS: int = 100
    MAX_PYTHON_FILES: int = 50
    MAX_PATTERN_LENGTH: int = 500

    def __init__(self, project_root: Path):
        """Initialize pytest config parser.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = project_root
        self.testpaths: List[str] = []
        self.python_files: List[str] = []
        self._loaded = False

    def load(self) -> None:
        """Load pytest configuration from available config files.

        Tries config files in order of precedence. Stops at first valid config.
        Falls back to defaults if no config found or parsing fails.

        Security: Validates file size before parsing to prevent resource exhaustion.
        """
        if self._loaded:
            return

        self._loaded = True

        # Try each config file in order of precedence
        config_loaders = [
            (self.project_root / "pytest.ini", self._load_pytest_ini),
            (self.project_root / "pyproject.toml", self._load_pyproject_toml),
            (self.project_root / "setup.cfg", self._load_setup_cfg),
            (self.project_root / "tox.ini", self._load_tox_ini),
        ]

        for config_path, loader_func in config_loaders:
            if config_path.exists():
                # Security: Check file size before parsing
                if not self._validate_file_size(config_path):
                    logger.warning(
                        f"Config file {config_path} exceeds size limit "
                        f"({self.MAX_CONFIG_FILE_SIZE} bytes), skipping"
                    )
                    continue

                try:
                    if loader_func(config_path):
                        logger.info(f"Loaded pytest config from {config_path}")
                        return
                except Exception as e:
                    logger.warning(f"Failed to parse {config_path}: {e}")
                    continue

        # No valid config found, use defaults
        logger.info("No pytest config found, using default patterns")
        self.testpaths = self.DEFAULT_TEST_PATHS.copy()
        self.python_files = self.DEFAULT_PYTHON_FILES.copy()

    def _validate_file_size(self, config_path: Path) -> bool:
        """Validate config file size to prevent resource exhaustion.

        Args:
            config_path: Path to config file

        Returns:
            True if file size is within limits, False otherwise
        """
        try:
            file_size = config_path.stat().st_size
            return file_size <= self.MAX_CONFIG_FILE_SIZE
        except OSError as e:
            logger.warning(f"Failed to check file size for {config_path}: {e}")
            return False

    def _load_pytest_ini(self, config_path: Path) -> bool:
        """Load configuration from pytest.ini.

        Args:
            config_path: Path to pytest.ini

        Returns:
            True if successfully loaded, False otherwise
        """
        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")

        if not parser.has_section("pytest"):
            return False

        return self._extract_config_values(parser, "pytest")

    def _load_pyproject_toml(self, config_path: Path) -> bool:
        """Load configuration from pyproject.toml.

        Args:
            config_path: Path to pyproject.toml

        Returns:
            True if successfully loaded, False otherwise
        """
        if tomllib is None:
            logger.warning(
                "tomli library not available for Python < 3.11, cannot parse pyproject.toml"
            )
            return False

        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        # Look for [tool.pytest.ini_options] section
        pytest_config = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
        if not pytest_config:
            return False

        return self._extract_from_dict(pytest_config)

    def _load_setup_cfg(self, config_path: Path) -> bool:
        """Load configuration from setup.cfg.

        Args:
            config_path: Path to setup.cfg

        Returns:
            True if successfully loaded, False otherwise
        """
        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")

        if not parser.has_section("tool:pytest"):
            return False

        return self._extract_config_values(parser, "tool:pytest")

    def _load_tox_ini(self, config_path: Path) -> bool:
        """Load configuration from tox.ini.

        Args:
            config_path: Path to tox.ini

        Returns:
            True if successfully loaded, False otherwise
        """
        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")

        if not parser.has_section("pytest"):
            return False

        return self._extract_config_values(parser, "pytest")

    def _extract_config_values(self, parser: configparser.ConfigParser, section: str) -> bool:
        """Extract testpaths and python_files from ConfigParser.

        Args:
            parser: ConfigParser instance
            section: Section name to read from

        Returns:
            True if any values extracted, False otherwise
        """
        found_any = False

        if parser.has_option(section, "testpaths"):
            testpaths_str = parser.get(section, "testpaths")
            testpaths = [p.strip() for p in testpaths_str.split()]
            self.testpaths = self._validate_patterns(
                testpaths, self.MAX_TESTPATHS, "testpaths", self.DEFAULT_TEST_PATHS
            )
            found_any = True
        else:
            self.testpaths = self.DEFAULT_TEST_PATHS.copy()

        if parser.has_option(section, "python_files"):
            python_files_str = parser.get(section, "python_files")
            python_files = [p.strip() for p in python_files_str.split()]
            self.python_files = self._validate_patterns(
                python_files, self.MAX_PYTHON_FILES, "python_files", self.DEFAULT_PYTHON_FILES
            )
            found_any = True
        else:
            self.python_files = self.DEFAULT_PYTHON_FILES.copy()

        return found_any

    def _extract_from_dict(self, config_dict: Dict[str, Any]) -> bool:
        """Extract testpaths and python_files from dictionary (TOML).

        Args:
            config_dict: Dictionary containing pytest config

        Returns:
            True if any values extracted, False otherwise
        """
        found_any = False

        if "testpaths" in config_dict:
            testpaths = config_dict["testpaths"]
            if isinstance(testpaths, list):
                # Validate all elements are strings
                if all(isinstance(p, str) for p in testpaths):
                    self.testpaths = self._validate_patterns(
                        testpaths, self.MAX_TESTPATHS, "testpaths", self.DEFAULT_TEST_PATHS
                    )
                    found_any = True
                else:
                    logger.warning("testpaths contains non-string values, using defaults")
                    self.testpaths = self.DEFAULT_TEST_PATHS.copy()
            elif isinstance(testpaths, str):
                testpaths_list = [p.strip() for p in testpaths.split()]
                self.testpaths = self._validate_patterns(
                    testpaths_list, self.MAX_TESTPATHS, "testpaths", self.DEFAULT_TEST_PATHS
                )
                found_any = True
        else:
            self.testpaths = self.DEFAULT_TEST_PATHS.copy()

        if "python_files" in config_dict:
            python_files = config_dict["python_files"]
            if isinstance(python_files, list):
                # Validate all elements are strings
                if all(isinstance(p, str) for p in python_files):
                    self.python_files = self._validate_patterns(
                        python_files,
                        self.MAX_PYTHON_FILES,
                        "python_files",
                        self.DEFAULT_PYTHON_FILES,
                    )
                    found_any = True
                else:
                    logger.warning("python_files contains non-string values, using defaults")
                    self.python_files = self.DEFAULT_PYTHON_FILES.copy()
            elif isinstance(python_files, str):
                python_files_list = [p.strip() for p in python_files.split()]
                self.python_files = self._validate_patterns(
                    python_files_list,
                    self.MAX_PYTHON_FILES,
                    "python_files",
                    self.DEFAULT_PYTHON_FILES,
                )
                found_any = True
        else:
            self.python_files = self.DEFAULT_PYTHON_FILES.copy()

        return found_any

    def _validate_patterns(
        self, patterns: List[str], max_count: int, pattern_type: str, default: List[str]
    ) -> List[str]:
        """Validate patterns for security limits.

        Args:
            patterns: List of patterns to validate
            max_count: Maximum number of patterns allowed
            pattern_type: Type of patterns (for logging)
            default: Default patterns to use if all patterns filtered out

        Returns:
            Validated list of patterns (truncated if needed), or default if empty
        """
        validated = []

        for i, pattern in enumerate(patterns):
            # Check count limit
            if i >= max_count:
                logger.warning(f"{pattern_type} exceeds limit of {max_count}, truncating")
                break

            # Check pattern length
            if len(pattern) > self.MAX_PATTERN_LENGTH:
                logger.warning(
                    f"{pattern_type} pattern exceeds length limit "
                    f"({self.MAX_PATTERN_LENGTH} chars), skipping: {pattern[:50]}..."
                )
                continue

            # Check for path traversal patterns
            if ".." in pattern or pattern.startswith("/"):
                logger.warning(
                    f"{pattern_type} pattern contains unsafe characters, skipping: {pattern}"
                )
                continue

            validated.append(pattern)

        return validated if validated else default.copy()

    def get_test_patterns(self) -> List[str]:
        """Get all test file patterns.

        Combines:
        - python_files patterns from config (e.g., test_*.py)
        - testpaths directory patterns (e.g., tests/**/*.py)
        - conftest.py pattern (always included)

        Returns:
            List of glob patterns for test files
        """
        if not self._loaded:
            self.load()

        patterns = []

        # Add python_files patterns with ** prefix for any directory
        for pattern in self.python_files:
            if not pattern.startswith("**/"):
                patterns.append(f"**/{pattern}")
            else:
                patterns.append(pattern)

        # Add testpaths directory patterns
        for testpath in self.testpaths:
            patterns.append(f"{testpath}/**/*.py")
            patterns.append(f"**/{testpath}/**/*.py")  # Match in subdirectories too

        # Always include conftest.py
        patterns.append(self.DEFAULT_CONFTEST_PATTERN)

        return patterns


def is_test_module(file_path: str, project_root: Optional[str] = None) -> bool:
    """Check if a file is a test module.

    Uses pytest configuration if available, otherwise falls back to default patterns.

    Implementation follows TDD Section 3.9.2:
    - Approach 2: Pytest Configuration Parsing (if config available)
    - Approach 1: Pattern Matching (fallback)

    Args:
        file_path: Path to file (absolute or relative)
        project_root: Project root directory (optional, defaults to cwd)

    Returns:
        True if file is a test module, False otherwise
    """
    from fnmatch import fnmatch

    path = Path(file_path)
    path_str = str(path)
    path_parts = path.parts

    # Load pytest config if project root provided
    if project_root:
        root = Path(project_root)
        config = PytestConfig(root)
        config.load()
        patterns = config.get_test_patterns()
    else:
        # Use default patterns
        patterns = [
            "**/test_*.py",
            "**/*_test.py",
            "**/tests/**/*.py",
            "**/conftest.py",
        ]

    # Check if file matches any pattern
    for pattern in patterns:
        # Handle **/ prefix patterns (match in any directory)
        if pattern.startswith("**/"):
            remaining_pattern = pattern[3:]  # Remove **/

            # Check if it's a directory pattern like tests/**/*.py
            if "/**/" in remaining_pattern:
                # Extract directory name before /**/
                dir_name = remaining_pattern.split("/**/")[0]
                # Check if this directory appears anywhere in the path
                if dir_name in path_parts and path.suffix == ".py":
                    return True

            # Check against filename only
            if fnmatch(path.name, remaining_pattern):
                return True
        else:
            # Pattern without **/ prefix, check directly
            if fnmatch(path_str, pattern) or fnmatch(path.name, pattern):
                return True

    return False
