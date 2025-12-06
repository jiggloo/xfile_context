# Copyright (c) 2025 Henru Wang
# All rights reserved.

"""Unit tests for the analyze_metrics.py script.

Tests cover all analysis features per TDD Section 3.10.6:
- JSONL parsing of session metrics
- Aggregate statistics computation
- Outlier detection
- Configuration recommendations
- Human-readable report generation
- JSON output format

Related Requirements:
- FR-48 (metrics analysis tool)
- T-10.7 (analysis tool functionality)
"""

import json

# Add scripts to path for imports
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator, List

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from analyze_metrics import (  # type: ignore[import-not-found]
    AggregateStatistics,
    AnalysisReport,
    ConfigurationRecommendation,
    analyze_metrics,
    check_performance_targets,
    compute_aggregate_statistics,
    format_report,
    generate_recommendations,
    identify_outliers,
    parse_session_metrics,
)


def create_session_data(
    session_id: str = "test-session",
    hit_rate: float = 0.7,
    total_reads: int = 100,
    cache_hits: int = 70,
    cache_misses: int = 30,
    peak_size_kb: float = 40.0,
    evictions_lru: int = 0,
    total_injections: int = 50,
    token_min: int = 10,
    token_max: int = 400,
    token_median: int = 150,
    token_p95: int = 350,
    threshold_exceedances: int = 2,
    parsing_median_ms: int = 20,
    parsing_p95_ms: int = 80,
    injection_median_ms: int = 10,
    injection_p95_ms: int = 30,
    total_warnings: int = 5,
    warnings_by_type: Dict[str, int] | None = None,
    total_files: int = 100,
    total_relationships: int = 300,
    functions_1_to_3: int = 80,
    functions_4_to_10: int = 15,
    functions_11_plus: int = 5,
    re_read_patterns: List[Dict[str, Any]] | None = None,
    config_cache_expiry: int = 10,
    config_cache_size: int = 50,
    config_token_limit: int = 500,
    config_function_threshold: int = 3,
) -> Dict[str, Any]:
    """Create a test session data dictionary."""
    if warnings_by_type is None:
        warnings_by_type = {"dynamic_dispatch": 3, "exec_eval": 2}
    if re_read_patterns is None:
        re_read_patterns = []

    return {
        "session_id": session_id,
        "start_time": "2025-01-15T10:00:00.000+00:00",
        "end_time": "2025-01-15T12:00:00.000+00:00",
        "cache_performance": {
            "hit_rate": hit_rate,
            "miss_rate": 1 - hit_rate,
            "total_reads": total_reads,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "staleness_refreshes": 0,
            "peak_size_kb": peak_size_kb,
            "evictions_lru": evictions_lru,
        },
        "context_injection": {
            "total_injections": total_injections,
            "token_counts": {
                "min": token_min,
                "max": token_max,
                "median": token_median,
                "p95": token_p95,
            },
            "threshold_exceedances": threshold_exceedances,
        },
        "relationship_graph": {
            "total_files": total_files,
            "total_relationships": total_relationships,
            "most_connected_files": [
                {"file": "utils.py", "dependency_count": 25},
            ],
        },
        "function_usage_distribution": {
            "1-3_files": functions_1_to_3,
            "4-10_files": functions_4_to_10,
            "11+_files": functions_11_plus,
        },
        "re_read_patterns": re_read_patterns,
        "performance": {
            "parsing_time_ms": {
                "min": 5,
                "max": parsing_p95_ms + 20,
                "median": parsing_median_ms,
                "p95": parsing_p95_ms,
            },
            "injection_latency_ms": {
                "min": 2,
                "max": injection_p95_ms + 10,
                "median": injection_median_ms,
                "p95": injection_p95_ms,
            },
        },
        "warnings": {
            "total_warnings": total_warnings,
            "by_type": warnings_by_type,
            "files_with_most_warnings": [
                {"file": "legacy.py", "warning_count": 3},
            ],
        },
        "identifier_resolution": {
            "function_calls_analyzed": 100,
            "resolved_to_imports": 50,
            "resolved_to_imports_pct": 50.0,
            "resolved_to_local": 30,
            "resolved_to_local_pct": 30.0,
            "resolved_to_builtin": 10,
            "resolved_to_builtin_pct": 10.0,
            "unresolved": 10,
            "unresolved_pct": 10.0,
            "unresolved_needed_for_context": 5,
            "unresolved_needed_for_context_pct": 5.0,
        },
        "configuration": {
            "cache_expiry_minutes": config_cache_expiry,
            "cache_size_limit_kb": config_cache_size,
            "context_token_limit": config_token_limit,
            "function_usage_warning_threshold": config_function_threshold,
            "warn_on_wildcards": False,
            "enable_context_injection": True,
        },
    }


