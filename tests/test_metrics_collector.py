# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Unit tests for MetricsCollector module.

Tests cover all metrics categories per TDD Section 3.10.1 and Section 3.4.9:
- Session lifecycle (start/end time, session ID)
- Cache performance metrics collection
- Context injection metrics with percentile calculation
- Relationship graph metrics
- Function usage distribution
- Re-read pattern tracking
- Performance metrics (parsing time, injection latency)
- Warning statistics
- Identifier resolution metrics
- JSONL file writing
- File path anonymization (FR-47)
- Configuration capture (FR-49)

Related Requirements:
- FR-43 through FR-49 (session metrics)
- T-10.1 through T-10.6 (session metrics tests)
"""

import json
import tempfile
import uuid
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

from xfile_context.metrics_collector import (
    CachePerformanceMetrics,
    ContextInjectionMetrics,
    FunctionUsageDistribution,
    IdentifierResolutionMetrics,
    MetricsCollector,
    RelationshipGraphMetrics,
    SessionMetrics,
    TokenCountStatistics,
    WarningStatisticsMetrics,
    anonymize_filepath,
    calculate_percentile_statistics,
    read_session_metrics,
)


class TestCalculatePercentileStatistics:
    """Tests for calculate_percentile_statistics function."""

    def test_empty_list_returns_zero_stats(self) -> None:
        """Empty list should return all zeros."""
        stats = calculate_percentile_statistics([])
        assert stats.min == 0
        assert stats.max == 0
        assert stats.median == 0
        assert stats.p95 == 0
        assert stats.total_count == 0

    def test_single_value(self) -> None:
        """Single value should be min, max, median, and p95."""
        stats = calculate_percentile_statistics([42])
        assert stats.min == 42
        assert stats.max == 42
        assert stats.median == 42
        assert stats.p95 == 42
        assert stats.total_count == 1

    def test_two_values(self) -> None:
        """Two values should calculate correctly."""
        stats = calculate_percentile_statistics([10, 20])
        assert stats.min == 10
        assert stats.max == 20
        assert stats.median == 15  # Python statistics.median
        assert stats.p95 == 20  # 95th percentile of 2 values
        assert stats.total_count == 2

    def test_multiple_values_unsorted(self) -> None:
        """Values should be sorted before calculation."""
        stats = calculate_percentile_statistics([50, 10, 30, 20, 40])
        assert stats.min == 10
        assert stats.max == 50
        assert stats.median == 30
        assert stats.total_count == 5

    def test_large_list_p95(self) -> None:
        """P95 should be calculated correctly for larger lists."""
        # Create list from 1 to 100
        values = list(range(1, 101))
        stats = calculate_percentile_statistics(values)
        assert stats.min == 1
        assert stats.max == 100
        assert stats.median == 50  # Middle value
        # p95 index = int(100 * 0.95) = 95, so value at index 95 = 96
        assert stats.p95 == 96
        assert stats.total_count == 100

    def test_duplicates(self) -> None:
        """Duplicate values should be handled correctly."""
        stats = calculate_percentile_statistics([5, 5, 5, 5, 5])
        assert stats.min == 5
        assert stats.max == 5
        assert stats.median == 5
        assert stats.p95 == 5


class TestTokenCountStatistics:
    """Tests for TokenCountStatistics dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        stats = TokenCountStatistics(min=10, max=100, median=50, p95=90, total_count=50)
        result = stats.to_dict()
        assert result == {"min": 10, "max": 100, "median": 50, "p95": 90}
        # total_count is not in to_dict (internal tracking only)

    def test_default_values(self) -> None:
        """Default values should all be zero."""
        stats = TokenCountStatistics()
        assert stats.min == 0
        assert stats.max == 0
        assert stats.median == 0
        assert stats.p95 == 0
        assert stats.total_count == 0


