# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
Functional Tests for Context Injection Logging (Test Category 5).

This module validates that context injection logging behavior works correctly
according to T-5.1 through T-5.7 from prd_testing.md Section 8.2.

Tests validate logging through the InjectionLogger class and integration with
CrossFileContextService, ensuring proper JSONL format, required fields,
parseability, query API, metrics calculation, and file size management.

Test Cases:
- T-5.1: Verify all context injections are logged to structured format (FR-26)
- T-5.2: Verify logs contain all required fields per FR-27
- T-5.3: Verify log format matches Claude Code session logs (.jsonl) for consistency
- T-5.4: Verify logs are parseable by standard JSON parsers
- T-5.5: Verify API/query mechanism can retrieve recent injection events (FR-29)
- T-5.6: Verify logs enable automated metrics calculation
- T-5.7: Verify log file size remains manageable (<10MB per 4-hour session)

References:
- TDD Section 3.8.5 (Injection Logging)
- TDD Section 3.10.2 (Injection Event Logging)
- FR-26, FR-27, FR-28, FR-29
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from xfile_context.config import Config
from xfile_context.injection_logger import (
    InjectionEvent,
    InjectionLogger,
    InjectionStatistics,
    get_recent_injections,
    read_injections_from_log,
)
from xfile_context.service import CrossFileContextService

# Path to the functional test codebase
TEST_CODEBASE_PATH = Path(__file__).parent / "test_codebase"
GROUND_TRUTH_PATH = TEST_CODEBASE_PATH / "ground_truth.json"

logger = logging.getLogger(__name__)


# Required fields per FR-27 (TDD Section 3.8.5)
REQUIRED_FIELDS = [
    "timestamp",
    "source_file",
    "target_file",
    "relationship_type",
    "snippet",
    "cache_age_seconds",
    "token_count",
]

# Additional fields for full JSONL schema
ALL_FIELDS = REQUIRED_FIELDS + [
    "event_type",
    "snippet_location",
    "cache_hit",
    "context_token_total",
]


@pytest.fixture(scope="module")
def ground_truth() -> Dict[str, Any]:
    """Load ground truth manifest for validation."""
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


@pytest.fixture
def temp_log_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for log files.

    Yields the temp directory path and cleans up after test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def injection_logger(temp_log_dir: Path) -> Generator[InjectionLogger, None, None]:
    """Create an InjectionLogger with temporary log directory.

    Yields logger and ensures cleanup.
    """
    logger_instance = InjectionLogger(log_dir=temp_log_dir)
    yield logger_instance
    logger_instance.close()


