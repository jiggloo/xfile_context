# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Unit tests for the injection logger module.

Tests cover TDD Section 3.8.5 requirements:
- T-5.1: All injections logged with required fields
- T-5.2: JSONL format parseable by standard tools
- T-5.3: Logs flushed immediately (no buffering)
- T-5.4: Statistics tracking (by type, by file, cache hit rate)
- T-5.5: Query API retrieves recent injection events (FR-29)
- T-5.6: Log file size monitoring
- T-5.7: File size remains manageable (<10MB per 4-hour session expected)
"""

import json
from pathlib import Path

import pytest

from xfile_context.injection_logger import (
    DEFAULT_INJECTION_LOG_FILE,
    InjectionEvent,
    InjectionLogger,
    InjectionStatistics,
    get_recent_injections,
    read_injections_from_log,
)


class TestInjectionEvent:
    """Tests for InjectionEvent dataclass."""

    def test_create_with_all_fields(self) -> None:
        """Test creating an InjectionEvent with all required fields."""
        event = InjectionEvent.create(
            source_file="/project/src/utils.py",
            target_file="/project/src/main.py",
            relationship_type="IMPORT",
            snippet="def helper_func():\n    pass",
            snippet_location="utils.py:10-12",
            cache_age_seconds=120.5,
            cache_hit=True,
            token_count=15,
            context_token_total=45,
        )

        assert event.source_file == "/project/src/utils.py"
        assert event.target_file == "/project/src/main.py"
        assert event.relationship_type == "IMPORT"
        assert event.snippet == "def helper_func():\n    pass"
        assert event.snippet_location == "utils.py:10-12"
        assert event.cache_age_seconds == 120.5
        assert event.cache_hit is True
        assert event.token_count == 15
        assert event.context_token_total == 45
        assert event.event_type == "context_injection"
        assert event.timestamp  # Should be auto-generated

    def test_create_with_no_cache(self) -> None:
        """Test creating an InjectionEvent with no cache (cache miss)."""
        event = InjectionEvent.create(
            source_file="/project/src/utils.py",
            target_file="/project/src/main.py",
            relationship_type="FUNCTION_CALL",
            snippet="def foo():",
            snippet_location="utils.py:5",
            cache_age_seconds=None,
            cache_hit=False,
            token_count=5,
            context_token_total=5,
        )

        assert event.cache_age_seconds is None
        assert event.cache_hit is False

    def test_to_dict(self) -> None:
        """Test converting InjectionEvent to dictionary."""
        event = InjectionEvent(
            timestamp="2025-11-25T10:30:45.123+00:00",
            event_type="context_injection",
            source_file="/project/src/utils.py",
            target_file="/project/src/main.py",
            relationship_type="IMPORT",
            snippet="def helper():",
            snippet_location="utils.py:10",
            cache_age_seconds=60.0,
            cache_hit=True,
            token_count=10,
            context_token_total=30,
        )

        d = event.to_dict()

        assert d["timestamp"] == "2025-11-25T10:30:45.123+00:00"
        assert d["event_type"] == "context_injection"
        assert d["source_file"] == "/project/src/utils.py"
        assert d["target_file"] == "/project/src/main.py"
        assert d["relationship_type"] == "IMPORT"
        assert d["snippet"] == "def helper():"
        assert d["snippet_location"] == "utils.py:10"
        assert d["cache_age_seconds"] == 60.0
        assert d["cache_hit"] is True
        assert d["token_count"] == 10
        assert d["context_token_total"] == 30

    def test_from_dict(self) -> None:
        """Test creating InjectionEvent from dictionary."""
        data = {
            "timestamp": "2025-11-25T10:30:45.123+00:00",
            "event_type": "context_injection",
            "source_file": "/project/src/utils.py",
            "target_file": "/project/src/main.py",
            "relationship_type": "IMPORT",
            "snippet": "def helper():",
            "snippet_location": "utils.py:10",
            "cache_age_seconds": 60.0,
            "cache_hit": True,
            "token_count": 10,
            "context_token_total": 30,
        }

        event = InjectionEvent.from_dict(data)

        assert event.timestamp == "2025-11-25T10:30:45.123+00:00"
        assert event.source_file == "/project/src/utils.py"
        assert event.cache_hit is True

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """Test that to_dict and from_dict are inverses."""
        original = InjectionEvent.create(
            source_file="/src/a.py",
            target_file="/src/b.py",
            relationship_type="IMPORT",
            snippet="def foo():",
            snippet_location="a.py:1",
            cache_age_seconds=30.0,
            cache_hit=True,
            token_count=5,
            context_token_total=5,
        )

        d = original.to_dict()
        restored = InjectionEvent.from_dict(d)

        assert restored.source_file == original.source_file
        assert restored.target_file == original.target_file
        assert restored.relationship_type == original.relationship_type
        assert restored.snippet == original.snippet
        assert restored.cache_age_seconds == original.cache_age_seconds
        assert restored.cache_hit == original.cache_hit
        assert restored.token_count == original.token_count


class TestInjectionStatistics:
    """Tests for InjectionStatistics dataclass."""

    def test_default_values(self) -> None:
        """Test InjectionStatistics with default values."""
        stats = InjectionStatistics()

        assert stats.total_injections == 0
        assert stats.by_relationship_type == {}
        assert stats.by_source_file == {}
        assert stats.total_tokens_injected == 0
        assert stats.cache_hit_count == 0
        assert stats.cache_miss_count == 0

    def test_to_dict(self) -> None:
        """Test converting InjectionStatistics to dictionary."""
        stats = InjectionStatistics(
            total_injections=100,
            by_relationship_type={"IMPORT": 60, "FUNCTION_CALL": 40},
            by_source_file={"/src/utils.py": 30, "/src/helpers.py": 20},
            total_tokens_injected=1500,
            cache_hit_count=80,
            cache_miss_count=20,
        )

        d = stats.to_dict()

        assert d["total_injections"] == 100
        assert d["by_relationship_type"] == {"IMPORT": 60, "FUNCTION_CALL": 40}
        assert d["total_tokens_injected"] == 1500
        assert d["cache_hit_count"] == 80
        assert d["cache_miss_count"] == 20
        assert d["cache_hit_rate"] == 0.8  # 80/100

    def test_to_dict_zero_injections_cache_rate(self) -> None:
        """Test cache_hit_rate is 0 when no injections."""
        stats = InjectionStatistics()
        d = stats.to_dict()
        assert d["cache_hit_rate"] == 0.0


class TestInjectionLogger:
    """Tests for InjectionLogger class."""

    def test_initialization_default_values(self, tmp_path: Path) -> None:
        """Test InjectionLogger initializes with correct defaults."""
        logger = InjectionLogger(log_dir=tmp_path)

        assert logger._log_dir == tmp_path
        assert logger._log_file == DEFAULT_INJECTION_LOG_FILE
        assert logger._injection_count == 0

        logger.close()

    def test_initialization_custom_log_file(self, tmp_path: Path) -> None:
        """Test InjectionLogger with custom log file name."""
        logger = InjectionLogger(log_dir=tmp_path, log_file="custom.jsonl")

        assert logger._log_file == "custom.jsonl"
        assert logger.get_log_path() == tmp_path / "custom.jsonl"

        logger.close()

    def test_initialization_rejects_path_in_log_file(self, tmp_path: Path) -> None:
        """Test InjectionLogger rejects path separators in log_file."""
        with pytest.raises(ValueError, match="must not contain path separators"):
            InjectionLogger(log_dir=tmp_path, log_file="subdir/log.jsonl")

        with pytest.raises(ValueError, match="must not contain path separators"):
            InjectionLogger(log_dir=tmp_path, log_file="..\\log.jsonl")

    def test_log_injection_creates_file(self, tmp_path: Path) -> None:
        """Test that log_injection creates the log file."""
        logger = InjectionLogger(log_dir=tmp_path)

        event = InjectionEvent.create(
            source_file="/src/a.py",
            target_file="/src/b.py",
            relationship_type="IMPORT",
            snippet="def foo():",
            snippet_location="a.py:1",
            cache_age_seconds=None,
            cache_hit=False,
            token_count=5,
            context_token_total=5,
        )

        logger.log_injection(event)
        logger.close()

        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        assert log_path.exists()

    def test_log_injection_jsonl_format(self, tmp_path: Path) -> None:
        """Test that logged events are in valid JSONL format (T-5.2)."""
        logger = InjectionLogger(log_dir=tmp_path)

        event = InjectionEvent.create(
            source_file="/src/utils.py",
            target_file="/src/main.py",
            relationship_type="IMPORT",
            snippet="def helper():",
            snippet_location="utils.py:10",
            cache_age_seconds=60.0,
            cache_hit=True,
            token_count=10,
            context_token_total=10,
        )

        logger.log_injection(event)
        logger.close()

        # Read and parse the log file
        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        with open(log_path) as f:
            line = f.readline().strip()
            data = json.loads(line)

        # Verify all required fields are present (T-5.1)
        assert "timestamp" in data
        assert data["event_type"] == "context_injection"
        assert data["source_file"] == "/src/utils.py"
        assert data["target_file"] == "/src/main.py"
        assert data["relationship_type"] == "IMPORT"
        assert data["snippet"] == "def helper():"
        assert data["snippet_location"] == "utils.py:10"
        assert data["cache_age_seconds"] == 60.0
        assert data["cache_hit"] is True
        assert data["token_count"] == 10
        assert data["context_token_total"] == 10

    def test_log_multiple_injections(self, tmp_path: Path) -> None:
        """Test logging multiple injection events."""
        logger = InjectionLogger(log_dir=tmp_path)

        events = [
            InjectionEvent.create(
                source_file=f"/src/file{i}.py",
                target_file="/src/main.py",
                relationship_type="IMPORT",
                snippet=f"def func{i}():",
                snippet_location=f"file{i}.py:{i}",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=5,
                context_token_total=5 * (i + 1),
            )
            for i in range(5)
        ]

        for event in events:
            logger.log_injection(event)
        logger.close()

        # Read all lines and verify count
        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        with open(log_path) as f:
            lines = f.readlines()

        assert len(lines) == 5

        # Verify each line is valid JSON
        for line in lines:
            data = json.loads(line.strip())
            assert "source_file" in data

    def test_log_injections_batch(self, tmp_path: Path) -> None:
        """Test batch logging of multiple events."""
        logger = InjectionLogger(log_dir=tmp_path)

        events = [
            InjectionEvent.create(
                source_file=f"/src/file{i}.py",
                target_file="/src/main.py",
                relationship_type="IMPORT",
                snippet=f"def func{i}():",
                snippet_location=f"file{i}.py:{i}",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=5,
                context_token_total=5 * (i + 1),
            )
            for i in range(3)
        ]

        logger.log_injections(events)
        logger.close()

        # Read and verify
        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        with open(log_path) as f:
            lines = f.readlines()

        assert len(lines) == 3

    def test_immediate_flush(self, tmp_path: Path) -> None:
        """Test that events are flushed immediately (T-5.3)."""
        logger = InjectionLogger(log_dir=tmp_path)

        event = InjectionEvent.create(
            source_file="/src/a.py",
            target_file="/src/b.py",
            relationship_type="IMPORT",
            snippet="def foo():",
            snippet_location="a.py:1",
            cache_age_seconds=None,
            cache_hit=False,
            token_count=5,
            context_token_total=5,
        )

        logger.log_injection(event)

        # File should be readable immediately without closing
        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        with open(log_path) as f:
            content = f.read()
            assert "source_file" in content

        logger.close()

    def test_statistics_tracking(self, tmp_path: Path) -> None:
        """Test injection statistics tracking (T-5.4)."""
        logger = InjectionLogger(log_dir=tmp_path)

        # Log events with different types and cache states
        events = [
            InjectionEvent.create(
                source_file="/src/utils.py",
                target_file="/src/main.py",
                relationship_type="IMPORT",
                snippet="def a():",
                snippet_location="utils.py:1",
                cache_age_seconds=60.0,
                cache_hit=True,
                token_count=10,
                context_token_total=10,
            ),
            InjectionEvent.create(
                source_file="/src/helpers.py",
                target_file="/src/main.py",
                relationship_type="FUNCTION_CALL",
                snippet="def b():",
                snippet_location="helpers.py:5",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=15,
                context_token_total=25,
            ),
            InjectionEvent.create(
                source_file="/src/utils.py",
                target_file="/src/main.py",
                relationship_type="IMPORT",
                snippet="def c():",
                snippet_location="utils.py:10",
                cache_age_seconds=30.0,
                cache_hit=True,
                token_count=10,
                context_token_total=35,
            ),
        ]

        for event in events:
            logger.log_injection(event)

        stats = logger.get_statistics()

        assert stats.total_injections == 3
        assert stats.by_relationship_type == {"IMPORT": 2, "FUNCTION_CALL": 1}
        assert stats.total_tokens_injected == 35  # 10 + 15 + 10
        assert stats.cache_hit_count == 2
        assert stats.cache_miss_count == 1

        logger.close()

    def test_get_log_size(self, tmp_path: Path) -> None:
        """Test getting log file size."""
        logger = InjectionLogger(log_dir=tmp_path)

        # Before any logging, size should be 0
        assert logger.get_log_size() == 0

        event = InjectionEvent.create(
            source_file="/src/a.py",
            target_file="/src/b.py",
            relationship_type="IMPORT",
            snippet="def foo():",
            snippet_location="a.py:1",
            cache_age_seconds=None,
            cache_hit=False,
            token_count=5,
            context_token_total=5,
        )

        logger.log_injection(event)

        # After logging, size should be > 0
        assert logger.get_log_size() > 0

        logger.close()

    def test_clear_statistics(self, tmp_path: Path) -> None:
        """Test clearing in-memory statistics."""
        logger = InjectionLogger(log_dir=tmp_path)

        event = InjectionEvent.create(
            source_file="/src/a.py",
            target_file="/src/b.py",
            relationship_type="IMPORT",
            snippet="def foo():",
            snippet_location="a.py:1",
            cache_age_seconds=60.0,
            cache_hit=True,
            token_count=10,
            context_token_total=10,
        )

        logger.log_injection(event)
        assert logger.get_statistics().total_injections == 1

        logger.clear_statistics()

        stats = logger.get_statistics()
        assert stats.total_injections == 0
        assert stats.cache_hit_count == 0

        logger.close()

    def test_context_manager(self, tmp_path: Path) -> None:
        """Test using InjectionLogger as context manager."""
        with InjectionLogger(log_dir=tmp_path) as logger:
            event = InjectionEvent.create(
                source_file="/src/a.py",
                target_file="/src/b.py",
                relationship_type="IMPORT",
                snippet="def foo():",
                snippet_location="a.py:1",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=5,
                context_token_total=5,
            )
            logger.log_injection(event)

        # File should exist after context manager exits
        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        assert log_path.exists()

    def test_file_size_warning_deprecated(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that size warnings are no longer issued per Issue #150.

        Per Issue #150, file size warnings are deprecated. Log files are now
        split by date for eventual immutability, and users control cleanup
        via date-based file management.
        """
        import logging

        caplog.set_level(logging.WARNING)

        # Use a very small threshold for testing - this is now ignored
        small_threshold = 100  # 100 bytes
        logger = InjectionLogger(log_dir=tmp_path, size_warning_threshold=small_threshold)

        # Log enough events to exceed threshold and trigger the check
        # The check happens every 100 injections, so we need at least 100
        for i in range(101):
            event = InjectionEvent.create(
                source_file=f"/src/file{i}.py",
                target_file="/src/main.py",
                relationship_type="IMPORT",
                snippet=f"def very_long_function_name_with_lots_of_text_{i}():",
                snippet_location=f"file{i}.py:{i}",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=20,
                context_token_total=20 * (i + 1),
            )
            logger.log_injection(event)

        logger.close()

        # Per Issue #150, size warnings are no longer issued
        warning_found = any(
            "Injection log file has grown to" in record.message for record in caplog.records
        )
        assert not warning_found, "Size warnings should not be issued per Issue #150"