class TestCachePerformanceMetrics:
    """Tests for CachePerformanceMetrics dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        metrics = CachePerformanceMetrics(
            hit_rate=0.75,
            miss_rate=0.20,
            total_reads=100,
            cache_hits=75,
            cache_misses=20,
            staleness_refreshes=5,
            peak_size_kb=45.678,
            evictions_lru=10,
        )
        result = metrics.to_dict()
        assert result["hit_rate"] == 0.75
        assert result["miss_rate"] == 0.2
        assert result["total_reads"] == 100
        assert result["cache_hits"] == 75
        assert result["cache_misses"] == 20
        assert result["staleness_refreshes"] == 5
        assert result["peak_size_kb"] == 45.68  # Rounded to 2 decimal places
        assert result["evictions_lru"] == 10

    def test_default_values(self) -> None:
        """Default values should all be zero."""
        metrics = CachePerformanceMetrics()
        assert metrics.hit_rate == 0.0
        assert metrics.miss_rate == 0.0
        assert metrics.total_reads == 0


class TestContextInjectionMetrics:
    """Tests for ContextInjectionMetrics dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        metrics = ContextInjectionMetrics(
            total_injections=50,
            token_counts=TokenCountStatistics(min=10, max=500, median=150, p95=400),
            threshold_exceedances=3,
        )
        result = metrics.to_dict()
        assert result["total_injections"] == 50
        assert result["token_counts"]["min"] == 10
        assert result["token_counts"]["max"] == 500
        assert result["threshold_exceedances"] == 3


class TestRelationshipGraphMetrics:
    """Tests for RelationshipGraphMetrics dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        metrics = RelationshipGraphMetrics(
            total_files=150,
            total_relationships=450,
            most_connected_files=[
                {"file": "utils.py", "dependency_count": 45},
                {"file": "base.py", "dependency_count": 32},
            ],
        )
        result = metrics.to_dict()
        assert result["total_files"] == 150
        assert result["total_relationships"] == 450
        assert len(result["most_connected_files"]) == 2


class TestFunctionUsageDistribution:
    """Tests for FunctionUsageDistribution dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        dist = FunctionUsageDistribution(files_1_to_3=120, files_4_to_10=25, files_11_plus=5)
        result = dist.to_dict()
        assert result["1-3_files"] == 120
        assert result["4-10_files"] == 25
        assert result["11+_files"] == 5


class TestWarningStatisticsMetrics:
    """Tests for WarningStatisticsMetrics dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        metrics = WarningStatisticsMetrics(
            total_warnings=10,
            by_type={"circular_import": 2, "dynamic_dispatch": 5},
            files_with_most_warnings=[{"file": "legacy.py", "warning_count": 4}],
        )
        result = metrics.to_dict()
        assert result["total_warnings"] == 10
        assert result["by_type"]["circular_import"] == 2
        assert len(result["files_with_most_warnings"]) == 1


class TestIdentifierResolutionMetrics:
    """Tests for IdentifierResolutionMetrics dataclass."""

    def test_to_dict_with_data(self) -> None:
        """Test serialization with actual data."""
        metrics = IdentifierResolutionMetrics(
            function_calls_analyzed=100,
            resolved_to_imports=50,
            resolved_to_local=30,
            resolved_to_builtin=10,
            unresolved=10,
            unresolved_needed_for_context=5,
        )
        result = metrics.to_dict()
        assert result["function_calls_analyzed"] == 100
        assert result["resolved_to_imports"] == 50
        assert result["resolved_to_imports_pct"] == 50.0
        assert result["resolved_to_local_pct"] == 30.0
        assert result["unresolved_pct"] == 10.0
        assert result["unresolved_needed_for_context_pct"] == 5.0

    def test_to_dict_zero_total(self) -> None:
        """Test serialization with zero total (should avoid division by zero)."""
        metrics = IdentifierResolutionMetrics()
        result = metrics.to_dict()
        assert result["function_calls_analyzed"] == 0
        assert result["resolved_to_imports_pct"] == 0.0


class TestSessionMetrics:
    """Tests for SessionMetrics dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        metrics = SessionMetrics(
            session_id="test-session-123",
            start_time="2025-01-15T10:00:00.000Z",
            end_time="2025-01-15T12:00:00.000Z",
            configuration={"cache_size_limit_kb": 50},
        )
        result = metrics.to_dict()
        assert result["session_id"] == "test-session-123"
        assert result["start_time"] == "2025-01-15T10:00:00.000Z"
        assert result["end_time"] == "2025-01-15T12:00:00.000Z"
        assert result["configuration"]["cache_size_limit_kb"] == 50
        # Nested metrics should be present (even if default)
        assert "cache_performance" in result
        assert "context_injection" in result
        assert "relationship_graph" in result
        assert "warnings" in result


