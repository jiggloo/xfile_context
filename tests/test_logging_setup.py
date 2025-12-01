# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Tests for logging setup."""

import json
import logging
import tempfile
from pathlib import Path

from xfile_context.logging_setup import StructuredFormatter, get_metrics_logger, setup_logging


def test_setup_logging_creates_directory():
    """Test that setup_logging creates the log directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / ".cross_file_context_logs"
        assert not log_dir.exists()

        setup_logging(log_dir=log_dir, console_output=False)

        assert log_dir.exists()
        assert log_dir.is_dir()


def test_setup_logging_creates_log_file():
    """Test that setup_logging creates a log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / ".cross_file_context_logs"

        setup_logging(log_dir=log_dir, console_output=False)

        # Check that at least one log file was created
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) == 1


def test_logging_produces_json():
    """Test that logs are written in JSON format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / ".cross_file_context_logs"

        setup_logging(log_dir=log_dir, log_level=logging.INFO, console_output=False)

        # Log a message
        logger = logging.getLogger("test_logger")
        logger.info("Test message")

        # Read the log file
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) == 1

        log_content = log_files[0].read_text()
        log_lines = [line for line in log_content.strip().split("\n") if line]

        # Should have at least 2 lines (startup message + test message)
        assert len(log_lines) >= 2

        # Verify JSON format
        for line in log_lines:
            log_entry = json.loads(line)
            assert "timestamp" in log_entry
            assert "level" in log_entry
            assert "logger" in log_entry
            assert "message" in log_entry


def test_logging_levels():
    """Test that different log levels work correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / ".cross_file_context_logs"

        setup_logging(log_dir=log_dir, log_level=logging.WARNING, console_output=False)

        logger = logging.getLogger("test_logger")
        logger.debug("Debug message")  # Should not be logged
        logger.info("Info message")  # Should not be logged
        logger.warning("Warning message")  # Should be logged
        logger.error("Error message")  # Should be logged

        log_files = list(log_dir.glob("*.log"))
        log_content = log_files[0].read_text()
        log_lines = [line for line in log_content.strip().split("\n") if line]

        # Should have startup message + warning + error (3 lines)
        # Startup is logged at INFO, but it comes from root logger setup
        messages = [json.loads(line)["message"] for line in log_lines]

        assert "Warning message" in messages
        assert "Error message" in messages
        assert "Debug message" not in messages
        assert "Info message" not in messages


def test_structured_formatter_with_exception():
    """Test that exceptions are formatted correctly."""
    formatter = StructuredFormatter()

    try:
        raise ValueError("Test exception")
    except ValueError:
        import sys

        exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="An error occurred",
            args=(),
            exc_info=exc_info,
        )

        formatted = formatter.format(record)
        log_entry = json.loads(formatted)

        assert log_entry["level"] == "ERROR"
        assert log_entry["message"] == "An error occurred"
        assert "exception" in log_entry
        assert "ValueError: Test exception" in log_entry["exception"]


def test_metrics_logger_separate_file():
    """Test that metrics logger writes to separate file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / ".cross_file_context_logs"

        metrics_logger = get_metrics_logger(log_dir=log_dir)
        metrics_logger.info("Test metrics entry")

        # Check metrics file exists
        metrics_file = log_dir / "session_metrics.jsonl"
        assert metrics_file.exists()

        # Verify content
        content = metrics_file.read_text()
        log_entry = json.loads(content.strip())

        assert log_entry["message"] == "Test metrics entry"


def test_metrics_logger_no_propagation():
    """Test that metrics logger doesn't propagate to root logger."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / ".cross_file_context_logs"

        # Set up both loggers
        setup_logging(log_dir=log_dir, console_output=False)
        metrics_logger = get_metrics_logger(log_dir=log_dir)

        # Log a metrics message
        metrics_logger.info("Metrics message")

        # Check that metrics message is only in metrics file
        log_files = list(log_dir.glob("xfile_context_*.log"))
        if log_files:
            main_log_content = log_files[0].read_text()
            # Metrics message should NOT appear in main log
            assert "Metrics message" not in main_log_content

        # But should be in metrics file
        metrics_file = log_dir / "session_metrics.jsonl"
        metrics_content = metrics_file.read_text()
        assert "Metrics message" in metrics_content


def test_setup_logging_clears_existing_handlers():
    """Test that setup_logging clears existing handlers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / ".cross_file_context_logs"

        # Set up logging twice
        setup_logging(log_dir=log_dir, console_output=False)
        initial_handler_count = len(logging.getLogger().handlers)

        setup_logging(log_dir=log_dir, console_output=False)
        final_handler_count = len(logging.getLogger().handlers)

        # Should have same number of handlers (not doubled)
        assert final_handler_count == initial_handler_count


def test_console_output_option():
    """Test that console output can be enabled/disabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / ".cross_file_context_logs"

        # With console output
        setup_logging(log_dir=log_dir, console_output=True)
        handlers_with_console = logging.getLogger().handlers
        assert len(handlers_with_console) == 2  # File + Console

        # Without console output
        setup_logging(log_dir=log_dir, console_output=False)
        handlers_without_console = logging.getLogger().handlers
        assert len(handlers_without_console) == 1  # File only