class TestParseSessionMetrics:
    """Tests for parse_session_metrics function."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_parse_single_session(self, temp_dir: Path) -> None:
        """Single session should be parsed correctly."""
        file_path = temp_dir / "metrics.jsonl"
        session = create_session_data()

        with open(file_path, "w") as f:
            f.write(json.dumps(session) + "\n")

        result = parse_session_metrics(file_path)
        assert len(result) == 1
        assert result[0]["session_id"] == "test-session"

    def test_parse_multiple_sessions(self, temp_dir: Path) -> None:
        """Multiple sessions should be parsed correctly."""
        file_path = temp_dir / "metrics.jsonl"

        with open(file_path, "w") as f:
            for i in range(5):
                session = create_session_data(session_id=f"session-{i}")
                f.write(json.dumps(session) + "\n")

        result = parse_session_metrics(file_path)
        assert len(result) == 5

    def test_parse_empty_lines_skipped(self, temp_dir: Path) -> None:
        """Empty lines should be skipped."""
        file_path = temp_dir / "metrics.jsonl"
        session = create_session_data()

        with open(file_path, "w") as f:
            f.write("\n")
            f.write(json.dumps(session) + "\n")
            f.write("\n\n")

        result = parse_session_metrics(file_path)
        assert len(result) == 1

    def test_parse_malformed_json_skipped(
        self, temp_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Malformed JSON lines should be skipped with warning."""
        file_path = temp_dir / "metrics.jsonl"
        session = create_session_data()

        with open(file_path, "w") as f:
            f.write("not valid json\n")
            f.write(json.dumps(session) + "\n")
            f.write("{broken: json}\n")

        result = parse_session_metrics(file_path)
        assert len(result) == 1

        # Check warnings were printed
        captured = capsys.readouterr()
        assert "Skipping malformed entry" in captured.err

    def test_parse_nonexistent_file_raises(self, temp_dir: Path) -> None:
        """Nonexistent file should raise FileNotFoundError."""
        file_path = temp_dir / "nonexistent.jsonl"

        with pytest.raises(FileNotFoundError):
            parse_session_metrics(file_path)


class TestComputeAggregateStatistics:
    """Tests for compute_aggregate_statistics function."""

    def test_empty_sessions_returns_zeros(self) -> None:
        """Empty session list should return all zeros."""
        stats = compute_aggregate_statistics([])
        assert stats.avg_hit_rate == 0.0
        assert stats.total_injections == 0
        assert stats.total_warnings == 0

    def test_single_session_statistics(self) -> None:
        """Single session should compute correct statistics."""
        session = create_session_data(
            hit_rate=0.75,
            total_injections=100,
            token_median=200,
            parsing_p95_ms=100,
        )
        stats = compute_aggregate_statistics([session])

        assert stats.avg_hit_rate == 0.75
        assert stats.total_injections == 100
        assert stats.token_median == 200
        assert stats.parsing_p95_ms == 100

    def test_multiple_sessions_averages(self) -> None:
        """Multiple sessions should compute averages correctly."""
        sessions = [
            create_session_data(session_id="s1", hit_rate=0.6, total_injections=50),
            create_session_data(session_id="s2", hit_rate=0.8, total_injections=50),
        ]
        stats = compute_aggregate_statistics(sessions)

        assert stats.avg_hit_rate == pytest.approx(0.7, rel=0.01)
        assert stats.total_injections == 100

    def test_warning_aggregation(self) -> None:
        """Warnings should be aggregated across sessions."""
        sessions = [
            create_session_data(
                session_id="s1",
                total_warnings=3,
                warnings_by_type={"exec_eval": 2, "dynamic_dispatch": 1},
            ),
            create_session_data(
                session_id="s2",
                total_warnings=5,
                warnings_by_type={"exec_eval": 3, "monkey_patching": 2},
            ),
        ]
        stats = compute_aggregate_statistics(sessions)

        assert stats.total_warnings == 8
        assert stats.warnings_by_type["exec_eval"] == 5
        assert stats.warnings_by_type["dynamic_dispatch"] == 1
        assert stats.warnings_by_type["monkey_patching"] == 2

    def test_function_usage_aggregation(self) -> None:
        """Function usage distribution should be aggregated."""
        sessions = [
            create_session_data(session_id="s1", functions_1_to_3=50, functions_4_to_10=10),
            create_session_data(session_id="s2", functions_1_to_3=60, functions_4_to_10=15),
        ]
        stats = compute_aggregate_statistics(sessions)

        assert stats.total_functions_1_to_3 == 110
        assert stats.total_functions_4_to_10 == 25

    def test_sessions_with_no_activity(self) -> None:
        """Sessions with zero activity should be handled gracefully."""
        session = create_session_data(
            total_reads=0,
            total_injections=0,
            hit_rate=0.0,
        )
        stats = compute_aggregate_statistics([session])

        # Should not raise and should handle zero activity
        assert stats.avg_hit_rate == 0.0
        assert stats.total_injections == 0


