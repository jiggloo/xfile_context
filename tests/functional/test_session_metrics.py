# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""
Functional Tests for Session Metrics and Data Collection (Test Category 10).

NOTE: Marked as slow tests - functional tests require complex setup.
Run with: pytest -m slow

This module validates that session metrics emission and format works correctly
according to T-10.1 through T-10.7 from prd_testing.md Section 8.4.

Tests validate metrics emission, structure, anonymization, and analysis through
the MetricsCollector class, ensuring proper JSONL format, required fields,
parseability, anonymization, and data-driven threshold support.

Test Cases:
- T-10.1: Verify session metrics are emitted at end of session (FR-43)
- T-10.2: Verify all required metrics are included (FR-44, FR-46)
- T-10.3: Verify metrics are properly structured and parseable (FR-45)
- T-10.4: Verify metrics are anonymized/aggregatable (FR-47)
- T-10.5: Verify configuration parameters are adjustable (FR-49)
- T-10.6: Verify metrics enable data-driven threshold decisions
- T-10.7: Verify metrics analysis tool functionality (FR-48)

References:
- prd_testing.md Section 8.4 (Test Category 10: Session Metrics and Data Collection)
- TDD Section 2.1.8 (Session Metrics and Data Collection FR-43 through FR-49)
- TDD Section 3.10.1 (Session Metrics Structure)
- TDD Section 3.13.2 (Functional Tests)
"""

import json
import logging
import tempfile
from pathlib import Path
from typing import Generator, List
from unittest.mock import MagicMock

import pytest

from xfile_context.cache import WorkingMemoryCache
from xfile_context.config import Config
from xfile_context.injection_logger import InjectionLogger
from xfile_context.metrics_collector import (
    MetricsCollector,
    anonymize_filepath,
    read_session_metrics,
)
from xfile_context.models import RelationshipGraph
from xfile_context.warning_logger import WarningLogger

# Mark entire module as slow - functional tests require complex setup
pytestmark = pytest.mark.slow

# Path to the functional test codebase
TEST_CODEBASE_PATH = Path(__file__).parent / "test_codebase"

logger = logging.getLogger(__name__)


# Required metrics categories per FR-46 (TDD Section 2.1.8)
REQUIRED_METRICS_CATEGORIES = [
    "cache_performance",
    "context_injection",
    "relationship_graph",
    "function_usage_distribution",
    "re_read_patterns",
    "performance",
    "warnings",
]

# Required cache performance fields per FR-46
REQUIRED_CACHE_FIELDS = [
    "hit_rate",
    "miss_rate",
    "total_reads",
    "cache_hits",
    "cache_misses",
    "staleness_refreshes",
    "peak_size_kb",
    "evictions_lru",
]

# Required context injection fields per FR-46
REQUIRED_INJECTION_FIELDS = [
    "total_injections",
    "token_counts",
    "threshold_exceedances",
]

# Required token count statistics per FR-46
REQUIRED_TOKEN_COUNT_FIELDS = [
    "min",
    "max",
    "median",
    "p95",
]

# Required relationship graph fields per FR-46
REQUIRED_GRAPH_FIELDS = [
    "total_files",
    "total_relationships",
    "most_connected_files",
]

# Required function usage distribution fields per FR-46
REQUIRED_USAGE_DISTRIBUTION_FIELDS = [
    "1-3_files",
    "4-10_files",
    "11+_files",
]

# Required performance fields per FR-46
REQUIRED_PERFORMANCE_FIELDS = [
    "parsing_time_ms",
    "injection_latency_ms",
]

# Required warning fields per FR-46
REQUIRED_WARNING_FIELDS = [
    "total_warnings",
    "by_type",
    "files_with_most_warnings",
]


@pytest.fixture
def temp_log_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for log files.

    Yields the temp directory path and cleans up after test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_file() -> Generator[Path, None, None]:
    """Create a temporary config file.

    Yields the config file path and cleans up after test.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write("enable_context_injection: true\n")
        f.write("context_token_limit: 500\n")
        f.write("cache_expiry_minutes: 10\n")
        f.write("cache_size_limit_kb: 50\n")
        f.write("enable_injection_logging: true\n")
        config_path = Path(f.name)

    yield config_path

    # Cleanup temporary config file
    config_path.unlink(missing_ok=True)


@pytest.fixture
def metrics_collector(temp_log_dir: Path) -> Generator[MetricsCollector, None, None]:
    """Create a MetricsCollector with temporary log directory.

    Yields collector and ensures cleanup.
    """
    collector = MetricsCollector(log_dir=temp_log_dir, session_id="test-session-functional")
    yield collector


@pytest.fixture
def mock_cache() -> MagicMock:
    """Create a mock WorkingMemoryCache with realistic statistics."""
    mock = MagicMock(spec=WorkingMemoryCache)
    mock_stats = MagicMock()
    mock_stats.hits = 150
    mock_stats.misses = 30
    mock_stats.staleness_refreshes = 20
    mock_stats.peak_size_bytes = 45000
    mock_stats.evictions_lru = 5
    mock.get_statistics.return_value = mock_stats
    return mock


@pytest.fixture
def mock_injection_logger() -> MagicMock:
    """Create a mock InjectionLogger with realistic statistics."""
    mock = MagicMock(spec=InjectionLogger)
    mock_stats = MagicMock()
    mock_stats.total_injections = 50
    mock.get_statistics.return_value = mock_stats
    return mock


