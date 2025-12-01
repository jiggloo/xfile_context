# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for configuration loading and validation."""

import tempfile
from pathlib import Path

import yaml

from xfile_context.config import Config


def test_default_config_when_file_missing():
    """Test that defaults are used when config file is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "nonexistent.yml"
        config = Config(config_path=config_path)

        # Check all defaults
        assert config.cache_expiry_minutes == 10
        assert config.cache_size_limit_kb == 50
        assert config.context_token_limit == 500
        assert config.enable_context_injection is True
        assert config.warn_on_wildcards is False
        assert config.suppress_warnings == []
        assert config.function_usage_warning_threshold == 3


def test_valid_config_loading():
    """Test loading a valid configuration file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yml"
        config_data = {
            "cache_expiry_minutes": 20,
            "cache_size_limit_kb": 100,
            "context_token_limit": 1000,
            "enable_context_injection": False,
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = Config(config_path=config_path)

        assert config.cache_expiry_minutes == 20
        assert config.cache_size_limit_kb == 100
        assert config.context_token_limit == 1000
        assert config.enable_context_injection is False
        # Defaults for unspecified values
        assert config.warn_on_wildcards is False


def test_invalid_parameter_values():
    """Test that invalid parameter values are rejected and defaults used."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yml"
        config_data = {
            "cache_expiry_minutes": -5,  # Invalid: must be > 0
            "cache_size_limit_kb": 0,  # Invalid: must be > 0
            "context_token_limit": 20000,  # Invalid: must be < 10000
            "function_usage_warning_threshold": 0,  # Invalid: must be > 0
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = Config(config_path=config_path)

        # Should use defaults for invalid values
        assert config.cache_expiry_minutes == 10
        assert config.cache_size_limit_kb == 50
        assert config.context_token_limit == 500
        assert config.function_usage_warning_threshold == 3


def test_invalid_parameter_types():
    """Test that invalid parameter types are rejected and defaults used."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yml"
        config_data = {
            "cache_expiry_minutes": "not_a_number",
            "enable_context_injection": "not_a_boolean",
            "suppress_warnings": "not_a_list",
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = Config(config_path=config_path)

        # Should use defaults for invalid types
        assert config.cache_expiry_minutes == 10
        assert config.enable_context_injection is True
        assert config.suppress_warnings == []


def test_unknown_parameters_ignored():
    """Test that unknown parameters are ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yml"
        config_data = {
            "cache_expiry_minutes": 15,
            "unknown_parameter": "some_value",
            "another_unknown": 123,
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = Config(config_path=config_path)

        # Known parameters should be loaded
        assert config.cache_expiry_minutes == 15
        # Unknown parameters should be ignored (no error)


def test_empty_config_file():
    """Test that an empty config file uses all defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yml"
        config_path.write_text("", encoding="utf-8")

        config = Config(config_path=config_path)

        assert config.cache_expiry_minutes == 10
        assert config.cache_size_limit_kb == 50


def test_invalid_yaml_syntax():
    """Test that invalid YAML syntax falls back to defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yml"
        config_path.write_text("invalid: yaml: syntax: here:", encoding="utf-8")

        config = Config(config_path=config_path)

        # Should use all defaults
        assert config.cache_expiry_minutes == 10
        assert config.context_token_limit == 500


def test_list_parameters():
    """Test that list parameters are handled correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yml"
        config_data = {
            "suppress_warnings": ["pattern1", "pattern2"],
            "ignore_patterns": ["*.generated.py", "vendor/**"],
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = Config(config_path=config_path)

        assert config.suppress_warnings == ["pattern1", "pattern2"]
        assert config.ignore_patterns == ["*.generated.py", "vendor/**"]


def test_boolean_suppression_flags():
    """Test all boolean suppression flags."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yml"
        config_data = {
            "suppress_dynamic_dispatch_warnings": True,
            "suppress_monkey_patching_warnings": True,
            "suppress_exec_eval_warnings": True,
            "suppress_decorator_warnings": True,
            "suppress_metaclass_warnings": True,
            "suppress_circular_import_warnings": True,
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = Config(config_path=config_path)

        assert config.suppress_dynamic_dispatch_warnings is True
        assert config.suppress_monkey_patching_warnings is True
        assert config.suppress_exec_eval_warnings is True
        assert config.suppress_decorator_warnings is True
        assert config.suppress_metaclass_warnings is True
        assert config.suppress_circular_import_warnings is True


def test_metrics_and_logging_flags():
    """Test metrics and logging configuration flags."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yml"
        config_data = {
            "metrics_anonymize_paths": True,
            "enable_injection_logging": False,
            "enable_warning_logging": False,
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = Config(config_path=config_path)

        assert config.metrics_anonymize_paths is True
        assert config.enable_injection_logging is False
        assert config.enable_warning_logging is False
