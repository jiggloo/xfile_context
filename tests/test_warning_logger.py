# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Unit tests for WarningLogger module.

Tests cover:
- JSONL file logging
- Real-time flush behavior
- Warning statistics generation
- Log file size monitoring
- Integration with WarningEmitter

Related Requirements:
- FR-41 (structured warning log)
- FR-44 (warning statistics in session metrics)
- T-6.9 (warnings logged to structured format)
"""

import json
from pathlib import Path
from unittest import mock

import pytest

from xfile_context.warning_formatter import StructuredWarning, WarningEmitter
from xfile_context.warning_logger import (
    DEFAULT_LOG_DIR,
    DEFAULT_WARNING_LOG_FILE,
    LOG_SIZE_WARNING_THRESHOLD_BYTES,
    WarningLogger,
    WarningStatistics,
    read_warnings_from_log,
)


@pytest.fixture
def temp_log_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for log files."""
    log_dir = tmp_path / "test_logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def sample_warning() -> StructuredWarning:
    """Create a sample StructuredWarning for testing."""
    return StructuredWarning(
        type="dynamic_dispatch",
        file="/project/src/module.py",
        line=42,
        severity="warning",
        pattern="getattr(obj, 'method')",
        message="Dynamic dispatch detected - relationship tracking unavailable",
        timestamp="2025-11-25T10:30:00.123Z",
        column=5,
        explanation="Consider using explicit function calls.",
        is_test_module=False,
        metadata={"object_name": "obj", "attribute_variable": "method"},
    )


@pytest.fixture
def sample_warnings() -> list[StructuredWarning]:
    """Create a list of sample warnings for testing."""
    return [
        StructuredWarning(
            type="dynamic_dispatch",
            file="/project/src/module.py",
            line=42,
            severity="warning",
            pattern="getattr(obj, 'method')",
            message="Dynamic dispatch detected",
            timestamp="2025-11-25T10:30:00.123Z",
        ),
        StructuredWarning(
            type="exec_eval",
            file="/project/src/module.py",
            line=100,
            severity="warning",
            pattern="exec(...)",
            message="exec/eval usage detected",
            timestamp="2025-11-25T10:30:01.456Z",
        ),
        StructuredWarning(
            type="monkey_patching",
            file="/project/src/utils.py",
            line=25,
            severity="warning",
            pattern="module.attr = replacement",
            message="Monkey patching detected",
            timestamp="2025-11-25T10:30:02.789Z",
        ),
    ]