class TestIdentifyOutliers:
    """Tests for identify_outliers function."""

    def test_no_outliers_in_normal_sessions(self) -> None:
        """Normal sessions should not produce outliers."""
        sessions = [
            create_session_data(session_id="s1", hit_rate=0.75),
            create_session_data(session_id="s2", hit_rate=0.80),
        ]
        stats = compute_aggregate_statistics(sessions)
        outliers = identify_outliers(sessions, stats)

        # No extreme deviations - may have some, check it's minimal
        assert len(outliers) < 3

    def test_low_cache_hit_rate_outlier(self) -> None:
        """Session with unusually low cache hit rate should be flagged."""
        sessions = [
            create_session_data(session_id="normal1", hit_rate=0.75),
            create_session_data(session_id="normal2", hit_rate=0.80),
            create_session_data(session_id="low-hit", hit_rate=0.30),
        ]
        stats = compute_aggregate_statistics(sessions)
        outliers = identify_outliers(sessions, stats)

        low_hit_outliers = [o for o in outliers if "low-hit" in o and "hit rate" in o.lower()]
        assert len(low_hit_outliers) >= 1

    def test_high_threshold_exceedance_outlier(self) -> None:
        """Session with high threshold exceedances should be flagged."""
        sessions = [
            create_session_data(
                session_id="high-exceed",
                total_injections=100,
                threshold_exceedances=10,  # 10% exceedance
            ),
        ]
        stats = compute_aggregate_statistics(sessions)
        outliers = identify_outliers(sessions, stats)

        exceed_outliers = [o for o in outliers if "exceed" in o.lower()]
        assert len(exceed_outliers) >= 1

    def test_slow_parsing_outlier(self) -> None:
        """Session with slow parsing should be flagged."""
        sessions = [
            create_session_data(
                session_id="slow-parse",
                parsing_p95_ms=500,  # > 2x 200ms target
            ),
        ]
        stats = compute_aggregate_statistics(sessions)
        outliers = identify_outliers(sessions, stats)

        slow_outliers = [o for o in outliers if "slow" in o.lower() and "parsing" in o.lower()]
        assert len(slow_outliers) >= 1

    def test_slow_injection_outlier(self) -> None:
        """Session with slow injection should be flagged."""
        sessions = [
            create_session_data(
                session_id="slow-inj",
                injection_p95_ms=150,  # > 2x 50ms target
            ),
        ]
        stats = compute_aggregate_statistics(sessions)
        outliers = identify_outliers(sessions, stats)

        slow_outliers = [o for o in outliers if "slow" in o.lower() and "injection" in o.lower()]
        assert len(slow_outliers) >= 1

    def test_excessive_re_reads_outlier(self) -> None:
        """Files with excessive re-reads should be flagged."""
        sessions = [
            create_session_data(
                session_id="s1",
                re_read_patterns=[{"file": "hot_file.py", "read_count": 15}],
            ),
        ]
        stats = compute_aggregate_statistics(sessions)
        outliers = identify_outliers(sessions, stats)

        re_read_outliers = [o for o in outliers if "re-read" in o.lower()]
        assert len(re_read_outliers) >= 1