class TestAnonymizeFilepath:
    """Tests for anonymize_filepath function."""

    def test_anonymizes_filepath(self) -> None:
        """File path should be anonymized to hash."""
        result = anonymize_filepath("/path/to/file.py")
        assert result.startswith("file_")
        assert len(result) == 21  # "file_" + 16 chars

    def test_consistent_hash(self) -> None:
        """Same path should always produce same hash."""
        path = "/some/path/to/module.py"
        result1 = anonymize_filepath(path)
        result2 = anonymize_filepath(path)
        assert result1 == result2

    def test_different_paths_different_hashes(self) -> None:
        """Different paths should produce different hashes."""
        result1 = anonymize_filepath("/path/a.py")
        result2 = anonymize_filepath("/path/b.py")
        assert result1 != result2


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def collector(self, temp_dir: Path) -> MetricsCollector:
        """Create a MetricsCollector with temp directory."""
        return MetricsCollector(log_dir=temp_dir)

    def test_init_generates_session_id(self, temp_dir: Path) -> None:
        """Session ID should be auto-generated if not provided."""
        collector = MetricsCollector(log_dir=temp_dir)
        session_id = collector.get_session_id()
        # Should be a valid UUID
        uuid.UUID(session_id)

    def test_init_uses_provided_session_id(self, temp_dir: Path) -> None:
        """Provided session ID should be used."""
        collector = MetricsCollector(log_dir=temp_dir, session_id="my-custom-id")
        assert collector.get_session_id() == "my-custom-id"

    def test_init_rejects_path_in_log_file(self, temp_dir: Path) -> None:
        """Log file with path separators should be rejected."""
        with pytest.raises(ValueError, match="filename only"):
            MetricsCollector(log_dir=temp_dir, log_file="subdir/metrics.jsonl")

    def test_record_injection_token_count(self, collector: MetricsCollector) -> None:
        """Token counts should be recorded."""
        collector.record_injection_token_count(100)
        collector.record_injection_token_count(200)
        collector.record_injection_token_count(150)

        # The collector tracks token counts internally
        assert collector._token_counts == [100, 200, 150]

    def test_record_injection_token_count_with_threshold_exceedance(
        self, collector: MetricsCollector
    ) -> None:
        """Threshold exceedances should be counted."""
        collector.record_injection_token_count(100, exceeded_threshold=False)
        collector.record_injection_token_count(600, exceeded_threshold=True)
        collector.record_injection_token_count(700, exceeded_threshold=True)

        assert collector._threshold_exceedances == 2

    def test_record_parsing_time(self, collector: MetricsCollector) -> None:
        """Parsing times should be recorded."""
        collector.record_parsing_time_ms(10)
        collector.record_parsing_time_ms(20)
        collector.record_parsing_time_ms(15)

        assert collector._parsing_times_ms == [10, 20, 15]

    def test_record_injection_latency(self, collector: MetricsCollector) -> None:
        """Injection latencies should be recorded."""
        collector.record_injection_latency_ms(5)
        collector.record_injection_latency_ms(10)

        assert collector._injection_latencies_ms == [5, 10]

    def test_record_file_read(self, collector: MetricsCollector) -> None:
        """File reads should be counted."""
        collector.record_file_read("/path/to/file1.py")
        collector.record_file_read("/path/to/file1.py")
        collector.record_file_read("/path/to/file2.py")

        assert collector._file_read_counts["/path/to/file1.py"] == 2
        assert collector._file_read_counts["/path/to/file2.py"] == 1

    def test_record_file_read_with_anonymization(self, temp_dir: Path) -> None:
        """File reads should be anonymized when enabled."""
        collector = MetricsCollector(log_dir=temp_dir, anonymize_paths=True)
        collector.record_file_read("/path/to/file.py")

        # Key should be anonymized
        keys = list(collector._file_read_counts.keys())
        assert len(keys) == 1
        assert keys[0].startswith("file_")

    def test_record_identifier_resolution(self, collector: MetricsCollector) -> None:
        """Identifier resolution should be tracked."""
        collector.record_identifier_resolution(resolved_to_import=True)
        collector.record_identifier_resolution(resolved_to_local=True)
        collector.record_identifier_resolution(resolved_to_builtin=True)
        collector.record_identifier_resolution(unresolved=True, needed_for_context=True)

        assert collector._identifier_resolution.function_calls_analyzed == 4
        assert collector._identifier_resolution.resolved_to_imports == 1
        assert collector._identifier_resolution.resolved_to_local == 1
        assert collector._identifier_resolution.resolved_to_builtin == 1
        assert collector._identifier_resolution.unresolved == 1
        assert collector._identifier_resolution.unresolved_needed_for_context == 1

    def test_set_configuration(self, collector: MetricsCollector) -> None:
        """Configuration should be captured."""
        config = {"cache_size_limit_kb": 50, "context_token_limit": 500}
        collector.set_configuration(config)

        assert collector._configuration == config

    def test_get_re_read_patterns(self, collector: MetricsCollector) -> None:
        """Re-read patterns should return files read multiple times."""
        # File read once - should not appear
        collector.record_file_read("/path/to/file1.py")

        # Files read multiple times - should appear
        for _ in range(5):
            collector.record_file_read("/path/to/file2.py")
        for _ in range(3):
            collector.record_file_read("/path/to/file3.py")

        patterns = collector.get_re_read_patterns(top_n=10)

        # Should only include files read more than once
        assert len(patterns) == 2

        # Should be sorted by count descending
        assert patterns[0]["file"] == "/path/to/file2.py"
        assert patterns[0]["read_count"] == 5
        assert patterns[1]["file"] == "/path/to/file3.py"
        assert patterns[1]["read_count"] == 3

    def test_collect_cache_metrics(self, collector: MetricsCollector) -> None:
        """Cache metrics should be collected from mock cache."""
        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 75
        mock_stats.misses = 20
        mock_stats.staleness_refreshes = 5
        mock_stats.peak_size_bytes = 48000
        mock_stats.evictions_lru = 10
        mock_cache.get_statistics.return_value = mock_stats

        metrics = collector.collect_cache_metrics(mock_cache)

        assert metrics.hit_rate == 0.75
        assert metrics.miss_rate == 0.20
        assert metrics.total_reads == 100
        assert metrics.cache_hits == 75
        assert metrics.cache_misses == 20
        assert metrics.staleness_refreshes == 5
        assert metrics.peak_size_kb == pytest.approx(46.875, rel=0.01)
        assert metrics.evictions_lru == 10

    def test_collect_injection_metrics(self, collector: MetricsCollector) -> None:
        """Injection metrics should be collected from mock logger."""
        # Record some token counts
        collector.record_injection_token_count(100)
        collector.record_injection_token_count(200)
        collector.record_injection_token_count(300, exceeded_threshold=True)

        mock_logger = MagicMock()
        mock_stats = MagicMock()
        mock_stats.total_injections = 3
        mock_logger.get_statistics.return_value = mock_stats

        metrics = collector.collect_injection_metrics(mock_logger)

        assert metrics.total_injections == 3
        assert metrics.token_counts.min == 100
        assert metrics.token_counts.max == 300
        assert metrics.token_counts.median == 200
        assert metrics.threshold_exceedances == 1

    def test_collect_warning_metrics(self, collector: MetricsCollector) -> None:
        """Warning metrics should be collected from mock logger."""
        mock_logger = MagicMock()
        mock_stats = MagicMock()
        mock_stats.total_warnings = 10
        mock_stats.by_type = {"dynamic_dispatch": 5, "exec_eval": 3}
        mock_stats.files_with_most_warnings = [{"file": "/path/legacy.py", "warning_count": 4}]
        mock_logger.get_statistics.return_value = mock_stats

        metrics = collector.collect_warning_metrics(mock_logger)

        assert metrics.total_warnings == 10
        assert metrics.by_type["dynamic_dispatch"] == 5
        assert len(metrics.files_with_most_warnings) == 1
        assert metrics.files_with_most_warnings[0]["file"] == "/path/legacy.py"

    def test_collect_warning_metrics_with_anonymization(self, temp_dir: Path) -> None:
        """Warning metrics should anonymize file paths when enabled."""
        collector = MetricsCollector(log_dir=temp_dir, anonymize_paths=True)

        mock_logger = MagicMock()
        mock_stats = MagicMock()
        mock_stats.total_warnings = 5
        mock_stats.by_type = {}
        mock_stats.files_with_most_warnings = [{"file": "/path/legacy.py", "warning_count": 4}]
        mock_logger.get_statistics.return_value = mock_stats

        metrics = collector.collect_warning_metrics(mock_logger)

        # File path should be anonymized
        assert metrics.files_with_most_warnings[0]["file"].startswith("file_")

    def test_collect_graph_metrics(self, collector: MetricsCollector) -> None:
        """Graph metrics should be collected from mock graph."""
        # Create mock relationships
        mock_rel1 = MagicMock()
        mock_rel1.source_file = "/src/a.py"
        mock_rel1.target_file = "/src/utils.py"
        mock_rel1.target_symbol = "helper_func"

        mock_rel2 = MagicMock()
        mock_rel2.source_file = "/src/b.py"
        mock_rel2.target_file = "/src/utils.py"
        mock_rel2.target_symbol = "helper_func"

        mock_rel3 = MagicMock()
        mock_rel3.source_file = "/src/c.py"
        mock_rel3.target_file = "/src/base.py"
        mock_rel3.target_symbol = "BaseClass"

        mock_graph = MagicMock()
        mock_graph.get_all_relationships.return_value = [mock_rel1, mock_rel2, mock_rel3]

        graph_metrics, usage_dist = collector.collect_graph_metrics(mock_graph)

        # 4 unique files: a.py, b.py, c.py, utils.py, base.py
        # Note: utils.py appears as target twice, base.py once
        assert graph_metrics.total_files == 5  # a, b, c, utils, base
        assert graph_metrics.total_relationships == 3

        # Most connected should include utils.py with count 2
        connected_files = {
            f["file"]: f["dependency_count"] for f in graph_metrics.most_connected_files
        }
        assert "/src/utils.py" in connected_files
        assert connected_files["/src/utils.py"] == 2

        # Function usage: helper_func used in 2 files (a.py, b.py), BaseClass in 1 file
        assert usage_dist.files_1_to_3 == 2  # helper_func (2 files) and BaseClass (1 file)

    def test_build_session_metrics(self, collector: MetricsCollector) -> None:
        """build_session_metrics should aggregate all metrics."""
        # Set up configuration
        collector.set_configuration({"cache_size_limit_kb": 50})

        # Record some data
        collector.record_injection_token_count(100)
        collector.record_parsing_time_ms(20)
        collector.record_file_read("/path/to/file.py")
        collector.record_file_read("/path/to/file.py")

        # Build metrics
        metrics = collector.build_session_metrics()

        assert metrics.session_id == collector.get_session_id()
        assert metrics.start_time  # Should have start time
        assert metrics.end_time  # Should have end time
        assert metrics.configuration["cache_size_limit_kb"] == 50

        # Performance metrics should include parsing times
        assert metrics.performance.parsing_time_ms.min == 20
        assert metrics.performance.parsing_time_ms.max == 20

        # Re-read patterns should include the file
        assert len(metrics.re_read_patterns) == 1
        assert metrics.re_read_patterns[0]["file"] == "/path/to/file.py"
        assert metrics.re_read_patterns[0]["read_count"] == 2

    def test_write_metrics(self, collector: MetricsCollector, temp_dir: Path) -> None:
        """write_metrics should write JSONL to file."""
        metrics = SessionMetrics(
            session_id="test-session",
            start_time="2025-01-15T10:00:00.000Z",
            end_time="2025-01-15T12:00:00.000Z",
            configuration={"cache_size_limit_kb": 50},
        )

        collector.write_metrics(metrics)

        # Check file was created
        log_path = collector.get_log_path()
        assert log_path.exists()

        # Check content is valid JSONL
        with open(log_path) as f:
            line = f.readline()
            data = json.loads(line)
            assert data["session_id"] == "test-session"

    def test_finalize_and_write(self, temp_dir: Path) -> None:
        """finalize_and_write should build and write metrics."""
        collector = MetricsCollector(log_dir=temp_dir)
        collector.set_configuration({"test": True})

        # Create mock components
        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 10
        mock_stats.misses = 5
        mock_stats.staleness_refreshes = 2
        mock_stats.peak_size_bytes = 1024
        mock_stats.evictions_lru = 0
        mock_cache.get_statistics.return_value = mock_stats

        mock_injection_logger = MagicMock()
        mock_inj_stats = MagicMock()
        mock_inj_stats.total_injections = 5
        mock_injection_logger.get_statistics.return_value = mock_inj_stats

        mock_warning_logger = MagicMock()
        mock_warn_stats = MagicMock()
        mock_warn_stats.total_warnings = 2
        mock_warn_stats.by_type = {}
        mock_warn_stats.files_with_most_warnings = []
        mock_warning_logger.get_statistics.return_value = mock_warn_stats

        mock_graph = MagicMock()
        mock_graph.get_all_relationships.return_value = []

        # Finalize and write
        metrics = collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Verify metrics
        assert metrics.session_id == collector.get_session_id()
        assert metrics.cache_performance.cache_hits == 10
        assert metrics.context_injection.total_injections == 5
        assert metrics.warnings.total_warnings == 2

        # Verify file was written
        log_path = collector.get_log_path()
        assert log_path.exists()

    def test_multiple_sessions_append(self, temp_dir: Path) -> None:
        """Multiple sessions should append to same file."""
        # First session
        collector1 = MetricsCollector(log_dir=temp_dir, session_id="session-1")
        metrics1 = collector1.build_session_metrics()
        collector1.write_metrics(metrics1)

        # Second session
        collector2 = MetricsCollector(log_dir=temp_dir, session_id="session-2")
        metrics2 = collector2.build_session_metrics()
        collector2.write_metrics(metrics2)

        # Verify both sessions in file
        log_path = collector1.get_log_path()
        with open(log_path) as f:
            lines = f.readlines()
            assert len(lines) == 2

            data1 = json.loads(lines[0])
            data2 = json.loads(lines[1])
            assert data1["session_id"] == "session-1"
            assert data2["session_id"] == "session-2"