class TestWarningLogger:
    """Test cases for WarningLogger class."""

    def test_init_default_values(self) -> None:
        """Test initialization with default values."""
        logger = WarningLogger()

        assert logger._log_dir == Path.cwd() / DEFAULT_LOG_DIR
        assert logger._log_file == DEFAULT_WARNING_LOG_FILE
        assert logger._size_warning_threshold == LOG_SIZE_WARNING_THRESHOLD_BYTES
        assert logger._warning_count == 0
        assert logger._file_handle is None

    def test_init_custom_values(self, temp_log_dir: Path) -> None:
        """Test initialization with custom values."""
        logger = WarningLogger(
            log_dir=temp_log_dir,
            log_file="custom.jsonl",
            size_warning_threshold=5000,
        )

        assert logger._log_dir == temp_log_dir
        assert logger._log_file == "custom.jsonl"
        assert logger._size_warning_threshold == 5000

    def test_log_single_warning(
        self, temp_log_dir: Path, sample_warning: StructuredWarning
    ) -> None:
        """Test logging a single warning to JSONL file."""
        logger = WarningLogger(log_dir=temp_log_dir)

        logger.log_warning(sample_warning)
        logger.close()

        # Verify file was created
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE
        assert log_path.exists()

        # Verify content
        content = log_path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 1

        # Verify JSON structure
        data = json.loads(lines[0])
        assert data["type"] == "dynamic_dispatch"
        assert data["file"] == "/project/src/module.py"
        assert data["line"] == 42
        assert data["severity"] == "warning"

    def test_log_multiple_warnings(
        self, temp_log_dir: Path, sample_warnings: list[StructuredWarning]
    ) -> None:
        """Test logging multiple warnings to JSONL file."""
        logger = WarningLogger(log_dir=temp_log_dir)

        logger.log_warnings(sample_warnings)
        logger.close()

        # Verify file content
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE
        content = log_path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 3

        # Verify each line is valid JSON
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["type"] == sample_warnings[i].type

    def test_log_warning_creates_directory(self, tmp_path: Path) -> None:
        """Test that log directory is created if it doesn't exist."""
        log_dir = tmp_path / "nested" / "logs"
        assert not log_dir.exists()

        logger = WarningLogger(log_dir=log_dir)
        logger.log_warning(
            StructuredWarning(
                type="test",
                file="/test.py",
                line=1,
                severity="warning",
                pattern="test",
                message="test",
                timestamp="2025-01-01T00:00:00Z",
            )
        )
        logger.close()

        assert log_dir.exists()
        assert (log_dir / DEFAULT_WARNING_LOG_FILE).exists()

    def test_immediate_flush(self, temp_log_dir: Path, sample_warning: StructuredWarning) -> None:
        """Test that warnings are flushed immediately (T-6.9 requirement)."""
        logger = WarningLogger(log_dir=temp_log_dir)
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE

        # Log warning but don't close
        logger.log_warning(sample_warning)

        # File should already contain the warning due to immediate flush
        assert log_path.exists()
        content = log_path.read_text()
        assert len(content) > 0
        data = json.loads(content.strip())
        assert data["type"] == "dynamic_dispatch"

        logger.close()

    def test_context_manager(self, temp_log_dir: Path, sample_warning: StructuredWarning) -> None:
        """Test context manager usage."""
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE

        with WarningLogger(log_dir=temp_log_dir) as logger:
            logger.log_warning(sample_warning)

        # File should be closed and content available
        assert log_path.exists()
        content = log_path.read_text()
        data = json.loads(content.strip())
        assert data["type"] == "dynamic_dispatch"

    def test_append_mode(
        self, temp_log_dir: Path, sample_warnings: list[StructuredWarning]
    ) -> None:
        """Test that multiple sessions append to the same file."""
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE

        # First session
        with WarningLogger(log_dir=temp_log_dir) as logger:
            logger.log_warning(sample_warnings[0])

        # Second session
        with WarningLogger(log_dir=temp_log_dir) as logger:
            logger.log_warning(sample_warnings[1])

        # Verify both warnings are in file
        content = log_path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2


class TestWarningStatistics:
    """Test cases for warning statistics generation."""

    def test_empty_statistics(self, temp_log_dir: Path) -> None:
        """Test statistics with no warnings logged."""
        logger = WarningLogger(log_dir=temp_log_dir)
        stats = logger.get_statistics()

        assert stats.total_warnings == 0
        assert stats.by_type == {}
        assert stats.files_with_most_warnings == []

    def test_statistics_after_logging(
        self, temp_log_dir: Path, sample_warnings: list[StructuredWarning]
    ) -> None:
        """Test statistics after logging multiple warnings."""
        logger = WarningLogger(log_dir=temp_log_dir)

        for warning in sample_warnings:
            logger.log_warning(warning)

        stats = logger.get_statistics()

        assert stats.total_warnings == 3
        assert stats.by_type == {
            "dynamic_dispatch": 1,
            "exec_eval": 1,
            "monkey_patching": 1,
        }

        # Check files with most warnings
        files = {f["file"]: f["warning_count"] for f in stats.files_with_most_warnings}
        assert files["/project/src/module.py"] == 2
        assert files["/project/src/utils.py"] == 1

    def test_statistics_to_dict(
        self, temp_log_dir: Path, sample_warnings: list[StructuredWarning]
    ) -> None:
        """Test statistics to_dict() for JSON serialization."""
        logger = WarningLogger(log_dir=temp_log_dir)

        for warning in sample_warnings:
            logger.log_warning(warning)

        stats = logger.get_statistics()
        data = stats.to_dict()

        assert isinstance(data, dict)
        assert "total_warnings" in data
        assert "by_type" in data
        assert "files_with_most_warnings" in data
        assert data["total_warnings"] == 3

    def test_statistics_top_files_limit(self, temp_log_dir: Path) -> None:
        """Test that top files are limited correctly."""
        logger = WarningLogger(log_dir=temp_log_dir)

        # Create warnings from 10 different files
        for i in range(10):
            logger.log_warning(
                StructuredWarning(
                    type="dynamic_dispatch",
                    file=f"/project/file{i}.py",
                    line=i,
                    severity="warning",
                    pattern="test",
                    message="test",
                    timestamp="2025-01-01T00:00:00Z",
                )
            )

        # Default limit is 5
        stats = logger.get_statistics()
        assert len(stats.files_with_most_warnings) == 5

        # Custom limit
        stats = logger.get_statistics(top_files_count=3)
        assert len(stats.files_with_most_warnings) == 3

    def test_clear_statistics(self, temp_log_dir: Path, sample_warning: StructuredWarning) -> None:
        """Test clearing statistics."""
        logger = WarningLogger(log_dir=temp_log_dir)

        logger.log_warning(sample_warning)
        assert logger._warning_count == 1

        logger.clear_statistics()

        assert logger._warning_count == 0
        assert len(logger._by_type) == 0
        assert len(logger._by_file) == 0