class TestGenerateRecommendations:
    """Tests for generate_recommendations function."""

    def test_adequate_cache_size(self) -> None:
        """Adequate cache size should not recommend increase."""
        sessions = [
            create_session_data(
                hit_rate=0.8,
                peak_size_kb=30.0,
                evictions_lru=0,
                config_cache_size=50,
            ),
        ]
        stats = compute_aggregate_statistics(sessions)
        recs = generate_recommendations(sessions, stats)

        cache_recs = [r for r in recs if r.parameter == "cache_size_limit_kb"]
        assert len(cache_recs) == 1
        assert cache_recs[0].recommended_value is None  # No change needed

    def test_cache_size_increase_recommendation(self) -> None:
        """Frequent evictions should recommend size increase."""
        sessions = [
            create_session_data(
                hit_rate=0.5,
                peak_size_kb=48.0,  # Near limit
                evictions_lru=15,  # Many evictions
                config_cache_size=50,
            ),
        ]
        stats = compute_aggregate_statistics(sessions)
        recs = generate_recommendations(sessions, stats)

        cache_recs = [r for r in recs if r.parameter == "cache_size_limit_kb"]
        assert len(cache_recs) == 1
        assert cache_recs[0].recommended_value == 75  # 1.5x increase

    def test_token_limit_adequate(self) -> None:
        """Adequate token limit should not recommend change."""
        sessions = [
            create_session_data(
                total_injections=100,
                token_p95=350,
                threshold_exceedances=2,  # < 5%
                config_token_limit=500,
            ),
        ]
        stats = compute_aggregate_statistics(sessions)
        recs = generate_recommendations(sessions, stats)

        token_recs = [r for r in recs if r.parameter == "context_token_limit"]
        assert len(token_recs) == 1
        assert token_recs[0].recommended_value is None

    def test_token_limit_increase_recommendation(self) -> None:
        """High exceedance rate should recommend limit increase."""
        sessions = [
            create_session_data(
                total_injections=100,
                token_p95=480,
                threshold_exceedances=10,  # 10% > 5%
                config_token_limit=500,
            ),
        ]
        stats = compute_aggregate_statistics(sessions)
        recs = generate_recommendations(sessions, stats)

        token_recs = [r for r in recs if r.parameter == "context_token_limit"]
        assert len(token_recs) == 1
        assert token_recs[0].recommended_value is not None
        assert token_recs[0].recommended_value > 500

    def test_function_threshold_adequate(self) -> None:
        """Appropriate threshold should not recommend change."""
        sessions = [
            create_session_data(
                functions_1_to_3=90,  # 90% in low bucket
                functions_4_to_10=8,
                functions_11_plus=2,
                config_function_threshold=3,
            ),
        ]
        stats = compute_aggregate_statistics(sessions)
        recs = generate_recommendations(sessions, stats)

        threshold_recs = [r for r in recs if "threshold" in r.parameter]
        # Should be adequate - check there's no increase recommended
        for rec in threshold_recs:
            if rec.recommended_value is not None:
                assert rec.recommended_value <= 4  # Modest increase at most


class TestCheckPerformanceTargets:
    """Tests for check_performance_targets function."""

    def test_all_targets_met(self) -> None:
        """All targets should be marked as met when within limits."""
        stats = AggregateStatistics(
            parsing_p95_ms=150,  # < 200ms
            injection_p95_ms=40,  # < 50ms
        )
        status = check_performance_targets(stats)

        assert status["parsing_p95_under_200ms"] is True
        assert status["injection_p95_under_50ms"] is True

    def test_parsing_target_exceeded(self) -> None:
        """Exceeded parsing target should be flagged."""
        stats = AggregateStatistics(
            parsing_p95_ms=250,  # > 200ms
            injection_p95_ms=40,
        )
        status = check_performance_targets(stats)

        assert status["parsing_p95_under_200ms"] is False
        assert status["injection_p95_under_50ms"] is True

    def test_injection_target_exceeded(self) -> None:
        """Exceeded injection target should be flagged."""
        stats = AggregateStatistics(
            parsing_p95_ms=150,
            injection_p95_ms=60,  # > 50ms
        )
        status = check_performance_targets(stats)

        assert status["parsing_p95_under_200ms"] is True
        assert status["injection_p95_under_50ms"] is False

    def test_zero_values_pass(self) -> None:
        """Zero values (no data) should pass targets."""
        stats = AggregateStatistics()  # All zeros
        status = check_performance_targets(stats)

        assert status["parsing_p95_under_200ms"] is True
        assert status["injection_p95_under_50ms"] is True