class TestReadSessionMetrics:
    """Tests for read_session_metrics function."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_read_nonexistent_file(self, temp_dir: Path) -> None:
        """Reading nonexistent file should return empty list."""
        log_path = temp_dir / "nonexistent.jsonl"
        result = read_session_metrics(log_path)
        assert result == []

    def test_read_empty_file(self, temp_dir: Path) -> None:
        """Reading empty file should return empty list."""
        log_path = temp_dir / "empty.jsonl"
        log_path.touch()
        result = read_session_metrics(log_path)
        assert result == []

    def test_read_single_session(self, temp_dir: Path) -> None:
        """Reading single session should work correctly."""
        # Write a session
        collector = MetricsCollector(log_dir=temp_dir, session_id="test-session")
        collector.set_configuration({"cache_size_limit_kb": 50})
        metrics = collector.build_session_metrics()
        collector.write_metrics(metrics)

        # Read it back
        result = read_session_metrics(collector.get_log_path())

        assert len(result) == 1
        assert result[0].session_id == "test-session"
        assert result[0].configuration["cache_size_limit_kb"] == 50

    def test_read_multiple_sessions(self, temp_dir: Path) -> None:
        """Reading multiple sessions should work correctly."""
        log_path = temp_dir / "session_metrics.jsonl"

        # Write multiple sessions
        for i in range(3):
            collector = MetricsCollector(log_dir=temp_dir, session_id=f"session-{i}")
            metrics = collector.build_session_metrics()
            collector.write_metrics(metrics)

        # Read all
        result = read_session_metrics(log_path)

        assert len(result) == 3
        assert result[0].session_id == "session-0"
        assert result[1].session_id == "session-1"
        assert result[2].session_id == "session-2"

    def test_read_with_limit(self, temp_dir: Path) -> None:
        """Reading with limit should respect limit."""
        log_path = temp_dir / "session_metrics.jsonl"

        # Write multiple sessions
        for i in range(5):
            collector = MetricsCollector(log_dir=temp_dir, session_id=f"session-{i}")
            metrics = collector.build_session_metrics()
            collector.write_metrics(metrics)

        # Read with limit
        result = read_session_metrics(log_path, limit=2)

        assert len(result) == 2
        assert result[0].session_id == "session-0"
        assert result[1].session_id == "session-1"

    def test_read_with_nested_metrics(self, temp_dir: Path) -> None:
        """Reading should correctly parse nested metrics."""
        log_path = temp_dir / "session_metrics.jsonl"

        # Create metrics with nested data
        collector = MetricsCollector(log_dir=temp_dir, session_id="nested-test")
        collector.record_injection_token_count(100)
        collector.record_injection_token_count(200)
        collector.record_injection_token_count(300)

        # Create mock components
        mock_cache = MagicMock()
        mock_stats = MagicMock()
        mock_stats.hits = 50
        mock_stats.misses = 10
        mock_stats.staleness_refreshes = 5
        mock_stats.peak_size_bytes = 2048
        mock_stats.evictions_lru = 2
        mock_cache.get_statistics.return_value = mock_stats

        mock_injection_logger = MagicMock()
        mock_inj_stats = MagicMock()
        mock_inj_stats.total_injections = 3
        mock_injection_logger.get_statistics.return_value = mock_inj_stats

        mock_warning_logger = MagicMock()
        mock_warn_stats = MagicMock()
        mock_warn_stats.total_warnings = 5
        mock_warn_stats.by_type = {"exec_eval": 3, "dynamic_dispatch": 2}
        mock_warn_stats.files_with_most_warnings = []
        mock_warning_logger.get_statistics.return_value = mock_warn_stats

        mock_graph = MagicMock()
        mock_graph.get_all_relationships.return_value = []

        collector.finalize_and_write(
            cache=mock_cache,
            injection_logger=mock_injection_logger,
            warning_logger=mock_warning_logger,
            graph=mock_graph,
        )

        # Read back
        result = read_session_metrics(log_path)

        assert len(result) == 1
        session = result[0]

        # Verify cache performance
        assert session.cache_performance.cache_hits == 50
        assert session.cache_performance.cache_misses == 10

        # Verify context injection
        assert session.context_injection.total_injections == 3
        assert session.context_injection.token_counts.min == 100
        assert session.context_injection.token_counts.max == 300

        # Verify warnings
        assert session.warnings.total_warnings == 5
        assert session.warnings.by_type["exec_eval"] == 3


class TestMetricsCollectorContextManager:
    """Tests for MetricsCollector context manager functionality."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_context_manager_basic(self, temp_dir: Path) -> None:
        """Context manager should work for basic usage."""
        with MetricsCollector(log_dir=temp_dir) as collector:
            collector.record_injection_token_count(100)
            assert collector._token_counts == [100]

    def test_context_manager_does_not_auto_write(self, temp_dir: Path) -> None:
        """Context manager should NOT auto-write metrics on exit."""
        with MetricsCollector(log_dir=temp_dir) as collector:
            collector.record_injection_token_count(100)
            log_path = collector.get_log_path()

        # File should not exist (no auto-write)
        assert not log_path.exists()