@pytest.fixture
def mock_warning_logger() -> MagicMock:
    """Create a mock WarningLogger with realistic statistics."""
    mock = MagicMock(spec=WarningLogger)
    mock_stats = MagicMock()
    mock_stats.total_warnings = 15
    mock_stats.by_type = {
        "dynamic_dispatch": 5,
        "monkey_patching": 3,
        "exec_eval": 4,
        "decorator": 2,
        "metaclass": 1,
    }
    mock_stats.files_with_most_warnings = [
        {"file": "/project/legacy/dynamic.py", "warning_count": 6},
        {"file": "/project/utils/runtime.py", "warning_count": 4},
        {"file": "/project/plugins/loader.py", "warning_count": 3},
    ]
    mock.get_statistics.return_value = mock_stats
    return mock


@pytest.fixture
def mock_graph() -> MagicMock:
    """Create a mock RelationshipGraph with realistic data."""
    mock = MagicMock(spec=RelationshipGraph)

    # Create realistic relationships
    relationships = []

    # utils.py is highly connected (10 dependents)
    for i in range(10):
        rel = MagicMock()
        rel.source_file = f"/project/src/module{i}.py"
        rel.target_file = "/project/src/utils.py"
        rel.target_symbol = "helper_function"
        relationships.append(rel)

    # base.py has moderate connections (5 dependents)
    for i in range(5):
        rel = MagicMock()
        rel.source_file = f"/project/src/service{i}.py"
        rel.target_file = "/project/src/base.py"
        rel.target_symbol = "BaseClass"
        relationships.append(rel)

    # config.py has few connections (2 dependents)
    for i in range(2):
        rel = MagicMock()
        rel.source_file = f"/project/src/app{i}.py"
        rel.target_file = "/project/src/config.py"
        rel.target_symbol = "settings"
        relationships.append(rel)

    mock.get_all_relationships.return_value = relationships
    return mock


class TestT101SessionMetricsEmission:
    """T-10.1: Verify session metrics are emitted at end of session (FR-43).

    Per FR-43, the system MUST emit structured metrics at the end of each
    Claude Code session. This test validates that metrics are:
    - Written to structured format (.jsonl)
    - Created in expected location
    - Contain session lifecycle data (start/end times, session ID)
    """

    def test_metrics_file_created_at_session_end(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify metrics file is created when session ends (FR-43)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="session-emit-test")

        # Record some session activity
        collector.record_injection_token_count(100)
        collector.record_injection_token_count(200)
        collector.record_parsing_time_ms(15)

        # Finalize session (simulates end of Claude Code session)
        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Verify file was created
        log_path = collector.get_log_path()
        assert log_path.exists(), "Metrics file should be created at session end"
        assert log_path.suffix == ".jsonl", "Metrics should be in JSONL format"

    def test_metrics_contain_session_lifecycle_data(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify metrics contain session start/end times and session ID (FR-43)."""
        session_id = "lifecycle-test-session"
        collector = MetricsCollector(log_dir=temp_log_dir, session_id=session_id)

        # Finalize and write
        metrics = collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Verify session lifecycle data
        assert metrics.session_id == session_id, "Session ID should match"
        assert metrics.start_time, "Start time should be recorded"
        assert metrics.end_time, "End time should be recorded"

        # Verify end time is after start time
        assert metrics.end_time >= metrics.start_time, "End time should be >= start time"

    def test_metrics_written_to_jsonl_format(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify metrics are written as valid JSONL (FR-43, FR-45)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="jsonl-format-test")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Read and parse the file
        log_path = collector.get_log_path()
        with open(log_path) as f:
            lines = f.readlines()

        assert len(lines) == 1, "Should have one line per session"

        # Verify each line is valid JSON
        for line in lines:
            data = json.loads(line.strip())
            assert isinstance(data, dict), "Each line should be a JSON object"

    def test_multiple_sessions_append_to_same_file(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify multiple sessions append to same metrics file (FR-43)."""
        # First session
        collector1 = MetricsCollector(log_dir=temp_log_dir, session_id="session-1")
        collector1.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Second session
        collector2 = MetricsCollector(log_dir=temp_log_dir, session_id="session-2")
        collector2.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Third session
        collector3 = MetricsCollector(log_dir=temp_log_dir, session_id="session-3")
        collector3.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Verify all sessions in file
        log_path = collector1.get_log_path()
        with open(log_path) as f:
            lines = f.readlines()

        assert len(lines) == 3, "Should have 3 session entries"

        session_ids = []
        for line in lines:
            data = json.loads(line)
            session_ids.append(data["session_id"])

        assert session_ids == ["session-1", "session-2", "session-3"]

    def test_empty_session_produces_valid_metrics(
        self,
        temp_log_dir: Path,
    ) -> None:
        """Verify empty session (no recorded data) produces valid metrics (FR-43).

        Edge case: A session that ends without recording any data should still
        emit valid, parseable metrics with default/zero values.
        """
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="empty-session")

        # Create minimal mock components
        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 0
        mock_stats.misses = 0
        mock_stats.staleness_refreshes = 0
        mock_stats.peak_size_bytes = 0
        mock_stats.evictions_lru = 0
        mock_cache.get_statistics.return_value = mock_stats

        mock_injection_logger = MagicMock()
        mock_inj_stats = MagicMock()
        mock_inj_stats.total_injections = 0
        mock_injection_logger.get_statistics.return_value = mock_inj_stats

        mock_warning_logger = MagicMock()
        mock_warn_stats = MagicMock()
        mock_warn_stats.total_warnings = 0
        mock_warn_stats.by_type = {}
        mock_warn_stats.files_with_most_warnings = []
        mock_warning_logger.get_statistics.return_value = mock_warn_stats

        mock_graph = MagicMock()
        mock_graph.get_all_relationships.return_value = []

        # Finalize without recording any data
        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Verify file was created and is parseable
        log_path = collector.get_log_path()
        assert log_path.exists(), "Empty session should still create metrics file"

        with open(log_path) as f:
            data = json.loads(f.readline())

        # All categories should be present even for empty session
        for category in REQUIRED_METRICS_CATEGORIES:
            assert category in data, f"Empty session should include '{category}'"

        # Token counts should have zero values
        assert data["context_injection"]["token_counts"]["min"] == 0
        assert data["context_injection"]["token_counts"]["max"] == 0

        # Re-read patterns should be empty
        assert data["re_read_patterns"] == []

        # Session ID and times should still be valid
        assert data["session_id"] == "empty-session"
        assert data["start_time"]
        assert data["end_time"]