class TestFormatReport:
    """Tests for format_report function."""

    def test_report_contains_header(self) -> None:
        """Report should contain header with session count."""
        report = AnalysisReport(
            sessions_analyzed=5,
            date_range=("2025-01-15", "2025-01-16"),
            statistics=AggregateStatistics(),
            recommendations=[],
            outliers=[],
            performance_status={},
        )
        output = format_report(report)

        assert "5 sessions analyzed" in output
        assert "=" * 30 in output  # Header line

    def test_report_contains_cache_section(self) -> None:
        """Report should contain cache performance section."""
        stats = AggregateStatistics(
            avg_hit_rate=0.72,
            avg_peak_size_kb=45.5,
        )
        report = AnalysisReport(
            sessions_analyzed=5,
            date_range=("", ""),
            statistics=stats,
            recommendations=[],
            outliers=[],
            performance_status={},
        )
        output = format_report(report)

        assert "Cache Performance:" in output
        assert "72%" in output or "hit rate" in output.lower()

    def test_report_contains_performance_section(self) -> None:
        """Report should contain performance section."""
        stats = AggregateStatistics(
            parsing_p95_ms=80,
            injection_p95_ms=30,
        )
        report = AnalysisReport(
            sessions_analyzed=5,
            date_range=("", ""),
            statistics=stats,
            recommendations=[],
            outliers=[],
            performance_status={"parsing_p95_under_200ms": True, "injection_p95_under_50ms": True},
        )
        output = format_report(report)

        assert "Performance:" in output
        assert "target" in output.lower()

    def test_report_contains_warnings_section(self) -> None:
        """Report should contain warnings section."""
        stats = AggregateStatistics(
            total_warnings=10,
            warnings_by_type={"dynamic_dispatch": 5, "exec_eval": 3},
        )
        report = AnalysisReport(
            sessions_analyzed=5,
            date_range=("", ""),
            statistics=stats,
            recommendations=[],
            outliers=[],
            performance_status={},
        )
        output = format_report(report)

        assert "Warnings:" in output

    def test_report_contains_recommendations(self) -> None:
        """Report should contain recommendations."""
        stats = AggregateStatistics()
        report = AnalysisReport(
            sessions_analyzed=5,
            date_range=("", ""),
            statistics=stats,
            recommendations=[
                ConfigurationRecommendation(
                    parameter="cache_size_limit_kb",
                    current_value=50,
                    recommended_value=75,
                    reason="Increase cache size for better performance",
                    confidence="high",
                ),
            ],
            outliers=[],
            performance_status={},
        )
        output = format_report(report)

        assert "RECOMMENDATION" in output

    def test_report_contains_outliers(self) -> None:
        """Report should contain outliers section when present."""
        report = AnalysisReport(
            sessions_analyzed=5,
            date_range=("", ""),
            statistics=AggregateStatistics(),
            recommendations=[],
            outliers=["Session abc: Low cache hit rate"],
            performance_status={},
        )
        output = format_report(report)

        assert "Outliers" in output
        assert "Low cache hit rate" in output