class TestGetRecentInjections:
    """Tests for get_recent_injections function (FR-29)."""

    def test_get_recent_injections_empty_log(self, tmp_path: Path) -> None:
        """Test getting recent injections from empty/non-existent log."""
        log_path = tmp_path / "injections.jsonl"
        events = get_recent_injections(log_path)
        assert events == []

    def test_get_recent_injections_all(self, tmp_path: Path) -> None:
        """Test getting all recent injections (T-5.5)."""
        logger = InjectionLogger(log_dir=tmp_path)

        # Log 5 events
        for i in range(5):
            event = InjectionEvent.create(
                source_file=f"/src/file{i}.py",
                target_file="/src/main.py",
                relationship_type="IMPORT",
                snippet=f"def func{i}():",
                snippet_location=f"file{i}.py:{i}",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=5,
                context_token_total=5 * (i + 1),
            )
            logger.log_injection(event)

        logger.close()

        # Get recent injections
        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        events = get_recent_injections(log_path, limit=10)

        assert len(events) == 5
        # Most recent first
        assert events[0].source_file == "/src/file4.py"
        assert events[4].source_file == "/src/file0.py"

    def test_get_recent_injections_with_limit(self, tmp_path: Path) -> None:
        """Test limiting the number of recent injections."""
        logger = InjectionLogger(log_dir=tmp_path)

        # Log 10 events
        for i in range(10):
            event = InjectionEvent.create(
                source_file=f"/src/file{i}.py",
                target_file="/src/main.py",
                relationship_type="IMPORT",
                snippet=f"def func{i}():",
                snippet_location=f"file{i}.py:{i}",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=5,
                context_token_total=5 * (i + 1),
            )
            logger.log_injection(event)

        logger.close()

        # Get only last 3
        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        events = get_recent_injections(log_path, limit=3)

        assert len(events) == 3
        # Most recent first (files 9, 8, 7)
        assert events[0].source_file == "/src/file9.py"
        assert events[1].source_file == "/src/file8.py"
        assert events[2].source_file == "/src/file7.py"

    def test_get_recent_injections_by_target_file(self, tmp_path: Path) -> None:
        """Test filtering recent injections by target file."""
        logger = InjectionLogger(log_dir=tmp_path)

        # Log events for different target files
        targets = ["/src/main.py", "/src/other.py", "/src/main.py", "/src/another.py"]
        for i, target in enumerate(targets):
            event = InjectionEvent.create(
                source_file=f"/src/file{i}.py",
                target_file=target,
                relationship_type="IMPORT",
                snippet=f"def func{i}():",
                snippet_location=f"file{i}.py:{i}",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=5,
                context_token_total=5 * (i + 1),
            )
            logger.log_injection(event)

        logger.close()

        # Get only events for main.py
        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        events = get_recent_injections(log_path, target_file="/src/main.py")

        assert len(events) == 2
        for event in events:
            assert event.target_file == "/src/main.py"