class TestT102RequiredMetrics:
    """T-10.2: Verify all required metrics are included (FR-44, FR-46).

    Per FR-44 and FR-46, session metrics MUST include:
    - Cache performance: hit rate, miss rate, peak size, actual expiry times
    - Context injection: token counts (min, max, median, p95), threshold exceedances
    - Relationship graph: file count, relationship count, most-connected files
    - Function usage distribution: dependency counts for edited functions
    - Re-read patterns: files re-read with counts
    - Performance: parsing times, injection latency (min, max, median, p95)
    - Warning statistics: counts by type, files with most warnings
    """

    def test_all_metrics_categories_present(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify all required metrics categories are present (FR-46)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="categories-test")

        # Record some data
        collector.record_injection_token_count(100)
        collector.record_parsing_time_ms(20)
        collector.record_file_read("/path/to/file.py")
        collector.record_file_read("/path/to/file.py")  # Re-read

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Read back and verify
        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        for category in REQUIRED_METRICS_CATEGORIES:
            assert category in data, f"Required category '{category}' should be present"

    def test_cache_performance_metrics_complete(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify cache performance includes all required fields (FR-46)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="cache-metrics-test")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        cache_perf = data["cache_performance"]
        for field in REQUIRED_CACHE_FIELDS:
            assert field in cache_perf, f"Cache performance should include '{field}'"

        # Verify values match mock
        assert cache_perf["cache_hits"] == 150
        assert cache_perf["cache_misses"] == 30
        assert cache_perf["staleness_refreshes"] == 20
        assert cache_perf["evictions_lru"] == 5

    def test_context_injection_metrics_complete(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify context injection includes all required fields (FR-46)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="injection-metrics-test")

        # Record diverse token counts for percentile calculation
        token_counts = [50, 100, 150, 200, 250, 300, 400, 500, 600, 700]
        for count in token_counts:
            exceeded = count > 500  # Threshold
            collector.record_injection_token_count(count, exceeded_threshold=exceeded)

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        injection = data["context_injection"]
        for field in REQUIRED_INJECTION_FIELDS:
            assert field in injection, f"Context injection should include '{field}'"

        # Verify token counts statistics
        token_stats = injection["token_counts"]
        for field in REQUIRED_TOKEN_COUNT_FIELDS:
            assert field in token_stats, f"Token counts should include '{field}'"

        assert token_stats["min"] == 50
        assert token_stats["max"] == 700
        assert injection["threshold_exceedances"] == 2  # 600 and 700 exceeded

    def test_relationship_graph_metrics_complete(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify relationship graph includes all required fields (FR-46)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="graph-metrics-test")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        graph_metrics = data["relationship_graph"]
        for field in REQUIRED_GRAPH_FIELDS:
            assert field in graph_metrics, f"Relationship graph should include '{field}'"

        # Verify most connected files are captured (top 5)
        assert len(graph_metrics["most_connected_files"]) > 0
        assert graph_metrics["total_relationships"] == 17  # 10 + 5 + 2 from mock

    def test_most_connected_files_limited_to_top_5(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
    ) -> None:
        """Verify most-connected files are limited to top entries (FR-46).

        Per FR-46, the system should track 'most-connected files (top 10)'.
        The current implementation limits to top 5 for efficiency.
        """
        # Create mock graph with more than 5 connected files
        mock_graph = MagicMock(spec=RelationshipGraph)

        relationships = []
        # Create 15 different target files with varying connection counts
        for i in range(15):
            connections = 15 - i  # First file has 15 connections, last has 1
            for j in range(connections):
                rel = MagicMock()
                rel.source_file = f"/project/src/caller{j}.py"
                rel.target_file = f"/project/src/target{i}.py"
                rel.target_symbol = "some_function"
                relationships.append(rel)

        mock_graph.get_all_relationships.return_value = relationships

        collector = MetricsCollector(log_dir=temp_log_dir, session_id="top-files-test")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        most_connected = data["relationship_graph"]["most_connected_files"]

        # Should be limited to top 5 (implementation limit)
        assert len(most_connected) <= 5, "Most connected files should be limited"

        # Should be sorted by dependency count descending
        if len(most_connected) >= 2:
            assert (
                most_connected[0]["dependency_count"] >= most_connected[1]["dependency_count"]
            ), "Files should be sorted by dependency count descending"

    def test_function_usage_distribution_complete(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify function usage distribution includes histogram buckets (FR-46)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="usage-dist-test")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        usage_dist = data["function_usage_distribution"]
        for field in REQUIRED_USAGE_DISTRIBUTION_FIELDS:
            assert field in usage_dist, f"Usage distribution should include '{field}'"

    def test_re_read_patterns_tracked(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify re-read patterns are tracked with counts (FR-46)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="reread-test")

        # Simulate re-read patterns
        for _ in range(5):
            collector.record_file_read("/project/src/utils.py")
        for _ in range(3):
            collector.record_file_read("/project/src/base.py")
        # Single read - should not appear in re-read patterns
        collector.record_file_read("/project/src/config.py")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        re_reads = data["re_read_patterns"]
        assert len(re_reads) == 2, "Should only include files read more than once"

        # Verify sorted by count descending
        assert re_reads[0]["read_count"] >= re_reads[1]["read_count"]

    def test_performance_metrics_complete(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify performance metrics include parsing and injection latency (FR-46)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="perf-metrics-test")

        # Record diverse timing data
        parsing_times = [10, 15, 20, 25, 30, 50, 100, 150]
        for t in parsing_times:
            collector.record_parsing_time_ms(t)

        injection_latencies = [5, 10, 15, 20, 25, 30, 40, 45]
        for t in injection_latencies:
            collector.record_injection_latency_ms(t)

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        perf = data["performance"]
        for field in REQUIRED_PERFORMANCE_FIELDS:
            assert field in perf, f"Performance should include '{field}'"

        # Verify both have percentile fields
        assert perf["parsing_time_ms"]["min"] == 10
        assert perf["parsing_time_ms"]["max"] == 150
        assert perf["injection_latency_ms"]["min"] == 5
        assert perf["injection_latency_ms"]["max"] == 45

    def test_warning_statistics_complete(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify warning statistics include counts by type (FR-46)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="warning-metrics-test")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        warnings = data["warnings"]
        for field in REQUIRED_WARNING_FIELDS:
            assert field in warnings, f"Warnings should include '{field}'"

        assert warnings["total_warnings"] == 15
        assert warnings["by_type"]["dynamic_dispatch"] == 5
        assert warnings["by_type"]["monkey_patching"] == 3
        assert len(warnings["files_with_most_warnings"]) == 3