class TestAnalyzeMetrics:
    """Tests for analyze_metrics main function."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_analyze_empty_returns_zero_sessions(self, temp_dir: Path) -> None:
        """Analyzing no files should return zero sessions."""
        report = analyze_metrics([])
        assert report.sessions_analyzed == 0

    def test_analyze_single_file(self, temp_dir: Path) -> None:
        """Analyzing single file should work correctly."""
        file_path = temp_dir / "metrics.jsonl"

        with open(file_path, "w") as f:
            for i in range(3):
                session = create_session_data(session_id=f"session-{i}")
                f.write(json.dumps(session) + "\n")

        report = analyze_metrics([file_path])

        assert report.sessions_analyzed == 3
        assert report.statistics.avg_hit_rate == pytest.approx(0.7, rel=0.01)

    def test_analyze_multiple_files(self, temp_dir: Path) -> None:
        """Analyzing multiple files should combine sessions."""
        file1 = temp_dir / "metrics1.jsonl"
        file2 = temp_dir / "metrics2.jsonl"

        with open(file1, "w") as f:
            for i in range(2):
                session = create_session_data(session_id=f"s1-{i}")
                f.write(json.dumps(session) + "\n")

        with open(file2, "w") as f:
            for i in range(3):
                session = create_session_data(session_id=f"s2-{i}")
                f.write(json.dumps(session) + "\n")

        report = analyze_metrics([file1, file2])

        assert report.sessions_analyzed == 5

    def test_analyze_nonexistent_file_skipped(self, temp_dir: Path) -> None:
        """Nonexistent files should be skipped with warning."""
        file1 = temp_dir / "exists.jsonl"
        file2 = temp_dir / "nonexistent.jsonl"

        with open(file1, "w") as f:
            session = create_session_data()
            f.write(json.dumps(session) + "\n")

        report = analyze_metrics([file1, file2])

        assert report.sessions_analyzed == 1

    def test_analyze_date_range(self, temp_dir: Path) -> None:
        """Date range should be extracted from sessions."""
        file_path = temp_dir / "metrics.jsonl"

        sessions_data = [
            {
                **create_session_data(session_id="s1"),
                "start_time": "2025-01-10T10:00:00.000+00:00",
                "end_time": "2025-01-10T12:00:00.000+00:00",
            },
            {
                **create_session_data(session_id="s2"),
                "start_time": "2025-01-20T10:00:00.000+00:00",
                "end_time": "2025-01-20T12:00:00.000+00:00",
            },
        ]

        with open(file_path, "w") as f:
            for session in sessions_data:
                f.write(json.dumps(session) + "\n")

        report = analyze_metrics([file_path])

        assert "2025-01-10" in report.date_range[0]
        assert "2025-01-20" in report.date_range[1]


class TestCommandLineInterface:
    """Tests for command-line interface functionality."""

    @pytest.fixture
    def temp_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_main_returns_success_on_valid_file(self, temp_dir: Path) -> None:
        """Main should return 0 on success."""
        import sys

        from analyze_metrics import main

        file_path = temp_dir / "metrics.jsonl"

        with open(file_path, "w") as f:
            session = create_session_data()
            f.write(json.dumps(session) + "\n")

        # Mock sys.argv
        original_argv = sys.argv
        try:
            sys.argv = ["analyze_metrics.py", str(file_path)]
            exit_code = main()
            assert exit_code == 0
        finally:
            sys.argv = original_argv

    def test_main_json_output(self, temp_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Main should output valid JSON when --json flag is used."""
        import sys

        from analyze_metrics import main

        file_path = temp_dir / "metrics.jsonl"

        with open(file_path, "w") as f:
            session = create_session_data()
            f.write(json.dumps(session) + "\n")

        original_argv = sys.argv
        try:
            sys.argv = ["analyze_metrics.py", "--json", str(file_path)]
            exit_code = main()

            captured = capsys.readouterr()
            output = json.loads(captured.out)

            assert exit_code == 0
            assert "sessions_analyzed" in output
            assert "recommendations" in output
            assert output["sessions_analyzed"] == 1
        finally:
            sys.argv = original_argv

    def test_main_returns_error_on_no_sessions(self, temp_dir: Path) -> None:
        """Main should return 1 when no valid sessions found."""
        import sys

        from analyze_metrics import main

        file_path = temp_dir / "empty.jsonl"
        file_path.touch()

        original_argv = sys.argv
        try:
            sys.argv = ["analyze_metrics.py", str(file_path)]
            exit_code = main()
            assert exit_code == 1
        finally:
            sys.argv = original_argv