class TestReadInjectionsFromLog:
    """Tests for read_injections_from_log utility function."""

    def test_read_all_injections(self, tmp_path: Path) -> None:
        """Test reading all injections from log file."""
        logger = InjectionLogger(log_dir=tmp_path)

        for i in range(5):
            event = InjectionEvent.create(
                source_file=f"/src/file{i}.py",
                target_file="/src/main.py",
                relationship_type="IMPORT",
                snippet=f"def func{i}():",
                snippet_location=f"file{i}.py:{i}",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=5,
                context_token_total=5 * (i + 1),
            )
            logger.log_injection(event)

        logger.close()

        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        events = read_injections_from_log(log_path)

        assert len(events) == 5
        # Chronological order
        assert events[0].source_file == "/src/file0.py"
        assert events[4].source_file == "/src/file4.py"

    def test_read_with_limit(self, tmp_path: Path) -> None:
        """Test reading with limit."""
        logger = InjectionLogger(log_dir=tmp_path)

        for i in range(10):
            event = InjectionEvent.create(
                source_file=f"/src/file{i}.py",
                target_file="/src/main.py",
                relationship_type="IMPORT",
                snippet=f"def func{i}():",
                snippet_location=f"file{i}.py:{i}",
                cache_age_seconds=None,
                cache_hit=False,
                token_count=5,
                context_token_total=5 * (i + 1),
            )
            logger.log_injection(event)

        logger.close()

        log_path = tmp_path / DEFAULT_INJECTION_LOG_FILE
        events = read_injections_from_log(log_path, limit=3)

        assert len(events) == 3
        # First 3 chronologically
        assert events[0].source_file == "/src/file0.py"
        assert events[2].source_file == "/src/file2.py"


