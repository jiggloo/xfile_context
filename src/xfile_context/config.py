# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Configuration loading and validation for Cross-File Context Links."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration validation fails critically."""

    pass


class Config:
    """Configuration for Cross-File Context Links MCP Server.

    Loads configuration from .cross_file_context_links.yml with validation and defaults.
    """

    # Default configuration values (from TDD Section 3.10.5)
    DEFAULTS = {
        "cache_expiry_minutes": 10,
        "cache_size_limit_kb": 50,
        "context_token_limit": 500,
        "enable_context_injection": True,
        "warn_on_wildcards": False,
        "suppress_warnings": [],
        "suppress_dynamic_dispatch_warnings": False,
        "suppress_monkey_patching_warnings": False,
        "suppress_exec_eval_warnings": False,
        "suppress_decorator_warnings": False,
        "suppress_metaclass_warnings": False,
        "suppress_circular_import_warnings": False,
        "file_specific_suppressions": {},
        "ignore_patterns": [],
        "function_usage_warning_threshold": 3,
        "metrics_anonymize_paths": False,
        "enable_injection_logging": True,
        "enable_warning_logging": True,
        # Symbol cache configuration (Issue #125 Phase 3)
        # Note: Two-phase analysis is always enabled (Issue #133 fix requirement)
        "symbol_cache_max_entries": 1000,  # Maximum cached files
    }

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration.

        Args:
            config_path: Path to configuration file. If None, uses default location.
        """
        if config_path is None:
            config_path = Path.cwd() / ".cross_file_context_links.yml"

        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load and validate configuration from file."""
        if not self.config_path.exists():
            logger.info(f"Configuration file not found at {self.config_path}, using defaults")
            self._config = self.DEFAULTS.copy()
            return

        try:
            with open(self.config_path, encoding="utf-8") as f:
                loaded_config = yaml.safe_load(f)

            if loaded_config is None:
                logger.warning("Configuration file is empty, using defaults")
                self._config = self.DEFAULTS.copy()
                return

            if not isinstance(loaded_config, dict):
                logger.warning(
                    f"Configuration file must contain a YAML dictionary, "
                    f"got {type(loaded_config)}, using defaults"
                )
                self._config = self.DEFAULTS.copy()
                return

            # Start with defaults and override with loaded values
            self._config = self.DEFAULTS.copy()
            self._validate_and_merge(loaded_config)

        except yaml.YAMLError as e:
            logger.warning(
                f"Error parsing configuration file {self.config_path}: {e}, using defaults"
            )
            self._config = self.DEFAULTS.copy()
        except Exception as e:
            logger.warning(
                f"Unexpected error loading configuration file "
                f"{self.config_path}: {e}, using defaults"
            )
            self._config = self.DEFAULTS.copy()

    def _validate_and_merge(self, loaded_config: Dict[str, Any]) -> None:
        """Validate loaded configuration and merge with defaults.

        Invalid parameters are logged as warnings and defaults are used.
        """
        for key, value in loaded_config.items():
            if key not in self.DEFAULTS:
                logger.warning(f"Unknown configuration parameter '{key}', ignoring")
                continue

            # Validate based on parameter type and constraints
            if not self._validate_parameter(key, value):
                logger.warning(
                    f"Invalid value for '{key}': {value}, using default {self.DEFAULTS[key]}"
                )
                continue

            self._config[key] = value

    def _validate_parameter(self, key: str, value: Any) -> bool:
        """Validate a configuration parameter.

        Returns:
            True if valid, False if invalid
        """
        # Type validation
        expected_type = type(self.DEFAULTS[key])
        if not isinstance(value, expected_type):
            return False

        # Range validation for numeric parameters
        if key == "cache_expiry_minutes" or key == "cache_size_limit_kb":
            return bool(isinstance(value, int) and value > 0)
        elif key == "context_token_limit":
            return bool(isinstance(value, int) and 0 < value < 10000)  # Sanity check from TDD
        elif key in ("function_usage_warning_threshold", "symbol_cache_max_entries"):
            return bool(isinstance(value, int) and value > 0)
        elif key in ["suppress_warnings", "ignore_patterns"]:
            # Must be a list
            return isinstance(value, list)
        elif key == "file_specific_suppressions":
            # Must be a dict with string keys and list of string values
            if not isinstance(value, dict):
                return False
            for filepath, pattern_types in value.items():
                if not isinstance(filepath, str):
                    return False
                if not isinstance(pattern_types, list):
                    return False
                # Validate that all pattern types are strings
                if not all(isinstance(pt, str) for pt in pattern_types):
                    return False
            return True

        return True

    # Property accessors for all configuration values
    @property
    def cache_expiry_minutes(self) -> int:
        """Cache expiry time in minutes."""
        value = self._config["cache_expiry_minutes"]
        assert isinstance(value, int)
        return value

    @property
    def cache_size_limit_kb(self) -> int:
        """Cache size limit in kilobytes."""
        value = self._config["cache_size_limit_kb"]
        assert isinstance(value, int)
        return value

    @property
    def context_token_limit(self) -> int:
        """Maximum tokens for context injection."""
        value = self._config["context_token_limit"]
        assert isinstance(value, int)
        return value

    @property
    def enable_context_injection(self) -> bool:
        """Whether context injection is enabled."""
        value = self._config["enable_context_injection"]
        assert isinstance(value, bool)
        return value

    @property
    def warn_on_wildcards(self) -> bool:
        """Whether to warn on wildcard imports."""
        value = self._config["warn_on_wildcards"]
        assert isinstance(value, bool)
        return value

    @property
    def suppress_warnings(self) -> List[str]:
        """File/directory patterns to suppress warnings for."""
        value = self._config["suppress_warnings"]
        assert isinstance(value, list)
        return value

    @property
    def suppress_dynamic_dispatch_warnings(self) -> bool:
        """Whether to suppress dynamic dispatch warnings."""
        value = self._config["suppress_dynamic_dispatch_warnings"]
        assert isinstance(value, bool)
        return value

    @property
    def suppress_monkey_patching_warnings(self) -> bool:
        """Whether to suppress monkey patching warnings."""
        value = self._config["suppress_monkey_patching_warnings"]
        assert isinstance(value, bool)
        return value

    @property
    def suppress_exec_eval_warnings(self) -> bool:
        """Whether to suppress exec/eval warnings."""
        value = self._config["suppress_exec_eval_warnings"]
        assert isinstance(value, bool)
        return value

    @property
    def suppress_decorator_warnings(self) -> bool:
        """Whether to suppress decorator warnings."""
        value = self._config["suppress_decorator_warnings"]
        assert isinstance(value, bool)
        return value

    @property
    def suppress_metaclass_warnings(self) -> bool:
        """Whether to suppress metaclass warnings."""
        value = self._config["suppress_metaclass_warnings"]
        assert isinstance(value, bool)
        return value

    @property
    def suppress_circular_import_warnings(self) -> bool:
        """Whether to suppress circular import warnings."""
        value = self._config["suppress_circular_import_warnings"]
        assert isinstance(value, bool)
        return value

    @property
    def file_specific_suppressions(self) -> Dict[str, List[str]]:
        """Per-file pattern-type suppressions.

        Returns:
            Dictionary mapping file paths to list of suppressed pattern types.
            Example: {"src/utils.py": ["dynamic_dispatch", "decorator"]}
        """
        value = self._config["file_specific_suppressions"]
        assert isinstance(value, dict)
        return value

    @property
    def ignore_patterns(self) -> List[str]:
        """Additional file patterns to ignore beyond .gitignore."""
        value = self._config["ignore_patterns"]
        assert isinstance(value, list)
        return value

    @property
    def function_usage_warning_threshold(self) -> int:
        """Threshold for function usage warnings."""
        value = self._config["function_usage_warning_threshold"]
        assert isinstance(value, int)
        return value

    @property
    def metrics_anonymize_paths(self) -> bool:
        """Whether to anonymize file paths in metrics."""
        value = self._config["metrics_anonymize_paths"]
        assert isinstance(value, bool)
        return value

    @property
    def enable_injection_logging(self) -> bool:
        """Whether context injection logging is enabled."""
        value = self._config["enable_injection_logging"]
        assert isinstance(value, bool)
        return value

    @property
    def enable_warning_logging(self) -> bool:
        """Whether warning logging is enabled."""
        value = self._config["enable_warning_logging"]
        assert isinstance(value, bool)
        return value

    @property
    def symbol_cache_max_entries(self) -> int:
        """Maximum number of files to cache symbol data for.

        When the cache reaches this limit, least recently used entries
        are evicted to make room for new entries.

        Default is 1000 files.
        """
        value = self._config["symbol_cache_max_entries"]
        assert isinstance(value, int)
        return value