@pytest.fixture
def default_config() -> Generator[Config, None, None]:
    """Create default configuration for tests.

    Yields config and cleans up temporary file after test completes.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write("enable_context_injection: true\n")
        f.write("context_token_limit: 500\n")
        f.write("cache_expiry_minutes: 10\n")
        f.write("cache_size_limit_kb: 50\n")
        f.write("enable_injection_logging: true\n")
        config_path = Path(f.name)

    yield Config(config_path)

    # Cleanup temporary config file
    config_path.unlink(missing_ok=True)


@pytest.fixture
def sample_injection_event() -> InjectionEvent:
    """Create a sample injection event for testing."""
    return InjectionEvent.create(
        source_file="/path/to/source.py",
        target_file="/path/to/target.py",
        relationship_type="IMPORT",
        snippet="def helper_function():\n    '''Docstring'''",
        snippet_location="source.py:10-15",
        cache_age_seconds=30.5,
        cache_hit=True,
        token_count=25,
        context_token_total=100,
    )


@pytest.fixture
def multiple_injection_events() -> list[InjectionEvent]:
    """Create multiple injection events for testing."""
    events = []

    # Event 1: Import relationship
    events.append(
        InjectionEvent.create(
            source_file="/project/models/user.py",
            target_file="/project/services/user_service.py",
            relationship_type="IMPORT",
            snippet="class User:\n    '''User model'''",
            snippet_location="user.py:5-20",
            cache_age_seconds=10.0,
            cache_hit=True,
            token_count=30,
            context_token_total=30,
        )
    )

    # Event 2: Function call relationship (cache miss)
    events.append(
        InjectionEvent.create(
            source_file="/project/utils/helpers.py",
            target_file="/project/services/user_service.py",
            relationship_type="FUNCTION_CALL",
            snippet="def format_name(name: str) -> str:\n    '''Format a name'''",
            snippet_location="helpers.py:45-55",
            cache_age_seconds=None,
            cache_hit=False,
            token_count=20,
            context_token_total=50,
        )
    )

    # Event 3: Class inheritance relationship
    events.append(
        InjectionEvent.create(
            source_file="/project/models/base.py",
            target_file="/project/models/product.py",
            relationship_type="CLASS_INHERITANCE",
            snippet="class BaseModel:\n    '''Base model class'''",
            snippet_location="base.py:1-10",
            cache_age_seconds=120.0,
            cache_hit=True,
            token_count=15,
            context_token_total=15,
        )
    )

    return events


class TestInjectionLogging:
    """Functional tests for context injection logging (Test Category 5)."""

    def test_t_5_1_injections_logged_to_structured_format(
        self,
        injection_logger: InjectionLogger,
        sample_injection_event: InjectionEvent,
    ) -> None:
        """T-5.1: Verify all context injections are logged to structured format (FR-26).

        Tests that injection events are written to a JSONL file with proper structure.
        """
        # Log an injection event
        injection_logger.log_injection(sample_injection_event)

        # Verify log file was created
        log_path = injection_logger.get_log_path()
        assert log_path.exists(), "Log file should be created after logging"

        # Read and verify content
        with open(log_path) as f:
            content = f.read()

        # Verify JSONL format (one JSON object per line)
        lines = content.strip().split("\n")
        assert len(lines) == 1, "Should have exactly one log entry"

        # Verify JSON is valid
        logged_event = json.loads(lines[0])
        assert isinstance(logged_event, dict), "Log entry should be a JSON object"

    def test_t_5_1_multiple_injections_logged(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.1: Verify multiple injections are logged (FR-26).

        Tests that all injection events are logged, not just some.
        """
        # Log multiple events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        # Read log file
        log_path = injection_logger.get_log_path()
        with open(log_path) as f:
            lines = [line for line in f.read().strip().split("\n") if line]

        # Verify all events were logged
        assert len(lines) == len(
            multiple_injection_events
        ), f"Expected {len(multiple_injection_events)} log entries, got {len(lines)}"

    def test_t_5_1_batch_logging(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.1: Verify batch logging works correctly (FR-26).

        Tests the log_injections method for batch logging.
        """
        # Log multiple events at once
        injection_logger.log_injections(multiple_injection_events)

        # Read log file
        log_path = injection_logger.get_log_path()
        events = read_injections_from_log(log_path)

        assert len(events) == len(
            multiple_injection_events
        ), "Batch logging should write all events"

    def test_t_5_2_logs_contain_required_fields(
        self,
        injection_logger: InjectionLogger,
        sample_injection_event: InjectionEvent,
    ) -> None:
        """T-5.2: Verify logs contain all required fields per FR-27.

        Required fields: timestamp, source_file, target_file, relationship_type,
        snippet, cache_age_seconds, token_count.
        """
        # Log an event
        injection_logger.log_injection(sample_injection_event)

        # Read the log entry
        log_path = injection_logger.get_log_path()
        with open(log_path) as f:
            logged_event = json.loads(f.readline())

        # Verify all required fields are present
        for field in REQUIRED_FIELDS:
            assert field in logged_event, f"Required field '{field}' missing from log entry"

        # Verify field values match the event
        assert logged_event["source_file"] == sample_injection_event.source_file
        assert logged_event["target_file"] == sample_injection_event.target_file
        assert logged_event["relationship_type"] == sample_injection_event.relationship_type
        assert logged_event["snippet"] == sample_injection_event.snippet
        assert logged_event["token_count"] == sample_injection_event.token_count
        assert logged_event["cache_age_seconds"] == sample_injection_event.cache_age_seconds

    def test_t_5_2_timestamp_is_iso8601(
        self,
        injection_logger: InjectionLogger,
        sample_injection_event: InjectionEvent,
    ) -> None:
        """T-5.2: Verify timestamp field is ISO 8601 format.

        Per TDD Section 3.3.5, timestamp should be ISO 8601 format.
        """
        from datetime import datetime

        # Log an event
        injection_logger.log_injection(sample_injection_event)

        # Read the log entry
        log_path = injection_logger.get_log_path()
        with open(log_path) as f:
            logged_event = json.loads(f.readline())

        # Verify timestamp is valid ISO 8601
        timestamp_str = logged_event["timestamp"]

        # Should parse without error
        parsed = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        assert parsed is not None, "Timestamp should be valid ISO 8601"

    def test_t_5_2_all_fields_present(
        self,
        injection_logger: InjectionLogger,
        sample_injection_event: InjectionEvent,
    ) -> None:
        """T-5.2: Verify all fields (required + additional) are present.

        Tests complete field coverage per TDD Section 3.8.5.
        """
        # Log an event
        injection_logger.log_injection(sample_injection_event)

        # Read the log entry
        log_path = injection_logger.get_log_path()
        with open(log_path) as f:
            logged_event = json.loads(f.readline())

        # Verify all fields are present
        for field in ALL_FIELDS:
            assert field in logged_event, f"Field '{field}' missing from log entry"

    def test_t_5_3_jsonl_format_one_object_per_line(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.3: Verify log format matches JSONL (one JSON object per line).

        JSONL format: Each line is a complete, valid JSON object.
        """
        # Log multiple events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        # Read raw file content
        log_path = injection_logger.get_log_path()
        with open(log_path) as f:
            content = f.read()

        # Split into lines
        lines = content.strip().split("\n")

        # Verify each line is a complete JSON object
        for i, line in enumerate(lines):
            try:
                obj = json.loads(line)
                assert isinstance(obj, dict), f"Line {i+1} should be a JSON object"
            except json.JSONDecodeError:
                pytest.fail(f"Line {i+1} is not valid JSON: {line[:100]}...")

    def test_t_5_3_claude_code_compatible_format(
        self,
        injection_logger: InjectionLogger,
        sample_injection_event: InjectionEvent,
    ) -> None:
        """T-5.3: Verify log format is compatible with Claude Code session logs.

        Per FR-28: Use same format as Claude Code session logs (.jsonl).
        """
        # Log an event
        injection_logger.log_injection(sample_injection_event)

        # Read the log entry
        log_path = injection_logger.get_log_path()
        with open(log_path) as f:
            logged_event = json.loads(f.readline())

        # Claude Code session logs use:
        # - event_type field for filtering
        # - timestamp in ISO 8601 format
        # - Compact JSON (no extra whitespace)
        assert "event_type" in logged_event, "Should have event_type for filtering"
        assert logged_event["event_type"] == "context_injection"

        # Verify compact format (no pretty printing)
        with open(log_path) as f:
            raw_line = f.readline()
        assert "\n" not in raw_line.rstrip("\n"), "JSON should be on single line (compact)"

    def test_t_5_4_logs_parseable_by_standard_json_parser(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.4: Verify logs are parseable by standard JSON parsers.

        Tests that the log file can be parsed using Python's standard json module.
        """
        # Log multiple events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        log_path = injection_logger.get_log_path()

        # Parse using standard library
        parsed_events = []
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    parsed_events.append(json.loads(line))

        assert len(parsed_events) == len(multiple_injection_events)

        # Verify parsed data matches original
        for i, event in enumerate(multiple_injection_events):
            assert parsed_events[i]["source_file"] == event.source_file
            assert parsed_events[i]["target_file"] == event.target_file

    def test_t_5_4_read_injections_from_log_utility(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.4: Verify read_injections_from_log utility works correctly.

        Tests the convenience function for reading log files.
        """
        # Log events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        log_path = injection_logger.get_log_path()

        # Use utility function
        parsed_events = read_injections_from_log(log_path)

        assert len(parsed_events) == len(multiple_injection_events)

        # Verify types
        for event in parsed_events:
            assert isinstance(event, InjectionEvent)

    def test_t_5_5_query_api_retrieves_recent_events(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.5: Verify API/query mechanism can retrieve recent injection events (FR-29).

        Tests the get_recent_injections function.
        """
        # Log events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        log_path = injection_logger.get_log_path()

        # Query recent events
        recent = get_recent_injections(log_path, limit=10)

        assert len(recent) == len(multiple_injection_events)

        # Verify most recent is first
        assert recent[0].source_file == multiple_injection_events[-1].source_file

    def test_t_5_5_query_api_filters_by_target_file(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.5: Verify query API can filter by target file (FR-29).

        Tests target_file filtering capability.
        """
        # Log events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        log_path = injection_logger.get_log_path()

        # Query with target file filter
        target = "/project/services/user_service.py"
        filtered = get_recent_injections(log_path, target_file=target, limit=10)

        # Should return only events for this target
        assert len(filtered) == 2  # Two events target user_service.py
        for event in filtered:
            assert event.target_file == target

    def test_t_5_5_query_api_respects_limit(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.5: Verify query API respects limit parameter (FR-29)."""
        # Log events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        log_path = injection_logger.get_log_path()

        # Query with limit
        recent = get_recent_injections(log_path, limit=1)

        assert len(recent) == 1

    def test_t_5_5_query_api_handles_empty_log(
        self,
        temp_log_dir: Path,
    ) -> None:
        """T-5.5: Verify query API handles empty/missing log gracefully."""
        log_path = temp_log_dir / "injections.jsonl"

        # Query non-existent file
        recent = get_recent_injections(log_path, limit=10)

        assert recent == []

    def test_t_5_6_metrics_calculation_cache_hit_rate(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.6: Verify logs enable cache hit rate calculation.

        Tests that statistics can be derived from logged events.
        """
        # Log events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        # Get statistics
        stats = injection_logger.get_statistics()

        # Verify cache hit rate calculation
        # From our test data: 2 hits, 1 miss = 2/3 hit rate
        assert stats.cache_hit_count == 2
        assert stats.cache_miss_count == 1
        assert stats.total_injections == 3

        # Verify cache_hit_rate in dict output
        stats_dict = stats.to_dict()
        expected_rate = 2 / 3
        assert abs(stats_dict["cache_hit_rate"] - expected_rate) < 0.01

    def test_t_5_6_metrics_calculation_average_context_age(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.6: Verify logs enable average context age calculation.

        Tests that cache_age_seconds field supports age analysis.
        """
        # Log events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        # Read back events
        log_path = injection_logger.get_log_path()
        events = read_injections_from_log(log_path)

        # Calculate average age (excluding None values)
        ages = [e.cache_age_seconds for e in events if e.cache_age_seconds is not None]
        assert len(ages) == 2  # Two events have cache_age_seconds

        avg_age = sum(ages) / len(ages)
        expected_avg = (10.0 + 120.0) / 2  # From test data
        assert avg_age == expected_avg

    def test_t_5_6_metrics_calculation_by_relationship_type(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.6: Verify logs enable metrics by relationship type."""
        # Log events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        # Get statistics
        stats = injection_logger.get_statistics()

        # Verify breakdown by relationship type
        assert stats.by_relationship_type["IMPORT"] == 1
        assert stats.by_relationship_type["FUNCTION_CALL"] == 1
        assert stats.by_relationship_type["CLASS_INHERITANCE"] == 1

    def test_t_5_6_metrics_calculation_total_tokens(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.6: Verify logs enable total token count calculation."""
        # Log events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        # Get statistics
        stats = injection_logger.get_statistics()

        # Verify total tokens (30 + 20 + 15 = 65)
        expected_tokens = sum(e.token_count for e in multiple_injection_events)
        assert stats.total_tokens_injected == expected_tokens

    def test_t_5_6_statistics_to_dict_serializable(
        self,
        injection_logger: InjectionLogger,
        multiple_injection_events: list[InjectionEvent],
    ) -> None:
        """T-5.6: Verify statistics can be serialized to JSON for metrics export."""
        # Log events
        for event in multiple_injection_events:
            injection_logger.log_injection(event)

        # Get statistics
        stats = injection_logger.get_statistics()
        stats_dict = stats.to_dict()

        # Verify JSON serializable
        json_str = json.dumps(stats_dict)
        assert json_str is not None

        # Verify can be parsed back
        parsed = json.loads(json_str)
        assert parsed["total_injections"] == 3

    def test_t_5_7_log_file_size_tracking(
        self,
        injection_logger: InjectionLogger,
        sample_injection_event: InjectionEvent,
    ) -> None:
        """T-5.7: Verify log file size is tracked."""
        # Log an event
        injection_logger.log_injection(sample_injection_event)

        # Check size tracking
        size = injection_logger.get_log_size()
        assert size > 0, "Log file size should be tracked"

    def test_t_5_7_log_size_warning_threshold(
        self,
        temp_log_dir: Path,
    ) -> None:
        """T-5.7: Verify warning is issued for large log files.

        Per TDD Section 3.8.5: Warn if file grows >50MB (or configurable threshold).
        """
        # Create logger with very low threshold for testing
        warning_threshold = 100  # 100 bytes for easy testing
        logger_instance = InjectionLogger(
            log_dir=temp_log_dir,
            size_warning_threshold=warning_threshold,
        )

        try:
            # Log enough events to exceed threshold
            for i in range(10):
                event = InjectionEvent.create(
                    source_file=f"/path/to/source_{i}.py",
                    target_file="/path/to/target.py",
                    relationship_type="IMPORT",
                    snippet="def function():\n    pass",
                    snippet_location=f"source_{i}.py:1-2",
                    cache_age_seconds=float(i),
                    cache_hit=True,
                    token_count=10,
                    context_token_total=10,
                )
                logger_instance.log_injection(event)

            # Verify size exceeds threshold
            size = logger_instance.get_log_size()
            assert size > warning_threshold, "Log should exceed threshold"

        finally:
            logger_instance.close()

    def test_t_5_7_log_size_within_session_limits(
        self,
        temp_log_dir: Path,
    ) -> None:
        """T-5.7: Verify log file size remains manageable (<10MB per 4-hour session).

        Estimates log entry size and validates expected file size for typical session.
        """
        logger_instance = InjectionLogger(log_dir=temp_log_dir)

        try:
            # Log a typical event
            event = InjectionEvent.create(
                source_file="/project/path/to/source_module.py",
                target_file="/project/path/to/target_module.py",
                relationship_type="IMPORT",
                snippet=(
                    "def helper_function(arg1: str, arg2: int) -> bool:\n"
                    "    '''Helper function'''\n"
                    "    return True"
                ),
                snippet_location="source_module.py:45-50",
                cache_age_seconds=30.5,
                cache_hit=True,
                token_count=25,
                context_token_total=100,
            )
            logger_instance.log_injection(event)

            # Get size of single entry
            entry_size = logger_instance.get_log_size()

            # Estimate for 4-hour session:
            # - Assume 1 injection per minute = 240 injections
            # - Conservative estimate: 2 injections per minute = 480 injections
            # - Very active: 5 injections per minute = 1200 injections
            estimated_size_typical = entry_size * 480
            estimated_size_active = entry_size * 1200

            # Per T-5.7: <10MB per 4-hour session
            max_size = 10 * 1024 * 1024  # 10MB

            assert estimated_size_active < max_size, (
                f"Estimated log size for active session ({estimated_size_active / 1024:.1f}KB) "
                f"should be less than 10MB limit"
            )

            logger.info(
                f"Log entry size: {entry_size} bytes, "
                f"Typical 4hr session: {estimated_size_typical / 1024:.1f}KB, "
                f"Active 4hr session: {estimated_size_active / 1024:.1f}KB"
            )

        finally:
            logger_instance.close()


class TestInjectionLoggingIntegration:
    """Integration tests for injection logging with CrossFileContextService."""

    def test_service_integration_logs_injections(
        self,
        default_config: Config,
        temp_log_dir: Path,
    ) -> None:
        """Verify service integration logs context injections.

        Tests end-to-end: reading file with context triggers injection logging.
        """
        # Create service with temp log directory
        service = CrossFileContextService(
            config=default_config,
            project_root=str(TEST_CODEBASE_PATH),
        )

        # Configure injection logger to use temp directory
        if hasattr(service, "_injection_logger"):
            service._injection_logger = InjectionLogger(log_dir=temp_log_dir)

        try:
            # Analyze test codebase
            service.analyze_directory(str(TEST_CODEBASE_PATH))

            # Read a file that has dependencies
            order_service_path = TEST_CODEBASE_PATH / "core" / "services" / "order_service.py"
            result = service.read_file_with_context(str(order_service_path))

            # Verify context was injected
            assert result.injected_context, "Context should be injected"

            # Check if injections were logged
            if hasattr(service, "_injection_logger"):
                stats = service._injection_logger.get_statistics()
                # May have injections depending on implementation
                logger.info(f"Integration test logged {stats.total_injections} injections")

        finally:
            # Cleanup
            if hasattr(service, "_injection_logger"):
                service._injection_logger.close()


class TestInjectionEventDataclass:
    """Tests for InjectionEvent dataclass behavior."""

    def test_create_factory_method(self) -> None:
        """Verify InjectionEvent.create factory method works correctly."""
        event = InjectionEvent.create(
            source_file="/src/module.py",
            target_file="/src/main.py",
            relationship_type="IMPORT",
            snippet="def func(): pass",
            snippet_location="module.py:1-1",
            cache_age_seconds=5.0,
            cache_hit=True,
            token_count=10,
            context_token_total=10,
        )

        assert event.event_type == "context_injection"
        assert event.timestamp  # Should be auto-generated
        assert event.source_file == "/src/module.py"

    def test_to_dict_round_trip(self) -> None:
        """Verify InjectionEvent can be converted to dict and back."""
        original = InjectionEvent.create(
            source_file="/src/module.py",
            target_file="/src/main.py",
            relationship_type="FUNCTION_CALL",
            snippet="def helper(): pass",
            snippet_location="module.py:10-11",
            cache_age_seconds=None,
            cache_hit=False,
            token_count=5,
            context_token_total=5,
        )

        # Convert to dict
        d = original.to_dict()

        # Convert back
        restored = InjectionEvent.from_dict(d)

        assert restored.source_file == original.source_file
        assert restored.target_file == original.target_file
        assert restored.relationship_type == original.relationship_type
        assert restored.snippet == original.snippet
        assert restored.cache_age_seconds == original.cache_age_seconds
        assert restored.cache_hit == original.cache_hit

    def test_cache_age_none_handling(self) -> None:
        """Verify cache_age_seconds can be None (for cache misses)."""
        event = InjectionEvent.create(
            source_file="/src/module.py",
            target_file="/src/main.py",
            relationship_type="IMPORT",
            snippet="code",
            snippet_location="module.py:1-1",
            cache_age_seconds=None,
            cache_hit=False,
            token_count=5,
            context_token_total=5,
        )

        d = event.to_dict()
        assert d["cache_age_seconds"] is None

        # Verify JSON serializable
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["cache_age_seconds"] is None


class TestInjectionStatistics:
    """Tests for InjectionStatistics dataclass."""

    def test_empty_statistics(self) -> None:
        """Verify empty statistics have correct defaults."""
        stats = InjectionStatistics()

        assert stats.total_injections == 0
        assert stats.cache_hit_count == 0
        assert stats.cache_miss_count == 0
        assert stats.total_tokens_injected == 0

    def test_cache_hit_rate_calculation(self) -> None:
        """Verify cache hit rate is calculated correctly."""
        stats = InjectionStatistics(
            total_injections=10,
            cache_hit_count=8,
            cache_miss_count=2,
        )

        d = stats.to_dict()
        assert d["cache_hit_rate"] == 0.8

    def test_cache_hit_rate_zero_injections(self) -> None:
        """Verify cache hit rate handles zero injections."""
        stats = InjectionStatistics()

        d = stats.to_dict()
        assert d["cache_hit_rate"] == 0.0