class TestLogFileManagement:
    """Test cases for log file management."""

    def test_get_log_path(self, temp_log_dir: Path) -> None:
        """Test getting log file path."""
        logger = WarningLogger(log_dir=temp_log_dir)
        log_path = logger.get_log_path()

        assert log_path == temp_log_dir / DEFAULT_WARNING_LOG_FILE

    def test_get_log_size_nonexistent(self, temp_log_dir: Path) -> None:
        """Test getting size of nonexistent log file."""
        logger = WarningLogger(log_dir=temp_log_dir)
        size = logger.get_log_size()

        assert size == 0

    def test_get_log_size_after_logging(
        self, temp_log_dir: Path, sample_warning: StructuredWarning
    ) -> None:
        """Test getting size after logging."""
        logger = WarningLogger(log_dir=temp_log_dir)
        logger.log_warning(sample_warning)
        logger.close()

        size = logger.get_log_size()
        assert size > 0

    def test_size_warning_threshold(self, temp_log_dir: Path) -> None:
        """Test warning when log file exceeds size threshold."""
        # Use small threshold for testing (50 bytes)
        logger = WarningLogger(log_dir=temp_log_dir, size_warning_threshold=50)

        with mock.patch("xfile_context.warning_logger.logger") as mock_logger:
            # Log enough warnings to exceed threshold - need to trigger size check
            # Size check happens every 100 warnings, so we need to log at least 100
            for i in range(150):
                logger.log_warning(
                    StructuredWarning(
                        type="dynamic_dispatch",
                        file=f"/project/file{i}.py",
                        line=i,
                        severity="warning",
                        pattern="getattr(obj, 'very_long_method_name')",
                        message="Dynamic dispatch detected with extra long message",
                        timestamp="2025-01-01T00:00:00.000000Z",
                    )
                )

            logger.close()

            # Verify warning was issued
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Warning log file has grown" in str(call)
            ]
            assert len(warning_calls) >= 1

    def test_size_warning_only_once(self, temp_log_dir: Path) -> None:
        """Test that size warning is only issued once."""
        logger = WarningLogger(log_dir=temp_log_dir, size_warning_threshold=100)

        with mock.patch("xfile_context.warning_logger.logger") as mock_logger:
            # Log many warnings
            for i in range(200):
                logger.log_warning(
                    StructuredWarning(
                        type="dynamic_dispatch",
                        file=f"/project/file{i}.py",
                        line=i,
                        severity="warning",
                        pattern="getattr(obj, 'method')",
                        message="Dynamic dispatch detected",
                        timestamp="2025-01-01T00:00:00Z",
                    )
                )

            logger.close()

            # Count size warnings
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "Warning log file has grown" in str(call)
            ]
            # Should be at most 1
            assert len(warning_calls) <= 1