@pytest.mark.slow
class TestInjectionLoggerIntegration:
    """Integration tests for injection logging in service context."""

    def test_log_integration_with_service(self, tmp_path: Path) -> None:
        """Test that InjectionLogger integrates with CrossFileContextService."""
        from xfile_context.config import Config
        from xfile_context.service import CrossFileContextService

        # Create a simple Python file to analyze
        source_file = tmp_path / "utils.py"
        source_file.write_text("def helper():\n    pass\n")

        main_file = tmp_path / "main.py"
        main_file.write_text("from utils import helper\n\nhelper()\n")

        # Create service with custom injection logger
        injection_logger = InjectionLogger(log_dir=tmp_path)
        config = Config()
        service = CrossFileContextService(
            config=config,
            project_root=str(tmp_path),
            injection_logger=injection_logger,
        )

        # Analyze the files
        service.analyze_file(str(source_file))
        service.analyze_file(str(main_file))

        # Read with context injection (triggers logging)
        service.read_file_with_context(str(main_file))

        # Check that injection statistics were tracked
        stats = service.get_injection_statistics()
        # We may have logged some injections depending on what context was found
        # At minimum, the stats should be accessible
        assert stats is not None
        assert hasattr(stats, "total_injections")

        # Cleanup
        service.shutdown()

    def test_get_recent_injections_from_service(self, tmp_path: Path) -> None:
        """Test get_recent_injections method on service."""
        from xfile_context.config import Config
        from xfile_context.service import CrossFileContextService

        config = Config()
        service = CrossFileContextService(
            config=config,
            project_root=str(tmp_path),
        )

        # Get recent injections (should work even with no events)
        events = service.get_recent_injections(limit=5)
        assert isinstance(events, list)

        service.shutdown()