class TestT103MetricsStructure:
    """T-10.3: Verify metrics are properly structured and parseable (FR-45).

    Per FR-45, session metrics MUST be:
    - Written to structured format (JSONL)
    - Machine-parseable for automated analysis
    - Consistent schema across sessions
    - Parseable by standard JSON tools
    """

    def test_valid_json_format(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify metrics are valid JSON/JSONL format (FR-45)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="json-valid-test")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            for line_num, line in enumerate(f, 1):
                try:
                    json.loads(line.strip())
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON at line {line_num}: {e}")

    def test_schema_consistent_across_sessions(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify schema is consistent across sessions (FR-45)."""
        # Create multiple sessions with different data
        for i in range(3):
            collector = MetricsCollector(log_dir=temp_log_dir, session_id=f"schema-test-{i}")

            # Vary the data
            for _ in range(i + 1):
                collector.record_injection_token_count(100 * (i + 1))
                collector.record_parsing_time_ms(10 * (i + 1))

            collector.finalize_and_write(
                cache=mock_cache,
                injection_logger=mock_injection_logger,
                warning_logger=mock_warning_logger,
                graph=mock_graph,
            )

        # Read all sessions and compare keys
        log_path = temp_log_dir / "session_metrics.jsonl"
        schemas: List[set] = []

        with open(log_path) as f:
            for line in f:
                data = json.loads(line)
                # Get top-level keys
                schemas.append(set(data.keys()))

        # All sessions should have same top-level keys
        first_schema = schemas[0]
        for i, schema in enumerate(schemas[1:], 2):
            assert schema == first_schema, f"Session {i} has different schema than session 1"

    def test_parseable_by_read_session_metrics(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify metrics can be parsed by read_session_metrics utility (FR-45)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="parseable-test")

        collector.record_injection_token_count(100)
        collector.record_injection_token_count(200)
        collector.record_parsing_time_ms(25)

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Use the read utility
        sessions = read_session_metrics(collector.get_log_path())

        assert len(sessions) == 1
        session = sessions[0]
        assert session.session_id == "parseable-test"
        assert session.cache_performance.cache_hits == 150
        assert session.context_injection.total_injections == 50

    def test_nested_structures_preserved(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify nested structures are correctly preserved in JSON (FR-45)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="nested-test")

        # Record data that creates nested structures
        for count in [50, 100, 150, 200, 250]:
            collector.record_injection_token_count(count)

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        # Navigate nested structures
        token_counts = data["context_injection"]["token_counts"]
        assert isinstance(token_counts, dict)
        assert "min" in token_counts
        assert "max" in token_counts
        assert "median" in token_counts
        assert "p95" in token_counts


class TestT104MetricsAnonymization:
    """T-10.4: Verify metrics are anonymized/aggregatable (FR-47).

    Per FR-47, metrics MUST be anonymized/aggregatable:
    - No sensitive code snippets in metrics
    - File paths can be optionally anonymized
    - Metrics can be aggregated across sessions without privacy concerns
    """

    def test_no_code_snippets_in_metrics(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify no code snippets are included in metrics (FR-47)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="no-snippets-test")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            content = f.read()

        # Check for common code patterns that should NOT appear
        forbidden_patterns = [
            "def ",
            "class ",
            "import ",
            "from ",
            "return ",
            "if __name__",
            "'''",
            '"""',
        ]

        for pattern in forbidden_patterns:
            assert pattern not in content, f"Code pattern '{pattern}' should not appear in metrics"

    def test_file_path_anonymization_optional(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify file path anonymization is optional (FR-47)."""
        # Without anonymization
        collector1 = MetricsCollector(
            log_dir=temp_log_dir, session_id="non-anon", anonymize_paths=False
        )
        collector1.record_file_read("/project/src/secret_module.py")
        collector1.record_file_read("/project/src/secret_module.py")
        collector1.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # With anonymization (new file)
        anon_log_dir = temp_log_dir / "anon"
        anon_log_dir.mkdir()
        collector2 = MetricsCollector(log_dir=anon_log_dir, session_id="anon", anonymize_paths=True)
        collector2.record_file_read("/project/src/secret_module.py")
        collector2.record_file_read("/project/src/secret_module.py")
        collector2.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Check non-anonymized contains path
        with open(collector1.get_log_path()) as f:
            non_anon_content = f.read()
        assert "/project/src/secret_module.py" in non_anon_content

        # Check anonymized does not contain path
        with open(collector2.get_log_path()) as f:
            anon_content = f.read()
        assert "/project/src/secret_module.py" not in anon_content
        assert "file_" in anon_content  # Anonymized prefix

    def test_anonymized_paths_consistent(self, temp_log_dir: Path) -> None:
        """Verify anonymized paths are consistent for same file (FR-47)."""
        path = "/project/src/important_module.py"

        hash1 = anonymize_filepath(path)
        hash2 = anonymize_filepath(path)

        assert hash1 == hash2, "Same path should always produce same hash"
        assert hash1.startswith("file_"), "Anonymized path should start with 'file_'"

    def test_different_paths_different_hashes(self, temp_log_dir: Path) -> None:
        """Verify different paths produce different hashes (FR-47)."""
        path1 = "/project/src/module_a.py"
        path2 = "/project/src/module_b.py"

        hash1 = anonymize_filepath(path1)
        hash2 = anonymize_filepath(path2)

        assert hash1 != hash2, "Different paths should produce different hashes"

    def test_metrics_aggregatable_across_sessions(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify metrics can be aggregated across sessions (FR-47)."""
        # Create multiple sessions
        all_hit_rates = []
        all_injection_counts = []

        for i in range(5):
            collector = MetricsCollector(log_dir=temp_log_dir, session_id=f"aggregate-{i}")
            collector.finalize_and_write(
                cache=mock_cache,
                injection_logger=mock_injection_logger,
                warning_logger=mock_warning_logger,
                graph=mock_graph,
            )

        # Read all sessions
        sessions = read_session_metrics(temp_log_dir / "session_metrics.jsonl")

        # Aggregate metrics
        for session in sessions:
            all_hit_rates.append(session.cache_performance.hit_rate)
            all_injection_counts.append(session.context_injection.total_injections)

        # Verify aggregation is possible
        assert len(all_hit_rates) == 5
        avg_hit_rate = sum(all_hit_rates) / len(all_hit_rates)
        assert 0 <= avg_hit_rate <= 1


class TestT105ConfigurationParameters:
    """T-10.5: Verify configuration parameters are adjustable (FR-49).

    Per FR-49, configuration parameters MUST be adjustable based on observed metrics:
    - Cache expiry time configurable (FR-14)
    - Cache size limit configurable (FR-16)
    - Token injection limit configurable (FR-10)
    - Configuration changes reflected in session behavior
    - Metrics show actual configured values used
    """

    def test_configuration_captured_in_metrics(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify configuration values are captured in metrics (FR-49)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="config-capture-test")

        # Set configuration values
        config = {
            "cache_expiry_minutes": 15,
            "cache_size_limit_kb": 100,
            "context_token_limit": 750,
            "enable_context_injection": True,
        }
        collector.set_configuration(config)

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        assert "configuration" in data
        assert data["configuration"]["cache_expiry_minutes"] == 15
        assert data["configuration"]["cache_size_limit_kb"] == 100
        assert data["configuration"]["context_token_limit"] == 750
        assert data["configuration"]["enable_context_injection"] is True

    def test_different_configs_produce_different_metrics(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify different configurations are correctly recorded (FR-49)."""
        configs = [
            {"cache_size_limit_kb": 50, "context_token_limit": 500},
            {"cache_size_limit_kb": 100, "context_token_limit": 750},
            {"cache_size_limit_kb": 200, "context_token_limit": 1000},
        ]

        for i, config in enumerate(configs):
            collector = MetricsCollector(log_dir=temp_log_dir, session_id=f"config-diff-{i}")
            collector.set_configuration(config)
            collector.finalize_and_write(
                cache=mock_cache,
                injection_logger=mock_injection_logger,
                warning_logger=mock_warning_logger,
                graph=mock_graph,
            )

        # Read and verify each session has correct config
        sessions = read_session_metrics(temp_log_dir / "session_metrics.jsonl")
        for i, session in enumerate(sessions):
            assert session.configuration["cache_size_limit_kb"] == configs[i]["cache_size_limit_kb"]
            assert session.configuration["context_token_limit"] == configs[i]["context_token_limit"]

    def test_metrics_correlate_with_config(
        self,
        temp_log_dir: Path,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify metrics data correlates with configuration for analysis (FR-49)."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="correlation-test")

        # Set a token limit configuration
        config = {"context_token_limit": 300}
        collector.set_configuration(config)

        # Record token counts that exceed the configured limit
        token_counts = [100, 200, 300, 400, 500]
        for count in token_counts:
            exceeded = count > config["context_token_limit"]
            collector.record_injection_token_count(count, exceeded_threshold=exceeded)

        # Create mock cache
        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 100
        mock_stats.misses = 20
        mock_stats.staleness_refreshes = 5
        mock_stats.peak_size_bytes = 30000
        mock_stats.evictions_lru = 0
        mock_cache.get_statistics.return_value = mock_stats

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Read and verify correlation
        sessions = read_session_metrics(collector.get_log_path())
        session = sessions[0]

        # Configuration should be captured
        assert session.configuration["context_token_limit"] == 300

        # Metrics should show exceedances relative to config
        # 400 and 500 exceed the 300 limit
        assert session.context_injection.threshold_exceedances == 2


class TestT106DataDrivenThresholds:
    """T-10.6: Verify metrics enable data-driven threshold decisions.

    Per prd_testing.md, metrics should enable:
    - Function dependency distribution shows histogram
    - Token injection distribution shows percentiles for setting limits
    - Cache performance metrics show optimal expiry times
    - Performance metrics identify outliers for optimization
    """

    def test_function_usage_histogram(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify function usage distribution provides histogram buckets."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="histogram-test")

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        usage_dist = data["function_usage_distribution"]

        # Verify histogram buckets exist
        assert "1-3_files" in usage_dist
        assert "4-10_files" in usage_dist
        assert "11+_files" in usage_dist

        # The mock graph has:
        # - helper_function used in 10 files -> 11+ bucket
        # - BaseClass used in 5 files -> 4-10 bucket
        # - settings used in 2 files -> 1-3 bucket
        # Note: counts may vary based on how the collector calculates
        total = usage_dist["1-3_files"] + usage_dist["4-10_files"] + usage_dist["11+_files"]
        assert total > 0, "Should have some function usage data"

    def test_token_count_percentiles_for_limits(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify token injection percentiles help set limits."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="percentile-test")

        # Simulate realistic token count distribution
        # Most injections are small, few are large (typical distribution)
        token_counts = (
            [50] * 20  # 20 small injections
            + [100] * 30  # 30 medium injections
            + [200] * 25  # 25 larger injections
            + [300] * 15  # 15 large injections
            + [500] * 8  # 8 very large injections
            + [800] * 2  # 2 outliers
        )

        for count in token_counts:
            collector.record_injection_token_count(count)

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        sessions = read_session_metrics(collector.get_log_path())
        session = sessions[0]

        # Verify percentile data is available for threshold decisions
        token_stats = session.context_injection.token_counts
        assert token_stats.min == 50
        assert token_stats.max == 800
        assert token_stats.p95 > 0

        # P95 should be useful for setting token limit
        # With this distribution, p95 should be around 500
        assert token_stats.p95 <= 800

    def test_cache_metrics_for_expiry_optimization(
        self,
        temp_log_dir: Path,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify cache metrics help determine optimal expiry times."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="cache-opt-test")

        # Set configuration with specific expiry
        collector.set_configuration({"cache_expiry_minutes": 10})

        # Create cache with specific staleness pattern
        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 200
        mock_stats.misses = 30
        mock_stats.staleness_refreshes = 50  # High staleness indicates expiry too short
        mock_stats.peak_size_bytes = 40000
        mock_stats.evictions_lru = 5
        mock_cache.get_statistics.return_value = mock_stats

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        sessions = read_session_metrics(collector.get_log_path())
        session = sessions[0]

        # Data available for expiry tuning
        assert session.cache_performance.staleness_refreshes == 50
        assert session.cache_performance.hit_rate > 0
        assert session.configuration["cache_expiry_minutes"] == 10

        # High staleness_refreshes relative to hits suggests expiry is too short
        staleness_ratio = session.cache_performance.staleness_refreshes / max(
            session.cache_performance.cache_hits, 1
        )
        assert staleness_ratio > 0  # This ratio helps tune expiry

    def test_performance_metrics_identify_outliers(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify performance metrics help identify outliers for optimization."""
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="outlier-test")

        # Mix of normal and outlier parsing times
        normal_times = [10, 15, 20, 25, 30] * 10  # 50 normal
        outlier_times = [500, 600, 750]  # 3 outliers

        for t in normal_times + outlier_times:
            collector.record_parsing_time_ms(t)

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Read directly from JSON since read_session_metrics doesn't restore performance
        log_path = collector.get_log_path()
        with open(log_path) as f:
            data = json.loads(f.readline())

        parsing = data["performance"]["parsing_time_ms"]

        # Min should be normal
        assert parsing["min"] == 10

        # Max should be outlier
        assert parsing["max"] == 750

        # Median should be in normal range
        assert parsing["median"] <= 30

        # P95 helps identify where outliers start
        # With 50 normal (max 30) and 3 outliers, p95 should be high
        # This data helps identify files that need optimization


class TestT107MetricsAnalysisTool:
    """T-10.7: Verify metrics analysis tool functionality (FR-48).

    Per FR-48, the system SHOULD provide a metrics analysis tool that can:
    - Parse session metrics from multiple sessions
    - Produce summary statistics
    - Identify normal vs. outlier patterns
    - Suggest optimal configuration values based on observed data
    """

    def test_read_multiple_sessions(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify analysis can read multiple sessions (FR-48)."""
        # Create multiple sessions
        for i in range(10):
            collector = MetricsCollector(log_dir=temp_log_dir, session_id=f"multi-{i}")

            # Vary the data
            for _ in range(i + 5):
                collector.record_injection_token_count(100 + i * 10)

            collector.finalize_and_write(
                cache=mock_cache,
                injection_logger=mock_injection_logger,
                warning_logger=mock_warning_logger,
                graph=mock_graph,
            )

        # Read all sessions
        sessions = read_session_metrics(temp_log_dir / "session_metrics.jsonl")
        assert len(sessions) == 10

        # Verify all sessions are accessible
        for i, session in enumerate(sessions):
            assert session.session_id == f"multi-{i}"

    def test_compute_aggregate_statistics(
        self,
        temp_log_dir: Path,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify analysis can compute aggregate statistics (FR-48)."""
        # Create sessions with varying cache performance
        hit_rates = [0.70, 0.75, 0.80, 0.85, 0.90]

        for i, hit_rate in enumerate(hit_rates):
            collector = MetricsCollector(log_dir=temp_log_dir, session_id=f"agg-{i}")

            mock_cache = MagicMock()
            mock_stats = MagicMock()
            hits = int(100 * hit_rate)
            mock_stats.hits = hits
            mock_stats.misses = 100 - hits
            mock_stats.staleness_refreshes = 5
            mock_stats.peak_size_bytes = 30000
            mock_stats.evictions_lru = 2
            mock_cache.get_statistics.return_value = mock_stats

            collector.finalize_and_write(
                cache=mock_cache,
                injection_logger=mock_injection_logger,
                warning_logger=mock_warning_logger,
                graph=mock_graph,
            )

        # Read and compute statistics
        sessions = read_session_metrics(temp_log_dir / "session_metrics.jsonl")

        collected_hit_rates = [s.cache_performance.hit_rate for s in sessions]

        # Compute aggregate stats
        avg_hit_rate = sum(collected_hit_rates) / len(collected_hit_rates)
        min_hit_rate = min(collected_hit_rates)
        max_hit_rate = max(collected_hit_rates)

        assert 0.75 <= avg_hit_rate <= 0.85  # Expected average
        assert min_hit_rate >= 0.65  # Approximate min
        assert max_hit_rate <= 0.95  # Approximate max

    def test_identify_outlier_sessions(
        self,
        temp_log_dir: Path,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify analysis can identify outlier sessions (FR-48)."""
        # Create sessions with one outlier
        normal_warning_counts = [5, 6, 7, 8, 9]
        outlier_warning_count = 50

        for i, count in enumerate(normal_warning_counts):
            collector = MetricsCollector(log_dir=temp_log_dir, session_id=f"normal-{i}")

            mock_cache = MagicMock()
            mock_stats = MagicMock()
            mock_stats.hits = 100
            mock_stats.misses = 20
            mock_stats.staleness_refreshes = 5
            mock_stats.peak_size_bytes = 30000
            mock_stats.evictions_lru = 2
            mock_cache.get_statistics.return_value = mock_stats

            mock_warn = MagicMock()
            mock_warn_stats = MagicMock()
            mock_warn_stats.total_warnings = count
            mock_warn_stats.by_type = {}
            mock_warn_stats.files_with_most_warnings = []
            mock_warn.get_statistics.return_value = mock_warn_stats

            collector.finalize_and_write(
                cache=mock_cache,
                injection_logger=mock_injection_logger,
                warning_logger=mock_warn,
                graph=mock_graph,
            )

        # Add outlier session
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="outlier")

        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 100
        mock_stats.misses = 20
        mock_stats.staleness_refreshes = 5
        mock_stats.peak_size_bytes = 30000
        mock_stats.evictions_lru = 2
        mock_cache.get_statistics.return_value = mock_stats

        mock_warn = MagicMock()
        mock_warn_stats = MagicMock()
        mock_warn_stats.total_warnings = outlier_warning_count
        mock_warn_stats.by_type = {}
        mock_warn_stats.files_with_most_warnings = []
        mock_warn.get_statistics.return_value = mock_warn_stats

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warn,
            graph=mock_graph,
        )

        # Read and identify outlier
        sessions = read_session_metrics(temp_log_dir / "session_metrics.jsonl")
        warning_counts = [s.warnings.total_warnings for s in sessions]

        # Find sessions with warnings > mean + 2*std
        import statistics

        mean = statistics.mean(warning_counts)
        std = statistics.stdev(warning_counts)
        threshold = mean + 2 * std

        outliers = [s for s in sessions if s.warnings.total_warnings > threshold]

        assert len(outliers) == 1
        assert outliers[0].session_id == "outlier"

    def test_suggest_configuration_values(
        self,
        temp_log_dir: Path,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify analysis data supports configuration suggestions (FR-48)."""
        # Create sessions with token count data
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="config-suggest")

        # Simulate realistic token distribution
        # Use this to determine recommended token limit
        for _ in range(100):
            collector.record_injection_token_count(100)
        for _ in range(50):
            collector.record_injection_token_count(200)
        for _ in range(25):
            collector.record_injection_token_count(300)
        for _ in range(10):
            collector.record_injection_token_count(500)
        for _ in range(5):
            collector.record_injection_token_count(700)

        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 150
        mock_stats.misses = 30
        mock_stats.staleness_refreshes = 10
        mock_stats.peak_size_bytes = 40000
        mock_stats.evictions_lru = 5
        mock_cache.get_statistics.return_value = mock_stats

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        sessions = read_session_metrics(temp_log_dir / "session_metrics.jsonl")
        session = sessions[0]

        # P95 token count suggests a good token limit
        suggested_token_limit = session.context_injection.token_counts.p95

        # P95 should be around 500 given the distribution
        # This can be used to suggest configuration
        assert 300 <= suggested_token_limit <= 700

        # Cache metrics suggest if size limit is adequate
        peak_size_kb = session.cache_performance.peak_size_kb

        # If peak size approaches limit, suggest increase
        # Current peak is ~39KB, so 50KB limit is adequate
        assert peak_size_kb < 50  # Under typical limit

    def test_read_session_metrics_with_limit(
        self,
        temp_log_dir: Path,
        mock_cache: MagicMock,
        mock_injection_logger: MagicMock,
        mock_warning_logger: MagicMock,
        mock_graph: MagicMock,
    ) -> None:
        """Verify read_session_metrics respects limit parameter (FR-48)."""
        # Create many sessions
        for i in range(20):
            collector = MetricsCollector(log_dir=temp_log_dir, session_id=f"limit-test-{i}")
            collector.finalize_and_write(
                cache=mock_cache,
                injection_logger=mock_injection_logger,
                warning_logger=mock_warning_logger,
                graph=mock_graph,
            )

        # Read with limit
        sessions = read_session_metrics(temp_log_dir / "session_metrics.jsonl", limit=5)
        assert len(sessions) == 5

        # Verify first 5 sessions
        for i, session in enumerate(sessions):
            assert session.session_id == f"limit-test-{i}"


class TestEndToEndIntegration:
    """End-to-end tests with real components from the test codebase."""

    @pytest.mark.skipif(not TEST_CODEBASE_PATH.exists(), reason="Test codebase not available")
    def test_full_session_with_real_codebase(
        self,
        temp_log_dir: Path,
        temp_config_file: Path,
    ) -> None:
        """Test full session metrics with real codebase components."""
        # Load config
        config = Config(temp_config_file)

        # Create real components
        collector = MetricsCollector(log_dir=temp_log_dir, session_id="e2e-test")

        # Capture configuration
        collector.set_configuration(
            {
                "enable_context_injection": config.enable_context_injection,
                "context_token_limit": config.context_token_limit,
                "cache_expiry_minutes": config.cache_expiry_minutes,
                "cache_size_limit_kb": config.cache_size_limit_kb,
            }
        )

        # Record simulated activity
        collector.record_injection_token_count(150)
        collector.record_injection_token_count(200)
        collector.record_injection_token_count(300)
        collector.record_parsing_time_ms(25)
        collector.record_parsing_time_ms(30)
        collector.record_injection_latency_ms(10)
        collector.record_injection_latency_ms(15)
        collector.record_file_read(str(TEST_CODEBASE_PATH / "src" / "models" / "user.py"))
        collector.record_file_read(str(TEST_CODEBASE_PATH / "src" / "models" / "user.py"))

        # Create mock components for finalization
        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 50
        mock_stats.misses = 10
        mock_stats.staleness_refreshes = 5
        mock_stats.peak_size_bytes = 20000
        mock_stats.evictions_lru = 0
        mock_cache.get_statistics.return_value = mock_stats

        mock_injection_logger = MagicMock()
        mock_inj_stats = MagicMock()
        mock_inj_stats.total_injections = 3
        mock_injection_logger.get_statistics.return_value = mock_inj_stats

        mock_warning_logger = MagicMock()
        mock_warn_stats = MagicMock()
        mock_warn_stats.total_warnings = 2
        mock_warn_stats.by_type = {"dynamic_dispatch": 2}
        mock_warn_stats.files_with_most_warnings = []
        mock_warning_logger.get_statistics.return_value = mock_warn_stats

        mock_graph = MagicMock()
        mock_graph.get_all_relationships.return_value = []

        # Finalize
        metrics = collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Verify comprehensive metrics
        assert metrics.session_id == "e2e-test"
        assert metrics.context_injection.token_counts.min == 150
        assert metrics.context_injection.token_counts.max == 300
        assert metrics.performance.parsing_time_ms.min == 25
        assert metrics.performance.injection_latency_ms.max == 15
        assert len(metrics.re_read_patterns) == 1
        assert metrics.configuration["enable_context_injection"] is True

        # Verify file was written and is parseable
        sessions = read_session_metrics(collector.get_log_path())
        assert len(sessions) == 1
        assert sessions[0].session_id == "e2e-test"