class TestReadWarningsFromLog:
    """Test cases for reading warnings from log file."""

    def test_read_warnings(
        self, temp_log_dir: Path, sample_warnings: list[StructuredWarning]
    ) -> None:
        """Test reading warnings back from log file."""
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE

        # Write warnings
        with WarningLogger(log_dir=temp_log_dir) as logger:
            logger.log_warnings(sample_warnings)

        # Read warnings back
        warnings = read_warnings_from_log(log_path)

        assert len(warnings) == 3
        assert warnings[0].type == "dynamic_dispatch"
        assert warnings[1].type == "exec_eval"
        assert warnings[2].type == "monkey_patching"

    def test_read_warnings_with_limit(
        self, temp_log_dir: Path, sample_warnings: list[StructuredWarning]
    ) -> None:
        """Test reading warnings with limit."""
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE

        with WarningLogger(log_dir=temp_log_dir) as logger:
            logger.log_warnings(sample_warnings)

        warnings = read_warnings_from_log(log_path, limit=2)

        assert len(warnings) == 2

    def test_read_warnings_empty_file(self, temp_log_dir: Path) -> None:
        """Test reading from empty log file."""
        log_path = temp_log_dir / "empty.jsonl"
        log_path.touch()

        warnings = read_warnings_from_log(log_path)

        assert warnings == []

    def test_read_warnings_file_not_found(self, temp_log_dir: Path) -> None:
        """Test reading from nonexistent file."""
        log_path = temp_log_dir / "nonexistent.jsonl"

        with pytest.raises(FileNotFoundError):
            read_warnings_from_log(log_path)


class TestWarningEmitterIntegration:
    """Test cases for WarningEmitter integration with WarningLogger."""

    def test_emitter_with_logger(self, temp_log_dir: Path) -> None:
        """Test WarningEmitter logs to file when logger is configured."""
        from xfile_context.detectors.dynamic_pattern_detector import (
            DynamicPatternType,
            DynamicPatternWarning,
            WarningSeverity,
        )

        warning_logger = WarningLogger(log_dir=temp_log_dir)
        emitter = WarningEmitter(warning_logger=warning_logger)

        # Add a warning
        raw_warning = DynamicPatternWarning(
            pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
            filepath="/test/module.py",
            line_number=10,
            message="Dynamic dispatch detected",
            severity=WarningSeverity.WARNING,
            is_test_module=False,
            metadata={"object_name": "obj"},
        )
        emitter.add_warning(raw_warning)

        warning_logger.close()

        # Verify warning was logged to file
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE
        assert log_path.exists()

        warnings = read_warnings_from_log(log_path)
        assert len(warnings) == 1
        assert warnings[0].type == "dynamic_dispatch"

    def test_emitter_without_logger(self) -> None:
        """Test WarningEmitter works without logger."""
        from xfile_context.detectors.dynamic_pattern_detector import (
            DynamicPatternType,
            DynamicPatternWarning,
            WarningSeverity,
        )

        emitter = WarningEmitter()

        raw_warning = DynamicPatternWarning(
            pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
            filepath="/test/module.py",
            line_number=10,
            message="Dynamic dispatch detected",
            severity=WarningSeverity.WARNING,
            is_test_module=False,
        )
        emitter.add_warning(raw_warning)

        # Should work without error
        assert emitter.count() == 1

    def test_emitter_set_logger(self, temp_log_dir: Path) -> None:
        """Test setting logger after emitter creation."""
        from xfile_context.detectors.dynamic_pattern_detector import (
            DynamicPatternType,
            DynamicPatternWarning,
            WarningSeverity,
        )

        emitter = WarningEmitter()
        warning_logger = WarningLogger(log_dir=temp_log_dir)

        emitter.set_warning_logger(warning_logger)

        # Add warning after setting logger
        raw_warning = DynamicPatternWarning(
            pattern_type=DynamicPatternType.EXEC_EVAL,
            filepath="/test/module.py",
            line_number=20,
            message="exec/eval usage detected",
            severity=WarningSeverity.WARNING,
            is_test_module=False,
            metadata={"call_type": "eval"},
        )
        emitter.add_warning(raw_warning)

        warning_logger.close()

        # Verify warning was logged
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE
        warnings = read_warnings_from_log(log_path)
        assert len(warnings) == 1
        assert warnings[0].type == "exec_eval"

    def test_emitter_get_logger(self, temp_log_dir: Path) -> None:
        """Test getting logger from emitter."""
        warning_logger = WarningLogger(log_dir=temp_log_dir)
        emitter = WarningEmitter(warning_logger=warning_logger)

        assert emitter.get_warning_logger() is warning_logger

        emitter.set_warning_logger(None)
        assert emitter.get_warning_logger() is None

    def test_emitter_statistics_from_logger(self, temp_log_dir: Path) -> None:
        """Test getting statistics from logger via emitter."""
        from xfile_context.detectors.dynamic_pattern_detector import (
            DynamicPatternType,
            DynamicPatternWarning,
            WarningSeverity,
        )

        warning_logger = WarningLogger(log_dir=temp_log_dir)
        emitter = WarningEmitter(warning_logger=warning_logger)

        # Add multiple warnings
        for i in range(5):
            raw_warning = DynamicPatternWarning(
                pattern_type=DynamicPatternType.DYNAMIC_DISPATCH,
                filepath=f"/test/module{i % 2}.py",
                line_number=i * 10,
                message="Dynamic dispatch detected",
                severity=WarningSeverity.WARNING,
                is_test_module=False,
            )
            emitter.add_warning(raw_warning)

        # Get statistics from logger
        stats = warning_logger.get_statistics()

        assert stats.total_warnings == 5
        assert stats.by_type["dynamic_dispatch"] == 5
        assert len(stats.files_with_most_warnings) == 2

        warning_logger.close()


class TestWarningStatisticsDataclass:
    """Test cases for WarningStatistics dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        stats = WarningStatistics()

        assert stats.total_warnings == 0
        assert stats.by_type == {}
        assert stats.files_with_most_warnings == []

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        stats = WarningStatistics(
            total_warnings=10,
            by_type={"dynamic_dispatch": 5, "exec_eval": 5},
            files_with_most_warnings=[
                {"file": "/src/a.py", "warning_count": 6},
                {"file": "/src/b.py", "warning_count": 4},
            ],
        )

        data = stats.to_dict()

        assert data["total_warnings"] == 10
        assert data["by_type"]["dynamic_dispatch"] == 5
        assert len(data["files_with_most_warnings"]) == 2


class TestJSONLFormat:
    """Test cases for JSONL format compliance."""

    def test_jsonl_one_object_per_line(
        self, temp_log_dir: Path, sample_warnings: list[StructuredWarning]
    ) -> None:
        """Test that each warning is on its own line (JSONL format)."""
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE

        with WarningLogger(log_dir=temp_log_dir) as logger:
            logger.log_warnings(sample_warnings)

        content = log_path.read_text()
        lines = content.strip().split("\n")

        # Each line should be valid JSON
        for line in lines:
            json.loads(line)  # Should not raise

        # Number of lines should match number of warnings
        assert len(lines) == len(sample_warnings)

    def test_jsonl_compact_format(
        self, temp_log_dir: Path, sample_warning: StructuredWarning
    ) -> None:
        """Test that JSON is compact (no extra whitespace)."""
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE

        with WarningLogger(log_dir=temp_log_dir) as logger:
            logger.log_warning(sample_warning)

        content = log_path.read_text().strip()

        # Should not contain newlines within JSON (compact format)
        data = json.loads(content)
        recompacted = json.dumps(data, separators=(",", ":"))
        assert content == recompacted

    def test_jsonl_machine_parseable(
        self, temp_log_dir: Path, sample_warnings: list[StructuredWarning]
    ) -> None:
        """Test that log file is machine-parseable."""
        log_path = temp_log_dir / DEFAULT_WARNING_LOG_FILE

        with WarningLogger(log_dir=temp_log_dir) as logger:
            logger.log_warnings(sample_warnings)

        # Standard JSONL parsing approach
        parsed_warnings = []
        with open(log_path) as f:
            for line in f:
                if line.strip():
                    parsed_warnings.append(json.loads(line))

        assert len(parsed_warnings) == 3
        assert all("type" in w for w in parsed_warnings)
        assert all("file" in w for w in parsed_warnings)
        assert all("line" in w for w in parsed_warnings)
